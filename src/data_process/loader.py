"""
loader.py - 원본 공공데이터 CSV 로딩 → 월별×요일 정규화 프로파일

데이터 출처 (data/ 폴더, read-only):
  - KPX 지역별 시간별 태양광 발전량  → PV 출력 프로파일 + 변동성 σ
  - 한국지역난방공사 시간대별 열공급량 → 열수요 프로파일 + 변동성 σ
  - KPX 시간별 전국 전력수요량        → 전기부하 변동성 σ

CSV 가 없거나 표본이 부족하면 계절별 fallback 프로파일을 사용한다.
모든 프로파일은 month_{m}_{wd|we} 24개 그룹으로 정규화된다.

본 모듈은 '달력/계절' 헬퍼와 CSV 파싱을 담당하는 하위 계층이며,
scenario_gen.py 가 이 결과를 받아 최종 시나리오 배열을 구성한다.
"""

import csv
import os
from datetime import datetime

import numpy as np

# ─────────────────────────────────────────────────────────
# 달력 / 계절 헬퍼 (평년 기준 — 윤년 미처리, 논문 assumption)
# ─────────────────────────────────────────────────────────
DAYS_IN_MONTH = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

MONTH_KEYS = [f"month_{m}_{dt}" for m in range(1, 13) for dt in ("wd", "we")]


def weekday_days(month: int) -> int:
    return round(DAYS_IN_MONTH[month] * 5 / 7)


def weekend_days(month: int) -> int:
    return DAYS_IN_MONTH[month] - weekday_days(month)


def month_to_season(month: int) -> str:
    if month in (6, 7, 8):
        return "summer"
    if month in (3, 4, 5, 9, 10):
        return "spring_fall"
    return "winter"


def season_key(month: int, day_type: str) -> str:
    return f"{month_to_season(month)}_{day_type}"


# ─────────────────────────────────────────────────────────
# 계절별 fallback 프로파일 (실측 CSV 부재/부족 시)
#
# ★ 주의 — 아래 PV fallback 값은 **구버전 규약(일별 최대=1 정규화)** 으로 만들어졌다.
#   현재 _parse_pv_csv 는 설비용량 기준 per-unit 규약을 쓰므로 두 규약이 다르다.
#   data/kpx_pv_wind_2024.csv 가 있으면 이 fallback 은 사용되지 않지만(정상 경로),
#   CSV 없이 실행하면 PV 발전량이 약 1.7배 과대·σ가 약 10배 과소로 잡힌다.
#   CSV 없는 환경에서 정량 결과가 필요하면 이 표를 새 규약으로 재생성해야 한다.
# ─────────────────────────────────────────────────────────
_PV_SEASON_FALLBACK = {
    "summer_wd":      np.array([0.001, 0, 0, 0, 0, 0.004, 0.067, 0.235, 0.458, 0.663, 0.797, 0.893, 0.949, 0.976, 0.931, 0.824, 0.722, 0.502, 0.313, 0.188, 0.123, 0.053, 0.015, 0.003]),
    "summer_we":      np.array([0.001, 0, 0, 0, 0, 0.003, 0.066, 0.226, 0.441, 0.635, 0.758, 0.854, 0.922, 0.962, 0.923, 0.832, 0.738, 0.510, 0.309, 0.176, 0.114, 0.050, 0.013, 0.003]),
    "spring_fall_wd": np.array([0.001, 0, 0, 0, 0, 0.001, 0.025, 0.163, 0.419, 0.676, 0.811, 0.917, 0.958, 0.946, 0.851, 0.700, 0.566, 0.376, 0.226, 0.160, 0.105, 0.045, 0.012, 0.003]),
    "spring_fall_we": np.array([0.001, 0, 0, 0, 0, 0.001, 0.029, 0.179, 0.453, 0.719, 0.846, 0.927, 0.955, 0.935, 0.849, 0.693, 0.554, 0.363, 0.212, 0.158, 0.107, 0.046, 0.013, 0.003]),
    "winter_wd":      np.array([0.001, 0, 0, 0, 0, 0, 0, 0.012, 0.163, 0.466, 0.728, 0.898, 0.969, 0.954, 0.823, 0.599, 0.441, 0.236, 0.184, 0.132, 0.068, 0.026, 0.008, 0.002]),
    "winter_we":      np.array([0.001, 0, 0, 0, 0, 0, 0, 0.014, 0.185, 0.512, 0.778, 0.940, 0.976, 0.921, 0.772, 0.545, 0.410, 0.244, 0.180, 0.131, 0.070, 0.026, 0.009, 0.002]),
}
_PV_SIGMA_FALLBACK = {
    "summer_wd": 0.0478, "summer_we": 0.0580,
    "spring_fall_wd": 0.0566, "spring_fall_we": 0.0590,
    "winter_wd": 0.0486, "winter_we": 0.0510,
}

_HEAT_SEASON_FALLBACK = {
    "summer_wd":      np.array([0.613, 0.531, 0.491, 0.481, 0.499, 0.573, 0.793, 1.108, 1.284, 1.348, 1.369, 1.355, 1.334, 1.321, 1.292, 1.263, 1.236, 1.185, 1.125, 1.105, 1.069, 0.988, 0.875, 0.759]),
    "summer_we":      np.array([0.730, 0.642, 0.590, 0.570, 0.576, 0.609, 0.678, 0.812, 1.034, 1.228, 1.307, 1.306, 1.267, 1.235, 1.200, 1.173, 1.168, 1.169, 1.200, 1.230, 1.219, 1.143, 1.027, 0.889]),
    "spring_fall_wd": np.array([0.940, 0.857, 0.807, 0.793, 0.804, 0.860, 1.022, 1.206, 1.162, 1.058, 1.000, 0.961, 0.934, 0.915, 0.891, 0.876, 0.890, 0.944, 1.069, 1.196, 1.264, 1.263, 1.200, 1.088]),
    "spring_fall_we": np.array([0.966, 0.881, 0.824, 0.804, 0.809, 0.833, 0.871, 0.935, 1.013, 1.074, 1.073, 1.039, 0.992, 0.953, 0.914, 0.896, 0.917, 0.984, 1.111, 1.238, 1.297, 1.274, 1.204, 1.098]),
    "winter_wd":      np.array([1.063, 1.010, 0.968, 0.949, 0.947, 0.975, 1.059, 1.164, 1.143, 1.018, 0.913, 0.839, 0.790, 0.762, 0.749, 0.753, 0.803, 0.929, 1.071, 1.179, 1.240, 1.260, 1.238, 1.178]),
    "winter_we":      np.array([1.077, 1.029, 0.988, 0.968, 0.964, 0.977, 1.000, 1.033, 1.054, 1.025, 0.962, 0.892, 0.839, 0.801, 0.778, 0.780, 0.832, 0.942, 1.083, 1.176, 1.225, 1.226, 1.201, 1.148]),
}
_HEAT_SIGMA_FALLBACK = {
    "summer_wd": 0.0819, "summer_we": 0.0638,
    "spring_fall_wd": 0.1493, "spring_fall_we": 0.1175,
    "winter_wd": 0.0548, "winter_we": 0.0513,
}

_LOAD_SIGMA_FALLBACK = {
    "summer_wd": 0.1217, "summer_we": 0.0980,
    "spring_fall_wd": 0.0938, "spring_fall_we": 0.0833,
    "winter_wd": 0.0914, "winter_we": 0.0707,
}


def _fallback_monthly(season_dict, sigma_dict):
    """계절별 fallback 을 월별×요일 24그룹으로 확장."""
    profiles, sigmas = {}, {}
    for m in range(1, 13):
        for dt in ("wd", "we"):
            sk = season_key(m, dt)
            if season_dict is not None:
                profiles[f"month_{m}_{dt}"] = season_dict[sk].copy()
            sigmas[f"month_{m}_{dt}"] = sigma_dict[sk]
    return profiles, sigmas


# ─────────────────────────────────────────────────────────
# CSV 파서
# ─────────────────────────────────────────────────────────
def _daily_scale_sigma(daily_totals, mode="lognormal"):
    """일 총량 산포 → Monte Carlo 스케일 계수의 σ.

    scenario_gen 은 프로파일에 스케일 계수를 곱해 시나리오를 만든다. 그 계수의 σ는
    '일별 총량이 얼마나 흔들리는가'여야 한다. 각 날을 자기 일통계로 정규화한 뒤
    형상 산포를 재면 일간 총량 변동이 모두 소거되어 σ가 실제의 1/10 수준으로
    과소평가된다(KPX 2024 태양광: 실측 일간 CV 0.431 vs 형상기반 0.044).

    기준 통계는 일 총량의 변동계수 CV = std/mean (실측값, 보고 가능).
    mode:
        'normal'    — 정규 스케일용. CV 를 그대로 σ로 사용.
        'lognormal' — 로그정규 스케일용. 그 분포가 위 CV 를 재현하도록
                      모먼트 정합: CV² = exp(σ²) − 1  →  σ = √ln(1+CV²).
                      (std(ln·)를 직접 쓰면 흐린 날의 로그 좌측 꼬리 때문에
                       CV 가 실측보다 커진다: 0.43 → 0.50.)
    표본 5일 미만이면 None (호출부에서 fallback).
    """
    e = np.asarray([t for t in daily_totals if t > 0], dtype=float)
    if e.size < 5:
        return None
    cv = float(np.std(e) / np.mean(e))
    if mode == "lognormal":
        return float(np.sqrt(np.log1p(cv ** 2)))
    return cv


def _parse_pv_csv(csv_path):
    """KPX 태양광 발전량 CSV → 월별 per-unit 프로파일 + 일간 변동성 σ.

    정규화 기준: 연중 최대 시간출력(설비용량 프록시)으로 **모든 날을 공통 기준**
    으로 나눈다. 따라서 profile[h] = 시간출력 / 설비용량 ∈ [0,1] 이 되어 모델의
    p_pv ≤ cap_pv × profile 과 단위가 정합하고, 흐린 날은 낮은 프로파일로 남는다.
    (이전 구현은 arr/arr.max() 로 날마다 다른 기준을 써서 모든 대표일이 '맑은 날'
     이 되고 일간 발전량 변동성이 사라졌다 — 발전량 약 1.7배 과대, σ 약 10배 과소.)
    """
    rows = {}
    with open(csv_path, encoding="cp949") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("연료원", "").strip() != "태양광":
                continue
            try:
                date = datetime.strptime(row["거래일자"].strip(), "%Y-%m-%d").date()
                hour = int(row["거래시간"]) - 1
                mwh = float(row["전력거래량(MWh)"])
            except (ValueError, KeyError):
                continue
            rows[(date, hour)] = rows.get((date, hour), 0.0) + mwh

    dates = sorted({d for d, _ in rows})
    daily = {d: np.array([rows.get((d, h), 0.0) for h in range(24)]) for d in dates}

    # 공통 정규화 기준 = 연중 최대 시간출력 (설비용량 프록시)
    #   [한계] 계통 전체가 동시에 정격에 도달하진 않으므로 실제 설비용량보다 작다
    #          → per-unit 출력이 다소 과대(이용률 약 19% vs 전국 실측 ~15%).
    p_ref = max((a.max() for a in daily.values()), default=0.0)
    if p_ref <= 0:
        raise ValueError("PV CSV 에서 정규화 기준 출력을 구할 수 없습니다")

    groups = {k: [] for k in MONTH_KEYS}
    totals = {k: [] for k in MONTH_KEYS}
    for date, arr in daily.items():
        if arr.sum() <= 0:            # 결측일만 제외 (흐린 날은 유지 — 불확실성의 원천)
            continue
        dt = "we" if date.weekday() >= 5 else "wd"
        key = f"month_{date.month}_{dt}"
        groups[key].append(arr / p_ref)
        totals[key].append(float(arr.sum()))

    return _finalize_groups(groups, _PV_SEASON_FALLBACK, _PV_SIGMA_FALLBACK,
                            totals=totals, sigma_mode="lognormal")


def _parse_heat_csv(csv_path):
    """지역난방공사 열공급량 CSV → 월별 정규화(일 평균=1) 프로파일 + σ."""
    rows = {}
    with open(csv_path, encoding="cp949") as f:
        reader = csv.DictReader(f)
        skip = {"실적일자", "요일", "시간", "단위"}
        jisa_cols = [h for h in reader.fieldnames if h not in skip]
        for row in reader:
            try:
                date = datetime.strptime(row["실적일자"].strip(), "%Y-%m-%d").date()
                hour = int(row["시간"]) - 1
            except (ValueError, KeyError):
                continue
            total = sum(float(row[c]) for c in jisa_cols
                        if row.get(c, "").strip() not in ("", "-"))
            rows[(date, hour)] = rows.get((date, hour), 0.0) + total

    dates = sorted({d for d, _ in rows})
    daily = {d: np.array([rows.get((d, h), 0.0) for h in range(24)]) for d in dates}

    # 열수요는 '형상'만 데이터에서 취한다 (절대 크기는 전기부하×heat.ratio 가정).
    #   → 프로파일은 일평균=1 정규화 유지. 단 MC 스케일 계수의 σ는 형상 산포가 아니라
    #     원단위 일 총량의 변동계수에서 구한다 (PV 와 같은 이유).
    groups = {k: [] for k in MONTH_KEYS}
    totals = {k: [] for k in MONTH_KEYS}
    for date, arr in daily.items():
        day_avg = arr.mean()
        if day_avg < 1e-6:
            continue
        dt = "we" if date.weekday() >= 5 else "wd"
        key = f"month_{date.month}_{dt}"
        groups[key].append(arr / day_avg)
        totals[key].append(float(arr.sum()))

    return _finalize_groups(groups, _HEAT_SEASON_FALLBACK, _HEAT_SIGMA_FALLBACK,
                            totals=totals, sigma_mode="normal")


def _parse_load_sigma_csv(csv_path):
    """KPX 전국 전력수요량 CSV → 월별 부하 스케일 변동성 σ (프로파일은 미사용).

    σ는 일 총수요의 변동계수(CV)로 산출한다. 각 날을 자기 일평균으로 정규화한 뒤
    형상 산포를 재면 일간 수요규모 변동이 소거된다 (PV·열과 같은 이유).
    """
    groups = {k: [] for k in MONTH_KEYS}
    with open(csv_path, encoding="cp949") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                date = datetime.strptime(row[0].strip(), "%Y-%m-%d")
                demand = np.array([float(x) for x in row[1:25]])
            except (ValueError, IndexError):
                continue
            dt = "we" if date.weekday() >= 5 else "wd"
            groups[f"month_{date.month}_{dt}"].append(demand)

    sigma_dict = {}
    _, fb_sigma = _fallback_monthly(None, _LOAD_SIGMA_FALLBACK)
    for key, data in groups.items():
        sig = _daily_scale_sigma([float(a.sum()) for a in data], "normal") if data else None
        sigma_dict[key] = sig if sig is not None else fb_sigma[key]
    return sigma_dict


def _finalize_groups(groups, season_fallback, sigma_fallback,
                     totals=None, sigma_mode="lognormal"):
    """그룹별 평균 프로파일 + 스케일 σ 산출. 표본 <5 면 fallback 사용.

    totals 가 주어지면 σ를 '일 총량 산포'(_daily_scale_sigma)에서 구한다.
    미지정 시에는 구버전과 동일하게 형상 산포를 쓰지만, 이는 일간 변동성을
    과소평가하므로 새 코드에서는 totals 를 넘길 것.
    """
    profiles, sigmas = {}, {}
    fb_p, fb_s = _fallback_monthly(season_fallback, sigma_fallback)
    for key, data in groups.items():
        if len(data) < 5:
            profiles[key] = fb_p[key]
            sigmas[key] = fb_s[key]
            continue
        arr = np.array(data)
        profiles[key] = arr.mean(axis=0)
        sig = _daily_scale_sigma(totals.get(key, []), sigma_mode) if totals else None
        sigmas[key] = sig if sig is not None else float(arr.std(axis=0).mean())
    return profiles, sigmas


# ─────────────────────────────────────────────────────────
# 공개 인터페이스
# ─────────────────────────────────────────────────────────
def load_profiles(config: dict, data_dir="data", logger=None) -> dict:
    """
    config['data_files'] 경로의 CSV 를 읽어 월별 프로파일/σ 묶음을 반환.

    Returns
    -------
    dict {
        'pv':   {'profiles': {...}, 'sigma': {...}},
        'heat': {'profiles': {...}, 'sigma': {...}},
        'load': {'sigma': {...}},
    }
    """
    files = config.get("data_files", {})

    def _say(msg):
        (logger.info if logger else print)(f"[loader] {msg}")

    def _load(kind, parser, fallback_season, fallback_sigma):
        fname = files.get(kind)
        path = os.path.join(data_dir, fname) if fname else None
        if path and os.path.exists(path):
            try:
                result = parser(path)
                _say(f"{kind} 실측 프로파일 로드 완료 ({fname})")
                return result
            except Exception as exc:                       # noqa: BLE001
                _say(f"{kind} CSV 파싱 실패 ({exc}) → fallback 사용")
        else:
            _say(f"{kind} CSV 없음 → fallback 사용")
        return _fallback_monthly(fallback_season, fallback_sigma)

    pv_p, pv_s = _load("pv", _parse_pv_csv, _PV_SEASON_FALLBACK, _PV_SIGMA_FALLBACK)
    heat_p, heat_s = _load("heat", _parse_heat_csv, _HEAT_SEASON_FALLBACK, _HEAT_SIGMA_FALLBACK)

    load_fname = files.get("demand")
    load_path = os.path.join(data_dir, load_fname) if load_fname else None
    if load_path and os.path.exists(load_path):
        try:
            load_sigma = _parse_load_sigma_csv(load_path)
            _say(f"demand 실측 σ 로드 완료 ({load_fname})")
        except Exception as exc:                           # noqa: BLE001
            _say(f"demand CSV 파싱 실패 ({exc}) → fallback 사용")
            _, load_sigma = _fallback_monthly(None, _LOAD_SIGMA_FALLBACK)
    else:
        _say("demand CSV 없음 → fallback 사용")
        _, load_sigma = _fallback_monthly(None, _LOAD_SIGMA_FALLBACK)

    return {
        "pv":   {"profiles": pv_p, "sigma": pv_s},
        "heat": {"profiles": heat_p, "sigma": heat_s},
        "load": {"sigma": load_sigma},
    }
