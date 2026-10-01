# CLAUDE.md — StockLens

Claude Code가 이 레포에서 작업할 때 먼저 읽는 파일이다. 짧게 유지한다.
영구 규칙의 원본은 `AGENTS.md`, 진행 기록은 `CURRENT_STATUS.md`다. 이 파일과
둘이 충돌하면 그 두 파일을 따르고, 이 파일을 고친다.

## 1. 사용자와 일하는 방식 (항상 지킬 것)

1. **git commit / push는 하지 않는다.** 코드·`CURRENT_STATUS.md` 변경은 working
   tree에만 하고, 끝나면 변경 파일 목록과 `git diff --stat`을 보여준다.
   커밋·푸시는 재훈이 직접 한다. 커밋 메시지 초안은 제안해도 된다.
2. **실행해야 할 것이 있으면 터미널 명령어를 그대로 붙여 넣을 수 있게 함께 준다.**
   레포 루트 기준, 필요한 환경변수 포함 (예: `STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/...`).
3. **실험마다 노션 페이지 제목용 영어 제목을 준다.** 핵심만, 최대 8단어.
   (예: `Risk overlay candidates on validation windows`)
4. 답변은 한국어. 직설적이고 기술적으로. 듣기 좋은 말보다 정확한 반대 의견.
5. 완료한 것 / 합의된 설계 / 계획 / 미결 질문을 구분해서 말한다. 확인하지
   않은 것을 구현됐다고 말하지 않는다. 이전 답이 틀렸으면 분명히 정정한다.
6. Codex 사용을 권하지 않는다 (사용자 환경에 없음).

## 2. 프로젝트 한 줄 요약

Kiwoom REST API 기반 한국 주식 **분석·추천** 시스템. 최종 목표는 투자성향 설문 →
개인화된 Top-N 추천 + 근거 설명. **실제 매수/매도 주문 기능은 만들지 않는다.**

현재 운용 경로: 고정 daily XGBoost(rank 타깃, `best_iteration` 9) → KOSPI200
시총 상위 50(`STOCKLENS_UNIVERSE=top50`) 중 top-10 → T+1 시가 진입, 5거래일 보유,
buffer 3.0. 설문(`scripts/survey.py`) → 프로필 재랭킹(`recommend.py --profile`).
최신 상태와 다음 과제는 `CURRENT_STATUS.md`의 마지막 항목을 본다.

## 3. 절대 깨면 안 되는 것

### 데이터 구간 잠금 (가장 중요)
- **forward holdout(2026-09-24~)은 1회뿐이다.** 읽을 수 있는 스크립트는
  `scripts/evaluate_forward_holdout.py` 하나뿐(항목 54). 다른 곳에서
  `select_segment(..., "forward")`를 부르면 `tests/test_run_ml_backtest_config.py`가 실패한다.
  forward를 여는 새 경로를 추가하지 말 것.
- daily test split(2023-07-01~2026-09-16)은 항목 41에서 이미 소진됨.
  test를 읽는 코드는 반드시 `src/eval/test_lock.confirm_final_test_use()`를 먼저 호출.
- 잠금 환경변수(`STOCKLENS_CONFIRM_FINAL_TEST`, `STOCKLENS_CONFIRM_INTRADAY_FORWARD`,
  `STOCKLENS_CONFIRM_INTRADAY_SEMI_HOLDOUT`)를 **에러를 없애려고 켜지 않는다.**
  켜야 하는 상황이면 멈추고 사용자에게 묻는다.
- 새 실험은 validation(walk-forward W1 2012~2015 / W2 2016~2019 / W3 2020~2023H1)
  만 사용. 분봉 dev(2025-09~2026-06)는 보고용.
- `reports/daily_picks/`(페이퍼 트레이딩 기록)를 보고 모델·전략을 바꾸지 않는다.

### 누수 방지
- 판단 시점 T의 feature는 T 종가까지의 정보만. 시계열을 섞지 않는다.
- 분할 상수의 단일 출처: `src/data/dataset.py`(daily), `src/data/intraday_split.py`(분봉).
  새 코드에서 날짜를 하드코딩하지 말고 여기서 import.
- 데이터 로딩은 `src/feature_selection/data_loading.py`(`load_split()`) 경유.
- 누수 가능성이 있는 변환에는 "미래 값을 바꿔도 결과 불변" 테스트를 붙인다.

### 실험 절차: 사전등록 → 실행 → 결과
- 새 실험은 먼저 `CURRENT_STATUS.md`에 새 항목으로 **사전등록**(목적, 후보, 평가 구간,
  판정 기준, 해석 한계, 구현 계획)하고, 결과를 보기 전에 고정한다.
- 결과를 본 뒤 판정 기준·후보·파라미터를 바꾸지 않는다. 결과는 같은 항목 아래
  추가 기록한다. 파라미터 그리드 탐색으로 결과에 맞추지 않는다.
- 비교는 항상 공용 엔진(`src/backtest/baseline.py`, `src/backtest/buffered.py`)과
  실제 거래비용으로. 평가 기준은 pooled RMSE가 아니라 횡단면 rank IC.
- 백테스트 동점 규칙(점수 동점이면 종목코드 오름차순)은 사전등록의 일부이므로 바꾸지 않는다.

### 보안 / git
- `.env`, 키, 토큰, 계좌번호를 코드·로그·출력에 넣지 않는다.
- 레포는 **public**. `data/raw/`, `data/processed/*.csv`, `data/user_profile.json`,
  `reports/runs/`, `*.log`는 커밋 대상이 아니다.
- `data/raw/kiwoom/ka10080/`(분봉)은 API가 약 1년치만 제공해서 **다시 받을 수 없다.**
  삭제·덮어쓰기·이동 금지.

## 4. 코드 작업 규칙

- 고치기 전에 실제 파일을 확인한다. `AGENTS.md`의 구조도는 의도일 뿐이고, 없는 모듈을
  중복으로 만들지 않는다.
- 최소한의 일관된 변경. 관련 없는 리팩터링·파일 수정 금지.
- feature는 scale-free만(가격 수준 feature는 종목 식별자 역할을 함). 선택된 feature는
  `src/features/engineering.py`의 상수가 단일 출처.
- Kiwoom 엔드포인트 필드명은 추측하지 말고 `config/kiwoom-rest-api-spec.json`에서 확인.
  API 코드는 `src/api/` 안에만. raw 응답과 정규화 데이터는 분리 저장.
- 구조적 문제는 일회성 패치가 아니라 공용 모듈·단일 출처·테스트로 막는다.
- 설명(Explanation)은 실제 점수를 만든 숫자로만. 근거를 지어내지 않는다.

## 5. 테스트

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q              # 전체 (testpaths = tests)
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_<module>.py   # 관련 테스트 먼저
```

- 네트워크는 반드시 mock. 실제 Kiwoom 키·실시간 데이터 없이 통과해야 한다.
- 새 기능에는 테스트를 같이 추가하고, `CURRENT_STATUS.md` 항목에 추가 개수와
  전체 통과 수를 기록한다.
- 테스트 통과가 금융적 타당성을 증명하지는 않는다.

## 6. 자주 쓰는 명령

```bash
# 야간 수집 (cron, 20시 이후) / 로그 확인
bash scripts/nightly_ingest.sh
tail -n 20 logs/nightly_ingest_$(TZ=Asia/Seoul date +%Y%m%d).log

# forward 분봉 커버리지 점검 (주 1회, forward를 '보는' 것이 아님)
STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/check_forward_minute_coverage.py

# 설문 → 추천
PYTHONPATH=. .venv/bin/python scripts/survey.py
STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/recommend.py --profile saved
```

## 7. 문서 역할

- `AGENTS.md` — 영구 규칙 원본 (길다; 필요한 절만 찾아 읽기. 특히 13 시계열 분할,
  14 누수, 22 백테스트, 23 생존편향, 42 test/forward 잠금).
- `CURRENT_STATUS.md` — 번호 매긴 작업 기록. 의미 있는 작업이 끝날 때마다 갱신.
- `README.md` — 사람용 개요·설치. `CODEX_CONTEXT.md` — 초기 배경 문서.
- 실험 결과 정리는 노션(사용자가 직접), 코드는 GitHub.
