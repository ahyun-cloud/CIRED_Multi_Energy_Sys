"""future_pathway.py - 한국 정책정합 미래경로 분석 (2030/2035/2040/2050).

제11차 전력수급기본계획(2025.2 확정)·NDC·2050 탄소중립 경로에 정박한 연도별 시나리오로
배전단 PV·ESS·CHP siting/sizing 진화와 ESS 가치 원천(피크저감/차익/PV흡수/위험헤지)을 분석.

연도별로 동시 반영하는 정책·기술 변화:
    - PV 침투율↑        (RE 목표 추세, 로컬 stylized 매핑)
    - ESS 비용 학습곡선↓ (BloombergNEF: 2010 대비 -93%, 2030 $80/kWh 팩)
    - RE 비중↑ → SMP↓   (make_korea_re_prices, 정오대 수출단가 하락)
    - 탄소가격↑          (K-ETS 강화; CHP·보일러 가스에 부과)
    - REC 단가↓          (재생 보급 확대)

가정 수치는 모두 stylized(민감도 대상). base = cired_rep24 (확률론 24, 자유 siting MILP).
각 연도 ESS 최적 / ESS 금지(counterfactual) 2회 풀이 → ESS 가치 분해.

실행: python analysis/future_pathway.py
결과: outputs/future_pathway/ (pathway.csv, pathway.png, ess_value.png)
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
import logging
from pathlib import Path

import pyomo.environ as pyo

from src.utils.config_loader import load_config, _deep_merge
from src.utils.logger import setup_logger
from src.data_process.loader import load_profiles
from src.data_process.scenario_gen import build_scenarios
from src.powerflow.linear_pf import LinearPowerFlow
from src.planning.model import build_model
from src.planning.solver import solve_model
from src.planning.extractor import extract_results, compute_cost_breakdown
from src.fig_makers.plot_pathway import plot_pathway, plot_ess_value, plot_param_trends

#: main() 이 setup_logger 로 핸들러를 붙이는 것과 같은 이름 — 모듈 함수에서도 쓰기 위해
logger = logging.getLogger("cired")

OUT = Path("outputs") / "future_pathway"        # --export_limit 시 __main__ 에서 재지정
BASE = "cired_rep24"
# 역송한계(export_limit_mw):
#   - 기본 None(무제한) = counterfactual. 이땐 curt≈0 → ESS PV흡수 가치 소멸(ESS≈0).
#   - --export_limit 지정 시 main pathway: 고침투서 curt 발생 → ESS 흡수가치 발현.
#   과거 미수렴 함정(CLAUDE.md)은 warm-start(ESS=0 초기해)+CPLEX튜닝으로 완화 시도.
EXPORT_LIMIT = None                              # [MW] None=무제한
# ESS-최적 풀이에서 PV 설치노드를 같은 연도 no-ESS 해로 고정할지 여부(--fix_pv_siting).
#   PV 배치는 손실 미계상으로 거의 degenerate한데 이진변수 32개가 분기탐색을 지배해
#   ESS 결정이 시간제한에 걸린다. 고정 시 조건부 분석이 되므로 결과 서술에 명시할 것.
FIX_PV_SITING = False
# 연도별 MILP 시간제한·gap (--time_limit/--mip_gap 로 조정).
#   2040 은 2400s(40분)에서 미수렴 → 재실행 시 넉넉히 늘릴 것(예: 10800 = 3시간).
TIME_LIMIT = 2400                                # [s]
MIP_GAP = 0.01

# 연도별 정책 가정 (stylized; 출처: 11차 전기본·NDC·BNEF·K-ETS) — 민감도 대상.
#   c_deg = c_energy / (2 × cycle_life 3000) 으로 동반 갱신.
PARAMS = {
    2030: dict(pv=3.3, re=21.6, c_energy=1.30e8, c_power=1.00e8, c_deg=21667,
               rec=65000, gas=82000, carbon=30000),
    2035: dict(pv=4.4, re=30.0, c_energy=1.10e8, c_power=0.85e8, c_deg=18333,
               rec=55000, gas=85000, carbon=50000),
    2040: dict(pv=5.6, re=35.0, c_energy=0.90e8, c_power=0.70e8, c_deg=15000,
               rec=45000, gas=88000, carbon=70000),
    2050: dict(pv=7.7, re=70.0, c_energy=0.70e8, c_power=0.55e8, c_deg=11667,
               rec=35000, gas=92000, carbon=100000),
}
YEARS = sorted(PARAMS)


def _override(p):
    ov = {
        "pv": {"target_mwp": p["pv"]},
        "ess": {"cost": {"c_power": p["c_power"], "c_energy": p["c_energy"],
                         "c_deg_per_mwh": p["c_deg"]}},  # rep24 본래 후보 11노드·cap 1.5 유지 (warm-start로 수렴)
        "market": {"rec_price": p["rec"], "gas_price": p["gas"],
                   "carbon_price": p["carbon"]},
        "scenarios": {"re_penetration": p["re"]},
        # 자유 siting MILP 수렴: tight gap(0.01) + 시간↑. warm-start(full ESS=0 주입)는
        #   _solve 에서 처리. ※ emphasis_mip=2 등 공격적 옵션은 2050 build-all 유발 →
        #   제거(rep24·sweep 검증대로 디폴트 + warm-start 가 안정적).
        "solver": {"time_limit": TIME_LIMIT, "mip_gap": MIP_GAP},
    }
    if EXPORT_LIMIT is not None:                  # 역송한계 → 고침투서 curt 발생 → ESS 흡수가치
        ov["grid"] = {"export_limit_mw": EXPORT_LIMIT}
    return ov


def _copy_solution(src, dst):
    """src 모델 해를 dst 모델 동일 변수에 복사 (CPLEX MIP warm-start 초기 incumbent)."""
    for sv in src.component_objects(pyo.Var, active=True):
        dv = getattr(dst, sv.name, None)
        if dv is None:
            continue
        for idx in sv:
            v = pyo.value(sv[idx], exception=False)
            if v is not None and idx in dv and not dv[idx].fixed:
                dv[idx].value = v


def _solve(base_config, override, profiles, lpf, no_ess, warm_src=None,
           fix_pv_from=None):
    config = _deep_merge(base_config, override)
    sc = build_scenarios(config, profiles)
    data = {"scenario": sc, "lpf": lpf}
    m = build_model(config, data)
    if no_ess:                       # counterfactual: ESS 설치 금지
        for n in m.N_ess:
            m.inv_ess[n].fix(0)
            m.cap_ess_p[n].fix(0)
            m.cap_ess_e[n].fix(0)
    if fix_pv_from is not None:
        # PV 설치노드를 같은 연도의 no-ESS proven-optimal 해로 고정 (용량은 자유).
        #   근거: 목적함수·수급식에 계통손실이 없어 PV 배치가 총 수전량에 영향을 주지
        #   않으므로 배치가 거의 degenerate하다. 32개 PV 이진변수가 분기탐색을 지배해
        #   "ESS 를 지을 것인가"라는 정작 중요한 질문이 시간제한에 걸리는 원인이 된다.
        #   ※ 조건부 분석임을 명시할 것 — 고정된 PV 배치 하에서의 ESS 최적성이다.
        n_on = 0
        for n in m.N_pv:
            on = pyo.value(fix_pv_from.inv_pv[n], exception=False)
            on = 1 if (on is not None and on > 0.5) else 0
            m.inv_pv[n].fix(on)
            n_on += on
        logger.info(f"  PV siting 고정: {n_on}노드 (no-ESS 해 재사용, 용량은 자유)")
    if warm_src is not None:         # ESS=0 해를 초기 incumbent로 제공 (build-all 회피)
        _copy_solution(warm_src, m)
    solve_model(m, config, warmstart=(warm_src is not None))
    chp_enabled = config.get("components", {}).get("chp", True)
    return (extract_results(m, config, data),
            compute_cost_breakdown(m, config, chp_enabled),
            m)


def _prevent_sleep():
    """실행 중 Windows 절전 방지 — 장시간 MILP 동안 PC sleep 시 wall-clock 폭증 차단."""
    try:
        import ctypes
        # ES_CONTINUOUS(0x80000000) | ES_SYSTEM_REQUIRED(0x00000001)
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:                                  # noqa: BLE001
        pass


CSV = OUT / "pathway.csv"


def _num(v):
    """CSV 문자열 → 숫자(가능하면 int) 변환."""
    try:
        f = float(v)
        s = str(v)
        return int(f) if (f.is_integer() and "." not in s and "e" not in s.lower()) else f
    except (ValueError, TypeError):
        return v


def _load_done():
    """기존 pathway.csv(체크포인트)에서 완료된 연도 로드 → {year: row}."""
    done = {}
    if CSV.exists():
        with open(CSV, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                rr = {k: _num(v) for k, v in r.items()}
                done[int(float(rr["year"]))] = rr
    return done


def _rewrite(done):
    """체크포인트 CSV 를 done 딕셔너리 내용으로 재작성 (재실행할 연도 행 제거용)."""
    if not done:
        CSV.unlink(missing_ok=True)
        return
    rows = [v for _, v in sorted(done.items())]
    with open(CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(years=None, redo=False):
    """years=None 이면 전체(YEARS), 리스트면 해당 연도만 풀이(단독 검증용).

    redo=True 면 그 연도의 기존 체크포인트 행을 지우고 다시 푼다. 미수렴으로
    남은 연도(2040)를 시간제한을 늘려 재실행할 때 쓴다.
    """
    run_years = sorted(years) if years else YEARS
    full_run = (run_years == YEARS)
    _prevent_sleep()
    OUT.mkdir(parents=True, exist_ok=True)
    logger = setup_logger("cired", OUT / "pathway.log")
    base_config = load_config(BASE)
    profiles = load_profiles(base_config, data_dir="data", logger=logger)
    lpf = LinearPowerFlow()

    done = _load_done()
    if redo:
        dropped = [y for y in run_years if y in done]
        if dropped:
            for y in dropped:
                done.pop(y)
            _rewrite(done)
            logger.info(f"--redo: 기존 체크포인트에서 {dropped} 제거 → 다시 풀이")
    if done:
        logger.info(f"체크포인트 발견 — 완료 연도 {sorted(done)} 스킵")

    for year in run_years:
        if year in done:
            logger.info(f"=== {year} 이미 완료(체크포인트) — 건너뜀 ===")
            continue
        p = PARAMS[year]
        ov = _override(p)
        logger.info(f"=== {year}  PV={p['pv']}MWp  RE={p['re']}%  "
                    f"c_energy={p['c_energy']:.2e}  carbon={p['carbon']} ===")
        res_0, bd_0, m_0 = _solve(base_config, ov, profiles, lpf, no_ess=True)
        res_e, bd_e, _ = _solve(base_config, ov, profiles, lpf, no_ess=False,
                                warm_src=m_0,
                                fix_pv_from=(m_0 if FIX_PV_SITING else None))

        # ESS 가치 = (ESS 없음) − (ESS 최적), 항목별 [억원]. 양수=ESS가 절감.
        val = {k: (bd_0[k] - bd_e[k]) / 1e8 for k in bd_e}
        row = {
            "year": year, "PV_MWp": p["pv"], "RE_pct": p["re"],
            "carbon_won_tco2": p["carbon"],
            "ESS_MW": round(res_e["total_P_MW"], 3),
            "ESS_MWh": round(res_e["total_E_MWh"], 3),
            "CHP_MW": round(res_e["total_CHP_MW"], 3),
            "curt_ESS_%": round(res_e["curtailment_pct"], 2),
            "curt_noESS_%": round(res_0["curtailment_pct"], 2),
            "cost_ESS_억": round(res_e["objective"] / 1e8, 1),
            "cost_noESS_억": round(res_0["objective"] / 1e8, 1),
            "cvar_ESS_억": round(res_e["cvar_op_cost"] / 1e8, 1),
            "cvar_noESS_억": round(res_0["cvar_op_cost"] / 1e8, 1),
            "val_peak_억": round(val["demand_charge"], 2),
            "val_arb_억": round(val["import_cost"] + val["export_revenue"], 2),
            "val_pv_억": round(val["rec_revenue"], 2),
            "val_fuel_억": round(val["fuel_carbon"], 2),
            "val_deg_억": round(val["ess_degradation"], 2),
            "val_total_억": round(val["total"], 2),
        }
        # ── 체크포인트: 연도 완료 즉시 CSV append (중단 대비) ──
        write_header = not CSV.exists()
        with open(CSV, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                w.writeheader()
            w.writerow(row)
        logger.info(f"  → {year} 저장됨: ESS={row['ESS_MW']}MW/{row['ESS_MWh']}MWh  "
                    f"CHP={row['CHP_MW']}MW  curt {row['curt_noESS_%']}→{row['curt_ESS_%']}%  "
                    f"ESS가치={row['val_total_억']}억")

    # ── 전체 완료 후 CSV 재로드 → 그림 (단독 검증 run 에서는 스킵) ──
    if not full_run:
        logger.info(f"부분 run({run_years}) — 그림 생성 스킵. 검증 후 전체 run 시 생성됨.")
        logger.info(f"완료 → {OUT}/")
        return
    final = [v for _, v in sorted(_load_done().items())]
    plot_pathway(final, OUT / "pathway.png")
    plot_ess_value(final, OUT / "ess_value.png")
    plot_param_trends("data/annual_smp_rec_re.csv", PARAMS, OUT / "param_trends.png",
                      anchor_2024={"c_energy": 2.0e8, "carbon": 9000, "pv": 3.3})
    logger.info(f"완료 → {OUT}/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="정책정합 미래경로 분석")
    ap.add_argument("--years", type=int, nargs="+", default=None,
                    help="풀 연도 한정(단독 검증용). 예: --years 2040")
    ap.add_argument("--export_limit", type=float, default=None,
                    help="[MW] 역송한계. 지정 시 별도 폴더(future_pathway_exp{값})로 저장. 미지정=무제한")
    ap.add_argument("--fix_pv_siting", action="store_true",
                    help="ESS-최적 풀이에서 PV 설치노드를 같은 연도 no-ESS 해로 고정 "
                         "(PV 이진 32개 제거 → ESS 결정 수렴 확보. 조건부 분석)")
    ap.add_argument("--out_suffix", default="",
                    help="출력 폴더 접미사 (기존 결과 보존용). 예: _fixpv")
    ap.add_argument("--time_limit", type=int, default=TIME_LIMIT,
                    help=f"[s] 연도별 MILP 시간제한 (기본 {TIME_LIMIT}). 미수렴 연도"
                         f" 재실행 시 늘릴 것. 예: --time_limit 10800")
    ap.add_argument("--mip_gap", type=float, default=MIP_GAP,
                    help=f"MIP 상대 gap 허용치 (기본 {MIP_GAP})")
    ap.add_argument("--redo", action="store_true",
                    help="--years 로 지정한 연도의 기존 체크포인트 행을 지우고 다시 풀이 "
                         "(없으면 이미 완료된 연도는 건너뜀)")
    args = ap.parse_args()
    if args.export_limit is not None:
        EXPORT_LIMIT = args.export_limit
        OUT = Path("outputs") / f"future_pathway_exp{args.export_limit:g}"
    if args.out_suffix:
        OUT = Path("outputs") / f"{OUT.name}{args.out_suffix}"
    CSV = OUT / "pathway.csv"
    FIX_PV_SITING = args.fix_pv_siting
    TIME_LIMIT = args.time_limit
    MIP_GAP = args.mip_gap
    main(years=args.years, redo=args.redo)
