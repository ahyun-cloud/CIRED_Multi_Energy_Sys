"""
config_loader.py - 시나리오 YAML 로딩 + 상속(inherit) + 재현성 복사

규칙 (PROJECT_GUIDE):
  - 시나리오 정의는 scenarios/*.yaml 로 관리
  - 'inherit: base' 키가 있으면 base.yaml 을 먼저 로드 후 덮어쓰기
  - 실행 시 사용된 config 는 outputs/<scenario>/config.yaml 로 복사 (재현성)
"""

import shutil
from copy import deepcopy
from pathlib import Path

import yaml


def load_config(scenario_name: str, scenarios_dir="scenarios") -> dict:
    """
    YAML config 로드. 'inherit' 키가 있으면 부모 config 를 재귀적으로 병합.

    Parameters
    ----------
    scenario_name : str
        확장자 없는 시나리오 이름 (예: 'cired_stochastic')
    scenarios_dir : str
        시나리오 폴더 경로

    Returns
    -------
    dict
        '_scenario_name', '_config_path' 메타키가 추가된 설정 딕셔너리
    """
    config_path = Path(scenarios_dir) / f"{scenario_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if "inherit" in config:
        base_name = config.pop("inherit")
        base_config = load_config(base_name, scenarios_dir)
        # 부모의 메타키는 자식 기준으로 다시 채워지므로 제거
        base_config.pop("_scenario_name", None)
        base_config.pop("_config_path", None)
        config = _deep_merge(base_config, config)

    config["_scenario_name"] = scenario_name
    config["_config_path"] = str(config_path)
    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """dict 를 재귀적으로 병합. override 가 우선."""
    result = deepcopy(base)
    for key, value in override.items():
        if (key in result and isinstance(result[key], dict)
                and isinstance(value, dict)):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def prepare_output_dir(scenario_name: str, outputs_dir="outputs",
                       scenarios_dir="scenarios") -> Path:
    """
    outputs/<scenario>/ 디렉토리(+ results/, figs/)를 생성하고
    사용된 config 원본을 복사하여 재현성을 보장.
    """
    output_dir = Path(outputs_dir) / scenario_name
    for sub in ["results", "figs"]:
        (output_dir / sub).mkdir(parents=True, exist_ok=True)

    src_config = Path(scenarios_dir) / f"{scenario_name}.yaml"
    if src_config.exists():
        shutil.copy2(src_config, output_dir / "config.yaml")

    return output_dir


def get(config: dict, path: str, default=None):
    """
    점(.)으로 구분된 경로로 중첩 config 값을 안전하게 조회.

    예: get(config, "ess.cost.c_power", 1.5e8)
    """
    node = config
    for key in path.split("."):
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return default
    return node
