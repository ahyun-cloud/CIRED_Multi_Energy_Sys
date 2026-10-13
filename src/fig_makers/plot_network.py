"""plot_network.py - IEEE 33-bus 단선도 + 설치 자원(PV/ESS/CHP/TES) — 글리프+표 스타일.

출판용 단순화 설계 (한 노드 다중설비 난잡함 해결):
  - 계통도(좌): 노드마다 자원을 아이콘 여러 개로 흩뿌리지 않고, **도넛 글리프 1개**로
    표현(부채꼴 색=설치 자원 종류). 비설치 노드는 작은 점.
  - 용량 표(우): 노드별 정확한 용량 수치를 **표로 분리**(그림은 위치, 표는 수치).
레이아웃 좌표(_layout_from_edges)는 plot_network_layered 도 공유하므로 유지한다.
"""

from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt

from . import int_sites
from matplotlib.patches import Wedge, Circle, Polygon, Rectangle
import numpy as np

from src.data_process.network import (
    LINE_DATA, NUM_NODES, SLACK_BUS, PEAK_LOAD_MW, BASE_KV, DHN_PIPE_DATA,
)

# 라테랄 y-레벨
_LATERAL_LEVELS = [-2.7, 3.4, 2.0, -4.2, 4.8]

# 자원 색 (글리프 부채꼴 / 표 헤더 공통)
_GOLD = "#E8A800"      # PV
_GREEN = "#2EA043"     # ESS
_ORANGE = "#E07B00"    # CHP
_TEAL = "#117A65"      # TES
_NODE = "#34699A"      # 비설치 버스 점
_GRAY = "#3A3A3A"
_LGRAY = "#9aa0a6"
_HEAT = "#C0392B"      # DHN 열배관
_INK = "#2B2B2B"


def _layout_from_edges():
    """실제 LINE_DATA 연결로부터 단선도 좌표를 계산 (데이터 충실).

    - 본선(trunk) = slack 에서 가장 먼 경로 → 수평 배치
    - 각 lateral(본선에서 분기한 체인) → attach x 기준 수직 오프셋으로 수평 배치
    Returns: (pos {idx:(x,y)}, trunk [idx...], laterals [{'chain':[...], 'y':float}])
    """
    adj = defaultdict(list)
    for line in LINE_DATA:
        a, b = int(line[0]), int(line[1])
        adj[a].append(b)
        adj[b].append(a)

    parent = {SLACK_BUS: None}
    order = [SLACK_BUS]
    queue = [SLACK_BUS]
    while queue:
        u = queue.pop(0)
        for v in adj[u]:
            if v not in parent:
                parent[v] = u
                order.append(v)
                queue.append(v)

    depth = {}
    for n in order:
        depth[n] = 0 if parent[n] is None else depth[parent[n]] + 1

    end = max(depth, key=lambda n: depth[n])               # 본선 끝(최장경로)
    trunk = []
    x = end
    while x is not None:
        trunk.append(x)
        x = parent[x]
    trunk = trunk[::-1]
    trunk_set = set(trunk)

    pos = {n: (float(i), 0.0) for i, n in enumerate(trunk)}

    laterals = []
    for n in order:
        if n in trunk_set or parent[n] not in trunk_set:
            continue
        chain, cur = [n], n
        while True:
            kids = [v for v in adj[cur] if parent.get(v) == cur]
            if len(kids) == 1:
                chain.append(kids[0])
                cur = kids[0]
            else:
                break
        laterals.append({"attach": parent[n], "chain": chain})

    laterals.sort(key=lambda L: pos[L["attach"]][0])
    for idx, lat in enumerate(laterals):
        ax = pos[lat["attach"]][0]
        y = _LATERAL_LEVELS[idx % len(_LATERAL_LEVELS)]
        lat["y"] = y
        for k, n in enumerate(lat["chain"]):
            pos[n] = (ax + k, y)
    return pos, trunk, laterals


# ── 마커 ──────────────────────────────────────────────
def _substation(ax, x, y):
    ax.add_patch(Polygon([(x, y + 0.26), (x + 0.26, y), (x, y - 0.26), (x - 0.26, y)],
                 closed=True, fc="white", ec=_INK, lw=1.8, zorder=8))


def _glyph(ax, x, y, present, r=0.30):
    """노드 자원 글리프(도넛). present=[(color),...] 순서대로 부채꼴 분할."""
    n = len(present)
    if n == 0:
        return
    if n == 1:
        ax.add_patch(Circle((x, y), r, fc=present[0], ec="white", lw=1.0, zorder=8))
        ax.add_patch(Circle((x, y), r * 0.42, fc="white", ec="none", zorder=9))
        return
    for k, color in enumerate(present):
        th1, th2 = 90 + k * 360 / n, 90 + (k + 1) * 360 / n
        ax.add_patch(Wedge((x, y), r, th1, th2, width=r * 0.58,
                     fc=color, ec="white", lw=1.0, zorder=8))


# ── 메인 ──────────────────────────────────────────────
def plot_network(results, out_path, title="Optimal DER siting", lam=None):
    results = results or {}
    pos, trunk, laterals = _layout_from_edges()
    results = int_sites(results)          # summary.json 재사용 시 키가 문자열
    pv = results.get("pv_sites", {})
    ess = results.get("ess_sites", {})
    chp = results.get("chp_sites", {})

    fig = plt.figure(figsize=(15.5, 7.2))
    gs = fig.add_gridspec(1, 2, width_ratios=[2.35, 1.0], wspace=0.04)
    axm = fig.add_subplot(gs[0])     # 계통도
    axt = fig.add_subplot(gs[1])     # 용량 표
    axt.axis("off")

    # ── 계통도: 피더 ──
    for line in LINE_DATA:
        i, j = int(line[0]), int(line[1])
        (xi, yi), (xj, yj) = pos[i], pos[j]
        axm.plot([xi, xj], [yi, yj], color=_GRAY, lw=1.8, solid_capstyle="round", zorder=2)

    # ── DHN 열배관 overlay (점선 적색) ──
    for p in DHN_PIPE_DATA:
        a, b = int(p[0]), int(p[1])
        if a in pos and b in pos:
            (xa, ya), (xb, yb) = pos[a], pos[b]
            axm.plot([xa, xb], [ya, yb], color=_HEAT, lw=2.2,
                     ls=(0, (4, 2)), alpha=0.75, zorder=2.4, solid_capstyle="round")

    # ── 변전소 ──
    x0, y0 = pos[SLACK_BUS]
    axm.plot([x0, x0], [y0, y0 - 0.9], color=_GRAY, lw=1.8, zorder=2)
    _substation(axm, x0, y0 - 1.2)
    axm.text(x0, y0 - 1.62, "Substation", ha="center", va="top", fontsize=8, color=_INK)

    # ── 노드: 글리프(설치) 또는 점(비설치) + 버스번호 ──
    def _present(n):
        out = []
        if n in pv:
            out.append(_GOLD)
        if n in ess:
            out.append(_GREEN)
        if n in chp and chp[n].get("P_e_MW", 0) > 1e-3:
            out.append(_ORANGE)
        if n in chp and chp[n].get("E_tes_MWh", 0) > 1e-3:
            out.append(_TEAL)
        return out

    for n in range(NUM_NODES):
        x, y = pos[n]
        pr = _present(n)
        if pr:
            _glyph(axm, x, y, pr)
        elif n != SLACK_BUS:
            axm.add_patch(Circle((x, y), 0.075, fc=_NODE, ec="white", lw=0.5, zorder=6))
        axm.text(x, y + 0.40, str(n + 1), ha="center", va="bottom",
                 fontsize=7.5, color="black", zorder=9)

    # ── 글리프 범례 ──
    leg = [(_GOLD, "PV"), (_GREEN, "ESS"), (_ORANGE, "CHP"), (_TEAL, "TES")]
    handles = [plt.Line2D([], [], marker="o", ls="", markersize=10,
               markerfacecolor=c, markeredgecolor="white", label=l) for c, l in leg]
    handles.append(plt.Line2D([], [], color=_HEAT, lw=2.2, ls=(0, (4, 2)), label="DH pipe"))
    axm.legend(handles=handles, loc="upper right", fontsize=9, ncol=2,
               framealpha=0.95, title="Installed resource", title_fontsize=9,
               borderpad=0.6, columnspacing=1.0)

    lam_str = f"   (λ = {lam})" if lam is not None else ""
    axm.set_title(f"IEEE 33-bus — {title}{lam_str}", fontsize=14, fontweight="bold", pad=8)
    axm.set_aspect("equal")
    axm.axis("off")
    axm.set_xlim(-2.2, max(p[0] for p in pos.values()) + 1.0)

    # ── 용량 표 (우) ──
    cols, keys = ["Bus"], []
    if pv:
        cols.append("PV\n[MWp]"); keys.append("pv")
    if ess:
        cols += ["ESS\n[MW]", "ESS\n[MWh]"]; keys.append("ess")
    if chp:
        cols.append("CHP\n[MWe]"); keys.append("chp")
        cols.append("TES\n[MWh]"); keys.append("tes")

    sited = sorted(set(pv) | set(ess) | set(chp))
    rows = []
    for n in sited:
        r = [str(n + 1)]
        if "pv" in keys:
            r.append(f"{pv[n]['cap_MWp']:.2f}" if n in pv else "–")
        if "ess" in keys:
            r += ([f"{ess[n]['P_MW']:.2f}", f"{ess[n]['E_MWh']:.2f}"] if n in ess else ["–", "–"])
        if "chp" in keys:
            r.append(f"{chp[n]['P_e_MW']:.2f}" if n in chp and chp[n].get('P_e_MW', 0) > 1e-3 else "–")
        if "tes" in keys:
            r.append(f"{chp[n].get('E_tes_MWh', 0):.2f}" if n in chp and chp[n].get('E_tes_MWh', 0) > 1e-3 else "–")
        rows.append(r)

    # 합계 행
    tot = ["Σ"]
    if "pv" in keys:
        tot.append(f"{results.get('total_PV_MWp', sum(v['cap_MWp'] for v in pv.values())):.2f}")
    if "ess" in keys:
        tot += [f"{sum(v['P_MW'] for v in ess.values()):.2f}",
                f"{sum(v['E_MWh'] for v in ess.values()):.2f}"]
    if "chp" in keys:
        tot.append(f"{sum(v.get('P_e_MW', 0) for v in chp.values()):.2f}")
    if "tes" in keys:
        tot.append(f"{sum(v.get('E_tes_MWh', 0) for v in chp.values()):.2f}")
    rows.append(tot)

    if rows:
        tbl = axt.table(cellText=rows, colLabels=cols, loc="center", cellLoc="center",
                        bbox=[0.0, 0.0, 1.0, 0.96])
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        # 헤더 색
        hdr_clr = {"PV\n[MWp]": _GOLD, "ESS\n[MW]": _GREEN, "ESS\n[MWh]": _GREEN,
                   "CHP\n[MWe]": _ORANGE, "TES\n[MWh]": _TEAL}
        ncol = len(cols)
        for c in range(ncol):
            cell = tbl[0, c]
            cell.set_facecolor(hdr_clr.get(cols[c], "#444"))
            cell.set_text_props(color="white", fontweight="bold")
        # 합계 행 강조
        last = len(rows)
        for c in range(ncol):
            tbl[last, c].set_facecolor("#EFEFEF")
            tbl[last, c].set_text_props(fontweight="bold")
        axt.set_title("Installed capacity by bus", fontsize=11, fontweight="bold", pad=2)

    # ── 푸터 ──
    tot_pv = results.get("total_PV_MWp", 0.0)
    tot_p, tot_e = results.get("total_P_MW", 0.0), results.get("total_E_MWh", 0.0)
    dh_km = (results.get("dhn") or {}).get("total_pipe_km", 0.0)
    fig.text(0.5, 0.02,
             f"33 buses | 32 branches | {BASE_KV} kV | Peak load {PEAK_LOAD_MW*1000:.0f} kW   ·   "
             f"PV {tot_pv:.2f} MWp | ESS {tot_p:.2f} MW / {tot_e:.2f} MWh | "
             f"CHP {results.get('total_CHP_MW',0):.2f} MWe | TES {results.get('total_TES_MWh',0):.2f} MWh | "
             f"DH {dh_km:.1f} km",
             ha="center", va="bottom", fontsize=8.5, color=_LGRAY)

    fig.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
