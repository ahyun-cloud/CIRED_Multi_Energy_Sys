"""make_flow_figs.py - 시간별 운전 그림 + 연간 에너지 흐름 Sankey 생성 (재풀이 없음).

전제: 대상 시나리오를 `output.save_variable_csvs: true` 로 한 번 실행해
      `outputs/<scenario>/results/*.csv` (시간별 변수)가 있어야 한다.
      CSV 가 없으면 무엇을 실행해야 하는지 안내하고 종료한다.

실행:
    py figures/make_flow_figs.py --scenario cired_rep24
결과:
    outputs/<scenario>/figs/hourly_dispatch.png
    outputs/<scenario>/figs/energy_flow_sankey.png
    outputs/<scenario>/results/annual_energy_flow.csv
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
import sys
from pathlib import Path

import numpy as np

from src.data_process.loader import load_profiles
from src.data_process.scenario_gen import build_scenarios, collapse_to_expected
from src.fig_makers.plot_flows import (annual_flows, heat_load_profile,
                                       load_hourly, plot_dispatch, plot_sankey)
from src.utils.config_loader import get, load_config

# Windows 콘솔 기본 코드페이지(cp949)는 em dash·σ 를 못 찍어 UnicodeEncodeError 로
# 죽는다. 출력 스트림을 UTF-8 로 돌려 PYTHONUTF8 환경변수 없이도 돌게 한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

#: 시간별 그림에 쓸 대표 시나리오 선정 기준 (라벨, 점수 함수)
PICKS = [("peak heat", lambda hl, pv: hl.sum(axis=1)),
         ("peak PV", lambda hl, pv: pv.sum(axis=1)),
         ("min PV", lambda hl, pv: -pv.sum(axis=1))]


def main():
    ap = argparse.ArgumentParser(description="시간별 운전·에너지 흐름 그림 생성")
    ap.add_argument("--scenario", default="cired_rep24", help="대상 시나리오 이름")
    ap.add_argument("--days", type=int, default=3,
                    help="시간별 그림에 넣을 대표일 수 (기본 3)")
    args = ap.parse_args()

    config = load_config(args.scenario)
    out = Path("outputs") / args.scenario
    res_dir = out / "results"

    profiles = load_profiles(config, data_dir="data")
    scenario = build_scenarios(config, profiles)
    if get(config, "planning.mode", "stochastic") == "deterministic":
        scenario = collapse_to_expected(scenario)
    probs = np.asarray(scenario["probs"], dtype=float)
    names = list(scenario["names"])
    n_scen = len(probs)

    if not (res_dir / "p_import.csv").exists():
        raise SystemExit(
            f"시간별 변수 CSV 가 없다: {res_dir}\n"
            f"  base.yaml 의 'output.save_variable_csvs' 를 true 로 두고\n"
            f"  py run_scenario.py --scenario {args.scenario}\n"
            f"  를 한 번 실행해야 한다 (본 스크립트는 재풀이하지 않는다).")

    h = load_hourly(res_dir, n_scen)
    hl = heat_load_profile(scenario, config)

    # ── 연간 에너지 흐름 ────────────────────────────────────
    f = annual_flows(h, probs, config, hl)
    with open(res_dir / "annual_energy_flow.csv", "w", encoding="utf-8-sig",
              newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["flow", "GWh_per_year"])
        for k, v in f.items():
            w.writerow([k, round(v, 4)])
    print(f"\n연간 에너지 흐름 [GWh/yr] — {args.scenario}")
    print("-" * 46)
    for k, v in f.items():
        print(f"  {k:16s} {v:10.3f}")

    # 검산: 전력 버스 유입 = 유출
    bus_in = f["import"] + f["pv"] + f["chp_elec"] + f["ess_discharge"]
    bus_out = f["elec_load"] + f["export"] + f["ess_charge"]
    print("-" * 46)
    print(f"  전력버스 검산   유입 {bus_in:.3f} / 유출 {bus_out:.3f} "
          f"(차 {bus_in - bus_out:+.2e})")

    p_sankey = plot_sankey(
        f, out / "figs" / "energy_flow_sankey.png",
        title="Annual energy flow [GWh/yr]")
    print(f"저장 → {p_sankey}")

    # ── 시간별 운전 ─────────────────────────────────────────
    pv_tot = np.asarray(scenario["pv"], dtype=float)
    picks, notes, seen = [], [], set()
    for label, fn in PICKS[:args.days]:
        idx = int(np.argmax(fn(hl, pv_tot)))
        if idx not in seen:
            picks.append(idx)
            notes.append(label)                      # 그림에 선정 기준을 밝힌다
            seen.add(idx)
    p_disp = plot_dispatch(
        h, hl, picks, names, out / "figs" / "hourly_dispatch.png",
        title="Hourly dispatch of representative days", row_notes=notes)
    print(f"저장 → {p_disp}   (대표일: {', '.join(names[i] for i in picks)})")


if __name__ == "__main__":
    main()
