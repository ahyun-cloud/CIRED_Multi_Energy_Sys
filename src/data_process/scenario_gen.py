"""
scenario_gen.py - 시나리오 배열 생성 (대표 24일 / Monte Carlo)

loader.load_profiles() 가 만든 월별 정규화 프로파일을 받아
계획 모델이 소비하는 시나리오 배열을 구성한다.

시나리오 배열 schema (모든 값은 numpy):
    {
        'pv'      : (S, 24)  정규화 PV 출력 (0~1)
        'load'    : (S, 24)  정규화 전기부하 (피크=1 기준)
        'heat'    : (S, 24)  정규화 열수요 (일평균=1 기준)
        'price_im': (S, 24)  수전 단가 [원/kWh]
        'price_ex': (S, 24)  수출 단가 [원/kWh]
        'probs'   : (S,)     시나리오 확률 (합=1)
        'names'   : [str]    시나리오 이름
    }

요금 단위는 [원/kWh] 이며, 운영비 함수에서 ×1000 하여 [원/MWh] 로 변환한다.
"""

import numpy as np

from src.data_process.loader import (
    MONTH_KEYS, weekday_days, weekend_days, month_to_season,
)

# ─────────────────────────────────────────────────────────
# 한전 TOU 요금 (2025.04.01 기준, 원/kWh) — ★ 모듈 기본값(fallback)
#   실제 값은 base.yaml 'tariff' 섹션에서 외부화하여 주입(_resolve_tariff).
#   config 에 tariff 가 없을 때만 아래 기본값이 사용된다 (하위 호환).
# ─────────────────────────────────────────────────────────
KEPCO_IM = {   # 수전(구매) 단가
    "summer":      {"off": 95.7,  "mid": 121.5, "peak": 155.0},
    "spring_fall": {"off": 95.7,  "mid": 100.5, "peak": 119.7},
    "winter":      {"off": 103.1, "mid": 120.0, "peak": 149.4},
}
KEPCO_EX = {   # 수출(판매/SMP 대용) 단가
    "summer":      {"off": 58.0, "mid": 83.0, "peak": 102.0},
    "spring_fall": {"off": 55.0, "mid": 76.0, "peak":  92.0},
    "winter":      {"off": 62.0, "mid": 85.0, "peak": 105.0},
}

# 시간대(0~23) → 부하구간 패턴 (off/mid/peak)
_TOU_PATTERN = (
    ["off"] * 9 + ["mid", "peak", "peak", "mid", "peak", "peak",
                   "peak", "peak", "mid", "mid", "mid", "mid", "mid", "mid"]
    + ["off"]
)

# ─────────────────────────────────────────────────────────
# 한국 재생에너지 보급 시나리오 (민감도/비교용)
# ─────────────────────────────────────────────────────────
KOREA_RE_SCENARIOS = [
    ("현재(2024)",      10, "현행 SMP"),
    ("2030 NDC",        30, "탄소감축 목표"),
    ("2036 11차전기본", 50, "재생에너지 확대"),
    ("고재생 시나리오", 70, "장기 고재생"),
]
SMP_DROP_PER_10PCT = -5.0   # RE 10%p 증가당 SMP 변화 [원/kWh]


def _resolve_tariff(config: dict) -> dict:
    """config['tariff'] 를 모듈 기본값 위에 병합 (하드코딩 제거, 하위 호환).

    base.yaml 의 tariff 섹션이 있으면 그 값을, 없으면 모듈 기본값을 사용한다.
    """
    t = (config or {}).get("tariff", {}) or {}
    return {
        "import": t.get("import", KEPCO_IM),
        "export": t.get("export", KEPCO_EX),
        "pattern": t.get("tou_pattern", _TOU_PATTERN),
        "smp_noise_std": float(t.get("smp_noise_std", 0.05)),
        "re_smp_drop_per_10pct": float(t.get("re_smp_drop_per_10pct", SMP_DROP_PER_10PCT)),
    }


# ─────────────────────────────────────────────────────────
# 정규화 전기부하 프로파일 (요일별 고정 형상)
# ─────────────────────────────────────────────────────────
def _load_weekday():
    return np.array([
        0.52, 0.50, 0.48, 0.47, 0.48, 0.52, 0.62, 0.76,
        0.88, 0.93, 0.95, 0.94, 0.90, 0.92, 0.93, 0.95,
        0.97, 1.00, 0.98, 0.94, 0.87, 0.78, 0.68, 0.58,
    ])


def _load_weekend():
    return np.array([
        0.54, 0.51, 0.49, 0.48, 0.49, 0.52, 0.57, 0.63,
        0.70, 0.76, 0.80, 0.82, 0.81, 0.80, 0.80, 0.82,
        0.85, 0.88, 0.90, 0.88, 0.83, 0.76, 0.68, 0.60,
    ])


def _make_kepco_prices(season: str, tariff: dict = None):
    """계절별 24시간 수출/수전 단가 [원/kWh] 생성 (tariff 주입)."""
    tariff = tariff or _resolve_tariff({})
    r, e = tariff["import"][season], tariff["export"][season]
    pattern = tariff["pattern"]
    pim = np.array([r[seg] for seg in pattern])
    pex = np.array([e[seg] for seg in pattern])
    return pex, pim


def make_korea_re_prices(re_pct: float, season="spring_fall", tariff: dict = None):
    """재생에너지 비중에 따른 SMP(수출단가) 조정 [원/kWh]."""
    tariff = tariff or _resolve_tariff({})
    pex_base, pim = _make_kepco_prices(season, tariff)
    delta_pct = max(0.0, re_pct - 10.0)
    t = np.arange(24)
    drop_curve = np.exp(-0.5 * ((t - 12.5) / 3.0) ** 2)
    drop_curve[drop_curve < 0.05] = 0.0
    drop = drop_curve * (tariff["re_smp_drop_per_10pct"] * (delta_pct / 10.0))
    pex_adj = np.clip(pex_base + drop, 0.01, None)
    return pex_adj, pim


# ─────────────────────────────────────────────────────────
# 시나리오 빌더
# ─────────────────────────────────────────────────────────
def build_representative_24(profiles: dict, tariff: dict = None,
                            re_pct: float = 10.0) -> dict:
    """월별×요일 24개 대표 시나리오 (확률 = 연중 일수 비율).

    re_pct: 재생에너지 발전비중 [%]. >10 이면 정오대 SMP(수출단가) 하락 반영
            (make_korea_re_prices). 기본 10.0 → 하락 0 (기존 동일, 하위호환).
    """
    tariff = tariff or _resolve_tariff({})
    pv_prof = profiles["pv"]["profiles"]
    heat_prof = profiles["heat"]["profiles"]

    pv_s, ld_s, heat_s = [], [], []
    pex_s, pim_s, probs, names = [], [], [], []

    for m in range(1, 13):
        season = month_to_season(m)
        pex, pim = make_korea_re_prices(re_pct, season, tariff)
        for dt, ld_fn, n_days in (("wd", _load_weekday, weekday_days(m)),
                                  ("we", _load_weekend, weekend_days(m))):
            key = f"month_{m}_{dt}"
            pv_s.append(pv_prof[key])
            ld_s.append(ld_fn())
            heat_s.append(heat_prof[key])
            pex_s.append(pex)
            pim_s.append(pim)
            probs.append(n_days / 365.0)
            names.append(key)

    probs = np.array(probs)
    probs /= probs.sum()
    return {
        "pv": np.array(pv_s), "load": np.array(ld_s), "heat": np.array(heat_s),
        "price_ex": np.array(pex_s), "price_im": np.array(pim_s),
        "probs": probs, "names": names,
    }


def build_monte_carlo(profiles: dict, n_scenarios=100, seed=42,
                      tariff: dict = None, re_pct: float = 10.0) -> dict:
    """월별 σ 기반 Monte Carlo 샘플링 (seed 고정 — 재현성).

    re_pct: 재생에너지 비중 [%] → 정오대 SMP 하락 반영(기본 10 = 변화 없음).
    """
    tariff = tariff or _resolve_tariff({})
    smp_std = tariff["smp_noise_std"]
    rng = np.random.default_rng(seed)
    pv_prof = profiles["pv"]["profiles"]
    pv_sigma = profiles["pv"]["sigma"]
    heat_prof = profiles["heat"]["profiles"]
    heat_sigma = profiles["heat"]["sigma"]
    load_sigma = profiles["load"]["sigma"]

    base = []
    for m in range(1, 13):
        season = month_to_season(m)
        for dt, ld_fn, n_days in (("wd", _load_weekday, weekday_days(m)),
                                  ("we", _load_weekend, weekend_days(m))):
            key = f"month_{m}_{dt}"
            base.append((key, season, ld_fn(), n_days / 365.0))

    base_probs = np.array([b[3] for b in base])
    base_probs /= base_probs.sum()

    # 각 대표일에 배정할 표본 수 (확률 비례, 합 = n_scenarios)
    samples_per = np.round(base_probs * n_scenarios).astype(int)
    diff = n_scenarios - samples_per.sum()
    if diff > 0:
        for i in np.argsort(base_probs)[::-1][:diff]:
            samples_per[i] += 1
    elif diff < 0:
        for i in np.argsort(samples_per)[:abs(diff)]:
            samples_per[i] = max(1, samples_per[i] - 1)
        while samples_per.sum() > n_scenarios:
            samples_per[samples_per.argmax()] -= 1

    pv_s, ld_s, heat_s = [], [], []
    pex_s, pim_s, prob_list, names = [], [], [], []

    for b_idx, (key, season, base_ld, _) in enumerate(base):
        n_samp = int(samples_per[b_idx])
        if n_samp == 0:
            continue
        pex_base, pim_base = make_korea_re_prices(re_pct, season, tariff)
        for k in range(n_samp):
            # 로그정규 스케일: 평균이 1이 되도록 μ = -σ²/2 로 보정.
            #   (μ=0 이면 E[scale]=exp(σ²/2). σ=0.04 에선 무시할 수 있었으나
            #    실측 일간 변동성 σ≈0.4 에서는 약 8% 상향 편향이 된다.)
            s_pv = float(pv_sigma[key])
            pv_scale = np.clip(rng.lognormal(-0.5 * s_pv ** 2, s_pv), 0.15, 2.5)
            ld_scale = np.clip(rng.normal(1.0, load_sigma[key]), 0.75, 1.25)
            heat_scale = np.clip(rng.normal(1.0, heat_sigma[key]), 0.55, 1.55)
            smp_scale = np.clip(rng.normal(1.0, smp_std), 0.85, 1.15)

            pv_s.append(np.clip(pv_prof[key] * pv_scale, 0, 1))
            ld_s.append(np.clip(base_ld * ld_scale, 0, 1))
            heat_s.append(np.clip(heat_prof[key] * heat_scale, 0.3, 2.0))
            pex_s.append(pex_base * smp_scale)
            pim_s.append(pim_base.copy())
            prob_list.append(base_probs[b_idx] / n_samp)
            names.append(f"{key}_{k + 1}")

    probs = np.array(prob_list)
    probs /= probs.sum()
    return {
        "pv": np.array(pv_s), "load": np.array(ld_s), "heat": np.array(heat_s),
        "price_ex": np.array(pex_s), "price_im": np.array(pim_s),
        "probs": probs, "names": names,
    }


# 사계절 대표월: 봄(4월), 여름(7월), 가을(10월), 겨울(1월) 평일
_SEASON4 = [
    ("spring_fall", 4, "봄"),
    ("summer",      7, "여름"),
    ("spring_fall", 10, "가을"),
    ("winter",      1,  "겨울"),
]


def build_season_4(profiles: dict, tariff: dict = None,
                   re_pct: float = 10.0) -> dict:
    """봄·여름·가을·겨울 평일 대표 4개 시나리오 (빠른 테스트용).

    re_pct: 재생에너지 비중 [%] → 정오대 SMP 하락 반영(기본 10 = 변화 없음).
    """
    tariff = tariff or _resolve_tariff({})
    pv_prof = profiles["pv"]["profiles"]
    heat_prof = profiles["heat"]["profiles"]

    pv_s, ld_s, heat_s, pex_s, pim_s, names = [], [], [], [], [], []
    for season, month, label in _SEASON4:
        key = f"month_{month}_wd"
        pex, pim = make_korea_re_prices(re_pct, season, tariff)
        pv_s.append(pv_prof[key])
        ld_s.append(_load_weekday())
        heat_s.append(heat_prof[key])
        pex_s.append(pex)
        pim_s.append(pim)
        names.append(label)

    probs = np.full(4, 0.25)
    return {
        "pv": np.array(pv_s), "load": np.array(ld_s), "heat": np.array(heat_s),
        "price_ex": np.array(pex_s), "price_im": np.array(pim_s),
        "probs": probs, "names": names,
    }


def build_scenarios(config: dict, profiles: dict) -> dict:
    """config['scenarios'] 설정에 따라 시나리오 배열 생성."""
    sc_cfg = config.get("scenarios", {})
    sc_type = sc_cfg.get("type", "representative_24")
    tariff = _resolve_tariff(config)             # TOU 요금 외부화 주입
    re_pct = float(sc_cfg.get("re_penetration", 10.0))   # RE 비중[%] → SMP 하락 훅 (기본 10=무변화)
    if sc_type == "monte_carlo":
        return build_monte_carlo(
            profiles,
            n_scenarios=sc_cfg.get("n_scenarios", 100),
            seed=config.get("seed", 42),
            tariff=tariff,
            re_pct=re_pct,
        )
    if sc_type == "season_4":
        return build_season_4(profiles, tariff, re_pct=re_pct)
    return build_representative_24(profiles, tariff, re_pct=re_pct)


def collapse_to_expected(scenario: dict) -> dict:
    """확률 가중 평균으로 단일 시나리오로 축약 (결정론적 계획용)."""
    p = scenario["probs"][:, None]
    return {
        "pv":   (scenario["pv"] * p).sum(axis=0, keepdims=True),
        "load": (scenario["load"] * p).sum(axis=0, keepdims=True),
        "heat": (scenario["heat"] * p).sum(axis=0, keepdims=True),
        "price_ex": (scenario["price_ex"] * p).sum(axis=0, keepdims=True),
        "price_im": (scenario["price_im"] * p).sum(axis=0, keepdims=True),
        "probs": np.array([1.0]),
        "names": ["expected"],
    }


def compute_cvar(costs, probs, alpha=0.95):
    """이산 시나리오 비용 분포의 CVaR_α (사후 검증용)."""
    costs = np.asarray(costs, dtype=float)
    probs = np.asarray(probs, dtype=float)
    idx = np.argsort(costs)[::-1]
    sc, sp = costs[idx], probs[idx]
    cum = cvar = 0.0
    for c, p in zip(sc, sp):
        if cum >= (1 - alpha):
            break
        take = min(p, (1 - alpha) - cum)
        cvar += c * take
        cum += take
    return cvar / (1 - alpha) if (1 - alpha) > 0 else float(sc[0])
