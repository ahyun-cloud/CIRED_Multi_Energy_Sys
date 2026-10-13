"""plot_comparison.py - 결정론적 vs 확률론적 비교 / α·λ 민감도 시각화."""

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
import numpy as np


def plot_det_vs_stoch(r_det: dict, r_sto: dict, out_path, title=""):
    """결정론 vs 확률론 비교: (좌) 설비용량  (우) 비용 분해.
    단위가 다른 용량(MW/MWh)과 비용(억원)을 패널로 분리해 가독성 확보."""
    # 결정론은 시나리오가 1개라 CVaR 가 정의되지 않는다(그 값은 단일 시나리오 운영비).
    # 막대를 그리면 "위험회피 계획의 꼬리비용이 더 크다"로 거꾸로 읽히므로 생략하고 n/a 표기.
    det_na = {"cvar_op_cost"}

    def _grouped(ax, metrics, ylabel, ptitle):
        labels = [m[0] for m in metrics]
        det = [None if k in det_na else (r_det.get(k, 0) or 0) * sc for _, k, sc in metrics]
        sto = [(r_sto.get(k, 0) or 0) * sc for _, k, sc in metrics]
        x = np.arange(len(labels))
        ax.bar(x - 0.2, [0 if d is None else d for d in det], 0.4,
               label="Deterministic", color="gray")
        ax.bar(x + 0.2, sto, 0.4, label="Stochastic (CVaR)", color="steelblue")
        for i, (d, s) in enumerate(zip(det, sto)):
            if d is None:
                ax.annotate("n/a", (x[i] - 0.2, 0), ha="center", va="bottom",
                            fontsize=8, color="gray")
            else:
                ax.annotate(f"{d:.2f}", (x[i] - 0.2, d), ha="center", va="bottom", fontsize=8)
            ax.annotate(f"{s:.2f}", (x[i] + 0.2, s), ha="center", va="bottom", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel(ylabel)
        ax.set_title(ptitle, fontweight="bold")
        ax.grid(True, alpha=0.3, axis="y")

    # 위험회피가 어느 자원을 키우는지 보이는 조합: 전기 저장(ESS) vs 열 측(CHP·TES).
    #   ESS 가 0 이고 CHP·TES 가 커지는 것이 결과의 핵심이므로 TES 를 포함한다.
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    _grouped(ax1, [("ESS P [MW]", "total_P_MW", 1.0),
                   ("CHP P [MW]", "total_CHP_MW", 1.0),
                   ("TES E [MWh_th]", "total_TES_MWh", 1.0)],
             "Capacity", "Installed capacity")
    ax1.legend()
    _grouped(ax2, [("Investment", "invest_cost", 1e-8),
                   ("Expected OPEX", "expected_op_cost", 1e-8),
                   ("CVaR OPEX", "cvar_op_cost", 1e-8)],
             "Cost [100M KRW]", "Cost breakdown")
    fig.suptitle(f"Deterministic vs Stochastic {title}".strip(), fontweight="bold", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_sensitivity(rows: list, x_key: str, out_path):
    """α 또는 λ 민감도 4분할: 설치용량 · 투자비 · 기대운영비 · CVaR.

    설비 패널은 CHP 와 ESS 를 **같은 MW 축**에 겹쳐 그린다. ESS 단독 패널로 두면
    최적 ESS 가 0 인 현재 결과에서 y축이 ±0.04 인 빈 직선만 남아 그림이 고장난 것처럼
    보이고, 캡션이 말하는 investment 패널도 없었다. 투자비를 함께 보여야
    "위험회피를 강화하면 투자↑·운영비↓" 라는 trade-off 가 그림 안에서 읽힌다.
    """
    x_label = "CVaR confidence α" if x_key == "alpha" else "Risk weight λ"
    x = [r[x_key] for r in rows]
    chp = [(r.get("total_CHP_MW", 0) or 0) for r in rows]
    ess = [(r.get("total_P_MW", 0) or 0) for r in rows]

    # 라벨이 전부 영문이므로 한글 폰트(Malgun Gothic)에 의존하지 않는다.
    #   모듈 전역 설정을 그대로 쓰면 Malgun 이 없는 PC 에서 폰트가 달라져
    #   논문에 들어간 그림과 재생성본이 미세하게 어긋난다.
    with plt.rc_context({"font.family": "DejaVu Sans", "axes.unicode_minus": False}):
        return _sensitivity_body(x, x_label, x_key, chp, ess, rows, out_path)


def _sensitivity_body(x, x_label, x_key, chp, ess, rows, out_path):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))

    ax = axes[0, 0]
    ax.plot(x, chp, "o-", color="seagreen", lw=2, ms=7,
            markerfacecolor="white", markeredgewidth=2, label="CHP")
    ax.plot(x, ess, "s--", color="steelblue", lw=2, ms=7,
            markerfacecolor="white", markeredgewidth=2, label="ESS (battery)")
    if max(ess) <= 1e-6:                      # 전 구간 0 이면 그 사실을 글로 밝힌다
        ax.annotate("ESS = 0 throughout", xy=(x[len(x) // 2], 0), xytext=(0, 12),
                    textcoords="offset points", ha="center", fontsize=8,
                    color="steelblue")
    ax.set_ylim(-0.15, max(max(chp), max(ess)) * 1.25 or 1.0)
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title(f"Installed capacity vs {x_label}", fontsize=9, fontweight="bold")
    ax.legend(fontsize=8, loc="center right")

    panels = [
        (axes[0, 1], "Investment [100M KRW]", "invest_cost", "#6a51a3"),
        (axes[1, 0], "Expected OPEX [100M KRW]", "expected_op_cost", "darkorange"),
        (axes[1, 1], "CVaR of OPEX [100M KRW]", "cvar_op_cost", "tomato"),
    ]
    for ax_, ylabel, key, color in panels:
        ax_.plot(x, [(r.get(key, 0) or 0) * 1e-8 for r in rows], "o-", color=color,
                 lw=2, ms=7, markerfacecolor="white", markeredgewidth=2)
        ax_.set_ylabel(ylabel)
        ax_.set_title(f"{ylabel.split(' [')[0]} vs {x_label}", fontsize=9, fontweight="bold")

    for ax_ in axes.flatten():
        ax_.set_xlabel(x_label)
        ax_.set_xticks(x)
        ax_.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
