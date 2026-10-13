"""plot_network_layered.py - 2-layer electricity-heat integrated system schematic.

레퍼런스(HE-IES) 스타일 개념도. 하단은 IEEE 33-bus 전력망, 상단은 **모델에 실제로 들어간
DHN**(6노드·5배관, DHN_PIPE_DATA)만 그린다. 설비가 설치된 노드는 **채워진 원(●)**,
열 후보 노드 중 미설치는 빈 원(○).
층 사이 gap 에 변환·저장 설비(CHP / Gas boiler / TES) chip 을 두고 가스·전기·열 벡터 화살표로 연결.

물리 정합: 전기↔열 결합은 CHP(가스→전기+열). Gas boiler=열전용, TES=열저장.
  (열수요·DH 는 표시된 노드에 모델링 — docs/ASSUMPTIONS.md 의 stylized overlay. 캡션 명시 권장.)
라벨 영문. 폰트는 rc_context 로 이식성 고정.
"""
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import int_sites
from matplotlib.patches import Polygon, Circle, FancyArrowPatch, FancyBboxPatch
import numpy as np

from src.data_process.network import (
    LINE_DATA, NUM_NODES, SLACK_BUS, CHP_CANDIDATE_NODES, DHN_PIPE_DATA,
)
from src.fig_makers.plot_network import _layout_from_edges


def _adjacency():
    adj = defaultdict(list)
    for line in LINE_DATA:
        a, b = int(line[0]), int(line[1])
        adj[a].append(b)
        adj[b].append(a)
    return adj


def _bus_perp(n, pos, adj):
    """노드 n 의 피더에 수직인 평면방향(버스바 방향) 단위벡터."""
    vs = []
    for m in adj[n]:
        dx, dy = pos[m][0] - pos[n][0], pos[m][1] - pos[n][1]
        d = (dx * dx + dy * dy) ** 0.5 or 1.0
        vs.append((dx / d, dy / d))
    if not vs:
        return 0.0, 1.0
    sx, sy = sum(v[0] for v in vs), sum(v[1] for v in vs)
    mag = (sx * sx + sy * sy) ** 0.5
    fx, fy = (vs[0] if mag < 1e-6 else (sx / mag, sy / mag))   # 직진노드는 피더에 수직
    return -fy, fx

# ── palette ───────────────────────────────────────────────
_ELEC  = "#2C5F8A"     # electricity vector / electric network
_HEAT  = "#C0392B"     # heat vector / heat network
_GAS   = "#8C6D3F"     # gas (fuel) vector
_CHP   = "#E07B00"
_TES   = "#117A65"
_DOT_E = "#8FB3D4"     # non-resource electric bus
_DOT_H = "#E2A6A0"     # non-resource heat bus
_INK   = "#2B2B2B"
_GRAY  = "#9A9A9A"
_ELEC_FILL = "#DCE9F5"
_HEAT_FILL = "#F7ECCD"

# ── isometric projection ──────────────────────────────────
_A = 0.55
_B = 0.30
_ZGAP = 6.8
_ANG = float(np.degrees(np.arctan2(_B, _A)))


def _iso(x, y, z):
    return x + _A * y, _B * y + z


def _plane(ax, xs, ys, z, fc, ec):
    padx, pady = 1.4, 1.4
    x0, x1 = min(xs) - padx, max(xs) + padx
    y0, y1 = min(ys) - pady, max(ys) + pady
    corners = [_iso(x0, y0, z), _iso(x1, y0, z), _iso(x1, y1, z), _iso(x0, y1, z)]
    ax.add_patch(Polygon(corners, closed=True, fc=fc, ec=ec, lw=1.5,
                         alpha=0.5, zorder=z * 10, joinstyle="round"))
    return x0, x1, y0, y1


def _network(ax, pos, adj, z, line_color, installed, fill_color):
    """한 평면에 33-bus 피더 + 모든 버스의 bus-bar(짝대기) + 설치노드 채운 원."""
    zb = z * 10
    for line in LINE_DATA:
        i, j = int(line[0]), int(line[1])
        p1, p2 = _iso(*pos[i], z), _iso(*pos[j], z)
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=line_color, lw=1.4,
                zorder=zb + 2, solid_capstyle="round", alpha=0.85)
    L = 0.30                                     # bus-bar 반길이(평면단위)
    for n in range(NUM_NODES):
        px, py = _bus_perp(n, pos, adj)
        a = _iso(pos[n][0] + px * L, pos[n][1] + py * L, z)
        b = _iso(pos[n][0] - px * L, pos[n][1] - py * L, z)
        ax.plot([a[0], b[0]], [a[1], b[1]], color=line_color, lw=1.8,
                solid_capstyle="butt", zorder=zb + 3)         # 모든 버스 표시
        sx, sy = _iso(*pos[n], z)
        if n == SLACK_BUS and z == 0.0:
            ax.add_patch(Polygon([(sx, sy + 0.22), (sx + 0.22, sy),
                                  (sx, sy - 0.22), (sx - 0.22, sy)],
                         closed=True, fc="white", ec=_INK, lw=1.6, zorder=zb + 6))
        elif n in installed:
            ax.add_patch(Circle((sx, sy), 0.16, fc=fill_color, ec="white",
                                lw=1.1, zorder=zb + 5))


# DHN 노드 라벨 위치 (0-indexed 노드 → (dx, dy, ha, va)). Bus 7·8·24·25 가 붙어 있어 수동 배치.
_DHN_NODE_LBL = {6: (-0.32, 0.0, "right", "center"), 7: (0.30, -0.30, "left", "top"),
                 23: (-0.30, 0.30, "right", "bottom"), 24: (0.10, 0.34, "left", "bottom"),
                 29: (0.0, -0.36, "center", "top"), 31: (0.0, -0.36, "center", "top")}


def _dhn(ax, pos, z, installed):
    """열 평면에 실제 DHN 배관(DHN_PIPE_DATA)과 노드만 그린다. 노드 라벨은 1-indexed Bus 번호."""
    zb = z * 10
    for i, j, _km in DHN_PIPE_DATA:   # 구간 길이는 좁아서 생략, 총연장은 층 라벨에 표기
        i, j = int(i), int(j)
        p1, p2 = _iso(*pos[i], z), _iso(*pos[j], z)
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=_HEAT, lw=3.0,
                zorder=zb + 2, solid_capstyle="round")
    for n in CHP_CANDIDATE_NODES:
        sx, sy = _iso(*pos[n], z)
        filled = n in installed
        ax.add_patch(Circle((sx, sy), 0.22, fc=_HEAT if filled else "white",
                            ec=_HEAT, lw=1.8, zorder=zb + 5))
        dx, dy, ha, va = _DHN_NODE_LBL.get(n, (0.0, -0.36, "center", "top"))
        ax.text(sx + dx, sy + dy, f"Bus {n + 1}", fontsize=8.5, color=_INK,
                ha=ha, va=va, zorder=zb + 7)


def _chip(ax, cx, cy, w, h, label, ec):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                 boxstyle="round,pad=0.02,rounding_size=0.14",
                 fc="white", ec=ec, lw=2.0, zorder=500, mutation_aspect=0.9))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=10.5,
            fontweight="bold", color=_INK, zorder=501)


def _arrow(ax, p0, p1, color, both=False, lw=1.7, z=450):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="<|-|>" if both else "-|>",
                 mutation_scale=12, color=color, lw=lw, zorder=z,
                 shrinkA=3, shrinkB=3, joinstyle="round"))


def plot_network_layered(results, out_path,
                         title="Integrated electricity–heat energy system", dpi=160):
    results = results or {}
    pos, _, _ = _layout_from_edges()
    xs = [pos[n][0] for n in pos]
    ys = [pos[n][1] for n in pos]
    results = int_sites(results)          # summary.json 재사용 시 키가 문자열
    pv, ess, chp = (results.get("pv_sites", {}), results.get("ess_sites", {}),
                    results.get("chp_sites", {}))
    e_inst = set(pv) | set(ess)
    h_inst = set(chp)

    with plt.rc_context({"font.family": "DejaVu Sans", "axes.unicode_minus": False}):
        fig, ax = plt.subplots(figsize=(13, 11))

        # planes
        hx0, hx1, hy0, hy1 = _plane(ax, xs, ys, _ZGAP, _HEAT_FILL, _HEAT)
        ex0, ex1, ey0, ey1 = _plane(ax, xs, ys, 0.0, _ELEC_FILL, _ELEC)
        # 하단: 33-bus 전력망 / 상단: 실제 DHN(6노드·5배관)
        adj = _adjacency()
        _dhn(ax, pos, _ZGAP, h_inst)
        _network(ax, pos, adj, 0.0, _ELEC, e_inst, _ELEC)

        # layer labels (left, outside plane, along tilt)
        for (x0, y0, z, txt, clr) in [
                (hx0, hy0, _ZGAP, f"District heating network ({len(CHP_CANDIDATE_NODES)} nodes, "
                 f"{DHN_PIPE_DATA[:, 2].sum():.1f} km)", _HEAT),
                (ex0, ey0, 0.0, "Electric power system (IEEE 33-bus)", _ELEC)]:
            lx, ly = _iso(x0, y0, z)
            ax.text(lx - 0.35, ly - 0.2, txt, fontsize=12, fontweight="bold",
                    color=clr, rotation=_ANG, rotation_mode="anchor",
                    ha="right", va="top", zorder=600)

        # coupling: dotted vertical connectors at heat(CHP) nodes
        for n in CHP_CANDIDATE_NODES:
            b, t = _iso(*pos[n], 0.18), _iso(*pos[n], _ZGAP - 0.18)
            ax.plot([b[0], t[0]], [b[1], t[1]], color=_GRAY, lw=0.9,
                    ls=(0, (2, 3)), zorder=3, alpha=0.7)

        # device chips in the gap
        gap_cy = _ZGAP / 2 + _B * (max(ys) + min(ys)) / 2
        cx_mid = _A * (max(ys) + min(ys)) / 2 + (max(xs) + min(xs)) / 2
        chips = [(cx_mid - 4.4, "CHP", _CHP),
                 (cx_mid,        "Gas boiler", _GAS),
                 (cx_mid + 4.4,  "TES", _TES)]
        cw, ch = 2.7, 0.9
        for cx, lbl, ec in chips:
            _chip(ax, cx, gap_cy, cw, ch, lbl, ec)
        chp_cx, boil_cx, tes_cx = (c[0] for c in chips)

        c0 = CHP_CANDIDATE_NODES[1]
        e_anc, h_anc = _iso(*pos[c0], 0.25), _iso(*pos[c0], _ZGAP - 0.25)
        _arrow(ax, (chp_cx - 0.5, gap_cy + ch / 2), h_anc, _HEAT)   # heat up
        _arrow(ax, (chp_cx - 0.5, gap_cy - ch / 2), e_anc, _ELEC)   # elec down
        _arrow(ax, (boil_cx, gap_cy + ch / 2), (boil_cx, h_anc[1] - 0.3), _HEAT)
        _arrow(ax, (tes_cx, gap_cy + ch / 2), (tes_cx, h_anc[1] - 0.3), _HEAT, both=True)
        gas_y = gap_cy - ch / 2 - 0.85
        ax.plot([chp_cx, boil_cx], [gas_y, gas_y], color=_GAS, lw=2.2, zorder=440)
        for cx in (chp_cx, boil_cx):
            _arrow(ax, (cx, gas_y), (cx, gap_cy - ch / 2 - 0.02), _GAS)
        ax.text(boil_cx + 0.55, gas_y, "Gas supply", color=_GAS, fontsize=9,
                fontweight="bold", va="center", ha="left", zorder=441)

        # legend (reserved lower-right, outside planes)
        handles = [
            plt.Line2D([], [], marker="o", ls="", markersize=10, markerfacecolor=_HEAT,
                       markeredgecolor="white", label="Heat source (CHP/TES installed)"),
            plt.Line2D([], [], marker="o", ls="", markersize=10, markerfacecolor="white",
                       markeredgecolor=_HEAT, label="DHN node (heat demand)"),
            plt.Line2D([], [], marker="o", ls="", markersize=10, markerfacecolor=_ELEC,
                       markeredgecolor="white", label="Electric resource node"),
            plt.Line2D([], [], color=_ELEC, lw=2.4, label="Electricity"),
            plt.Line2D([], [], color=_HEAT, lw=2.4, label="Heat"),
            plt.Line2D([], [], color=_GAS, lw=2.4, label="Gas (fuel)")]
        # 범례를 전력망 아래(하단 여백)에 가로로 배치 → 계통과 겹침 방지
        ax.legend(handles=handles, loc="lower right", ncol=3, fontsize=9.5,
                  framealpha=0.96, borderpad=0.7, columnspacing=1.3,
                  handletextpad=0.5, bbox_to_anchor=(1.0, 0.0))

        # reserved zones: title (top), labels (left), legend (하단)
        sxmin = ex0 + _A * ey0 - 0.3
        sxmax = hx1 + _A * hy1 + 0.3
        symin = _B * ey0 - 3.6
        symax = _ZGAP + _B * hy1
        ax.set_xlim(sxmin - 3.0, sxmax + 0.5)
        ax.set_ylim(symin, symax + 1.9)
        if title:
            ax.text(cx_mid + 1.5, symax + 1.0, title, ha="center", va="center",
                    fontsize=15, fontweight="bold", color=_INK)

        ax.set_aspect("equal")
        ax.axis("off")
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)
    return out_path
