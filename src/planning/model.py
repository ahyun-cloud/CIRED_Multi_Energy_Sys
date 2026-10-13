"""
model.py - 2단계 확률론적 MILP 계획 모델 빌더

이 파일은 모델 '구조'만 정의한다 (Set·Parameter·Variable).
  - 제약은 constraints/ 의 add_*_constraints 함수로 부착
  - 목적함수는 objective.add_objective
  - 풀이는 solver.solve_model, 결과 추출은 extractor.extract_results

데이터 schema:
    data = {
        'scenario': scenario_gen 의 시나리오 배열 dict,
        'lpf'     : LinearPowerFlow 객체,
    }
단위: KRW(원), MW, MWh, MW_th
"""

import numpy as np
import pyomo.environ as pyo

from src.data_process.network import (
    NUM_NODES, SLACK_BUS, LINE_DATA, LOAD_DATA_MW, LOAD_DATA_MVAR,
    PV_CANDIDATE_NODES, ESS_CANDIDATE_NODES, CHP_CANDIDATE_NODES,
    DHN_PIPE_DATA,
)
from src.utils.config_loader import get
from src.planning.constraints.pv import add_pv_constraints
from src.planning.constraints.ess import add_ess_constraints
from src.planning.constraints.chp import add_chp_constraints
from src.planning.constraints.dhn import add_dhn_constraints
from src.planning.constraints.balance import add_power_balance_constraints
from src.planning.constraints.grid import add_grid_constraints
from src.planning.objective import add_objective


def build_model(config: dict, data: dict) -> pyo.ConcreteModel:
    """config 와 data 로 풀이 전 ConcreteModel 을 구성하여 반환."""
    sc = data["scenario"]
    lpf = data["lpf"]

    comps = config.get("components", {})
    chp_enabled = comps.get("chp", True)
    dhn_enabled = comps.get("dhn", False)
    if dhn_enabled and not chp_enabled:
        raise ValueError("DHN 사용 시 CHP(열원)가 반드시 활성화되어야 합니다.")

    mode = get(config, "planning.mode", "stochastic")
    relax = get(config, "grid.relax_voltage", False)
    heat_ratio = get(config, "heat.ratio", 0.8)

    pv_prof = np.asarray(sc["pv"], dtype=float)
    ld_prof = np.asarray(sc["load"], dtype=float)
    heat_prof = np.asarray(sc["heat"], dtype=float)
    probs = np.asarray(sc["probs"], dtype=float)
    S = len(probs)

    # 요금 [원/kWh] → [원/MWh]
    price_im = np.asarray(sc["price_im"], dtype=float) * 1000.0
    price_ex = np.asarray(sc["price_ex"], dtype=float) * 1000.0

    load_peak = LOAD_DATA_MW                       # [MW]
    heat_peak = LOAD_DATA_MW * heat_ratio          # [MW_th]

    pq_idx = [i for i in range(NUM_NODES) if i != SLACK_BUS]
    n_lines = len(LINE_DATA)
    A_v, b_v = lpf.get_voltage_sensitivity()       # A_v: (32×64) = [dV/dP | dV/dQ]
    A_vq, _ = lpf.get_q_voltage_sensitivity()      # dV/dQ: (32×32)
    A_i, b_i = lpf.get_current_sensitivity()

    q_load_peak = LOAD_DATA_MVAR                   # [Mvar] 노드별 무효전력 피크부하

    chp_nodes = list(CHP_CANDIDATE_NODES) if chp_enabled else []
    n_pipes = len(DHN_PIPE_DATA)

    m = pyo.ConcreteModel(name=config.get("_scenario_name", "cired"))

    # ── Sets ──────────────────────────────────────────────
    m.S = pyo.Set(initialize=range(S), doc="시나리오")
    m.T = pyo.Set(initialize=range(24), doc="시각 [h]")
    m.N = pyo.Set(initialize=range(NUM_NODES), doc="노드")
    # ESS 후보노드: config 지정 시 한정(slack 제외), 미설정 시 전 노드
    _ess_cfg = get(config, "ess.candidate_nodes", None)
    ess_nodes = ([int(n) for n in _ess_cfg if int(n) != SLACK_BUS]
                 if _ess_cfg else ESS_CANDIDATE_NODES)
    m.N_pv = pyo.Set(initialize=PV_CANDIDATE_NODES, doc="PV 후보 노드")
    m.N_ess = pyo.Set(initialize=ess_nodes, doc="ESS 후보 노드")
    m.N_chp = pyo.Set(initialize=chp_nodes, doc="CHP/TES 노드")
    m.L = pyo.Set(initialize=range(n_lines), doc="선로")
    m.PQ = pyo.Set(initialize=pq_idx, doc="비-슬랙 노드")
    if dhn_enabled:
        m.DHN_P = pyo.Set(initialize=range(n_pipes), doc="DHN 배관")

    # ── Parameters ────────────────────────────────────────
    m.elec_load = pyo.Param(m.S, m.N, m.T, within=pyo.NonNegativeReals,
        initialize={(s, n, t): float(ld_prof[s, t] * load_peak[n])
                    for s in range(S) for n in range(NUM_NODES) for t in range(24)},
        doc="노드별 전기부하 [MW]")
    if chp_enabled:
        m.heat_load = pyo.Param(m.S, m.N_chp, m.T, within=pyo.NonNegativeReals,
            initialize={(s, n, t): float(heat_prof[s, t] * heat_peak[n])
                        for s in range(S) for n in chp_nodes for t in range(24)},
            doc="노드별 열부하 [MW_th]")

    m.pv_profile = pyo.Param(m.S, m.T, within=pyo.NonNegativeReals,
        initialize={(s, t): float(pv_prof[s, t])
                    for s in range(S) for t in range(24)},
        doc="정규화 PV 출력 [-]")
    m.price_im = pyo.Param(m.S, m.T,
        initialize={(s, t): float(price_im[s, t])
                    for s in range(S) for t in range(24)}, doc="수전 단가 [원/MWh]")
    m.price_ex = pyo.Param(m.S, m.T,
        initialize={(s, t): float(price_ex[s, t])
                    for s in range(S) for t in range(24)}, doc="수출 단가 [원/MWh]")
    m.prob = pyo.Param(m.S, initialize={s: float(probs[s]) for s in range(S)},
        doc="시나리오 확률")

    # LPF 감도행렬 — 유효전력(P) + 무효전력(Q) 분리
    m.Av = pyo.Param(m.PQ, m.PQ, initialize={
        (i, j): float(A_v[pq_idx.index(i), pq_idx.index(j)])
        for i in pq_idx for j in pq_idx}, doc="전압 감도 dV/dP")
    m.Avq = pyo.Param(m.PQ, m.PQ, initialize={
        (i, j): float(A_vq[pq_idx.index(i), pq_idx.index(j)])
        for i in pq_idx for j in pq_idx}, doc="전압 감도 dV/dQ")
    m.bv = pyo.Param(m.PQ, initialize={
        i: float(b_v[pq_idx.index(i)]) for i in pq_idx}, doc="기준 전압 [pu]")
    m.Ai = pyo.Param(m.L, m.PQ, initialize={
        (l, j): float(A_i[l, pq_idx.index(j)])
        for l in range(n_lines) for j in pq_idx}, doc="전류 감도 dI/dP")
    m.bi = pyo.Param(m.L, initialize={
        l: float(b_i[l]) for l in range(n_lines)}, doc="기준 전류 [pu]")

    # 무효전력 부하 (Baran & Wu 1989 LOAD_DATA_MVAR, 전기부하와 같은 형상 가정)
    m.react_load = pyo.Param(m.S, m.N, m.T, within=pyo.NonNegativeReals,
        initialize={(s, n, t): float(ld_prof[s, t] * q_load_peak[n])
                    for s in range(S) for n in range(NUM_NODES) for t in range(24)},
        doc="노드별 무효전력 부하 [Mvar]")

    # ── 1단계 투자 변수 ───────────────────────────────────
    m.inv_pv = pyo.Var(m.N_pv, domain=pyo.Binary, doc="PV 설치 여부")
    m.cap_pv = pyo.Var(m.N_pv, domain=pyo.NonNegativeReals, doc="PV 용량 [MWp]")
    m.inv_ess = pyo.Var(m.N_ess, domain=pyo.Binary, doc="ESS 설치 여부")
    m.cap_ess_p = pyo.Var(m.N_ess, domain=pyo.NonNegativeReals, doc="ESS 출력 [MW]")
    m.cap_ess_e = pyo.Var(m.N_ess, domain=pyo.NonNegativeReals, doc="ESS 에너지 [MWh]")

    if chp_enabled:
        m.inv_chp = pyo.Var(m.N_chp, domain=pyo.Binary, doc="CHP 설치 여부")
        m.cap_chp = pyo.Var(m.N_chp, domain=pyo.NonNegativeReals, doc="CHP 전기용량 [MW_e]")
        m.inv_boiler = pyo.Var(m.N_chp, domain=pyo.Binary, doc="보일러 설치 여부")
        m.cap_boiler = pyo.Var(m.N_chp, domain=pyo.NonNegativeReals, doc="보일러 용량 [MW_th]")
        m.inv_tes = pyo.Var(m.N_chp, domain=pyo.Binary, doc="TES 설치 여부")
        m.cap_tes = pyo.Var(m.N_chp, domain=pyo.NonNegativeReals, doc="TES 용량 [MWh_th]")

    # ── 2단계 운영 변수 ───────────────────────────────────
    m.p_pv = pyo.Var(m.S, m.N_pv, m.T, domain=pyo.NonNegativeReals, doc="PV 발전 [MW]")
    m.q_pv = pyo.Var(m.S, m.N_pv, m.T, domain=pyo.Reals, doc="PV 인버터 무효전력 [Mvar]")
    m.p_charge = pyo.Var(m.S, m.N_ess, m.T, domain=pyo.NonNegativeReals, doc="ESS 충전 [MW]")
    m.p_discharge = pyo.Var(m.S, m.N_ess, m.T, domain=pyo.NonNegativeReals, doc="ESS 방전 [MW]")
    m.soc = pyo.Var(m.S, m.N_ess, m.T, domain=pyo.NonNegativeReals, doc="ESS SOC [MWh]")
    m.q_ess = pyo.Var(m.S, m.N_ess, m.T, domain=pyo.Reals, doc="ESS 인버터 무효전력 [Mvar]")
    m.p_import = pyo.Var(m.S, m.T, domain=pyo.NonNegativeReals, doc="계통 수전 [MW]")
    # 역송전 한계(feed-in limit): 설정 시 수출 상한 → 고침투 시 잉여 PV curtailment 유발
    _exp_lim = get(config, "grid.export_limit_mw", None)
    m.p_export = pyo.Var(m.S, m.T, domain=pyo.NonNegativeReals,
                         bounds=(0, _exp_lim), doc="계통 수출 [MW]")
    m.p_peak = pyo.Var(m.S, domain=pyo.NonNegativeReals, doc="시나리오별 피크 수전 [MW] (기본요금)")

    fr_enabled = get(config, "market.fr_enabled", False)
    if fr_enabled:
        m.r_fr_up = pyo.Var(m.S, m.N_ess, m.T, domain=pyo.NonNegativeReals,
                            doc="ESS 상향 FR 예비력 [MW]")
        m.r_fr_dn = pyo.Var(m.S, m.N_ess, m.T, domain=pyo.NonNegativeReals,
                            doc="ESS 하향 FR 예비력 [MW]")

    if chp_enabled:
        m.p_chp_elec = pyo.Var(m.S, m.N_chp, m.T, domain=pyo.NonNegativeReals, doc="CHP 전기 [MW]")
        m.p_chp_heat = pyo.Var(m.S, m.N_chp, m.T, domain=pyo.NonNegativeReals, doc="CHP 열 [MW_th]")
        m.p_boiler_heat = pyo.Var(m.S, m.N_chp, m.T, domain=pyo.NonNegativeReals, doc="보일러 열 [MW_th]")
        m.tes_charge = pyo.Var(m.S, m.N_chp, m.T, domain=pyo.NonNegativeReals, doc="TES 충열 [MW_th]")
        m.tes_discharge = pyo.Var(m.S, m.N_chp, m.T, domain=pyo.NonNegativeReals, doc="TES 방열 [MW_th]")
        m.soc_tes = pyo.Var(m.S, m.N_chp, m.T, domain=pyo.NonNegativeReals, doc="TES SOC [MWh_th]")

    if dhn_enabled:
        t_sup_min = get(config, "dhn.t_sup_min", 70.0)
        t_sup_max = get(config, "dhn.t_sup_max", 120.0)
        t_ret_min = get(config, "dhn.t_ret_min", 40.0)
        t_ret_max = get(config, "dhn.t_ret_max", 60.0)
        m.t_supply = pyo.Var(m.S, m.N_chp, m.T, domain=pyo.NonNegativeReals,
            bounds=(t_sup_min, t_sup_max), doc="공급온도 [°C]")
        m.t_return = pyo.Var(m.S, m.N_chp, m.T, domain=pyo.NonNegativeReals,
            bounds=(t_ret_min, t_ret_max), doc="환수온도 [°C]")
        m.q_pipe = pyo.Var(m.S, m.DHN_P, m.T, domain=pyo.Reals, doc="배관 열유량 [MW_th]")

    if relax:
        m.v_slack_up = pyo.Var(m.S, m.PQ, m.T, domain=pyo.NonNegativeReals, doc="전압 상한 위반 [pu]")
        m.v_slack_dn = pyo.Var(m.S, m.PQ, m.T, domain=pyo.NonNegativeReals, doc="전압 하한 위반 [pu]")

    if mode == "stochastic":
        m.cvar_eta = pyo.Var(domain=pyo.Reals, doc="CVaR η (≈VaR)")
        m.cvar_z = pyo.Var(m.S, domain=pyo.NonNegativeReals, doc="CVaR 초과손실")

    # ── 제약 부착 ─────────────────────────────────────────
    add_pv_constraints(m, config)
    add_ess_constraints(m, config)
    if chp_enabled:
        add_chp_constraints(m, config, dhn_enabled)
    if dhn_enabled:
        add_dhn_constraints(m, config)
    add_power_balance_constraints(m, chp_enabled)
    add_grid_constraints(m, config, chp_enabled)

    # 피크 수전 정의 (기본요금/수요요금 산정용): p_peak[s] ≥ 모든 시각의 수전
    m.peak_def = pyo.Constraint(
        m.S, m.T, rule=lambda m, s, t: m.p_peak[s] >= m.p_import[s, t],
        doc="시나리오별 피크 수전 정의")

    # ── 목적함수 ──────────────────────────────────────────
    add_objective(m, config)

    return m
