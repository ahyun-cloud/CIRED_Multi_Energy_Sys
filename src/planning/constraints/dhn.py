"""
dhn.py - 선형 지역난방망(District Heating Network) 제약

물리적 의미:
    열원(CHP·보일러)이 생산한 열이 배관을 통해 다른 노드로 전달될 수 있도록
    네트워크 단위 열균형을 구성한다. 질량유량을 고정값으로 두어 온도만 변수로
    남기는 선형화(Q = mcp·ΔT)를 적용한다.

수식:
    q_pipe[l] = mcp·(T_sup[from] - T_ret[from])                         (열유량 정의)
    T_sup[to] = T_sup[from] - β·L·(T_sup[from] - T_amb)                 (배관 열손실)
    [네트워크 열균형]
      (p_chp_heat + p_boiler_heat + tes_dis - tes_ch)[n]
       + Σ_in q_pipe - Σ_out q_pipe ≥ heat_load[n]                       ∀ s,n,t

Limitation (논문 기술):
    유량 고정·압력손실 무시·선형 열손실 → hydraulic 모델 대비 정확도 낮음(MILP 유지 목적).

가정 수정 (이전 버전 대비):
    배관 열손실을 mcp 와 무관한 무차원 손실계수 β[/km] 로 재정의하여
    공급온도 제약([T_sup_min, T_sup_max])과 양립 가능한 feasible 모델로 보정.
"""

import pyomo.environ as pyo

from src.data_process.network import DHN_PIPE_DATA
from src.utils.config_loader import get


def add_dhn_constraints(model: pyo.ConcreteModel, config: dict):
    cp = get(config, "dhn.cp", 4.182)                    # 물 비열 [kJ/(kg·°C)]
    m_dot = get(config, "dhn.m_dot_base", 10.0)          # 질량유량 [kg/s]
    mcp = m_dot * cp * 1e-3                               # [MW/°C]

    t_amb = get(config, "dhn.t_amb", 10.0)               # 외기 [°C]
    t_sup_max = get(config, "dhn.t_sup_max", 120.0)
    t_ret_min = get(config, "dhn.t_ret_min", 40.0)
    beta = get(config, "dhn.temp_loss_per_km", 0.02)     # 무차원 손실률 [/km]
    dt_min = get(config, "dhn.min_temp_diff", 10.0)      # 최소 공급-환수 온도차 [°C]

    pipe_from = [int(p[0]) for p in DHN_PIPE_DATA]
    pipe_to = [int(p[1]) for p in DHN_PIPE_DATA]
    pipe_len = [float(p[2]) for p in DHN_PIPE_DATA]
    q_pipe_max = mcp * (t_sup_max - t_ret_min)           # [MW_th] 배관 용량

    # ── 열유량 정의 ───────────────────────────────────────
    model.dhn_q_def = pyo.Constraint(
        model.S, model.DHN_P, model.T,
        rule=lambda m, s, l, t:
            m.q_pipe[s, l, t] == mcp * (m.t_supply[s, pipe_from[l], t]
                                        - m.t_return[s, pipe_from[l], t]),
        doc="배관 열유량 = mcp·(T_sup-T_ret)")

    # ── 배관 열손실 (공급온도 강하) ───────────────────────
    def _temp_drop(m, s, l, t):
        loss_rate = beta * pipe_len[l]                   # [무차원]
        return (m.t_supply[s, pipe_to[l], t]
                == m.t_supply[s, pipe_from[l], t]
                - loss_rate * (m.t_supply[s, pipe_from[l], t] - t_amb))

    model.dhn_temp_drop = pyo.Constraint(
        model.S, model.DHN_P, model.T, rule=_temp_drop,
        doc="배관 열손실에 의한 공급온도 강하")

    # ── 네트워크 열균형 (TES·배관 포함) ───────────────────
    def _heat_balance(m, s, n, t):
        local = (m.p_chp_heat[s, n, t] + m.p_boiler_heat[s, n, t]
                 + m.tes_discharge[s, n, t] - m.tes_charge[s, n, t])
        q_in = sum(m.q_pipe[s, l, t] for l in range(len(pipe_to))
                   if pipe_to[l] == n)
        q_out = sum(m.q_pipe[s, l, t] for l in range(len(pipe_from))
                    if pipe_from[l] == n)
        return local + q_in - q_out >= m.heat_load[s, n, t]

    model.dhn_heat_balance = pyo.Constraint(
        model.S, model.N_chp, model.T, rule=_heat_balance,
        doc="네트워크 노드별 열 수급 균형")

    # ── 온도차·배관 용량 ──────────────────────────────────
    model.dhn_temp_diff = pyo.Constraint(
        model.S, model.N_chp, model.T,
        rule=lambda m, s, n, t: m.t_return[s, n, t] <= m.t_supply[s, n, t] - dt_min,
        doc="공급-환수 최소 온도차")
    model.dhn_q_ub = pyo.Constraint(
        model.S, model.DHN_P, model.T,
        rule=lambda m, s, l, t: m.q_pipe[s, l, t] <= q_pipe_max,
        doc="배관 열유량 상한")
    model.dhn_q_lb = pyo.Constraint(
        model.S, model.DHN_P, model.T,
        rule=lambda m, s, l, t: m.q_pipe[s, l, t] >= -q_pipe_max,
        doc="배관 열유량 하한 (역방향)")
