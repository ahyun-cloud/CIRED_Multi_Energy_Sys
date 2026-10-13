"""
run_scenario.py - 시나리오 실행 단일 진입점

Usage:
    python run_scenario.py --scenario cired_deterministic
    python run_scenario.py --scenario cired_deterministic cired_stochastic

실행 파이프라인:
    config 로드 → output 준비(config 복사) → 로깅 → 데이터 로드 →
    시나리오 생성 → LPF → 모델 build → solve → 결과 추출 →
    저장(json/excel/csv) → figure 생성
"""

import argparse
from datetime import datetime

from src.utils.config_loader import load_config, prepare_output_dir, get
from src.utils.logger import setup_logger
from src.data_process.network import network_summary
from src.data_process.loader import load_profiles
from src.data_process.scenario_gen import build_scenarios, collapse_to_expected
from src.powerflow.linear_pf import LinearPowerFlow
from src.planning.model import build_model
from src.planning.solver import (
    solve_model, load_siting, fix_siting, load_warmstart, apply_warmstart,
)
from src.planning.extractor import extract_results, extract_all, compute_voltage_profile
from src.utils.io_helpers import (
    save_results_json, export_summary_excel, save_variable_csvs,
)
from src.fig_makers.plot_scenarios import plot_scenarios
from src.fig_makers.plot_siting import plot_siting
from src.fig_makers.plot_network import plot_network
from src.fig_makers.plot_network_layered import plot_network_layered
from src.fig_makers.plot_voltage import plot_voltage_surface


def run_single_scenario(scenario_name: str):
    config = load_config(scenario_name)
    out_dir = prepare_output_dir(scenario_name)
    logger = setup_logger("cired", out_dir / "run.log")

    logger.info("=" * 60)
    logger.info(f"시나리오: {scenario_name}  |  시작: {datetime.now().isoformat(timespec='seconds')}")
    logger.info(config.get("description", ""))
    logger.info("\n" + network_summary())

    chp_enabled = config.get("components", {}).get("chp", True)
    mode = get(config, "planning.mode", "stochastic")

    # ── 데이터 / 시나리오 ─────────────────────────────────
    profiles = load_profiles(config, data_dir="data", logger=logger)
    full_scenario = build_scenarios(config, profiles)
    logger.info(f"시나리오 생성: type={get(config, 'scenarios.type', '?')}, "
                f"S={len(full_scenario['probs'])}")

    plot_scenarios(full_scenario, out_dir / "figs" / "scenarios.png",
                   chp_enabled=chp_enabled)

    model_scenario = (collapse_to_expected(full_scenario)
                      if mode == "deterministic" else full_scenario)

    # ── 모델 build / solve ────────────────────────────────
    lpf = LinearPowerFlow(verbose=get(config, "solver.verbose", False))
    data = {"scenario": model_scenario, "lpf": lpf}

    logger.info("모델 구성 중...")
    model = build_model(config, data)

    # 대규모 시나리오(MC) tractability: tractable 시나리오의 siting 을 고정(용량 자유)
    siting_from = get(config, "planning.siting_from", None)
    if siting_from:
        siting = load_siting(siting_from)
        fix_siting(model, siting)
        logger.info(f"siting 고정: '{siting_from}' 배치 재사용 (용량·운영은 자유) → tractable")

    # MIP warm-start: 결정론 등 빠른 시나리오의 1단계 해를 초기 incumbent 로 주입
    #   → 어려운 stochastic MILP(rep24)가 junk incumbent 에 갇히는 것을 방지.
    use_warmstart = False
    warmstart_from = get(config, "planning.warmstart_from", None)
    if warmstart_from and not siting_from:        # siting 고정 시엔 불필요
        ws = load_warmstart(warmstart_from)
        if ws:
            apply_warmstart(model, ws)
            use_warmstart = True
            logger.info(f"warm-start 원본: '{warmstart_from}' 1단계 해 주입")
        else:
            logger.warning(f"warm-start 원본 없음('{warmstart_from}') → cold start")

    solve_model(model, config, warmstart=use_warmstart)

    # ── 결과 추출 / 저장 ──────────────────────────────────
    results = extract_results(model, config, data)
    save_results_json(results, out_dir / "results")
    export_summary_excel(results, config, out_dir / "results" / f"results_{scenario_name}.xlsx")
    if get(config, "output.save_variable_csvs", False):
        save_variable_csvs(extract_all(model), out_dir / "results")

    # ── Figure ────────────────────────────────────────────
    plot_siting(results, out_dir / "figs" / "siting.png",
                title=f"Siting result ({scenario_name})")
    plot_network(results, out_dir / "figs" / "network.png", title="Optimal DER Siting",
                 lam=(get(config, "planning.lambda_risk") if mode == "stochastic" else None))
    plot_network_layered(results, out_dir / "figs" / "network_layered.png")
    vprof = compute_voltage_profile(model, data, chp_enabled)
    plot_voltage_surface(vprof, out_dir / "figs" / "voltage_profile.png",
                         title=f"Voltage profile ({scenario_name})")

    _print_summary(results, logger)
    logger.info(f"완료 → outputs/{scenario_name}/")
    return results


def _print_summary(r, logger):
    logger.info("-" * 60)
    logger.info("[결과 요약]")
    logger.info(f"  계획 전략   : {r.get('mode')}")
    logger.info(f"  총비용      : {(r.get('objective', 0) or 0) / 1e8:,.1f} 억원")
    logger.info(f"   ├ 투자비   : {r.get('invest_cost', 0) / 1e8:,.1f} 억원")
    logger.info(f"   └ 기대운영 : {r.get('expected_op_cost', 0) / 1e8:,.1f} 억원 "
                f"(CVaR {r.get('cvar_op_cost', 0) / 1e8:,.1f} 억원)")
    logger.info(f"  PV  : {r.get('total_PV_MWp', 0):.2f} MWp ({r.get('n_pv_sites', 0)}개소), "
                f"curtailment {r.get('curtailment_pct', 0):.1f}%")
    logger.info(f"  ESS : {r.get('total_P_MW', 0):.2f} MW / {r.get('total_E_MWh', 0):.2f} MWh "
                f"({r.get('n_ess_sites', 0)}개소)")
    logger.info(f"  CHP : {r.get('total_CHP_MW', 0):.2f} MW ({r.get('n_chp_sites', 0)}개소)")
    logger.info(f"  보일러/TES : {r.get('total_boiler_MW', 0):.2f} MW_th / "
                f"{r.get('total_TES_MWh', 0):.2f} MWh_th ({r.get('n_tes_sites', 0)}개소)")
    if r.get("dhn"):
        logger.info(f"  DHN : {r['dhn']['total_pipe_km']:.1f} km, "
                    f"투자비 {r['dhn']['invest_cost_억']:.1f} 억원")
    logger.info("-" * 60)


def main():
    parser = argparse.ArgumentParser(description="다중에너지 계획 시나리오 실행")
    parser.add_argument("--scenario", nargs="+", required=True,
                        help="시나리오 이름 (예: cired_deterministic cired_stochastic)")
    args = parser.parse_args()

    for name in args.scenario:
        print(f"\n{'=' * 60}\n  Running: {name}\n{'=' * 60}")
        run_single_scenario(name)


if __name__ == "__main__":
    main()
