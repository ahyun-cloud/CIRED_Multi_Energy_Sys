# 논문 개정 지침 (PAPER_REVISION)

> 대상: `260701_CIRED_조아현_v5_최종.pdf` (CIRED 2026 Seoul Workshop, 2026-11-02~03 제출본)
> 근거: `docs/RESULTS.md` (2026-09-03 재실행), 코드 `main` + 버그 수정 2건
> 상태: 제출 완료 · **개정판 재업로드 가능** → 아래 순서로 수정

---

## 0. 한눈에

**바뀌는 것**: Results(§3)와 Conclusion(§4) 전체, Abstract, Table 1~2, Fig. 2~7, §3.1의 사실 오류 몇 곳.
**그대로 남는 것**: Title, §1 Introduction, §2 Methodology **전체(식 (1)~(7) 포함)**, 참고문헌.

논문 식 (6)은 `soc[t+1] = soc[t] + η·p^ch[t] − p^dch[t]/η`로 **원래 옳게** 적혀 있었고
어긋난 쪽이 코드였다. 수정으로 코드가 논문 식을 따라오게 되었으므로 **수식은 손대지 않는다.**

제목의 "PV-ESS-CHP"도 유지 가능하다 — ESS는 여전히 의사결정 변수이고, 그 최적값이 0으로
나온 것이 결과다. 다만 Abstract·Conclusion에서 그 사실을 명확히 해야 한다.

---

## 1. 개정 원칙 — 서사 전환

| | 기존 논문 | 개정판 |
|---|---|---|
| 헤드라인 | 불확실성을 고려하면 ESS가 0 → 1.16 MW | **위험회피가 늘리는 것은 열 측 유연성(CHP·TES)이며, 배전급 ESS는 현 시장 신호에서 도입되지 않는다** |
| 근거 | VSS가 양(+) | 결정론 → 확률론에서 CHP +23 %, TES 0 → 11.52 MWh, ESS 0 → 0 |
| 위험의 소재 | 전기 측 | **열 측**(부호 반대) |
| 기여 | 통합계획에서 ESS 최적 배치·용량 | **다중에너지 계통에서 어떤 자원이 꼬리위험을 흡수하는가 + 배전급 ESS의 도입 조건(손익분기 단가)** |

**핵심 논리 (새 서사의 뼈대)** — 이 문단을 §3.2 또는 §4에 넣으면 결과 전체가 하나로 설명된다.

> 이 모델이 표현하는 불확실성은 수량 위험(PV 출력·전기·열 수요)이다. PV가 부족한 날의 위험은
> 에너지가 모자란 위험이므로, 이를 헤지하려면 에너지를 **생산**하는 자원이 필요하다. ESS는
> 하루 안에서 에너지를 **이동**시킬 뿐이므로 이 위험을 헤지할 수 없고, 가스를 연소해 전기와 열을
> 동시에 생산하는 CHP와, 그 열을 시간이동시키는 TES가 자연스러운 헤지 수단이 된다. 저장장치가
> 잘 헤지하는 위험은 가격 위험인데, 본 모델의 수전 단가는 규제 요금(한전 TOU)이라 확률변수가
> 아니다. 따라서 저장장치가 헤지할 위험이 불확실성 집합에 존재하지 않는다.

이 논리는 한계와 향후 연구를 동시에 제공한다 → SMP·요금 불확실성 도입이 최우선 확장.
논문 참고문헌 [2]가 이미 SMP 변동성(LNG 연동) 연구이므로 서사가 자연히 이어진다.

---

## 2. 절별 수정안

### 2.1 Abstract — 전면 재작성

**삭제할 문장 3개**

1. *"Accounting for uncertainty raises the optimal ESS from virtually zero to 1.16 MW, located at
   the same bus as CHP"* → 재실행 결과 ESS는 결정론·확률론 모두 **0**.
2. *"a deterministic (expected value) plan omits this storage, so the stochastic model yields a
   positive value of the stochastic solution, i.e., a lower expected cost under uncertainty"*
   → VSS를 계산하지 않았고, 투자+기대운영도 결정론 425.5 vs 확률론 427.0으로 확률론이 **더 높다**
   (그 대가로 CVaR을 낮춤). 표현 자체가 성립하지 않는다.
3. *"With higher risk aversion, ESS increases much more than CHP, indicating that risk is
   concentrated on the electricity side"* → 부호가 반대.

**대체 문안 (초안)**

> This paper proposes a two-stage stochastic conditional value-at-risk model for the optimal siting
> and sizing of electricity–heat coupled flexibility resources on the IEEE 33-bus network integrated
> with a district heating network, embedding linearized power-flow constraints and Korean market
> signals. Under measured PV variability, the optimal plan installs no distributed battery storage:
> the tail risk of operating cost is driven by energy quantity rather than price, and is hedged by
> dispatchable heat-and-power resources. Moving from the expected-value plan to the risk-averse
> stochastic plan raises CHP capacity by 23 % and introduces 11.5 MWh of thermal storage, while
> battery capacity remains zero; with a 100-scenario Monte Carlo set that reproduces the measured
> daily PV variability, thermal storage grows further to 17.3 MWh and battery capacity is still zero.
> A forced 1.16 MW battery raises total cost by 0.75 billion KRW while reducing the expected peak
> demand by only 73 kW — 6 % of its rating — because the CHP installed for heat already caps the
> residual peak import at 0.94 MW on a 3.7 MW feeder. Doubling the demand charge does not introduce
> storage either; it expands CHP instead. Halving the battery capital cost does not change the
> outcome, so the binding obstacle is not capital cost but the absence of a value stream that
> storage can capture: the regulated import tariff removes price risk from the uncertainty set,
> and frequency-regulation remuneration barely exceeds the cycling degradation cost.

**★ "손익분기 단가" 표현은 쓰지 말 것.** 진단 E(`docs/RESULTS.md` §2.5)에서 `c_deg`를 고정한 채
capex만 ×0.50(100,000원/kWh)까지 낮춰도 ESS는 **0**이며 proven optimal이다. 진단 B(§2.2)의
140,000원/kWh 진입은 capex 효과가 아니라 **FR 용량요금 수익이 열린 결과**이고, `base.yaml`이
FR 순단가를 현재 `c_deg` 기준 손익분기(`c_deg·μ = 8,333 ≈ fr_cap_price 8,500`)에 맞춰 둔 설정에
의존한다. 결정적 증거: ESS 총량이 세 케이스 모두 정확히 2.0 MW = `fr_total_cap_mw` 상한.

따라서 논문의 메시지는 **"더 싸지면 된다"가 아니라 "값을 받을 수익원이 있어야 한다"** 이다.

### 2.2 §1 Introduction — 문장 두 곳만

- *"it quantifies the value of the stochastic solution"* → *"it quantifies which flexibility resource
  absorbs operating-cost tail risk, and the cost condition under which distributed storage enters
  the optimal plan"*.
- 잉여 PV·출력제한 동기(*"surplus generation"*)는 유지해도 되지만, **본 시나리오의 curtailment는
  0 %**(역송 무제한)이고 출력제한 논의는 역송한계 1.0 MW를 가정한 별도 분석에서만 성립함을
  §3에서 명시할 것. 서론에서 과하게 예고하지 않는 편이 안전하다.
- 나머지(NDC·2050 목표, 제주 curtailment [1], SMP 변동성 [2], 선행연구 [3]~[7], 연구 gap 진술)는
  **그대로 유지**.

### 2.3 §2 Methodology — 한 문장만

§2.3의 *"The state of charge considers the two-way efficiency (6), with 50% initial SOC for daily
cycling."* 에 종기 조건을 명시:

> The state of charge follows (6) with the two-way efficiency, and the daily cycle is closed by
> requiring the end-of-day state — i.e. the state after the last hour's charging and discharging —
> to return to 50 % of the installed energy capacity.

식 (1)~(7), CVaR 선형화, LPF 감도 정식화, DHN 선형화 서술은 **수정 불필요**.

### 2.4 §3.1 Parameter Settings — 사실 오류 5건

| 원문 | 문제 | 수정안 |
|---|---|---|
| *"Excluding the slack bus, the 32 buses are PV/ESS candidates"* | ESS 후보는 `base.yaml`에서 11개로 제한 | *"the 32 non-slack buses are PV candidates, and 11 buses with peak load ≥ 100 kW are ESS candidates"* + 축소 근거(피크저감·전압지지 가치가 대형 부하노드에 집중, MILP 수렴성) |
| *"Profiles are normalized from KPX PV, KEPCO demand, and KDHC heat data scaled by peak loads"* | **전기부하 형상은 실측이 아니라 하드코딩된 평일/주말 2개 곡선.** KPX 수요 데이터는 월별 σ 산출에만 사용 | *"PV and heat profiles are derived from KPX and KDHC measurements; the electrical load shape uses typical weekday/weekend curves, with KPX demand data used to estimate monthly variability"* |
| *"the export price equals the SMP"* | 실측 SMP 시계열이 아니라 계절×시간대 3구간 전형값 | *"the export price approximates the SMP by season and time-of-use block"* |
| *"Costs use an NPV basis (real rate r, horizon N)"* | 값이 본문에 없음 | *"real discount rate 4.5 % over a 15-year horizon (PVIFA = 10.74); capex at t = 0 undiscounted"* 명기 |
| PV 프로파일 정규화 서술 없음 | ② 수정으로 규약이 바뀜 | **새 문장 추가**: *"Hourly PV profiles are normalized by the annual maximum fleet output as a proxy for installed capacity, preserving day-to-day energy variability; the resulting yield is 1,654 kWh/kWp/yr (capacity factor 18.9 %) and the log-normal scale parameter is matched to the measured coefficient of variation of daily energy (0.43)."* |

### 2.5 §3.2 Baseline Results — 전면 교체

**Table 1 교체** (버스 번호는 내부 0-indexed **+1**):

| Resource | Bus | Capacity |
|---|---|---|
| PV | 27, 28, 29, 30 | Total 3.3 MWp (0.3 / 1.0 / 1.0 / 1.0) |
| ESS | — | **Not installed** |
| CHP | 7, 8, 24 | 1.0 / 0.735 / 0.478 MWe (2.213 MWe total) |
| TES | 7, 8, 24 | 2.71 / 5.86 / 2.95 MWh_th (11.52 MWh_th total) |
| Boiler | — | Not installed |

**수정할 문장**

- *"converges to a total annualized cost of 47.84 billion KRW"* → **59.44 billion KRW as a 15-year
  NPV**, 그리고 이 값이 λ·CVaR 항(16.74 billion)을 포함한 목적함수값임을 명시. 결정론과 비교할
  때는 투자 + 기대운영(42.55 vs 42.70 billion)을 쓸 것.
- *"PV is placed at the downstream buses …, which locates generation near the loads to **reduce line
  losses** and reverse power flow…"* → **손실 문구 삭제.** 목적함수·수급식에 손실항이 없다.
  나아가 **PV 배치를 결과로 주장하지 말 것** — 수정 과정에서 PV 노드가 네 번 모두 다르게 나왔다
  (`docs/RESULTS.md` §1 헤드라인 4). *"the total 3.3 MWp is allocated among candidate buses subject to
  the voltage constraints; because network losses are not priced in the single-substation settlement,
  the allocation is nearly degenerate and is not interpreted as a result"* 정도로 한정.
- *"The ESS is placed at Bus 7 that also has CHP, which concentrates the flexibility resources and
  improves electricity–heat coordination."* → **문단 삭제** (ESS 미설치).
- *"No boiler is installed, because CHP and TES alone meet the whole heat demand…"* → **유지**.
  siting 고정 실험에서도 보일러는 자유변수였고 모든 케이스에서 0이었다(견고).
- *"The nodal voltage stays within [0.95, 1.05] p.u. at all buses and time steps (Fig. 4)"* → 유지.
  단 *"which confirms the feasibility"* 이상의 의미(전압이 계획을 제약했다는 식)는 부여하지 말 것.

**결정론 vs 확률론 비교 (Fig. 5 재작성)** — 이제 ESS가 아니라 CHP·TES를 비교해야 한다.

| | 결정론 | rep24 확률론 |
|---|---:|---:|
| 투자 + 기대운영 | 42.55 bn | 42.70 bn |
| CVaR (운영비) | — | 33.49 bn |
| ESS | 0 | **0** |
| CHP | 1.803 MWe | **2.213 MWe (+23 %)** |
| TES | **0** | **11.52 MWh_th** |

핵심 문장: 결정론 해는 축열조를 **전혀** 설치하지 않고, 위험을 명시적으로 가격화한 확률론 해만
설치한다 → 열 측 저장이 꼬리위험 헤지 수단임을 보인다.

**MC100 비교 (구 Table 2)** — 재실행 후 작성. 두 가지 주의:
1. 기존 설정은 `siting_from`으로 **rep24의 siting을 그대로 물려받으므로** "rep24가 MC100을 재현한다"는
   siting에 대해서는 순환논리다. 반드시 *"for the siting obtained from rep24"*로 한정할 것.
2. §4의 *"within about 2 % in both cost and ESS capacity"*는 사실이 아니었다 — 비용은 1.9 %였지만
   ESS는 +8.8 %, TES는 +56 %였다. 재실행 후 항목별로 다시 확인해 서술할 것.

### 2.6 §3.3 Sensitivity Analysis — 재실행 완료 (2026-09-04)

확정 수치는 `docs/RESULTS.md` §4.1. 서술 요지:

> As the risk-aversion weight λ increases from 0 to 2, pre-emptive investment rises from 14.05 to
> 14.33 bn KRW while both the expected operating cost and its CVaR fall (28.62 → 28.41 and
> 33.72 → 33.42 bn KRW). The trade-off reported in the original submission therefore holds, but the
> instrument is CHP (2.10 → 2.29 MWe, +9 %) rather than battery storage, which stays at zero
> throughout. The confidence level α has almost no effect: with 24 representative days the
> probability of a single weekday scenario is 22/365 = 0.060 > 0.05, so for α ≥ 0.94 the tail
> collapses to one worst-case day and the α-sensitivity is structurally suppressed.

**침투율 패널은 폐기 또는 재설계**: PV 발전량 보정으로 7.7 MWp에서도 curtailment가 0.27 %
(수정 전 21.1 %)여서 "고침투 잉여흡수" 서사가 성립하지 않는다. 유지하려면 역송한계를 더 강하게
(0.5 MW 등) 가정해 다시 만들고, ⑴ 그 가정이 이 분석에만 적용된다는 점과 ⑵ 기준 시나리오가
rep24가 아니라 사계절 4시나리오라는 점을 반드시 명시할 것.

### 2.6b 이전 주의사항 (해소 여부)

- **CHP 상한 결착**: λ·α 민감도는 siting을 rep24 해로 고정하고 돌리므로, 선택된 CHP 노드의
  노드당 상한(1.0 MWe)이 CHP 총량의 상한이 된다. 기존 결과의 CHP 2.000 MW는 그 상한과 정확히
  일치했다 → *"ESS increases far more than CHP"*라는 비교는 성립하지 않았다. 개정판에서는
  상한 결착 여부를 그림에 점선으로 표시하거나 서술로 명시할 것.
- **α 이산화**: rep24 평일 시나리오 하나의 확률이 22/365 = 0.0603 > 0.05 = 1−α이므로
  **α ≥ 0.94에서 꼬리가 단일 최악 시나리오로 붕괴**한다. "α는 부차적, λ가 지배적"이라는 결론은
  유지해도 되지만 이유를 바꿔 쓸 것: *"with 24 representative days the tail at α ≥ 0.94 collapses to
  a single worst-case day, so the α-sensitivity is structurally suppressed; a denser scenario set
  would restore it."*

### 2.7 §4 Conclusion — 전면 재작성

**새 three main findings (초안)**

1. **저장장치는 도입되지 않으며, 그 이유는 CHP의 구축(crowding-out) 효과다.** Under measured PV
   variability no distributed battery enters the optimal plan, for either the 24 representative days
   or the 100-scenario Monte Carlo set. A forced 1.16 MW battery raises total cost by 0.75 bn KRW
   while cutting the expected peak by only 73 kW (6 % of its rating), because the CHP installed to
   serve heat already caps the residual peak import at 0.94 MW on a 3.7 MW feeder. Doubling the
   demand charge expands CHP (2.21 → 2.30 MWe) rather than introducing storage.
2. **위험은 열 측에서 흡수된다.** CHP rises 23 % (1.80 → 2.21 MWe) and 11.5 MWh_th of thermal
   storage appears, whereas the expected-value plan installs none. As the scenario set becomes more
   variable (rep24 → MC100, CVaR 33.5 → 37.7 bn), thermal storage grows further to 17.3 MWh_th while
   battery capacity stays at zero. No boiler is needed because CHP and TES cover the heat demand
   including the worst-case scenarios.
3. **막는 것은 자본비가 아니라 없는 수익원이다.** Halving the battery capital cost (to
   100,000 KRW/kWh, with the cycling degradation cost held fixed) leaves the optimal battery
   capacity at zero. Storage enters only once the reserve capacity payment exceeds about
   11,000–12,000 KRW/MW/h — roughly 1.3–1.4 times the current KPX level — and it is then sized
   exactly to the reserve procurement limit at locations that vary arbitrarily between cases.
   Distribution-level storage in this system is therefore an ancillary-service asset, not a
   peak-shaving or hedging asset. The same mechanism reappears along the 2030–2050 pathway: as the
   carbon price displaces the gas CHP (2.00 → 0 MWe) and the cycling degradation cost falls,
   storage grows from 1.50 to 2.48 MW.

**한계 절 보강** (현재는 LPF 근사와 대표일 처리 두 줄뿐). 최소 다음 4개 추가:

- **가격 불확실성 부재** — 수전 단가가 규제 요금이라 확률변수가 아니고 MC100도 수출 SMP만 교란한다.
  저장장치가 헤지하는 위험이 모델에 없으므로 본 연구의 ESS 결과는 **수량 위험 하의 결론**으로
  한정된다. 향후 SMP·요금 불확실성 도입 시 저장 가치는 커질 방향이다.
- **계통손실·전류한계 미반영** — 손실이 목적함수에 없어 배치가 총 수전량에 영향을 주지 않으며,
  `I_max = 1.0 pu`(456 A)는 피크 3.715 MW 피더에서 non-binding이다.
- **PV 총량 외생 고정** — 보정된 발전량으로도 REC 수익만 MWp당 1.24 bn(capex 1.16 bn)이라 PV는
  상한까지 짓는 것이 최적이다. 3.3 MWp는 부지·계통연계 제약을 반영한 **정책 시나리오 변수**다.
- **기본요금 근사** — 실제는 월 최대수요 기준인데 대표일 피크×12개월로 근사했다. `p_peak`가
  볼록함수이므로 청구액을 구조적으로 과소평가하며, 이는 ESS에 불리하게 작용한다.

기존 향후 연구(비선형 AC 조류, 보조서비스 수익, 2030~2050 연도별 투자)는 유지하되
**가격 불확실성 도입을 1순위로** 올릴 것.

### 2.8 그림·표 체크리스트

| 항목 | 조치 |
|---|---|
| Fig. 1 (flowchart) | 유지 |
| Fig. 2 (대표일 프로파일) | **재생성** — ② 수정으로 PV 형상·수준이 크게 바뀜(peak 0.98 → 0.56) |
| Fig. 3 (배치도) | **재생성** — ESS 없음, CHP 3노드, TES 3노드 |
| Fig. 4 (전압 3D) | **재생성** |
| Fig. 5 (det vs stoch) | **재작성** — 비교 대상을 ESS에서 CHP·TES로 |
| Fig. 6 (λ) | 재실행 후 재생성 + 상한 표시 |
| Fig. 7 (α) | 재실행 후 재생성 + 이산화 각주 |
| Table 1 | 위 §2.5 표로 교체 (버스 번호 +1) |
| Table 2 (det/MC 비교) | 재실행 후 작성 |

**버스 번호 주의**: 코드는 0-indexed 노드를 쓰고 스스로 `Bus = node + 1`로 출력한다. 기존 Table 1의
숫자는 내부 인덱스였다. 그림 라벨도 같이 확인할 것.

---

## 3. 재실행 체크리스트 (순서 중요)

```
py run_scenario.py --scenario cired_deterministic     # 완료 (2026-09-03)
py run_scenario.py --scenario cired_rep24             # 완료 (2026-09-03)
py analysis/ess_diagnosis.py                                   # ESS 진단 (A/B/C/D)
py run_scenario.py --scenario cired_stochastic        # MC100 — rep24 이후
py analysis/compare_scenarios.py --base cired_rep24 --analyses lambda alpha --fix_siting cired_rep24
py analysis/pv_penetration_sweep.py                            # 역송한계 1.0 MW 가정 분석
```

각 단계 후 `docs/RESULTS.md`를 갱신할 것. `outputs/`는 gitignore이므로 숫자는 `docs/RESULTS.md`에만 남는다.

---

## 4. 심사·질의 대응 준비

| 예상 질문 | 대응 |
|---|---|
| "ESS가 0인데 왜 제목에 ESS가 있나" | ESS는 의사결정 변수이고 그 최적값이 0으로 나온 것이 결과다. 아울러 손익분기 단가를 제시해 *언제* 도입되는지 답한다. |
| "저장장치 가치가 과소평가된 것 아닌가" | 그렇다 — 가격 불확실성이 모델에 없고 기본요금을 대표일 피크로 근사했으며 ESS만 현재 단가를 썼다(다른 자원은 2030 전망). 세 요인 모두 ESS에 불리한 방향이며 한계로 명시했다. 이 조건에서도 **열 측 헤지 우위**라는 정성적 결론은 유지된다. |
| "PV 발전량 1,654 kWh/kWp/yr의 근거" | KPX 2024 실측 시간출력을 연중 최대출력(설비용량 프록시)으로 정규화. 이용률 18.9 %로 전국 실측(~15 %)보다 다소 높으며, 프록시가 실제 설비용량보다 작기 때문임을 명시. |
| "왜 대표 24일인가, MC100과 다르지 않나" | 계산 효율. 단 rep24는 월×요일 평균이라 일간 변동이 들어가지 않으므로 일간 불확실성은 MC100에서 평가했다고 정직하게 서술. |
| "TES 11.52 MWh는 견고한가" | 절대값은 약하게 결정된다(자유 siting 11.52 vs siting 고정 15.89가 거의 동일 비용). 정성적 방향(결정론 0 → 확률론 다량)은 견고하다고 한정. |
| "상한이 결과를 만든 것 아닌가" | 이전 결과의 CHP 2.000 MW는 노드당 상한과 정확히 일치했으나 개정판은 3노드 2.213 MW로 상한에서 벗어났다. ESS 노드당 상한 1.5 MW는 ESS가 0이므로 무관. 모든 상한과 근거는 `base.yaml`에 문서화. |

---

## 5. 우선순위

1. **초록·§4 재작성** — 방향이 반대이므로 가장 먼저.
2. **§3.1 사실 오류 5건 수정** — 수치 확정과 무관하게 지금 가능.
3. **Table 1 · Fig. 2~5 교체** — 확정된 결과로 가능.
4. **진단 결과 반영** — 완료(2026-09-03). 초록·§4 초안에 A~E 수치 반영됨.
   추가로 권장: capex 고정·FR 정산단가만 sweep 해 **FR 임계값**을 구하면 정책 인용에 가장 좋다
   (`docs/RESULTS.md` §2.5 말미).
5. **§3.3 · Table 2 · Fig. 6~7** — MC100·민감도 재실행 후.
