# CLAUDE.md — 프로젝트 가이드 (세션 시작 시 필독)

IEEE 33-bus 전기 + DHN 열 통합 **2단계 확률론적 CVaR 계획** 모델 (PV·ESS·CHP·TES·보일러·DHN
최적 siting & sizing). 타겟: **CIRED 컨퍼런스**.

## ★ 작업 재개 시 읽는 순서
1. **`docs/HANDOFF.md`** — 현재 상황·챕터별 요약·다음 할 일 (**여기부터**)
2. `docs/RESULTS.md` — 모든 확정 수치 (단일 소스)
3. `docs/paper/PAPER_REVISION.md` — 논문 절별 수정안·Abstract 영문 초안·심사 대응
4. `docs/ASSUMPTIONS.md` — 가정·한계 / `docs/guides/PROJECT_GUIDE.md` — 코드 구조 규칙

## ★ 결과 분석·작성 시 (가장 중요)
- **결과는 이미 계산되어 있습니다. 재실행(solve) 불필요.**
- 분석/작성/논의는 **`docs/RESULTS.md`(커밋됨, 모든 최종 숫자)** + `outputs/<scenario>/results/summary.json`
  (로컬에 있을 때)를 **읽어서** 하세요.
- **시나리오를 다시 풀지 마세요** — 사용자가 "재실행/다시 돌려"라고 **명시적으로 요청할 때만** 풀이.
  (한 번 푸는 데 CPLEX + 10~25분. `outputs/`는 그림·summary.json·분석 CSV만 추적 → 수치는 docs/RESULTS.md 기준.)

## 환경
- 이 머신: **CPLEX 설치됨** (`C:\Program Files\IBM\ILOG\CPLEX_Studio2212\...`, PATH 등록),
  **Python 3.14** (`py` 런처로 실행 — `python`은 WindowsApps 스텁이라 실패),
  pyomo 6.10 ·numpy·pandas·matplotlib·pyyaml·openpyxl. `base.yaml`의 `solver.name: cplex`.
- CPLEX 없는 환경이면 분석만 가능(위 참조). 굳이 풀어야 하면 `solver.name: cbc/glpk`(느림).

## 실행 명령어 (재실행이 정말 필요할 때만)
```
py run_scenario.py --scenario cired_deterministic cired_rep24 cired_stochastic
py analysis/pv_penetration_sweep.py
py analysis/compare_scenarios.py --base cired_rep24 --analyses lambda alpha --fix_siting cired_rep24
py analysis/ess_diagnosis.py            # ESS 경제성 진단 (가치곡선·단가 손익분기·기본요금·MC100)
```
- 순서 중요: `cired_stochastic`(MC100)은 `cired_rep24`의 siting을 읽음(`siting_from`) → rep24 먼저.
- `analysis/ess_diagnosis.py`도 `cired_rep24` 결과에서 PV/CHP/TES siting을 읽음 → rep24 먼저.

## 시나리오 맵
- `cired_deterministic` 결정론 baseline · `cired_rep24` **본**(rep24 확률론) ·
  `cired_stochastic` MC100(siting_from으로 tractable) · `quick_season4` 빠른검증
  (`analysis/pv_penetration_sweep.py`의 기준 시나리오).

## 함정 (수정 금지/주의)
- `grid.export_limit_mw`는 **base.yaml에서 null** 유지. (1.0 넣으면 rep24 미수렴·MC100 실패.
  역송한계는 `analysis/pv_penetration_sweep.py`에서만 override.)
- 파라미터 실제값은 **base.yaml**에 있음 (`scenarios/equipment/*.yaml`은 출처 문서, 미로딩).
- 그림 라벨은 영문 (영문 논문).

## 현재 단계 (2026-09-03 갱신)
제출된 논문(`260701_CIRED_조아현_v5_최종.pdf`)과 코드를 대조 점검하다 **모델 버그 2건**을 발견해
수정·재실행했고, 그 결과 **논문의 헤드라인 결과가 유지되지 않는다**. 개정판 재업로드 준비 단계.

- **수정 1 — ESS·TES 일주기 SOC 종기조건**: `soc[23]`에 t=23 충·방전이 반영되지 않아 매일
  마지막 시각에 무상 방전이 가능했음. 논문 식 (6)은 원래 옳았고 코드가 어긋나 있었다.
- **수정 2 — PV 프로파일 정규화**: 각 날을 그 날의 최대로 정규화해(`arr/arr.max()`) 모든 대표일이
  '맑은 날'이 되고 일간 변동성이 소실됐음 → 발전량 1.7배 과대·σ 10배 과소. 설비용량 기준
  per-unit 정규화로 교체하고 σ를 일 총량 변동계수 기반으로 재산출.
- **결과**: ESS 최적값이 1.16 MW → **0**. 위험헤지는 전기 저장이 아니라 **CHP·TES(열 측)** 가 담당.
  상세 수치·근거·논문 개정 방안: `docs/RESULTS.md`, `docs/paper/PAPER_REVISION.md`.

**주의**: 논문 PDF의 수치는 모두 수정 전 값이다. 인용·재사용 시 `docs/RESULTS.md` 기준.
