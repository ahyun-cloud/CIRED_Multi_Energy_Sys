"""make_network_fig.py - 전기·열 2층 배치도(논문 Fig. 3 / 포스터 Fig. 1)만 재생성.

run_scenario.py 가 그리는 network_layered.png 를 재풀이 없이 summary.json 으로 다시 그린다.
실행: py figures/make_network_fig.py [--scenario cired_rep24]
결과: outputs/<scenario>/figs/network_layered.png
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

from src.fig_makers.plot_network_layered import plot_network_layered


def main():
    ap = argparse.ArgumentParser(description="전기·열 2층 배치도 재생성")
    ap.add_argument("--scenario", default="cired_rep24")
    ap.add_argument("--dpi", type=int, default=160, help="포스터용은 400 권장")
    ap.add_argument("--out", default=None, help="저장 경로 (기본: outputs/<scenario>/figs/network_layered.png)")
    args = ap.parse_args()
    p = Path("outputs") / args.scenario / "results" / "summary.json"
    with open(p, encoding="utf-8") as f:
        results = json.load(f)
    out = Path(args.out) if args.out else Path("outputs") / args.scenario / "figs" / "network_layered.png"
    print(f"저장 → {plot_network_layered(results, out, dpi=args.dpi)}")


if __name__ == "__main__":
    main()
