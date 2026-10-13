"""
compare_scenarios.py - 시나리오 간 비교 및 민감도 분석

CIRED 핵심 분석:
    1. 결정론적 vs 확률론적(CVaR) 비교 (ESS 집중→분산 배치)
    2. 리스크 가중치 λ 민감도 (ESS 증가율 vs CHP 증가율)
    3. 신뢰수준 α 민감도 (ESS 용량 단조성)
    4. PV 출력제한 허용/불허에 따른 ESS 투자비 변화

데이터(profiles)·LPF 는 1회만 계산하여 모든 변형에서 재사용한다.
결과/그림은 outputs/scenario_comparison/ 에 저장.

Usage:
    python analysis/compare_scenarios.py --base cired_stochastic
    python analysis/compare_scenarios.py --base cired_stochastic --analyses det_sto alpha lambda curtail
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
from copy import deepcopy
from pathlib import Path

from src.utils.config_loader import load_config, _deep_merge, get
from src.utils.logger import setup_logger
from src.data_process.loader import load_profiles
from src.data_process.scenario_gen import build_scenarios, collapse_to_expected
from src.powerflow.linear_pf import LinearPowerFlow
from src.planning.model import build_model
from src.planning.solver import solve_model, load_siting, fix_siting
from src.planning.extractor import extract_results
from src.fig_makers.plot_comparison import plot_det_vs_stoch, plot_sensitivity

OUT = Path("outputs") / "scenario_comparison"


def _solve_variant(base_config, overrides, profiles, lpf, logger, siting=None,
                   free_ess=True):
    """base_config 에 overrides 를 병합해 1개 변형을 풀고 결과 반환.

    siting 이 주어지면 1단계 배치를 고정(용량·운영 자유)해 tractable 하게 푼다.
    단 free_ess=True(기본)면 **ESS 노드는 고정하지 않는다** — λ·α 민감도는 ESS 거동
    자체가 분석 대상이므로, 기준 해의 ESS 가 0 일 때 siting 을 고정하면 ESS 가 0 으로
    강제되어 분석이 무의미해진다. PV·CHP·TES 만 고정해 조합 탐색을 줄인다.
    """
    config = _deep_merge(base_config, overrides)
    scenario = build_scenarios(config, profiles)
    if get(config, "planning.mode", "stochastic") == "deterministic":
        scenario = collapse_to_expected(scenario)
    data = {"scenario": scenario, "lpf": lpf}
    model = build_model(config, data)
    if siting is not None:
        fix_siting(model, siting, free_ess=free_ess)
    solve_model(model, config)
    return extract_results(model, config, data)


def _row(label, r):
    """비교표 행: 용량 + 비용 분해(투자/기대운영/CVaR/총)."""
    return [label, r["total_P_MW"], r["total_E_MWh"], r["total_CHP_MW"],
            r["invest_cost"] / 1e8, r["expected_op_cost"] / 1e8,
            r["cvar_op_cost"] / 1e8, r["objective"] / 1e8,
            r["curtailment_pct"], r["n_ess_sites"]]


def run_comparison(base_name, analyses, fix_siting_from=None):
    OUT.mkdir(parents=True, exist_ok=True)
    logger = setup_logger("cired", OUT / "compare.log")
    base_config = load_config(base_name)

    logger.info(f"비교 기준 시나리오: {base_name}  분석: {analyses}  siting고정: {fix_siting_from}")
    profiles = load_profiles(base_config, data_dir="data", logger=logger)
    lpf = LinearPowerFlow()

    # tractability: 확률론 민감도 변형은 PV·CHP·TES siting 고정(빠른 수렴). det_sto는 free.
    #   ESS 는 고정하지 않는다(_solve_variant free_ess=True) — ESS 거동이 분석 대상.
    siting = load_siting(fix_siting_from) if fix_siting_from else None
    if siting is not None:
        logger.info(f"siting 고정: PV {sorted(siting['pv'])} · CHP {sorted(siting['chp'])} · "
                    f"TES {sorted(siting['tes'])} (ESS 는 자유배치)")

    rows = []   # 비교표 누적

    # ── 1. 결정론적 vs 확률론적 ──────────────────────────
    if "det_sto" in analyses:
        logger.info("[1] 결정론적 vs 확률론적")
        r_det = _solve_variant(base_config, {"planning": {"mode": "deterministic"}},
                               profiles, lpf, logger)
        r_sto = _solve_variant(base_config, {"planning": {"mode": "stochastic"}},
                               profiles, lpf, logger)
        plot_det_vs_stoch(r_det, r_sto, OUT / "det_vs_stoch.png")
        rows.append(_row("결정론적", r_det))
        rows.append(_row("확률론적", r_sto))

    # ── 2. λ 민감도 ──────────────────────────────────────
    if "lambda" in analyses:
        logger.info("[2] 리스크 가중치 λ 민감도")
        lam_rows = []
        for lam in [0.0, 0.5, 1.0, 2.0]:
            r = _solve_variant(base_config,
                               {"planning": {"mode": "stochastic", "lambda_risk": lam}},
                               profiles, lpf, logger, siting=siting)
            r["lambda"] = lam
            lam_rows.append(r)
            rows.append(_row(f"λ={lam}", r))
        plot_sensitivity(lam_rows, "lambda", OUT / "sensitivity_lambda.png")

    # ── 3. α 민감도 ──────────────────────────────────────
    if "alpha" in analyses:
        logger.info("[3] 신뢰수준 α 민감도")
        a_rows = []
        for alpha in [0.80, 0.90, 0.95, 0.99]:
            r = _solve_variant(base_config,
                               {"planning": {"mode": "stochastic", "alpha": alpha}},
                               profiles, lpf, logger, siting=siting)
            r["alpha"] = alpha
            a_rows.append(r)
            rows.append(_row(f"α={alpha}", r))
        plot_sensitivity(a_rows, "alpha", OUT / "sensitivity_alpha.png")

    # ── 4. PV 출력제한 허용/불허 ─────────────────────────
    if "curtail" in analyses:
        logger.info("[4] PV 출력제한 허용 vs 불허")
        for label, no_curt in [("출력제한 허용", False), ("출력제한 불허", True)]:
            r = _solve_variant(base_config, {"pv": {"no_curtailment": no_curt}},
                               profiles, lpf, logger, siting=siting)
            rows.append(_row(label, r))

    # ── 비교표 저장 ──────────────────────────────────────
    csv_path = OUT / "comparison.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["케이스", "ESS_P_MW", "ESS_E_MWh", "CHP_P_MW",
                    "투자_억", "기대운영_억", "CVaR_억", "총비용_억",
                    "curtailment_%", "ESS_노드수"])
        for row in rows:
            w.writerow([row[0]] + [round(v, 4) if isinstance(v, float) else v
                                   for v in row[1:]])
    logger.info(f"비교표 저장 → {csv_path}")
    logger.info("완료 → outputs/scenario_comparison/")


def main():
    parser = argparse.ArgumentParser(description="시나리오 비교/민감도 분석")
    parser.add_argument("--base", default="cired_stochastic",
                        help="비교 기준 시나리오 yaml 이름")
    parser.add_argument("--analyses", nargs="+",
                        default=["det_sto", "lambda", "alpha", "curtail"],
                        choices=["det_sto", "lambda", "alpha", "curtail"])
    parser.add_argument("--fix_siting", default=None,
                        help="확률론 민감도 변형의 siting을 고정할 기준 시나리오 "
                             "(예: cired_rep24). tractability용. det_sto는 항상 free.")
    args = parser.parse_args()
    run_comparison(args.base, args.analyses, fix_siting_from=args.fix_siting)


if __name__ == "__main__":
    main()
