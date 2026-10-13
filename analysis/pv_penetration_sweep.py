"""pv_penetration_sweep.py - PV 침투율 x ESS 유무에 따른 curtailment 분석.

C3(고침투 잉여흡수) hero figure: 침투율이 오를수록 잉여 PV curtailment가 증가하나,
ESS가 이를 흡수해 ~0%로 낮춤. ESS 유/무 counterfactual로 ESS의 잉여흡수 가치를 정량화.
역송전 한계(grid.export_limit_mw)가 있어야 curtailment가 발생함.

실행: python analysis/pv_penetration_sweep.py
결과: outputs/penetration_sweep/ (penetration.csv, penetration_sweep.png)
"""

# 프로젝트 루트를 import 경로·작업 디렉토리로 고정 — 어디서 실행해도
# `from src...` 와 outputs/·data/·scenarios/ 상대경로가 동작하도록.
import os
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import csv
from pathlib import Path

import pyomo.environ as pyo
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt

from src.utils.config_loader import load_config, _deep_merge
from src.utils.logger import setup_logger
from src.data_process.loader import load_profiles
from src.data_process.scenario_gen import build_scenarios
from src.powerflow.linear_pf import LinearPowerFlow
from src.planning.model import build_model
from src.planning.solver import solve_model
from src.planning.extractor import extract_results

OUT = Path("outputs") / "penetration_sweep"
BASE = "quick_season4"
PENETRATIONS = [3.3, 4.4, 5.6, 6.6, 7.7]


EXPORT_LIMIT_MW = 1.0   # 고침투 curtailment 연구용 역송전 한계 (base는 무제한)


def _copy_solution(src, dst):
    """src 모델 해를 dst 동일 변수에 복사 (full-solution MIP warm-start)."""
    for sv in src.component_objects(pyo.Var, active=True):
        dv = getattr(dst, sv.name, None)
        if dv is None:
            continue
        for idx in sv:
            v = pyo.value(sv[idx], exception=False)
            if v is not None and idx in dv and not dv[idx].fixed:
                dv[idx].value = v


def _solve(base_config, target, profiles, lpf, no_ess, warm_src=None):
    # tight gap + 시간↑ → free-siting degeneracy(build-all) 회피, 수렴 확보
    config = _deep_merge(base_config, {"pv": {"target_mwp": target},
                                       "grid": {"export_limit_mw": EXPORT_LIMIT_MW},
                                       "solver": {"time_limit": 1800, "mip_gap": 0.005}})
    sc = build_scenarios(config, profiles)
    data = {"scenario": sc, "lpf": lpf}
    m = build_model(config, data)
    if no_ess:                       # counterfactual: ESS 설치 금지
        for n in m.N_ess:
            m.inv_ess[n].fix(0)
            m.cap_ess_p[n].fix(0)
            m.cap_ess_e[n].fix(0)
    if warm_src is not None:         # no-ESS 해를 초기 incumbent로 → build-all 회피
        _copy_solution(warm_src, m)
    solve_model(m, config, warmstart=(warm_src is not None))
    return extract_results(m, config, data), m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    logger = setup_logger("cired", OUT / "sweep.log")
    base_config = load_config(BASE)
    profiles = load_profiles(base_config, data_dir="data", logger=logger)
    lpf = LinearPowerFlow()

    rows = []
    for tg in PENETRATIONS:
        # no-ESS 먼저 → 그 해를 ESS 케이스 warm-start로 (build-all 회피)
        r_no, m_no = _solve(base_config, tg, profiles, lpf, no_ess=True)
        r_ess, _ = _solve(base_config, tg, profiles, lpf, no_ess=False, warm_src=m_no)
        rows.append({"pen_MWp": tg,
                     "curt_ESS_%": round(r_ess["curtailment_pct"], 2),
                     "curt_noESS_%": round(r_no["curtailment_pct"], 2),
                     "ESS_MW": round(r_ess["total_P_MW"], 3),
                     "cost_ESS_억": round(r_ess["objective"] / 1e8, 1),
                     "cost_noESS_억": round(r_no["objective"] / 1e8, 1)})
        logger.info(f"PV={tg}MWp: curt(ESS)={r_ess['curtailment_pct']:.1f}% "
                    f"curt(noESS)={r_no['curtailment_pct']:.1f}% "
                    f"ESS={r_ess['total_P_MW']:.2f}MW")

    with open(OUT / "penetration.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    pen = [r["pen_MWp"] for r in rows]
    cn = [r["curt_noESS_%"] for r in rows]
    ce = [r["curt_ESS_%"] for r in rows]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    ax[0].plot(pen, cn, "o-", color="tomato", lw=2.2, ms=7, label="Without ESS")
    ax[0].plot(pen, ce, "s-", color="steelblue", lw=2.2, ms=7, label="With ESS (optimal)")
    ax[0].fill_between(pen, ce, cn, color="steelblue", alpha=0.15, label="ESS-absorbed")
    ax[0].set_xlabel("PV penetration [MWp]")
    ax[0].set_ylabel("Curtailment [%]")
    ax[0].set_title("PV curtailment vs penetration", fontweight="bold")
    ax[0].legend(); ax[0].grid(alpha=0.3)
    ax[1].plot(pen, [r["ESS_MW"] for r in rows], "D-", color="seagreen", lw=2.2, ms=7)
    ax[1].set_xlabel("PV penetration [MWp]")
    ax[1].set_ylabel("Optimal ESS power [MW]")
    ax[1].set_title("Optimal ESS capacity vs penetration", fontweight="bold")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "penetration_sweep.png", dpi=150, bbox_inches="tight")
    logger.info(f"완료 -> {OUT}/")


if __name__ == "__main__":
    main()
