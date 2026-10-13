"""make_flowchart.py - 논문 Fig. 1 (방법론 흐름도) 생성.

기존 논문 Fig. 1(TikZ 스타일: Start → Input → Scenario → Optimization 묶음 → Analysis → End)의
모양·배치를 유지하고, 현재 방법론에 맞지 않던 부분만 고친 버전.
  - 2030–2050 연도 루프(Year y, y = 2050?) 삭제 — 연도 분석은 결론의 future work
  - ESS value decomposition 상자 삭제
  - 식 번호를 논문 식 (1)–(8)에 맞춤
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
from matplotlib.patches import FancyBboxPatch, Polygon

OUT = Path("outputs") / "paper" / "figs"
INK, EDGE, ARROW = "#1A1A1A", "#1A1A1A", "#555555"
OPT_EC, OPT_FC, OPT_TXT = "#4CAF50", "#EAF7E6", "#2E7D32"     # Optimization 묶음 (기존 녹색)
ANA_EC, ANA_FC, ANA_TXT = "#9FA8DA", "#EEF0FA", "#1A237E"     # Analysis 묶음 (기존 남색)
W, H = 12.0, 4.53                                             # 논문 그림틀 비율(2.65)에 맞춤


def box(ax, cx, cy, w, h, title, body, fs=7.6, tfs=7.8):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                 boxstyle="round,pad=0,rounding_size=0.07", fc="white", ec=EDGE, lw=1.1, zorder=3))
    ax.text(cx, cy + h / 2 - 0.12, title, ha="center", va="top", fontsize=tfs,
            fontweight="bold", color=INK, zorder=4)
    ax.text(cx, cy + h / 2 - 0.34, body, ha="center", va="top", fontsize=fs,
            color=INK, linespacing=1.3, zorder=4)


def oval(ax, cx, cy, label):
    ax.add_patch(FancyBboxPatch((cx - 0.38, cy - 0.15), 0.76, 0.30,
                 boxstyle="round,pad=0,rounding_size=0.15", fc="#EFEFEF", ec=EDGE, lw=1.1, zorder=3))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=7.8, color=INK, zorder=4)


def group(ax, x0, y0, x1, y1, label, ec, fc, tc):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                 boxstyle="round,pad=0,rounding_size=0.12", fc=fc, ec=ec, lw=1.1,
                 ls=(0, (4, 3)), zorder=1))
    ax.text((x0 + x1) / 2, y1 + 0.08, label, ha="center", va="bottom", fontsize=10,
            fontweight="bold", color=tc, zorder=2)


def arrow(ax, pts):
    """꺾은선 화살표: pts = [(x, y), ...], 마지막 점에 화살촉."""
    xs, ys = zip(*pts)
    ax.plot(xs[:-1] + (xs[-1],), ys[:-1] + (ys[-1],), color=ARROW, lw=1.1, zorder=2)
    ax.annotate("", xy=pts[-1], xytext=pts[-2],
                arrowprops=dict(arrowstyle="-|>", color=ARROW, lw=1.1, mutation_scale=10),
                zorder=2)


def main():
    rc = {"font.family": "DejaVu Sans", "mathtext.fontset": "cm"}
    with plt.rc_context(rc):
        fig = plt.figure(figsize=(W, H))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")

        # ── Start → Input data (평행사변형) ─────────────────────
        oval(ax, 1.65, 3.95, "Start")
        px, py, pw, ph, sk = 1.65, 2.55, 2.85, 1.35, 0.20
        ax.add_patch(Polygon([(px - pw / 2 + sk, py + ph / 2), (px + pw / 2 + sk, py + ph / 2),
                              (px + pw / 2 - sk, py - ph / 2), (px - pw / 2 - sk, py - ph / 2)],
                             closed=True, fc="#F7F7F7", ec=EDGE, lw=1.1, zorder=3))
        ax.text(px - pw / 2 + 0.28, py + ph / 2 - 0.10, "Input Data:", ha="left", va="top",
                fontsize=6.8, fontweight="bold", color=INK, zorder=4)
        ax.text(px - pw / 2 + 0.22, py + ph / 2 - 0.28,
                "• IEEE 33-bus system + DHN (6 nodes, 5.1 km)\n"
                "• Candidate nodes, capacity limits, costs\n"
                "   (PV, ESS, CHP, TES, Boiler, DHN)\n"
                "• Measured profiles (KPX PV/load, KDHC heat)\n"
                "• Uncertainty parameters (PV, demand,\n"
                "   heat, SMP $\\sigma$)\n"
                "• KEPCO TOU tariff, SMP, FR reserve price",
                ha="left", va="top", fontsize=6.0, color=INK, linespacing=1.25, zorder=4)
        arrow(ax, [(1.65, 3.80), (1.65, py + ph / 2)])

        # ── Scenario generation ─────────────────────────────
        sx, sy = 4.20, 2.55
        box(ax, sx, sy, 1.75, 0.95, "Scenario Generation",
            "Representative\n24 days (rep24) /\nMonte Carlo (MC100)")
        arrow(ax, [(px + pw / 2, py), (sx - 0.875, sy)])

        # ── Optimization 묶음 ───────────────────────────────
        ox = 6.95
        group(ax, ox - 1.70, 0.30, ox + 1.70, 3.98, "Optimization", OPT_EC, OPT_FC, OPT_TXT)
        box(ax, ox, 3.22, 3.10, 1.18, "Two-stage stochastic CVaR MILP",
            r"$\min\ C_{\mathrm{inv}} + \sum_s \pi_s\, C_{\mathrm{op},s} + \lambda\cdot\mathrm{CVaR}_{\alpha}$",
            fs=8.0)
        ax.text(ox, 3.22 - 0.07, "s.t.  Power balance (3), Voltage & current (4)–(5),\n"
                "SOC (6), DHN (7), CVaR (2), (8)", ha="center", va="top", fontsize=6.8,
                color=INK, linespacing=1.3, zorder=4)
        box(ax, ox, 1.95, 3.10, 0.62, "Solve (CPLEX)", "Solve MILP")
        box(ax, ox, 0.95, 3.10, 0.80, "Optimal Siting & Sizing",
            "Node-wise location & capacity of\nPV, ESS, CHP, TES, Boiler")
        arrow(ax, [(sx + 0.875, sy), (5.16, sy), (5.16, 3.22), (ox - 1.55, 3.22)])
        arrow(ax, [(ox, 3.22 - 0.59), (ox, 1.95 + 0.31)])
        arrow(ax, [(ox, 1.95 - 0.31), (ox, 0.95 + 0.40)])

        # ── Analysis 묶음 ───────────────────────────────────
        ax_ = 10.45
        group(ax, ax_ - 1.40, 1.15, ax_ + 1.40, 3.15, "Analysis", ANA_EC, ANA_FC, ANA_TXT)
        box(ax, ax_, 2.15, 2.50, 1.45, "Results & Analysis",
            "Optimal siting & sizing (rep24)\n"
            "Cost breakdown (investment,\nexpected OPEX, CVaR)\n"
            "Deterministic vs rep24 vs MC100\n"
            "Sensitivity to $\\lambda$ and $\\alpha$\n"
            "ESS entry conditions", fs=7.2)
        arrow(ax, [(ox + 1.55, 0.95), (8.85, 0.95), (8.85, 2.15), (ax_ - 1.25, 2.15)])

        # ── End ────────────────────────────────────────────
        oval(ax, ax_, 0.45, "End")
        arrow(ax, [(ax_, 1.15), (ax_, 0.60)])

        OUT.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            fig.savefig(OUT / f"fig1_flowchart.{ext}", dpi=400, facecolor="white")
        plt.close(fig)
    print(f"저장 → {OUT / 'fig1_flowchart.png'}")


if __name__ == "__main__":
    main()
