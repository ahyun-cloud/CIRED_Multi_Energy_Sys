"""
grid.py - LPF 감도행렬 기반 전압·전류 운영 제약

물리적 의미:
    노드별 순주입전력(발전 - 부하)의 변화가 전압·선로전류에 미치는 영향을
    선형 감도행렬(A_v, A_i)로 근사하여 운영 한계 내로 제한한다.

수식:
    V_MIN ≤ Σ_j A_v[i,j]·p_inj[j] + b_v[i] ≤ V_MAX        ∀ i∈PQ, s, t
    -I_MAX ≤ Σ_j A_i[l,j]·p_inj[j] + b_i[l] ≤ I_MAX         ∀ l, s, t

    p_inj[n] = (p_pv + p_discharge - p_charge - load + p_chp_elec) / BASE_MVA  [pu]

relax_voltage=True 면 전압 제약을 slack 변수로 완화하고 위반량에 큰 패널티를 부과한다
(출력제한 불가 등 tight 케이스의 feasibility 진단용).
"""

import pyomo.environ as pyo

from src.data_process.network import BASE_MVA, V_MIN, V_MAX, I_MAX_PU
from src.utils.config_loader import get


def add_grid_constraints(model: pyo.ConcreteModel, config: dict,
                         chp_enabled: bool):
    relax = get(config, "grid.relax_voltage", False)
    pq = list(model.PQ)

    def p_inj_pu(m, s, n, t):
        """노드 n 의 순유효전력 주입 [pu] (발전 - 부하)."""
        pv  = m.p_pv[s, n, t] if n in m.N_pv else 0.0
        ch  = m.p_charge[s, n, t] if n in m.N_ess else 0.0
        dis = m.p_discharge[s, n, t] if n in m.N_ess else 0.0
        chp = m.p_chp_elec[s, n, t] if (chp_enabled and n in m.N_chp) else 0.0
        return (pv + dis - ch - m.elec_load[s, n, t] + chp) / BASE_MVA

    def q_inj_pu(m, s, n, t):
        """노드 n 의 순무효전력 주입 [pu] (인버터 공급 - 부하 소비)."""
        qpv  = m.q_pv[s, n, t] if n in m.N_pv else 0.0
        qess = m.q_ess[s, n, t] if n in m.N_ess else 0.0
        return (qpv + qess - m.react_load[s, n, t]) / BASE_MVA

    def _v_expr(m, s, i, t):
        return (sum(m.Av[i, j]  * p_inj_pu(m, s, j, t) for j in pq)
              + sum(m.Avq[i, j] * q_inj_pu(m, s, j, t) for j in pq)
              + m.bv[i])

    if relax:
        model.volt_lb = pyo.Constraint(
            model.S, model.PQ, model.T,
            rule=lambda m, s, i, t: _v_expr(m, s, i, t) + m.v_slack_dn[s, i, t] >= V_MIN,
            doc="전압 하한 (완화)")
        model.volt_ub = pyo.Constraint(
            model.S, model.PQ, model.T,
            rule=lambda m, s, i, t: _v_expr(m, s, i, t) - m.v_slack_up[s, i, t] <= V_MAX,
            doc="전압 상한 (완화)")
    else:
        model.volt_lb = pyo.Constraint(
            model.S, model.PQ, model.T,
            rule=lambda m, s, i, t: _v_expr(m, s, i, t) >= V_MIN,
            doc="전압 하한")
        model.volt_ub = pyo.Constraint(
            model.S, model.PQ, model.T,
            rule=lambda m, s, i, t: _v_expr(m, s, i, t) <= V_MAX,
            doc="전압 상한")

    model.curr_ub = pyo.Constraint(
        model.S, model.L, model.T,
        rule=lambda m, s, l, t:
            sum(m.Ai[l, j] * p_inj_pu(m, s, j, t) for j in pq)
            + m.bi[l] <= I_MAX_PU,
        doc="선로 전류 상한")
    model.curr_lb = pyo.Constraint(
        model.S, model.L, model.T,
        rule=lambda m, s, l, t:
            sum(m.Ai[l, j] * p_inj_pu(m, s, j, t) for j in pq)
            + m.bi[l] >= -I_MAX_PU,
        doc="선로 전류 하한 (역방향)")
