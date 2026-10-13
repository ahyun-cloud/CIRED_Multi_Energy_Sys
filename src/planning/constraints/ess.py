"""
ess.py - ESS 설치(Siting)·용량(Sizing) 및 충방전 운영 제약

물리적 의미:
    - 각 후보 노드에 ESS 설치 여부(inv_ess), 출력(cap_ess_p)·에너지(cap_ess_e) 용량 결정
    - 지속시간(duration = E/P)을 [min_dur, max_dur] 로 제한
    - 운영: 충전/방전 출력 한계, SOC 상하한, 초기·종기 SOC, SOC 동특성(에너지 보존)

수식 (요지):
    soc[t] = soc[t-1] + η·p_charge[t-1] - (1/η)·p_discharge[t-1]
    soc_min·E ≤ soc[t] ≤ soc_max·E,   soc[0]=0.5·E

    soc[t] 는 '시각 t 진입 시점'의 저장량이므로 하루의 종결 상태는 soc[23] 이 아니라
    soc[23] 에 t=23 의 충·방전을 반영한 값이다. 따라서 일 주기 조건은
        soc[23] + η·p_charge[23] - (1/η)·p_discharge[23] = 0.5·E
    로 부과한다. (soc[23]=0.5·E 로 두면 t=23 의 충·방전이 어떤 에너지 보존식에도
    들어가지 않아 마지막 시각에 무상 방전이 가능해진다.)
"""

import math

import pyomo.environ as pyo

from src.utils.config_loader import get


def add_ess_constraints(model: pyo.ConcreteModel, config: dict):
    eta = get(config, "ess.efficiency", 0.95)            # 충방전 효율 [-]
    soc_min = get(config, "ess.soc_min", 0.10)
    soc_max = get(config, "ess.soc_max", 0.90)
    min_dur = get(config, "ess.min_duration_h", 2.0)     # [h]
    max_dur = get(config, "ess.max_duration_h", 4.0)     # [h]
    min_p = get(config, "ess.min_power_mw", 0.1)         # [MW] 최소 설치 출력
    budget = get(config, "ess.budget_mw", None)          # [MW] 총 출력 예산

    # 노드별 ESS 출력 상한 [MW] — big-M 타이트닝(LP 완화 강화 + 현실성)
    #   cap_max_mw 명시 시 그 값을, 없으면 (PV상한 × ESS:PV 비율) 폴백.
    cap_max_mw = get(config, "ess.cap_max_mw", None)
    if cap_max_mw is not None:
        p_max_node = cap_max_mw
    else:
        pv_cap_max = get(config, "pv.cap_max_mwp", 1.0)
        ratio = get(config, "ess.pv_to_ess_ratio", 3.0)
        p_max_node = pv_cap_max * ratio          # [MW]
    e_max_node = p_max_node * max_dur        # [MWh]

    # ── 용량/설치 연동 ────────────────────────────────────
    model.ess_p_ub = pyo.Constraint(
        model.N_ess, rule=lambda m, n: m.cap_ess_p[n] <= p_max_node * m.inv_ess[n],
        doc="ESS 출력 용량 상한")
    model.ess_e_ub = pyo.Constraint(
        model.N_ess, rule=lambda m, n: m.cap_ess_e[n] <= e_max_node * m.inv_ess[n],
        doc="ESS 에너지 용량 상한")
    model.ess_dur_lb = pyo.Constraint(
        model.N_ess, rule=lambda m, n: m.cap_ess_e[n] >= min_dur * m.cap_ess_p[n],
        doc="지속시간 하한 (E ≥ min_dur·P)")
    model.ess_dur_ub = pyo.Constraint(
        model.N_ess, rule=lambda m, n: m.cap_ess_e[n] <= max_dur * m.cap_ess_p[n],
        doc="지속시간 상한 (E ≤ max_dur·P)")
    model.ess_p_lb = pyo.Constraint(
        model.N_ess, rule=lambda m, n: m.cap_ess_p[n] >= min_p * m.inv_ess[n],
        doc="ESS 최소 설치 출력")

    if budget:
        model.ess_budget = pyo.Constraint(
            rule=lambda m: sum(m.cap_ess_p[n] for n in m.N_ess) <= budget,
            doc="ESS 총 출력 예산")

    # ── 충방전 운영 / FR 예비력 ────────────────────────────
    # FR 활성 시: 출력 여유(capacity margin)와 SOC 여유를 동시에 확보
    fr_enabled = get(config, "market.fr_enabled", False)

    if fr_enabled:
        model.ess_discharge_ub = pyo.Constraint(
            model.S, model.N_ess, model.T,
            rule=lambda m, s, n, t: m.p_discharge[s, n, t] + m.r_fr_up[s, n, t] <= m.cap_ess_p[n],
            doc="방전+상향FR ≤ 출력용량")
        model.ess_charge_ub = pyo.Constraint(
            model.S, model.N_ess, model.T,
            rule=lambda m, s, n, t: m.p_charge[s, n, t] + m.r_fr_dn[s, n, t] <= m.cap_ess_p[n],
            doc="충전+하향FR ≤ 출력용량")
        # FR 발동 여유: 상향은 SOC 하한 위로, 하향은 SOC 상한 아래로
        model.ess_soc_lb = pyo.Constraint(
            model.S, model.N_ess, model.T,
            rule=lambda m, s, n, t: m.soc[s, n, t] >= soc_min * m.cap_ess_e[n] + m.r_fr_up[s, n, t],
            doc="SOC 하한 (상향FR 발동 여유 포함)")
        model.ess_soc_ub = pyo.Constraint(
            model.S, model.N_ess, model.T,
            rule=lambda m, s, n, t: m.soc[s, n, t] <= soc_max * m.cap_ess_e[n] - m.r_fr_dn[s, n, t],
            doc="SOC 상한 (하향FR 발동 여유 포함)")
        # 시스템 전체 FR 조달 상한 (방향별) — 시장 깊이 반영, 'ESS 최대' 비현실 해 차단
        fr_cap = get(config, "market.fr_total_cap_mw", None)
        if fr_cap is not None:
            model.fr_cap_up = pyo.Constraint(
                model.S, model.T,
                rule=lambda m, s, t: sum(m.r_fr_up[s, n, t] for n in m.N_ess) <= fr_cap,
                doc="시스템 전체 상향 FR 조달 상한")
            model.fr_cap_dn = pyo.Constraint(
                model.S, model.T,
                rule=lambda m, s, t: sum(m.r_fr_dn[s, n, t] for n in m.N_ess) <= fr_cap,
                doc="시스템 전체 하향 FR 조달 상한")
    else:
        model.ess_discharge_ub = pyo.Constraint(
            model.S, model.N_ess, model.T,
            rule=lambda m, s, n, t: m.p_discharge[s, n, t] <= m.cap_ess_p[n],
            doc="방전 출력 한계")
        model.ess_charge_ub = pyo.Constraint(
            model.S, model.N_ess, model.T,
            rule=lambda m, s, n, t: m.p_charge[s, n, t] <= m.cap_ess_p[n],
            doc="충전 출력 한계")
        model.ess_soc_lb = pyo.Constraint(
            model.S, model.N_ess, model.T,
            rule=lambda m, s, n, t: m.soc[s, n, t] >= soc_min * m.cap_ess_e[n],
            doc="SOC 하한")
        model.ess_soc_ub = pyo.Constraint(
            model.S, model.N_ess, model.T,
            rule=lambda m, s, n, t: m.soc[s, n, t] <= soc_max * m.cap_ess_e[n],
            doc="SOC 상한")
    model.ess_soc_init = pyo.Constraint(
        model.S, model.N_ess,
        rule=lambda m, s, n: m.soc[s, n, 0] == 0.5 * m.cap_ess_e[n],
        doc="초기 SOC = 50%")
    model.ess_soc_end = pyo.Constraint(
        model.S, model.N_ess,
        rule=lambda m, s, n: (m.soc[s, n, 23]
                              + eta * m.p_charge[s, n, 23]
                              - (1.0 / eta) * m.p_discharge[s, n, 23]
                              == 0.5 * m.cap_ess_e[n]),
        doc="종기 SOC = 50% (일 주기 운영) — t=23 충·방전 반영")

    def _soc_dynamics(m, s, n, t):
        if t == 0:
            return pyo.Constraint.Skip
        return m.soc[s, n, t] == (m.soc[s, n, t - 1]
                                  + eta * m.p_charge[s, n, t - 1]
                                  - (1.0 / eta) * m.p_discharge[s, n, t - 1])

    model.ess_soc_dynamics = pyo.Constraint(
        model.S, model.N_ess, model.T, rule=_soc_dynamics,
        doc="SOC 동특성 (에너지 보존)")

    # ── 인버터 무효전력 범위 (역률 제한) ──────────────────
    # |q_ess| ≤ cap_ess_p × tan(arccos(pf_min))
    pf_min = get(config, "ess.pf_min", 0.95)
    tan_phi = math.tan(math.acos(pf_min))
    model.ess_q_ub = pyo.Constraint(
        model.S, model.N_ess, model.T,
        rule=lambda m, s, n, t: m.q_ess[s, n, t] <= m.cap_ess_p[n] * tan_phi,
        doc="ESS 인버터 무효전력 상한")
    model.ess_q_lb = pyo.Constraint(
        model.S, model.N_ess, model.T,
        rule=lambda m, s, n, t: m.q_ess[s, n, t] >= -m.cap_ess_p[n] * tan_phi,
        doc="ESS 인버터 무효전력 하한")
