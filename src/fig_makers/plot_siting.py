"""plot_siting.py - 설치 결과(ESS/PV/CHP) 노드별 시각화."""

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt

from . import int_sites
import numpy as np


def _pad_xlim(ax, n_items, min_span=5):
    """막대 수가 적을 때(<3) x축을 대칭 확장해 막대가 과대해 보이지 않게.

    노드가 1~2개면 막대가 그래프 폭을 꽉 채워 '용량이 큰 것'처럼 오해되므로,
    중앙 정렬 + 여백을 둔다. 3개 이상이면 matplotlib 기본 자동범위를 유지한다.
    """
    if n_items >= 3:
        return
    center = (n_items - 1) / 2.0
    ax.set_xlim(center - min_span / 2.0, center + min_span / 2.0)


def plot_siting(results: dict, out_path, title="Siting result"):
    """ESS(출력·에너지)·PV·CHP/TES 용량을 노드별 막대로 (3-패널) 표시."""
    results = int_sites(results)          # summary.json 재사용 시 키가 문자열
    ess = results.get("ess_sites", {})
    pv = results.get("pv_sites", {})
    chp = results.get("chp_sites", {})

    fig, axes = plt.subplots(3, 1, figsize=(11, 10.5))

    # ── ESS ──
    ax = axes[0]
    if ess:
        nodes = sorted(ess.keys())
        x = np.arange(len(nodes))
        p = [ess[n]["P_MW"] for n in nodes]
        e = [ess[n]["E_MWh"] for n in nodes]
        ax.bar(x - 0.2, p, 0.4, label="P [MW]", color="steelblue")
        ax.bar(x + 0.2, e, 0.4, label="E [MWh]", color="darkorange")
        ax.set_xticks(x)
        ax.set_xticklabels([f"Bus{int(n) + 1}" for n in nodes], rotation=45, fontsize=8)
        _pad_xlim(ax, len(nodes))
        ax.legend()
    else:
        ax.text(0.5, 0.5, "No ESS installed", ha="center", transform=ax.transAxes)
    ax.set_ylabel("ESS capacity")
    ax.set_title(f"{title} — ESS ({results.get('total_P_MW', 0):.2f} MW / "
                 f"{results.get('total_E_MWh', 0):.2f} MWh)", fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")

    # ── PV ──
    ax = axes[1]
    if pv:
        nodes = sorted(pv.keys())
        x = np.arange(len(nodes))
        cap = [pv[n]["cap_MWp"] for n in nodes]
        ax.bar(x, cap, 0.6, color="tomato")
        ax.set_xticks(x)
        ax.set_xticklabels([f"Bus{int(n) + 1}" for n in nodes], rotation=45, fontsize=8)
        _pad_xlim(ax, len(nodes))
    else:
        ax.text(0.5, 0.5, "No PV installed", ha="center", transform=ax.transAxes)
    ax.set_ylabel("PV capacity [MWp]")
    ax.set_title(f"PV ({results.get('total_PV_MWp', 0):.2f} MWp, "
                 f"curtailment {results.get('curtailment_pct', 0):.1f}%)", fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")

    # ── CHP / TES ──
    ax = axes[2]
    if chp:
        nodes = sorted(chp.keys())
        x = np.arange(len(nodes))
        pe = [chp[n]["P_e_MW"] for n in nodes]
        tes = [chp[n]["E_tes_MWh"] for n in nodes]
        ax.bar(x - 0.2, pe, 0.4, label="CHP $P_e$ [MW]", color="seagreen")
        ax.bar(x + 0.2, tes, 0.4, label="TES E [MWh]", color="mediumpurple")
        ax.set_xticks(x)
        ax.set_xticklabels([f"Bus{int(n) + 1}" for n in nodes], rotation=45, fontsize=8)
        _pad_xlim(ax, len(nodes))
        ax.legend()
    else:
        ax.text(0.5, 0.5, "No CHP installed", ha="center", transform=ax.transAxes)
    ax.set_ylabel("CHP / TES capacity")
    ax.set_title(f"CHP ({results.get('total_CHP_MW', 0):.2f} MW$_e$) + "
                 f"TES ({results.get('total_TES_MWh', 0):.2f} MWh)", fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
