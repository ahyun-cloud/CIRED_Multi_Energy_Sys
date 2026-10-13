"""
balance.py - 계통 전력 수급 균형 (변전소 연계점 단일 정산)

물리적 의미:
    계통 전체에서 시각별 수전(import) - 수출(export) 은
    [총 부하 + 총 충전 - 총 방전 - 총 PV발전 - 총 CHP발전] 과 같다.
    노드별 조류는 grid.py 의 LPF 감도 제약으로 별도 처리한다.

수식:
    p_import[s,t] - p_export[s,t]
      = Σ_n load[s,n,t] + Σ_n charge[s,n,t] - Σ_n discharge[s,n,t]
        - Σ_n p_pv[s,n,t] - Σ_n p_chp_elec[s,n,t]        ∀ s,t
"""

import pyomo.environ as pyo


def add_power_balance_constraints(model: pyo.ConcreteModel, chp_enabled: bool):
    def _balance(m, s, t):
        total_load = sum(m.elec_load[s, n, t] for n in m.N)
        total_pv = sum(m.p_pv[s, n, t] for n in m.N_pv)
        total_charge = sum(m.p_charge[s, n, t] for n in m.N_ess)
        total_discharge = sum(m.p_discharge[s, n, t] for n in m.N_ess)
        total_chp = (sum(m.p_chp_elec[s, n, t] for n in m.N_chp)
                     if chp_enabled else 0.0)
        net = (total_load + total_charge - total_discharge
               - total_pv - total_chp)
        return m.p_import[s, t] - m.p_export[s, t] == net

    model.power_balance = pyo.Constraint(
        model.S, model.T, rule=_balance, doc="계통 전력 수급 균형")
