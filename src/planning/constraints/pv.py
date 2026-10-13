"""
pv.py - PV 설치(Siting)·용량(Sizing) 및 출력 제약

물리적 의미:
    - 각 후보 노드에 PV 설치 여부(inv_pv)와 용량(cap_pv)을 결정한다.
    - target_mwp 가 주어지면 총 보급량 Σcap_pv 를 그 값으로 고정하고
      '어느 노드에 얼마나 둘지'(siting)만 최적화한다 (penetration 시나리오).
    - 설치 시 용량은 [cap_min, cap_max] 범위로 제한된다.
    - 실시간 발전량 p_pv 는 설치용량 × 열화계수 × 정규화 출력 프로파일을 상한으로 한다.
      no_curtailment=True 면 등호, False 면 부등호(curtailment 허용).

열화 모델 (단일기간 근사):
    연간 저하율 d 로 y년차 출력 = cap_pv × (1-d)^(y-1) × pv_profile.
    계획기간 N년 평균 유효계수:
        deg_factor = (1-(1-d)^N) / (N·d)  ← 단일기간 제약에 적용
    N=15, d=0.005 → deg_factor ≈ 0.964

수식:
    cap_min·inv_pv[n] ≤ cap_pv[n] ≤ cap_max·inv_pv[n]                      ∀ n
    p_pv[s,n,t] ≤ cap_pv[n] · deg_factor · pv_profile[s,t]  (또는 = )      ∀ s,n,t
"""

import math

import pyomo.environ as pyo

from src.utils.config_loader import get


def add_pv_constraints(model: pyo.ConcreteModel, config: dict):
    cap_min = get(config, "pv.cap_min_mwp", 0.1)      # [MWp]
    cap_max = get(config, "pv.cap_max_mwp", 1.0)      # [MWp]
    no_curt = get(config, "pv.no_curtailment", False)
    target = get(config, "pv.target_mwp", None)       # [MWp] 총 보급량 고정(시나리오)
    min_total = get(config, "pv.min_total_mwp", 0.0)  # [MWp] 총 설치 하한 (target 미설정 시)
    budget = get(config, "pv.budget_mwp", None)       # [MWp] 총 설치 상한 (target 미설정 시)

    # ── 계획기간 평균 유효용량계수 (연간 출력 저하 반영) ──────────────────────
    ny = get(config, "planning.horizon_years", 15)
    d = get(config, "pv.degradation_rate", 0.0)        # [-/년] 연간 저하율
    if d > 0 and ny > 1:
        deg_factor = (1.0 - (1.0 - d) ** ny) / (ny * d)  # N=15,d=0.005 → ≈0.964
    else:
        deg_factor = 1.0

    model.pv_cap_ub = pyo.Constraint(
        model.N_pv, rule=lambda m, n: m.cap_pv[n] <= cap_max * m.inv_pv[n],
        doc="PV 용량 상한 (설치 시)")
    model.pv_cap_lb = pyo.Constraint(
        model.N_pv, rule=lambda m, n: m.cap_pv[n] >= cap_min * m.inv_pv[n],
        doc="PV 용량 하한 (설치 시)")

    if target is not None:
        # 총 PV 보급량은 penetration 시나리오로 고정.
        # '어느 노드에 얼마나 둘지'(siting)만 최적화 → REC/수출에 의한 과대설치 방지.
        model.pv_total_fixed = pyo.Constraint(
            rule=lambda m: sum(m.cap_pv[n] for n in m.N_pv) == target,
            doc="총 PV 보급량 고정 (penetration 시나리오)")
    else:
        if min_total and min_total > 0:
            model.pv_min_total = pyo.Constraint(
                rule=lambda m: sum(m.cap_pv[n] for n in m.N_pv) >= min_total,
                doc="PV 총 설치 용량 하한")
        if budget:
            model.pv_budget = pyo.Constraint(
                rule=lambda m: sum(m.cap_pv[n] for n in m.N_pv) <= budget,
                doc="PV 총 설치 용량 예산")

    if no_curt:
        model.pv_output = pyo.Constraint(
            model.S, model.N_pv, model.T,
            rule=lambda m, s, n, t: (
                m.p_pv[s, n, t] == m.cap_pv[n] * deg_factor * m.pv_profile[s, t]),
            doc="PV 출력 (출력제한 불가 — 열화 포함)")
    else:
        model.pv_output = pyo.Constraint(
            model.S, model.N_pv, model.T,
            rule=lambda m, s, n, t: (
                m.p_pv[s, n, t] <= m.cap_pv[n] * deg_factor * m.pv_profile[s, t]),
            doc="PV 출력 상한 (curtailment 허용, 열화 포함)")

    # ── 인버터 무효전력 범위 (역률 제한) ──────────────────
    # |q_pv| ≤ cap_pv × tan(arccos(pf_min))
    # pf_min=0.95 → tan_phi ≈ 0.329 (IEEE 1547-2018 스마트인버터 기준)
    pf_min = get(config, "pv.pf_min", 0.95)
    tan_phi = math.tan(math.acos(pf_min))
    model.pv_q_ub = pyo.Constraint(
        model.S, model.N_pv, model.T,
        rule=lambda m, s, n, t: m.q_pv[s, n, t] <= m.cap_pv[n] * tan_phi,
        doc="PV 인버터 무효전력 상한")
    model.pv_q_lb = pyo.Constraint(
        model.S, model.N_pv, model.T,
        rule=lambda m, s, n, t: m.q_pv[s, n, t] >= -m.cap_pv[n] * tan_phi,
        doc="PV 인버터 무효전력 하한")
