"""make_det_vs_stoch_fig.py - 결정론 vs 확률론 비교 그림(논문 Fig. 5)만 재생성.

compare_scenarios.py 의 'det_sto' 분석은 두 케이스를 **다시 풀어서** 그림을 그린다.
그런데 두 해는 이미 run_scenario.py 로 풀려 outputs/<scenario>/results/summary.json 에
있으므로, 재풀이 없이 그 결과만 읽어 같은 그림을 만든다 (CPLEX 불필요, 수초).

실행: py figures/make_det_vs_stoch_fig.py [--sto cired_rep24]
결과: outputs/scenario_comparison/det_vs_stoch.png
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
import json
from pathlib import Path

from src.fig_makers.plot_comparison import plot_det_vs_stoch

OUT = Path("outputs") / "scenario_comparison"


def load_summary(scenario: str) -> dict:
    p = Path("outputs") / scenario / "results" / "summary.json"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} 없음 → 먼저 'py run_scenario.py --scenario {scenario}' 실행")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="det vs stoch 비교 그림 재생성")
    ap.add_argument("--det", default="cired_deterministic")
    ap.add_argument("--sto", default="cired_rep24")
    args = ap.parse_args()

    r_det = load_summary(args.det)
    r_sto = load_summary(args.sto)
    OUT.mkdir(parents=True, exist_ok=True)
    path = plot_det_vs_stoch(r_det, r_sto, OUT / "det_vs_stoch.png")

    def _line(tag, r):
        return (f"  {tag:<14} ESS {r['total_P_MW']:.3f} MW / {r['total_E_MWh']:.3f} MWh · "
                f"CHP {r['total_CHP_MW']:.3f} MW · TES {r['total_TES_MWh']:.2f} MWh · "
                f"투자 {r['invest_cost']/1e8:.1f}억 · 기대운영 {r['expected_op_cost']/1e8:.1f}억 · "
                f"CVaR {r['cvar_op_cost']/1e8:.1f}억")

    print(f"저장 → {path}")
    print(_line(args.det, r_det))
    print(_line(args.sto, r_sto))


if __name__ == "__main__":
    main()
