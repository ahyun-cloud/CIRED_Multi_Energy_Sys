"""plot_scenarios.py - 시나리오 프로파일 시각화 (PV·부하·요금·열)."""

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
import numpy as np


def plot_scenarios(scenario: dict, out_path, chp_enabled=True):
    """24시간 시나리오 프로파일 (전 시나리오 옅게 + 확률가중 평균 굵게)."""
    hours = np.arange(24)
    probs = np.asarray(scenario["probs"])[:, None]

    panels = [
        ("pv", "Normalized PV output [-]", "tomato"),
        ("load", "Normalized electric load [-]", "steelblue"),
        ("price_im", "Import price [KRW/kWh]", "seagreen"),
    ]
    if chp_enabled and "heat" in scenario:
        panels.append(("heat", "Normalized heat demand [-]", "darkorange"))

    n = len(panels)
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 7.0))
    axes = axes.flatten()

    for ax, (key, ylabel, color) in zip(axes, panels):
        arr = np.asarray(scenario[key])
        for s in range(arr.shape[0]):
            ax.plot(hours, arr[s], color=color, alpha=0.12, lw=0.8)
        ax.plot(hours, (arr * probs).sum(axis=0), color=color, lw=2.4,
                label="Prob.-weighted mean")
        ax.set_xlabel("Hour [h]")
        ax.set_ylabel(ylabel)
        ax.set_xticks(range(0, 24, 6))
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)

    for ax in axes[n:]:                 # 패널 수 < 4 이면 빈 칸 숨김
        ax.axis("off")

    fig.suptitle(f"Scenario profiles (S={len(scenario['probs'])})", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
