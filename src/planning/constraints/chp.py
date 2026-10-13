"""
chp.py - CHP / 가스보일러 / TES 설치·용량·운영 제약

물리적 의미:
    - CHP: 전기·열 병산. 열출력 = α·전기출력 (α = η_heat/η_elec, 고정 열전비)
    - 보일러: 가스 연소로 열 공급
    - TES: 열에너지 저장 (충방열, SOC 동특성)
    - 열 균형: DHN 미사용 시 '노드별 로컬 열균형'을 여기서 부과한다.
              DHN 사용 시 열균형은 네트워크 단위로 dhn.py 에서 처리한다.
              (※ 두 곳에서 동시에 부과하면 배관이 무의미해지므로 분리)

수식 (요지):
    p_chp_heat = α·p_chp_elec
    soc_tes[t] = soc_tes[t-1] + η·tes_charge[t-1] - (1/η)·tes_discharge[t-1]
    [로컬 열균형] p_chp_heat + p_boiler_heat + tes_discharge - tes_charge ≥ heat_load

    ESS 와 동일하게 soc_tes[t] 는 '시각 t 진입 시점' 저장량이므로, 일 주기 종결은
        soc_tes[23] + η·tes_charge[23] - (1/η)·tes_discharge[23] = 0.5·cap_tes
    로 부과한다 (soc_tes[23]=0.5·cap_tes 로 두면 t=23 방열이 무상이 된다).
"""

import pyomo.environ as pyo

from src.utils.config_loader import get


def add_chp_constraints(model: pyo.ConcreteModel, config: dict,
                        dhn_enabled: bool):
    eta_e = get(config, "chp.eta_elec", 0.35)
    eta_h = get(config, "chp.eta_heat", 0.50)
    alpha = eta_h / eta_e                                # 열전비 [-]
    p_chp_max = get(config, "chp.p_max_mw", 1.0)         # [MW_e]
    p_boil_max = get(config, "boiler.p_max_mw", 2.0)     # [MW_th]

    tes_eta = get(config, "tes.efficiency", 0.95)
    tes_min_soc = get(config, "tes.soc_min", 0.10)
    tes_max_soc = get(config, "tes.soc_max", 0.90)
    tes_min_dur = get(config, "tes.min_duration_h", 2.0)  # [h]
    tes_max_dur = get(config, "tes.max_duration_h", 6.0)  # [h]

    # ── 용량/설치 연동 ────────────────────────────────────
    model.chp_cap_ub = pyo.Constraint(
        model.N_chp, rule=lambda m, n: m.cap_chp[n] <= p_chp_max * m.inv_chp[n],
        doc="CHP 전기 용량 상한")
    model.boiler_cap_ub = pyo.Constraint(
        model.N_chp, rule=lambda m, n: m.cap_boiler[n] <= p_boil_max * m.inv_boiler[n],
        doc="보일러 열 용량 상한")

    _M_tes = tes_max_dur * p_chp_max * alpha             # Big-M (물리 상한 기반)
    model.tes_cap_ub = pyo.Constraint(
        model.N_chp,
        rule=lambda m, n: m.cap_tes[n] <= _M_tes * m.inv_tes[n],
        doc="TES 에너지 용량 상한")
    model.tes_cap_lb = pyo.Constraint(
        model.N_chp,
        rule=lambda m, n: m.cap_tes[n] >= tes_min_dur * m.cap_chp[n] * alpha
                          - _M_tes * (1 - m.inv_tes[n]),
        doc="TES 최소 용량 (설치 시)")

    # ── CHP / 보일러 운영 ─────────────────────────────────
    model.chp_elec_ub = pyo.Constraint(
        model.S, model.N_chp, model.T,
        rule=lambda m, s, n, t: m.p_chp_elec[s, n, t] <= m.cap_chp[n],
        doc="CHP 전기 출력 한계")
    model.chp_heat_def = pyo.Constraint(
        model.S, model.N_chp, model.T,
        rule=lambda m, s, n, t: m.p_chp_heat[s, n, t] == alpha * m.p_chp_elec[s, n, t],
        doc="CHP 열-전 병산 (열 = α·전기)")
    model.boiler_heat_ub = pyo.Constraint(
        model.S, model.N_chp, model.T,
        rule=lambda m, s, n, t: m.p_boiler_heat[s, n, t] <= m.cap_boiler[n],
        doc="보일러 열 출력 한계")

    # ── TES 운영 ──────────────────────────────────────────
    model.tes_charge_ub = pyo.Constraint(
        model.S, model.N_chp, model.T,
        rule=lambda m, s, n, t: m.tes_charge[s, n, t] <= m.cap_tes[n] / tes_max_dur,
        doc="TES 충열 출력 한계")
    model.tes_discharge_ub = pyo.Constraint(
        model.S, model.N_chp, model.T,
        rule=lambda m, s, n, t: m.tes_discharge[s, n, t] <= m.cap_tes[n] / tes_max_dur,
        doc="TES 방열 출력 한계")
    model.tes_soc_lb = pyo.Constraint(
        model.S, model.N_chp, model.T,
        rule=lambda m, s, n, t: m.soc_tes[s, n, t] >= tes_min_soc * m.cap_tes[n],
        doc="TES SOC 하한")
    model.tes_soc_ub = pyo.Constraint(
        model.S, model.N_chp, model.T,
        rule=lambda m, s, n, t: m.soc_tes[s, n, t] <= tes_max_soc * m.cap_tes[n],
        doc="TES SOC 상한")
    model.tes_soc_init = pyo.Constraint(
        model.S, model.N_chp,
        rule=lambda m, s, n: m.soc_tes[s, n, 0] == 0.5 * m.cap_tes[n],
        doc="TES 초기 SOC = 50%")
    model.tes_soc_end = pyo.Constraint(
        model.S, model.N_chp,
        rule=lambda m, s, n: (m.soc_tes[s, n, 23]
                              + tes_eta * m.tes_charge[s, n, 23]
                              - (1.0 / tes_eta) * m.tes_discharge[s, n, 23]
                              == 0.5 * m.cap_tes[n]),
        doc="TES 종기 SOC = 50% — t=23 충·방열 반영")

    def _tes_dynamics(m, s, n, t):
        if t == 0:
            return pyo.Constraint.Skip
        return m.soc_tes[s, n, t] == (m.soc_tes[s, n, t - 1]
                                      + tes_eta * m.tes_charge[s, n, t - 1]
                                      - (1.0 / tes_eta) * m.tes_discharge[s, n, t - 1])

    model.tes_soc_dynamics = pyo.Constraint(
        model.S, model.N_chp, model.T, rule=_tes_dynamics,
        doc="TES SOC 동특성")

    # ── 로컬 열균형 (DHN 미사용 시에만) ───────────────────
    if not dhn_enabled:
        model.heat_balance = pyo.Constraint(
            model.S, model.N_chp, model.T,
            rule=lambda m, s, n, t:
                m.p_chp_heat[s, n, t] + m.p_boiler_heat[s, n, t]
                + m.tes_discharge[s, n, t] - m.tes_charge[s, n, t]
                >= m.heat_load[s, n, t],
            doc="노드별 로컬 열 수급 균형")
