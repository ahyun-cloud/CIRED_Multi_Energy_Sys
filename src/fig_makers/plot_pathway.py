"""plot_pathway.py - 미래경로(연도별) trajectory + ESS 가치분해 그림."""

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
import numpy as np


def plot_pathway(rows, out_path):
    """연도축 4-panel: 설치용량 / curtailment / 총비용 / ESS 가치."""
    yr = [r["year"] for r in rows]
    fig, ax = plt.subplots(2, 2, figsize=(12, 8))

    a = ax[0, 0]
    a.plot(yr, [r["PV_MWp"] for r in rows], "o-", color="tomato", lw=2, label="PV [MWp]")
    a.plot(yr, [r["ESS_MW"] for r in rows], "s-", color="steelblue", lw=2, label="ESS [MW]")
    a.plot(yr, [r["CHP_MW"] for r in rows], "D-", color="seagreen", lw=2, label="CHP [MW]")
    a.set_title("Optimal capacity pathway", fontweight="bold")
    a.set_ylabel("Capacity"); a.legend(); a.grid(alpha=0.3)

    a = ax[0, 1]
    cn = [r["curt_noESS_%"] for r in rows]
    ce = [r["curt_ESS_%"] for r in rows]
    a.plot(yr, cn, "o-", color="tomato", lw=2, label="Without ESS")
    a.plot(yr, ce, "s-", color="steelblue", lw=2, label="With ESS")
    a.fill_between(yr, ce, cn, color="steelblue", alpha=0.15, label="ESS-absorbed")
    a.set_title("PV curtailment", fontweight="bold")
    a.set_ylabel("Curtailment [%]"); a.legend(); a.grid(alpha=0.3)

    a = ax[1, 0]
    a.plot(yr, [r["cost_noESS_억"] for r in rows], "o-", color="tomato", lw=2, label="Without ESS")
    a.plot(yr, [r["cost_ESS_억"] for r in rows], "s-", color="steelblue", lw=2, label="With ESS")
    a.set_title("Total system cost (NPV)", fontweight="bold")
    a.set_xlabel("Year"); a.set_ylabel("Cost [억원]"); a.legend(); a.grid(alpha=0.3)

    a = ax[1, 1]
    a.plot(yr, [r["val_total_억"] for r in rows], "D-", color="purple", lw=2,
           label="ESS operational value")
    a.plot(yr, [r["cvar_noESS_억"] - r["cvar_ESS_억"] for r in rows], "^--",
           color="darkorange", lw=2, label="CVaR reduction (risk hedge)")
    a.axhline(0, color="k", lw=0.6)
    a.set_title("ESS value over time", fontweight="bold")
    a.set_xlabel("Year"); a.set_ylabel("Value [억원]"); a.legend(); a.grid(alpha=0.3)

    for a in ax.flat:
        a.set_xticks(yr)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_ess_value(rows, out_path):
    """연도별 ESS 가치 원천 분해 stacked bar.

    가치 = (ESS 없음) − (ESS 최적) 운영비 항목차. 양수=ESS 덕분에 절감된 비용.
    구성: 피크저감 / 차익·자가소비 / PV흡수(REC) / 연료·탄소대체  −  ESS 열화비.
    """
    yr = [str(r["year"]) for r in rows]
    x = np.arange(len(yr))

    comps = [("val_peak_억", "Peak shaving (demand charge)", "steelblue"),
             ("val_arb_억", "Arbitrage / self-consumption", "skyblue"),
             ("val_pv_억", "PV absorption (REC)", "gold"),
             ("val_fuel_억", "Fuel/carbon substitution", "seagreen")]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    pos = np.zeros(len(yr))   # 양수 누적 기준
    neg = np.zeros(len(yr))   # 음수 누적 기준
    for key, lab, col in comps:
        vals = np.array([r[key] for r in rows], dtype=float)
        bottoms = np.where(vals >= 0, pos, neg)
        ax.bar(x, vals, 0.6, bottom=bottoms, label=lab, color=col)
        pos = pos + np.where(vals >= 0, vals, 0.0)
        neg = neg + np.where(vals < 0, vals, 0.0)
    # ESS 열화비(가치 차감) → 음수 막대
    deg = np.array([-r["val_deg_억"] for r in rows], dtype=float)
    ax.bar(x, deg, 0.6, bottom=np.where(deg >= 0, pos, neg),
           label="ESS degradation (−)", color="lightcoral")

    ax.plot(x, [r["val_total_억"] for r in rows], "ko-", lw=2, label="Net ESS value")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(yr)
    ax.set_xlabel("Year"); ax.set_ylabel("ESS value [억원]")
    ax.set_title("ESS value decomposition over policy pathway", fontweight="bold")
    ax.legend(fontsize=8, loc="best"); ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_param_trends(csv_path, params, out_path, anchor_2024=None):
    """입력 파라미터 과거실측(+문헌앵커) → 미래가정 trajectory (6-panel).

    미래 가정이 과거 추세와 정합함을 보여 가정의 근거·투명성을 확보하는 그림.
    csv: 연도 / 평균SMP[원/kWh] / REC[원/MWh] / RE비중[%]  (한글 헤더 → 위치 인덱스 사용).
    params: future_pathway.PARAMS (연도→{pv,re,c_energy,carbon,rec,...}).
    anchor_2024: 과거 단일 앵커 {c_energy, carbon, pv} (csv에 없는 항목용).
    """
    import pandas as pd
    from src.data_process.scenario_gen import make_korea_re_prices, _resolve_tariff

    anchor_2024 = anchor_2024 or {}
    try:
        df = pd.read_csv(csv_path, encoding="cp949")
    except Exception:                                  # noqa: BLE001
        df = pd.read_csv(csv_path, encoding="latin1")
    yr = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    smp_h = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    rec_h = pd.to_numeric(df.iloc[:, 2], errors="coerce")
    re_h = pd.to_numeric(df.iloc[:, 3], errors="coerce")

    fy = sorted(params)
    tariff = _resolve_tariff({})
    re_f = [params[y]["re"] for y in fy]
    rec_f = [params[y]["rec"] / 1000 for y in fy]                 # k-won/MWh
    ce_f = [params[y]["c_energy"] / 1e6 for y in fy]              # M-won/MWh
    cb_f = [params[y]["carbon"] / 1000 for y in fy]              # k-won/tCO2
    pv_f = [params[y]["pv"] for y in fy]
    smp_f = [make_korea_re_prices(params[y]["re"], "summer", tariff)[0][12]
             for y in fy]                                         # 정오 수출단가

    HIST = dict(color="0.35", marker="o", ls="-", label="Historical / anchor")
    FUT = dict(color="crimson", marker="*", ms=12, ls="--", label="Future (assumed)")

    fig, ax = plt.subplots(2, 3, figsize=(14, 8))
    panels = [
        (ax[0, 0], yr, re_h, fy, re_f, "RE share", "%"),
        (ax[0, 1], yr, smp_h, fy, smp_f, "SMP / midday export price", "won/kWh"),
        (ax[0, 2], yr, rec_h / 1000, fy, rec_f, "REC price", "k-won/MWh"),
        (ax[1, 0], None, None, fy, ce_f, "ESS energy cost", "M-won/MWh"),
        (ax[1, 1], None, None, fy, cb_f, "Carbon price (K-ETS)", "k-won/tCO2"),
        (ax[1, 2], None, None, fy, pv_f, "PV deployment", "MWp"),
    ]
    anchor_key = {ax[1, 0]: ("c_energy", 1e6), ax[1, 1]: ("carbon", 1000),
                  ax[1, 2]: ("pv", 1.0)}
    for a, xh, yh, xf, yf, title, unit in panels:
        if xh is not None:
            a.plot(xh, yh, **HIST)
        elif a in anchor_key:
            k, div = anchor_key[a]
            if k in anchor_2024:
                a.plot([2024], [anchor_2024[k] / div], **HIST)
        a.plot(xf, yf, **FUT)
        a.axvspan(2025.5, 2051, color="navy", alpha=0.05)        # 미래 구간 음영
        a.set_title(title, fontweight="bold")
        a.set_xlabel("Year"); a.set_ylabel(unit)
        a.grid(alpha=0.3); a.legend(fontsize=7)

    fig.suptitle("Input parameter trajectories: historical actuals → future assumptions",
                 fontweight="bold", y=1.005)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
