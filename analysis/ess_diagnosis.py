"""
ess_diagnosis.py - ESS 경제성 진단 (SOC 종기조건 수정 후)

배경:
    SOC 종기조건 수정 후 rep24 최적해에서 ESS 가 0 이 되었다. ESS 가 손익분기
    경계에 있는지, 어떤 조건에서 경제적이 되는지 정량화한다.

세 가지 진단:
    A. ESS 가치곡선   — ESS 출력을 X MW 로 강제하고 목적함수 증가분 측정
                        → "ESS 를 X MW 지으면 얼마 손실인가"
    B. 단가 손익분기  — ESS capex(c_power/c_energy/c_deg)를 k 배로 낮추며
                        ESS 자유배치 → ESS 가 진입하는 k 를 찾는다
    C. 기본요금 민감도 — demand_charge 를 d 배로 올리며 ESS 자유배치

공통 처리:
    PV·CHP·TES 의 siting 은 수정 후 rep24 해로 고정하여 tractable 하게 만든다
    (ESS 이외 자원의 배치 조합 탐색을 제거). ESS 는 진단별로 off/강제/자유.
    데이터·LPF 는 1회만 계산해 모든 변형에서 재사용한다.

Usage:
    python analysis/ess_diagnosis.py                    # 전체
    python analysis/ess_diagnosis.py --only A           # A 만
    python analysis/ess_diagnosis.py --only A B C
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

import pyomo.environ as pyo

from src.utils.config_loader import load_config, _deep_merge, get
from src.utils.logger import setup_logger
from src.data_process.loader import load_profiles
from src.data_process.scenario_gen import build_scenarios
from src.powerflow.linear_pf import LinearPowerFlow
from src.planning.model import build_model
from src.planning.solver import solve_model
from src.planning.extractor import extract_results, compute_cost_breakdown

OUT = Path("outputs") / "ess_diagnosis"

# 진단 격자 --------------------------------------------------------------
ESS_FORCE_MW = [0.5, 1.0, 1.16, 1.5]      # A: 강제 설치 출력 [MW]
COST_FACTORS = [1.0, 0.8, 0.7, 0.6, 0.5]  # B: ESS capex 배수 [-]
DC_FACTORS = [1.0, 1.5, 2.0]              # C: 기본요금 배수 [-]
MC_COST_FACTORS = [1.0, 0.7]              # D: MC100(실측 불확실성) × ESS capex 배수
# F: FR 용량요금 [원/MW/h]. 손익분기는 c_deg·μ = 33,333×0.25 = 8,333 (현재값 8,500).
#    capex 는 고정 → 예비력 정산단가만의 임계값을 본다.
FR_PRICES = [8_500, 10_000, 12_000, 15_000, 20_000]

ESS_FORCE_NODE = 7                         # A: 강제 설치 노드 (기존 논문 해와 동일)

# 진단용 solver 설정 (본 실행보다 짧게 — siting 고정으로 대부분 LP 수준)
SOLVER_FIXED = {"time_limit": 600, "mip_gap": 0.005}    # ESS off/강제 (완전 고정)
SOLVER_FREE = {"time_limit": 1800, "mip_gap": 0.005}    # ESS 자유배치 (11 이진)
SOLVER_MC = {"time_limit": 2700, "mip_gap": 0.01}       # D: S=100 × ESS 자유배치


def load_rep24_siting(path="outputs/cired_rep24/results/summary.json") -> dict:
    """수정 후 rep24 해에서 PV/CHP/TES 설치 노드를 읽는다 (ESS 는 사용 안 함)."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {
        "pv": {int(k) for k in d.get("pv_sites", {})},
        "chp": {int(k) for k, v in d.get("chp_sites", {}).items()
                if v.get("P_e_MW", 0) > 1e-4},
        "tes": {int(k) for k, v in d.get("chp_sites", {}).items()
                if v.get("E_tes_MWh", 0) > 1e-4},
        "_objective": d.get("objective"),
    }


def apply_fixing(m, siting: dict, ess_mode: str,
                 ess_node: int = None, ess_p_mw: float = None):
    """PV/CHP/TES siting 고정 + ESS 는 모드별로 off / forced / free.

    ess_mode:
        'off'    : 모든 ESS 설치 금지 (기준선)
        'forced' : ess_node 에만 설치하고 출력을 ess_p_mw 로 고정 (에너지는 자유)
        'free'   : ESS 설치 여부·노드·용량 모두 자유 (11 후보노드 이진 탐색)
    """
    for n in m.N_pv:
        m.inv_pv[n].fix(1 if n in siting["pv"] else 0)
    if hasattr(m, "inv_chp"):
        for n in m.N_chp:
            m.inv_chp[n].fix(1 if n in siting["chp"] else 0)
            m.inv_tes[n].fix(1 if n in siting["tes"] else 0)
            # inv_boiler 는 자유 (꼬리 시나리오 열 백업 허용)

    if ess_mode == "off":
        for n in m.N_ess:
            m.inv_ess[n].fix(0)
    elif ess_mode == "forced":
        if ess_node not in list(m.N_ess):
            raise ValueError(f"node {ess_node} 는 ESS 후보노드가 아닙니다: {list(m.N_ess)}")
        for n in m.N_ess:
            m.inv_ess[n].fix(1 if n == ess_node else 0)
        m.cap_ess_p[ess_node].fix(ess_p_mw)     # 에너지 용량은 duration 제약 내 자유
    elif ess_mode != "free":
        raise ValueError(f"알 수 없는 ess_mode: {ess_mode}")


def solve_variant(label, base_config, overrides, profiles, lpf, siting,
                  ess_mode, logger, ess_node=None, ess_p_mw=None):
    """변형 1개를 풀어 결과 dict 를 반환. 실패 시 status 를 담아 반환."""
    config = _deep_merge(base_config, overrides)
    scenario = build_scenarios(config, profiles)
    data = {"scenario": scenario, "lpf": lpf}

    m = build_model(config, data)
    apply_fixing(m, siting, ess_mode, ess_node, ess_p_mw)

    logger.info(f"--- [{label}] 풀이 시작 (ess_mode={ess_mode}) ---")
    _, status = solve_model(m, config)
    if "optimal" not in status.lower() and "maxTimeLimit" not in status:
        logger.error(f"[{label}] 종료 상태 = {status} → 결과 신뢰 불가")
        return {"label": label, "status": status}

    r = extract_results(m, config, data)
    chp_on = config.get("components", {}).get("chp", True)
    bd = compute_cost_breakdown(m, config, chp_on)

    row = {
        "label": label,
        "status": status,
        "objective_억": r["objective"] / 1e8,
        "invest_억": r["invest_cost"] / 1e8,
        "exp_op_억": r["expected_op_cost"] / 1e8,
        "cvar_억": r["cvar_op_cost"] / 1e8,
        "ess_P_MW": r["total_P_MW"],
        "ess_E_MWh": r["total_E_MWh"],
        "ess_nodes": ",".join(str(k) for k in r["ess_sites"]),
        "chp_MW": r["total_CHP_MW"],
        "tes_MWh": r["total_TES_MWh"],
        "boiler_MW": r["total_boiler_MW"],
        "curt_%": r["curtailment_pct"],
        "demand_charge_억": bd["demand_charge"] / 1e8,
        "ess_deg_억": bd["ess_degradation"] / 1e8,
        "fr_net_억": bd["fr_net"] / 1e8,
        "import_억": bd["import_cost"] / 1e8,
        "export_억": bd["export_revenue"] / 1e8,
    }
    logger.info(
        f"[{label}] obj={row['objective_억']:.2f}억  inv={row['invest_억']:.2f}  "
        f"E[op]={row['exp_op_억']:.2f}  CVaR={row['cvar_억']:.2f}  "
        f"ESS={row['ess_P_MW']:.3f}MW  CHP={row['chp_MW']:.3f}  TES={row['tes_MWh']:.2f}"
    )
    return row


CSV_COLS = ["label", "status", "objective_억", "delta_vs_base_억", "invest_억",
            "exp_op_억", "cvar_억", "ess_P_MW", "ess_E_MWh", "ess_nodes",
            "chp_MW", "tes_MWh", "boiler_MW", "curt_%", "demand_charge_억",
            "ess_deg_억", "fr_net_억", "import_억", "export_억",
            "cost_factor", "dc_factor", "scenario_set",
            "fr_cap_price", "fr_net_rate"]


def write_csv(rows, path):
    """케이스마다 즉시 덮어쓰기 — 중간 실패 시에도 여기까지의 결과를 보존."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v)
                        for k, v in r.items()})


def safe_solve(rows, csv_path, logger, *a, **kw):
    """solve_variant 를 감싸 예외를 삼키고, 성공/실패 모두 즉시 CSV 에 반영."""
    label = a[0] if a else kw.get("label", "?")
    try:
        r = solve_variant(*a, **kw)
    except Exception as exc:                                # noqa: BLE001
        logger.error(f"[{label}] 예외로 건너뜀: {type(exc).__name__}: {exc}")
        r = {"label": label, "status": f"EXCEPTION: {type(exc).__name__}"}
    rows.append(r)
    write_csv(rows, csv_path)
    return r


def ess_cost_override(k: float, scale_deg: bool = True) -> dict:
    """ESS capex 를 k 배로.

    scale_deg=True  : c_deg 도 함께 k 배 (c_deg = c_energy/(2·cycle_life) 연동 관계).
        ※ 주의 — base.yaml 은 FR 순단가를 (c_deg·μ − fr_price) ≈ 0 이 되도록 현재
          c_deg=33,333 기준으로 의도적으로 맞춰 두었다. 따라서 c_deg 를 낮추면
          FR 이 손익분기에서 벗어나 '용량요금 수익'이 함께 열린다.
          진단 B 의 ESS 진입은 대부분 이 FR 수익 때문이며 순수 capex 효과가 아니다.
    scale_deg=False : c_deg 를 33,333 에 고정 → FR 순단가 불변 → **순수 capex 효과만** 측정.
    """
    cost = {
        "c_power": 150_000_000 * k,          # [원/MW]
        "c_energy": 200_000_000 * k,         # [원/MWh]
        "c_fixed": 30_000_000 * k,           # [원/site]
    }
    if scale_deg:
        cost["c_deg_per_mwh"] = 33_333 * k   # [원/MWh throughput]
    return {"ess": {"cost": cost}}


def main():
    ap = argparse.ArgumentParser(description="ESS 경제성 진단")
    ap.add_argument("--only", nargs="+", default=["A", "B", "C", "D"],
                    choices=["A", "B", "C", "D", "E", "F"], help="실행할 진단")
    ap.add_argument("--out", default="diagnosis.csv",
                    help="결과 CSV 파일명 (outputs/ess_diagnosis/ 하위). "
                         "일부 진단만 재실행할 때 기존 결과를 덮지 않도록 분리")
    ap.add_argument("--time_limit", type=int, default=None,
                    help="[s] ESS 자유배치 케이스의 solver 시간제한 override. "
                         "시간제한으로 미수렴한 케이스를 다시 풀 때 사용")
    ap.add_argument("--fr_prices", type=int, nargs="+", default=None,
                    help="[원/MW/h] 진단 F 의 FR 용량요금 격자 override (임계값 세분화용)")
    args = ap.parse_args()

    if args.time_limit:
        SOLVER_FREE["time_limit"] = args.time_limit
        SOLVER_MC["time_limit"] = args.time_limit
    fr_prices = args.fr_prices if args.fr_prices else FR_PRICES

    OUT.mkdir(parents=True, exist_ok=True)
    logger = setup_logger("cired", OUT / "diagnosis.log")

    base_config = load_config("cired_rep24")
    # warm-start/siting_from 은 진단에서 쓰지 않는다 (직접 고정하므로)
    base_config.get("planning", {}).pop("warmstart_from", None)
    base_config.get("planning", {}).pop("siting_from", None)

    siting = load_rep24_siting()
    logger.info(f"고정 siting — PV {sorted(siting['pv'])}  "
                f"CHP {sorted(siting['chp'])}  TES {sorted(siting['tes'])}")
    logger.info(f"참조 rep24 목적함수 = {siting['_objective'] / 1e8:.2f} 억원")

    profiles = load_profiles(base_config, data_dir="data", logger=logger)
    lpf = LinearPowerFlow()

    rows = []
    csv_path = OUT / args.out

    # ── 기준선: ESS 금지 ────────────────────────────────────
    base_row = safe_solve(
        rows, csv_path, logger,
        "기준선(ESS 금지)", base_config, {"solver": SOLVER_FIXED},
        profiles, lpf, siting, "off", logger)
    o_base = base_row.get("objective_억")

    # ── A. ESS 가치곡선 (rep24, node 7 강제) ────────────────
    if "A" in args.only:
        for x in ESS_FORCE_MW:
            r = safe_solve(
                rows, csv_path, logger,
                f"A: ESS 강제 {x} MW", base_config, {"solver": SOLVER_FIXED},
                profiles, lpf, siting, "forced", logger,
                ess_node=ESS_FORCE_NODE, ess_p_mw=x)
            if "objective_억" in r and o_base is not None:
                r["delta_vs_base_억"] = r["objective_억"] - o_base
                write_csv(rows, csv_path)

    # ── B. ESS 단가 손익분기 (rep24, ESS 자유배치) ──────────
    if "B" in args.only:
        for k in COST_FACTORS:
            ov = _deep_merge(ess_cost_override(k), {"solver": SOLVER_FREE})
            r = safe_solve(
                rows, csv_path, logger,
                f"B: ESS 단가 x{k:.2f} ({int(200_000 * k):,}원/kWh)",
                base_config, ov, profiles, lpf, siting, "free", logger)
            r["cost_factor"] = k
            write_csv(rows, csv_path)

    # ── C. 기본요금 민감도 (rep24, ESS 자유배치) ────────────
    if "C" in args.only:
        for d in DC_FACTORS:
            ov = _deep_merge({"market": {"demand_charge": 8320 * d}},
                             {"solver": SOLVER_FREE})
            r = safe_solve(
                rows, csv_path, logger,
                f"C: 기본요금 x{d:.1f} ({int(8320 * d):,}원/kW/월)",
                base_config, ov, profiles, lpf, siting, "free", logger)
            r["dc_factor"] = d
            write_csv(rows, csv_path)

    # ── D. MC100 (실측 일간 변동성 반영) × ESS 자유배치 ─────
    #   rep24 는 월×요일 '평균' 프로파일이라 일간 PV 변동이 들어가지 않는다.
    #   실측 CV 0.43 수준의 불확실성은 MC100 에서만 표현되므로, ESS 의
    #   위험헤지 가치를 시험하려면 여기서 봐야 한다.
    #   ※ MC100 은 원래 siting_from 으로 ESS 까지 고정하지만(순환논리),
    #     여기서는 PV·CHP·TES 만 고정하고 ESS 는 자유로 둔다.
    if "D" in args.only:
        for k in MC_COST_FACTORS:
            ov = _deep_merge(ess_cost_override(k), {
                "scenarios": {"type": "monte_carlo", "n_scenarios": 100},
                "solver": SOLVER_MC,
            })
            r = safe_solve(
                rows, csv_path, logger,
                f"D: MC100 × ESS 단가 x{k:.2f} ({int(200_000 * k):,}원/kWh)",
                base_config, ov, profiles, lpf, siting, "free", logger)
            r["cost_factor"] = k
            r["scenario_set"] = "MC100"
            write_csv(rows, csv_path)

    # ── E. 순수 capex 효과 (c_deg 고정 → FR 순단가 불변) ────
    #   진단 B 는 c_deg 를 함께 낮춰 FR 수익이 열리므로 capex 효과와 섞인다.
    #   여기서는 c_deg 를 33,333 에 고정해 capex 만의 손익분기를 본다.
    #   추가로 FR 을 끈 케이스(k=1.0)를 넣어 FR 기여분을 분리한다.
    if "E" in args.only:
        for k in COST_FACTORS:
            ov = _deep_merge(ess_cost_override(k, scale_deg=False),
                             {"solver": SOLVER_FREE})
            r = safe_solve(
                rows, csv_path, logger,
                f"E: capex만 x{k:.2f} ({int(200_000 * k):,}원/kWh, c_deg 고정)",
                base_config, ov, profiles, lpf, siting, "free", logger)
            r["cost_factor"] = k
            write_csv(rows, csv_path)
        # FR 제외 (기본요금·차익만으로 ESS 가 성립하는지)
        ov = _deep_merge({"market": {"fr_enabled": False}}, {"solver": SOLVER_FREE})
        r = safe_solve(
            rows, csv_path, logger,
            "E: FR 제외 (단가 x1.00)", base_config, ov,
            profiles, lpf, siting, "free", logger)
        write_csv(rows, csv_path)

    # ── F. FR 정산단가 임계값 (capex·c_deg 고정) ────────────
    #   진단 E 로 capex 하락만으로는 ESS 가 도입되지 않음이 확인됐다. 반대로 진단 B 에서
    #   ESS 가 들어온 경로는 FR 순수익이었다. 그렇다면 "예비력 정산단가가 얼마를 넘어야
    #   배전급 ESS 가 성립하는가"가 정책적으로 가장 인용 가능한 숫자다.
    #   FR 순단가 = c_deg·μ − fr_cap_price = 8,333 − fr_cap_price [원/MW/h] (음수=수익).
    if "F" in args.only:
        for fp in fr_prices:
            ov = _deep_merge({"market": {"fr_cap_price": fp}}, {"solver": SOLVER_FREE})
            net = 33_333 * 0.25 - fp                     # [원/MW/h]
            r = safe_solve(
                rows, csv_path, logger,
                f"F: FR 단가 {fp:,}원/MW/h (순단가 {net:+,.0f})",
                base_config, ov, profiles, lpf, siting, "free", logger)
            r["fr_cap_price"] = fp
            r["fr_net_rate"] = net
            write_csv(rows, csv_path)

    logger.info(f"진단표 저장 → {csv_path}")

    # 콘솔 요약
    logger.info("=" * 78)
    logger.info(f"{'케이스':<34}{'obj(억)':>10}{'Δ(억)':>9}{'ESS(MW)':>9}{'노드':>7}")
    logger.info("-" * 78)
    for r in rows:
        if "objective_억" not in r:
            logger.info(f"{r['label']:<34}{'FAILED: ' + r.get('status', '?'):>35}")
            continue
        d = r.get("delta_vs_base_억")
        logger.info(f"{r['label']:<34}{r['objective_억']:>10.2f}"
                    f"{(f'{d:+.2f}' if d is not None else '-'):>9}"
                    f"{r['ess_P_MW']:>9.3f}{r['ess_nodes'] or '-':>7}")
    logger.info("=" * 78)


if __name__ == "__main__":
    main()
