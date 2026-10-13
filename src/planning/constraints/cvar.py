"""
cvar.py - 조건부 위험가치(CVaR) 리스크 항

물리적 의미:
    시나리오별 운영비 분포의 상위 (1-α) 최악 구간 평균(tail risk)을
    Rockafellar-Uryasev 선형화로 표현한다. 목적함수에서 λ 가중으로 결합된다.

수식 (Rockafellar & Uryasev, 2000):
    CVaR_α = η + 1/(1-α)·Σ_s prob[s]·z[s]
    s.t.  z[s] ≥ op_cost[s] - η,   z[s] ≥ 0          ∀ s

    η ≈ VaR_α (최적해에서). z[s] = 초과손실.
"""

import pyomo.environ as pyo

from src.utils.config_loader import get


def add_cvar_risk(model: pyo.ConcreteModel, config: dict, op_cost_exprs: list):
    """
    CVaR 보조 제약을 추가하고 CVaR 항(목적함수에 더할 표현식)을 반환.
    model.cvar_eta, model.cvar_z 변수는 model.py 에서 미리 선언되어 있어야 한다.
    """
    alpha = get(config, "planning.alpha", 0.95)

    model.cvar_link = pyo.Constraint(
        model.S,
        rule=lambda m, s: m.cvar_z[s] >= op_cost_exprs[s] - m.cvar_eta,
        doc="CVaR 초과손실 선형화 (z ≥ op_cost - η)")

    return (model.cvar_eta
            + 1.0 / (1.0 - alpha)
            * sum(model.prob[s] * model.cvar_z[s] for s in model.S))
