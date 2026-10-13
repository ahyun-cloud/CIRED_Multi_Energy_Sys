"""make_flowchart.py - 논문 Fig. 1 (방법론 흐름도) 생성.

현재 논문의 방법론(식 (1)–(8), rep24 기준 · MC100 검증, 연도 루프 없음)에 맞춘 개념도.
모델 결과를 읽지 않는 순수 도식이라 CPLEX·summary.json 불필요.
실행: py figures/make_flowchart.py
결과: outputs/paper/figs/fig1_flowchart.png (+ .pdf)
"""

# 프로젝트 루트를 import 경로·작업 디렉토리로 고정 — 어디서 실행해도
# `from src...` 와 outputs/·data/·scenarios/ 상대경로가 동작하도록.
import os
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path("outputs") / "paper" / "figs"
INK, GRAY = "#2B2B2B", "#6B6B6B"
C_IN, C_SC, C_OPT, C_OUT = "#5B7DB1", "#3E8E7E", "#C0392B", "#8C6D3F"   # 단계별 테두리색


def _box(ax, x, y, w, h, head, lines, color, fill="white", head_fs=8.2, fs=6.8, body_off=0.45):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.0,rounding_size=0.06",
                                fc=fill, ec=color, lw=1.6, zorder=2))
    ax.text(x + w / 2, y + h - 0.13, head, ha="center", va="top", fontsize=head_fs,
            fontweight="bold", color=color, zorder=3)
    ax.text(x + 0.10, y + h - body_off, "\n".join(lines), ha="left", va="top", fontsize=fs,
            color=INK, linespacing=1.45, zorder=3)


def _arrow(ax, p0, p1, color=GRAY):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=11,
                                 color=color, lw=1.4, zorder=1))


def main():
    with plt.rc_context({"font.family": "DejaVu Sans", "mathtext.fontset": "dejavusans"}):
        fig, ax = plt.subplots(figsize=(9.0, 3.4))
        ax.set_xlim(0, 9.0); ax.set_ylim(0, 3.4); ax.axis("off")
        H, Y = 2.9, 0.25

        _box(ax, 0.05, Y, 1.75, H, "Input data", [
            "Network",
            "• IEEE 33-bus feeder",
            "• DHN: 6 nodes, 5.1 km",
            "Measured profiles",
            "• KPX PV & load",
            "• KDHC heat demand",
            "Market & cost",
            "• KEPCO TOU tariff",
            "• SMP, FR reserve price",
            "• CAPEX, O&M, gas"], C_IN)

        _box(ax, 2.05, Y, 1.75, H, "Scenario generation", [
            "rep24 (base case)",
            "• 12 months ×",
            "  weekday/weekend",
            "• weight = days per year",
            "",
            "MC100 (robustness)",
            "• 100 sampled days",
            "• PV log-normal;",
            "  load, heat, SMP normal"], C_SC)

        # 2단계 MILP (가운데 큰 상자) - 안쪽에 Stage 1 / Stage 2 / Objective
        x0, w0 = 4.05, 2.95
        ax.add_patch(FancyBboxPatch((x0, Y), w0, H, boxstyle="round,pad=0.0,rounding_size=0.06",
                                    fc="#FBEDEB", ec=C_OPT, lw=1.6, zorder=1))
        ax.text(x0 + w0 / 2, Y + H - 0.13, "Two-stage stochastic CVaR MILP", ha="center",
                va="top", fontsize=8.6, fontweight="bold", color=C_OPT, zorder=3)
        _box(ax, x0 + 0.12, Y + 1.78, w0 - 0.24, 0.74, "Stage 1: investment", [
            "Siting & sizing of PV (3.3 MWp),",
            "ESS, CHP, TES, gas boilers"], C_OPT, head_fs=7.2, fs=6.6, body_off=0.34)
        _box(ax, x0 + 0.12, Y + 0.72, w0 - 0.24, 0.98, "Stage 2: hourly operation", [
            "Each scenario: power balance (3),",
            "LPF voltage & current (4)–(5),",
            "SOC (6), DHN heat balance (7)"], C_OPT, head_fs=7.2, fs=6.6, body_off=0.34)
        ax.text(x0 + w0 / 2, Y + 0.42,
                r"$\min\ C^{\mathrm{inv}} + \sum_s \pi_s C_s^{\mathrm{op}} + \lambda\,\mathrm{CVaR}_\alpha$",
                ha="center", va="center", fontsize=8.2, color=INK, zorder=3)
        ax.text(x0 + w0 / 2, Y + 0.13, "objective (1); CVaR (2), (8); solved with CPLEX",
                ha="center", va="center", fontsize=6.8, color=GRAY, zorder=3)
        _arrow(ax, (x0 + w0 / 2, Y + 1.78), (x0 + w0 / 2, Y + 1.70), C_OPT)

        _box(ax, 7.25, Y, 1.70, H, "Analysis", [
            "• Optimal plan (rep24)",
            "• Deterministic vs",
            "  rep24 vs MC100",
            "• Sensitivity to λ, α",
            "• ESS entry tests:",
            "  forced battery,",
            "  CAPEX, FR price"], C_OUT)

        ym = Y + H / 2
        for xa, xb in [(1.80, 2.05), (3.80, 4.05), (7.00, 7.25)]:
            _arrow(ax, (xa, ym), (xb, ym))

        OUT.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            fig.savefig(OUT / f"fig1_flowchart.{ext}", dpi=400, bbox_inches="tight",
                        facecolor="white")
        plt.close(fig)
    print(f"저장 → {OUT / 'fig1_flowchart.png'}")


if __name__ == "__main__":
    main()
