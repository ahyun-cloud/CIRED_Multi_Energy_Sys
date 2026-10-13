# HANDOFF — 작업 재개 시 여기부터 (2026-09-04 기준)

> 다른 PC·다른 세션에서 이어서 작업할 때 **이 파일을 먼저** 읽으세요.
> 상태: `main` 단일 브랜치. `outputs/` 중 논문용 그림(*.png)·`summary.json`·분석 CSV 만 추적되고
> 로그·엑셀·변수 덤프는 제외된다 → 숫자는 `docs/RESULTS.md` 가 기준.
>
> | 문서 | 역할 |
> |---|---|
> | **HANDOFF.md** (이 파일) | 상황 파악 · 챕터별 요약 · 다음 할 일 |
> | **docs/RESULTS.md** | 모든 확정 수치 (단일 소스) |
> | **docs/paper/PAPER_REVISION.md** | 논문 절별 수정안 · Abstract 영문 초안 · 심사 대응 |
> | **docs/ASSUMPTIONS.md** | 가정·한계 (★신규 표시가 이번 발견) |
> | **CLAUDE.md** | 환경·실행법·함정 |

---

## 1. 지금 상황 세 줄

1. 제출된 논문(`260701_CIRED_조아현_v5_최종.pdf`)에서 **모델 버그 2건**을 발견해 수정·재실행했다.
2. 그 결과 **ESS 최적값이 1.16 MW → 0** 이 되었고, 위험을 흡수하는 자원이
   **전기 저장 → 열 측(CHP·TES)** 으로 바뀌었다. 논문 결론과 **부호가 반대**다.
3. CIRED 발표는 2026-11-02. **개정판 재업로드가 가능**하며, 아래 §4 순서로 수정하면 된다.
   교수님(교신저자) 승인이 필요한 "결론 변경" 이므로 혼자 진행할 사안이 아니다.

### 수정한 버그 2건

| # | 내용 | 파일 |
|---|---|---|
| ① | **일주기 SOC 종기조건** — `soc[23]=0.5E` 로 두어 t=23 충·방전이 에너지 보존식에서 빠졌다. 매일 정격만큼 **무상 방전**이 가능했다. **논문 식 (6)은 원래 옳았고 코드가 어긋난 것** → 수식 수정 불필요. | `constraints/ess.py`, `chp.py` |
| ② | **PV 프로파일 정규화** — 각 날을 그 날의 최대로 나눠(`arr/arr.max()`) 모든 대표일이 '맑은 날'이 됐다. 발전량 1.7배 과대·σ 10배 과소. 설비용량 기준 per-unit 으로 교체. | `data_process/loader.py`, `scenario_gen.py` |

부수로 ③ `extractor` 보고값의 할인 누락(REC 수익·DHN 투자비)도 고쳤다.

---

## 2. 챕터별 요약 (논문 양식 그대로)

### Abstract — 문장 3개 교체
| 지울 문장 | 대체 |
|---|---|
| "ESS가 0에서 1.16 MW로 늘어난다" | ESS는 0 |
| "VSS가 양(+)이다" | 위험은 열 측에서 흡수됨 |
| "위험이 전기 측에 집중" | **부호 반대** |

기억할 한 줄: `ESS 0 · CHP 1.803→2.213 MW · TES 0→11.52 MWh`

### §1 Introduction — 거의 그대로
문장 2곳만. ⑴ "value of the stochastic solution" → "어떤 자원이 꼬리위험을 흡수하는가",
⑵ 잉여 PV·출력제한을 서론에서 과하게 예고하지 않기(본 결과 curtailment 0%).
선행연구·연구 gap·NDC 배경은 **손대지 않음**.

### §2 Methodology — 손대지 않음
**식 (1)~(7) 전부 유효.** §2.3 "50% initial SOC" 문구에 종기조건 한 구절만 추가.

### §3.1 Parameter Settings — 사실 오류 5곳
| 원문 | 수정 |
|---|---|
| "32 buses are PV/ESS candidates" | PV 32개, **ESS 11개** |
| "KEPCO demand 로 부하 프로파일" | 부하 형상은 **하드코딩 2곡선**(KPX는 σ만) |
| "export price equals the SMP" | 계절×시간대 **전형값 근사** |
| "NPV basis (real rate r, horizon N)" | **4.5%, 15년, PVIFA 10.74** 명기 |
| (PV 정규화 서술 없음) | **문장 추가** — 설비용량 기준 per-unit 정규화, 발전량 **1,654 kWh/kWp/yr(CF 18.9%)**, σ **0.343**(실측 일간 CV 0.431에 모먼트 정합) |

### §3.2 Baseline Results — Table 1 교체 + 문단 3개
**새 Table 1** (노드 인덱스 **+1** = 실제 Bus):

| 자원 | Bus | 용량 |
|---|---|---|
| PV | 27, 28, 29, 30 | 3.3 MWp (외생 고정) |
| **ESS** | — | **미설치** |
| CHP | 7, 8, 24 | 2.213 MWe |
| TES | 7, 8, 24 | 11.52 MWh_th |
| 보일러 | — | 미설치 |

**새 비교표** (억원, 15년 NPV, 전부 proven optimal):

| | 결정론 | rep24 | MC100 |
|---|---:|---:|---:|
| 목적함수 | 425.5 | **594.4** | 618.9 |
| 투자 | 135.4 | 142.3 | 143.7 |
| 기대운영 | 290.0 | 284.7 | 286.8 |
| CVaR | (290.0) | 334.9 | 376.8 |
| ESS | 0 | **0** | 0 |
| CHP | 1.803 | **2.213** | 2.298 MW |
| TES | **0** | **11.52** | 17.35 MWh |

손볼 문단 3개: ⑴ "total annualized cost 47.84 bn" → **15년 NPV이고 λ·CVaR 포함** 명기,
⑵ **"선로손실 저감" 삭제**(모델에 손실항 없음), ⑶ "ESS를 CHP와 같은 버스에" 문단 **삭제**.

핵심 문장: *결정론은 축열조를 아예 짓지 않고, 위험을 가격화한 확률론 해만 짓는다.*

### §3.3 Sensitivity — λ·α는 살아남고, 침투율은 폐기
**λ·α 서사 성립.** λ 0→2 에서 선제투자 140.5→143.3억, 기대운영 286.2→284.1, CVaR 337.2→334.2.
**주역만 ESS → CHP**(2.097→2.286 MW). α 무감응 결론도 유지되되 이유가 바뀜 — 평일 시나리오
확률 22/365=0.0603 > 0.05 → **α≥0.94 에서 꼬리가 단일 시나리오로 붕괴**(이산화 효과).

**침투율 패널은 폐기.** 7.7 MWp 에서 curtailment 21.1% → **0.27%**. 유지하려면 역송한계를
0.5 MW 등으로 재설정하고, 기준이 rep24 가 아니라 **사계절 4시나리오**임을 명시할 것.

### §4 Conclusion — findings 3개 교체 + 한계 4줄
| 새 finding | 근거 |
|---|---|
| ① ESS 미도입, 원인은 CHP 구축(crowding-out) | 기대 피크 수전 **0.94 MW**, ESS 1.16 MW가 깎는 양 **73 kW = 정격 6%** |
| ② 위험은 열 측에서 흡수 | CHP +23%, TES **0 → 11.52**(MC100 17.35) MWh |
| ③ 막는 건 자본비가 아니라 수익원 | capex 절반에도 0 / FR 정산단가 **11,000~12,000 원/MW/h**(현행 8,500의 1.3~1.4배) 넘으면 진입 |

추가할 한계 4개: 가격 불확실성 부재(**향후연구 1순위**) · 계통손실 미계상 → PV 배치를 결과로
주장 못 함 · PV 총량 외생 고정 · 기본요금을 대표일 피크×12개월로 근사

---

## 3. 진단 A~F — 한 줄씩만 기억하면 됨

전부 §4 finding ①·③ 을 뒷받침하는 근거다. 상세는 `docs/RESULTS.md` §2.

| | 질문 | 답 |
|---|---|---|
| A | 논문의 1.16 MW 를 강제하면? | **+7.47억 손실**, 피크 저감 73 kW뿐 |
| B | ESS 단가를 낮추면? | 들어오지만 **FR 수익 혼입** → 손익분기로 인용 금지 |
| C | 기본요금 2배로? | ESS 0, 대신 CHP 증가(2.213→2.304) |
| D | 실측 불확실성(MC100)에선? | **ESS 0** (proven) |
| E | capex 만 절반으로? | **ESS 0** (proven) → 자본비가 원인 아님 |
| F | FR 정산단가를 올리면? | **11,000~12,000 원/MW/h 에서 진입** ← 논문에 쓸 숫자 |

임계값을 넘으면 ESS 가 정확히 **2.0 MW = `fr_total_cap_mw`(시장 조달 상한)** 로 포화하고
설치 노드가 케이스마다 무의미하게 바뀐다 → **위치 무관한 시스템 서비스 자산으로만 진입**.

**미래경로(2030~2050)는 논문에 없는 부록성 분석.** 한 줄만: 탄소가격이 CHP 를 밀어내자
(2.000 → 0 MWe) ESS 가 들어온다(1.500 → 2.476 MW). finding ① 과 같은 이야기.

---

## 4. 다음에 할 일 (순서대로)

- [ ] **교수님(교신저자)과 상의** — 이건 "오타 수정"이 아니라 결론 변경이다. 이 파일 +
      `docs/paper/PAPER_REVISION.md` 를 근거로. 발표 2개월 전이고 수정 경로가 명확하다는 점을 함께.
- [ ] Abstract·§4 재작성 (방향이 반대이므로 가장 먼저)
- [ ] §3.1 사실 오류 5곳 수정
- [ ] Table 1 교체 + 버스번호 **+1** 확인 (그림 라벨도)
- [ ] §3.2 문단 3개 손봄
- [ ] §3.3 숫자 교체 + 침투율 패널 처리 결정
- [ ] 그림 파일 교체 (이미 전부 재생성됨 — `outputs/` 참조. 새 환경이면 재실행 필요)
- [ ] 개정판 재업로드

**작업량**: 제목·서론·방법론·식 (1)~(7)·참고문헌·페이지 분량은 **전부 그대로**.
바뀌는 것은 초록 3문장, §3.1 다섯 곳, Table 1, §3.2 세 문단, §3.3 숫자, §4 결론.
현실적으로 **2~3일**.

**하지 말 것**: 모델 개선(가격 불확실성 도입·손실항 추가·기본요금 월최대 정식화·rep24 일간변동
반영)은 각각 1~2주 작업이고 결론을 다시 흔든다. **한계로 명시하고 저널 확장으로 넘긴다.**
가격 불확실성이 저널 확장 1순위이며 참고문헌 [2]가 이미 SMP 변동성 연구다.

---

## 5. 미확정·미해결

| 항목 | 상태 |
|---|---|
| `future_pathway` 2040년 | ⚠ PV siting 고정 후에도 40분 제한 미수렴. incumbent 가 no-ESS 해와 거의 동일. 양옆 연도가 모두 ESS 설치하므로 **이 0은 신뢰 불가**. **재실행 명령은 §6 참조** (`--time_limit`·`--redo` 옵션 추가됨) |
| `future_pathway` PV siting 고정 | **조건부 분석**. 자유 siting 으로는 2030·2035·2040 이 모두 미수렴이었고, 처음 보고한 "2030 ESS=0"은 실제로 1.5 MW 였다. "그 PV 배치 하에서의 ESS 최적성"으로 한정 서술할 것 |
| 침투율 패널 | curtailment ≈ 0 → 폐기 또는 역송한계 재설정 후 재생성 |
| FR 임계값 세분화 | 11,000~12,000 구간을 더 좁히려면 11,500 등 추가 |
| 권장 추가 진단 | `fr_util_factor`(발동계수 μ) 민감도 — 현재 0.25 는 stylized 가정이고 FR 임계값이 이 값에 직접 의존한다 |

---

## 6. 재실행 방법 (새 환경에서 필요할 때만)

```
py run_scenario.py --scenario cired_deterministic cired_rep24 cired_stochastic
py analysis/ess_diagnosis.py                                  # 진단 A~D
py analysis/ess_diagnosis.py --only E --out diagnosis_capex_only.csv
py analysis/ess_diagnosis.py --only F --out diagnosis_fr.csv --time_limit 5400
py analysis/compare_scenarios.py --base cired_rep24 --analyses lambda alpha --fix_siting cired_rep24
py analysis/pv_penetration_sweep.py
py figures/make_det_vs_stoch_fig.py                          # Fig.5 (재풀이 없음)
py analysis/future_pathway.py --fix_pv_siting --out_suffix _fixpv

# 2040 만 시간제한을 늘려 재실행 (미확정 항목 해소용) — 3시간, gap 0.005
py analysis/future_pathway.py --years 2040 --redo --fix_pv_siting --out_suffix _fixpv \
   --time_limit 10800 --mip_gap 0.005
```

**2040 재실행 시 주의**
- `--redo` 없이는 `pathway.csv` 체크포인트 때문에 **아무것도 풀지 않고 건너뛴다**.
  `--redo` 는 지정 연도 행만 지우고 나머지 연도(2030·2035·2050)는 그대로 보존한다.
- 판정 기준: 새 `cost_ESS_억` 이 `cost_noESS_억`(651.5) 보다 **낮으면** ESS>0 이 맞고,
  기존의 `ESS_MW=0` 은 미수렴 incumbent였다는 뜻이다. 두 값이 또 같고 상태가
  `maxTimeLimit` 이면 시간제한을 더 늘리거나, 아래 대안을 쓴다.
- **대안(훨씬 가벼움)**: ESS 후보를 한 노드로 제한해(다른 노드 `inv_ess` 를 0 고정) 풀면
  ESS 이진 11개 중 10개가 사라져 금방 끝난다. 그 값이 651.5 보다 낮으면
  "ESS=0 은 최적이 아니다"가 **증명**된다 (FR 진입은 위치 무관 — `docs/RESULTS.md` §2.6).
  전 구간 최적값이 필요하지 않고 0의 진위만 판정하려면 이 쪽이 효율적이다.

**주의**
- 순서 중요: `cired_stochastic`·`ess_diagnosis`·`compare_scenarios` 는 `cired_rep24` 결과를 읽는다.
- `py` 를 쓸 것 (`python` 은 WindowsApps 스텁). Python **3.14**, CPLEX **Studio2212**.
- ESS 가 실제로 진입하는 케이스는 분기탐색이 무겁다 → 시간제한을 넉넉히(`--time_limit`).
- λ·α 민감도는 **ESS 자유배치**여야 한다(`free_ess=True` 기본). rep24 의 ESS 가 0 이라
  ESS 까지 고정하면 분석이 무의미해진다.
- `grid.export_limit_mw` 는 `base.yaml` 에서 **null** 유지.

---

## 시간별 운전 그림 · 연간 에너지 흐름 Sankey (2026-09-21 추가, 지도 피드백)

### 왜 지금까지 없었나
`run_scenario.py` 는 시간별 변수 CSV 를 `output.save_variable_csvs` 가 **true 일 때만**
저장하는데, `base.yaml` 에 `output:` 섹션 자체가 없어 기본값 false 로 동작했다.
그래서 `outputs/<시나리오>/results/` 에는 `summary.json` 만 남아 있고 **시간별 데이터가
하나도 없다** → 시간별 그림도, 에너지 흐름도 사후 생성이 불가능했다.

이번에 `base.yaml` 에 `output.save_variable_csvs: true` 를 추가했다. **대상 시나리오를
한 번 다시 풀어야** 그림을 만들 수 있다 (기존 결과 CSV 가 없으므로).

### 실행
```
py run_scenario.py --scenario cired_rep24     # ← CSV 생성 목적의 1회 재실행 (필수)
py figures/make_flow_figs.py --scenario cired_rep24   # ← 재풀이 없음, 수초
```
결과:
- `outputs/<시나리오>/figs/hourly_dispatch.png` — 대표일 시간별 운전(전력·열·FR 예비력)
- `outputs/<시나리오>/figs/energy_flow_sankey.png` — 연간 에너지 흐름 [GWh/yr]
- `outputs/<시나리오>/results/annual_energy_flow.csv` — 그림의 원수치

### 코드
| 파일 | 역할 |
|---|---|
| `src/fig_makers/sankey_core.py` | 의존성 없는 Sankey 렌더러 (matplotlib 만, plotly 불필요) |
| `src/fig_makers/plot_flows.py` | 연간화·흐름 계산 + Sankey/시간별 그림 |
| `figures/make_flow_figs.py` | 드라이버. CSV 없으면 무엇을 실행해야 하는지 안내하고 종료 |

연간화는 `objective.py` 의 `weight = 365·PVIFA` 와 같은 일→연 환산을 쓰되, PVIFA 는
비용 할인계수이므로 **에너지 그림에는 적용하지 않는다**:
`E[MWh/yr] = Σ_s prob_s · Σ_t x[s,t] · 365`.

드라이버가 전력버스 수지(유입=유출)를 자동 검산해 출력한다. 합성 데이터 검증에서
전력버스·CHP·열버스 3건 모두 잔차 0 확인.

### 그림에서 읽히도록 만든 것 (심사 대응)
- **FR 예비력 패널**: rep24 는 ESS=0 이므로 "No ESS installed → no FR reserve offered"
  가 그대로 찍힌다. 결론의 시각적 근거.
- **Heat surplus 노드**: `dhn.py` 의 열균형이 **부등식(≥)** 이라 공급이 부하를 넘을 수
  있다. 그 잉여를 숨기지 않고 종단 노드로 명시했다.
- **Conversion loss 노드**: CHP·보일러 변환손실을 명시 (LHV 기준).
- 집합 수지에는 **계통 손실이 없다** — `balance.py` 는 무손실 수급식이고 손실은 LPF
  감도 제약으로 따로 처리한다. 그림 각주에 명시했다.
