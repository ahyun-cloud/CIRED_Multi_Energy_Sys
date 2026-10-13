# PYOMO_PATTERNS.md
# 전력 시스템 최적화 코딩 패턴 가이드 (Pyomo 기반)

> `docs/guides/PROJECT_GUIDE.md`(1단계: 폴더 구조)를 따른 뒤, 이 문서의 패턴을 적용하세요.
> 여기 나오는 코드는 **복사해서 바로 쓸 수 있는 템플릿**입니다.

---

## 목차

1. [Pyomo 모델 함수화 패턴](#1-pyomo-모델-함수화-패턴)
2. [Constraint 모듈화](#2-constraint-모듈화)
3. [시나리오 Config 고급 패턴](#3-시나리오-config-고급-패턴)
4. [Solver 관리 패턴](#4-solver-관리-패턴)
5. [결과 추출 표준화](#5-결과-추출-표준화)
6. [자주 하는 실수와 해결법](#6-자주-하는-실수와-해결법)

---

## 1. Pyomo 모델 함수화 패턴

### ❌ 나쁜 예: 모든 것이 한 파일에

```python
# bad_example.py (1200줄짜리 스크립트)
import pyomo.environ as pyo

model = pyo.ConcreteModel()
model.T = pyo.Set(initialize=range(24))
model.G = pyo.Set(initialize=['gen1', 'gen2', 'gen3'])
model.N = pyo.Set(initialize=['bus1', 'bus2', 'bus3'])
# ... Set 30개
# ... Parameter 50개
# ... Variable 20개
# ... Constraint 40개
# ... Objective
# ... Solve
# ... 결과 추출 100줄
# ... Figure 그리기 200줄
```

### ✅ 좋은 예: build → solve → extract 3단계 분리

```
src/dso/planning/
├── expansion_model.py    # build_model()        ← 모델 구성
├── constraints/          # Constraint 함수 모음
│   ├── __init__.py
│   ├── power_balance.py
│   ├── line_flow.py
│   ├── generation.py
│   └── investment.py
├── solver.py             # solve_model()         ← 풀이
└── extractor.py          # extract_results()     ← 결과 추출
```

### 모델 빌더 템플릿 (`expansion_model.py`)

```python
"""
expansion_model.py - DSO 설비 확장 계획 모델

이 파일은 모델 '구조'만 정의합니다.
- Set, Parameter, Variable, Objective 정의
- Constraint는 constraints/ 폴더에서 import
- 풀이는 solver.py, 결과 추출은 extractor.py
"""

import pyomo.environ as pyo
from src.data_process.loader import load_data

# Constraint 함수들을 import
from .constraints.power_balance import add_power_balance_constraints
from .constraints.line_flow import add_line_flow_constraints
from .constraints.generation import add_generation_constraints
from .constraints.investment import add_investment_constraints


def build_model(config: dict, data: dict) -> pyo.ConcreteModel:
    """
    모델 구성 함수. config와 data를 받아 ConcreteModel을 반환.

    Parameters
    ----------
    config : dict
        scenarios/scenario_x.yaml 에서 로드한 설정
    data : dict
        data/ 폴더에서 로드한 입력 데이터
        keys: 'demand', 'network', 'generators', 'candidates' 등

    Returns
    -------
    pyo.ConcreteModel
        풀이 전 상태의 완성된 모델
    """
    model = pyo.ConcreteModel(name=config.get("scenario_name", "unnamed"))

    # ── Sets ──────────────────────────────────
    _define_sets(model, config, data)

    # ── Parameters ────────────────────────────
    _define_parameters(model, config, data)

    # ── Variables ─────────────────────────────
    _define_variables(model, config)

    # ── Constraints ───────────────────────────
    add_power_balance_constraints(model)
    add_line_flow_constraints(model)
    add_generation_constraints(model, config)
    add_investment_constraints(model, config)

    # 시나리오별 선택적 constraint
    if config["parameters"].get("carbon_cap_enabled", False):
        from .constraints.carbon import add_carbon_cap_constraints
        add_carbon_cap_constraints(model, config)

    # ── Objective ─────────────────────────────
    _define_objective(model, config)

    return model


# ── 내부 함수 (private) ──────────────────────────

def _define_sets(model, config, data):
    """Set 정의를 모아둔 내부 함수"""
    T = config.get("time_horizon_hours", 24)

    model.T = pyo.Set(initialize=range(T), doc="시간 인덱스")
    model.N = pyo.Set(initialize=data["network"]["bus"].unique(), doc="노드(버스)")
    model.G = pyo.Set(initialize=data["generators"]["gen_id"].unique(), doc="기존 발전기")
    model.L = pyo.Set(initialize=data["network"]["line_id"].unique(), doc="선로")
    model.C = pyo.Set(initialize=data["candidates"]["cand_id"].unique(), doc="투자 후보")

    # 발전기-노드 매핑 (2차원 Set)
    gen_bus_pairs = list(zip(
        data["generators"]["gen_id"],
        data["generators"]["bus"]
    ))
    model.GB = pyo.Set(within=model.G * model.N, initialize=gen_bus_pairs)


def _define_parameters(model, config, data):
    """Parameter 정의"""
    demand_dict = {
        (row["bus"], row["hour"]): row["demand_mw"]
        for _, row in data["demand"].iterrows()
    }
    model.Demand = pyo.Param(model.N, model.T, initialize=demand_dict, doc="시간별 수요 [MW]")

    gen_data = data["generators"].set_index("gen_id")
    model.Pmax = pyo.Param(
        model.G,
        initialize=gen_data["pmax_mw"].to_dict(),
        doc="최대 출력 [MW]"
    )
    model.GenCost = pyo.Param(
        model.G,
        initialize=gen_data["cost_per_mwh"].to_dict(),
        doc="발전 한계비용 [$/MWh]"
    )

    # 시나리오 파라미터
    model.DiscountRate = pyo.Param(
        initialize=config["parameters"].get("discount_rate", 0.05)
    )
    model.CarbonPrice = pyo.Param(
        initialize=config["parameters"].get("carbon_price_usd_per_ton", 0)
    )


def _define_variables(model, config):
    """Variable 정의"""
    model.p = pyo.Var(model.G, model.T, within=pyo.NonNegativeReals, doc="발전량 [MW]")
    model.x_inv = pyo.Var(model.C, within=pyo.Binary, doc="투자 결정 (0/1)")
    model.flow = pyo.Var(model.L, model.T, within=pyo.Reals, doc="선로 조류 [MW]")


def _define_objective(model, config):
    """목적함수 정의"""
    def total_cost_rule(m):
        # 운영비
        op_cost = sum(
            m.GenCost[g] * m.p[g, t]
            for g in m.G for t in m.T
        )
        # 탄소비용
        carbon_cost = sum(
            m.CarbonPrice * m.p[g, t] * 0.5  # 0.5 tCO2/MWh 가정
            for g in m.G for t in m.T
        )
        return op_cost + carbon_cost

    model.TotalCost = pyo.Objective(rule=total_cost_rule, sense=pyo.minimize)
```

---

## 2. Constraint 모듈화

### 핵심 원칙: 하나의 파일 = 하나의 물리적 의미

```
constraints/
├── power_balance.py    # 전력 수급 균형 (노드별 유효/무효전력)
├── line_flow.py        # 선로 조류 제약 (DC-OPF or AC-OPF)
├── generation.py       # 발전기 운영 제약 (출력 한계, ramp 등)
├── investment.py       # 투자 관련 제약 (예산, 건설 기간 등)
└── carbon.py           # 탄소 배출 상한 (선택적 활성화)
```

### Constraint 파일 템플릿 (`power_balance.py`)

```python
"""
power_balance.py - 노드별 전력 수급 균형 제약

물리적 의미:
    각 노드에서, 해당 노드의 발전량 합 - 유출 조류 합 = 수요
"""

import pyomo.environ as pyo


def add_power_balance_constraints(model: pyo.ConcreteModel):
    """
    모델에 전력 수급 균형 제약을 추가

    수식:
        sum(p[g,t] for g in node) + sum(flow_in) - sum(flow_out) = Demand[n,t]
        ∀ n ∈ N, t ∈ T
    """

    def power_balance_rule(m, n, t):
        # 해당 노드의 발전량 합
        gen_at_node = sum(
            m.p[g, t] for (g, bus) in m.GB if bus == n
        )
        # 선로 조류 (간략화 버전, 실제로는 incidence matrix 사용)
        # flow_in - flow_out 은 프로젝트에 맞게 수정
        return gen_at_node == m.Demand[n, t]

    model.PowerBalance = pyo.Constraint(
        model.N, model.T,
        rule=power_balance_rule,
        doc="노드별 전력 수급 균형"
    )
```

### Constraint 파일 작성 규칙

```python
"""
[constraint_name].py - [한 줄 설명]

물리적 의미:
    [이 제약이 현실에서 무엇을 의미하는지 2-3줄로 설명]
    학생들이 논문 없이도 제약의 목적을 이해할 수 있도록 작성

수식 (LaTeX 스타일):
    sum_{g ∈ G_n} p_{g,t} = D_{n,t}    ∀ n ∈ N, t ∈ T
"""


def add_xxx_constraints(model, config=None):
    """
    Parameters
    ----------
    model : pyo.ConcreteModel
    config : dict, optional
        시나리오별로 제약 동작이 달라질 경우 사용
        예: config["parameters"]["ramp_limit_enabled"]
    """
    # 1. 필요한 전처리 (있다면)
    # 2. Constraint rule 정의
    # 3. model에 Constraint 추가

    def some_rule(m, *indices):
        return ...  # Constraint expression

    model.SomeConstraint = pyo.Constraint(
        model.SET1, model.SET2,
        rule=some_rule,
        doc="제약 설명"
    )
```

---

## 3. 시나리오 Config 고급 패턴

### 기본: 숫자만 바꾸는 경우

```yaml
# scenarios/base.yaml (공통 기본값)
time_horizon_hours: 8760
solver: "gurobi"
solver_options:
  MIPGap: 0.01
  TimeLimit: 7200

parameters:
  discount_rate: 0.05
  demand_growth_rate: 0.02
  carbon_price_usd_per_ton: 0
  renewable_target: 0.0
  carbon_cap_enabled: false
  ramp_limit_enabled: true

data_files:
  demand: "demand_2030.csv"
  network: "network_base.csv"
  generators: "generators.csv"
  candidates: "candidates.csv"
```

### 고급 1: 정책 Constraint On/Off

```yaml
# scenarios/scenario_high_re.yaml
inherit: "base"  # base.yaml 기본값을 상속

scenario_name: "High RE + Carbon Cap"
description: "재생에너지 80% + 탄소 상한 적용"

parameters:
  renewable_target: 0.80
  carbon_cap_enabled: true        # ← 탄소 상한 제약 활성화
  carbon_cap_mt_per_year: 50.0
  carbon_price_usd_per_ton: 30
```

### 고급 2: Technology Cost Trajectory

```yaml
# scenarios/scenario_low_battery.yaml
inherit: "base"

scenario_name: "Low Battery Cost Trajectory"
description: "배터리 가격 급락 시나리오"

parameters:
  renewable_target: 0.60

# 연도별 기술 비용 경로 (config에서 직접 정의)
technology_cost_trajectory:
  battery:
    2025: 200   # $/kWh
    2030: 120
    2035: 80
    2040: 60
  offshore_wind:
    2025: 3500  # $/kW
    2030: 2800
    2035: 2200
    2040: 1800
```

### 고급 3: 네트워크 구조 변경

```yaml
# scenarios/scenario_new_line.yaml
inherit: "base"

scenario_name: "신규 송전선 추가"
description: "bus3-bus5 구간 345kV 신설 시나리오"

data_files:
  network: "network_with_new_line.csv"  # ← 다른 네트워크 파일 지정

# 또는 base 네트워크에 추가할 선로를 config에서 정의
network_additions:
  - from_bus: "bus3"
    to_bus: "bus5"
    voltage_kv: 345
    capacity_mw: 500
    length_km: 120
    cost_million_usd: 250
```

### Config 로더에서 상속 처리

```python
# src/utils/config_loader.py

import yaml
from pathlib import Path
from copy import deepcopy


def load_config(scenario_name: str, scenarios_dir: str = "scenarios") -> dict:
    """
    YAML config 로드. 'inherit' 키가 있으면 base config를 먼저 로드 후 덮어쓰기.

    scenarios/base.yaml:
        discount_rate: 0.05
        renewable_target: 0.0

    scenarios/scenario_1.yaml:
        inherit: "base"
        renewable_target: 0.80    ← 이것만 덮어씀
    """
    config_path = Path(scenarios_dir) / f"{scenario_name}.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 상속 처리
    if "inherit" in config:
        base_name = config.pop("inherit")
        base_config = load_config(base_name, scenarios_dir)  # 재귀 호출
        config = _deep_merge(base_config, config)

    config["_scenario_name"] = scenario_name
    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """dict를 재귀적으로 병합. override가 우선."""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
```

---

## 4. Solver 관리 패턴

### Solver 래퍼 (`src/utils/solver.py`)

```python
"""
solver.py - Solver 실행 및 결과 검증

역할:
    1. Solver 설정 (옵션, 시간제한 등)
    2. 풀이 실행
    3. 결과 상태 확인 (optimal / infeasible / unbounded)
    4. Infeasibility 디버깅 지원
"""

import pyomo.environ as pyo
import logging

logger = logging.getLogger(__name__)


def solve_model(
    model: pyo.ConcreteModel,
    config: dict
) -> pyo.SolverResults:
    """
    모델 풀이 실행 + 결과 검증

    Returns
    -------
    pyo.SolverResults

    Raises
    ------
    RuntimeError
        solver가 optimal을 찾지 못한 경우
    """
    solver_name = config.get("solver", "gurobi")
    solver_options = config.get("solver_options", {})

    solver = pyo.SolverFactory(solver_name)
    for key, value in solver_options.items():
        solver.options[key] = value

    logger.info(f"Solver: {solver_name}, Options: {solver_options}")
    logger.info(f"Variables: {len(list(model.component_objects(pyo.Var)))}")
    logger.info(f"Constraints: {len(list(model.component_objects(pyo.Constraint)))}")

    results = solver.solve(model, tee=True)

    # ── 결과 상태 확인 ──
    status = results.solver.termination_condition

    if status == pyo.TerminationCondition.optimal:
        obj_value = pyo.value(model.TotalCost)
        logger.info(f"✓ Optimal found. Objective = {obj_value:,.2f}")

    elif status == pyo.TerminationCondition.infeasible:
        logger.error("✗ INFEASIBLE - 실행 가능 해가 없음")
        _log_infeasibility_diagnosis(model)
        raise RuntimeError("Model is infeasible. Check run.log for diagnosis.")

    elif status == pyo.TerminationCondition.unbounded:
        logger.error("✗ UNBOUNDED - 목적함수에 하한이 없음")
        raise RuntimeError("Model is unbounded. Check objective and variable bounds.")

    else:
        logger.warning(f"⚠ Solver terminated with: {status}")

    return results


def _log_infeasibility_diagnosis(model: pyo.ConcreteModel):
    """
    Infeasible 모델의 원인을 진단하는 헬퍼

    실행 순서:
        1. 각 Constraint를 비활성화하며 재풀이 → 어떤 제약이 문제인지 파악
        2. Variable bound 확인
    """
    logger.info("=" * 60)
    logger.info("INFEASIBILITY DIAGNOSIS START")
    logger.info("=" * 60)

    # 방법 1: 각 Constraint 블록을 하나씩 비활성화하며 테스트
    constraints = list(model.component_objects(pyo.Constraint, active=True))
    logger.info(f"Active constraint blocks: {len(constraints)}")

    for con in constraints:
        con_name = con.name
        num_constraints = len(list(con))
        logger.info(f"  {con_name}: {num_constraints} constraints")

    # 방법 2: Variable bounds 요약
    logger.info("-" * 40)
    logger.info("Variable bounds summary:")
    for var in model.component_objects(pyo.Var, active=True):
        var_name = var.name
        sample = list(var.values())[:3]  # 처음 3개만
        for v in sample:
            logger.info(f"  {v.name}: lb={v.lb}, ub={v.ub}, value={v.value}")

    logger.info("=" * 60)
    logger.info("TIP: Constraint를 하나씩 deactivate하며 재풀이 해보세요")
    logger.info("  model.SomeConstraint.deactivate()")
    logger.info("=" * 60)
```

### Infeasibility 대화형 디버깅 (개발 중 사용)

```python
# notebooks/ 또는 디버깅 스크립트에서 사용
# 어떤 constraint가 infeasibility를 유발하는지 빠르게 찾기

def find_infeasible_constraint(model, config):
    """
    Constraint 블록을 하나씩 비활성화하며 재풀이.
    어떤 제약을 끄면 feasible해지는지 확인.
    """
    solver = pyo.SolverFactory(config.get("solver", "gurobi"))

    constraints = list(model.component_objects(pyo.Constraint, active=True))

    for con in constraints:
        con.deactivate()
        results = solver.solve(model, tee=False)
        status = results.solver.termination_condition

        if status == pyo.TerminationCondition.optimal:
            print(f"✓ Feasible when '{con.name}' is OFF → 이 제약이 문제!")
        else:
            print(f"  Still infeasible without '{con.name}'")

        con.activate()  # 복원
```

---

## 5. 결과 추출 표준화

### ❌ 나쁜 예: 결과를 하드코딩으로 뽑기

```python
# 매번 이렇게 쓰면 실수하기 쉽고, 변수가 바뀔 때마다 수정해야 함
results_gen = []
for g in model.G:
    for t in model.T:
        results_gen.append({
            'gen': g, 'time': t, 'power': pyo.value(model.p[g, t])
        })
df_gen = pd.DataFrame(results_gen)

results_inv = []
for c in model.C:
    results_inv.append({
        'candidate': c, 'invested': pyo.value(model.x_inv[c])
    })
df_inv = pd.DataFrame(results_inv)
# ... 이런 식으로 변수마다 반복 ...
```

### ✅ 좋은 예: 범용 추출 함수

```python
# src/utils/extractor.py

"""
extractor.py - Pyomo 모델 결과 추출 유틸리티

사용법:
    from src.utils.extractor import extract_variable, extract_all, extract_duals

    df = extract_variable(model.p)
    all_results = extract_all(model)
    duals = extract_duals(model.PowerBalance)
"""

import pyomo.environ as pyo
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def extract_variable(var: pyo.Var, name: str = None) -> pd.DataFrame:
    """
    Pyomo Variable → DataFrame 자동 변환

    Parameters
    ----------
    var : pyo.Var
        추출할 변수 (1차원, 2차원, 3차원 모두 지원)
    name : str, optional
        값 컬럼 이름. 미지정 시 변수 이름 사용.

    Returns
    -------
    pd.DataFrame
        인덱스별 값을 담은 DataFrame

    Examples
    --------
    >>> extract_variable(model.p)
        index_0  index_1     p
    0   gen1     0         100.0
    1   gen1     1          95.5
    ...
    """
    var_name = name or var.name
    records = []

    for index in var:
        val = pyo.value(var[index], exception=False)
        if val is None:
            continue

        # index가 tuple이면 풀어서, 아니면 리스트로 감싸기
        idx = index if isinstance(index, tuple) else (index,)
        record = {f"index_{i}": v for i, v in enumerate(idx)}
        record[var_name] = val
        records.append(record)

    return pd.DataFrame(records)


def extract_duals(constraint: pyo.Constraint, name: str = None) -> pd.DataFrame:
    """
    Constraint의 dual variable (shadow price) 추출

    주의: LP만 가능. MIP는 dual이 없으므로 LP relaxation 후 사용.

    Examples
    --------
    >>> duals = extract_duals(model.PowerBalance)
        index_0  index_1  dual_PowerBalance
    0   bus1     0        35.2
    1   bus1     1        38.1
    """
    con_name = name or f"dual_{constraint.name}"
    records = []

    for index in constraint:
        try:
            dual_val = constraint[index].expr
            # model.dual 사용 시:
            # dual_val = model.dual[constraint[index]]
            idx = index if isinstance(index, tuple) else (index,)
            record = {f"index_{i}": v for i, v in enumerate(idx)}
            record[con_name] = dual_val
            records.append(record)
        except (AttributeError, KeyError):
            pass

    return pd.DataFrame(records)


def extract_all(model: pyo.ConcreteModel) -> dict:
    """
    모델의 모든 Variable을 한 번에 추출

    Returns
    -------
    dict
        {변수이름: DataFrame} 형태
    """
    results = {}
    for var in model.component_objects(pyo.Var, active=True):
        df = extract_variable(var)
        if not df.empty:
            results[var.name] = df
            logger.info(f"Extracted {var.name}: {len(df)} rows")
    return results


def save_results(
    results: dict,
    output_dir: Path,
    config: dict = None
):
    """
    추출된 결과를 CSV로 저장 + 메타데이터 기록

    Parameters
    ----------
    results : dict
        extract_all()의 반환값
    output_dir : Path
        저장 경로 (예: outputs/scenario_1/results/)
    config : dict, optional
        config 정보를 results_meta.yaml로 함께 저장
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for var_name, df in results.items():
        filepath = output_dir / f"{var_name}.csv"
        df.to_csv(filepath, index=False)
        logger.info(f"Saved: {filepath}")

    # 메타데이터 저장
    if config:
        import yaml
        meta = {
            "scenario_name": config.get("_scenario_name", "unknown"),
            "variables_saved": list(results.keys()),
            "row_counts": {k: len(v) for k, v in results.items()},
        }
        meta_path = output_dir / "results_meta.yaml"
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.dump(meta, f, allow_unicode=True)
```

### Dual Variable 추출 (LP 모델인 경우)

```python
# solver.py에서 dual 활성화
model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
results = solver.solve(model, tee=True)

# 추출
from src.utils.extractor import extract_duals

lmp = extract_duals(model.PowerBalance)
# → 각 노드, 시간별 LMP (Locational Marginal Price)
```

---

## 6. 자주 하는 실수와 해결법

### 실수 1: Constraint rule에서 data 직접 참조

```python
# ❌ 나쁜 예: rule 안에서 외부 DataFrame 직접 접근
def bad_rule(m, n, t):
    return m.p[n, t] <= demand_df.loc[n, t]  # ← DataFrame을 직접 참조

# ✅ 좋은 예: 반드시 Param으로 변환 후 사용
model.Demand = pyo.Param(model.N, model.T, initialize=demand_dict)

def good_rule(m, n, t):
    return m.p[n, t] <= m.Demand[n, t]  # ← Param으로 접근
```

> **이유**: Pyomo는 수식을 symbolic하게 처리합니다. 외부 객체를 직접 참조하면
> 모델 재구성, LP 파일 export 등에서 문제가 생깁니다.

### 실수 2: Set 초기화 시 index 불일치

```python
# ❌ data에는 'bus_001'인데, Set에는 정수 0,1,2를 넣는 경우
model.N = pyo.Set(initialize=range(3))
# → Param, Constraint에서 key mismatch 에러

# ✅ data에서 직접 가져오기
model.N = pyo.Set(initialize=data["network"]["bus_id"].unique())
```

### 실수 3: pyo.value() 빠뜨리기

```python
# ❌ Variable 객체를 그대로 연산에 사용
total = sum(model.p[g, t] for g in model.G for t in model.T)
print(f"Total: {total}")  # → Pyomo expression 객체가 출력됨

# ✅ 풀이 후에는 반드시 pyo.value()로 값을 추출
total = sum(pyo.value(model.p[g, t]) for g in model.G for t in model.T)
print(f"Total: {total}")  # → 숫자가 출력됨
```

### 실수 4: Big-M을 너무 크게 잡기

```python
# ❌ "크면 되겠지" 하고 M=1e10으로 설정
M = 1e10  # → 수치 불안정, solver가 느려지거나 잘못된 해를 줌

# ✅ 물리적 의미에서 상한을 계산
# 예: 선로 용량 최대값의 2배 정도
M = 2 * max(line_capacity.values())
```

### 실수 5: 시나리오 바꿀 때 코드를 직접 수정

```python
# ❌ 코드 안에 하드코딩
carbon_price = 50  # 시나리오마다 이 줄을 수정...
renewable_target = 0.8

# ✅ config에서 읽기
carbon_price = config["parameters"]["carbon_price_usd_per_ton"]
renewable_target = config["parameters"]["renewable_target"]
```

---

## 부록: 전체 실행 흐름 요약

```
run_scenario.py --scenario scenario_1
│
├── 1. load_config("scenario_1")
│       → scenarios/scenario_1.yaml 로드
│       → base.yaml 상속 처리
│
├── 2. prepare_output_dir("scenario_1")
│       → outputs/scenario_1/ 생성
│       → config.yaml 복사
│
├── 3. setup_logger()
│       → outputs/scenario_1/run.log 생성
│
├── 4. load_data(config)
│       → data/*.csv → dict of DataFrames
│
├── 5. build_model(config, data)
│       → Sets, Params, Vars 정의
│       → Constraints 추가 (constraints/*.py)
│       → config에 따라 선택적 제약 활성화
│       → Objective 정의
│       → return ConcreteModel
│
├── 6. solve_model(model, config)
│       → Solver 설정 및 실행
│       → 결과 상태 확인 (optimal/infeasible)
│       → infeasible이면 진단 로그 출력
│
├── 7. extract_all(model)
│       → 모든 Variable → DataFrame
│       → save_results() → CSV 저장
│
├── 8. generate_figures()
│       → src/fig_makers/ 의 함수 호출
│       → outputs/scenario_1/figs/ 에 저장
│
└── 9. (선택) compare_scenarios.py
        → 여러 시나리오 결과 비교
        → outputs/scenario_comparison/ 에 저장
```
