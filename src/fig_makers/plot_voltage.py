"""plot_voltage.py - 노드별×시간별 전압 프로파일 3D surface."""

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib import cm
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (3D projection 등록용)

from src.data_process.network import V_MIN, V_MAX


def plot_voltage_surface(vprof: dict, out_path, title="Voltage profile",
                         which="V_exp"):
    """전압 surface (X=Buses, Y=Time[h], Z=Voltage[pu]).

    vprof : extractor.compute_voltage_profile() 의 반환 dict.
    which : 'V_exp'(확률가중 기대전압) | 'V_min'(시나리오 최저전압).
    """
    Z = vprof[which]                          # (N, T)
    N, T = Z.shape
    buses = np.arange(1, N + 1)               # 1-indexed Bus 번호
    hours = np.arange(T)
    Bg, Tg = np.meshgrid(buses, hours, indexing="ij")   # (N,T)

    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(Bg, Tg, Z, cmap=cm.jet,
                           vmin=float(Z.min()), vmax=float(Z.max()),
                           rstride=1, cstride=1, linewidth=0.15,
                           edgecolor="0.3", antialiased=True)

    ax.set_xlabel("Buses")
    ax.set_ylabel("Time (h)")
    ax.set_zlabel("Voltage (pu)")
    # z축: 전압 운영한계가 보이도록 데이터 + [V_MIN, V_MAX] 포괄
    ax.set_zlim(min(V_MIN, float(Z.min()) - 0.003),
                max(1.01, float(Z.max()) + 0.003))
    ax.view_init(elev=22, azim=-60)
    ax.set_title(title, fontweight="bold")

    cbar = fig.colorbar(surf, ax=ax, shrink=0.6, aspect=12, pad=0.10)
    cbar.set_label("Voltage (pu)")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
