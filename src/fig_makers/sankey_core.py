"""sankey_core.py - 의존성 없는 Sankey(리본) 렌더러.

plotly 없이 matplotlib 만으로 그린다. 노드는 열(column)에 배치되고 흐름은
3차 베지어 리본으로 이어진다. 값의 단위는 호출부가 정한다(본 프로젝트: GWh/yr).

사용:
    sk = Sankey()
    sk.node("LNG", col=0, color="#4E9BD6")
    sk.flow("LNG", "CHP", 19229)
    sk.draw(ax)
"""
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.path import Path
from matplotlib.patches import PathPatch, Rectangle

#: 노드 박스 폭 [축 좌표], 열 간 간격 대비 비율
BAR_W = 0.022
#: 같은 열 노드 사이 최소 세로 간격 [0~1 정규화]
GAP = 0.055


class Sankey:
    """열 기반 Sankey 다이어그램.

    노드 높이는 (유입 합, 유출 합) 중 큰 값에 비례한다 — 변환 손실이 있으면
    유입이 크므로 박스가 리본보다 높게 남고, 그 여백이 곧 손실이다.
    """

    def __init__(self):
        self.nodes = {}      # name -> dict(col, color, label)
        self.flows = []      # list of dict(src, dst, value, color, alpha)
        self.anchors = {}    # col -> 0(아래)~1(위) 수직 정렬 위치

    # ── 정의 ────────────────────────────────────────────────
    def node(self, name, col, color="#888888", label=None, order=None):
        """order: 열 안에서 위→아래 배치 순서. 생략 시 등록 순.

        리본 교차는 거의 전적으로 이 순서가 결정한다 — 보내는 쪽과 받는 쪽의
        순서를 맞춰 두면 교차가 사라진다.
        """
        self.nodes[name] = {"col": col, "color": color, "label": label or name,
                            "order": len(self.nodes) if order is None else order}
        return self

    def anchor(self, col, frac):
        """열의 수직 정렬 위치. 0=아래, 0.5=가운데(기본), 1=위.

        가벼운 열(예: 저장설비 하나뿐인 열)은 가운데 정렬하면 무거운 열의
        리본 위에 얹혀 오독을 부른다. 연결된 리본 쪽으로 끌어내린다.
        """
        self.anchors[col] = float(frac)
        return self

    def flow(self, src, dst, value, color=None, alpha=0.62):
        """value <= 0 인 흐름은 무시한다 (미설치 설비 → 그림에서 자동 제거)."""
        if value is None or value <= 1e-9:
            return self
        self.flows.append({"src": src, "dst": dst, "value": float(value),
                           "color": color, "alpha": alpha})
        return self

    # ── 배치 ────────────────────────────────────────────────
    def _totals(self):
        """노드별 (유입, 유출) 합계 [값 단위]."""
        tin = {n: 0.0 for n in self.nodes}
        tout = {n: 0.0 for n in self.nodes}
        for f in self.flows:
            tout[f["src"]] += f["value"]
            tin[f["dst"]] += f["value"]
        return tin, tout

    def _layout(self):
        """노드 → (x, y_bottom, height). 값→높이 축척은 전 열 공통."""
        tin, tout = self._totals()
        size = {n: max(tin[n], tout[n]) for n in self.nodes}

        cols = {}
        for n, d in self.nodes.items():
            if size[n] > 0:
                cols.setdefault(d["col"], []).append(n)
        if not cols:
            raise ValueError("그릴 흐름이 없다")

        # 축척: 가장 무거운 열이 세로 공간(간격 제외)을 꽉 채우도록
        scale = min((1.0 - GAP * (len(ns) - 1)) / sum(size[n] for n in ns)
                    for ns in cols.values())

        pos = {}
        for col, ns in cols.items():
            # y 는 아래에서 위로 쌓으므로, order 0 이 위로 오도록 역순 정렬한다
            ns.sort(key=lambda n: -self.nodes[n]["order"])
            total = sum(size[n] * scale for n in ns) + GAP * (len(ns) - 1)
            y = (1.0 - total) * self.anchors.get(col, 0.5)   # 열 수직 정렬
            ncol = max(cols) or 1
            for n in ns:
                h = size[n] * scale
                pos[n] = (col / ncol, y, h)
                y += h + GAP
        return pos, size, scale

    # ── 렌더 ────────────────────────────────────────────────
    @staticmethod
    def _ribbon(ax, x0, y0, x1, y1, h0, h1, color, alpha):
        """(x0,y0)~(x1,y1) 두 점을 잇는 두께 h0→h1 의 베지어 리본."""
        cx = (x0 + x1) / 2.0                         # 제어점 x (수평 진입/진출)
        verts = [(x0, y0), (cx, y0), (cx, y1), (x1, y1),
                 (x1, y1 + h1), (cx, y1 + h1), (cx, y0 + h0), (x0, y0 + h0),
                 (x0, y0)]
        codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
                 Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
                 Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), facecolor=color,
                               edgecolor="none", alpha=alpha, zorder=1))

    def draw(self, ax, fmt="{:,.0f}", label_fs=9, value_fs=8.5):
        pos, size, _ = self._layout()
        ncol = max(d["col"] for d in self.nodes.values()) or 1

        # 노드 박스
        for n, (x, y, h) in pos.items():
            ax.add_patch(Rectangle((x - BAR_W / 2, y), BAR_W, h, zorder=3,
                                   facecolor=self.nodes[n]["color"],
                                   edgecolor="none"))

        # 리본 (노드별로 위→아래 순서를 유지하기 위해 오프셋 누적)
        off_out = {n: pos[n][1] for n in pos}
        off_in = {n: pos[n][1] for n in pos}
        for f in sorted(self.flows, key=lambda f: -f["value"]):
            s, d = f["src"], f["dst"]
            if s not in pos or d not in pos:
                continue
            _, _, hs = pos[s]
            hv = f["value"] / max(size[s], 1e-12) * hs          # 리본 두께(출발)
            _, _, hd = pos[d]
            hv_d = f["value"] / max(size[d], 1e-12) * hd        # 리본 두께(도착)
            color = f["color"] or self.nodes[s]["color"]
            self._ribbon(ax, pos[s][0] + BAR_W / 2, off_out[s],
                         pos[d][0] - BAR_W / 2, off_in[d], hv, hv_d,
                         color, f["alpha"])
            off_out[s] += hv
            off_in[d] += hv_d

        # 라벨 — 양 끝 열은 바깥쪽, 중간 열은 박스 위에
        for n, (x, y, h) in pos.items():
            col = self.nodes[n]["col"]
            # 반올림해서 0 으로 보이는 값은 "0" 대신 상한을 밝힌다
            val = fmt.format(size[n]) if size[n] >= 0.05 else "<0.05"
            txt = f"{self.nodes[n]['label']}\n{val}"
            if col == 0:
                ax.text(x - BAR_W, y + h / 2, txt, ha="right", va="center",
                        fontsize=label_fs, zorder=4)
            elif col == ncol:
                ax.text(x + BAR_W, y + h / 2, txt, ha="left", va="center",
                        fontsize=label_fs, zorder=4)
            else:
                ax.text(x, y + h / 2, txt, ha="center", va="center",
                        fontsize=value_fs, zorder=4,
                        bbox=dict(boxstyle="round,pad=0.25", fc="white",
                                  ec="none", alpha=0.82))

        ax.set_xlim(-0.16, 1.16)
        ax.set_ylim(-0.04, 1.04)
        ax.axis("off")
        return ax
