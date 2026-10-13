"""plot_poster.py - 포스터용 핵심결과 2x2 그림.

논문 Fig. 6·7 은 λ 4패널 + α 4패널 = 8패널이라 포스터에 둘 다 싣기 어렵다.
핵심 주장만 남겨 한 장으로 합친다. 재풀이 없이 기존 결과만 읽는다.

    (a) λ 민감도 · 설비        (b) 결정론 → rep24 → MC100 · 설비
    (c) λ 민감도 · 비용        (d) α 민감도 · 비용

─ 형태 ────────────────────────────────────────────────────────────
설비 패널은 **막대**, 비용 패널은 **꺾은선**이다. λ∈{0, 0.5, 1, 2}·α·시나리오
집합은 이산적 설계 선택이지 연속 변수가 아니라, 꺾은선으로 그리면 점 사이를
보간해도 되는 것처럼 보인다. 또 λ 축을 선형으로 두면 1.0→2.0 이 0.5→1.0 의 두
배로 벌어져 평탄 구간이 실제보다 길어 보인다 → 전 패널 x축을 범주형 등간격으로
둔다. 반면 비용 패널은 추세 자체가 메시지라 선을 쓴다.

(b) 는 CHP[MW] 와 TES[MWh_th] 로 단위가 달라 **2축을 쓰지 않고 small multiples**
(나란한 두 작은 패널)로 쪼갠다. 2축 그래프는 두 계열의 높이를 눈으로 비교하게
만들어 실제로는 없는 관계를 읽히게 한다 — 축척을 어떻게 잡느냐로 결론이 바뀌는
형태라 포스터에서는 특히 위험하다.

ESS 는 전 케이스 0 이라 막대로 그리면 아무것도 안 그려진다 — 계열로 넣는 대신
글상자로 명시한다. 포스터에서는 보이지 않는 0 막대보다 글자가 읽힌다.

─ 색 ──────────────────────────────────────────────────────────────
검증된 범주형 슬롯에서 고르고 CVD·명도 게이트를 통과시킨 조합만 쓴다
(OKLab ΔE×100, Machado 2009 severity 1.0, all-pairs 기준):

    막대  CHP #008300 · TES #1baf7a      CVD ΔE 15.2 / normal 15.6
    선    Investment #2a78d6 · Expected OPEX #4a3aa7 · CVaR #e34948
                                        CVD ΔE 13.0 / normal 16.3
    두 차트 간 최악 쌍도 normal ΔE 24.0 으로 떨어져 있다.

TES 의 aqua 는 흰 표면 대비 2.74:1 로 3:1 미만이라 'relief' 대상인데, 막대마다
값을 직접 적는 것으로 해소한다. 숫자·축·범례 글자는 계열 색이 아니라 잉크 색을
쓴다 — 색은 마크가 지고 글자는 읽히기만 하면 된다.

그림 라벨은 영문(영문 논문·포스터).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

#: 검증 통과 팔레트 — 계열(entity)에 고정, 순위에 따라 바뀌지 않는다
C_CHP = "#008300"      # green
C_TES = "#1baf7a"      # aqua
C_INV = "#2a78d6"      # blue
C_EOPEX = "#4a3aa7"    # violet
C_CVAR = "#e34948"     # red

#: 표면·잉크 토큰 (글자는 계열 색을 입지 않는다)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e3e2de"

#: 포스터는 멀리서 본다 — 논문용보다 글자를 키운다
FS_TITLE, FS_LAB, FS_TICK, FS_LEG, FS_VAL = 12.0, 11.0, 10.5, 10.5, 10.0


def _style(ax):
    """격자·축을 뒤로 물린다 — 데이터가 앞에 오도록."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=FS_TICK, length=0)


def _bars(ax, labels, vals, color, ylabel, title, fmt="{:.2f}"):
    """범주형 막대 + 막대마다 값 직접 표기(저대비 색의 relief 수단)."""
    xs = np.arange(len(labels))
    # 막대는 얇게 — 두꺼운 채도 블록은 멀리서 "덩어리"로만 읽히고 여백을 잡아먹는다
    bars = ax.bar(xs, vals, width=0.46, color=color,
                  edgecolor=SURFACE, lw=2.0)                 # 2px 표면 간격
    for b in bars:
        ax.annotate(fmt.format(b.get_height()),
                    xy=(b.get_x() + b.get_width() / 2, b.get_height()),
                    xytext=(0, 4), textcoords="offset points", ha="center",
                    va="bottom", fontsize=FS_VAL, color=INK, fontweight="bold")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, max(max(vals), 1e-9) * 1.38)
    ax.set_ylabel(ylabel, fontsize=FS_LAB, color=INK2)
    if title:
        ax.set_title(title, fontsize=FS_TITLE, fontweight="bold", color=INK)
    _style(ax)
    return bars


def _ess_note(ax, text, pos=(0.5, 0.91)):
    """ESS = 0 은 막대가 안 보이므로 글상자로 밝힌다 (잉크 색)."""
    ax.annotate(text, xy=pos, xycoords="axes fraction", ha="center",
                va="center", fontsize=FS_LEG, color=INK2,
                bbox=dict(boxstyle="round,pad=0.32", fc=SURFACE, ec=GRID,
                          lw=1.4))


def _cost_panel(ax, xvals, series, base_i, x_label, title, ylim):
    """기준 케이스 대비 **상대변화 [%]** — 절대값 축은 오독을 부른다.

    투자비는 λ 전 구간 ±2 %, α 전 구간 ±0.13 % 밖에 안 움직이는데 축을 자동으로
    맞추면 그 변화가 화면을 가로지르는 급등으로 그려진다. 포스터는 축을 읽지
    않고 모양만 보는 매체라 "투자가 폭증한다"로 오독된다. 세 지표를 같은 % 축
    (두 패널 공통 범위)에 올려 과장을 없애고 크기 비교도 되게 한다.

    마커 모양(o·s·^)을 계열마다 다르게 둬 색 말고도 구분되게 한다.
    """
    xs = np.arange(len(xvals))
    handles = []
    for label, vals, color, marker in series:
        base = vals[base_i]
        h, = ax.plot(xs, [(v - base) / base * 100.0 for v in vals],
                     marker=marker, ls="-", color=color, lw=2.0, ms=8.0,
                     markerfacecolor=SURFACE, markeredgewidth=2.0, label=label)
        handles.append(h)
    ax.axhline(0, color=INK2, lw=1.0, ls=(0, (2, 3)), zorder=1)
    ax.annotate("base case", xy=(xs[base_i], 0), xytext=(0, -16),
                textcoords="offset points", ha="center", fontsize=9.0,
                color=INK2)
    ax.set_ylim(*ylim)
    ax.set_xlim(-0.35, len(xvals) - 0.65)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{v:g}" for v in xvals])
    ax.set_xlabel(x_label, fontsize=FS_LAB, color=INK2)
    ax.set_ylabel("Change from base case [%]", fontsize=FS_LAB, color=INK2)
    ax.set_title(title, fontsize=FS_TITLE, fontweight="bold", color=INK)
    _style(ax)
    return handles


def plot_poster_sensitivity(lam_rows, alp_rows, scen, out_path,
                            title="Robustness of the planning decision"):
    """포스터용 2x2. lam/alp_rows 는 make_sensitivity_figs 형식,
    scen 은 [{label, short, total_CHP_MW, total_TES_MWh}, ...] 순서대로."""
    def col(rows, key):
        return [(r.get(key, 0) or 0) for r in rows]

    lam_x, alp_x = col(lam_rows, "lambda"), col(alp_rows, "alpha")
    s_short = [s["short"] for s in scen]

    # 한글 폰트에 의존하지 않는다 — Malgun 유무로 그림이 달라지지 않도록
    with plt.rc_context({"font.family": "DejaVu Sans",
                         "axes.unicode_minus": False,
                         "axes.edgecolor": GRID, "text.color": INK}):
        fig = plt.figure(figsize=(9.2, 6.8), facecolor=SURFACE)
        gs = fig.add_gridspec(2, 4, hspace=0.48, wspace=0.44,
                              left=0.075, right=0.985, top=0.885, bottom=0.205)
        ax_a = fig.add_subplot(gs[0, 0:2])
        ax_b1 = fig.add_subplot(gs[0, 2])
        ax_b2 = fig.add_subplot(gs[0, 3])
        ax_c = fig.add_subplot(gs[1, 0:2])
        ax_d = fig.add_subplot(gs[1, 2:4])

        # ── (a) λ 별 CHP ────────────────────────────────────
        _bars(ax_a, [f"{v:g}" for v in lam_x], col(lam_rows, "total_CHP_MW"),
              C_CHP, "CHP capacity [MW]",
              "(a) Sizing vs risk weight λ")
        ax_a.set_xlabel("risk weight λ", fontsize=FS_LAB, color=INK2)
        _ess_note(ax_a, "ESS = 0 for every λ")

        # ── (b) 시나리오 집합 — 2축 대신 small multiples ────
        _bars(ax_b1, s_short, [s["total_CHP_MW"] for s in scen], C_CHP,
              "CHP [MW]", "")
        _bars(ax_b2, s_short, [s["total_TES_MWh"] for s in scen], C_TES,
              "TES [MWh_th]", "", fmt="{:.1f}")
        for ax in (ax_b1, ax_b2):
            ax.set_xlabel("scenario set size S", fontsize=9.5, color=INK2)
            ax.tick_params(axis="x", labelsize=9.5)
        # 두 작은 패널을 묶는 머리글 (패널 제목은 각각 CHP·TES)
        box = ax_b1.get_position().bounds, ax_b2.get_position().bounds
        xmid = (box[0][0] + box[1][0] + box[1][2]) / 2
        fig.text(xmid, 0.905, "(b) Sizing vs scenario set size",
                 ha="center", va="bottom", fontsize=FS_TITLE,
                 fontweight="bold", color=INK)
        _ess_note(ax_b2, "ESS = 0", pos=(0.5, 0.93))

        # ── (c)(d) 비용 — 기준 케이스(λ=0.5, α=0.95) 대비 ───
        def cost_series(rows):
            return [("Investment", col(rows, "invest_cost"), C_INV, "o"),
                    ("Expected OPEX", col(rows, "expected_op_cost"), C_EOPEX, "s"),
                    ("CVaR of OPEX", col(rows, "cvar_op_cost"), C_CVAR, "^")]

        lam_base = min(range(len(lam_x)), key=lambda i: abs(lam_x[i] - 0.5))
        alp_base = min(range(len(alp_x)), key=lambda i: abs(alp_x[i] - 0.95))
        ylim = (-2.9, 1.9)                    # 두 패널 공통 — 크기 비교가 되도록
        handles = _cost_panel(ax_c, lam_x, cost_series(lam_rows), lam_base,
                              "risk weight λ",
                              "(c) Cost vs risk weight λ", ylim)
        _cost_panel(ax_d, alp_x, cost_series(alp_rows), alp_base,
                    "CVaR confidence α",
                    "(d) Cost vs CVaR confidence α", ylim)

        # 비용 두 패널이 공유하는 범례 하나 (패널마다 두면 데이터를 가린다)
        fig.legend(handles, [h.get_label() for h in handles], ncol=3,
                   loc="lower center", bbox_to_anchor=(0.5, 0.068),
                   frameon=False, fontsize=FS_LEG, handlelength=2.0,
                   columnspacing=2.4, labelcolor=INK2)

        fig.suptitle(title, fontsize=13.5, fontweight="bold", color=INK, y=0.975)
        note = chr(10).join([
            "(a)(c)(d): siting fixed to the cired_rep24 solution, sizing "
            "re-optimised. Base case λ = 0.5, α = 0.95.",
            "(b): siting and sizing re-optimised for each scenario set."])
        fig.text(0.5, 0.008, note, ha="center", va="bottom", fontsize=8.6,
                 color=INK2, linespacing=1.4)

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=400, facecolor=SURFACE)
        fig.savefig(out_path.with_suffix(".pdf"), facecolor=SURFACE)
        plt.close(fig)
    return out_path
