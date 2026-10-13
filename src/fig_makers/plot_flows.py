"""plot_flows.py - 시간별 운전 그림(Fig. 8) · 연간 에너지 흐름 Sankey(Fig. 9).

입력은 `output.save_variable_csvs: true` 로 실행했을 때 저장되는
`outputs/<scenario>/results/*.csv` (extract_all 결과) 이다.

연간화:
    E[MWh/yr] = Σ_s prob_s · Σ_t x[s,t] · Δt(=1h) · 365
    objective.py 의 weight(= 365·PVIFA) 와 같은 일→연 환산이며, PVIFA 는 비용
    할인 계수이므로 에너지 그림에는 적용하지 않는다.

그림 라벨은 영문(영문 논문).
"""
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.data_process.network import LOAD_DATA_MW, CHP_CANDIDATE_NODES
from src.fig_makers.sankey_core import Sankey
from src.utils.config_loader import get

#: 캐리어별 색 (전 그림 공통)
C = {"lng": "#4E9BD6", "grid": "#8C8C8C", "pv": "#F0B429", "chp": "#D64545",
     "boiler": "#E08A5B", "elec": "#E8A33D", "heat": "#C0392B",
     "ess": "#5DADE2", "tes": "#AF7AC5", "loss": "#C4C4C4", "export": "#7FB069"}

#: (변수명, 노드 인덱스 보유 여부) — 없으면 0 배열로 대체
VARS = [("p_pv", True), ("p_chp_elec", True), ("p_chp_heat", True),
        ("p_boiler_heat", True), ("p_charge", True), ("p_discharge", True),
        ("soc", True), ("tes_charge", True), ("tes_discharge", True),
        ("soc_tes", True), ("r_fr_up", True), ("r_fr_dn", True),
        ("p_import", False), ("p_export", False)]


def load_hourly(results_dir, n_scen: int, n_t: int = 24) -> dict:
    """변수 CSV → {변수명: [S x T] 배열} (노드 축은 합산).

    미설치 설비(ESS=0 등)로 CSV 가 없으면 0 배열을 넣는다.
    """
    results_dir = Path(results_dir)
    out = {}
    for name, has_node in VARS:
        path = results_dir / f"{name}.csv"
        arr = np.zeros((n_scen, n_t))
        if path.exists():
            df = pd.read_csv(path)
            si, ti = "index_0", ("index_2" if has_node else "index_1")
            g = df.groupby([si, ti])[name].sum()
            for (s, t), v in g.items():
                if int(s) < n_scen and int(t) < n_t:
                    arr[int(s), int(t)] = v
        out[name] = arr
    return out


def heat_load_profile(scenario: dict, config: dict) -> np.ndarray:
    """시스템 총 열부하 [S x T, MW_th] — model.py 의 Param 구성과 동일하게 복원.

        heat_load[s,n,t] = heat_prof[s,t] · LOAD_DATA_MW[n] · heat_ratio
    """
    heat_ratio = get(config, "dhn.heat_ratio", 0.8)
    peak = float(sum(LOAD_DATA_MW[n] for n in CHP_CANDIDATE_NODES)) * heat_ratio
    return np.asarray(scenario["heat"], dtype=float) * peak


def annual_flows(h: dict, probs, config: dict, heat_load: np.ndarray) -> dict:
    """연간 에너지 흐름 [GWh/yr]. 부호·항목은 balance.py / dhn.py 와 일치."""
    p = np.asarray(probs, dtype=float)[:, None]

    def E(arr):                                   # [S x T, MW] → [GWh/yr]
        return float((np.asarray(arr) * p).sum() * 365.0 / 1000.0)

    eta_e = get(config, "chp.eta_elec", 0.35)
    eta_b = get(config, "boiler.eta", 0.90)

    chp_e, chp_h = E(h["p_chp_elec"]), E(h["p_chp_heat"])
    boil_h = E(h["p_boiler_heat"])
    gas_chp = E(h["p_chp_elec"] / eta_e)          # CHP 연료 투입 [GWh_LHV/yr]
    gas_boil = E(h["p_boiler_heat"] / eta_b)
    chg, dis = E(h["p_charge"]), E(h["p_discharge"])
    tch, tdis = E(h["tes_charge"]), E(h["tes_discharge"])
    imp, exp = E(h["p_import"]), E(h["p_export"])
    pv = E(h["p_pv"])

    # 전력 부하: balance.py 의 수급식에서 역산 (변수만으로 닫힌다)
    e_load = imp - exp + pv + chp_e + dis - chg
    h_load = E(heat_load)
    # 열 잉여: dhn.py 의 열균형이 부등식(≥)이라 공급이 부하를 넘을 수 있다
    h_dump = max(chp_h + boil_h + tdis - tch - h_load, 0.0)

    return {"gas_chp": gas_chp, "gas_boiler": gas_boil,
            "chp_elec": chp_e, "chp_heat": chp_h,
            "chp_loss": max(gas_chp - chp_e - chp_h, 0.0),
            "boiler_heat": boil_h, "boiler_loss": max(gas_boil - boil_h, 0.0),
            "pv": pv, "import": imp, "export": exp,
            "ess_charge": chg, "ess_discharge": dis,
            "ess_loss": max(chg - dis, 0.0),
            "tes_charge": tch, "tes_discharge": tdis,
            "tes_loss": max(tch - tdis, 0.0),
            "elec_load": e_load, "heat_load": h_load, "heat_dump": h_dump}


#: 대표일 내부명(month_2_we) → 그림용 영문 라벨(Feb, weekend)
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pretty_day(name) -> str:
    """시나리오 내부명을 독자가 읽을 라벨로. 규칙에 안 맞으면 원문을 그대로."""
    m = re.fullmatch(r"month_(\d{1,2})_(wd|we)", str(name))
    if not m:
        return str(name)
    season = "weekday" if m.group(2) == "wd" else "weekend"
    return f"{_MONTHS[int(m.group(1)) - 1]}, {season}"


def plot_sankey(f: dict, out_path, title="Annual energy flow [GWh/yr]"):
    """원천 → 변환 → 캐리어 → 저장 → 수요 Sankey.

    저장(ESS·TES)은 **버스와 수요 사이의 독립 열**에 둔다. 충·방전은 같은 버스를
    오가는 순환이라 엄밀한 DAG 로는 못 그리므로 '저장을 거쳐 수요에 도달한
    에너지'로 환산한다 — 저장 노드의 크기가 곧 연간 순환량이고, 저장이 0 이면
    (Sankey.flow 가 0 을 버리므로) 노드가 자동으로 사라진다.

    손실·잉여는 종단 노드로 **명시**한다. 변환효율과 열 잉여가 그림에서 바로
    읽혀야 심사에서 방어된다.
    """
    # 저장을 경유하는 몫 / 버스에서 수요로 직행하는 몫
    tes_to_load = min(f["tes_discharge"], f["heat_load"])
    heat_direct = max(f["heat_load"] - tes_to_load, 0.0)
    ess_to_load = min(f["ess_discharge"], f["elec_load"])
    elec_direct = max(f["elec_load"] - ess_to_load, 0.0)

    sk = Sankey()
    #            이름                 열  색          order(0=맨 위)
    sk.node("PV", 0, C["pv"], order=0)
    sk.node("Grid import", 0, C["grid"], order=1)
    sk.node("LNG", 0, C["lng"], order=2)
    sk.node("CHP", 1, C["chp"], order=0)
    sk.node("Boiler", 1, C["boiler"], order=1)
    sk.node("Electricity bus", 2, C["elec"], order=0)
    sk.node("Conversion loss", 2, C["loss"], order=1)
    sk.node("Heat bus", 2, C["heat"], order=2)
    sk.node("ESS", 3, C["ess"], order=0)
    sk.node("TES", 3, C["tes"], order=1)
    sk.node("Export", 4, C["export"], order=0)
    sk.node("Electric load", 4, C["elec"], order=1)
    sk.node("Storage loss", 4, C["loss"], order=2)
    sk.node("Heat surplus", 4, C["loss"], order=3)
    sk.node("Heat load", 4, C["heat"], order=4)

    sk.flow("LNG", "CHP", f["gas_chp"], C["lng"])
    sk.flow("LNG", "Boiler", f["gas_boiler"], C["lng"])
    sk.flow("CHP", "Electricity bus", f["chp_elec"], C["chp"])
    sk.flow("CHP", "Conversion loss", f["chp_loss"], C["loss"], 0.40)
    sk.flow("CHP", "Heat bus", f["chp_heat"], C["heat"])
    sk.flow("Boiler", "Heat bus", f["boiler_heat"], C["boiler"])
    sk.flow("Boiler", "Conversion loss", f["boiler_loss"], C["loss"], 0.40)
    sk.flow("Grid import", "Electricity bus", f["import"], C["grid"])
    sk.flow("PV", "Electricity bus", f["pv"], C["pv"])
    sk.flow("Electricity bus", "ESS", f["ess_charge"], C["ess"])
    sk.flow("Electricity bus", "Electric load", elec_direct, C["elec"])
    sk.flow("Electricity bus", "Export", f["export"], C["export"])
    sk.flow("ESS", "Electric load", ess_to_load, C["ess"])
    sk.flow("ESS", "Storage loss", f["ess_loss"], C["ess"], 0.40)
    sk.flow("Heat bus", "TES", f["tes_charge"], C["tes"])
    sk.flow("Heat bus", "Heat load", heat_direct, C["heat"])
    sk.flow("Heat bus", "Heat surplus", f["heat_dump"], C["loss"], 0.40)
    sk.flow("TES", "Heat load", tes_to_load, C["tes"])
    sk.flow("TES", "Storage loss", f["tes_loss"], C["tes"], 0.40)

    # ESS 가 없으면 저장 열에 TES 만 남아 가운데 정렬 시 전력 리본 위에
    # 얹힌다 — 열(heat) 리본 높이로 내려 오독을 막는다.
    if f["ess_charge"] <= 1e-9:
        sk.anchor(3, 0.30)

    # CIRED 2단 전체 폭(약 7.2 in)에 1:1 로 들어가도록 설계 — 축소 없이 실리면
    # 그림 안 글자 크기가 본문과 같은 눈금으로 읽힌다.
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    sk.draw(ax, fmt="{:,.1f}", label_fs=7.0, value_fs=6.6)
    ax.set_title(title, fontsize=9.5, pad=8)
    note = ("Fuel on LHV basis. Representative days are weighted by scenario "
            "probability and annualised over 365 days.\n"
            "Storage nodes show the annual throughput routed through the store; "
            "network losses are excluded (handled by the LPF constraints).\n"
            "Heat surplus is CHP heat dumped because the DHN heat balance is an "
            "inequality.")
    fig.text(0.5, 0.025, note, ha="center", va="bottom", fontsize=5.8,
             color="#555555", linespacing=1.45)
    fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.17)
    return _save(fig, out_path)


def plot_dispatch(h: dict, heat_load: np.ndarray, s_idx: list, names: list,
                  out_path, title="Hourly dispatch", row_notes=None):
    """대표 시나리오별 시간별 운전 (행=대표일, 열=전력·열[·예비력]).

    전력 패널은 balance.py 와 같은 부호 규약을 쓴다: 공급(발전·수전·방전)은 +,
    소비(충전·수출)는 −. 부하선은 스택 상단과 일치해야 한다(검산용).

    ESS 가 설치되지 않은 해에서는 FR 예비력 열이 통째로 빈 패널이 되므로 열
    자체를 뺀다. 값이 0 인 계열은 범례에서도 제외한다.
    """
    hrs = np.arange(24)
    nrow = len(s_idx)

    def peak(key):
        return max(float(np.max(np.abs(h[key][s]))) for s in s_idx)

    has_ess = (peak("r_fr_up") + peak("r_fr_dn")
               + peak("p_charge") + peak("p_discharge")) > 1e-9
    has_boiler = peak("p_boiler_heat") > 1e-9
    has_export = peak("p_export") > 1e-9
    ncol = 3 if has_ess else 2

    plt.rcParams["hatch.linewidth"] = 0.5
    fig, axes = plt.subplots(nrow, ncol, squeeze=False, sharex=True,
                             figsize=(3.1 * ncol + 1.0, 1.85 * nrow + 0.85))

    # 행 간 비교가 가능하도록 축 범위를 전 행 공통으로 둔다
    e_top = max(float((h["p_import"][s] + h["p_chp_elec"][s] + h["p_pv"][s]
                       + h["p_discharge"][s]).max()) for s in s_idx)
    e_bot = -max(float((h["p_export"][s] + h["p_charge"][s]).max())
                 for s in s_idx)
    q_top = max(float((h["p_chp_heat"][s] + h["p_boiler_heat"][s]
                       + h["tes_discharge"][s]).max()) for s in s_idx)
    q_bot = -peak("tes_charge")
    soc_lo = min(float(h["soc_tes"][s].min()) for s in s_idx)
    soc_hi = max(float(h["soc_tes"][s].max()) for s in s_idx)
    soc_pad = max((soc_hi - soc_lo) * 0.08, 1e-3)
    soc_handle = ([], [])

    for r, s in enumerate(s_idx):
        # ── (1) 전력 ────────────────────────────────────────
        ax = axes[r][0]
        stack, colors, labels = [], [], []
        for key, col, lab, keep in (
                ("p_import", C["grid"], "Grid import", True),
                ("p_chp_elec", C["chp"], "CHP", True),
                ("p_pv", C["pv"], "PV", True),
                ("p_discharge", C["ess"], "ESS discharge", has_ess)):
            if keep:
                stack.append(h[key][s])
                colors.append(col)
                labels.append(lab)
        ax.stackplot(hrs, *stack, colors=colors, labels=labels, alpha=0.9)
        if has_export:
            ax.fill_between(hrs, 0, -h["p_export"][s], color=C["export"],
                            alpha=0.9, label="Export")
        if has_ess:
            ax.fill_between(hrs, -h["p_export"][s],
                            -h["p_export"][s] - h["p_charge"][s],
                            color=C["ess"], alpha=0.55, label="ESS charge")
        e_load = (h["p_import"][s] - h["p_export"][s] + h["p_pv"][s]
                  + h["p_chp_elec"][s] + h["p_discharge"][s] - h["p_charge"][s])
        ax.plot(hrs, e_load, color="black", lw=1.3, ls="--", label="Electric load")
        row = pretty_day(names[s])
        if row_notes:
            row += f" · {row_notes[r]}"
        ax.set_ylabel(f"{row}\nPower [MW]", fontsize=7.0)
        ax.axhline(0, color="#999999", lw=0.6)
        ax.set_ylim(min(e_bot * 1.15, -0.02), e_top * 1.30)
        if r == 0:
            ax.set_title("Electricity", fontsize=9)

        # ── (2) 열 ──────────────────────────────────────────
        ax = axes[r][1]
        hstack, hcolors, hlabels = [h["p_chp_heat"][s]], [C["heat"]], ["CHP heat"]
        if has_boiler:
            hstack.append(h["p_boiler_heat"][s])
            hcolors.append(C["boiler"])
            hlabels.append("Boiler")
        hstack.append(h["tes_discharge"][s])
        hcolors.append(C["tes"])
        hlabels.append("TES discharge")
        ax.stackplot(hrs, *hstack, colors=hcolors, labels=hlabels, alpha=0.9)
        ax.fill_between(hrs, 0, -h["tes_charge"][s], color=C["tes"], alpha=0.42,
                        label="TES charge")
        # 공급이 부하를 넘는 구간 = 버려지는 열. Sankey 의 Heat surplus 와 같은 양.
        net = (h["p_chp_heat"][s] + h["p_boiler_heat"][s]
               + h["tes_discharge"][s] - h["tes_charge"][s])
        ax.fill_between(hrs, heat_load[s], net, where=net > heat_load[s] + 1e-9,
                        facecolor="none", hatch="///", edgecolor="#404040",
                        linewidth=0.0, label="Heat surplus (dumped)")
        ax.plot(hrs, heat_load[s], color="black", lw=1.3, ls="--",
                label="Heat load")
        ax.axhline(0, color="#999999", lw=0.6)
        ax.set_ylabel("Heat [MW_th]", fontsize=7.0)
        # 범례(좌상단)가 데이터를 가리지 않도록 열 패널은 위 여백을 넉넉히
        ax.set_ylim(min(q_bot * 1.15, -0.02), q_top * 1.48)
        ax2 = ax.twinx()
        ax2.plot(hrs, h["soc_tes"][s], color="#4A235A", lw=1.2, ls="-",
                 label="TES SOC (right axis)")
        ax2.set_ylim(soc_lo - soc_pad, soc_hi + soc_pad)
        ax2.set_ylabel("TES SOC [MWh_th]", fontsize=6.5, color="#4A235A")
        ax2.tick_params(axis="y", labelsize=6, colors="#4A235A")
        if r == 0:
            ax.set_title("Heat (DHN)", fontsize=9)
            soc_handle = ax2.get_legend_handles_labels()

        # ── (3) FR 예비력 · ESS SOC (ESS 가 있을 때만) ──────
        if has_ess:
            ax = axes[r][2]
            ax.fill_between(hrs, 0, h["r_fr_up"][s], color="#2E86C1", alpha=0.7,
                            label="FR reserve up")
            ax.fill_between(hrs, 0, -h["r_fr_dn"][s], color="#AF601A", alpha=0.7,
                            label="FR reserve down")
            ax.axhline(0, color="#999999", lw=0.6)
            ax.set_ylabel("Reserve [MW]", fontsize=7.0)
            ax2 = ax.twinx()
            ax2.plot(hrs, h["soc"][s], color="#1B4F72", lw=1.2)
            ax2.set_ylabel("ESS SOC [MWh]", fontsize=6.5, color="#1B4F72")
            ax2.tick_params(axis="y", labelsize=6, colors="#1B4F72")
            if r == 0:
                ax.set_title("FR reserve offered", fontsize=9)

        for c in range(ncol):
            a = axes[r][c]
            a.set_xlim(0, 23)
            a.set_xticks(range(0, 24, 4))
            a.tick_params(labelsize=6.5)
            a.grid(alpha=0.22, lw=0.4)
            if r == nrow - 1:
                a.set_xlabel("Hour", fontsize=7.5)

    for c in range(ncol):
        hnd, lab = axes[0][c].get_legend_handles_labels()
        if c == 1:                                   # 열 패널엔 SOC 선도 넣는다
            hnd, lab = hnd + soc_handle[0], lab + soc_handle[1]
        if lab:
            axes[0][c].legend(hnd, lab, fontsize=5.8, loc="upper left", ncol=2,
                              framealpha=0.85, handlelength=1.4,
                              columnspacing=0.9, borderpad=0.35)

    fig.suptitle(title, fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    return _save(fig, out_path)


def _save(fig, out_path):
    """PNG(400 dpi) + 인쇄용 벡터 PDF 를 같은 이름으로 저장한다."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=400)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    return out_path
