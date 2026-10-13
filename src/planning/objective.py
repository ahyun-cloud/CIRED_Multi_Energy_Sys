"""
objective.py - 목적함수: 투자비 + 기대 운영비 + λ·CVaR (NPV 기준)

목적함수:
    min  C_invest + E_s[C_op(s)] + λ·CVaR_α[C_op(s)]   (확률론적)
    min  C_invest + C_op(expected)                     (결정론적)

비용 항 (모두 계획기간 현재가치, NPV):
    C_invest : 설비 capex(t=0) + 할인된 O&M(PVIFA) + DHN 배관 고정비
    C_op(s)  : (수전비 - 수출수익 - REC수익 + 열화 - FR수익 + 가스연료비)·365·PVIFA

할인:
    운영비·O&M 등 연간 반복 현금흐름은 연금현가계수
    PVIFA(r,N) = Σ_{t=1..N} (1+r)^-t = (1-(1+r)^-N)/r 로 할인 합산한다.
    capex 는 t=0 발생으로 보아 할인하지 않는다. r=0 이면 PVIFA=N (비할인 합산).

운영비/투자비는 pyo.Expression 으로 등록하여 extractor 가 그대로 재사용한다.
요금(price_im/ex)은 model.py 에서 [원/MWh] 로 변환되어 들어온다.
"""

import pyomo.environ as pyo

from src.data_process.network import DHN_PIPE_DATA
from src.utils.config_loader import get
from src.planning.constraints.cvar import add_cvar_risk


def pvifa_factor(rate: float, n: int) -> float:
    """연금현가계수 Σ_{t=1}^{n} 1/(1+r)^t. r≤0 이면 n (비할인 합산).

    extractor 의 보고값도 목적함수와 동일한 할인을 쓰도록 여기서 공유한다.
    """
    if rate is None or rate <= 0:
        return float(n)
    return (1.0 - (1.0 + rate) ** (-n)) / rate


def _operation_cost(m, config, s, chp_enabled):
    """시나리오 s 의 운영비 [원] (계획기간 전체).

    항목:
        전기비용   = 수전비 - 수출수익 - REC수익
        ESS 열화   = c_deg × (충전+방전) 처리량  [사이클 마모 비용]
        FR 순비용  = (c_deg·μ − fr_price) × (상향+하향) 예비력
                     [용량요금 수익 − 발동 throughput 열화비용]
        가스연료비 = (CHP 투입 + 보일러 투입) × 가스단가
    """
    ny = get(config, "planning.horizon_years", 15)
    r = get(config, "planning.discount_rate", 0.045)       # 실질 할인율
    pvifa = pvifa_factor(r, ny)                            # 연금현가계수
    rec = get(config, "market.rec_price", 70_000)          # [원/MWh]
    gas = get(config, "market.gas_price", 80_000)          # [원/MWh]
    eta_e = get(config, "chp.eta_elec", 0.35)
    eta_boil = get(config, "boiler.eta", 0.90)
    weight = 365.0 * pvifa                                 # 일→계획기간 환산 (NPV 할인)

    elec = sum(
        (m.price_im[s, t] * m.p_import[s, t]
         - m.price_ex[s, t] * m.p_export[s, t]
         - rec * sum(m.p_pv[s, n, t] for n in m.N_pv)) * weight
        for t in m.T
    )

    # 수요요금(기본요금): 피크 수전 기반 월 요금 → 피크저감 가치 (한국 ESS 핵심 동인)
    #   연 12개월 × PVIFA 할인. ESS 방전이 p_peak 를 낮춰 절감.
    dc = get(config, "market.demand_charge", 0.0) * 1000.0   # [원/kW/월] → [원/MW/월]
    if dc > 0:
        elec += dc * m.p_peak[s] * 12.0 * pvifa

    # ESS 열화 비용: 충·방전 처리량(throughput)에 비례하는 사이클 마모 비용
    c_deg = get(config, "ess.cost.c_deg_per_mwh", 0.0)    # [원/MWh throughput]
    if c_deg > 0:
        elec += sum(
            c_deg * (m.p_charge[s, n, t] + m.p_discharge[s, n, t]) * weight
            for n in m.N_ess for t in m.T
        )

    # FR 보조서비스: 용량요금 수익(−) − 발동(regulation) 사이클 열화비용(+)
    #   순 단가 = (c_deg·μ − fr_price) [원/MW/h]. μ=fr_util_factor.
    #   c_deg·μ ≈ fr_price 면 FR 순수익≈0 → "공짜 용량요금" 무한증설 방지.
    #   [가정] 발동은 평균 에너지중립(up≈dn)으로 SOC 동특성 미반영, throughput 열화만 부과.
    #          용량요금 기반(KPX) — mileage(에너지) 정산수익은 미반영(보수적).
    fr_enabled = get(config, "market.fr_enabled", False)
    fr_price = get(config, "market.fr_cap_price", 0.0)     # [원/MW/h]
    fr_util = get(config, "market.fr_util_factor", 0.25)   # [-] 발동 throughput 계수 μ
    if fr_enabled and fr_price > 0 and hasattr(m, "r_fr_up"):
        fr_net_rate = c_deg * fr_util - fr_price           # [원/MW/h] (음수=순수익)
        elec += sum(
            fr_net_rate * (m.r_fr_up[s, n, t] + m.r_fr_dn[s, n, t]) * weight
            for n in m.N_ess for t in m.T
        )

    if not chp_enabled:
        return elec
    # 가스 연료비 + 탄소비용(K-ETS): 탄소비를 연료단가에 내재화
    #   fuel = gas + carbon_price·ef  [원/MWh_gas].  carbon_price 기본 0 → 기존 결과 불변.
    #   미래 시나리오(future_pathway)에서 carbon_price 를 override 해 탈탄소 압력 반영.
    carbon = get(config, "market.carbon_price", 0.0)         # [원/tCO2]
    ef = get(config, "market.gas_emission_factor", 0.0)      # [tCO2/MWh_gas]
    fuel = gas + carbon * ef                                 # [원/MWh_gas]
    gas_op = sum(
        (m.p_chp_elec[s, n, t] / eta_e
         + m.p_boiler_heat[s, n, t] / eta_boil) * fuel * weight
        for n in m.N_chp for t in m.T
    )
    return elec + gas_op


def _investment_cost(m, config):
    """총 투자비 [원] (capex + 할인된 O&M, NPV). DHN 배관은 고정 상수.

    O&M(연간 반복비)은 PVIFA(r,N)로 할인 합산한다. capex 는 t=0 발생으로 비할인.
    """
    ny = get(config, "planning.horizon_years", 15)
    r = get(config, "planning.discount_rate", 0.045)
    pvifa = pvifa_factor(r, ny)                    # 할인된 O&M 누적계수
    comps = config.get("components", {})

    # PV
    pv_cp = get(config, "pv.cost.c_power", 1.2e9) * (1 + get(config, "pv.cost.om_rate", 0.015) * pvifa)
    pv_cf = get(config, "pv.cost.c_fixed", 5.0e7)
    inv = sum(pv_cp * m.cap_pv[n] + pv_cf * m.inv_pv[n] for n in m.N_pv)

    # ESS
    es_cp = get(config, "ess.cost.c_power", 1.5e8) * (1 + get(config, "ess.cost.om_rate", 0.025) * pvifa)
    es_ce = get(config, "ess.cost.c_energy", 2.0e8) * (1 + get(config, "ess.cost.om_rate", 0.025) * pvifa)
    es_cf = get(config, "ess.cost.c_fixed", 3.0e7)
    inv += sum(es_cp * m.cap_ess_p[n] + es_ce * m.cap_ess_e[n] + es_cf * m.inv_ess[n]
               for n in m.N_ess)

    # CHP / 보일러 / TES
    if comps.get("chp", True):
        chp_cp = get(config, "chp.cost.c_power", 2.0e8) * (1 + get(config, "chp.cost.om_rate", 0.03) * pvifa)
        chp_cf = get(config, "chp.cost.c_fixed", 2.0e7)
        boil_cp = get(config, "boiler.cost.c_power", 5.0e7) * (1 + get(config, "boiler.cost.om_rate", 0.02) * pvifa)
        tes_ce = get(config, "tes.cost.c_energy", 3.0e7) * (1 + get(config, "tes.cost.om_rate", 0.02) * pvifa)
        inv += sum(chp_cp * m.cap_chp[n] + chp_cf * m.inv_chp[n] for n in m.N_chp)
        inv += sum(boil_cp * m.cap_boiler[n] for n in m.N_chp)
        inv += sum(tes_ce * m.cap_tes[n] for n in m.N_chp)

    # DHN 배관 (고정 상수). c_pipe 는 노선 단위(공급+환수 포함) 단가이므로
    # 별도 공급/환수 ×2 불필요 (DEA Transport of Energy 카탈로그 기준).
    if comps.get("dhn", False):
        c_pipe = get(config, "dhn.cost.c_pipe", 1.146e9) * (1 + get(config, "dhn.cost.om_rate", 0.015) * pvifa)
        total_len = float(DHN_PIPE_DATA[:, 2].sum())
        inv += c_pipe * total_len

    return inv


def add_objective(model: pyo.ConcreteModel, config: dict):
    """목적함수 및 운영비/투자비 Expression 을 모델에 추가."""
    chp_enabled = config.get("components", {}).get("chp", True)
    mode = get(config, "planning.mode", "stochastic")
    relax = get(config, "grid.relax_voltage", False)
    v_pen = get(config, "grid.v_penalty", 1.0e10)

    model.op_cost = pyo.Expression(
        model.S, rule=lambda m, s: _operation_cost(m, config, s, chp_enabled))
    model.invest_cost = pyo.Expression(rule=lambda m: _investment_cost(m, config))

    voltage_penalty = 0.0
    if relax and hasattr(model, "v_slack_up"):
        voltage_penalty = v_pen * sum(
            model.v_slack_up[s, i, t] + model.v_slack_dn[s, i, t]
            for s in model.S for i in model.PQ for t in model.T)

    if mode == "deterministic":
        s0 = list(model.S)[0]
        model.objective = pyo.Objective(
            expr=model.invest_cost + model.op_cost[s0] + voltage_penalty,
            sense=pyo.minimize)
    else:
        expected_op = sum(model.prob[s] * model.op_cost[s] for s in model.S)
        cvar_term = add_cvar_risk(
            model, config, [model.op_cost[s] for s in model.S])
        lam = get(config, "planning.lambda_risk", 0.5)
        model.objective = pyo.Objective(
            expr=model.invest_cost + expected_op + lam * cvar_term + voltage_penalty,
            sense=pyo.minimize)
