# CIRED Multi-Energy System Planning

IEEE 33-bus 배전계통 + 지역난방망(DHN) 통합 **2단계 확률론적 CVaR 계획 모델**.
PV·ESS·CHP·TES·보일러·DHN 배관의 최적 입지·용량(siting & sizing)을 Pyomo MILP로 결정한다.
타겟: CIRED 2026.

- 1단계(투자): 설비 위치·용량 — 모든 시나리오 공통
- 2단계(운영): 시나리오별 시간대 급전 (선형 조류, DHN 열수지, SOC)
- 목적함수: 투자비 + 기대운영비 + λ·CVaR_α(운영비)  (15년 실질 NPV, [억원])
- 데이터: KPX 수요·태양광(2024–25), 한국지역난방공사 열수요(2022), SMP/REC

> 결과는 `docs/RESULTS.md`에 모두 정리되어 있으므로 재실행 없이 분석할 수 있다.
> 제출된 논문 PDF의 수치는 모델 버그 2건 수정 **이전** 값이다 (상세: `docs/RESULTS.md` §0).

## 폴더 구조

```
run_scenario.py               단일 진입점 — 시나리오 1개 풀이

analysis/                     추가 분석 (모델을 다시 푼다, CPLEX 필요)
  compare_scenarios.py        λ·α 민감도, 결정론 vs 확률론 비교
  pv_penetration_sweep.py     PV 침투율 sweep (역송한계 override)
  ess_diagnosis.py            ESS 경제성 진단 (가치곡선·단가 손익분기·FR 임계값)
  future_pathway.py           2030–2050 미래경로
figures/                      저장된 결과로 그림만 재생성 (재풀이 없음)
  make_det_vs_stoch_fig.py    Fig. 5 결정론 vs 확률론
  make_sensitivity_figs.py    λ·α 민감도 그림·포스터 그림
  make_flow_figs.py           연간 에너지 흐름(Sankey)·시간별 운전 그림

src/
  data_process/   데이터 로딩, 33-bus/DHN 네트워크, 시나리오 생성(rep24·MC)
  planning/       Pyomo 모델·제약(constraints/)·목적함수·솔버·결과 추출
  powerflow/      민감도 계수 기반 선형 조류 (LPF)
  fig_makers/     그림 생성
  utils/          config 로더, 로거, I/O
scenarios/
  base.yaml       모든 파라미터의 실제 값 (단일 소스)
  cired_*.yaml    논문 시나리오 (deterministic / rep24 / stochastic MC100)
  quick_season4   사계절 4시나리오 (PV sweep 기준)
  equipment/      파라미터 출처·근거 문서 (코드에서 로드하지 않음)
docs/
  HANDOFF.md      현재 상황·다음 할 일 (작업 재개 시 여기부터)
  RESULTS.md      모든 확정 수치
  ASSUMPTIONS.md  가정·한계
  paper/          논문 개정안(PAPER_REVISION.md)·참고문헌(references.bib)
  guides/         연구실 코드 규칙(PROJECT_GUIDE.md, PYOMO_PATTERNS.md)
data/             입력 시계열 CSV
outputs/          논문용 그림(png/pdf)·summary.json·분석 CSV (로그·엑셀은 미추적)
```

## 실행

```bash
pip install -r requirements.txt      # + CPLEX (base.yaml solver.name: cplex)

python run_scenario.py --scenario cired_deterministic cired_rep24 cired_stochastic
python analysis/pv_penetration_sweep.py
python analysis/compare_scenarios.py --base cired_rep24 --analyses lambda alpha --fix_siting cired_rep24
python analysis/ess_diagnosis.py
```

`cired_stochastic`과 `analysis/ess_diagnosis.py`는 `cired_rep24`의 siting을 읽으므로 rep24를 먼저 실행한다.
시나리오 1개당 CPLEX 기준 10–25분. CPLEX가 없으면 `solver.name`을 `cbc`/`glpk`로 바꿀 수 있으나 느리다.

## 문서

| 파일 | 내용 |
|---|---|
| `CLAUDE.md` | Claude Code 세션용 프로젝트 지침 (루트 유지 필수) |
| `docs/RESULTS.md` | 모든 확정 수치 (단일 소스) |
| `docs/ASSUMPTIONS.md` | 가정·한계 |
| `docs/paper/PAPER_REVISION.md` | 논문 절별 개정안, 영문 Abstract 초안, 심사 대응 |
| `docs/HANDOFF.md` | 현재 상황·다음 할 일 |
| `docs/guides/PROJECT_GUIDE.md`, `docs/guides/PYOMO_PATTERNS.md` | 연구실 코드 구조·Pyomo 작성 규칙 |
| `docs/paper/references.bib` | 참고문헌 |
