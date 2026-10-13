# PROJECT_GUIDE.md
# 연구실 프로젝트 코드 구조화 가이드

> 새 프로젝트를 시작할 때 이 파일을 프로젝트 루트에 복사하고, 아래 구조를 따라주세요.

---

## 1. 기본 원칙

| 원칙 | 설명 |
|------|------|
| **파일 길이** | 단일 `.py` 파일은 **200~500줄** 이내로 유지 |
| **파일 단위** | 하나의 파일 = 하나의 기능 (최적화 문제 하나, 데이터 처리 단계 하나 등) |
| **시나리오 관리** | 시나리오 정의는 **YAML config** 파일로 관리 |
| **재현성** | 실행 시 사용된 config가 output 폴더에 자동 복사되어야 함 |
| **로깅** | Python `logging` 모듈 사용, output 폴더에 `.log` 파일 자동 생성 |

---

## 2. 디렉토리 구조

```
project/
│
├── run_scenario.py          # 단일 진입점 (시나리오 실행 스크립트)
├── compare_scenarios.py     # 시나리오 간 비교 스크립트 (추후 추가)
├── PROJECT_GUIDE.md         # 이 파일
├── requirements.txt         # 패키지 의존성
│
├── src/                     # 핵심 소스코드 (컴포넌트별 분리)
│   ├── __init__.py
│   ├── interaction/         # TSO-DSO 상호작용 (coordination 알고리즘 등)
│   │   ├── __init__.py
│   │   └── coordinator.py
│   ├── tso/                 # TSO 최적화 문제
│   │   ├── __init__.py
│   │   └── tso_model.py
│   ├── dso/                 # DSO 관련
│   │   ├── __init__.py
│   │   ├── planning/        # DSO 계획 문제
│   │   │   ├── __init__.py
│   │   │   └── expansion_model.py
│   │   └── operation/       # DSO 운영 문제
│   │       ├── __init__.py
│   │       └── dispatch_model.py
│   ├── data_process/        # 데이터 전처리, 로딩
│   │   ├── __init__.py
│   │   └── loader.py
│   ├── fig_makers/          # Figure 생성 함수 모음
│   │   ├── __init__.py
│   │   ├── plot_dispatch.py     # 급전 결과 시각화
│   │   ├── plot_investment.py   # 투자 결과 시각화
│   │   └── plot_comparison.py   # 시나리오 간 비교 시각화
│   └── utils/               # 공용 유틸리티 함수
│       ├── __init__.py
│       ├── logger.py        # 로깅 설정
│       └── io_helpers.py    # 파일 입출력 헬퍼
│
├── scenarios/               # 시나리오 config 파일들 (YAML)
│   ├── scenario_1.yaml
│   ├── scenario_2.yaml
│   └── base.yaml            # 공통 기본값 (선택사항)
│
├── data/                    # 원본 입력 데이터 (수정하지 않음)
│   ├── demand.csv
│   ├── network.csv
│   └── generation.csv
│
└── outputs/                 # 시나리오별 실행 결과
    ├── scenario_1/          # 자동 생성됨
    │   ├── config.yaml      # 실행 시 사용된 config 복사본
    │   ├── run.log          # 실행 로그
    │   ├── results/         # 최적화 결과 (csv, pkl 등)
    │   │   ├── dispatch.csv
    │   │   └── investment.csv
    │   └── figs/            # 시나리오별 figure
    │       └── cost_breakdown.png
    │
    └── scenario_comparison/ # 시나리오 간 비교 결과 및 figure
        ├── comparison.csv
        └── comparison_chart.png
```

### 폴더 역할 요약

- **`src/`** : 모든 핵심 로직. `run_scenario.py`에서 import하여 사용
- **`src/fig_makers/`** : Figure 생성 함수 모음. 시나리오별/비교용 그래프 함수를 여기서 관리
- **`scenarios/`** : 시나리오 정의 YAML 파일. 파라미터 변경은 여기서만
- **`data/`** : 원본 데이터. 코드로 수정하지 않음 (read-only 취급)
- **`outputs/`** : 실행 결과. 시나리오별로 자동 생성. config 복사본 포함
- **`outputs/scenario_comparison/`** : 시나리오 **간 비교** 결과 및 figure. `compare_scenarios.py` 실행 시 여기에 저장

---

## 3. 시나리오 Config 예시 (`scenarios/scenario_1.yaml`)

```yaml
# scenario_1.yaml
scenario_name: "High Renewable Penetration"
description: "재생에너지 비율 80% 목표 시나리오"

# 시뮬레이션 설정
time_horizon: 2030
discount_rate: 0.05
solver: "gurobi"
solver_options:
  MIPGap: 0.01
  TimeLimit: 3600

# 시나리오 고유 파라미터
parameters:
  renewable_target: 0.80
  carbon_price_usd_per_ton: 50
  demand_growth_rate: 0.02
  ev_penetration: 0.30
  battery_cost_usd_per_kwh: 150

# 입력 데이터 경로 (data/ 기준 상대경로)
data_files:
  demand: "demand.csv"
  network: "network.csv"
  generation: "generation.csv"
```

---

## 4. 단일 진입점 사용법 (`run_scenario.py`)

### 실행 방법

```bash
# 단일 시나리오 실행
python run_scenario.py --scenario scenario_1

# 여러 시나리오 순차 실행
python run_scenario.py --scenario scenario_1 scenario_2 scenario_3
```

### `run_scenario.py` 기본 템플릿

```python
"""
run_scenario.py - 시나리오 실행 단일 진입점

Usage:
    python run_scenario.py --scenario scenario_1
    python run_scenario.py --scenario scenario_1 scenario_2
"""

import argparse
import yaml
import shutil
import logging
from pathlib import Path
from datetime import datetime

from src.utils.logger import setup_logger


def load_config(scenario_name: str) -> dict:
    """scenarios/ 폴더에서 YAML config를 로드"""
    config_path = Path("scenarios") / f"{scenario_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["_scenario_name"] = scenario_name
    config["_config_path"] = str(config_path)
    return config


def prepare_output_dir(scenario_name: str) -> Path:
    """output 디렉토리 생성 및 config 복사"""
    output_dir = Path("outputs") / scenario_name
    for sub in ["results", "figs"]:
        (output_dir / sub).mkdir(parents=True, exist_ok=True)

    # config 복사 (재현성 보장)
    src_config = Path("scenarios") / f"{scenario_name}.yaml"
    shutil.copy2(src_config, output_dir / "config.yaml")

    return output_dir


def run_single_scenario(scenario_name: str):
    """단일 시나리오 실행 파이프라인"""
    # 1) Config 로드
    config = load_config(scenario_name)

    # 2) Output 디렉토리 준비 + config 복사
    output_dir = prepare_output_dir(scenario_name)

    # 3) Logger 설정
    logger = setup_logger(
        name=scenario_name,
        log_file=output_dir / "run.log"
    )
    logger.info(f"=== Scenario: {scenario_name} ===")
    logger.info(f"Start time: {datetime.now().isoformat()}")
    logger.info(f"Config: {config}")

    # 4) 데이터 로드
    # from src.data_process.loader import load_data
    # data = load_data(config)
    # logger.info("Data loaded successfully")

    # 5) 모델 구성 및 풀이
    # from src.tso.tso_model import build_tso_model
    # from src.dso.planning.expansion_model import build_expansion_model
    # model = build_tso_model(config, data)
    # results = model.solve()

    # 6) 결과 저장
    # results.to_csv(output_dir / "results" / "dispatch.csv")
    # logger.info(f"Results saved to {output_dir / 'results'}")

    # 7) Figure 생성
    # from src.utils.io_helpers import save_figures
    # save_figures(results, output_dir / "figs")

    logger.info(f"=== Scenario {scenario_name} completed ===")


def main():
    parser = argparse.ArgumentParser(description="Run optimization scenario")
    parser.add_argument(
        "--scenario", nargs="+", required=True,
        help="Scenario name(s), e.g., scenario_1 scenario_2"
    )
    args = parser.parse_args()

    for scenario_name in args.scenario:
        print(f"\n{'='*60}")
        print(f"  Running: {scenario_name}")
        print(f"{'='*60}")
        run_single_scenario(scenario_name)


if __name__ == "__main__":
    main()
```

---

## 5. Logger 설정 템플릿 (`src/utils/logger.py`)

```python
"""
logger.py - 표준 로깅 설정

사용법:
    from src.utils.logger import setup_logger
    logger = setup_logger("my_module", log_file="outputs/scenario_1/run.log")
    logger.info("모델 풀이 시작")
"""

import logging
from pathlib import Path


def setup_logger(name: str, log_file: Path = None, level=logging.INFO):
    """파일 + 콘솔 동시 출력 로거 생성"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers = []  # 중복 핸들러 방지

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 콘솔 출력
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 출력
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
```

---

## 6. 코드 작성 규칙

### 파일 분리 기준

| 상황 | 조치 |
|------|------|
| 파일이 500줄을 넘어감 | 기능 단위로 분리 |
| 하나의 파일에 2개 이상의 최적화 문제 | 문제별로 분리 |
| 전처리 + 모델링 + 후처리가 한 파일에 | 각 단계별로 분리 |
| 여러 파일에서 같은 함수를 복사해서 쓰고 있음 | `utils/`로 이동 |

### import 규칙

```python
# run_scenario.py 또는 script에서 src를 import
from src.tso.tso_model import build_tso_model
from src.dso.planning.expansion_model import build_expansion_model
from src.data_process.loader import load_data
from src.utils.logger import setup_logger
```

### 네이밍 규칙

- 파일명: `snake_case.py` (예: `tso_model.py`, `expansion_model.py`)
- 클래스명: `PascalCase` (예: `TSOModel`, `DSOPlanner`)
- 함수명: `snake_case` (예: `build_model()`, `load_demand_data()`)
- 상수: `UPPER_SNAKE_CASE` (예: `DEFAULT_SOLVER = "gurobi"`)

---

## 7. 체크리스트 (프로젝트 시작 시)

- [ ] 이 `PROJECT_GUIDE.md`를 프로젝트 루트에 복사
- [ ] 위 디렉토리 구조대로 폴더 생성
- [ ] `requirements.txt` 작성 (pyomo, pandas, pyyaml, matplotlib 등)
- [ ] `src/utils/logger.py` 복사
- [ ] `run_scenario.py` 템플릿 복사 후 프로젝트에 맞게 수정
- [ ] 첫 번째 시나리오 config (`scenarios/scenario_1.yaml`) 작성
- [ ] `python run_scenario.py --scenario scenario_1` 실행 테스트
- [ ] `outputs/scenario_1/` 에 config.yaml, run.log 생성 확인
