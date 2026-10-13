"""make_sensitivity_figs.py - λ·α 민감도 그림(논문 Fig. 6·7)만 재생성.

compare_scenarios.py 의 'lambda'/'alpha' 분석은 케이스마다 **다시 풀어서** 그림을 그린다.
그런데 8개 케이스 결과는 이미 outputs/scenario_comparison/comparison.csv 에 있으므로,
재풀이 없이 그 표만 읽어 같은 그림을 만든다 (CPLEX 불필요, 수초).

실행: py figures/make_sensitivity_figs.py
결과: outputs/scenario_comparison/sensitivity_lambda.png, sensitivity_alpha.png
"""

# 프로젝트 루트를 import 경로·작업 디렉토리로 고정 — 어디서 실행해도
# `from src...` 와 outputs/·data/·scenarios/ 상대경로가 동작하도록.
import os
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import argparse
import csv
import json
from pathlib import Path

from src.fig_makers.plot_comparison import plot_sensitivity
from src.fig_makers.plot_poster import plot_poster_sensitivity

OUT = Path("outputs") / "scenario_comparison"
CSV = OUT / "comparison.csv"

#: comparison.csv 의 열 이름 → plot_sensitivity 가 기대하는 키 (단위: 억원 → 원)
COLS = {"ESS_P_MW": ("total_P_MW", 1.0),
        "CHP_P_MW": ("total_CHP_MW", 1.0),
        "투자_억": ("invest_cost", 1e8),
        "기대운영_억": ("expected_op_cost", 1e8),
        "CVaR_억": ("cvar_op_cost", 1e8)}


def load_rows(prefix: str, x_key: str) -> list:
    """'λ=' / 'α=' 로 시작하는 행만 뽑아 x 오름차순으로 돌려준다."""
    if not CSV.exists():
        raise FileNotFoundError(
            f"{CSV} 없음 → 먼저 'py analysis/compare_scenarios.py --base cired_rep24 "
            f"--analyses lambda alpha --fix_siting cired_rep24' 실행")
    rows = []
    with open(CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            case = r["케이스"]
            if not case.startswith(prefix):
                continue
            row = {x_key: float(case.split("=")[1])}
            for col, (key, scale) in COLS.items():
                row[key] = float(r[col]) * scale
            rows.append(row)
    if not rows:
        raise ValueError(f"comparison.csv 에 '{prefix}...' 행이 없다")
    rows.sort(key=lambda r: r[x_key])
    return rows


#: (b) 패널용 — 시나리오 집합이 커질수록 설비가 어떻게 변하는지
_NL = chr(10)
SCENARIOS = [("cired_deterministic", "Deterministic" + _NL + "(S = 1)"),
             ("cired_rep24", "Representative" + _NL + "(S = 24)"),
             ("cired_stochastic", "Monte Carlo" + _NL + "(S = 100)")]


def load_scenarios() -> list:
    """outputs/<시나리오>/results/summary.json 에서 CHP·TES 용량을 읽는다."""
    out = []
    for name, label in SCENARIOS:
        path = Path("outputs") / name / "results" / "summary.json"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} 없음 → 'py run_scenario.py --scenario {name}' 필요. "
                f"(outputs/ 는 gitignore 라 새 클론엔 없을 수 있다)")
        d = json.loads(path.read_text(encoding="utf-8"))
        out.append({"label": label,
                    "short": label.split("(")[-1].rstrip(")").strip(),
                    "total_CHP_MW": float(d.get("total_CHP_MW", 0.0)),
                    "total_TES_MWh": float(d.get("total_TES_MWh", 0.0)),
                    "total_P_MW": float(d.get("total_P_MW", 0.0))})
    return out


def main():
    ap = argparse.ArgumentParser(description="λ·α 민감도 그림 재생성 (재풀이 없음)")
    ap.add_argument("--poster", action="store_true",
                    help="포스터용 통합 2x2 (8패널 → 핵심 4패널) 도 함께 생성")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.poster:
        lam, alp = load_rows("λ", "lambda"), load_rows("α", "alpha")
        scen = load_scenarios()
        path = plot_poster_sensitivity(lam, alp, scen, OUT / "poster_sensitivity.png")
        print(f"저장 → {path} (+ .pdf)   포스터용 2x2")
        print(f"    λ: CHP {lam[0]['total_CHP_MW']:.3f} → {lam[-1]['total_CHP_MW']:.3f} MW · "
              f"투자 {lam[0]['invest_cost']/1e8:.2f} → {lam[-1]['invest_cost']/1e8:.2f}억 · "
              f"CVaR {lam[0]['cvar_op_cost']/1e8:.2f} → {lam[-1]['cvar_op_cost']/1e8:.2f}억")
        print(f"    α: CHP {alp[0]['total_CHP_MW']:.3f} → {alp[-1]['total_CHP_MW']:.3f} MW · "
              f"투자 {alp[0]['invest_cost']/1e8:.2f} → {alp[-1]['invest_cost']/1e8:.2f}억 · "
              f"CVaR {alp[0]['cvar_op_cost']/1e8:.2f} → {alp[-1]['cvar_op_cost']/1e8:.2f}억")
        print(f"    ESS: 전 케이스 "
              f"{max(max(r['total_P_MW'] for r in lam), max(r['total_P_MW'] for r in alp)):.3f} MW")
        for sc in scen:
            print(f"    {sc['label'].replace(chr(10), ' '):28s} "
                  f"CHP {sc['total_CHP_MW']:.3f} MW · TES {sc['total_TES_MWh']:6.2f} MWh_th · "
                  f"ESS {sc['total_P_MW']:.3f} MW")
    for prefix, x_key, name in (("λ", "lambda", "sensitivity_lambda.png"),
                                ("α", "alpha", "sensitivity_alpha.png")):
        rows = load_rows(prefix, x_key)
        path = plot_sensitivity(rows, x_key, OUT / name)
        span = f"{rows[0][x_key]} → {rows[-1][x_key]}"
        print(f"저장 → {path}   ({x_key} {span}, {len(rows)}개 케이스)")
        print(f"    투자 {rows[0]['invest_cost']/1e8:.2f} → {rows[-1]['invest_cost']/1e8:.2f}억 · "
              f"기대운영 {rows[0]['expected_op_cost']/1e8:.2f} → "
              f"{rows[-1]['expected_op_cost']/1e8:.2f}억 · "
              f"CVaR {rows[0]['cvar_op_cost']/1e8:.2f} → {rows[-1]['cvar_op_cost']/1e8:.2f}억")


if __name__ == "__main__":
    main()
