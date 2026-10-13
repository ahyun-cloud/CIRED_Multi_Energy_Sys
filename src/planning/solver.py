"""
solver.py - Solver 실행 및 결과 상태 검증

역할:
    1. config['solver'] 설정으로 solver 구성 (cplex / gurobi / cbc)
    2. 풀이 실행 및 termination 상태 확인
    3. infeasible/unbounded 시 진단 로그
"""

import json
import logging
from pathlib import Path

import pyomo.environ as pyo

from src.utils.config_loader import get

logger = logging.getLogger("cired")


def load_siting(scenario_name: str, outputs_dir="outputs") -> dict:
    """이전에 풀린 시나리오의 summary.json 에서 설치 노드(siting) 집합 로드.

    대규모 시나리오(MC100)를 tractable 하게 풀기 위해, tractable 한 시나리오
    (rep24 등)에서 결정한 siting 을 재사용한다. 노드 집합만 쓰므로 반올림 무관.
    """
    p = Path(outputs_dir) / scenario_name / "results" / "summary.json"
    if not p.exists():
        raise FileNotFoundError(
            f"siting_from='{scenario_name}' 결과 없음: {p}\n"
            f"  → 먼저 'python run_scenario.py --scenario {scenario_name}' 실행 필요")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return {
        "pv":  {int(k) for k in d.get("pv_sites", {})},
        "ess": {int(k) for k, v in d.get("ess_sites", {}).items() if v.get("P_MW", 0) > 1e-4},
        "chp": {int(k) for k, v in d.get("chp_sites", {}).items() if v.get("P_e_MW", 0) > 1e-4},
        "tes": {int(k) for k, v in d.get("chp_sites", {}).items() if v.get("E_tes_MWh", 0) > 1e-4},
    }


def load_warmstart(scenario_name: str, outputs_dir="outputs") -> dict | None:
    """이전에 풀린 시나리오의 summary.json 에서 1단계(투자) 해를 로드 (MIP warm-start용).

    siting 만 쓰는 load_siting 과 달리, 설치노드+용량까지 모두 읽어
    1단계 변수에 초기값으로 주입하기 위한 원본(raw summary)을 반환한다.
    원본이 없으면 None (호출부에서 cold start 로 폴백).
    """
    p = Path(outputs_dir) / scenario_name / "results" / "summary.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def apply_warmstart(model: pyo.ConcreteModel, summary: dict):
    """summary.json 의 1단계 해(설치여부+용량)를 model 변수 .value 로 설정.

    부분(partial) MIP start — 1단계 변수만 채우면 CPLEX 가 2단계(운영) LP 를
    repair 로 완성한다. 1단계가 조합적 난이도의 핵심이므로 이것만으로 충분히
    좋은 incumbent 를 빠르게 확보해 junk incumbent 갇힘을 방지한다.
    """
    def _set(var, val):
        var.set_value(float(val), skip_validation=True)

    pv = summary.get("pv_sites", {})
    for n in model.N_pv:
        v = pv.get(str(n))
        on = v is not None
        _set(model.inv_pv[n], 1 if on else 0)
        _set(model.cap_pv[n], v.get("cap_MWp", 0.0) if on else 0.0)

    ess = summary.get("ess_sites", {})
    for n in model.N_ess:
        v = ess.get(str(n))
        on = v is not None and v.get("P_MW", 0) > 1e-6
        _set(model.inv_ess[n], 1 if on else 0)
        _set(model.cap_ess_p[n], v.get("P_MW", 0.0) if on else 0.0)
        _set(model.cap_ess_e[n], v.get("E_MWh", 0.0) if on else 0.0)

    if hasattr(model, "inv_chp"):
        chp = summary.get("chp_sites", {})
        for n in model.N_chp:
            v = chp.get(str(n))
            chp_on = v is not None and v.get("P_e_MW", 0) > 1e-6
            _set(model.inv_chp[n], 1 if chp_on else 0)
            _set(model.cap_chp[n], v.get("P_e_MW", 0.0) if v else 0.0)
            boiler_on = v is not None and v.get("P_boiler_MW", 0) > 1e-6
            _set(model.inv_boiler[n], 1 if boiler_on else 0)
            _set(model.cap_boiler[n], v.get("P_boiler_MW", 0.0) if v else 0.0)
            tes_on = v is not None and v.get("E_tes_MWh", 0) > 1e-6
            _set(model.inv_tes[n], 1 if tes_on else 0)
            _set(model.cap_tes[n], v.get("E_tes_MWh", 0.0) if v else 0.0)


def fix_siting(model: pyo.ConcreteModel, siting: dict, free_ess: bool = False):
    """1단계 siting(이진)을 고정 — 용량·운영·보일러는 자유.

    siting 조합 탐색(정수 폭발)을 제거해 대규모 시나리오를 LP 수준으로 빠르게 푼다.
    보일러는 자유로 두어 꼬리 시나리오 열 백업을 허용한다.

    free_ess=True 면 ESS 설치노드를 고정하지 않는다(11개 이진만 남음). ESS 거동 자체가
    분석 대상인 경우(λ·α 민감도, 단가·FR 민감도)에는 반드시 이 옵션을 써야 한다 —
    기준 해의 ESS 가 0 이면 siting 고정이 ESS 를 0 으로 강제해 분석이 무의미해진다.
    """
    for n in model.N_pv:
        model.inv_pv[n].fix(1 if n in siting["pv"] else 0)
    if not free_ess:
        for n in model.N_ess:
            model.inv_ess[n].fix(1 if n in siting["ess"] else 0)
    if hasattr(model, "inv_chp"):
        for n in model.N_chp:
            model.inv_chp[n].fix(1 if n in siting["chp"] else 0)
            model.inv_tes[n].fix(1 if n in siting["tes"] else 0)
            # inv_boiler 는 자유 (꼬리 시나리오 열 백업)


def solve_model(model: pyo.ConcreteModel, config: dict, warmstart: bool = False):
    """모델 풀이 + 상태 검증. (solver_results, status_str) 반환."""
    name = get(config, "solver.name", "cplex")
    time_limit = get(config, "solver.time_limit", 600)
    mip_gap = get(config, "solver.mip_gap", 0.005)
    verbose = get(config, "solver.verbose", False)

    solver = pyo.SolverFactory(name)
    if name == "gurobi":
        solver.options["TimeLimit"] = time_limit
        solver.options["MIPGap"] = mip_gap
        if not verbose:
            solver.options["OutputFlag"] = 0
    elif name == "cplex":
        o = solver.options
        o["timelimit"] = time_limit
        o["mip_tolerances_mipgap"] = mip_gap
        # ── 그 외 전부 OPT-IN (config.solver.* 에 명시할 때만) ──────
        #   ※ 항상-켬으로 두면 케이스별로 역효과. 특히 parallel=1(결정론)·emphasis_mip=2
        #     는 시간제한 MILP(rep24)에서 build-all junk 해로 끝나는 사례 확인됨.
        #     기본은 CPLEX 네이티브 디폴트(= 가장 안정적인 incumbent 탐색).
        for cfg_key, cplex_key in (("threads", "threads"),
                                   ("parallel", "parallel"),
                                   ("advance", "advance"),
                                   ("repair_tries", "mip_limits_repairtries"),
                                   ("emphasis_mip", "emphasis_mip"),
                                   ("probe", "mip_strategy_probe"),
                                   ("rins_freq", "mip_strategy_rinsheur")):
            v = get(config, f"solver.{cfg_key}", None)
            if v is not None:
                o[cplex_key] = v
        pol = get(config, "solver.polish_after_frac", None)
        if pol:
            o["mip_polishafter_time"] = float(pol) * time_limit
    else:  # cbc / glpk
        solver.options["sec"] = time_limit
        solver.options["ratio"] = mip_gap

    n_vars = sum(1 for _ in model.component_data_objects(pyo.Var, active=True))
    n_cons = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))
    logger.info(f"Solver={name}  변수={n_vars:,}  제약={n_cons:,}  "
                f"(time_limit={time_limit}s, gap={mip_gap})")

    if warmstart:
        logger.info("warm-start: 1단계 해를 MIP start 로 전달")
    results = solver.solve(model, tee=verbose, warmstart=warmstart)
    status = str(results.solver.termination_condition)

    if status == str(pyo.TerminationCondition.optimal):
        logger.info(f"✓ Optimal — 목적함수 = {pyo.value(model.objective):,.0f} 원")
    elif status == str(pyo.TerminationCondition.maxTimeLimit):
        try:
            logger.warning(f"⚠ 시간제한 도달 — incumbent 목적함수 "
                           f"= {pyo.value(model.objective):,.0f} 원")
        except Exception:                              # noqa: BLE001
            logger.error("⚠ 시간제한 도달 — feasible 해 없음")
    elif "infeasible" in status.lower():
        logger.error("✗ INFEASIBLE — 실행 가능 해 없음")
        _diagnose(model, config)
    elif "unbounded" in status.lower():
        logger.error("✗ UNBOUNDED — 목적함수 하한 없음 (변수 범위/비용 부호 확인)")
    else:
        logger.warning(f"⚠ Solver 종료 상태: {status}")

    return results, status


def _diagnose(model: pyo.ConcreteModel, config: dict):
    """infeasible 진단: 제약 블록 요약 + 권장 조치."""
    logger.info("=" * 55)
    logger.info("INFEASIBILITY 진단")
    cons = list(model.component_objects(pyo.Constraint, active=True))
    for con in cons:
        logger.info(f"  {con.name}: {len(list(con))} constraints")
    if not get(config, "grid.relax_voltage", False):
        logger.info("TIP: grid.relax_voltage=true 로 전압 제약을 완화해 "
                    "위반 노드를 식별하세요.")
    logger.info("=" * 55)
