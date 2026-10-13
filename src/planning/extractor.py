"""
extractor.py - Pyomo 모델 결과 추출 표준화

extract_results() : 논문/보고용 구조화 결과 (설치 노드, 용량, 비용, curtailment, CVaR)
extract_all()     : 모든 Variable → {이름: DataFrame} (범용 CSV 저장용)
"""

import logging

import numpy as np
import pandas as pd
import pyomo.environ as pyo

from src.data_process.network import DHN_PIPE_DATA, NUM_NODES, SLACK_BUS, BASE_MVA
from src.data_process.scenario_gen import compute_cvar
from src.planning.objective import pvifa_factor
from src.utils.config_loader import get

logger = logging.getLogger("cired")


def _val(var):
    """pyo.value 안전 래퍼 (미초기화 시 0.0)."""
    try:
        v = pyo.value(var, exception=False)
        return float(v) if v is not None else 0.0
    except Exception:                                  # noqa: BLE001
        return 0.0


def extract_results(model: pyo.ConcreteModel, config: dict, data: dict) -> dict:
    """구조화된 결과 dict 반환."""
    sc = data["scenario"]
    probs = np.asarray(sc["probs"], dtype=float)
    S = len(probs)
    comps = config.get("components", {})
    chp_enabled = comps.get("chp", True)
    dhn_enabled = comps.get("dhn", False)
    ny = get(config, "planning.horizon_years", 15)
    rec = get(config, "market.rec_price", 70_000)
    alpha = get(config, "planning.alpha", 0.95)

    # ── 설치 결과 ─────────────────────────────────────────
    pv_sites = {n: {"cap_MWp": round(_val(model.cap_pv[n]), 4)}
                for n in model.N_pv if _val(model.inv_pv[n]) > 0.5
                and _val(model.cap_pv[n]) > 1e-4}
    ess_sites = {n: {"P_MW": round(_val(model.cap_ess_p[n]), 4),
                     "E_MWh": round(_val(model.cap_ess_e[n]), 4)}
                 for n in model.N_ess if _val(model.inv_ess[n]) > 0.5
                 and _val(model.cap_ess_p[n]) > 1e-4}

    chp_sites = {}
    if chp_enabled:
        alpha_chp = get(config, "chp.eta_heat", 0.50) / get(config, "chp.eta_elec", 0.35)
        for n in model.N_chp:
            if _val(model.inv_chp[n]) > 0.5 and _val(model.cap_chp[n]) > 1e-4:
                pe = _val(model.cap_chp[n])
                chp_sites[n] = {
                    "P_e_MW": round(pe, 4),
                    "P_h_MW": round(pe * alpha_chp, 4),
                    "P_boiler_MW": round(_val(model.cap_boiler[n]), 4),
                    "E_tes_MWh": round(_val(model.cap_tes[n]), 4),
                }

    # ── curtailment (확률 가중) ──────────────────────────────
    # potential 은 모델의 실제 출력 상한(= cap×deg×profile)과 일치시켜야 한다.
    # deg(열화계수) 미반영 시 (1-deg)≈3.5%가 가짜 curtailment로 잡힘.
    d_pv = get(config, "pv.degradation_rate", 0.0)
    deg = (1.0 - (1.0 - d_pv) ** ny) / (ny * d_pv) if (d_pv > 0 and ny > 1) else 1.0
    total_pot = total_act = daily_pv_avg = 0.0
    for s in range(S):
        s_pv = 0.0
        for n in model.N_pv:
            cap = _val(model.cap_pv[n])
            for t in range(24):
                pot = cap * deg * float(sc["pv"][s, t])
                act = _val(model.p_pv[s, n, t])
                total_pot += probs[s] * pot
                total_act += probs[s] * act
                s_pv += act
        daily_pv_avg += probs[s] * s_pv
    curt_pct = ((total_pot - total_act) / total_pot * 100) if total_pot > 1e-9 else 0.0
    # REC 수익도 목적함수와 동일하게 PVIFA 로 할인 (비할인 ny 를 쓰면 약 40% 과대보고)
    rec_revenue = daily_pv_avg * 365 * pvifa_factor(
        get(config, "planning.discount_rate", 0.045), ny) * rec

    # ── 비용 / 리스크 ─────────────────────────────────────
    op_costs = np.array([_val(model.op_cost[s]) for s in range(S)])
    expected_op = float((probs * op_costs).sum())
    cvar_op = compute_cvar(op_costs, probs, alpha) if S > 1 else float(op_costs[0])
    invest = _val(model.invest_cost)

    dhn_results = _extract_dhn(model, config, S) if dhn_enabled else None

    results = {
        "status": "ok",
        "objective": _val(model.objective),
        "invest_cost": invest,
        "expected_op_cost": expected_op,
        "cvar_op_cost": cvar_op,
        "pv_sites": pv_sites,
        "ess_sites": ess_sites,
        "chp_sites": chp_sites,
        "total_PV_MWp": round(sum(v["cap_MWp"] for v in pv_sites.values()), 4),
        "total_P_MW": round(sum(v["P_MW"] for v in ess_sites.values()), 4),
        "total_E_MWh": round(sum(v["E_MWh"] for v in ess_sites.values()), 4),
        "total_CHP_MW": round(sum(v["P_e_MW"] for v in chp_sites.values()), 4),
        "total_boiler_MW": round(sum(v["P_boiler_MW"] for v in chp_sites.values()), 4),
        "total_TES_MWh": round(sum(v["E_tes_MWh"] for v in chp_sites.values()), 4),
        "n_tes_sites": sum(1 for v in chp_sites.values() if v["E_tes_MWh"] > 1e-4),
        "curtailment_pct": round(curt_pct, 2),
        "rec_revenue_억": round(rec_revenue / 1e8, 2),
        "n_ess_sites": len(ess_sites),
        "n_pv_sites": len(pv_sites),
        "n_chp_sites": len(chp_sites),
        "mode": get(config, "planning.mode", "stochastic"),
        "dhn": dhn_results,
    }
    return results


def _extract_dhn(model, config, S):
    """DHN 운영 결과 요약."""
    c_pipe = get(config, "dhn.cost.c_pipe", 1.146e9)
    om = get(config, "dhn.cost.om_rate", 0.015)
    ny = get(config, "planning.horizon_years", 15)
    total_len = float(DHN_PIPE_DATA[:, 2].sum())
    # c_pipe = 노선 단위(공급+환수 포함) → ×2 불필요.
    # O&M 은 목적함수와 동일하게 PVIFA 할인 (비할인 ny 사용 시 과대보고)
    invest = c_pipe * (1 + om * pvifa_factor(
        get(config, "planning.discount_rate", 0.045), ny)) * total_len

    n_pipes = len(DHN_PIPE_DATA)
    avg_flow = {
        l: round(float(np.mean([_val(model.q_pipe[s, l, t])
                                for s in range(S) for t in range(24)])), 4)
        for l in range(n_pipes)
    }
    return {
        "total_pipe_km": round(total_len, 2),
        "invest_cost_억": round(invest / 1e8, 2),
        "avg_pipe_flow_MW": avg_flow,
    }


def extract_variable(var: pyo.Var, name=None) -> pd.DataFrame:
    """Pyomo Variable → DataFrame (1~3차원 인덱스 지원)."""
    var_name = name or var.name
    records = []
    for index in var:
        val = pyo.value(var[index], exception=False)
        if val is None:
            continue
        idx = index if isinstance(index, tuple) else (index,)
        rec = {f"index_{i}": v for i, v in enumerate(idx)}
        rec[var_name] = val
        records.append(rec)
    return pd.DataFrame(records)


def extract_all(model: pyo.ConcreteModel) -> dict:
    """모든 Variable 을 {이름: DataFrame} 으로 추출."""
    out = {}
    for var in model.component_objects(pyo.Var, active=True):
        df = extract_variable(var)
        if not df.empty:
            out[var.name] = df
    return out


def compute_voltage_profile(model: pyo.ConcreteModel, data: dict,
                            chp_enabled: bool) -> dict:
    """solve된 model 에서 노드별×시간별 전압 [pu] 재구성 (LPF 감도식).

    grid.py 의 운영 전압식과 동일:
        V[s,i,t] = b_v[i] + Σ_j Av[i,j]·p_inj[j] + Σ_j Avq[i,j]·q_inj[j]   (i∈PQ)
        슬랙(SLACK_BUS) 은 1.0 pu (기준전압).
    Returns:
        {'V': (S,N,T) ndarray [pu], 'probs': (S,),
         'V_exp': (N,T) 확률가중 기대전압, 'V_min': (N,T) 시나리오 최저전압}
    """
    sc = data["scenario"]
    probs = np.asarray(sc["probs"], dtype=float)
    S = len(probs)
    pq = list(model.PQ)

    # 감도행렬·기준전압을 numpy 로 1회 추출 (Param 접근 최소화 → 벡터화)
    Av = np.array([[_val(model.Av[i, j]) for j in pq] for i in pq])    # (npq,npq) dV/dP
    Avq = np.array([[_val(model.Avq[i, j]) for j in pq] for i in pq])  # (npq,npq) dV/dQ
    bv = np.array([_val(model.bv[i]) for i in pq])                     # (npq,) 기준전압

    def p_inj(s, n, t):
        pv = _val(model.p_pv[s, n, t]) if n in model.N_pv else 0.0
        ch = _val(model.p_charge[s, n, t]) if n in model.N_ess else 0.0
        dis = _val(model.p_discharge[s, n, t]) if n in model.N_ess else 0.0
        chp = _val(model.p_chp_elec[s, n, t]) if (chp_enabled and n in model.N_chp) else 0.0
        return (pv + dis - ch - _val(model.elec_load[s, n, t]) + chp) / BASE_MVA

    def q_inj(s, n, t):
        qpv = _val(model.q_pv[s, n, t]) if n in model.N_pv else 0.0
        qess = _val(model.q_ess[s, n, t]) if n in model.N_ess else 0.0
        return (qpv + qess - _val(model.react_load[s, n, t])) / BASE_MVA

    V = np.ones((S, NUM_NODES, 24))
    for s in range(S):
        for t in range(24):
            pvec = np.array([p_inj(s, j, t) for j in pq])
            qvec = np.array([q_inj(s, j, t) for j in pq])
            v_pq = bv + Av @ pvec + Avq @ qvec
            for idx, i in enumerate(pq):
                V[s, i, t] = v_pq[idx]
            V[s, SLACK_BUS, t] = 1.0

    return {
        "V": V,
        "probs": probs,
        "V_exp": np.tensordot(probs, V, axes=(0, 0)),   # (N,T) 확률가중 기대
        "V_min": V.min(axis=0),                          # (N,T) 시나리오 최저
    }


def compute_cost_breakdown(model: pyo.ConcreteModel, config: dict,
                           chp_enabled: bool) -> dict:
    """확률가중 기대 운영비를 항목별 [원]으로 분해 (objective._operation_cost 와 1:1 대응).

    부호 규약: 비용(+) / 수익(−).  'total' 은 expected_op_cost 와 일치해야 한다(검증).
    ESS 유/무 두 해의 분해를 빼면 ESS 가치의 원천을 귀속할 수 있다:
        Δdemand_charge = 피크저감,  Δ(import+export) = 차익·자가소비,
        Δrec_revenue   = PV 흡수(curtailment 저감),  Δfuel = 연료대체.
    위험헤지(CVaR) 가치는 cvar_op_cost 차이로 별도 평가.
    """
    ny = get(config, "planning.horizon_years", 15)
    r = get(config, "planning.discount_rate", 0.045)
    pvifa = (1.0 - (1.0 + r) ** (-ny)) / r if (r and r > 0) else float(ny)
    rec = get(config, "market.rec_price", 70_000)
    gas = get(config, "market.gas_price", 80_000)
    carbon = get(config, "market.carbon_price", 0.0)
    ef = get(config, "market.gas_emission_factor", 0.0)
    fuel = gas + carbon * ef
    eta_e = get(config, "chp.eta_elec", 0.35)
    eta_boil = get(config, "boiler.eta", 0.90)
    weight = 365.0 * pvifa
    dc = get(config, "market.demand_charge", 0.0) * 1000.0
    c_deg = get(config, "ess.cost.c_deg_per_mwh", 0.0)
    fr_enabled = get(config, "market.fr_enabled", False)
    fr_price = get(config, "market.fr_cap_price", 0.0)
    fr_util = get(config, "market.fr_util_factor", 0.25)

    imp = exp = recv = dcharge = deg = frnet = fuelc = 0.0
    for s in model.S:
        p = _val(model.prob[s])
        imp += p * weight * sum(_val(model.price_im[s, t]) * _val(model.p_import[s, t])
                                for t in model.T)
        exp += p * weight * sum(_val(model.price_ex[s, t]) * _val(model.p_export[s, t])
                                for t in model.T)
        recv += p * weight * rec * sum(_val(model.p_pv[s, n, t])
                                       for n in model.N_pv for t in model.T)
        if dc > 0:
            dcharge += p * dc * _val(model.p_peak[s]) * 12.0 * pvifa
        if c_deg > 0:
            deg += p * weight * c_deg * sum(
                _val(model.p_charge[s, n, t]) + _val(model.p_discharge[s, n, t])
                for n in model.N_ess for t in model.T)
        if fr_enabled and fr_price > 0 and hasattr(model, "r_fr_up"):
            rate = c_deg * fr_util - fr_price
            frnet += p * weight * rate * sum(
                _val(model.r_fr_up[s, n, t]) + _val(model.r_fr_dn[s, n, t])
                for n in model.N_ess for t in model.T)
        if chp_enabled:
            fuelc += p * weight * fuel * sum(
                _val(model.p_chp_elec[s, n, t]) / eta_e
                + _val(model.p_boiler_heat[s, n, t]) / eta_boil
                for n in model.N_chp for t in model.T)

    return {
        "import_cost": imp,
        "export_revenue": -exp,        # 수익(음수)
        "rec_revenue": -recv,          # 수익(음수)
        "demand_charge": dcharge,      # 피크저감 가치 대상
        "ess_degradation": deg,
        "fr_net": frnet,               # 음수면 순수익
        "fuel_carbon": fuelc,          # 가스+탄소비
        "total": imp - exp - recv + dcharge + deg + frnet + fuelc,
    }
