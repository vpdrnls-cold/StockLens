StockLens Current Project Status

  이 파일은 변경 가능한 프로젝트 상태 기록이다. 의미 있는 구현 작업이
  끝날 때마다 갱신한다. 영구적인 개발 규칙은 이 파일이 아니라
  AGENTS.md에 둔다.

------------------------------------------------------------------------

1. Current Project Goal

StockLens는 개인화된 주식 분석/추천 시스템으로 개발 중이다. 실제 매수/매도 주문 기능은 만들지 않는다.

최종 제품 목표: 투자성향 설문 → 시장 정보로 종목 분석 → 종목별 신호/예측 → 성향에 맞춘 개인화 랭킹 →
설명이 포함된 Top-N 추천 + 보유 종목 HOLD/SELL 판단.

------------------------------------------------------------------------

2. Current Status (2026-10-06 기준, 항목 65~76 반영)

단계: **Research / Validation**. Pre-production 아님. 실자금 투입 근거 없음.

운용 경로(고정, forward 평가 전까지 변경 금지):
-   데이터: Kiwoom 일봉(ka10081, 수정주가), KOSPI200 시총 상위 50(`STOCKLENS_UNIVERSE=top50`,
    2026-09-21 기준 — 생존편향).
-   타깃: `close(T+5)/open(T+1)-1`의 날짜별 rank(`entry="next_open"`, 항목 44).
-   모델: XGBoost, train 2002-10-29~2019-12-31, validation 2020-01-01~2023-06-30로 IC 조기종료,
    `tree_method="exact"`, `n_jobs=1`. best_iteration 9, 트리 지문 `config/frozen_daily_model.json`(항목 65).
    19개 feature를 넣지만 실제로 쓰는 것은 4개(`price_to_sma_5`, `return_20d`, `price_to_sma_20`,
    `high_low_range`) — 사실상 단기 반전 규칙. 하루 점수 ≈ 8종류라 상위권 동점이 많음(동점 → 종목코드 오름차순).
-   전략: top-10 동일가중, T+1 시가 진입, 5거래일 보유, buffer 3.0(보유 종목은 30위 안이면 유지), 실제 비용.
-   리스크 관리: 없음(항목 55 후보 전부 탈락, R0). HOLD/SELL 손절 레이어는 운용 경로에 연결되지 않음.
-   추천 CLI: `scripts/recommend.py`(그날 순위 top-10 + 이전 로그를 재생한 buffer 전략 보유 종목, 항목 66),
    설문 `scripts/survey.py` → `--profile saved`.

검증 상태(항목 65 감사):
-   운용 구성은 깨끗한 표본 밖 데이터로 평가된 적 없음. daily test(2023-07~2026-09)는 항목 14·15·30·31·34·41에서
    소진됐고, 항목 41의 test 결과(+311%)는 다른 구성(close 타깃·top_n=2·buffer 없음)의 숫자.
-   validation W1~W3는 10개 이상의 결정에 재사용 + 조기종료와 성과 보고를 같은 구간에서 함 → in-sample.
    W3 순누적 +65.0%는 리밸런싱 시작일 5가지 중 최댓값(−9.4%~+65.0%, 항목 65). 시작일 평균으로는 W3에서
    유니버스 동일가중(비용 없음)보다 −25.3%p 뒤짐, W1 +30.3%p, W2 +14.9%p, dev +1.6%p(항목 66).
-   분봉 dev(2025-09~2026-06, daily 모델 입장에서 표본 밖): daily IC −0.0041, buffer 순수익 +54.7% <
    유니버스 동일가중(비용 없음) +57.6%.
-   신호 크기는 감쇠 중: rank IC W1 0.066 → W2 0.046 → W3 0.022 → dev −0.004.
-   종목 holdout(항목 79, 학습에 안 쓴 KOSPI200 150종목): test 기간 IC +0.026(t 2.05) → 일반화 지지, 연도별 모두 양수.
    단 top-10 buffer 전략은 모든 구간에서 150종목 동일가중에 크게 뒤짐(P −51.7%p) — 순위 신호와 롱온리 수익은 별개.

분봉 오버레이(w=0.5)는 후보. forward(2026-09-24~) 판단일 60개 이상 쌓이면 `scripts/evaluate_forward_holdout.py`로
1회 평가(2027-01 첫 주 전후). 판정(D2·I6)은 기록하되 forward 단독으로 운용 경로를 바꾸지 않고 forward2에서도
같은 방향일 때만 반영(항목 53·65).

수집(모두 모델 미사용 — 운용 경로는 일봉 top50만):
-   KOSPI200 전체 200종목(`kospi200`, top50 포함): 일봉·분봉·수급을 야간 수집(항목 68). 추가 150종목은 데이터 확보만,
    이번 사이클의 어떤 실험·판정에도 쓰지 않음.
-   지수 KOSPI·KOSPI200(ka20006), 종목별 수급(ka10059, 2006~).
-   DART 공시 목록(200종목, 최근 40일 증분, 항목 72), ECOS 금리 4종·원/달러(2000~, 항목 74),
    뉴스 제목(NAVER API HUB, top50 종목당 최신 1,000건, 항목 75 — 지난 기사는 나중에 못 받음, 원본 백업 포함).
-   FRED는 보류(T−2 시점 규칙, 항목 59).

분석가 패널(제품 레이어, AGENTS 43절 — 추천은 퀀트만, 나머지는 "모델 미사용" 참고 정보):
-   카드 5종 JSON `reports/analyst_cards/<T>/`: 퀀트(`recommend.py`, 순위·TreeSHAP 근거·전략 보유, 항목 69),
    차트(상태 5개 + 과거 통계 + 수급, 항목 61), 공시(최근 30일 목록·정정·DART 링크, 항목 72),
    뉴스(최근 3일 — 잡음 제외 후 같은 사건을 이슈로 묶어 보도 매체 수 순, 항목 75·76), 시장(지수·금리·환율·대형주 수급, 항목 74).
    좋고 나쁨 판정·종합 점수 없음.
-   뷰어 `app/viewer.py`(Streamlit, 별도 `.venv-ui`, 읽기 전용, 가격·수익률 미표시): 시장 박스 + 보유·상위 10 목록 +
    종목별 전문가 박스(퀀트·차트·공시/뉴스) 요약과 아래 전체 폭 상세(항목 70·73).
-   금요일 야간 수집이 로그·카드를 자동 생성. `recommend.py`는 그날 로그가 있으면 덮어쓰지 않음(종료 코드 3),
    카드만 다시 만들 때는 `--cards-only`(항목 71).

테스트: 전체 406개 통과(항목 76 기준, `pytest.ini`로 `tests/`만 수집).

------------------------------------------------------------------------

3. Known Open Issues

-   forward 판정 검정력이 거의 없음(SE(IC) ≈ 0.06) — "기각되지 않음"은 증거가 약함(항목 65).
-   모델 해상도(점수 8종류, 동점)와 학습 데이터 노후(2019년까지 fit). 다음 사이클 과제.
-   경로 잡음: 동점 처리 순서(±18~29%p)와 리밸런싱 시작일(W3 −9.4%~+65.0%)이 백테스트 수익률을 크게 바꿈.
-   생존편향(현재 대형주 50개를 과거에 적용), 018260의 상장 전 K-OTC 구간이 학습 데이터에 포함(항목 58).
-   페이퍼 로그의 전략 보유는 이전 로그 재생으로 계산(항목 66). 주 1회 기록이라 엔진의 5거래일 일정과 조금 다름.
-   일봉에 미완성 표시 없음, 당일 확정 시각(`SESSION_FINAL_TIME_KST`) 임시값 18:00(항목 64 측정 대기).
-   split 사이 라벨 purge: `split_by_time(purge_days=...)` 옵션은 추가했으나 고정 모델은 0 유지(다음 사이클부터).
-   운용 코드가 `scripts/run_ml_backtest.py`에 있고 여러 스크립트가 import함, `WINDOWS`·비용 상수 중복.
-   뉴스 카드: 대형주는 하루치도 일부만 수집(검색 API 한도), 짧은 종목명(LG·SK)은 계열사 기사 포함, 이슈 묶기는
    제목 유사도라 드물게 갈리거나 섞임(항목 75·76). 뉴스·분봉은 맥이 꺼져 있던 날의 데이터가 영구히 빠짐.
-   분석가 카드는 실제 금요일 판단일(10/9) 화면을 아직 보지 못함 — 10/2 카드는 뉴스 수집 전이라 대부분 빈 상태.

------------------------------------------------------------------------

4. Next Steps (우선순위 순)

1.  항목 64 측정(10/6·10/7): 20:30 cron 스냅샷 + 다음 날 `snapshot --date` → `compare` → 규칙대로 확정,
    cron 측정 줄 삭제. 다음 사이클 사전등록 초안은 항목 67(forward 평가 후 확정, 미결 질문 3개).
2.  10/6 밤 첫 확장 야간 수집 로그 확인(분봉 200·수급·DART·ECOS·뉴스 단계), 10/9(금) 뒤 자동 생성된 카드 5종과
    뷰어 실제 화면 확인 → 불편한 점 수정.
3.  데이터 수집 유지: 야간 수집(cron) 확인(20:37에 맥이 깨어 있어야 함), 주 1회
    `STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/check_forward_minute_coverage.py`.
    10일 넘게 비우지 않는다.
4.  평가 전 환경 고정(12월): xgboost 등 라이브러리 변경 금지 — 트리 지문이 달라지면 forward 평가가 멈춤.
5.  forward 평가 1회(2027-01 첫 주) → 결과를 새 항목으로 기록 → 항목 53(+65 보강) 표대로 다음 사이클.
6.  그 뒤 새 사이클: 항목 67 초안을 확정해 사전등록. 핵심은 검정력 — 50종목·IC 0.02면 holdout으로 확인 불가(≈12년).
7.  실험 백로그는 항목 78: forward 전에는 A1(추가 150종목 종목 holdout 점검, 재훈 결정 필요)·A3·A5(12월 전),
    forward 후에는 C1~C9. 실행 전 각각 사전등록.
8.  A1(항목 79) 완료 — 일반화 지지(IC +0.026, t 2.05). 다음 사이클 입력: 포트폴리오 구성(top-10 롱온리가 IC를 수익으로
    못 바꿈), forward2 기간 재계산(IC 표준편차 0.155). A3 일간 MDD는 항목 80(완료), 남은 12월 전 코드 작업은 A5.
    항목 81 사후 진단: IC는 하위 회피에서 나오고 top-10은 비용 전에도 평균 수준, 포지션 2/3가 5일 보유 → 다음 사이클 C10.

------------------------------------------------------------------------

5. NOT CURRENT SCOPE

새로 모은 데이터(수급·공시·뉴스·금리·추가 150종목)를 모델 feature로 쓰는 것 — 하려면 새 사이클에서 사전등록.
분석가 카드의 과거 통계(시장·수급 base rate), LLM 문장 요약, 공개 웹 서비스(유사투자자문업 규제 확인 전), 사용자 피드백 학습.
forward 결과 전에는 범위를 넓히지 않는다.

------------------------------------------------------------------------

6. Current Project Position

Kiwoom API(일봉·분봉·지수·수급) → 완료
일별 데이터(top50, 2002~) → 완료(품질 이슈: K-OTC 구간, 미완성 표시 없음)
Daily feature/타깃/모델 → 완료(신호 약하고 감쇠 중)
buffer 전략·비용 → 완료(validation에서 선택, 경로 잡음 큼)
분봉 수집·오버레이 후보 → 완료(forward 대기)
리스크 관리 → 후보 전부 탈락, 미보유
개인화·설문 → CLI 수준
분석가 패널(퀀트·차트·공시·뉴스·시장 카드 + Streamlit 뷰어) → 1차 완료(항목 69~76), 실제 금요일 화면 확인 대기
추가 데이터(KOSPI200 200종목, DART, ECOS, 뉴스) → 야간 수집 중, 모델 미사용
**현재: forward holdout 누적 대기 + 분석가 패널 실사용 확인**

------------------------------------------------------------------------

7. Current Priority

1순위는 forward holdout을 깨끗하게 지키는 것: 분봉 수집 누락 없이, forward를 여는 스크립트는
`evaluate_forward_holdout.py` 하나(항목 54), 분봉 raw를 읽는 스크립트는 `tests/test_forward_access_guard.py`
allowlist로만(항목 65), 고정 모델은 트리 지문으로 확인, 결과를 본 뒤 판정 규칙을 바꾸지 않는다.
분석가 패널은 참고 층 — 카드 내용으로 모델·전략·`reports/daily_picks/`를 바꾸지 않는다(AGENTS 43.1).

------------------------------------------------------------------------

8. Document Roles

`AGENTS.md` 영구 규칙(2절 현황은 초기 스냅샷), `CLAUDE.md` Claude Code 작업 요약, 이 파일 = 현재 상태 + 작업 로그.
노션 = 실험 결과 정리(사용자), 감사 보고서 = claude.ai artifact "StockLens 감사 보고서"(2026-10-04).

------------------------------------------------------------------------

9. Update Policy

의미 있는 작업이 끝날 때마다:

1.  이 파일을 갱신한다.
2.  "다음 단계"의 항목을 "완료"로 옮긴다.
3.  중요한 발견과 미해결 이슈를 기록한다.
4.  미래 아이디어와 구현된 기능을 명확히 분리한다.
5.  진행 상황 갱신만을 위해 AGENTS.md를 고치지 않는다.
6.  아래 항목 11번부터는 시간순 작업 로그다. 새 작업은 마지막에 번호를 이어서
    추가하고, 위의 요약 절(1~8)도 함께 최신 상태로 맞춘다. (요약 절 번호와 작업 로그 번호는 별개)

11. **평가지표(Metrics) 구현 및 테스트 완료**
- ML 모델의 예측 성능을 평가하기 위한 기본 회귀 평가지표를 구현함.
- `RMSE(Root Mean Squared Error)`를 포함한 평가 함수를 작성하고 단위 테스트를 수행함.
- RMSE 계산 과정에서 테스트 기대값과 실제 수학적 계산값의 불일치를 확인하고 수정함.
- 최종적으로 전체 metrics 테스트가 `5 passed`로 통과하여 구현된 평가지표의 기본 동작을 검증함.
- 향후 모델 학습 및 검증 단계에서는 단일 지표만으로 판단하지 않고, 문제의 목적에 맞는 여러 평가 지표를 함께 사용해야 함.
12. **ML 데이터셋 구축 준비 및 Feature Selection 단계 진입**
- 기존의 일별 OHLCV 데이터와 약 25개의 기술적 feature를 기반으로 ML 학습용 데이터셋을 구성하는 작업을 진행함.
- 현재 feature들은 최종 feature set이 아니라, Feature Selection을 통해 유용성·중복성·안정성을 검토해야 하는 후보 feature 집합으로 정의함.
- Feature Selection은 전체 데이터를 한꺼번에 사용하면 미래 정보가 학습 과정에 유입될 수 있으므로, 이후 정의할 시간 순서 기반 Train/Validation/Test 구조 안에서 수행하도록 설계함.
13. **현재 단계에서의 핵심 과제 정리**
- 현재까지 **Kiwoom API 연동 → 과거 일별 데이터 수집 → 데이터 품질 이슈 확인 → 기술적 Feature Engineering → 관련 테스트 → Metrics 테스트**까지 진행함.
- 다음 단계는 단순히 모델을 바로 학습시키는 것이 아니라, 먼저 **예측 대상(Target), 예측 기간(Horizon), 의사결정 시점(Decision Timestamp)**을 명확하게 정의하는 것임.
- 이후 해당 정의에 맞춰 **미래 정보가 포함되지 않는 Leakage-safe ML Dataset**을 구축하고, 시간 순서를 유지한 Train/Validation/Test 분할을 적용해야 함.
- 그 다음 **Rule-based Baseline → Feature Selection → ML Model → Out-of-Sample Evaluation** 순서로 진행하여 ML 모델이 단순한 기준 전략보다 실제로 유용한지를 검증할 예정임.

14. **ML 백테스트 손실 원인 진단 (IC 분석) 및 SELECTED_FEATURES 임시 확장**

- 문제 상황: `scripts/run_ml_backtest.py`로 5개 selected feature(`price_to_sma_5, price_to_sma_60, macd_hist_pct, volatility_20, atr_pct`) 기반 XGBoost 전략을 테스트 기간(2023-07~2026-09)에 돌린 결과, 누적수익률 -28.55%로 룰베이스 모멘텀 baseline(+24.08%)에 크게 뒤짐.
- 원인 진단(IC): 예측값과 실제 `target_return_5d`의 cross-sectional rank IC를 계산한 결과 평균 -0.0280, IC>0인 날 비율 43.62%(동전던지기 이하)로 랭킹 신호가 사실상 없음을 확인. 000660 제외 4종목 재실행 시에도 -0.0136 / 46.76%로 크게 개선되지 않아, **손실 원인이 특정 종목(000660) 쏠림이 아님**을 확인함.
- 근본 원인: 현재 5개 feature는 애초에 Filter/Wrapper/Embedded로 정식 검증된 적이 없음 — 원래 Wrapper 승자(sma_5, sma_60, macd_hist, atr_14 등 raw-price-scale 피처)가 종목 간 가격 스케일 차이를 랭킹 신호로 오인하는 버그가 있었고, 그 수정(scale-free 버전으로 교체)은 재검증 없이 적용됐으며, 이후 학습 데이터 범위가 601개 bar(2024-03~2026-09)에서 전체 이력(2002-10~2026-09)로 확장되면서 그마저도 다른 데이터 체제에서 그대로 재사용되고 있었음.
- 검증: raw-scale 8개(`sma_5, sma_20, sma_60, macd, macd_signal, macd_hist, atr_14, volume_sma_20`)를 제외한 scale-free 19개 후보 전체로 넓혀 validation 구간에서 하이퍼파라미터·feature subset을 스캔(교차검증은 validation만 사용, test는 최종 확인 1회만 — AGENTS.md 13절 원칙 준수). Default 하이퍼파라미터가 최적이었고, feature set을 19개로 넓힌 것이 유일하게 유의미한 개선(validation cross-sectional IC +0.0179 → +0.0289).
- 조치: `src/features/engineering.py`의 `SELECTED_FEATURES`를 scale-free 19개 후보 전체로 임시 확장(브루트포스 — 정식 Feature Selection 재실행 아님). Test 기간 1회 확인 결과 ML 전략 누적수익률 -28.55% → **+3.42%**, Hit Rate 51.95% → 52.60%, MDD -43.32% → -38.21%로 개선됐으나, 여전히 룰베이스 baseline(+24.08%)에는 못 미침.
- 다음 단계(미완료): (1) 지금의 19개 전체 사용은 정식 선택이 아니므로, raw-scale 8개를 제외한 후보로 Filter/Wrapper/Embedded를 cross-sectional IC 기준으로 재실행할 것. (2) 그래도 baseline을 못 넘으면 가격/변동성 기반 feature의 한계로 보고 Phase H~J(뉴스·매크로·거래량 심화)로 진행할 것.

15. **Feature Selection 재실행(Filter/Wrapper/Embedded, cross-sectional IC 기준) — 안정적 개선 없음 확인, MVP 결론 및 scope 확장 결정**

- `scripts/feature_selection_ic_rerun.py` 작성: scale-free 19개 후보에 대해 Filter(개별 feature 표준 IC 랭킹), Wrapper(cross-sectional IC 기준 순방향 탐색), Embedded(XGBoost gain importance) 세 방식을 재실행. 항상 validation으로만 비교하고 test는 최종 확인 1회만 사용(AGENTS.md 13절 원칙 준수).
- 단일 validation 구간(2020-2023) 결과: Filter/Embedded는 결국 19개 전체가 최선이었고, Wrapper만 `atr_pct + gap` 2개 조합으로 validation IC +0.0464(19개 전체 대비 +0.0289보다 높음)를 찾음. Test 1회 확인 시 IC +0.0439, IC>0 비율 51.80%로 처음으로 50%를 확실히 넘김. 다만 실제 백테스트에서는 누적수익률 +15.47%(19개 전체 +3.42%보다 높음)이나 Hit Rate 47.40%(19개 전체 52.60%보다 낮음), MDD -56.17%(19개 전체 -38.21%보다 나쁨, baseline -55.11%과 비슷한 수준)로 트레이드오프 존재.
- **재현성 문제 발견**: 동일 코드·동일 데이터를 다른 기기에서 실행하니 Wrapper 승자가 다르게 나옴(`atr_pct+gap` vs `return_20d`). XGBoost 히스토그램 트리 학습이 `n_jobs=-1`일 때 스레드별 부분합 순서가 기기(코어 수)에 따라 달라져 `random_state` 고정에도 결과가 갈릴 수 있음을 확인. `DETERMINISTIC_PARAMS={"n_jobs":1}`로 고정했으나 **그래도 기기 간 차이가 해소되지 않음** — 즉 원인이 스레딩이 아니었음.
- **`scripts/walk_forward_wrapper.py`로 근본 원인 확인**: 같은 기기 하나에서 train/validation 경계만 다르게 3개 구간(2012-2015, 2016-2019, 2020-2023.06)으로 잘라 같은 Wrapper 탐색을 반복한 결과, 매번 다른 승자가 나옴 — `return_5d`(IC +0.0885) → `price_to_sma_5, atr_pct`(IC +0.0528) → `atr_pct, gap`(IC +0.0464). `atr_pct`만 2/3 구간에서 재등장했을 뿐 안정적인 단일 승자는 없었고, IC 크기 자체도 구간이 최근으로 올수록 계속 감소함(시장 효율화/알파 감쇠 가능성 — 추가 검증 없이는 가설 수준).
- **결론**: 기기 간 재현성 문제와 시간 구간 간 불안정성 문제가 동시에 존재하며, 후자가 근본 원인 — 즉 Wrapper가 찾아내는 "승자"는 그 구간에 특화된 노이즈이지 안정적인 신호가 아님. Filter/Embedded도 결국 19개 전체가 최선이라고 판단한 것과 일관됨.
- **MVP 평가(본 문서 8절 기준) 결론**: "daily OHLCV 기반 feature만으로 baseline 대비 안정적으로 우월한 랭킹 신호를 만들 수 있는가?"에 대한 답은 현재로선 **아니오**. 5→19개 확장은 실질적 개선이었으나, 그 이상으로 더 쪼개거나 선택을 정교화하는 시도는 세 시간구간·두 기기에서 반복 검증한 결과 효과가 없음이 확인됨.
- **조치**: `SELECTED_FEATURES`는 19개 scale-free 전체로 유지(변경하지 않음, 이미 이 상태로 커밋됨). Wrapper/Filter/Embedded로 더 쪼개려는 시도는 여기서 종료. 본 문서 9절("만약 답이 아니오면, scope를 넓히기 전에 MVP를 진단하고 개선하라")에 따라, daily 기술적 feature만으로는 진단·개선을 충분히 시도했다고 보고 **Phase H(인트라데이) 이후로 scope 확장을 진행**하기로 결정.
- **결정 재검토 (항목 16 참고)**: 위에서 Phase H로 바로 넘어가기로 했던 결정은, 최종 산출물의 형태(개인화 재랭킹, 보유 종목 HOLD/SELL 판단)가 아직 전혀 구현되지 않은 상태에서 내려진 것이었음을 재훈이 다시 짚었고, 재검토 끝에 이 두 레이어를 먼저 구현하는 것으로 순서를 바꿈. 자세한 내용은 항목 16 참고.

16. **개인화 재랭킹 레이어 + 보유 종목 HOLD/SELL 판단 레이어 최초 구현**

- **배경**: 재훈이 최종 산출물의 형태에 대한 방향성을 다시 점검하면서, (a) 공격형/안정형 등 투자성향별 추천 차별화, (b) 사용자가 매수가를 입력하면 그에 맞춰 보유 종목을 HOLD/SELL 판단해주는 기능, 이 두 가지가 원래 비전에 있었지만 아직 구현되지 않았음을 확인함. AGENTS.md 5절(로드맵)에는 개인화(Phase L)가 인트라데이/뉴스/매크로(Phase H~K)보다 뒤에 있지만, 개인화/HOLD-SELL "레이어의 배관"은 어떤 신호가 들어오든 그 위에 얹는 별도 구조(AGENTS.md 9·10절)이므로, 데이터 소스 확장을 건너뛰는 것이 아니라 소비자 레이어를 먼저 만들어두는 것으로 판단하여 순서를 조정함.
- **개인화 재랭킹 레이어** (`src/recommendation/scoring.py`): AGENTS.md 9절의 conservative/neutral/aggressive 예시를 그대로 따라 `RiskProfile` 및 `PROFILES` 정의. `personalized_score = predicted_return + momentum_weight*price_to_sma_5 + volume_weight*(volume_ratio_20-1) - risk_weight*volatility_20`. neutral은 가중치 전부 0 → 기존 모델 예측값과 완전히 동일. 모델 재학습이나 새 feature 계산 없이, 이미 존재하는 scale-free feature만 재조합함(AGENTS.md 9절 "personalization은 객관적 시장 신호 자체를 왜곡하면 안 된다" 준수). `personalize_scores()`, `top_n_recommendations()`, `make_profile_score_fn()`(기존 `src/ml/strategy.make_model_score_fn`과 동일한 인터페이스로 백테스트 엔진 재사용) 구현.
- **가중치 검증**: AGENTS.md 9절 "이 가중치를 임의로 하드코딩하고 과학적으로 타당하다고 하지 마라 — 백테스트로 실제 효과를 확인하라"는 원칙에 따라, `scripts/evaluate_personalization.py`로 validation 구간에서 3개 프로필을 실제 백테스트 엔진에 태워 비교. 결과: neutral 대비 conservative는 기간별 수익률 표준편차 3.96%→3.52%(하락, 의도대로 안정적), aggressive는 3.96%→4.33%(상승, 의도대로 변동성 높음) — 의도한 방향으로 실제 차별화가 확인됨(수익률 자체를 개선하려는 목적이 아니라, 프로필이 실제로 다른 리스크 프로파일을 만드는지 확인하는 것이 목적).
- **보유 종목 HOLD/SELL 판단 레이어** (`src/portfolio/optimizer.py`): 원래 로드맵의 "Phase 4: 동적 투자 판단(상승확률·목표가·위험가 기반 HOLD/SELL/BUY 로직)"을 CURRENT_STATUS.md 자체의 "User Feedback / Outcome Learning" 원칙("한 번의 거래로 시장 예측 모델을 즉시 바꾸지 마라")에 맞게 구현. 모델 재학습 없이, 이미 계산된 예측치(`predicted_return`)와 `atr_pct`만으로 두 가지 규칙 적용: ① 손절(stop-loss) — 보유 수익률이 그 종목 자체의 ATR% 기반 임계값(기본 3×ATR%) 밑으로 떨어지면 모델 예측과 무관하게 SELL, ② 신호 반전 — 손절선 이내라도 모델이 더 이상 양의 수익률을 예측하지 않으면 SELL, ③ 그 외 HOLD. 모든 판단에 근거 수치(`unrealized_return`, `stop_loss_threshold`, `predicted_return`)를 함께 반환하여 설명 가능(AGENTS.md 24절)하게 구성.
- **테스트**: `tests/test_recommendation_scoring.py`(11개), `tests/test_portfolio_optimizer.py`(7개) 신규 작성. 전체 테스트 스위트 94→113개 전부 통과.
- **AGENTS.md 보강**: 이번 프로젝트에서 실제로 겪은 문제 중 앞으로도 재발 가능한 일반 원칙 3가지를 12절(cross-sectional 모델에 raw-scale/scale-free 피처를 섞지 말 것 + 단일 validation split만으로 feature subset을 채택하지 말고 walk-forward로 확인할 것), 22절(cross-sectional rank IC를 기본 평가지표로 사용할 것 + 최소 유효 일수 기준), 25절(XGBoost 등 히스토그램 기반 모델의 멀티스레드 비결정성 및 n_jobs=1 고정 권고)에 추가.
- **다음 단계(미완료)**: (1) 실제 추천 결과를 사용자에게 보여주는 explanation/UI 레이어는 아직 없음 — `top_n_recommendations()`와 `evaluate_position()`의 출력을 사람이 읽는 설명으로 변환하는 작업이 남음. (2) HOLD/SELL 규칙의 파라미터(3×ATR% 손절 등)도 개인화 가중치와 마찬가지로 임의 초기값이며 아직 백테스트로 검증되지 않음. (3) Phase H(인트라데이) 착수 여부는 이 레이어들이 실사용 가능한 수준으로 다듬어진 뒤 다시 논의하기로 함.

17. **HOLD/SELL 손절/신호반전 임계값 백테스트 검증 (AGENTS.md 9절 원칙 적용)**

- **배경**: 항목 16에서 구현한 `PositionConfig`의 기본값(`stop_loss_atr_multiple=3.0`, `sell_predicted_return_threshold=0.0`)은 개인화 가중치와 마찬가지로 검증되지 않은 임의값이었음. `scripts/evaluate_personalization.py`와 동일한 방식(동일 universe·top_n=2·비용, VALIDATION 구간만 사용, AGENTS.md 13절 준수)으로 `scripts/evaluate_position_thresholds.py`를 작성해 검증함.
- **방법**: 기존 백테스트 엔진의 고정 T+5 종가 청산 대신, 동일한 진입(T+1 시가)·종목선정(top_n=2, 모델 `predicted_return` 기준) 결정 그리드는 그대로 유지한 채, T+1 종가부터 T+5 종가까지 매일 `evaluate_position()`을 호출해 SELL 신호가 뜨는 첫날 종가에 청산하도록 시뮬레이션(`simulate_exit_rule`). "조기청산 없음"(기존 baseline, 항목 16의 `run_baseline_backtest`와 동일)을 기준선으로 두고, 손절배수·신호반전 임계값을 각각 그리드/단독 on-off로 비교.
- **결과(VALIDATION 구간, 조기청산 없음 대비)**: 기본값(3.0x/0.0)은 stop-loss가 거래의 1.5%에서만 발동해 mdd -65.67%→-63.30%, std_period 3.96%→3.92%로 소폭 개선(수익률도 -43.15%→-41.79%로 소폭 개선). 손절배수를 1.5x로 좁히면 개선폭이 더 커짐(cum_return -43.15%→**-38.56%**, 이 그리드에서 최고치, 발동률 14.9%). 반면 1.0x까지 좁히면 발동률이 30.7%로 급증하며 오히려 baseline보다 악화(cum_return -46.64%, mdd -68.62%) — 너무 타이트한 손절은 회복 가능한 눌림목까지 실현손실로 확정시켜 역효과를 냄. 2x~6x는 baseline에 점차 수렴(발동률이 낮아짐).
- **signal-reversal 규칙**(`predicted_return<=0.0`)은 검증구간 거래의 0.6%에서만 발동하고, 단독으로 켰을 때(손절 사실상 비활성화) cum_return이 baseline보다 오히려 악화(-43.15%→-44.86%) — 이 구간에서 모델이 음수 `predicted_return`을 내는 경우가 거의 없어 규칙이 사실상 비활성 상태이며, 드물게 발동한 경우도 순효과가 음(-)의 방향. 항목 15에서 이미 확인된 모델의 약한 cross-sectional rank IC(~0)와 일관된 결과 — 모델 예측값의 raw sign 자체가 신뢰도가 낮아, 그 위에 세운 임계값 규칙도 힘을 못 씀.
- **결론**: 손절 규칙은 실제로 리스크(mdd·std_period)를 줄이는 방향으로 유효하게 동작하며, 이 검증구간만 보면 3.0x보다 1.5x가 더 나은 트레이드오프였음. signal-reversal 규칙은 현재 형태(절대 임계값 0.0)로는 사실상 무의미함. 다만 1.0x→1.5x 구간의 급격한 성능 절벽은 단일 validation split 결과이므로, 항목 15에서 확인한 "단일 split 승자는 구간 특화 노이즈일 수 있다"는 경고를 그대로 적용해야 함 — **이 결과만으로 기본값을 3.0x→1.5x로 확정 변경하지는 않음**.
- **다음 단계(미완료)**: (1) `stop_loss_atr_multiple`을 (항목 15의 `scripts/walk_forward_wrapper.py`처럼) 여러 시간구간에서 walk-forward로 재확인한 뒤에만 기본값 변경을 결정. (2) signal-reversal 규칙은 절대 0.0 임계값 대신 상대적 기준(예: 그날 cross-sectional 예측값 중앙값/분포 대비)으로 재설계하거나, 모델 raw sign의 신뢰도가 낮다는 점을 감안해 제거를 검토. (3) 위 결정 이후 explanation/UI 레이어(항목 16의 미완료 1번) 착수.

18. **손절배수 walk-forward 재검증 — 1.5x는 재현되지 않음, 기존 기본값 3.0x가 더 견고함**

- **배경**: 항목 17에서 단일 validation split(2020~2023.06)만으로 1.5x가 3.0x보다 낫다는 결과를 얻었으나, 항목 15의 "단일 split 승자는 그 구간 특화 노이즈일 수 있다"는 경고가 그대로 적용되는 상황이었음. `scripts/walk_forward_wrapper.py`가 feature selection을 검증할 때 썼던 것과 동일한 3개 시간구간(Window1: val 2012-2015 / Window2: val 2016-2019 / Window3: val 2020-2023.06=기존 기본값 구간)에 대해 `scripts/walk_forward_position_thresholds.py`를 작성해 손절배수 그리드(1x~6x)를 재검증함. 실제 TEST 구간(2023-07~)은 이번에도 전혀 건드리지 않음(AGENTS.md 13절).
- **이상 징후 발견**: Window1(2012-2015)에서 학습된 모델의 `best_iteration=0`으로 나옴 — early stopping이 첫 라운드에서 이미 최선이라고 판단해 사실상 거의 학습이 안 된 모델임. 항목 22절 원칙("근접 미훈련 모델이 거의 상수에 가까운 예측을 낼 때 결과가 허위양성일 수 있다")과 같은 종류의 문제로, **Window1 결과는 신뢰도가 낮다고 보고 참고용으로만 사용**(원인은 아직 미조사 — 후속 과제로 남김).
- **신뢰 가능한 두 구간(Window2, Window3, best_iteration 52·56으로 정상 학습됨)만 놓고 보면**: 1.0x는 두 구간 모두에서 baseline보다 악화(cum_return Window2 -11.32%→-28.21%, Window3 -43.15%→-46.64%) — 항목 17 결론과 일치. **1.5x는 Window3에서만 개선(-43.15%→-38.56%)되고 Window2에서는 오히려 악화**(-11.32%→-14.39%, mdd -32.17%→-37.42%) — 항목 17에서 "최고"로 봤던 1.5x가 다른 구간에서는 재현되지 않음, 즉 그 구간에 특화된 결과였을 가능성이 높음. **반대로 기존 기본값 3.0x는 Window2(-11.32%→-9.96%)와 Window3(-43.15%→-41.79%) 둘 다에서 소폭이지만 일관되게 baseline보다 나음** — cum_return과 mdd 모두 두 구간 모두에서 개선되거나 거의 동일한 유일한 배수.
- **결론**: 항목 17에서 검토했던 "3.0x→1.5x로 변경" 방향은 walk-forward 검증 결과 기각함. 오히려 원래의 임의값이었던 3.0x가 이번에 테스트한 배수들 중 가장 견고했음 — "검증 안 된 기본값을 검증했더니 우연히도 잘 골랐던 경우"에 해당. `PositionConfig.stop_loss_atr_multiple` 기본값은 **3.0x 그대로 유지**하기로 결정, 코드 변경 없음.
- **다음 단계(미완료)**: (1) Window1의 `best_iteration=0` 원인 조사(데이터 문제인지, 그 시기 시장 특성인지) — 당장 급한 건 아니나 다른 walk-forward 검증에도 영향을 줄 수 있어 기록해둠. (2) signal-reversal 규칙 재설계/제거 검토(항목 17에서 이미 지적, 아직 미착수). (3) 위 결정 이후 explanation/UI 레이어(항목 16의 미완료 1번) 착수.

19. **Explanation 레이어 최초 구현 (콘솔/텍스트 수준)**

- **배경**: 항목 16부터 미뤄져 있던 마지막 조각. `top_n_recommendations()`(개인화 재랭킹)와 `evaluate_position()`(HOLD/SELL)은 이미 근거 수치(`contribution_risk/momentum/volume`, `unrealized_return`, `stop_loss_threshold`, `predicted_return`)를 들고 있었지만, 이를 사람이 읽는 문장으로 바꿔주는 레이어가 없었음. 지금 단계는 콘솔/스크립트에서 쓸 수 있는 텍스트 생성까지만 범위로 정함(웹/앱 UI는 범위 밖).
- **구현**: `src/explanation/` 패키지 신규 추가.
  - `recommendation.py`: `explain_recommendation(row)` — `top_n_recommendations()` 결과 한 행을 받아 순위·종목·모델 예측수익률·개인화 점수와, 그 점수를 구성한 contributor(모멘텀/거래량/리스크 페널티)를 |값| 내림차순으로 나열한 문장 생성. 기여도가 `_CONTRIBUTION_EPSILON`(0.05%p) 미만인 항목은 생략(예: neutral 프로필은 가중치가 전부 0이라 "개인화 조정 없음"만 표시). `explain_recommendations()`/`format_recommendations_report()`로 여러 종목을 한 번에 처리.
  - `position.py`: `explain_position_decision(position, decision)` — `evaluate_position()`이 이미 내놓은 `PositionDecision`을 받아 HOLD/SELL과 그 근거(손절 규칙 발동 vs 신호 반전 vs 정상 보유)를 문장으로 변환. 새 판단을 내리지 않고 기존 `reason` 문자열을 파싱해 어떤 규칙이 발동했는지만 구분 — 즉 이 레이어가 HOLD/SELL 판단 자체와 어긋날 수 없음.
  - AGENTS.md 24절("설명은 실제로 랭킹에 영향을 준 것과 동일한 신호/피처/점수로부터 생성되어야 하며 사후에 지어내면 안 된다") 준수: 두 함수 모두 새로운 계산을 하지 않고, 이미 계산된 컬럼/필드가 없으면 `ValueError`로 명시적으로 실패함.
  - 출력 언어는 한국어로 결정함 — 코드베이스 자체(docstring/식별자/테스트)는 지금까지처럼 전부 영어를 유지하되, 이 레이어만 최종 사용자(한국 사용자, KRX 종목)가 직접 읽는 텍스트라 한국어로 생성하도록 정함. `PositionDecision.reason`(영어, 기존 테스트가 영어 부분 문자열을 검증 중)은 변경하지 않고 그 위에 얹는 방식으로 구현해 기존 테스트와 충돌 없음.
- **실데이터 확인**: validation 구간 마지막 날짜(2023-06-30) 데이터로 aggressive 프로필 top-3, 그리고 임의의 손절 시나리오 하나를 직접 돌려 출력 형태 확인함 — 예:
  ```
  [1위] 005380 (2023-06-30, aggressive 프로필) — 모델 예측수익률 +0.27%, 개인화 점수 +3.49%:
    - 거래량 기여: +2.34%p
    - 모멘텀 기여: +0.88%p
  ```
- **테스트**: `tests/test_explanation_recommendation.py`(8개), `tests/test_explanation_position.py`(4개) 신규 작성 — 누락 컬럼 거부, contributor epsilon 필터링, 정렬 순서, 프로필별(neutral/conservative/aggressive) contributor 존재 여부, HOLD/손절SELL/신호반전SELL 세 케이스 각각 올바른 문구만 포함하고 서로 다른 케이스의 문구는 섞이지 않는지 확인. 전체 테스트 스위트 113→125개 전부 통과.
- **다음 단계(미완료)**: (1) 지금은 DataFrame 행/PositionDecision을 직접 받는 라이브러리 함수 수준 — 실제 CLI 진입점(`app.py`)이나 API 응답 포맷으로 연결하는 작업은 아직 없음. (2) signal-reversal 규칙 재설계(항목 17·18에서 계속 미룸)와 Window1 `best_iteration=0` 조사(항목 18)는 그대로 미해결.

20. **signal-reversal 규칙 재설계: 절대 임계값 → cross-sectional percentile, walk-forward로 pct<=20% 후보 확인**

- **배경**: 항목 17에서 이미 지적했듯, 현재 signal-reversal 규칙(`predicted_return<=0.0`)은 이 모델의 predicted_return이 거의 항상 양수(평균 +0.41%, 99.7%+가 0 초과)라 검증구간 거래의 0.6%에서만 발동하고, 단독으로 켰을 때 오히려 baseline보다 나쁨(항목 17). AGENTS.md 22절이 이 모델의 출력을 절대값이 아니라 cross-sectional 랭킹(rank IC)으로만 신뢰하기로 이미 정해둔 것과 같은 기준을, signal-reversal 규칙에도 적용하기로 함 — "예측값이 0 이하인가"가 아니라 "오늘 유니버스 내에서 이 종목의 신호가 상대적으로 뒤처졌는가"로 재정의.
- **구현**: `src/portfolio/optimizer.py`에 `PositionConfig.sell_percentile_threshold: float | None`(기본 `None`, 기존 절대 임계값과 하위호환)와 `PositionSignal.predicted_return_percentile: float | None`(기본 `None`) 추가. `sell_percentile_threshold`가 설정되면 `predicted_return_percentile <= threshold`(그날 유니버스 내 하위 X% 이내)일 때 SELL, `None`이면 기존 절대 규칙 그대로 동작(기존 동작/테스트 전부 하위호환, 회귀 없음 확인). `src/recommendation/scoring.py`에 `add_predicted_return_percentile()` 추가 — trade_date별로 predicted_return을 `.rank(pct=True)`해서 cross-sectional percentile 컬럼을 붙임. `src/explanation/position.py`도 percentile 규칙 발동 시 다른 문구("...대비 하위권으로 떨어져 매도 신호")를 내도록 수정.
- **검증구간 단일 split 결과** (`scripts/evaluate_signal_reversal_thresholds.py`, stop_loss=3.0x 고정, item 18의 검증된 기본값): `stop_loss_only`(reversal 없음) baseline -39.99%/mdd -63.30%. `absolute_thr=0.0`(현재 기본값)은 -41.79%/mdd -63.30% — mdd는 그대로인데 수익률만 깎아먹음(항목 17과 일관). percentile 그리드에서 **pct<=40%가 가장 인상적**: cum_return -38.35%(baseline보다도 나음), mdd -50.96%(baseline 대비 +12.34%p 개선), std_period 2.99%(대폭 개선) — 단, 5종목 유니버스라 pct<=10%는 구조적으로 아예 발동 불가능(순위 최솟값이 1/5=20%라 그 밑으로는 못 내려감).
- **walk-forward 재검증** (`scripts/walk_forward_signal_reversal.py`, 항목 18과 동일한 3개 시간구간): Window1은 이번에도 `best_iteration=0`으로 나와 신뢰도 낮음으로 제외(항목 18과 같은 이상 징후가 **두 번째로 재현** — 우연이 아닐 가능성이 높아짐, 후속 조사 우선순위를 올림). 신뢰 가능한 Window2·Window3만 보면, **단일 split에서 제일 좋아 보였던 pct<=40%는 Window2에서 mdd가 오히려 악화**(-32.43%→-33.93%)되어 재현되지 않음 — 항목 18에서 겪은 것과 똑같은 패턴. 반면 **pct<=20%는 두 구간 모두에서 mdd와 std_period가 일관되게 개선**됨(Window2: cum_return -9.82%→-5.87%, mdd -32.43%→-25.97%, std 3.33%→3.12% / Window3: cum_return -39.99%→-46.39%(악화), mdd -63.30%→-62.59%(소폭 개선), std 3.90%→3.44%) — 두 신뢰 구간 모두에서 mdd·std_period가 개선된 유일한 후보.
- **결론**: 절대 임계값(현재 기본값)은 "제거해도 되는" 수준이 아니라 그대로 두면 손해라는 게 재확인됨. `pct<=40%`처럼 단일 split에서 극적으로 좋아 보이는 값은 항목 18의 교훈대로 walk-forward에서 기각. `pct<=20%`는 평균 수익률을 소폭 희생(-1.22%p)하는 대신 두 신뢰 구간 모두에서 mdd·변동성을 일관되게 낮추는, 지금까지 이 프로젝트에서 나온 리스크관리용 파라미터 중 가장 견고한 근거를 가진 후보임. **아직 기본값을 코드에서 바꾸지는 않음** — 재훈 확인 후 `PositionConfig` 기본값(`sell_percentile_threshold=0.20`, `sell_predicted_return_threshold`는 사실상 미사용)으로 교체할지 결정 예정.
- **테스트**: `tests/test_portfolio_optimizer.py`에 percentile 규칙 6개(발동/미발동/절대 규칙 무시됨/percentile 필드 누락 시 에러/범위 검증/손절이 percentile보다 우선) 추가, `tests/test_recommendation_scoring.py`에 `add_predicted_return_percentile` 4개 추가. 전체 스위트 125→135개 전부 통과.
- **다음 단계(미완료)**: (1) 재훈 확인 후 `PositionConfig` 기본값을 `sell_percentile_threshold=0.20`으로 교체할지 결정. (2) Window1 `best_iteration=0`이 이제 두 번째로 재현됐으니 원인 조사 우선순위를 올림(항목 18에서는 "당장 급하지 않음"이었으나 재고 필요). (3) explanation/UI 레이어를 CLI/API에 연결하는 작업(항목 19의 미완료 1번)은 그대로 대기.

21. **`scripts/walk_forward_signal_reversal.py`를 재훈의 기기에서 독립 재실행 — pct<=20%가 기기 간에도 유일하게 재현됨, 재현성 이슈가 Window1뿐 아니라 전 구간으로 확대 확인**

- **배경**: 항목 20의 walk-forward 결과를 재훈이 본인 기기에서 그대로 재실행함. `n_jobs=1`로 고정했음에도(AGENTS.md 25절) 항목 15에서 이미 "n_jobs=1로도 기기 간 차이가 해소되지 않는다"고 확인된 문제가 이번에도 나타남 — Window2 `best_iteration` 52(제 기기) vs 47(재훈 기기), Window3 56 vs 32로 전부 다르게 나옴. **이번에 새로 확인된 점**: 지금까지는 이 재현성 문제가 Window1의 `best_iteration=0`에서만 뚜렷했는데, 이번 재실행으로 **Window2·Window3처럼 정상적으로 학습된(0이 아닌) 구간들도 기기마다 다른 `best_iteration`과 다른 숫자를 낸다**는 게 명확해짐 — 즉 "몇몇 이상 구간의 문제"가 아니라 이 프로젝트의 XGBoost 학습 파이프라인 전반의 구조적 재현성 문제임.
- **그럼에도 불구하고 결론은 같은 방향으로 재현됨**: 두 기기, 두 번의 독립적인 walk-forward 실행에서 공통적으로 — (a) `stop_loss_only` 대비 mdd·std_period가 신뢰 구간(Window2·3) 모두에서 개선되는 후보는 `pct<=20%`가 유일하게 두 실행 모두에서 mdd_wins 2/2·std_wins 2/2를 기록함. (b) `pct<=40%`는 제 기기에서는 mdd_wins 1/2(Window2에서 악화)였는데 재훈 기기에서는 mdd_wins 2/2로 바뀜 — 즉 `pct<=40%`는 실행마다 판정이 뒤집히는 반면, `pct<=20%`는 두 번 다 흔들림 없이 승리함. (c) `pct<=20%`의 평균 수익률 손실도 두 실행에서 비슷한 수준(-1.82%p, -1.22%p)으로 일관됨.
- **해석**: `pct<=40%`가 실행마다 판정이 뒤집힌다는 사실 자체가, 그 값이 모델의 미세한 적합 차이에 민감한 "그 순간의 우연"에 가깝다는 걸 방증함(항목 15의 Wrapper 재현성 문제와 같은 종류). 반대로 `pct<=20%`는 시간구간(walk-forward)뿐 아니라 기기 간 비결정성까지 뚫고 두 번 다 같은 결론을 냄 — 지금까지 이 프로젝트의 어떤 파라미터 검증보다 강한 근거.
- **결정**: `PositionConfig`의 signal-reversal 기본값을 `sell_percentile_threshold=0.20`(percentile 방식)으로 변경하기로 결정. 코드 변경은 재훈 확인 후 적용 예정(아직 미반영 — 다음 턴에서 실제로 `PositionConfig` 기본값 필드를 바꾸는 작업 필요).
- **재현성 문제 자체는 별도 과제로 격상**: Window1뿐 아니라 전 구간에서 기기 간 결과가 달라진다는 게 이번에 확인됐으므로, 항목 18에서 "당장 급하지 않음"으로 미뤄뒀던 것과 달리 이제는 이 프로젝트의 모든 walk-forward/재현성 주장에 영향을 주는 구조적 문제로 봐야 함. `n_jobs=1`로도 해결이 안 된 원인(라이브러리 버전 차이? OS/CPU 아키텍처 차이? 부동소수점 연산 순서?)을 조사하는 게 다음 walk-forward 검증들보다 먼저 필요할 수 있음.
- **다음 단계(미완료)**: (1) `PositionConfig(sell_predicted_return_threshold=0.0)` 기본값을 `PositionConfig(sell_percentile_threshold=0.20)`으로 실제 코드 변경 — 관련 테스트·`scripts/demo_explanation.py` 등 기본값에 의존하는 곳 확인 필요. (2) 기기 간 재현성 문제 원인 조사(격상됨, 우선순위 높음). (3) explanation/UI 레이어를 CLI/API에 연결(항목 19의 미완료 1번)은 그대로 대기.

22. **`PositionConfig.sell_percentile_threshold` 기본값을 실제로 `0.20`으로 변경 완료 — percentile 방식이 signal-reversal 규칙의 정식 기본값이 됨**

- **배경**: 항목 20·21에서 `pct<=20%`가 walk-forward 2개 신뢰 구간 + 재훈의 독립된 기기에서의 재실행까지 총 네 번(제 기기 2구간 + 재훈 기기 2구간) 흔들림 없이 mdd·std_period를 개선하는 것으로 확인됨에 따라, 재훈이 기본값 교체를 확정 승인함("ㄱㄱㄱ"). 이 항목은 그 승인을 실제 코드에 반영한 기록.
- **구현**: `src/portfolio/optimizer.py`의 `PositionConfig.sell_percentile_threshold` 기본값을 `None` → `0.20`으로 변경. 클래스/모듈 docstring도 percentile 방식을 기본, 절대 임계값 방식(`sell_percentile_threshold=None`)을 하위호환용 opt-in으로 서술하도록 재작성.
- **파급 범위 점검 및 조치**: `evaluate_position()`의 percentile 필드 검증이 손절 여부와 무관하게 항상 먼저 실행되는 구조라, 단순히 기본값만 바꾸면 (a) `predicted_return_percentile`을 안 넘기는 기존 호출부가 전부 `ValueError`로 깨지고 (b) "절대 규칙만/손절만 격리" 같은 과거 실험의 의미가 조용히 percentile 방식으로 바뀌어버릴 위험이 있었음. `grep -rn "PositionConfig("` / `grep -rn "evaluate_position("`로 전체 호출부를 먼저 파악한 뒤 두 가지로 나눠 처리:
  - **새 기본값(percentile)을 그대로 받아들이는 곳**: `tests/test_portfolio_optimizer.py`·`tests/test_explanation_position.py`의 기본 config 호출들에 `predicted_return_percentile` 값을 채워 넣음(손절이 결과를 결정하는 케이스도 검증 로직이 그 필드를 요구하므로 포함). `scripts/demo_explanation.py`는 `add_predicted_return_percentile()`로 그날 유니버스의 percentile을 계산해 005930의 값을 `PositionSignal`에 채워 넣도록 수정.
  - **과거 실험의 원래 의미(절대 규칙 전용 / 손절 전용)를 그대로 지켜야 하는 곳**: `sell_percentile_threshold=None`을 명시적으로 고정 — `tests/test_portfolio_optimizer.py`의 절대 규칙 테스트(이름을 `test_sell_on_signal_reversal_absolute_rule_when_opted_in`으로 변경), `tests/test_explanation_position.py`의 절대 규칙 설명 문구 테스트, `scripts/evaluate_position_thresholds.py`(기본값 행·손절 배율 그리드·`stop_loss=3.0x only`·`reversal_thr=0.0 only` 4곳), `scripts/walk_forward_position_thresholds.py`(손절 배율 그리드), `scripts/evaluate_signal_reversal_thresholds.py`(`stop_loss_only`·`absolute_thr=0.0` 2곳), `scripts/walk_forward_signal_reversal.py`(`stop_only_cfg`).
- **회귀 검증**: 전체 테스트 스위트 `135 passed` 유지(신규 실패 없음). 파급 범위를 점검하며 수정한 4개 실험 스크립트(`evaluate_position_thresholds.py`, `evaluate_signal_reversal_thresholds.py`, `walk_forward_position_thresholds.py`, `walk_forward_signal_reversal.py`)를 전부 재실행해 항목 17/18/20/21에 이미 기록된 숫자와 정확히 동일한 결과가 나오는지 확인함 — 예: `evaluate_position_thresholds.py`의 `default (3.0x atr, thr=0.0)` cum_return -41.79%/mdd -63.30%(항목 17과 동일), `walk_forward_signal_reversal.py`의 Window2·3 `pct<=20%` mdd 개선폭(항목 20·21과 동일)까지 전부 일치. 즉 "암묵적 `None`을 명시적으로 고정"한 조치가 과거 실험들의 실제 동작을 전혀 바꾸지 않았음을 확인함.
- **결론**: `PositionConfig`의 signal-reversal 기본값이 이제 코드 레벨에서 `sell_percentile_threshold=0.20`(percentile 방식)이며, 절대 임계값 방식은 명시적 opt-in(`sell_percentile_threshold=None`)으로만 동작함. 향후 이 레이어를 호출하는 새 코드는 별도 설정 없이도 항목 20·21에서 검증된 리스크관리 규칙을 기본으로 사용하게 됨.
- **다음 단계(미완료)**: (1) 기기 간 XGBoost 재현성 문제 원인 조사(항목 21에서 격상됨, 아직 미착수 — `n_jobs=1`로도 해소 안 되는 원인이 라이브러리 버전/OS·CPU 아키텍처/부동소수점 연산 순서 중 무엇인지 불명). (2) explanation/UI 레이어를 실제 CLI/API 진입점에 연결하는 작업(항목 19의 미완료 1번, 계속 대기 중).

23. **기기 간 재현성 문제 원인 확정: XGBoost 기본 `tree_method="hist"`의 히스토그램 합산이 CPU 아키텍처마다 다름 — `tree_method="exact"`로 두 기기(리눅스 x86_64 vs macOS arm64)에서 실데이터 예측값이 비트 단위로 완전히 일치함을 확인**

- **배경**: 항목 21까지도 `n_jobs=1`(AGENTS.md 25)로 고정했음에도 재훈의 기기와 제 샌드박스가 서로 다른 `best_iteration`/결과를 내는 이유가 불명이었음. `requirements.txt`가 `pandas`/`numpy`/`xgboost` 버전을 전혀 고정하지 않고 있다는 것도 이번에 확인(버전 드리프트 자체가 원인일 가능성도 배제 못 함).
- **진단 방법**: `scripts/diagnose_reproducibility_env.py`(신규) — StockLens 데이터/코드와 완전히 무관한 합성 데이터로 `n_jobs=1, random_state=42` 미니 XGBoost 학습을 두 번(기본 tree_method / `tree_method="exact"`) 수행하고, 예측값을 sha256 해시로 찍어 "완전히 같음"을 육안 비교 없이 확인 가능하게 함. 두 기기에서 각각 실행:
  - 제 기기: Linux x86_64, xgboost 3.2.0(GCC 10.3.1/glibc 2.28, CUDA 빌드), numpy 2.4.4, pandas 3.0.2.
  - 재훈 기기: macOS arm64(Apple Silicon), xgboost 3.4.1(Clang 15.0.0), numpy 2.5.2, pandas 3.0.5.
  - 결과: 기본 tree_method(사실상 `hist`)에서는 두 기기 해시가 다름(`d8aa8038...` vs `361b3784...`) — 예상대로 재현 안 됨. **`tree_method="exact"`에서는 두 기기 해시가 완전히 동일**(`6584b2410c265cbcab4887457990782ca550315074a4ea6fb10523e34c893fc1`) — CPU 아키텍처·OS·컴파일러·xgboost/numpy/pandas 버전이 전부 다른데도 비트 단위로 일치함.
- **실데이터 재검증**: 합성 데이터에서만 맞은 건 아닌지 확인하려고 `scripts/verify_exact_tree_method_reproducibility.py`(신규)로 실제 StockLens 검증구간 단일 split에서 동일 테스트 반복. 기본 tree_method는 두 기기가 여전히 다름(`best_iteration` 56 vs 32, 항목 15/18/20/21과 같은 패턴). **`tree_method="exact"`는 실데이터에서도 두 기기 해시(`72ad9f2056c4efd6b97097964006fb2937ed86ce83fb1e23a8df70677c962de9`)와 `best_iteration`(116)이 완전히 일치**. 이걸로 항목 15부터 이어진 재현성 문제의 원인이 StockLens 코드가 아니라 **XGBoost의 `hist` 히스토그램 합산이 CPU 아키텍처/컴파일러마다 부동소수점 연산 순서가 달라 1000라운드 부스팅을 거치며 오차가 누적되는 구조적 한계**임이 확정됨(XGBoost 공식 문서도 플랫폼 간 비트 재현성을 보장하지 않는다고 명시).
- **트레이드오프 확인 필요 — `tree_method="exact"`를 실제 기본값으로 바꿔도 되는지는 아직 미해결**: `scripts/compare_tree_method_hist_vs_exact.py`(신규)로 같은 검증구간 단일 split에서 기본값 vs `exact`의 cross-sectional IC와 top_n=2 백테스트 성능을 비교함. 결과: `val_xsec_IC` +0.0289(기본) → +0.0113(exact, 약 60% 하락), 반면 백테스트 성능은 엇비슷(cum_return -43.15%→-42.05%, hit_rate 46.20%→45.03%, mdd -65.67%→-61.82%, mdd는 오히려 소폭 개선). 학습 시간은 0.3초→3.3초(약 11배) 늘지만 이 데이터 규모에선 절대적으로 무시할 수준. **IC가 유의하게 떨어진다는 신호가 있는데 이건 단일 split 결과라, 이 프로젝트 자체 원칙(항목 15/18/20/21: 단일 split 결과는 walk-forward 전엔 믿지 않는다)에 따라 아직 `DEFAULT_PARAMS`를 바꿀 근거로는 부족함.**
- **결론/결정**: (1) 재현성 문제의 원인은 완전히 규명됨 — 앞으로 이 프로젝트의 walk-forward/재현성 검증 스크립트들(`DETERMINISTIC_PARAMS = {"n_jobs": 1}`를 쓰는 모든 곳)에 `tree_method="exact"`를 추가하면 그 즉시 기기 간 재현성 문제가 해결된다는 게 두 기기 실측으로 확정됨. (2) 다만 `src/models/predict.py`의 전역 `DEFAULT_PARAMS`(실제 모델 학습 전반에 쓰이는 기본값)를 `tree_method="exact"`로 바꾸는 것은 IC 하락 신호 때문에 별도 walk-forward 검증 없이는 보류. 아직 코드 변경 없음(다음 턴에 재훈 결정에 따라 반영 예정).
- **다음 단계(미완료)**: 아래 두 방향 중 재훈 결정 필요 — (a) `DETERMINISTIC_PARAMS`에만 `tree_method="exact"`를 추가해 앞으로의 walk-forward 검증들을 기기 간 신뢰 가능하게 만들되 전역 기본값은 그대로 유지, (b) 위와 별개로 `tree_method="exact"`를 walk-forward로 제대로 검증해서 전역 `DEFAULT_PARAMS` 자체를 바꿀지까지 결정. explanation/UI 레이어를 CLI/API에 연결하는 작업(항목 19의 미완료 1번)은 계속 대기.

24. **(a) 적용: `DETERMINISTIC_PARAMS`에 `tree_method="exact"` 반영 완료 — 그런데 재실행하니 `pct<=20%` 결론이 재현 안 됨(항목 22 결정에 의문 제기)**

- **구현**: 항목 23의 (a) 방향대로, 이 프로젝트의 walk-forward/실험 스크립트 6곳(`scripts/demo_explanation.py`, `scripts/feature_selection_ic_rerun.py`, `scripts/walk_forward_position_thresholds.py`, `scripts/walk_forward_signal_reversal.py`, `scripts/walk_forward_wrapper.py`, `scripts/evaluate_signal_reversal_thresholds.py`)의 `DETERMINISTIC_PARAMS`(또는 동등한 inline params)에 `tree_method="exact"`를 추가함. `src/models/predict.py`의 전역 `DEFAULT_PARAMS`는 그대로 유지(항목 23에서 결정한 대로, IC 하락 신호 때문에 별도 walk-forward 검증 전까지 보류). 전체 테스트 135개 그대로 통과.
- **재실행 결과 1 (`walk_forward_position_thresholds.py`)**: `stop_loss_atr_multiple=3.0x`는 여전히 3개 구간 중 2개에서 baseline 대비 mdd 개선(Window1은 `best_iteration=1`로 사실상 미학습 상태라 신뢰 불가) — 항목 18의 결론과 방향이 일치, `tree_method` 전환에 영향받지 않는 것으로 보임.
- **재실행 결과 2 (`walk_forward_signal_reversal.py`) — 문제 발견**: Window1의 `best_iteration`이 0(`hist`)에서 1(`exact`)로 바뀌었을 뿐 여전히 사실상 미학습 상태인데, 스크립트의 "신뢰 불가 구간 제외" 로직이 `best_iteration == 0`만 걸러내서 이번엔 Window1이 (잘못) "신뢰 가능"으로 집계됨 — 필터 로직 보강 필요(아직 미수정, 아래 참고). Window1을 수동으로 제외하고 Window2·3만 비교하면, **`pct<=20%`가 항목 21에서 재훈 기기까지 포함해 두 번 다 이겼던 mdd 개선이 이번엔 Window3에서 깨짐**(mdd -63.04% vs baseline -61.12%, 즉 악화 — Window2에서만 개선: -27.09% vs -33.65%). 즉 "신뢰 가능한 두 구간 모두에서 mdd 개선"이라는 항목 21의 핵심 근거가, 제 기기에서 `tree_method=exact`로 바꾸자 더 이상 재현되지 않음.
- **해석**: `tree_method="exact"`가 기기 간 재현성은 확실히 해결하지만(항목 23), 동시에 실제로 다른 모델을 학습시키는 변경이라는 것도 다시 확인됨(Window3 `best_iteration` 56→116). `sell_percentile_threshold=0.20`을 프로젝트 기본값으로 확정한 항목 22의 결정은 `hist` tree_method 하에서 검증된 것이라, `exact`로 넘어오면서 그 근거가 흔들리는 상황. 손절 배율(3.0x) 쪽 결론은 이번 전환에서도 유지된 것과 대조적.
- **다음 단계(미완료)**: (1) 재훈 기기에서도 새 `walk_forward_signal_reversal.py`(tree_method=exact 반영판)를 돌려서, 제 기기의 이번 결과(Window2/3 mdd delta)가 기기 간에도 재현되는지 확인 필요 — 재현되면 `pct<=20%` 채택 결정(항목 22)을 재고해야 함. (2) Window1류의 "사실상 미학습" 구간을 `best_iteration==0`이 아니라 더 넓은 기준으로 거르도록 `walk_forward_signal_reversal.py`의 필터 로직 보강(현재 `best_iteration=1`을 놓침). (3) `PositionConfig.sell_percentile_threshold=0.20` 기본값(항목 22)을 이대로 유지할지, 되돌릴지, 다른 임계값으로 바꿀지는 (1)의 결과를 보고 결정. (4) `scripts/feature_selection_ic_rerun.py`·`scripts/walk_forward_wrapper.py`는 fit 횟수가 많아(최대 ~150회) 아직 `tree_method=exact`로 재실행하지 않음 — 코드는 반영됐으나 결과 재확인은 미완료.

25. **`tree_method="exact"` 반영판 3개 스크립트를 재훈 기기에서 재실행 — 세 개 다 완전히 동일한 숫자로 재현됨(재현성 문제 완전 해결). 그런데 그중 `walk_forward_signal_reversal.py` 결과가 `pct<=20%` 채택(항목 22)의 근거를 무너뜨림**

- **재현성 결과(전부 성공)**: `walk_forward_signal_reversal.py`, `scripts/feature_selection_ic_rerun.py`, `scripts/walk_forward_wrapper.py` 세 스크립트를 재훈 기기에서 재실행한 콘솔 출력을 제 기기 결과와 대조함. **세 스크립트 전부, 모든 구간·모든 자리수(IC 소수점 4자리, mdd/cum_return 소수점 둘째자리, `best_iteration`까지)가 완전히 일치**함. 특히 `walk_forward_wrapper.py`는 항목 15에서 애초에 이 조사를 촉발한 스크립트(같은 코드·같은 데이터인데 기기마다 `('atr_pct', 'gap')` vs `('return_20d',)`로 다른 Wrapper 승자를 고르던 문제)인데, 이번엔 3개 구간 전부 라운드별 세부 수치까지 완전히 동일하게 재현됨(Window1 `('price_to_sma_5','price_to_sma_60','volatility_5')` IC+0.1067, Window2 `('rsi_14','volume_ratio_20')` IC+0.0751, Window3 `('atr_pct','high_low_range')` IC+0.0428). **항목 15부터 이어진 기기 간 비결정성 문제가 완전히 해결됐다고 결론지어도 되는 수준의 증거.**
- **그런데 `walk_forward_signal_reversal.py`의 재현된 결과 자체가 문제**: Window1은 여전히 `best_iteration=1`(사실상 미학습, 필터 로직이 못 거름 — 항목 24에서 이미 지적)이라 제외하고 Window2·3만 보면, `pct<=20%`는 **Window2에서만 mdd 개선**(-27.09% vs baseline -33.65%)하고 **Window3에서는 오히려 악화**(-63.04% vs -61.12%)됨 — 이제 두 기기 모두에서 "신뢰 가능한 구간 중 1/2만 승리"로 완전히 일치함(더 이상 기기 간 우연의 일치가 아니라 진짜 결론). 항목 21이 "재현 가능한 두 구간 모두에서 mdd 개선"이라고 내렸던 결론은, 돌이켜보면 `hist` tree_method의 (그 자체로 비재현적인) 부동소수점 경로가 그 시점의 두 기기에서 우연히 비슷하게 떨어졌던 결과였을 뿐, `exact`처럼 진짜로 재현 가능한 기준에서는 성립하지 않음.
- **Wrapper 결과에 대한 별도 해석**: `feature_selection_ic_rerun.py`/`walk_forward_wrapper.py`가 완벽히 재현된 것 자체는 좋은 소식이지만, Wrapper가 뽑은 승자 조합은 3개 구간에서 전부 다름(Window1/2/3 겹치는 feature 없음 — 스크립트 자체의 "2-3/3 구간에서 반복돼야 신뢰"라는 기준 미달, 항목 15와 같은 결론). 즉 이 부분은 재현성은 해결됐지만 "새 feature 조합을 채택해야 한다"는 근거는 여전히 없음 — `SELECTED_FEATURES` 변경 사유는 아님.
- **결론**: (1) 재현성 문제는 이 항목으로 완전히 종결. 앞으로 이 프로젝트의 모든 walk-forward/실험 결과는 `tree_method="exact"` 하에서 기기 간 신뢰 가능. (2) 그 대가로, 항목 22에서 확정했던 `PositionConfig.sell_percentile_threshold=0.20` 기본값의 근거(항목 21의 "두 기기 모두 mdd 개선")가 무효화됨 — `exact` 기준으로는 신뢰 가능한 2개 구간 중 1개에서만 이기므로, 이 프로젝트가 항목 18에서부터 지켜온 "전 구간(또는 최소 과반) 승리해야 채택" 기준을 충족 못 함.
- **다음 단계(미완료, 재훈 결정 필요)**: (1) `PositionConfig.sell_percentile_threshold` 기본값을 `0.20`에서 다시 `None`(손절만, signal-reversal 없음)으로 되돌릴지 — 지금 증거로는 되돌리는 쪽이 이 프로젝트 원칙에 맞음. (2) `walk_forward_signal_reversal.py`의 Window1류 "사실상 미학습" 구간 필터 로직 보강(여전히 미수정). (3) explanation/UI 레이어를 CLI/API에 연결(항목 19의 미완료 1번)은 계속 대기.

26. **`PositionConfig` 기본값을 손절 전용으로 되돌리고, "signal-reversal 완전 비활성"을 제대로 표현할 수 있도록 필드 설계를 수정함**

- **배경**: 항목 25에서 재훈이 되돌리는 쪽으로 확정. 되돌리는 방법을 구체적으로 확인하는 과정에서, 단순히 `sell_percentile_threshold=None`으로만 되돌리면 코드 구조상 `sell_predicted_return_threshold`가 여전히 `0.0`이 기본값이라 absolute 규칙이 자동으로 다시 활성화된다는 걸 발견함. 이 absolute 규칙은 항목 17에서 이미 "거래의 1% 미만에서만 발동, 격리 시 mdd 이득 없이 cum_return만 깎아먹음"으로 확인된 규칙이라 그대로 부활시키는 건 원치 않는 결과. 재훈에게 확인한 결과 "손절만 남기기"로 결정.
- **구현**: `PositionConfig`의 `sell_predicted_return_threshold` 타입을 `float = 0.0`에서 `float | None = None`으로 변경(percentile 필드와 동일한 tri-state 패턴). `evaluate_position()`의 absolute 규칙 분기를 `config.sell_predicted_return_threshold is not None`으로 먼저 게이트하도록 수정. 결과적으로 두 리버설 필드가 모두 `None`(기본값)이면 신호 반전 규칙이 아예 평가되지 않고, 손절 규칙만 SELL을 만들 수 있음 — "리버설 규칙 완전 비활성"이라는 상태를 매직 넘버(예: `REVERSAL_DISABLED=-1.0`) 없이 명시적으로 표현 가능해짐.
- **모듈/클래스 docstring 전면 재작성**: 두 변형(absolute, percentile) 모두 "기본 off, 명시적 opt-in"으로 서술 변경. absolute는 항목 17 근거로, percentile은 항목 20/21에서 한때 기본값이었다가(항목 22) 항목 25에서 walk-forward 재검증(진짜 재현 가능한 `tree_method=exact` 기준) 실패로 되돌려졌다는 히스토리를 명시. "이 모듈에서 실제로 검증된 유일한 규칙은 손절(3.0x ATR, 항목 18/24)뿐"이라고 명확히 함.
- **파급 범위 점검**: `grep`으로 전체 `PositionConfig(`/`evaluate_position(` 호출부 재확인. 실험 스크립트들(`evaluate_position_thresholds.py`, `evaluate_signal_reversal_thresholds.py`, `walk_forward_position_thresholds.py`, `walk_forward_signal_reversal.py`)은 항목 22에서 이미 두 리버설 필드를 전부 명시적으로 지정해뒀기 때문에 이번 기본값 변경에 영향받지 않음(변경 불필요). 영향받은 곳은 테스트 2곳뿐: `tests/test_portfolio_optimizer.py`의 절대 규칙 테스트(`sell_percentile_threshold=None`만 있던 걸 `sell_predicted_return_threshold=0.0`도 명시적으로 추가), `tests/test_explanation_position.py`의 동일 패턴 테스트. 그 외 default-config 테스트들은 애초에 손절이 결과를 결정하는 케이스라 영향 없음(percentile 필드가 이제 선택적이라 관련 주석만 정리). `tests/test_portfolio_optimizer.py`에 새 테스트 `test_default_config_has_no_signal_reversal_rule` 추가 — 극단적으로 나쁜 predicted_return/percentile을 줘도 기본 config로는 SELL이 안 나는지 확인. `scripts/demo_explanation.py`의 percentile 계산 로직은 이제 필수는 아니지만 해롭지 않아 그대로 둠(주석만 정정).
- **회귀 검증**: 전체 테스트 136개(신규 1개 포함) 통과. `scripts/demo_explanation.py` 재실행해서 정상 동작 확인(손절 SELL 예시 그대로 출력).
- **결론**: `PositionConfig()` 기본값은 이제 손절(3.0x ATR)만 활성화된 상태 — absolute·percentile 두 signal-reversal 변형 모두 명시적 opt-in 전용이며 프로덕션 기본값에서 완전히 제외됨. 이 모듈에서 실제로 백테스트로 뒷받침되는 규칙은 손절뿐이라는 게 이 프로젝트의 정직한 현재 상태.
- **다음 단계(미완료)**: (1) `walk_forward_signal_reversal.py`의 Window1류 "사실상 미학습" 구간 필터 로직 보강(`best_iteration==0`만 거르고 `==1`은 못 거름, 여전히 미수정). (2) signal-reversal 자체를 다른 방식으로 재설계할지(예: 더 큰 유니버스, 다른 타겟, 다른 모델)는 열린 질문으로 남김 — 당장 급한 작업은 아님. (3) explanation/UI 레이어를 CLI/API에 연결(항목 19의 미완료 1번)은 계속 대기.

27. **병행 정리 작업: 미학습 구간 필터 보강, 상태 문서/의존성/잔여 파일 정리**

- `scripts/walk_forward_signal_reversal.py`: 미학습 구간 판정을 `best_iteration == 0`에서 `best_iteration < MIN_RELIABLE_BEST_ITERATION`(=10)으로 변경. 항목 24/25에서 `tree_method="exact"` 전환 후 Window1이 `best_iteration=1`로 나와 기존 필터를 통과하던 문제를 해소. 정상 구간은 47~116 라운드에서 멈췄으므로 10은 양쪽에 충분한 여유가 있음. 경고 문구와 요약 출력도 실제 값과 기준을 함께 표시하도록 수정. 결과는 Window1이 제외되고 Window2·3만 집계되어야 하며, 기존 항목 25의 수동 제외 결과와 일치해야 함(재훈 기기에서 재실행 확인 필요).
- `CURRENT_STATUS.md`: 1~10절이 "Feature Selection/ML 시작 전" 상태로 남아 항목 14~26과 모순되던 문제를 수정. 1~9절을 현재 상태(MVP 평가 결과, 완료 작업, 미해결 이슈, 다음 단계, 위치)로 다시 작성하고, 항목 11번 이후 로그는 그대로 유지.
- `stocklens_walk_forward_stop_loss.patch` 삭제: 항목 16~18 시점의 패치 파일로, 대상 파일(`walk_forward_position_thresholds.py` 등)이 이미 저장소에 반영되어 있고 참조하는 곳이 없음.
- `requirements.txt`: `xgboost`, `numpy`, `pandas` 버전을 항목 23에서 확인한 재훈 기기(macOS arm64) 환경 기준으로 고정. 나머지 패키지는 그대로.
- 미착수: `app.py`와 Explanation 레이어 연결(신호가 약한 동안은 낮은 우선순위), `walk_forward_position_thresholds.py`의 미학습 구간 제외 로직.

28. **유니버스 확장 인프라 구현 (KOSPI200 시총 상위 50 대응)**

- **발견한 구조적 제약**: 백테스트 엔진(`src/backtest/baseline.py`)이 (a) 종목 수를 정확히 5개로 강제하고 (b) 모든 종목의 날짜를 inner join한 공통 구간만 사용했음. 종목만 50개로 늘리면 (b) 때문에 사용 가능한 이력이 가장 늦게 상장한 종목 기준으로 줄어들 수 있었음(예: 2022년 상장 종목이 하나라도 있으면 백테스트 구간이 그 이후로 제한). 따라서 종목 추가 전에 엔진 확장이 필요했음.
- **엔진**: `BaselineConfig.allow_partial_universe`(기본 `False`) 추가. `False`면 기존 동작 그대로(5종목 강제, inner join)라서 항목 14~26의 모든 기록 수치가 그대로 재현됨. `True`면 종목 수 제한이 없고, 날짜는 outer join하며, 각 결정일에 그 거래에 필요한 가격(T-lookback 종가, T 종가, T+1 시가, T+holding 종가)이 모두 있고 score_fn이 유한한 점수를 내는 종목만 랭킹함. 모델 score_fn이 예측 없음(`KeyError`, feature warm-up)을 내는 종목도 제외. 거래 가능 종목이 `top_n`보다 적은 날은 그 기간 현금 보유로 건너뜀. `src/ml/backtest.py`의 랭킹 계산도 동일하게 처리.
- **유니버스 모듈**: `src/data/universe.py` 신규. `get_universe()`가 환경변수 `STOCKLENS_UNIVERSE`(기본 `core5`, 또는 `top50`)로 종목 목록을 결정. 종목 목록은 손으로 쓰지 않고 `scripts/build_universe.py`가 Kiwoom API로 생성: `ka20002`(KOSPI200 구성종목) → 종목별 `ka10001`의 시가총액(`mac`, 억원) → 우선주(코드가 0으로 끝나지 않는 종목) 제외 후 상위 N개를 `config/universe_kospi200_top50.json`에 `as_of` 날짜와 함께 저장. 시가총액 순위는 자주 바뀌므로(2026년에 SK하이닉스가 1위로 올라선 것처럼) 임의로 하드코딩하지 않고 실행 시점의 값을 기록하도록 함. `KiwoomClient.get_index_constituents()`(cont-yn/next-key 자동 처리) 추가.
- **스크립트 전환**: `ingest_kiwoom_daily_chart_batch.py`, `build_ml_dataset.py`, `check_data_coverage.py`, `run_backtest.py`, `run_ml_backtest.py`, `feature_selection_ic_rerun.py`, `walk_forward_wrapper.py`가 `get_universe()`를 사용. 기본값은 core5라 아무것도 안 바꾸면 기존과 동일. `run_ml_backtest.py`의 `TOP_N`은 `STOCKLENS_TOP_N` 환경변수로 덮어쓸 수 있음(50종목에서 top_n=2는 매우 집중적).
- **테스트**: 136 → 150개 통과. 신규: `tests/test_backtest_partial_universe.py`(5종목 공통 달력에서 partial과 기본 결과가 완전히 동일, 늦게 상장한 종목이 이력을 줄이지 않음, lookback 이력 전에는 랭킹 제외, 거래 가능 종목 < top_n이면 건너뜀, 예측 없는 종목 제외, 랭킹 산출), `tests/test_universe.py`, `tests/test_kiwoom_index_constituents.py`. 합성 50종목×6000일 백테스트는 약 11초.
- **알려진 한계**: (1) 실제 Kiwoom API로는 아직 실행하지 않음(`ka20002`의 응답 필드는 API 명세 기준으로 작성). (2) top50은 현재 시점 기준 대형주라 과거 구간에 생존편향이 있음(AGENTS.md 23절). (3) HOLD/SELL 실험 스크립트 4종은 core5 전용으로 남김. (4) exact 트리 학습은 학습 행이 약 10배가 되어 fit 1회가 수십 초 단위로 늘어날 수 있음 — `walk_forward_wrapper.py`처럼 fit이 많은 스크립트는 수 시간이 걸릴 수 있음.
- **보안 조치**: `.env.example`에 실제 키/계좌번호로 보이는 값이 들어 있어 플레이스홀더로 교체. 이미 공개 저장소 이력에 남아 있으므로 키 재발급이 필요함.
- **다음 단계**: `build_universe.py` 실행 → 종목 확정 → 수집 → 커버리지 확인 → 평가(위 5절 1번).

29. **top50 수집 결과: 48/50 성공, 기아(000270)·삼성전기(009150) 실패 → 1990년 이전 OHLC 불일치 봉 처리**

- **결과**: `build_universe.py`로 top50 확정(삼성전자, SK하이닉스, SK스퀘어, 삼성전기, LG에너지솔루션, 현대차, ... 현대글로비스), `ingest_kiwoom_daily_chart_batch.py` 수집은 48/50 성공. 실패한 두 종목은 정규화 검증에서 "High price is below open or close on 1986-01-25"(009150), "Low price exceeds open or close on 1985-01-30"(000270)로 종목 전체가 거부됨.
- **원인**: 수십 년치 수정주가(액면분할·유상증자 반영) 과정에서 1980년대 봉의 시가/종가와 고가/저가가 서로 어긋난 것으로 보임(정확한 원인은 원본 미확인). 이 봉들은 모델이 쓰지 않음 — 학습 구간이 2002-10-29부터이고 rolling feature도 최대 약 60봉만 거슬러 올라감.
- **조치**: `src/data/normalization.py`에 `LEGACY_OHLC_TOLERANCE_BEFORE = 2000-01-01` 추가. 이 날짜 이전의 OHLC 불일치 봉만 경고 로그와 함께 버리고 나머지는 그대로 저장. 2000-01-01 이후의 같은 불일치는 여전히 예외(기존 엄격한 검증 유지). 중복 날짜, 음수 거래량 등 다른 검증도 그대로. 채워 넣거나 보정하지 않고 버리는 방식이라 조작된 값은 생기지 않음. 테스트 `tests/test_legacy_bar_handling.py` 2개 추가, 전체 152개 통과.
- **다음 단계**: 두 종목 재수집(`ingest_kiwoom_daily_chart_batch.py 000270 009150`), `check_data_coverage.py`로 50종목 이력 확인.

30. **top50(47~50종목/일) 첫 feature selection 재실행 결과 + IC 계산 편향 수정**

- **유니버스 현황**(항목 29 이후): 50종목 수집 완료. 학습 시작(2003년 초) 시점에 30종목, 검증 구간 47종목, 테스트 구간 50종목이 데이터를 가짐. partial 엔진은 날짜별로 가능한 종목만 랭킹하므로 "50종목 공통 구간 4.6년"은 제약이 아님.
- **`feature_selection_ic_rerun.py` 결과(검증 구간, n≈865일)**:
  - 19개 전체 baseline IC **+0.0024**(%days>0 50.46%). 5종목에서 +0.0289였던 값이 사라짐 → 5종목 결과는 표본 잡음이었을 가능성이 높음.
  - Filter: 단일 feature IC가 전부 -0.025~+0.002. 수익률/추세 계열(`price_to_sma_60`, `return_20d`, `return_10d`, `rsi_14`)이 음수 → 이 유니버스/기간에서 단기 반전(reversal) 성향이 약하게 보임. 표준오차가 대략 0.01(5일 중첩 수익률 고려)이라 -0.025는 약 2SE, 19개 중 최대값이라 다중검정 감안하면 확정 불가.
  - Wrapper 우승 `('return_20d','return_10d','price_to_sma_60','gap')` IC +0.0566, 그러나 **n=343/865일**. Filter top-8도 n=496.
  - Embedded: 3개 IC +0.0073, 19개 +0.0027.
  - Test 1회 확인: IC +0.0168, %days>0 52.77%, **n=415**(테스트 구간 약 800일 중).
- **평가 편향 발견**: `cross_sectional_ic`가 "그날 모든 종목의 예측값이 동일한 날"(IC 미정의)을 계산에서 **제외**했음. early stopping된 얕은 트리(max_depth=2, 소수 트리) 모델은 feature가 1~4개일 때 모든 종목이 같은 leaf에 들어가 예측이 같아지는 날이 많음 → 모델이 랭킹을 매긴 날(선택된 부분집합, 대략 40%)의 IC만 보고됨. 즉 Wrapper의 +0.0566은 전체 일수 기준이 아니며 다른 후보(n=865)와 공정하게 비교된 값이 아니었음. 미정의 일을 0으로 계산하면 Wrapper는 대략 +0.0566 × 343/865 ≈ +0.022 수준(근사치, 재실행 필요). 기존 `MIN_DAYS=300` 가드는 극단적인 경우만 거름(항목 15의 n=47 사례).
- **조치**: `scripts/feature_selection_ic_rerun.py`와 `scripts/walk_forward_wrapper.py`의 `cross_sectional_ic`를 "eligible한 모든 날(종목 3개 이상)을 분모로 하고 미정의 일은 IC=0으로 계산"하도록 수정하고, `(mean_ic, pct_pos, n_days, coverage)`를 반환·출력(coverage=IC가 정의된 날의 비율). `pct_pos`도 전체 일수 기준. `tests/test_cross_sectional_ic.py` 3개 추가, 전체 155개 통과. **이 수정 이전의 IC 수치(항목 14~15의 5종목 결과 포함)는 같은 편향을 일부 포함할 수 있음** — 5종목 결과는 n이 크게 줄지 않은 경우가 많아 영향이 작았을 것으로 보이나 재확인하지 않음.
- **현재 판단**: 아직 `SELECTED_FEATURES`를 바꿀 근거 없음(위 Wrapper 결과는 편향된 비교이며 Test IC도 0에 가까움). 수정된 스크립트로 재실행한 뒤 walk_forward_wrapper로 3개 구간 재현성을 확인해야 함.
- **다음 단계**: (1) 수정된 두 스크립트 재실행(coverage 확인). (2) `walk_forward_wrapper.py` 3개 구간 재현성 확인, Window1 `best_iteration` 확인. (3) 결과에 따라 모델링 방향(rank/분류 타겟, 모멘텀과의 앙상블, 반전 신호 활용) 결정.

31. **IC 편향 수정 후 top50 재실행 결과: 신호는 여전히 약하고 최근 구간으로 갈수록 사라짐, 소형 모델의 "예측 상수화"가 구조적 문제로 확인**

- **수정된 IC 기준 재실행(검증 2020~2023.06, n=865)**: baseline(19개 전체) IC +0.0024(coverage 99.9%). Filter top-8은 coverage 57.3%, %days>0 31.9%(IC +0.0165)로 소형 모델 특유의 상수 예측 문제가 그대로 나타남. Wrapper 우승 `('return_20d','gap','rsi_14')` IC +0.0278이지만 coverage 60.9%, %days>0 36.5%. Embedded는 coverage 100%지만 IC +0.0073(3개)·+0.0027(19개)로 0 근처.
- **Test 1회 확인(재실행에서 다시 사용됨)**: Wrapper 우승의 Test IC **+0.0032**, coverage 73.8%, %days>0 36.28% (정의된 날 기준으로 환산하면 36.28/73.8 ≈ 49.2%로 동전던지기). 검증 +0.0278 → 테스트 +0.0032로 붕괴 — 검증 구간에 맞춰진 선택이었음. 편향 수정 전 값(+0.0566 → +0.0168)과 같은 방향. **`SELECTED_FEATURES` 변경 근거 없음(19개 전체 유지).** 이 재실행으로 테스트 구간을 한 번 더 보게 되었으므로(항목 30에서 이미 1회 사용), 이후 이 테스트 결과로는 어떤 설계 결정도 하지 않음(AGENTS.md 13절).
- **walk-forward(`walk_forward_wrapper.py`, 3개 구간)**: W1(2012~2015) 우승 `('return_5d',)` IC +0.0389(%days>0 56.1%, coverage 96.7%, n=988), W2(2016~2019) `('rsi_14',)` +0.0376(56.5%, coverage 99.1%, n=979), W3(2020~2023.06) 3개 feature +0.0278(coverage 60.9%). 스크립트 기준으로는 `rsi_14`만 2/3 구간 등장. 다만 세 우승 모두 최근 수익률/과매수 계열(return_5d, rsi_14, return_20d)의 "단기 가격 반전" 계열이라는 공통점이 있음. 단, 이 IC는 각 구간에서 19개 feature × 여러 라운드 중 최대값이라 선택 편향(winner's curse)이 있고, 모델의 IC로는 부호를 알 수 없음(표준오차는 대략 0.01, 선택 편향 감안하면 약 2~3SE 수준). 신호 크기는 W1(+0.039) ≈ W2(+0.038) > W3(+0.002, baseline) 순으로 최근으로 갈수록 약해지는 패턴이 항목 15의 관찰(알파 감쇠 가설)과 일치.
- **구조적 문제 진단**: 모델이 학습 시 raw `target_return_5d`에 RMSE로 fit하고 RMSE로 early stopping하는데, 이 타깃에는 그날 종목들이 함께 움직이는 시장 성분이 분산의 대부분을 차지함. 종목 간 차이(우리가 필요한 신호)는 약해서 RMSE가 몇 트리 만에 개선을 멈추고(early stopping), 그 결과 모든 종목이 같은 leaf로 들어가 예측이 같아지는 날이 많음(coverage < 100%). 이는 항목 18/20/24의 Window1 `best_iteration=0~1` 현상과 같은 원인일 가능성이 높음(미검증).
- **다음 실험 준비**: `src/ml/cross_section.py`(daily_rank_ic, demean_by_date, rank_by_date), `scripts/diagnose_feature_ic_by_year.py`(모델 없이 feature별 연도별 표준 IC, test 미사용), `scripts/experiment_target_transform.py`(raw/demeaned/rank 타깃 × all19/reversal4 feature 세트 × 3개 구간, IC·coverage·best_iteration 비교, test 미사용) 추가. 합성 데이터로 두 스크립트 동작 확인(planted 반전 신호 복원), 테스트 158개 통과. 실제 데이터 실행 결과는 아직 없음.
- **다음 단계**: (1) `diagnose_feature_ic_by_year.py` 실행 — 반전 신호의 부호가 구간별로 안정적인지, 언제 사라졌는지 확인. (2) `experiment_target_transform.py` 실행 — 타깃 변환이 coverage와 IC를 올리는지, 3개 구간 모두에서 재현되는지 확인. (3) 결과에 따라 `train_model` 기본 타깃/early stopping 기준 변경 여부 결정.


32. **feature 연도별 IC + 타깃 변환 실험 결과: 반전 효과는 부호가 안정적이나 크기가 감쇠, rank 타깃이 가장 안정적, 비용 차감 후 수익성은 미검증**

- **연도별 IC(`diagnose_feature_ic_by_year.py`, test 제외)**: 최근 수익률/추세 계열(return_5d, return_10d, return_20d, rsi_14, price_to_sma_*)은 거의 모든 연도·구간에서 음(=단기 반전)의 부호를 유지. 다만 크기는 구간별로 줄어 2020~2023.06 구간에서는 약 -1(×100) 수준. 변동성 계열 feature는 2016년 전후로 부호가 뒤집힘(구간 간 불안정). 연도별 IC의 표준오차 ≈2(×100), 4년 구간 평균 ≈1(×100)이므로 개별 연도의 차이는 잡음일 수 있음.
- **타깃 변환 실험(`experiment_target_transform.py`, 3개 구간)**: rank 타깃 + all19 feature가 3개 구간 모두 IC 양수(W1 0.0635 / W2 0.0413 / W3 0.0130), coverage ≈100%로 가장 안정적이나 최근으로 갈수록 감소. raw 타깃 all19는 W2에서 best_iteration=0으로 붕괴(불안정). reversal4 + demeaned 조합도 best_iteration=0으로 붕괴. 개선폭은 있지만 크지 않고 감쇠 패턴은 그대로.
- **해석**: (1) 안정적으로 관찰되는 것은 단기 반전뿐, 크기는 감쇠 중. (2) 기존 모멘텀 baseline(`calculate_score`)은 이 유니버스에서 부호가 반대(잘못된 방향)로 보임. (3) IC 0.04 수준이면 5일 총수익 ≈0.3%로 왕복 비용 ≈0.43%보다 낮거나 비슷할 수 있음 → 경제적 유의성은 미검증.
- **조치**: `scripts/walk_forward_backtest_compare.py` 추가. 검증 구간별로 모멘텀 / 반전(score=-momentum) / ML(all19, rank 타깃)을 top_n 5·10, 비용 0 및 실제 비용 두 설정으로 백테스트하고 유니버스 평균 대비 초과수익·t값·순수익·MDD를 출력. test 미사용. 합성 데이터로만 동작 확인, 실제 데이터 결과는 아직 없음.
- **다음 단계**: (1) `STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/walk_forward_backtest_compare.py` 실행 후 결과 확인. (2) 비용 차감 후에도 초과수익이 있는지에 따라 `train_model` 기본 타깃(rank)/early stopping 기준 변경 또는 Phase H~J(뉴스/거시/거래량 feature) 진행 결정.

33. **walk_forward_backtest_compare 실제 데이터 결과(top50, 검증 3개 구간): 총수익 기준 약한 반전 알파는 있으나 왕복 비용(~0.43%) 차감 후 순수익은 거의 전부 음수**

- **설정**: 검증 구간만 사용(test 미사용), 5일 비중복 리밸런싱, 모멘텀 / 반전(score=-momentum) / ML(all19, rank 타깃), top_n 5·10, 유니버스 평균 대비 초과수익. ML best_iteration: W1 294, W2 45, W3 8(W3는 거의 미학습 수준).
- **3개 구간 평균(5일 기준)**: ML top5 gross +0.303% / excess +0.222% / t 1.34 / net -0.128%; ML top10 +0.264% / +0.183% / t 1.63 / net -0.166%; 반전 top5 +0.326% / +0.245% / t 1.38 / net -0.105%; 반전 top10 +0.208% / +0.127% / t 1.15 / net -0.222%; 모멘텀 top5 -0.224% / -0.304% / t -1.71 / net -0.652%.
- **관찰**: (1) 모멘텀은 방향이 반대(W2 top5 t=-3.03). (2) 반전·ML 모두 excess가 12개 구간×top_n 조합 전부에서 양수이나 t값은 대부분 1~1.5 수준, 2를 넘는 것은 ML W1 top5(2.23)·반전 W1 top10(2.01) 둘뿐(다중비교 감안 시 확정 불가). (3) net이 양수인 조합은 W3 반전 top5(+0.107%/5일)와 ML top5(+0.021%)뿐이고, 평균 net은 전 조합에서 음수. (4) ML이 단순 반전(=-momentum 한 줄)을 뚜렷하게 이기지 못함(top5 평균 gross 0.303 vs 0.326, top10은 0.264 vs 0.208). (5) net_cum -27~-83%, MDD -40~-84%로 비용 차감 시 실전 불가 수준.
- **주의(편향)**: 반전 전략의 방향은 모멘텀이 지는 것을 본 뒤, 그리고 같은 검증 구간의 feature IC를 본 뒤에 정한 것이므로 이 검증 결과에는 선택 편향이 일부 있음. 손익분기 비용은 gross ≈0.3%/5일로, 세금+수수료(~0.23%)만으로도 여유가 ≈0.07%뿐이어서 구조적으로 빠듯함.
- **결론**: 현 feature(가격/거래량 기반 19개)와 5일 전량 교체 방식으로는 비용 차감 후 수익성 근거 없음. `SELECTED_FEATURES`, 기본 모델, 운용 방식 변경 없음. 테스트 구간 추가 사용 없음.
- **다음 단계 후보**: (1) 회전율 절감(보유 종목이 상위 2k 안이면 유지하는 buffer 규칙)과 비용 민감도(슬리피지 0.03/0.1%)를 사전에 정한 그리드로 검증 구간에서 확인. (2) early stopping을 IC 기준으로 변경(W3 best_iteration=8 문제). (3) 가격 기반 신호의 한계가 확인됐으므로 Phase H~J(뉴스/거시/거래량·수급 feature) 진행.

34. **Test set 접근을 구조적으로 잠금 — 문서화가 아니라 코드로 강제(Phase H 진입 전 방법론 안전장치 1번째 항목)**

- **배경**: AGENTS.md 13절이 "test 구간을 반복 사용해 설계 결정을 내리지 말 것"을 이미 명시하고 있었는데도, 항목 14·30·31에서 실제로 test를 여러 번 들여다봤음. 특히 `feature_selection_ic_rerun.py`의 "ONE-TIME TEST CONFIRMATION" 섹션은 이름 그대로 "한 번만"이라고 주석에 적어뒀을 뿐이었고, IC 계산 편향 버그(항목 30)를 고치기 위해 스크립트를 다시 실행하면서 그 섹션도 같이 다시 실행돼 test를 한 번 더 보게 됨(항목 31에서 자체적으로 인지). 즉 "기억해서 지키기"는 이미 한 번 실패한 방식임.
- **원칙**: `src/feature_selection/data_loading.py`가 leakage를 "고치는 게 아니라 구조적으로 불가능하게" 만든 것과 같은 방식을 test 구간에도 적용. 사람이 기억해야 하는 규칙이 아니라 코드가 막는 규칙으로 전환.
- **구현**: `src/eval/test_lock.py` 신규 — `confirm_final_test_use(caller)`가 환경변수 `STOCKLENS_CONFIRM_FINAL_TEST=1`이 없으면 `TestSetLockedError`를 던짐. `splits.test`를 실제로 읽는 세 스크립트(`scripts/run_backtest.py`, `scripts/run_ml_backtest.py`, `scripts/feature_selection_ic_rerun.py`)의 test 접근 직전에 이 호출을 추가함. 순수 validation 실험용 walk-forward 스크립트들(`walk_forward_wrapper.py`, `walk_forward_signal_reversal.py`, `walk_forward_position_thresholds.py`, `walk_forward_backtest_compare.py`, `experiment_target_transform.py`)은 애초에 `splits.test`를 읽지 않고 `TEST_START_DATE`를 validation 구간의 상한 경계로만 쓰고 있어서(재확인 완료) 수정 불필요.
- **검증**: 신규 테스트 4개(`tests/test_eval_test_lock.py`) 포함 전체 162개 통과. `python -m scripts.run_backtest`를 환경변수 없이 실행하면 test 접근 직전에 `TestSetLockedError`로 즉시 중단되는 것, `STOCKLENS_CONFIRM_FINAL_TEST=1`로는 정상적으로 끝까지 실행되는 것(core5 baseline 누적수익 +42.28%, 항목 11 이후 기록된 5종목 결과 범위와 일치)을 직접 실행해 확인함.
- **다음 단계**: 이제부터 진행하는 회전율/비용 그리드, IC 기준 early stopping, Window1 원인 조사, rank/분류 타겟·모멘텀+ML 앙상블 실험은 전부 validation에서만 수행하고(위 스크립트들은 test를 안 읽으므로 자동으로 안전함), `STOCKLENS_CONFIRM_FINAL_TEST=1`은 이 실험들이 전부 끝나고 최종 결론을 낼 때 딱 한 번만 사용한다. 이 플래그를 켜는 걸 이번 결정 사이클의 "끝났다"는 신호로 취급할 것.

35. **회전율 절감(buffer) 규칙 도입 — top_n=10에서 반전·ML 둘 다 3개 구간 전부 순수익 흑자로 전환(사전등록 그리드, validation 전용)**

- **배경**: 항목 33에서 reversal/ML 모두 비용 차감 전(gross/excess)에는 3개 구간 전부 양수였지만, 매 5일마다 보유 종목 전량을 청산·재매수하는 구조 때문에 왕복비용(~0.43%)이 매번 청구되어 net이 거의 다 마이너스였음. 같은 종목이 다음 구간에도 여전히 상위권이면 팔았다가 다시 사는 게 아니라 그냥 들고 있으면 그 비용을 안 낼 수 있다는 게 가설.
- **구현**: `src/backtest/buffered.py` 신규. `run_baseline_backtest`와 동일한 타이밍(T 종가 스코어 → T+1 시가 진입 → T+5 종가 청산)과 비용 모델을 쓰되, 이미 보유 중인 종목이 이번 랭킹에서도 상위 `buffer_multiplier × top_n`위 안에 들면 매도·재매수 없이 계속 보유시킴 — 실제로 사고판 시점(진입/이탈)에서만 수수료·슬리피지·세금을 청구하고, 그냥 들고만 있는 구간은 종가 대 종가 순수 가격변동만 반영(비용 0). `buffer_multiplier=None`이면 항상 매 구간 전량 재매수/재매도라 `run_baseline_backtest`와 완전히 동일해야 함.
- **버그 발견 및 수정**: 처음 구현에서는 "이 종목이 지난 구간에도 보유 중이었나"만으로 진입/이탈 비용을 면제했는데, buffer를 꺼둔 상태(`buffer_multiplier=None`)에서도 같은 종목이 우연히 연속 구간 1등을 하면 재매수 비용이 빠지는 버그가 있었음 — `tests/test_backtest_buffered.py::test_no_buffer_matches_run_baseline_backtest_exactly`가 이를 잡아냄(reference 케이스가 기존 엔진과 안 맞음). 원인은 "보유 중"과 "buffer 규칙이 실제로 넘겨준 것"을 구분 안 한 것. 각 구간마다 buffer 규칙이 명시적으로 "이어서 보유"로 판단한 종목 집합(`carried`)을 별도로 추적하도록 수정 — buffer가 꺼져 있으면 `carried`는 항상 공집합이라 매 구간 전량 재매수/재매도가 강제됨. 수정 후 `buffer_multiplier=None`이 `run_baseline_backtest`와 top_n=1/2/3에서 완전히 동일한 거래 내역을 내는 것을 회귀 테스트로 고정. 테스트 4개 추가(정상 회귀 재현, 지속 보유 종목의 중간 구간 비용 면제, 회전율 감소 확인, `buffer_multiplier<1.0` 거부), 전체 166개 통과.
- **사전등록 그리드**(`scripts/walk_forward_buffer_cost_grid.py`, top50 유니버스, 3개 walk-forward 구간, validation만 사용): 전략={reversal, ml}(모멘텀은 항목 33에서 비용 이전부터 이미 음수라 제외), top_n={5,10}, buffer_multiplier={none, 1.5, 2.0, 3.0}, 슬리피지={0.10%(기존 기본값), 0.03%}. gross/excess는 buffer와 무관해서 1회만 계산, net/net_cum/net_mdd/entries_per_period(회전율 진단)는 그리드 셀마다 계산. `buffer_multiplier=none, slippage=0.10%` 기준값이 항목 33에서 이미 기록된 수치(예: reversal top5 net -0.105%/5일, ML top10 net -0.166%/5일)와 정확히 일치하는 것으로 엔진 정합성 확인.
- **결과(현재 0.10% 슬리피지 가정 기준)**: **top_n=10, buffer_multiplier=3.0에서 reversal과 ML 둘 다 3개 구간(W1/W2/W3) 전부 net_cum이 양수로 전환됨** — reversal10: W1 +12.0%, W2 +22.4%, W3 +28.9%; ML10: W1 +23.9%, W2 +1.7%, W3 +42.8%. 같은 설정에서 회전율(entries_per_period)은 10.00(매 구간 전량 교체)에서 2.09~3.83(약 65~80% 감소)으로 줄어듦 — 가설대로 불필요한 왕복거래 비용이 순손실의 상당 부분이었던 것으로 보임. top_n=5는 구간별로 부호가 엇갈려(W1 reversal5 buf3 -22.2% vs ML5 buf3 +21.2%, 반대로 W2는 그 반대 부호) top_n=10만큼 일관되지 않음. 슬리피지를 0.03%로 낮추면 더 많은 조합이 양전환되지만(예: ML top5 buffer≥1.5x 전부 양수), 이건 비용 가정을 낙관적으로 바꾼 결과라 별개로 다뤄야 함(다음 단계 4번, 가정 검증).
- **캐비어트**: (1) MDD는 양전환된 조합에서도 여전히 -20%~-45%로 큼 — 순수익이 플러스라고 해서 실전 투입 가능하다는 뜻은 아님. (2) 그리드가 2×2×4×2=32칸이라 다중비교 우려가 있으나, top_n=10/buffer=3.0 조합은 3개 구간 전부·reversal/ML 둘 다에서 일관되게 나타나 단일 구간 우연히 걸린 결과보다는 신뢰도가 높음. (3) top50 생존편향(AGENTS.md 23절)은 항목 33과 동일하게 적용됨. (4) 이 결과는 여전히 validation만 사용했고 test는 안 건드림.
- **다음 단계**: (1) top_n=10/buffer_multiplier=3.0을 새 기본 운용 파라미터로 채택할지 재훈이 결정 — 채택한다면 `run_ml_backtest.py` 등 실제 운용 스크립트를 `run_baseline_backtest`에서 `run_buffered_backtest`로 바꿔야 함(아직 안 바꿈, 지금은 실험 스크립트에만 존재). (2) pre-registered checklist 3번(IC 기준 early stopping)으로 이동 — W3 `best_iteration=8` 문제가 이번 재실행에서도 그대로 재현됨(W1=294, W2=45, W3=8). (3) 슬리피지 가정 자체의 현실성 검증(다음 단계 4번)은 이 buffer 결과가 그 가정에 민감하다는 걸 확인했으므로 우선순위가 올라감.

36. **Early stopping을 cross-sectional rank IC 기준으로 변경 — RMSE 기준이 "사실상 미학습"으로 붕괴하는 구간을 실제로 구제함(validation 전용)**

- **배경**: 항목 30/31/33/35에서 반복 관찰된 문제 — RMSE로 fit·early stopping하면 `target_return_5d`의 분산 대부분을 차지하는 종목-공통(market-wide) 성분 때문에 몇 라운드 만에 개선이 멈추고(`best_iteration` 0~8), 그 결과 그날 모든 종목의 예측이 사실상 동일해져(같은 leaf) coverage가 무너지는 경우가 있었음(top50 W3 rank 타깃 `best_iteration=8`이 항목 33/35에서 두 번 재현). 종목 간 상대 순위만 보는 cross-sectional rank IC는 그 공통 성분이 구조적으로 상쇄되므로, 같은 기준으로 early stopping하면 이 붕괴를 피할 수 있을 것이라는 가설.
- **구현**: `src/models/predict.py`에 `train_model(..., early_stopping_metric="rmse"|"ic")` 파라미터 추가(기본값 `"rmse"`라 기존 모든 호출부는 동작 불변). `"ic"`는 XGBoost의 custom `eval_metric` callable로 `-mean_ic`(날짜별 rank IC 평균의 부호 반전, `src/ml/cross_section.py`의 `daily_rank_ic`/`summarize_ic` 재사용 — IC 미정의일은 0으로 처리해 항목 30의 coverage-aware 관례와 동일)를 반환하는 `_make_ic_eval_metric()`을 사용. XGBoost 3.2.0의 실제 동작(콜러블은 튜플이 아니라 순수 float 반환, 시그니처는 `(y_true, y_pred)`, 작을수록 좋음이라는 관례를 그대로 따름 — RMSE와 동일)을 별도 토이 스크립트로 먼저 검증한 뒤 구현. `"ic"`를 쓰려면 `X_val`에 `trade_date` 컬럼이 있어야 하며(날짜별로 IC를 계산해야 하므로), 없으면 명시적 `ValueError`.
- **테스트**: `tests/test_predict.py`에 3개 추가 — `trade_date` 없이 `"ic"` 요청 시 에러, 알 수 없는 `early_stopping_metric` 값 거부, 그리고 항목 30-32가 진단한 문제를 그대로 재현하는 합성 cross-sectional 데이터(날짜별 큰 공통 충격 + 작은 학습 가능 신호)에서 `"ic"`로 학습한 모델의 검증 IC가 `"rmse"`로 학습한 모델의 검증 IC보다 나쁘지 않음을 확인. (`best_iteration` 자체의 대소는 검증하지 않음 — 수백 일 단위의 라운드별 IC는 그 자체로 잡음이 커서 ic 쪽이 더 일찍 멈출 수도 늦게 멈출 수도 있고, 실제로 중요한 것은 최종적으로 도달한 지점의 실전 지표(IC) 성능이기 때문.) 전체 테스트 166 → 169개 통과.
- **실데이터 검증(`scripts/compare_early_stopping_metric.py`, top50, 3개 walk-forward 구간 × {raw, rank} 타깃, validation만 사용, test 미접근)**:

  | window | target | stop_on | best_iter | val_ic | coverage |
  |---|---|---|---|---|---|
  | W1 | raw | rmse | 157 | 0.0609 | 100.0% |
  | W1 | raw | ic | 134 | 0.0614 | 100.0% |
  | W1 | rank | rmse | 294 | 0.0635 | 100.0% |
  | W1 | rank | ic | 47 | 0.0626 | 100.0% |
  | W2 | raw | rmse | **0** | **-0.0010** | **0.9%** |
  | W2 | raw | ic | 44 | **0.0357** | 100.0% |
  | W2 | rank | rmse | 45 | 0.0413 | 100.0% |
  | W2 | rank | ic | 49 | 0.0417 | 100.0% |
  | W3 | raw | rmse | 55 | 0.0024 | 99.9% |
  | W3 | raw | ic | 48 | 0.0046 | 98.6% |
  | W3 | rank | rmse | 8 | 0.0130 | 99.9% |
  | W3 | rank | ic | 4 | 0.0154 | 99.9% |

- **관찰**: (1) 실제로 완전히 붕괴한 사례는 W2의 raw 타깃이었음(원래 우려했던 W3가 아니라) — `best_iteration=0`, coverage 0.9%(사실상 랜덤). `"ic"`로 바꾸자 `best_iteration=44`, coverage 100%, val_ic가 -0.0010 → 0.0357로 회복해 같은 구간 rank 타깃 수준(0.041x)에 근접함 — 이 항목이 원래 노리던 "미학습 붕괴 구제"가 실제로 일어난 유일하지만 뚜렷한 사례. (2) 애초에 붕괴하지 않았던 조합(W1 전체, W2/W3 rank)에서는 `"ic"`가 val_ic를 소폭 개선(W1 raw, W3 raw/rank)하거나 소폭 악화(W1 rank: 0.0635→0.0626)시키는 정도로, 어느 쪽도 악화 폭이 크지 않음. (3) W3 rank 타깃(원래 이 항목을 촉발한 `best_iteration=8` 문제, 항목 33/35)은 `"ic"`로 바꿔도 `best_iteration`이 오히려 더 낮아짐(8→4)에도 val_ic는 개선(0.0130→0.0154) — 즉 "더 오래 학습시켜서" 고쳐지는 문제가 아니라, RMSE 기준으로 고른 정지 지점 자체가 IC 관점에서는 최선이 아니었던 것으로 보임. (4) 종합하면 rank 타깃이 여전히 raw 타깃보다 전반적으로 안정적이라는 항목 32의 결론은 유지되며, `"ic"` early stopping은 rank 타깃과 결합했을 때 W1에서만 미미하게 손해(-0.0009)를 보고 W2/W3에서는 동률이거나 개선.
- **결론**: IC 기준 early stopping은 (a) RMSE 기준이 완전히 붕괴하는 극단적 사례를 실제로 구제하고, (b) 이미 정상 작동하던 사례를 크게 훼손하지 않음. `rank` 타깃 + `early_stopping_metric="ic"` 조합을 새 기본값 후보로 볼 수 있는 근거가 됨 — 다만 `train_model`의 기본값(`early_stopping_metric="rmse"`)은 기존 호출부 하위호환을 위해 아직 바꾸지 않았고(opt-in 상태), 실제로 기본값을 바꿀지·어느 운용 스크립트에 적용할지는 항목 4(Window1/W3 root-cause) 및 5(rank/분류 타겟 채택 결정)와 함께 재훈이 최종 결정할 사항으로 남김.
- **다음 단계**: (1) 이 결과를 pre-registered checklist 4번(Window1/W3 `best_iteration` 원인 조사)에 반영 — 이번 결과로 "원인은 RMSE가 공통 성분에 의해 조기 정체되는 것"이라는 항목 31의 가설이 사실상 확인됨(W2 raw 사례로), 다만 W3 rank의 `best_iteration=8` 자체는 `"ic"`로도 낮게 유지되는 것으로 보아 이 특정 구간은 애초에 학습 가능한 신호가 거의 없어서(항목 32의 "신호 감쇠") 짧게 멈추는 것이 오히려 정상일 가능성도 있음 — 별도 판단 필요. (2) checklist 5번(rank/분류 타겟 채택 + 모멘텀·ML 앙상블)으로 이동. (3) test는 여전히 미접근.

37. **W3 `best_iteration` 근본 원인 조사(pre-registered checklist 4번, 마지막 확인 실험) — 오라클(사후 최댓값) 곡선도 이미 관찰한 값과 사실상 동일 → "학습을 덜 시킨 게 문제"가 아니라 신호 자체가 얕은 게 확인됨. 부산물로 XGBoost 커스텀 eval_metric 콜백의 신뢰 불가 동작 발견**

- **배경**: 항목 36에서 IC 기준 early stopping으로 바꿔도 W3의 `best_iteration`이 오히려 더 낮아지는(rank: 8→4) 현상을 보고, "그럼 아예 early stopping을 끄고 끝까지(현재 프로덕션 상한인 `n_estimators=1000`까지) 학습시켰을 때, 지금 관찰한 것보다 훨씬 좋은 지점이 뒤쪽 라운드에 숨어있는 건 아닌가"를 직접 확인하기로 함(재훈이 제안한 "early_stopping_rounds 크게" vs "n_estimators 고정" 중 후자를 선택 — 전자는 후자의 부분집합이라 별도로 할 필요 없음).
- **버그 발견(중요, 별도 기록 가치)**: 처음 구현에서는 `early_stopping_rounds=None`으로 끄고 항목 36과 동일한 커스텀 IC `eval_metric` 콜러블을 넘긴 뒤 `model.evals_result()`로 라운드별 곡선을 뽑으려 했는데, 그 결과가 명백히 틀렸음(예: round 0의 IC가 -0.32 근처로 나오는데, 같은 라운드의 실제 모델로 `model.predict(iteration_range=(0,1))` 후 직접 `daily_rank_ic`로 계산하면 +0.10 — 둘이 완전히 다름). 합성 데이터로 격리 실험한 결과, `early_stopping_rounds`가 실제로 멈춤을 발생시키지 않는 상황(`None`이든 아주 큰 값이든)에서 XGBoost 3.2.0의 커스텀 `eval_metric` 콜백이 `model.predict()`가 실제로 반환하는 값과 다른 예측값으로 메트릭을 계산해 `evals_result()`에 저장하는 것으로 보임(원인 자체는 XGBoost 내부 동작이라 더 파고들지 않음). `_make_ic_eval_metric` 자체의 버그는 아님 — `early_stopping_rounds`가 실제로 멈춤을 만드는 조건(`train_model`의 정상 사용, 항목 36)에서는 `tests/test_predict.py`로 이미 독립 검증됨. **교훈: 이 프로젝트에서 커스텀 `eval_metric` 콜러블을 쓸 때는 `early_stopping_rounds`가 실제로 멈춤을 발동시키는 용도로만 신뢰하고, `evals_result()`의 라운드별 곡선 값 자체를 읽어서 쓰는 건(특히 조기종료가 실제로 트리거되지 않는 설정에서는) 신뢰하지 말 것.**
- **수정한 방법**: `scripts/diagnose_w3_training_ceiling.py` — `eval_metric`/`eval_set` 없이 `n_estimators=1000`(현재 프로덕션 `DEFAULT_PARAMS`의 상한, 이 실험을 위해 새로 고른 숫자 아님)으로 그냥 한 번 학습시킨 뒤, 라운드 체크포인트(1~100은 매 라운드, 125~1000은 25라운드 간격)마다 `model.predict(X_val, iteration_range=(0,k))`로 직접 예측하고 항목 30에서 이미 검증된 `daily_rank_ic`/`summarize_ic`로 IC를 매번 새로 계산 — XGBoost의 내부 콜백을 전혀 거치지 않음. top50, W3(val 2020-2023H1)만 대상(W1/W2는 이미 두 자릿수 이상 라운드에서 정상 학습되고 있어 조사 대상 아님), raw/rank 타깃 둘 다.
- **결과**:

  | target | 오라클 라운드 | 오라클 val_ic | vs rmse-stop | vs ic-stop |
  |---|---|---|---|---|
  | raw | 49 | +0.0046 | rmse(55, +0.0024) 대비 +0.0022 | ic(48, +0.0046) 대비 +0.0000 |
  | rank | 5 | +0.0154 | rmse(8, +0.0130) 대비 +0.0024 | ic(4, +0.0154) 대비 +0.0000 |

  라운드별 샘플을 봐도(raw: round 1부터 1000까지 대략 -0.002~+0.005 범위를 벗어나지 않음; rank: 대략 +0.006~+0.015 범위 안에서 왔다갔다) 1000라운드 끝까지 어디에도 지금 관찰한 것보다 확연히 더 나은 구간이 없음. 특히 오라클 라운드 자체가 이미 IC 기준 early stopping이 고른 라운드(raw 48↔49, rank 4↔5)와 사실상 일치함 — IC 기준 조기종료가 이미 "그 안에서 가장 좋은 지점"을 거의 정확히 찾아내고 있었다는 뜻.
- **결론**: W3의 낮은 `best_iteration`은 조기종료 기준(RMSE든 IC든)이 학습을 너무 일찍 포기해서 생기는 문제가 아니라, **이 구간 자체에 raw든 rank든 학습 가능한 cross-sectional 신호가 원래 얕다**는 걸 오라클 곡선으로 직접 확인한 것. "더 오래/다르게 학습시키면 W3도 W1/W2 수준으로 좋아질 것"이라는 가설은 기각. 항목 32에서 이미 관찰된 "최근 구간으로 갈수록 신호 감쇠"라는 설명과 정확히 들어맞음. checklist 4번(Window1/W3 원인 조사)은 이걸로 마무리 — W2 raw의 진짜 붕괴는 항목 36에서 IC 기준으로 이미 구제됐고, W3는 "구제할 게 없는(신호 자체가 부족한) 정상 상태"였음이 확인됨.
- **주의(오라클의 한계, 스크립트 docstring에도 명시)**: 오라클은 "미래(뒤쪽 라운드 전부)를 보고 사후에 고른 최댓값"이라 실전에서 재현 불가능한 정보 — 이 결과가 "그러니 더 큰 patience로 학습시키자"는 실전 조치의 근거가 되지는 않음. 순수하게 "학습 가능한 신호의 상한이 지금 관찰한 것보다 훨씬 높은가"라는 진단 질문에만 답하는 용도.
- **회귀 검증**: 이번 항목은 진단 스크립트만 추가(프로덕션 코드 변경 없음), 전체 테스트 169개 그대로 통과. test 구간은 여전히 미접근.
- **다음 단계**: pre-registered checklist 5번(rank/분류 타겟 채택 결정 + 모멘텀·ML 앙상블 실험)으로 이동. 지금까지의 결론을 종합하면: rank 타깃이 raw보다 안정적(항목 32/36), IC 기준 early stopping이 극단적 붕괴를 구제하면서 손해가 거의 없음(항목 36), W3는 신호 자체가 얕아 구조적으로 개선 여지가 제한적임(이번 항목) — 5번에서는 이 결론들을 깔고 "rank 타깃 + IC 기준 early stopping"을 새 기본값으로 채택할지, 모멘텀과의 앙상블이 W3처럼 신호가 얕은 구간을 보완할 수 있는지를 확인.

38. **pre-registered checklist 5번(A): 분류 타깃 확인 → rank 회귀가 항상 같거나 나음(분류 채택 안 함) → "rank 타깃 + IC 기준 early stopping"을 `run_ml_backtest.py`(실제 Phase G 최종 비교 스크립트)의 기본값으로 실제 채택. 부수적으로 top50에서 이 스크립트가 애초에 실행조차 안 되던 버그 2개 발견·수정**

- **(A-1) 분류 타깃 가벼운 확인(`scripts/experiment_classification_target.py`, top50, 3개 walk-forward 구간, validation만 사용)**: 라벨은 "그날 같은 유니버스의 중앙값보다 5일 수익률이 높은가"(같은 날짜 peer 기준 이진화 — `rank_by_date`와 동일한 leakage-safety, 이산화만 다름). `XGBClassifier`(`logloss` 기준 조기종료, 그 외 하이퍼파라미터는 회귀와 동일)로 학습, 예측 확률을 점수로 삼아 raw 타깃 기준 cross-sectional IC로 평가(항목 36과 동일한 비교 관례).

  | 구간 | best_iter | val_ic(분류) | val_ic(rank 회귀, rmse-stop) | val_ic(rank 회귀, ic-stop) | accuracy |
  |---|---|---|---|---|---|
  | W1 | 254 | +0.0622 | +0.0635 | +0.0626 | 52.79% |
  | W2 | 30 | +0.0366 | +0.0413 | +0.0417 | 51.29% |
  | W3 | 1 | +0.0005 | +0.0130 | +0.0154 | 50.63% |

  **결과**: 분류가 3개 구간 전부에서 rank 회귀와 같거나 나쁨 — 특히 W3는 오히려 더 심하게 붕괴(`best_iteration=1`, val_ic 거의 0). accuracy도 51~53%로 동전던지기 수준. **분류로 바꿔서 얻는 이득이 전혀 없음** — 오히려 W3에서 항목 36/37이 이미 다룬 "얕은 신호+조기 정체" 문제가 그대로(또는 더 심하게) 재현됨. 결론: 분류 타깃은 채택하지 않음. (참고: 시간 관계상 분류에 IC 기준 조기종료를 추가로 시도해보진 않았음 — 항목 37에서 이미 이 구간 자체의 신호 상한이 낮다는 게 회귀로 확인됐으므로, 분류로 바꿔 봐도 근본적으로 크게 달라질 것 같지 않다고 판단.)
- **(A-2) 실제 채택**: 위 결과 + 항목 32(rank가 raw보다 3구간 다 안정적)·36(IC 기준이 극단적 붕괴를 구제하며 손해 없음)·37(W3는 조기종료 문제가 아니라 신호 자체가 얕음)을 종합해서, **`scripts/run_ml_backtest.py`**(Phase G의 실제 "ML vs baseline" 최종 비교 스크립트 — 지금까지의 rank/IC 실험은 전부 이 스크립트가 아니라 별도 walk-forward 진단 스크립트에서만 검증됐었음)의 학습 타깃/조기종료 기준을 raw+rmse에서 **rank_by_date(target_return_5d) + `early_stopping_metric="ic"`**로 실제로 변경함. `feature_columns`는 그대로(이 스크립트가 기본으로 쓰는 `SELECTED_FEATURES`가 이미 walk-forward 실험들의 `ALL_19`와 완전히 동일한 19개 feature라 변경 불필요 — 직접 확인함). `predictions_for_dataset`이 만드는 점수는 이제 rank 스케일(대략 -0.5~0.5)이지 실제 수익률이 아니지만, `run_baseline_backtest`의 `score_fn`은 순위 매기기에만 쓰여서 문제 없음(코드 주석으로 명시).
- **버그 발견·수정 2개(이 스크립트를 top50에서 실제로 처음 끝까지 돌려보다가 발견, 항목 5와 별개지만 이걸 고치지 않으면 검증 자체가 불가능했음)**:
  1. `_load_priced_dataset()`가 다른 모든 top50 진단 스크립트와 달리 `+-inf → NaN` 치환을 안 하고 있어서, top50 일부 종목의 feature 값이 inf가 되는 경우(core5에선 안 만났던 경우) XGBoost가 즉시 하드 에러를 냄 — `run_ml_backtest.py`가 top50에서 애초에 한 번도 끝까지 실행된 적이 없었다는 뜻(raw+rmse였던 원래 코드로 되돌려서 재확인함 — 항목 5와 무관하게 이미 존재하던 버그). 다른 스크립트들과 동일한 치환 로직 추가로 수정.
  2. `train_model` 호출에 `n_jobs=1, tree_method="exact"`가 전혀 설정돼 있지 않았음(core5 데이터 초기 items 15/23-25에서 "기기마다 다른 모델이 나올 수 있다"고 확인된 바로 그 문제) — 정작 Phase H 여부를 가르는 진짜 최종 비교 스크립트에 이게 빠져 있었음. `DETERMINISTIC_PARAMS`(다른 스크립트들과 동일)를 추가.
- **검증**: top50/core5 둘 다에서 `STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/run_ml_backtest.py`(및 top50 없이 core5)를 test 구간 확인 플래그 없이 실행 — 학습까지 정상 완료 후 `TestSetLockedError`로 올바르게 멈추는 것 확인(test는 여전히 미접근). top50 결과 `best_iteration=4`로, 항목 36/37의 W3(rank+ic) walk-forward 결과와 **완전히 동일**(같은 학습 구간이므로 당연히 일치해야 하고, 실제로 일치함 — 교차검증 성공). 전체 테스트 169개 그대로 통과.
- **다음 단계**: checklist 5번(B) 모멘텀+ML 앙상블 실험으로 이동. 이제 `run_ml_backtest.py`가 실제로 채택된 설정(rank+ic, deterministic)을 쓰므로, 앙상블 실험도 이 설정으로 학습된 모델의 점수를 기준으로 진행. test는 여전히 미접근 — 앙상블 실험이 끝나야 pre-registered checklist가 완료되고, 그 다음에만 `STOCKLENS_CONFIRM_FINAL_TEST=1`로 이 스크립트를 실제로 한 번 실행해 Phase H 여부를 결정(checklist 6·7번).

39. **pre-registered checklist 5번(B): 반전(reversal)+ML 앙상블 — 모든 구간에서 순수 ML(rank+ic)이 항상 최선, 블렌딩은 도움 안 됨**

- **이름 수정**: 체크리스트 원문은 "모멘텀+ML 앙상블"이지만, `calculate_score`(순수 과거 5일 모멘텀)는 항목 33에서 이미 이 유니버스/기간에 부호가 반대(초과수익 지속적으로 마이너스, W2 t=-3.03)라고 확인됨 — 실제로 통했던 건 그 반대 부호인 **반전(reversal, score=-momentum=-`return_5d`)**이었음(항목 33/35). 그래서 이미 반대로 작동한다고 확인된 신호를 그대로 섞는 대신, 실제로 검증된 반전 신호로 앙상블을 구성함(재훈 확인 받고 진행).
- **방법**(`scripts/experiment_reversal_ml_ensemble.py`, top50, 3개 walk-forward 구간, validation만 사용): ML은 항목 36/38에서 채택한 설정(rank_by_date 타깃, `early_stopping_metric="ic"`, deterministic params)으로 각 구간마다 새로 학습. 검증 구간에서 반전 점수(`-return_5d`)와 ML 예측 점수를 각각 날짜별로 z-score 표준화한 뒤 `blended = alpha*z(reversal) + (1-alpha)*z(ML)`로 블렌딩. `alpha`는 사전등록 그리드 {0.0(순수 ML), 0.25, 0.5, 0.75, 1.0(순수 반전)}. raw 타깃 기준 cross-sectional IC로 평가(항목 32/36/37과 동일 관례).
- **결과**:

  | 구간 | alpha=0(순수ML) | 0.25 | 0.5 | 0.75 | alpha=1(순수반전) |
  |---|---|---|---|---|---|
  | W1 | **0.0626** | 0.0576 | 0.0536 | 0.0470 | 0.0408 |
  | W2 | **0.0417** | 0.0411 | 0.0385 | 0.0352 | 0.0308 |
  | W3 | **0.0154** | 0.0104 | 0.0091 | 0.0096 | 0.0104 |

  **3개 구간 전부 alpha=0(순수 ML)이 최댓값** — 반전을 섞을수록(alpha가 커질수록) W1/W2는 단조 감소, W3는 중간 지점(0.5)에서 오히려 양끝보다 더 나빠졌다가 반전 단독(alpha=1)에서 살짝 회복하지만 여전히 순수 ML보다 못함. 즉 두 신호가 서로 보완되는 지점(중간 alpha에서 양끝보다 좋아지는 지점)이 어디에도 없음.
- **결론**: 반전+ML 앙상블은 도움이 안 됨 — 이미 채택된 순수 ML(rank+ic, 항목 38)이 세 구간 모두에서 블렌딩보다 항상 낫거나 같음. `run_ml_backtest.py`에 앙상블을 추가로 도입할 근거 없음, 현재 설정 유지. (비용 민감도 백테스트까지 갈 필요 없음 — IC 단계에서 이미 명확한 결론이 나왔으므로 항목 35의 buffer 백테스트 그리드로 추가 확인하는 단계는 생략.)
- **회귀 검증**: 진단 스크립트만 추가, 프로덕션 코드 변경 없음, 전체 테스트 169개 그대로 통과. test 미접근.
- **pre-registered checklist 진행 상황**: 1(테스트 락)·2(buffer 그리드)·3(IC 조기종료)·4(W3 근본원인)·5(rank/분류 결정+앙상블) 전부 완료. 남은 건 6(비용/슬리피지 가정 현실성 검증)과 7(최종 test 1회 확인 → Phase H 결정)뿐.

40. **pre-registered checklist 6번: 비용/슬리피지 가정 현실성 검증 — 수수료·세금은 실제 요율과 일치 확인, 세율의 역사적 변동을 발견했으나 "지금 배포한다면"이라는 질문엔 무관하다고 결론(코드 변경 없음)**

- **조사**: 키움증권 온라인 매매수수료는 코스피/코스닥 매수·매도 각 0.015%, 유관기관 수수료 별도 없음(2026년 기준) — `BaselineConfig` 기본값(`buy_fee=0.00015, sell_fee=0.00015`)과 정확히 일치. 증권거래세+농특세 합산세율은 2023-01-01부터 코스피·코스닥 공통 0.20%(현재도 유지) — `BaselineConfig.sell_tax=0.0020`과 정확히 일치.
- **발견(역사적 세율 변동)**: 다만 이 세율은 최근에서야 0.20%가 됐고, 그 이전 구간은 더 높았음 — ~2020년 0.25%, 2021~2022년 0.23%, 2023년~ 0.20%. 지금까지의 모든 walk-forward 백테스트(W1 2012-2015, W2 2016-2019, W3 2020-2023H1)는 전 구간 실제로는 더 높았던 시기인데도 균일하게 현재 세율(0.20%)로 계산돼 있음.
- **판단(재훈 질문 "이 재검증이 지금 의미가 있냐"에 대한 결론)**: **의미 없음 — 오히려 지금 방식(균일하게 현재 세율 적용)이 맞는 방법론**. 이 백테스트의 목적은 "그때 실제로 거래했다면 얼마 벌었을까"를 재현하는 게 아니라 "지금/앞으로 이 전략을 배포하면 어떨까"를 판단하는 것이고, 실전 배포는 항상 현재 세율(0.20%)로 이뤄짐. W1/W2/W3는 비용은 고정한 채 "서로 다른 시장 국면에서도 신호가 일관되는가"를 보는 용도임. 또한 이 편향은 모멘텀/반전/ML, buffer 유무 등 모든 비교 대상에 동일하게 적용돼 상대 비교에는 영향이 없고, 과거 세율(더 높음)로 다시 계산하면 절대 수익률은 오히려 더 나빠지는 방향이라 실전 배포 판단을 낙관적으로 왜곡하지도 않음. 따라서 역사적으로 정확한 세율 스케줄로 재검증하는 코드 작업은 하지 않기로 함.
- **슬리피지**: 실제 시장충격/슬리피지는 요율표처럼 찾을 수 있는 값이 아니라 가정이며, 항목 35에서 이미 0.10%(기본)와 0.03%(낙관적) 두 값으로 민감도를 확인함 — 추가 작업 불필요.
- **결론**: 비용 가정 검증 완료. `BaselineConfig` 기본값 변경 없음. checklist 6번 종료.
- **다음 단계**: checklist 7번(최종 test 1회 확인) — pre-registered checklist 1~6번이 전부 끝났으므로, 재훈이 준비되면 `STOCKLENS_CONFIRM_FINAL_TEST=1`로 `run_ml_backtest.py`(항목 38에서 rank+ic로 업데이트됨)를 실제로 한 번 실행해 최종 test 결과를 확인하고 Phase H 진행 여부를 결정.

41. **pre-registered checklist 7번(최종): 유일한 test 확인 실행 완료 — baseline 대비 4개 지표 전부 개선, Phase H 진행 결정. 단 concentration/MDD/비교 기준/buffer 미적용 등 유보사항 명시**

- **실행**: 재훈이 직접 `STOCKLENS_UNIVERSE=top50 STOCKLENS_CONFIRM_FINAL_TEST=1 PYTHONPATH=. python scripts/run_ml_backtest.py`를 1회 실행. `Best iteration: 4` — 항목 36-38에서 validation으로 확인한 W3 rank+ic 결과와 정확히 일치(같은 학습 구간이므로 당연히 일치해야 하고, 실제로 일치함으로써 학습 파이프라인 자체가 이 스크립트에서도 정상 동작함을 재확인). Test 기간 2023-07-03~2026-09-14, `top_n=2`(동일가중), 154개 리밸런싱 구간, 308개 포지션.
- **결과**:

  | | 누적수익 | 구간평균수익 | Hit Rate | MDD |
  |---|---|---|---|---|
  | 모멘텀 baseline | -54.4705% | -0.2053% | 45.4545%(70/154) | -71.3749% |
  | ML(rank+ic) | **+311.3914%** | **+1.1168%** | **57.1429%(88/154)** | **-40.5908%** |

  (`average_trade_return`/`win_rate`는 `calculate_performance`의 구현상 개별 트레이드가 아니라 **구간(period) 단위**로 가중평균된 값 — 154개 구간 기준. Hit Rate 45.4545%=70/154, 57.1429%=88/154로 정확히 재현됨.)
- **해석 — 유보사항 없이 볼 수 없는 결과임**:
  - **(a) top_n=2 집중도 / 분산 확인**: 50종목 중 매번 2종목에만 배팅하는 구조라 구간별 결과의 변동성이 큼. 산술평균 구간수익(+1.1168%)으로 무분산 복리를 가정하면 154구간 후 누적수익은 약 +453%가 나와야 하는데, 실제 누적수익은 +311%로 그보다 상당히 낮음 → 역산한 기하평균 구간수익은 약 +0.92%, 즉 산술-기하 격차(분산 손실)로부터 역산한 구간당 수익 표준편차는 대략 6%대. 이 스케일 자체는 프로젝트가 이미 관측한 개별 종목 5일 수익률의 변동폭(개별 트레이드 gross return이 +20~34%까지 나오는 경우도 있었음)과 어울리는 수준이라 "한두 건의 이상치가 전부를 설명"한다고 단정할 근거는 아니지만, 이 집계 수치만으로 "넓게 분산된 edge"인지 "몇 번의 큰 승리가 대부분을 견인"했는지 확정할 수는 없음. 확정하려면 308건 트레이드의 `net_return` 분포(상위 몇 건이 전체 수익에서 차지하는 비중)를 직접 봐야 하는데, 그건 이미 한 번 생성된 출력(터미널 trade table)을 다시 들여다보는 것뿐이라 test 재접근이 아님 — 재훈이 이미 갖고 있는 그 출력에서 확인 가능.
  - **(b) MDD -40.59%**: baseline보다는 훨씬 낫지만 그 자체로 작지 않은 값. ML 전략도 도중에 고점 대비 -40%까지 빠지는 구간을 실제로 겪었다는 뜻 — "이겼다"는 결과 서사에 가려지기 쉬운 리스크이므로 실전 배포 시 포지션 사이징에서 반드시 고려해야 함.
  - **(c) 비교 기준의 한계(모멘텀 baseline)**: 항목 33에서 이 유니버스/기간에 플레인 모멘텀이 구조적으로 역방향(음의 t-stat)임이 이미 검증됨. 이번 test 결과가 그 역방향성이 test 구간(2023-07~2026-09)에서도 유지된다는 걸 새로 확인한 건 나름 의미가 있지만, "ML이 모멘텀을 이겼다"는 "ML이 반전(reversal)을 이겼다"보다 약한 증거임. 이 최종 test 실행에서 ML 단독 vs reversal 단독을 직접 비교하지는 않았고 — 그 비교를 지금 test로 새로 하는 것은 "체크리스트당 test는 한 번만 본다"는 원칙 위반이라 하지 않음. 다만 validation에서는 항목 39가 3개 구간 전부(W1/W2/W3)에서 순수 ML(alpha=0)이 순수 반전(alpha=1)보다 IC가 항상 높다는 걸 이미 확인해뒀음(0.0626 vs 0.0408, 0.0417 vs 0.0308, 0.0154 vs 0.0104) — 즉 "ML이 반전보다 낫다"는 근거는 test가 아니라 validation에 이미 존재함.
  - **(d) buffer(회전율 절감) 엔진 미적용**: 이번 실행은 항목 35의 buffer 엔진이 아니라 매 구간 전량 재매수/재매도하는 원래 엔진(`run_baseline_backtest`)을 사용함. buffer 엔진을 쓰면 비용이 줄어 실제 배포 시 수익률이 이보다 나을 여지가 있음 — 뒤집어 말하면 이번 결과는 "더 불리한 비용 조건에서도 이긴다"는 보수적인 숫자이기도 함. buffer 엔진을 최종 결정 스크립트에 반영해서 다시 test를 보는 것은 이번 사이클의 일이 아니라 이후 별도로 결정할 사안.
  - **(e) 표본 크기**: 154구간/308포지션은 작지 않지만 단일 test 기간 하나에서 나온 결과라 "이 성과가 앞으로도 반복된다"고 통계적으로 확정할 수 없음(AGENTS.md 22) — 이는 체크리스트 설계 시점부터 인지한 한계이지 새로 발견된 문제는 아님.
- **결론(Phase H 진행 여부)**: 지금까지의 전체 증거 — 3개 walk-forward validation 구간 전부에서 일관된 양의 IC(항목 32/36), IC 기반 조기종료가 RMSE 붕괴를 구제(항목 36), W3의 낮은 `best_iteration`이 학습 부족이 아니라 실제 신호 한계임을 확인(항목 37), 분류·반전+ML 앙상블 등 대안이 전부 rank+ic와 같거나 못함(항목 38/39), 비용 가정이 실제 요율과 일치함(항목 40), 그리고 이번 유일한 test 확인에서 4개 지표(누적수익/평균수익/Hit Rate/MDD) 전부 baseline 대비 개선 — 을 종합하면 **Phase H(인트라데이 데이터)로 진행하는 것은 근거 있는 결정**. 다만 (a)-(d)는 "당장 안심하고 실전 자금 배포"와는 별개 문제이므로, Phase H 착수와 병행/후속으로 (i) buffer 엔진을 최종 결정 경로에 통합하는 작업, (ii) top_n 민감도(집중도 vs 분산) 판단, (iii) 실사용 전 리스크 관리(포지션 사이징, 드로다운 대응) 설계가 필요함 — 이들은 "test를 또 보는" 게 아니라 이미 검증된 신호를 운용 가능한 형태로 다듬는 별개의 엔지니어링 트랙임.
- **다음 단계**: pre-Phase-H checklist(1~7번) 전 항목 종료. Phase H(인트라데이 데이터 도입) 착수. 이번 test 결과는 이번 결정 사이클의 유일한 test 확인이었으므로, 앞으로 daily 모델을 추가로 손보고 싶어지더라도(예: top_n 조정, buffer 엔진 최종 반영 확인 등) 그건 새로운 별도의 결정 사이클로 취급하고, 최소 하나의 pre-registered 실험 설계를 다시 거친 뒤에만 test에 접근할 것 — 이번 결과를 보고 "이 부분만 다시 손보자"는 식으로 test를 다시 들여다보지 않는다.

42. **Phase H 착수: `ka10080`(분봉) 클라이언트 + raw 수집 + decision-timestamp leakage cutoff 구현, 실데이터로 검증 완료**

- **배경**: 항목 41에서 daily ML(rank+ic)이 test 구간에서 baseline 대비 4개 지표 전부 개선하며 Phase H(인트라데이) 진행이 결정됨. 이 항목은 그 착수 작업 — decision timestamp 설계와 `ka10080` 데이터 파이프라인 최초 구현 — 을 기록.
- **decision timestamp 설계**: 파일럿 범위를 다음과 같이 확정 — (a) 날짜당 스냅샷 1개(그리드 아님 — 기존 walk-forward/IC 평가체계를 그대로 재사용하기 위함이자 AGENTS.md 35절의 분봉 자기상관 경고를 처음부터 피하기 위함), (b) 14:00 KST 고정(AGENTS.md 6.1절 예시와 일치, 정규장 마감 90분 전), (c) target(`target_return_5d`)/entry(T+1 시가)는 기존 daily 파이프라인 그대로 유지 — feature-cutoff 하나만 바꾸는 단일 변수 실험 원칙. **아직 반영 안 한 것**: 기존 daily feature(`SELECTED_FEATURES`)의 기준을 T가 아니라 T-1로 옮기는 작업 — decision timestamp를 14:00으로 당기면 T 자체가 아직 미완성 봉이라, 기존 daily feature 파이프라인이 지금처럼 T행(T의 완성 종가 기반 SMA/RSI/MACD/ATR 등)을 그대로 쓰면 조용히 leakage가 생김. 다음 단계로 남겨둠.
- **`ka10080` 클라이언트** (`src/api/kiwoom_client.py`): `get_minute_chart_page()`(단일 페이지 raw 조회, `cont-yn`/`next-key` 헤더 노출) + `get_minute_chart_history()`(`get_daily_chart()`와 동일한 continuation-following 패턴, `stop_date` 파라미터로 수집 범위를 명시적으로 제한). `scripts/check_kiwoom_minute_chart.py`로 실 API를 먼저 점검한 뒤(AGENTS.md 8절 "추측 대신 실제 스키마를 확인하라" 원칙) 그 결과를 반영해 누적 수집 메서드를 구현하는 순서로 진행.
- **실데이터 검증(005930, tic_scope=15)**: (1) 한 페이지가 `base_dt` 하루치가 아니라 ~30일치(900행)를 반환하고, continuation이 daily(`ka10081`)와 동일하게 과거로 페이지를 넘김을 확인(페이지 경계에서 겹침/공백 없이 정확히 15분 간격 — page1 최고참 봉 `20260811141500` ↔ page2 최신참 봉 `20260811140000`) — 애초에 예상했던 "하루 단위 수집" 가정은 틀렸음이 확인되어 정정함. (2) `stop_date="20260622"`로 005930 3개월치(2026-06-22~09-23) 수집 시 3페이지(API 콜 3회)로 1866행 수집 — 분봉 수집 비용이 처음 우려했던 것보다 훨씬 저렴함. (3) **중요 발견**: `ka10080` 응답에 정규장(09:00~15:30) 밖 시간대(NXT/시간외, 관측된 예시는 18:00대까지)가 섞여 들어옴 — 3개월 파일럿 기준 112/1866행(6.0%).
- **raw 저장** (`src/data/storage.py::save_raw_ka10080`, `src/data/ingest.py::ingest_kiwoom_minute_chart_raw`, `scripts/ingest_kiwoom_minute_chart.py`): `ka10081` 저장 패턴과 동일하게 `data/raw/kiwoom/ka10080/<종목>/<타임스탬프>.json`에 저장. `stop_date`를 CLI 필수값으로 강제(파일럿이 실수로 전체 이력까지 걸어가는 것 방지). 정규화(`MinuteBar` 모델)는 아직 구현 안 함 — 스키마 확정 전 결정할 게 남아있었음(다음 항목에서 그 이유가 드러남).
- **`as_of_snapshot()` leakage cutoff** (`src/data/intraday.py`): 시간외 데이터 발견으로, 14:00 cutoff가 단순히 "`cntr_tm` ≤ 1400"이 아니라 날짜별로 다른 규칙이 필요함이 드러남 — ① decision_date(T) 당일은 09:00~14:00만 유지(그 이후는 leakage), ② T 이전 날짜는 09:00~15:30 정규장 전체 유지(시간외만 제외 — leakage가 아니라 다른 트레이딩 레짐이라서 제외). `src/feature_selection/data_loading.py`/`src/eval/test_lock.py`와 같은 "주석이 아니라 코드로 강제" 원칙 적용. 단위 테스트 8개(`tests/test_intraday.py`) 전부 통과.
- **실데이터로 두 규칙 모두 개별 검증**: (규칙②) 2026-06-22~09-22 과거 구간에 적용 시 정확히 112행이 제거됨(제거된 행 전부가 decision_date 이전 날짜였고 decision_date 당일 제거는 0건 — 시간외 규칙만 실제 작동을 확인한 것이었음이 명확히 구분됨). (규칙①) 09-01을 가짜 decision_date로 설정해 별도 검증 — 필터 전 27행(0900~1530), 필터 후 21행(0900~1400)으로 정확히 14:15~15:30 구간의 15분봉 6개만 제거됨을 확인. 두 규칙 모두 실데이터에서 의도대로 동작함이 각각 독립적으로 확인됨.
- **테스트**: 이번 사이클에서 추가된 테스트 — kiwoom client 10개(`get_minute_chart_page`/`get_minute_chart_history`), storage/ingest 3개, intraday cutoff 8개 — 전부 로컬 통과 확인. (참고: 이 작업은 별도 세션의 코드 리뷰 환경에서 진행되어 xgboost/pandas 등 ML 스택이 없는 상태로 검증함 — 이번 패치가 건드린 파일과는 무관한 모듈들이라 전체 스위트는 재훈 기기에서 재확인 권장.)
- **다음 단계(미완료)**: (1) 기존 daily feature(`SELECTED_FEATURES`)의 기준을 T-1로 옮기는 작업(leakage 없이 14:00 decision timestamp와 맞물리게 — 이 항목 "decision timestamp 설계"에서 이미 지적된 남은 일). (2) `as_of_snapshot()`으로 자른 09:00~14:00 분봉에서 intraday summary feature 후보 설계(그날 누적 수익률, 변동성, 거래량 비율 등, AGENTS.md 7절 예시 참고). (3) 기존 `rank_by_date + early_stopping_metric="ic"` 파이프라인에 이 feature들을 추가해 재학습 — validation-only, walk-forward, test는 미접근(AGENTS.md 13절 원칙 유지, 항목 34의 `confirm_final_test_use` 그대로 적용됨). (4) 지금은 005930 1종목만 파일럿 수집됨 — 신호가 있다는 게 확인되면 core5 나머지, 필요시 top50까지 raw 수집 확장.

43. **실험 시계열 저장 + 그래프 생성 기반 추가 (`src/reporting/run_log.py`, `scripts/plot_run.py`)**

- **배경**: 지금까지 실험 결과는 터미널 출력과 Notion 요약 표로만 남아서, 전략이 "언제" 벌고 잃었는지(누적수익 경로, 낙폭 구간, IC의 시기별 변화)를 다시 볼 방법이 없었음. Notion은 실험당 요약 숫자만 담으므로, 시계열은 코드가 자동으로 저장하고 그래프로 그리는 구조를 추가함.
- **저장** (`src/reporting/run_log.py`): `RunRecorder`로 스크립트 실행 중 trades와 daily rank IC를 모은 뒤 `save()` 한 번으로 `reports/runs/<시각>_<이름>/`에 `periods.csv`(구간 순수익), `trades.csv`, `ic_daily.csv`, `meta.json`을 기록. 구간 수익은 `calculate_performance`와 같은 방식(결정일당 가중평균, 구간당 1회 복리)으로 계산해 누적수익이 기존 출력과 정확히 일치함(테스트로 고정). 이 모듈은 데이터를 읽거나 분할을 고르지 않고 호출자가 이미 계산한 값만 받으므로 test 접근 범위를 넓히지 않음.
- **그래프** (`scripts/plot_run.py`): 저장된 run 폴더만 읽어 `figures/`에 `equity.png`(로그축 누적수익), `drawdown.png`, `ic.png`(롤링 평균 IC + 누적 IC, 누적 IC의 기울기가 평균 IC라 평탄해지면 신호 감쇠), `summary.csv`(패널/시리즈별 누적수익·MDD·Hit Rate·평균 구간수익·평균 IC) 생성. 같은 전략은 모든 그림에서 같은 색, 설정(top_n 등)은 선 스타일로 구분. `--series`/`--panel` 필터 결과는 `figures_<필터>/`에 따로 저장.
- **연결**: `scripts/walk_forward_backtest_compare.py`(validation 전용)는 매 실행마다 전략·top_n·구간별 순수익 trades와 ml/reversal의 daily rank IC를 저장. `scripts/run_ml_backtest.py`는 test 잠금을 통과한 경우에만 끝에서 결과를 저장 — 이후 그래프는 저장본으로 다시 그리면 되므로 그래프를 위해 test 스크립트를 재실행할 일이 없도록 함(재실행은 새로운 test 접근). 과거 항목 41의 test 결과는 저장본이 없고, 그래프를 위해 재실행하지 않음.
- **검증**: top50으로 `walk_forward_backtest_compare.py`를 재실행해 저장본의 `summary.csv` 누적수익이 터미널 표의 `net_cum`과 일치함을 확인(예: W3 ml top_n=5 +8.3%). `tests/test_reporting.py` 5개 추가. `reports/runs/`는 재생성 가능한 산출물이라 `.gitignore`에 추가, `requirements.txt`에 `matplotlib` 추가.
- **참고**: 이 스크립트의 ML은 항목 33 시점 설정(rank 타깃, RMSE 기준 early stopping)이라 항목 36·38에서 채택한 IC 기준 early stopping과는 다름 — 그래프는 항목 33 결과의 시각화로 읽어야 함.

44. **타깃 진입 시점 변경(`entry="next_open"`)이 walk-forward ML 수치를 바꾼 것 확인 — leakage 아님, 항목 33~41의 ML 수치는 이전 타깃(`close`) 기준으로 읽어야 함**

- **발견 경위**: 2026-09-26 top50 `walk_forward_backtest_compare.py` 재실행에서 모멘텀/반전 수치는 항목 33과 소수점까지 동일한데 ML만 달라짐(best_iteration W1/W2/W3 294/45/8 → 118/53/9, ML top5 평균 t(excess) 1.34 → 1.67, net -0.128% → -0.060%/5일). `compare_early_stopping_metric.py` 재실행 결과도 항목 36 표와 전부 다름.
- **원인**: 커밋 `b1614a4`(2026-09-26)의 `src/data/dataset.py` 변경 — 타깃 기본값이 `close(t+5)/close(t)-1`에서 `close(t+5)/open(t+1)-1`(`DEFAULT_ENTRY_MODE="next_open"`, 2026-09-24 결정, Notion "Entry timing IC on top-50 universe")로 바뀜. 백테스트 엔진은 원래부터 T+1 시가 진입이었으므로 새 타깃이 엔진이 실제로 실현하는 수익과 정확히 일치함(더 올바른 정의). 모멘텀/반전은 타깃을 쓰지 않으므로 불변, ML만 바뀐 것과 정확히 들어맞음. xgboost 버전(3.4.1)·`tree_method="exact"`·학습 코드 변경 없음 — 같은 스크립트를 xgboost 3.2.0(Linux)에서 돌려도 재훈 기기와 동일 수치(W1 rank+ic best_iteration 103, val_ic 0.0665)가 나와 환경 요인도 배제됨.
- **새 타깃 기준 수치(`compare_early_stopping_metric.py`, validation)**: rank 타깃 val_ic W1 0.0663(rmse)/0.0665(ic), W2 0.0457/0.0458, W3 0.0218/0.0218 — 이전 타깃 대비 3구간 모두 상승(W3 0.0154 → 0.0218). raw 타깃 W2 rmse 붕괴(항목 36의 best_iteration=0)는 더 이상 재현되지 않음(175, 0.0379) → 새 타깃에서는 rmse/ic 조기종료 차이가 거의 사라짐. rank 타깃 우위는 유지되므로 항목 38의 채택(rank + ic)은 그대로 둠.
- **영향**: (1) 항목 33~41의 ML 수치와 항목 41의 test 결과(best_iteration 4)는 `close` 타깃 기준. 현재 코드로 `run_ml_backtest.py`를 돌리면 다른 모델이 나옴 — 그렇다고 test를 다시 보지 않음(항목 41 원칙). 재현이 필요하면 `entry="close"`. (2) `walk_forward_backtest_compare.py`의 저장본(`reports/runs/20260926-123548_*`)이 새 타깃 기준선.
- **주의(Phase H 데이터 기간)**: `ka10080`은 약 1년치(2025-09-01~)만 제공 → 분봉 데이터 전체가 daily test 구간(2023-07~2026-09) 안에 있음. 분봉 IC 진단(Notion "Intraday summary features IC diagnostic")은 이미 이 구간을 사용함. 분봉 feature를 모델에 넣는 결정은 이 1년 안에서 별도 개발/홀드아웃을 나누거나, 앞으로 매일 쌓이는 신규 데이터를 forward 홀드아웃으로 삼아야 함(미결정).

45. **일봉 분해 5일 feature(gap_sum_5, intraday_sum_5, range_mean_5) 추가 실험 — 사전등록 기준 미달, 19개 유지**

- **목적**: Notion Phase H 계획 2번. next_open 타깃에서 train/validation 모두 신호가 보였던 3개 feature(특히 gap_sum_5: 베타중립 IC train -0.034 t -7.3, validation -0.041 t -3.9)를 모델에 넣으면 좋아지는가.
- **방법**(`scripts/experiment_decomposition_features.py`, top50, 3개 walk-forward 구간, validation만): A = ALL_19, B = ALL_19 + 3개. rank 타깃, `early_stopping_metric="ic"`, deterministic params. top_n=10, 실제 비용, buffer 없음/3.0. **사전등록 기준**: 3개 구간 전부 val IC(B) > IC(A) 그리고 buffer 순누적 평균 B ≥ A일 때만 채택.
- **결과**:

  | 구간 | A val_ic | B val_ic | A buf3 net_cum | B buf3 net_cum |
  |---|---|---|---|---|
  | W1 | 0.0665 (it 103) | 0.0640 (it 14) | +34.8% | +30.6% |
  | W2 | 0.0458 (it 55) | 0.0440 (it 22) | +15.9% | +8.6% |
  | W3 | 0.0218 (it 9) | 0.0246 (it 4) | +65.0% | +71.5% |

  IC는 W3만 개선(+0.0029), W1·W2 하락. buffer 순누적 평균 A +38.5% vs B +36.9%. → **기준 미달, 19개 유지**. 3개 feature를 넣으면 best_iteration이 크게 짧아짐(103 → 14 등) — 새 feature의 단순 반전 신호를 모델이 빨리 흡수한 뒤 조기종료되는 것으로 보이며, 기존 19개가 이미 반전(return_1d, price_to_sma_5 등)을 담고 있어 추가 정보가 적었던 것으로 해석.
- **부산물(중요)**: 새 타깃 기준 A(현 설정)의 top_n=10 + buffer 3.0은 3개 구간 전부 순누적 흑자(+34.8% / +15.9% / +65.0%, MDD -19.5% / -35.5% / -43.7%) — 항목 35의 이전 타깃 결과(+23.9% / +1.7% / +42.8%)보다 3구간 모두 개선. buffer 엔진을 최종 운용 경로에 넣는 작업(항목 41 유보사항 (d))의 근거가 강해짐.
- **선택 편향 주의**: gap_sum_5는 validation IC를 본 뒤 고른 후보라 이 실험이 통과했더라도 약한 증거였을 것. 결과가 기각이므로 영향 없음.
- **다음 단계**: (1) buffer 엔진(top_n=10, buffer 3.0)을 `run_ml_backtest.py` 경로에 넣는 새 결정 사이클 설계(test는 사이클 끝에 1회만). (2) 분봉 매일 수집 자동화 + 분봉 홀드아웃 규칙 확정(항목 44 주의). (3) 평가 지표에 베타중립 IC 추가(Notion 계획 3번).

46. **새 결정 사이클 설계: 판단 시점 A 확정, 분봉은 오버레이, 분봉 전용 split·holdout 잠금, 매일 수집 자동화 (사전등록)**

- **배경**: `ka10080`은 약 1년치(2025-09-01~)만 제공 → 분봉 전체가 daily test(2023-07-01~2026-09-16) 안에 있음(항목 44). daily test는 항목 41에서 이미 1회 사용됐고, 분봉 IC 진단(Notion, 2026-09-24)도 2025-09~2026-09-23 전체를 봤음. 따라서 **daily split을 분봉에 그대로 적용할 수 없고, 2026-07~09도 깨끗한 test가 아님.**
- **결정 1 — 판단 시점 A**: T일 확정(20:00 KST, 애프터마켓 종료) 후 판단 → T+1 시가 진입 → T+h 종가 청산. 타깃(`entry="next_open"`), 백테스트 엔진, 분봉 진단과 동일. feature는 T일 정규장(09:00~15:30) 전체를 써도 됨(판단이 장 마감 후라 leakage 아님), T+1 이후는 절대 불가. 장중 판단(B)은 타깃·엔진을 새로 만들어야 하고, 진단상 1일 보유 신호가 비용을 못 넘어서(손익분기 24bp < 왕복 ~43bp) 채택 안 함. 항목 42의 14:00 `as_of_snapshot()`은 장중 판단용으로 남겨두되 이번 사이클에서는 쓰지 않음.
- **결정 2 — 오버레이**: daily 모델(2002~2019 학습, 2020~2023H1 조기종료)은 고정. 2025-09 이후는 daily 입장에서 완전히 out-of-sample. 분봉은 XGBoost에 넣어 재학습하지 않고 `score = z(daily ML) + w·z(intraday)`로만 결합 — 10개월 데이터로 트리 모델을 재학습하기엔 표본이 부족하고, 과거 20년 구간을 분봉 결측으로 채우면 결측 여부가 기간 식별자가 될 위험이 있음. 상호작용(비선형)은 못 잡는 게 대가 — 분봉 2년 이상 쌓이면 재학습 재검토.
- **분봉 split** (`src/data/intraday_split.py`, 판단일 T 기준):

  | 구간 | 기간 | 용도 |
  |---|---|---|
  | dev | 2025-09-01 ~ 2026-06-30 | feature/가중치 결정. 블록 B1(2025-09~12)·B2(2026-01~03)·B3(2026-04~06)로 부호 일관성 확인 |
  | semi_holdout | 2026-07-01 ~ 2026-09-23 | 이미 진단에 쓰여 반쯤 오염. 부호 확인만, 1회. `STOCKLENS_CONFIRM_INTRADAY_SEMI_HOLDOUT=1` 필요 |
  | forward | 2026-09-24 ~ | 유일한 깨끗한 holdout. 판단일 60개 이상 쌓인 뒤 1회. `STOCKLENS_CONFIRM_INTRADAY_FORWARD=1` 필요 |

  - **라벨 purge**: `close(T+h)/open(T+1)-1`이 구간 끝을 넘는 행은 제거(예: 2026-06-29 판단의 라벨이 7월 가격을 읽지 않도록). 블록마다 자기 끝에서 purge.
  - **잠금**: `src/eval/test_lock.py`에 `confirm_holdout_use()` 추가 — 구간마다 별도 환경변수, 하나를 풀어도 다른 구간은 안 풀림. `FORWARD_MIN_DATES=60` 미만이면 환경변수가 있어도 에러.
  - **forward는 daily 트랙과 공유**: 앞으로 daily 모델/운용 변경(buffer 엔진 등)의 최종 확인도 같은 forward 구간에서 같은 시점에 1회만. 가장 빠른 평가 시점은 2026년 12월 말 전후(추석 연휴 반영 시 대략).
- **사전등록 체크리스트 (이 사이클)**:
  - **D1 (daily 운용)**: `run_ml_backtest.py` 경로를 buffer 엔진(`run_buffered_backtest`)으로 전환. 파라미터는 top_n=10, buffer_multiplier=3.0으로 고정(항목 35 그리드 + 항목 45 새 타깃 재확인, 3구간 전부 순수익 흑자). 추가 그리드 탐색 없음.
  - **I1 (분봉 feature 고정)**: 분봉에서만 계산 가능한 4개 — `vshare_auction`(+), `vshare_open30`(−), `vshare_late`(+), `rv_intraday`(−). 괄호는 부호(진단에서 고정). `range_pct` 등 일봉으로 계산 가능한 것은 제외(`high_low_range`로 이미 19개에 포함). **선택 편향 명시**: 이 후보는 semi_holdout을 포함한 전 기간 진단을 보고 고른 것.
  - **I2 (분봉 점수, 학습 없음)**: 날짜별 z-score에 부호를 곱해 4개 동일가중 평균.
  - **I3 (오버레이 가중치)**: w ∈ {0, 0.25, 0.5}, 이 외 값 없음.
  - **I4 (dev 판정)**: 주지표는 5일 raw 타깃 rank IC(기존 관례), 보조로 베타중립 IC 보고(판정엔 미사용). w>0 중 B1·B2·B3 **세 블록 모두**에서 IC가 w=0보다 높은 값이 있으면 그중 dev 전체 IC가 가장 높은 w를 채택 후보로, 없으면 분봉 오버레이 중단(daily 단독 유지).
  - **I5 (semi_holdout)**: I4 통과 시에만 1회. 채택 w의 IC 차이 부호가 음수로 뒤집히는지만 확인.
  - **I6/D2 (forward)**: 판단일 60개 이상 쌓이면 1회. daily 단독(buffer) vs daily+분봉 오버레이(buffer) 비교.
  - **해석 한계(사전 명시)**: 60거래일 ≈ 5일 비중복 12구간 → IC 평균 표준오차 ≈ 0.2/√12 ≈ 0.06. 기대 개선폭(0.01~0.02)을 확정할 검정력이 없음. forward 결과는 "개선 증명"이 아니라 "기각되지 않음" 수준으로만 해석하고, 결론은 "2025-09 이후 데이터 기준"으로 한정.
- **운영**: `scripts/nightly_ingest.sh` 추가 — 매 거래일 20:00 KST 이후 분봉(최근 10일, `--lookback-days`)을, 일봉은 금요일에만(수정주가라 매번 전체 이력을 다시 받아 50종목에 수 분 이상 걸리고, 분봉과 달리 언제든 재수집 가능 — `STOCKLENS_NIGHTLY_DAILY=1`로 강제) top50으로 수집, `STOCKLENS_RAW_BACKUP_DIR`가 있으면 분봉 raw를 백업. **분봉 raw는 재생성 불가**(API가 1년치만 제공, `data/raw/`는 gitignore) — `.gitignore` 주석도 "regenerable"에서 수정.
- **부수 수정**: 커밋 `b1614a4`(타깃 기본값 next_open) 이후 `tests/test_dataset.py`의 타깃 테스트 2개가 옛 close-to-close 공식을 기대해 실패하고 있었음 → `entry="close"`를 명시하고 next_open 기본값 테스트 1개 추가. 신규 `tests/test_intraday_split.py` 6개 포함 전체 200개 통과.
- **다음 단계**: (1) crontab 등록 후 매일 수집 확인. (2) D1 구현. (3) I1~I4 dev 전용 실험 스크립트 — 분봉 feature 패널 + 고정 daily 모델 점수를 dev 구간에서만 결합.

47. **D1: `run_ml_backtest.py`를 buffer 엔진(top_n=10, buffer 3.0)으로 전환 — 운용 경로가 실험 경로(항목 45 W3)를 정확히 재현, 최종 평가 대상을 소진된 test에서 forward holdout으로 교체**

- **변경** (`scripts/run_ml_backtest.py`): (1) 엔진을 `run_buffered_backtest_with_turnover`로, top_n=10·buffer_multiplier=3.0 고정(항목 46 사전등록 — `STOCKLENS_TOP_N` 환경변수 오버라이드 제거). (2) daily test(2023-07-01~2026-09-16, 항목 41에서 소진)를 더 이상 읽지 않음 — `confirm_final_test_use`/`splits.test` 제거. 최종 평가는 forward holdout(2026-09-24~)만, `src.data.intraday_split.select_segment(..., "forward")`로 읽음(`STOCKLENS_CONFIRM_INTRADAY_FORWARD=1` + 판단일 60개 이상 필요, 조건 미충족 시 메시지 출력 후 정상 종료). (3) 플래그 없이 실행하면 고정 daily 모델 학습 → validation(2020-01~2023-06) 백테스트 3종(ml_buffered / ml_plain / momentum, 동일 비용)까지 수행하고 forward 잠금에서 멈춤. Phase G 버전(top_n=2, test 기준)은 git 이력에 남아 있음.
- **교차검증 (validation, top50)**: 이 스크립트의 모델은 walk-forward W3 모델과 학습·조기종료 구간이 같으므로 항목 45(A_all19, W3)와 일치해야 함 → 정확히 일치.

  | 전략 | net_cum | 평균/5일 | hit | MDD | 진입/구간 |
  |---|---|---|---|---|---|
  | ml_buffered | **+65.0%** | +0.387% | 52.6% | -43.7% | 3.26 |
  | ml_plain | -2.2% | +0.067% | 50.3% | -43.4% | 10.00 |
  | momentum | -28.3% | -0.126% | 48.5% | -49.5% | 10.00 |

  best_iteration 9, ML daily rank IC +0.0218(IC>0 52.1%). buffer로 회전율이 10 → 3.26종목/구간(약 67% 감소)으로 줄며 같은 신호의 순수익이 -2.2% → +65.0%로 바뀜 — 비용이 순손실의 주원인이라는 항목 35의 결론과 일치.
- **주의**: 이 validation 수치는 조기종료에 쓴 구간과 같은 구간에서 잰 것이라 낙관적 편향이 있음(모든 walk-forward 실험과 동일한 관례). buffer 3.0 자체도 이 validation 구간들에서 고른 값. MDD -43.7%는 여전히 큼 — 실전 투입 판단은 forward 결과와 별도의 리스크 관리 설계가 필요.
- **테스트**: `tests/test_run_ml_backtest_config.py` 3개(사전등록 파라미터 고정, forward 잠금, test split 미사용) 추가, 전체 203개 통과. AGENTS.md 13절의 test lock 적용 스크립트 목록을 실제와 맞게 수정하고 forward holdout 규칙 추가.
- **다음 단계**: I1~I4 — dev 구간(2025-09~2026-06)에서 분봉 오버레이 실험. 비교 기준은 이 스크립트의 ml_buffered 경로.

48. **I1~I4: 분봉 오버레이 dev 실험 — 사전등록 기준(IC, 3블록 전부)은 w=0.5가 통과. 그러나 롱온리 top-10 수익은 오히려 감소(분봉 점수가 저베타 쪽으로 기울어 상승장에서 불리)**

- **방법** (`scripts/experiment_intraday_overlay_dev.py`, top50, dev 2025-09-01~2026-06-30만, 라벨 purge 적용): 항목 46의 I1~I4 그대로. 분봉 4개 feature(`vshare_auction` +, `vshare_open30` −, `vshare_late` +, `rv_intraday` −)를 날짜별 z-score·부호 곱·평균 후 다시 z-score(학습 없음). `score = z(daily ML) + w·z(intraday)`, w ∈ {0, 0.25, 0.5}. daily 모델은 `run_ml_backtest.py`의 고정 모델(best_iteration 9). 분봉 점수 결측(약 3%)은 0으로 처리해 모든 w가 같은 행으로 평가됨. 패널은 `reports/intraday_ic/features_panel.csv`(2025-09-01~2026-09-23) 재사용 — raw에서 다시 만들어도 dev 구간은 동일해야 함.
- **결과** (IC = 5일 raw 타깃 날짜별 rank IC. gross/net/MDD는 top-10·buffer 3.0 백테스트, 참고용):

  | 구간 | w | IC | IC_bn | gross | net | MDD | 유니버스 동일가중 |
  |---|---|---|---|---|---|---|---|
  | dev | 0 | −0.0041 | +0.0120 | +62.6% | +54.7% | −16.2% | +57.6% |
  | dev | 0.5 | +0.0135 | +0.0454 | +42.4% | +36.1% | −12.4% | +57.6% |
  | B1 | 0 → 0.5 | +0.0181 → +0.0230 | +0.041 → +0.046 | +23.6% → +14.3% | +20.5% → +11.9% | | +19.6% |
  | B2 | 0 → 0.5 | +0.0039 → +0.0287 | +0.015 → +0.058 | +36.4% → +38.8% | +34.3% → +36.5% | | +21.4% |
  | B3 | 0 → 0.5 | −0.0352 → −0.0020 | −0.017 → +0.052 | +1.8% → +8.8% | +0.6% → +7.2% | | +7.1% |

- **사전등록 판정(I4)**: w=0.25는 B1에서 −0.0006으로 탈락, **w=0.5는 B1 +0.0049 / B2 +0.0247 / B3 +0.0333으로 3블록 전부 통과 → 후보 w=0.5.** 규칙대로 I5(semi_holdout 부호 확인 1회)로 진행.
- **판정과 별개로 드러난 것(중요)**:
  1. **daily 모델 단독의 dev IC가 −0.0041** — 2025-09 이후 daily 신호가 사실상 0(항목 32·37의 감쇠 추세가 이어짐). 롱온리 net +54.7%는 대부분 시장 상승이며, 비용 없는 유니버스 동일가중(+57.6%)보다도 낮음.
  2. **분봉 점수는 강한 저베타 기울기**: 날짜별 rank corr(z_intraday, 60일 beta) 평균 −0.41(daily 점수와는 +0.23). 그래서 베타중립 IC는 크게 오르지만(+0.012 → +0.045), 강한 상승장이었던 dev 구간의 롱온리 top-10에서는 저베타 종목을 사게 돼 gross 수익이 줄어듦(회전율은 2.95 → 2.71로 오히려 감소 — 비용 문제 아님). 하락·횡보 블록(B3)에서는 반대로 도움이 됨.
  3. **선택 편향**: 4개 feature와 부호는 dev와 semi_holdout을 모두 포함한 기간의 진단(Notion, 2026-09-24)에서 고른 것 → dev 통과는 약한 증거이고, I5(semi_holdout)도 같은 이유로 오염. 깨끗한 판단은 forward에서만 가능.
- **결정**: 규칙은 결과를 본 뒤 바꾸지 않음 — w=0.5를 후보로 I5 진행. 다만 위 2번 때문에 **forward 평가(I6/D2) 보고 항목에 유니버스 동일가중 수익과 베타중립 IC를 추가**(판정 규칙은 그대로, 보고만 추가 — 결과를 본 뒤의 변경이므로 여기 명시). 롱온리 운용에서 오버레이가 "IC는 좋아지는데 수익은 줄어드는" 형태라면, 시장 중립(롱숏) 또는 베타 제약이 필요한지는 forward 이후 별도 사이클에서 다룸.
- **테스트**: `tests/test_intraday_overlay.py` 4개(사전등록 feature·부호·w 고정, z-score, 판정 규칙) 추가, 전체 207개 통과. 결과 CSV: `reports/intraday_overlay/dev_results.csv`.
- **다음 단계**: I5 — semi_holdout(2026-07-01~09-23)에서 w=0.5 vs w=0의 IC 차이 부호만 1회 확인(`STOCKLENS_CONFIRM_INTRADAY_SEMI_HOLDOUT=1`).

49. **I5: semi_holdout 부호 확인(1회) — w=0.5의 IC 개선 부호 유지(+0.0129), 오버레이 후보는 forward(I6)로. 단 이 구간의 큰 IC는 강한 단기 반전 국면 때문**

- **방법**: `scripts/experiment_intraday_overlay_dev.py --semi-holdout`(`STOCKLENS_CONFIRM_INTRADAY_SEMI_HOLDOUT=1`), 후보 w=0.5는 항목 48 결과로 고정(`CANDIDATE_W`). semi_holdout(2026-07-01~09-23, purge 적용)에서 w=0 vs w=0.5만 비교. 사전등록 규칙: IC 차이 > 0이면 유지, 아니면 오버레이 폐기. 크기는 판단하지 않음.
- **결과** (판단일 49개, 2026-07-01~09-09):

  | w | IC | IC>0 | IC_bn | gross | net | MDD | 유니버스 동일가중 |
  |---|---|---|---|---|---|---|---|
  | 0 | +0.1620 | 77.6% | +0.1138 | +7.7% | +6.6% | −21.2% | −0.5% |
  | 0.5 | +0.1749 | 77.6% | +0.1302 | +18.2% | +16.4% | −7.5% | −0.5% |

  **IC 차이 +0.0129 → 부호 유지(NOT FLIPPED). w=0.5를 forward(I6) 비교 후보로 유지.**
- **IC +0.16은 이상치로 보여 누수 여부를 확인함(이미 열린 dev+semi 구간만 사용)**: 월별 IC를 보면 단순 반전 점수(−return_5d)도 2026-08 +0.127, 2026-09 +0.279로 같이 급등 → 모델 버그가 아니라 **이 시기 시장 전체가 강한 단기 반전 국면**이었고, daily 모델은 사실상 반전 모델이라 그대로 따라간 것. 분봉 점수의 월별 IC는 2026-06 +0.28, 2026-07 +0.30으로 높고 2026-08~09는 ≈0 — semi_holdout의 오버레이 이득은 주로 7월에서 옴. dev 월별로는 daily −0.07~+0.06, 분봉 −0.11~+0.28로 변동이 매우 큼 → 어느 쪽이든 구간 몇 개의 평균으로 결론 내기 어려움(항목 46의 검정력 한계 그대로).
- **정보(판정 미사용)**: 유니버스가 −0.5%로 횡보·하락한 이 구간에서는 오버레이가 순수익(+6.6% → +16.4%)과 MDD(−21.2% → −7.5%) 모두 개선 — 항목 48의 "저베타 기울기라 상승장에선 불리, 하락·횡보에선 유리" 해석과 일치.
- **발견한 구현 문제(보수적, 누수 아님)**: `select_segment`의 purge는 `df`에 있는 날짜를 거래일 달력으로 씀. 그런데 `build_combined_dataset`은 타깃이 없는 마지막 5거래일 행을 만들지 않으므로, 데이터 끝 근처의 판단일은 라벨 구간이 달력 밖으로 나간 것처럼 보여 제거됨. 이번 I5는 이 때문에 09-10~09-16(유효한 5일)이 빠진 49일로 평가됨. **I5는 1회 원칙대로 다시 돌리지 않고 이 결과를 확정**(빠진 5일을 채우려고 재실행하면 항목 30·31의 "버그 수정 명목 재열람"과 같은 문제). 대신 아직 아무도 보지 않은 forward를 위해 `select_segment(..., calendar=...)` 옵션을 추가하고 `run_ml_backtest.py`의 forward 평가에 전체 봉 날짜 달력(`trading_calendar()`)을 넘기도록 수정. 기본 동작(calendar 없음)은 그대로라 항목 48·49 결과는 재실행해도 동일. 테스트 2개 추가.
- **테스트**: I5 판정 규칙 테스트 1개 + calendar 테스트 2개, 전체 210개 통과. 결과 CSV: `reports/intraday_overlay/semi_holdout_results.csv`.
- **다음 단계**: I6/D2 — forward holdout(판단일 60개 이상, 2027년 1월 초 전후)에서 daily 단독(buffer) vs daily + 분봉 오버레이 w=0.5(buffer)를 한 번에 비교하는 평가 스크립트를 **지금 미리 만들어 고정**(평가 전 사전등록). 항목 48에서 추가한 보고 항목(유니버스 동일가중, 베타중립 IC) 포함.

50. **I6/D2 forward 평가 스크립트 사전 고정 (`scripts/evaluate_forward_holdout.py`) — forward 데이터를 보기 전(2026-09-28)에 평가 방식·판정 규칙을 코드로 확정**

- **목적**: forward holdout(2026-09-24~)은 이번 사이클의 유일한 깨끗한 검증이고 딱 한 번만 봄. 결과를 본 뒤 평가 방식을 바꾸는 일이 없도록 판단일 60개가 쌓이기 전에 스크립트를 미리 만들어 고정.
- **비교 대상** (모두 top_n=10, 동일 비용): `daily`(고정 daily ML, buffer 3.0 — D2), `overlay`(z(daily) + 0.5·z(분봉), buffer 3.0 — I6), `momentum`(참고), `univ_ew`(유니버스 동일가중, 비용 없음 — 항목 48에서 추가한 롱온리 기준선).
- **사전등록 판정** (주지표: 5일 raw 타깃 날짜별 rank IC):
  - **D2**: IC(daily) > 0 → daily 트랙 기각되지 않음. 아니면 기각(표본 밖에서 daily 신호 없음).
  - **I6**: IC(overlay) − IC(daily) > 0 → 오버레이 기각되지 않음, w=0.5를 운용 경로에 반영. 아니면 오버레이 폐기.
  - 베타중립 IC, 순/총수익, MDD, 적중률, 회전율, univ_ew 대비 초과수익, 월별 IC는 해석용 보고만.
  - **해석 한계**: 판단일 60개 ≈ 5일 비중복 12구간, IC 평균 표준오차 ≈ 0.06 → "기각되지 않음"이 낼 수 있는 가장 강한 결론. 결론은 2025-09 이후 데이터 기준으로 한정.
- **안전장치**: `select_segment(..., "forward", calendar=trading_calendar())` — `STOCKLENS_CONFIRM_INTRADAY_FORWARD=1` + 판단일 60개 이상이어야 열림(항목 46·49). 분봉 패널은 raw에서 다시 만듦(저장된 `features_panel.csv`는 2026-09-23까지). 분봉 커버리지가 80% 미만이면 경고.
- **검증(dry run)**: 같은 `evaluate()`를 이미 열린 semi_holdout에 돌려 항목 49와 동일한 수치(daily IC +0.1620, overlay +0.1749, 순수익 +6.6% / +16.4%) 재현 확인. forward 경로는 플래그 없이 실행 시 잠금, 플래그가 있어도 판단일 0개(<60)라 `IntradaySplitError`로 멈추는 것 확인 — forward 데이터는 한 행도 보지 않음. 테스트 4개 추가(고정값, 판정 규칙), 전체 214개 통과.
- **실행 시점과 절차(2027년 1월 초 전후, 1회)**: ① `STOCKLENS_NIGHTLY_DAILY=1 bash scripts/nightly_ingest.sh`로 일봉 갱신 ② 분봉 수집 로그에 실패가 없는지 확인 ③ `STOCKLENS_UNIVERSE=top50 STOCKLENS_CONFIRM_INTRADAY_FORWARD=1 PYTHONPATH=. python scripts/evaluate_forward_holdout.py`. 판단일이 60개 미만이면 아무것도 보여주지 않고 종료하므로, 날짜를 확인하려고 미리 돌려도 forward 결과는 노출되지 않음.
- **그 전까지**: 이번 사이클에서 새로 판단할 것은 없음. 매일 수집이 잘 돌고 있는지만 주 1회 확인.

51. **Explanation 레이어를 CLI에 연결 — `scripts/recommend.py`(판단일 top-N + TreeSHAP 근거) + 주간 페이퍼 트레이딩 기록. 부산물로 "고정 모델의 점수 종류가 하루 8개 안팎이라 상위권 상당수가 동점"이라는 구조적 문제 발견**

- **무엇을 만들었나**: `scripts/recommend.py` — 모든 종목의 최신 일봉까지 feature를 다시 계산(학습 데이터셋은 타깃이 없는 마지막 5일을 버리므로 별도 경로), 가장 최근 공통 거래일 T를 고정 daily 모델(`run_ml_backtest.py`와 동일, best_iteration 9)로 점수화, 상위 N(기본 10)을 종목명·순위·점수와 함께 출력. 종목마다 점수를 가장 크게 움직인 feature 3개를 **실제 값 + TreeSHAP 기여**로 보여줌(`src/explanation/model_attribution.py`, XGBoost `pred_contribs`로 계산한 정확한 분해 — 합이 점수와 1e-4 이상 어긋나면 출력하지 않고 중단). AGENTS.md 24의 "순위를 만든 바로 그 숫자로 설명" 원칙. 모델이 rank 타깃이라 "예상 수익률 %"라는 표현은 쓰지 않음. 결과는 `reports/daily_picks/<T>.csv`(전 종목 순위 포함)에 저장 — forward 평가와 별개인 페이퍼 트레이딩 기록이며 이걸 보고 모델·전략을 바꾸지 않음.
- **의도적으로 뺀 것**: (1) 분봉 오버레이 — forward(I6) 전까지 후보일 뿐. (2) 기존 프로필 재랭킹(`src/recommendation/scoring.py`) — 원래 raw 수익률 예측 모델용 가중치라, rank 척도 점수(±0.01 수준)에 volatility 등을 그대로 더하면 척도가 맞지 않음. 재보정 전까지 출력하지 않음(후속 과제). 기존 `demo_explanation.py`/프로필 설명 모듈은 그대로 둠.
- **자동화**: `nightly_ingest.sh`에 4단계 추가 — 일봉을 갱신한 날(기본 금요일)에만 `recommend.py` 실행. 매주 금요일 종가 기준 추천이 쌓이고, 5거래일 보유 주기와 대략 맞음. 일봉이 오래됐으면(휴장일 제외) 경고 출력.
- **발견(중요) — 동점 문제**: 고정 모델은 깊이 2 트리 9개라 50종목에 대해 하루 평균 **7.8개의 서로 다른 점수**만 냄(validation 2020~2023H1 기준). 10위 점수 이상인 종목이 평균 **18.5개** → top-10의 상당 부분이 모델이 아니라 동점 처리 규칙으로 정해짐. 백테스트 엔진(`baseline.py`, `buffered.py`)은 `sorted(scores, key=score, reverse=True)`의 안정 정렬이라 **동점이면 종목코드가 작은 쪽이 먼저** 선택됨 — 항목 33~50의 모든 백테스트가 이 규칙을 암묵적으로 써 옴. `recommend.py`도 같은 규칙으로 맞추고, 동점으로 순위가 정해진 종목에는 그 사실을 출력.
- **동점 규칙 민감도 확인(validation W3, 이미 사용한 구간)**: 종목 순서만 무작위로 바꾼 20가지 동점 처리로 top-10·buffer 3.0을 다시 돌리면 순누적 **+34% ~ +142%(중앙값 +61%, 표준편차 29%p)**, MDD −40% ~ −49%. 코드 오름차순 규칙의 +65.0%는 분포 한가운데라 **유리하게 편향된 규칙은 아니지만**, 백테스트 수익률 한 숫자에 ±30%p 수준의 "임의 선택" 잡음이 섞여 있다는 뜻. IC는 동점과 무관(순위상관은 동점을 평균 순위로 처리)하므로 사전등록 판정(IC 기준)은 영향 없음.
- **판단**: 사전등록된 forward 평가의 판정 규칙·전략은 바꾸지 않음(동점 규칙도 코드 그대로 = 사전등록의 일부). 다만 forward 보고서에 **동점 처리 무작위화 분포를 해석용으로 추가**하는 것을 권장(판정 미사용, forward 데이터를 보기 전에 추가해야 의미 있음). 모델 해상도 문제(얕은 트리·적은 라운드)는 신호가 얕아 생긴 결과(항목 37)이며, 개선은 forward 이후 새 사이클의 과제.
- **테스트**: `tests/test_model_attribution.py` 4개(TreeSHAP 합 = 점수, 설명 문구, 값 표기, 엔진과 같은 동점 규칙) 추가, 전체 218개 통과.

52. **forward 보고서에 동점 처리 민감도 추가(해석용, 판정 미사용) — forward 데이터를 보기 전(2026-09-28)에 고정**

- **무엇을 바꿨나**: `scripts/evaluate_forward_holdout.py`에 `tie_orders()` / `tie_stats()` / `tie_sensitivity()` / `summarize_ties()` 추가. forward 평가 시 daily·overlay(buffer 3.0, top-10) 전략을 종목 순서만 무작위로 바꾼 **20가지 동점 처리**(`TIE_PERMUTATIONS=20`, `TIE_SEED=20260928`, 둘 다 사전 고정)로 다시 돌려 순누적수익 분포(min/median/max/std), 코드 오름차순 규칙(보고되는 전략)이 분포에서 차지하는 백분위, 최악 MDD, 하루 평균 서로 다른 점수 수·10위 점수 이상 종목 수를 출력. 결과는 `reports/forward_holdout/forward_tie_sensitivity.csv`(요약), `forward_tie_permutations.csv`(순열별)에 저장.
- **바꾸지 않은 것**: 판정 규칙(D2·I6), 보고되는 전략과 그 동점 규칙(코드 오름차순), `evaluate()`의 기존 출력. IC는 동점과 무관(평균 순위)하므로 판정은 이 추가로 달라질 수 없음. momentum은 점수가 연속값이라 제외.
- **구현 방식**: 엔진은 `data_by_stock` dict 순서대로 점수를 모아 안정 정렬하므로, dict 순서만 섞으면 동점 순서만 바뀜. 엔진 코드는 건드리지 않음.
- **검증(dry run, 이미 사용한 validation W3, daily 점수만)**: 코드 오름차순 순누적 +65.0%(항목 45·51과 일치), 서로 다른 점수 7.80개/일, 10위 점수 이상 18.5개/일(항목 51과 일치). 20개 순열 분포 +24% ~ +92%(중앙값 +55%, 표준편차 18%p), 오름차순 규칙은 75백분위, 최악 MDD −47%. 점수에 아주 작은 잡음을 넣어 동점을 없애면 순열 간 결과가 완전히 같음(순서가 동점을 통해서만 작용함을 확인). 항목 51의 20개 순열과 시드가 달라 범위는 다르지만 결론(수익률 한 숫자에 수십 %p의 임의 선택 잡음) 동일.
- **forward 경로는 여전히 잠김**: 새 코드는 `select_segment(..., "forward")` 이후에만 호출됨. forward 데이터는 한 행도 보지 않음.
- **테스트**: `tests/test_evaluate_forward_holdout.py`에 5개 추가(고정값, 순열 결정성, 동점 집계, 동점 없으면 순서 무관, 백분위 계산), 전체 223개 통과.

53. **forward 결과별 후속 행동 사전 고정 + 분봉 수집 누락 점검 스크립트 + 고정 모델 확인 가드 — forward 데이터를 보기 전(2026-09-28)에 확정**

- **왜 지금**: forward 평가는 1회뿐이고, 결과를 본 뒤에 "그럼 다음엔 뭘 하지"를 정하면 그 결정이 결과에 맞춰짐. dev에서 daily 단독 IC가 −0.0041(항목 48)이라 D2 기각이 충분히 가능한 상황 — 기각됐을 때 할 일을 지금 정해 둬야 함.
- **forward 결과별 후속 행동** (D2 = IC(daily) > 0, I6 = IC(overlay) − IC(daily) > 0, 판정 규칙 자체는 항목 50 그대로):

  | 경우 | D2 | I6 | 운용 경로 | 다음 사이클 1순위 |
  |---|---|---|---|---|
  | A | 통과 | 통과 | daily + 분봉 오버레이(w=0.5), top-10, buffer 3.0. `recommend.py` 기록도 오버레이로 전환 | 리스크 관리(MDD −44% 수준) + 오버레이의 저베타 기울기 대응(롱숏/베타 제약 검토, 항목 48) |
  | B | 통과 | 기각 | daily 단독 유지, 오버레이 폐기 | 모델 해상도(동점, 항목 51) 개선 + 리스크 관리. 분봉은 계속 수집, 2년치 쌓이면(2027-09 이후) 분봉 포함 재학습을 새로 사전등록 |
  | C | 기각 | 통과 | **운용 반영 없음**(아래 수정 사항) | 분봉 점수 단독 신호를 새 holdout에서 검증하는 사이클 사전등록 + daily 모델 재학습(최근 데이터 포함) 여부 판단 |
  | D | 기각 | 기각 | 운용 반영 없음 | 현재 방식(일봉 기술 feature + 분봉 오버레이) 중단. 뉴스·매크로·수급(Phase I~J) 또는 문제 재정의(horizon·타깃) 중 택1을 새로 사전등록 |

- **항목 50에 대한 수정(forward를 보기 전에 추가, 여기 명시)**: (1) I6 "기각되지 않음 → w=0.5 운용 반영"은 **D2도 통과했을 때만** 적용. 오버레이 점수의 절반은 daily 점수라서, daily 신호가 기각된 상태에서 둘을 섞는 건 근거가 없음(경우 C). I6 판정 자체는 그대로 기록. (2) forward 분봉 커버리지가 80% 미만이면 I6는 **판정 보류**(운용 반영 없음, 다음 사이클에서 재검증) — 커버리지가 낮으면 오버레이 점수가 거의 daily 점수라 차이가 0으로 쏠려 어느 쪽 결론도 믿을 수 없음.
- **모든 경우 공통**:
  - 실자금 투입은 forward 결과만으로 결정하지 않음(판단일 60개 ≈ 비중복 12구간, IC 표준오차 ≈ 0.06). 페이퍼 트레이딩 기록(`recommend.py`)은 계속.
  - forward 구간(2026-09-24 ~ 평가일)은 평가 후 다음 사이클의 dev가 됨. 다음 사이클의 holdout은 **평가일 이후 새로 쌓이는 판단일**(forward2, 최소 60개)이며, 같은 방식으로 잠금.
  - 동점 민감도(항목 52)에서 코드 오름차순 규칙이 분포의 10% 미만 또는 90% 초과 백분위에 있으면, 그 전략의 수익률 수치는 "동점 규칙이 만든 숫자"로 적고 해석에 쓰지 않음(판정과 무관).
  - D2/I6 문턱값은 결과를 본 뒤 바꾸지 않고, 데이터를 더 모아 forward를 다시 보지 않음(항목 50 그대로).
- **확정(2026-09-29, 재훈)**: 위 두 수정을 그대로 확정하고 코드로 강제 — `verdicts()`가 `i6_status`(not_rejected / rejected / withheld)와 `overlay_deploy`(D2·I6 둘 다 통과 + 커버리지 80% 이상일 때만 True)를 반환, forward 보고서가 `DEPLOY:` 줄로 운용 반영 대상을 직접 출력. D2/I6 판정값 자체(`d2_not_rejected`, `i6_not_rejected`)는 항목 50 그대로 기록. 테스트 3개 추가.
- **항목 65로 보강(2026-10-04, forward 보기 전, 재훈 승인)**: 위 표의 "운용 경로" 열은 forward 단독으로 적용하지 않음. D2·I6 판정은 그대로 기록하고, "기각되지 않음"은 forward2(평가일 이후 60개 이상 판단일)의 후보가 될 뿐이며 forward2에서도 같은 방향일 때만 운용에 반영. 기각 쪽 행동(오버레이 폐기, 경우 C·D)은 그대로. 코드: `verdicts()`의 `overlay_deploy` → `overlay_forward2_candidate`.
- **분봉 수집 누락 점검** (`scripts/check_forward_minute_coverage.py`): forward 구간의 (거래일, 종목)마다 forward 평가와 같은 27봉 규칙(`day_features`)으로 ok / incomplete / missing만 판정. 가격·수익률·feature 값·점수는 출력하지 않으므로 forward를 "본" 것이 아님. 전체 커버리지(80% 기준), 100% 미만 종목, 누락 있는 날, 아무 종목도 데이터가 없는 평일(휴장일이면 정상), 수집 지연 경고, 누락을 다시 받는 `--lookback-days N` 명령을 출력. 야간 수집은 최근 10일만 다시 받으므로 **주 1회 실행** 권장. 결과: `reports/forward_coverage/forward_minute_status.csv`.
- **고정 모델 확인 가드** (`evaluate_forward_holdout.py`): 고정 daily 모델의 `best_iteration`이 9가 아니면(라이브러리 버전·데이터 변경 등) forward 구간을 읽기 **전에** 멈춤 — 사전등록한 모델이 아닌 것으로 1회뿐인 평가를 소진하지 않도록. 실행 전 절차에 커버리지 점검과 이 항목 확인을 추가.
- **부수 기록(항목 52)**: 재훈 환경에서 순서 100가지로 돌린 validation 결과 — 순누적 +23.0% ~ +115.9%(중앙값 +59.5%, 표준편차 17.9%p), 코드 오름차순 +65.0%는 62백분위, 최악 MDD −50.7%. 20가지 결과와 결론 동일.
- **테스트**: `tests/test_check_forward_minute_coverage.py` 3개(27봉 규칙, 상태 분류·빈 평일, 재수집 일수), `tests/test_evaluate_forward_holdout.py` 1개(고정 모델 가드) 추가, 전체 227개 통과.

54. **forward holdout 이중 접근 경로 제거 — forward를 여는 스크립트를 `evaluate_forward_holdout.py` 하나로 고정 (forward 데이터를 보기 전, 2026-09-29)**

- **문제**: 항목 47에서 `run_ml_backtest.py`에 forward 평가 경로를 넣었고, 항목 50에서 `evaluate_forward_holdout.py`를 따로 만들었음. 두 스크립트 모두 같은 환경변수(`STOCKLENS_CONFIRM_INTRADAY_FORWARD=1`)로 forward를 열 수 있었고, `run_ml_backtest.py` docstring은 여전히 "이 스크립트로 forward 평가"라고 안내했음. 둘 다 실행하면 1회뿐인 forward 확인이 2회가 됨 — 항목 30·31의 "다른 이유로 재실행하다 test를 다시 본" 문제와 같은 구조.
- **조치**: `run_ml_backtest.py`에서 forward 구간(`select_segment(..., "forward")`, forward 결과 저장)을 삭제. 이제 validation 백테스트 + 항목 45 교차검증만 수행(플래그 불필요). `train_frozen_model`·`trading_calendar`·비용 설정은 그대로 두어 `evaluate_forward_holdout.py`가 계속 import해 같은 모델·비용을 씀. forward 평가 절차(항목 50·53)는 변경 없음 — 원래도 `evaluate_forward_holdout.py`만 지정했고, D2(daily buffer 전략)는 그 스크립트에서 평가됨.
- **사전등록에 대한 영향**: 판정 규칙(D2/I6), 전략, 파라미터 변경 없음. 빠진 것은 `run_ml_backtest.py`의 forward 출력 중 `ml_plain`(buffer 없는 참고 전략) 행뿐이며, 판정에 쓰이지 않던 값.
- **구조적 강제**: `tests/test_run_ml_backtest_config.py::test_only_the_forward_evaluation_script_reads_the_forward_holdout` — `scripts/*.py` 중 `select_segment(..., "forward")`를 호출하는 파일이 정확히 `evaluate_forward_holdout.py` 하나인지 검사. AGENTS.md 42절도 같은 규칙으로 수정.
- **부수 발견(환경변수 의존 테스트)**: `tests/test_evaluate_forward_holdout.py::test_tie_order_changes_results_only_through_ties`가 `STOCKLENS_UNIVERSE` 없이 실행하면 실패하고 있었음. `run_ml_backtest.BUFFERED_CONFIG.allow_partial_universe`가 import 시점에 유니버스 크기로 정해져(core5 → False), 합성 12종목을 엔진이 거부. 이번 변경과 무관한 기존 문제. 평가 코드는 그대로 두고, 테스트에서 `allow_partial_universe=True` 사본으로 바꿔 끼우도록 수정. 관련 테스트 파일 2개 통과 확인(재훈 기기).

55. **포트폴리오 리스크 관리 레이어 사전등록 (소비자 레이어, forward 대기 중 병행 — 항목 53 경우 A·B 후속 준비) — 실험 실행 전 고정**

- **문서 정리 기록(항목 65)**: 이 항목은 파일에 세 번 들어가 있었음. 앞의 두 개는 서로 똑같은 최초 사전등록 원문(R2 하단 e = 0)이었고 아래 최종본으로 대체됨 — 하단 0 → 0.5 변경은 결과를 보기 전(2026-09-30)이며 근거는 아래 "R2 하단 비중 0.5 결정 근거". 원문은 git 이력(`6a7e90b`, `c2f7095`)에 있음.

- **목적**: 운용 경로(고정 daily ML, top-10, buffer 3.0)의 MDD가 validation W3 −43.7%(항목 47) 수준이라 실전 투입이 불가능함. 종목 선택(신호)은 그대로 두고, **전체 투자 비중(exposure)만 조절**해서 MDD를 줄이면서 위험 대비 수익을 유지할 수 있는지 확인.
- **forward와의 관계**: 이 작업은 forward holdout을 읽지 않고, 항목 50·53의 판정(D2·I6, IC 기준)과 forward 보고서를 바꾸지 않음. 채택된 규칙의 표본 밖 확인은 **forward2**(평가일 이후 새로 쌓이는 판단일, 항목 53)에서 함.
- **구조** (`src/portfolio/risk_overlay.py`, 신규): 판단일 T마다 T 종가까지의 정보로 exposure e_T ∈ [0, 1]을 정함 → 그 기간(T+1 시가 ~ T+5 종가) 포트폴리오 수익 = e_T × (기존 엔진의 기간 수익), 나머지는 현금(수익 0). 레버리지 없음. 기존 엔진(`buffered.py`)은 건드리지 않고 기간 수익 시계열에 사후 적용.
  - **비중 변경 비용**: |e_T − e_{T−1}| × 0.315%(매도 쪽 편도 비용 = 수수료 0.015% + 세금 0.20% + 슬리피지 0.10%, 매수 쪽보다 큰 값으로 보수적 적용).
  - **시장 대용 지수**: 유니버스(top50) 동일가중 일간 수익률의 누적(`universe_ew_index`). 새 데이터 없이 계산 가능. 생존편향(AGENTS.md 23절)이 있으므로 절대 수치가 아니라 후보 간 상대 비교만 신뢰.
- **후보 (이 4개 외 없음, 파라미터 그리드 탐색 없음)**:

  | 후보 | 규칙 | 고정 파라미터 |
  |---|---|---|
  | R0 | 리스크 관리 없음, e = 1 (기준) | — |
  | R1 변동성 타기팅 | e = min(1, σ* / σ̂_T). σ̂_T = 대용 지수 최근 20거래일 일간 수익률 표준편차 × √252 | σ* = 각 window의 **train 구간** σ̂ 중앙값(validation 미사용) |
  | R2 추세 필터 | 대용 지수 종가 > 200거래일 이동평균이면 e = 1, 아니면 e = 0.5 | 200일, 하단 e = 0.5 |
  | R3 결합 | e = e(R1) × e(R2) | 위와 동일 |

  - **제외한 것과 이유**: 종목별 손절(3.0×ATR)은 HOLD/SELL 레이어에서 이미 따로 검증됨(항목 17~26), 기간 내 청산은 엔진 수정이 필요해 이번 범위 밖. 종목당 비중 상한은 이미 동일가중 10%라 의미 없음. 전략 자체 낙폭 기반 규칙(DD 컷)은 경로 의존성이 커서 whipsaw 위험 → 이번엔 제외.
  - **R2 하단 비중 0.5 결정 근거(결과 보기 전, 2026-09-30 재훈)**: 이동평균 하나로 100% ↔ 0%를 오가는 구조는 실제 리스크 레이어로 너무 이진적이고 whipsaw 비용이 큼. 설계상의 이유로 정한 값이며, **e = 0 변형은 이번 사이클에서 검증하지 않음**(결과를 보고 0과 0.5 중 고르면 사후 선택이 되므로). 따라서 R3의 R2 부분도 0.5.
- **평가 구간**: walk-forward validation W1(2012~2015), W2(2016~2019), W3(2020~2023H1). 각 window의 고정 daily 모델은 항목 45(A_all19, rank 타깃, IC 조기종료, `entry="next_open"`)와 같은 설정. 분봉 dev(2025-09~2026-06)는 **보고만**(판정 미사용). test·semi_holdout·forward는 읽지 않음.
- **사전등록 판정**:
  - 후보 Rk는 **세 window 모두에서** (a) MDD가 R0보다 5%p 이상 개선(덜 음수) **그리고** (b) Calmar(연환산 순수익 ÷ |MDD|)가 R0 이상일 때 통과.
  - 통과 후보가 여럿이면 세 window 평균 Calmar가 가장 높은 것. 차이가 0.05 미만이면 단순한 쪽(R2 → R1 → R3 순)을 채택.
  - 통과 후보가 없으면 R0 유지하고 기록(리스크 관리 없음이 아니라 "이 3개 규칙은 효과 없음"으로 기록).
  - 보고(판정 미사용): 순누적수익, 연환산 수익·변동성, Sharpe, MDD, 적중률, 평균 exposure, 현금 비중 기간 비율, exposure 변경 비용 합계, 기간별 equity 곡선(`plot_run.py`).
- **해석 한계(사전 명시)**: validation은 모델 조기종료·buffer 3.0 선택에 이미 쓰인 구간이라 R0 자체가 낙관적. 다만 리스크 규칙은 모델 점수를 쓰지 않고 시장 대용 지수만 쓰므로 이 편향이 후보 간 비교에 주는 영향은 제한적. 후보 3개 비교라 다중비교 여지가 있음 → 채택 규칙도 forward2 확인 전까지는 "후보"로만 취급하고 `recommend.py`에는 exposure를 **참고 정보로만** 출력.
- **누수 방지**: e_T는 T일 종가까지만 사용(판단 시점 A, 항목 46). 테스트로 강제 — T 이후 가격을 바꿔도 e_T가 변하지 않아야 함.
- **구현 계획**: (1) `src/portfolio/risk_overlay.py` — `universe_ew_index`, `exposure_vol_target`, `exposure_trend`, `apply_exposure`(비용 포함 기간 수익), `risk_metrics`. (2) `scripts/experiment_risk_overlay_validation.py` — W1~W3 × R0~R3 표 + dev 보고, 결과 `reports/risk_overlay/validation_results.csv`. (3) 테스트: R0 = 기존 엔진 결과와 일치, e ∈ [0, 1], 미래 가격 변경에 e_T 불변, 비용 계산.
- **결과 (2026-09-30, 1회 실행, `reports/risk_overlay/validation_results.csv`)**: W3 R0 순누적 +65.0%로 항목 45·47 재현(MATCH). σ* = W1 21.0% / W2 17.8% / W3 16.1%.

  | window | 후보 | 순누적 | 연수익 | 연변동성 | MDD | Calmar | 평균 e | e<1 비율 | 비중 변경 비용 |
  |---|---|---|---|---|---|---|---|---|---|
  | W1 | R0 | +34.8% | 8.0% | 17.7% | −19.5% | 0.41 | 1.00 | 0% | 0.00% |
  | W1 | R1 | +32.5% | 7.5% | 17.6% | −19.9% | 0.38 | 1.00 | 4.1% | 0.27% |
  | W1 | R2 | +7.0% | 1.8% | 13.3% | −23.9% | 0.07 | 0.82 | 36.7% | 4.72% |
  | W1 | R3 | +6.1% | 1.5% | 13.2% | −24.1% | 0.06 | 0.81 | 36.7% | 4.86% |
  | W2 | R0 | +15.9% | 3.9% | 19.7% | −35.5% | 0.11 | 1.00 | 0% | 0.00% |
  | W2 | R1 | +14.7% | 3.6% | 19.2% | −34.2% | 0.11 | 0.98 | 13.4% | 0.69% |
  | W2 | R2 | +8.9% | 2.2% | 14.7% | −27.3% | 0.08 | 0.79 | 41.8% | 2.68% |
  | W2 | R3 | +8.0% | 2.0% | 14.3% | −26.6% | 0.08 | 0.78 | 44.8% | 3.07% |
  | W3 | R0 | +65.0% | 15.9% | 30.9% | −43.7% | 0.36 | 1.00 | 0% | 0.00% |
  | W3 | R1 | +38.0% | 10.0% | 21.3% | −27.5% | 0.36 | 0.84 | 59.6% | 2.92% |
  | W3 | R2 | +50.7% | 12.9% | 21.3% | −29.7% | 0.43 | 0.81 | 38.0% | 1.73% |
  | W3 | R3 | +37.2% | 9.8% | 16.9% | −21.1% | 0.46 | 0.69 | 70.2% | 3.70% |

  dev(2025-09~2026-06, 보고만): R0 +54.7% / MDD −16.2%, R1·R3 +45.0% / −6.8%. R2는 구간 내내 지수가 200일선 위라 한 번도 작동하지 않아 R0와 동일.
- **사전등록 판정: 통과 후보 없음 → R0 유지.** MDD 개선(R0 대비, W1/W2/W3): R1 −0.4 / +1.3 / +16.2%p, R2 −4.4 / +8.2 / +14.0%p, R3 −4.6 / +8.9 / +22.6%p. 세 후보 모두 W1에서 MDD가 오히려 악화되어 탈락, R1은 W2에서도 기준 미달.
- **관찰(판정과 별개, 해석용)**:
  1. **효과가 국면 의존적**: 세 규칙 모두 W3(코로나 급락이 포함된 고변동 구간)에서만 MDD를 크게 줄임(R3 −43.7% → −21.1%, Calmar 0.36 → 0.46). 완만한 하락·횡보 구간(W1 2012~2015 박스권)에서는 도움이 안 되거나 해로움.
  2. **R1은 구조상 위기 때만 작동**: σ*를 train 중앙값으로 두고 e ≤ 1로 막았기 때문에, 시장 변동성이 평소 수준인 W1·W2에서는 거의 항상 e = 1(e<1 비율 4%·13%). "실패"라기보다 설계상 평시에는 꺼져 있는 규칙.
  3. **R2는 횡보장에서 whipsaw 비용이 큼**: W1에서 200일선을 약 30번 교차(비용 4.72%, 1회 0.16%)했고, 줄인 비중 때문에 반등도 놓쳐 수익 +34.8% → +7.0%로 줄면서 MDD는 오히려 악화.
- **하지 않는 것**: 이 결과를 보고 파라미터(σ* 기준, 이동평균 길이, 하단 비중, MDD 기준 5%p)를 바꿔 다시 돌리지 않음. 위 관찰에서 나온 새 규칙(예: 고변동 국면 전용 규칙)은 validation을 이미 본 뒤 만든 것이므로, 한다면 새 항목으로 사전등록하고 forward2에서 확인해야 함(validation 통과는 증거로 쓰지 않음).
- **운용 영향 없음**: 운용 경로·`recommend.py`·forward 평가(항목 50·53)는 그대로. 코드(`src/portfolio/risk_overlay.py`, 실험 스크립트, 테스트 8개)는 재사용 가능하도록 유지.
- **다음 단계**: 대기 기간 과제 중 프로필 재랭킹 rank 척도 재보정(항목 51 후속)으로 이동. 리스크 관리는 forward 결과(항목 53 경우 A·B) 이후 사이클에서 위 관찰을 바탕으로 재설계 여부 판단.

56. **프로필 재랭킹을 rank 척도 점수에 맞게 재보정 — 사전등록 (소비자 레이어, 항목 16·51 후속) — 실험 실행 전 고정**

- **문제(진단, validation W3, 수익률은 보지 않고 점수 분포만 확인)**: 날짜별 횡단면 표준편차 중앙값이 `predicted_return` 0.0041(rank 타깃 모델), `volatility_20` 0.0087, `price_to_sma_5` 0.021, `volume_ratio_20` 0.46. 기존 가중치(항목 16, raw 수익률 모델 기준)를 그대로 쓰면 개인화 항이 모델 점수를 압도함:

  | 프로필 | top-10이 neutral(모델)과 겹치는 비율 | 개인화 점수와 모델 점수의 rank 상관 |
  |---|---|---|
  | conservative | 25% (무작위 수준 20%와 비슷) | +0.25 |
  | aggressive | 19% | **−0.25** |

  즉 지금 conservative는 "저변동성 정렬", aggressive는 "거래량·모멘텀 정렬"이며 모델 신호가 거의 사라짐. aggressive가 음의 상관인 이유: 모델이 사실상 단기 반전 모델(항목 49)이라 단기 모멘텀 가중과 정면으로 충돌.
- **원칙(AGENTS.md 9)**: 개인화는 모델 신호를 **기울이는(tilt)** 것이지 대체하는 것이 아님.
- **새 점수** (`src/recommendation/scoring.py`, 단위 없는 결합):
  - 모든 항을 날짜별 **표준화 순위**로 변환: z(x) = (그날 순위 백분위 − 평균) ÷ 표준편차(동점은 평균 순위). 이상치(거래량 등)에 강하고 척도가 같아짐.
  - personalized = z(predicted_return) + λ_p · Σ_j w_{p,j} · z(f_j)
  - 방향 w (AGENTS.md 9 예시 그대로, 크기 1로 정규화):

    | 프로필 | volatility_20 | price_to_sma_5 | volume_ratio_20 |
    |---|---|---|---|
    | conservative | −1 | 0 | 0 |
    | neutral | 0 | 0 | 0 (λ = 0, 모델 점수 그대로) |
    | aggressive | +1/√3 | +1/√3 | +1/√3 |

  - **강도 λ_p는 수익률이 아니라 "모델 보존 정도"로 결정**: train 구간(각 window)에서 개인화 점수와 모델 점수의 날짜별 rank 상관 평균이 **ρ* = 0.8**이 되는 λ를 이분 탐색으로 구함. 수익률·IC를 전혀 쓰지 않으므로 결과에 맞춘 튜닝이 아님. validation은 λ 결정에 쓰지 않음.
- **평가 구간**: W1·W2·W3 validation, 운용 경로와 같은 엔진(top-10, buffer 3.0, 실제 비용). 모델은 항목 45·55와 동일. 분봉 dev는 보고만. test·semi_holdout·forward는 읽지 않음.
- **사전등록 판정** (목적은 수익 개선이 아니라 "프로필이 의도한 방향으로 다르게 행동하면서 모델 신호를 유지하는가"):
  1. **방향**: 세 window 모두에서 보유 종목 평균 `volatility_20`이 conservative < neutral < aggressive, **그리고** 포트폴리오 기간 수익률 표준편차가 conservative < neutral.
  2. **신호 보존**: 세 window 모두에서 validation의 모델 점수와의 rank 상관 평균 ≥ 0.7(train 목표 0.8에서 크게 벗어나지 않음), **그리고** 개인화 점수의 IC가 0 이상(모델 신호를 뒤집지 않음).
  - 두 조건을 모두 만족한 프로필만 `recommend.py`에서 선택 가능하게 연결(기본값은 neutral). 실패한 프로필은 비활성화하고 기록.
  - 보고(판정 미사용): 순누적수익, Sharpe, MDD, 적중률, 회전율, top-10 겹침 비율, 보유 종목 평균 feature 값, λ_p.
- **해석 한계**: 프로필 간 수익 차이는 위험 선호의 차이이지 우열이 아님. 판정 1의 aggressive 쪽은 수익 변동성 조건을 두지 않음(모델과 충돌하는 방향이라 변동성이 반드시 커진다는 보장이 없고, 보유 종목 변동성으로 충분).
- **누수 방지**: 모든 z는 판단일 T의 횡단면 값만 사용. λ_p는 train 구간만 사용. 테스트로 강제.
- **구현 계획**: (1) `scoring.py`에 `standardized_rank`, `calibrate_lambda`, 새 `personalize_scores`(기여도 열 유지 — 설명 레이어용), 기존 raw 가중치 방식은 제거(항목 16 수치는 git 이력). (2) `scripts/evaluate_personalization.py`를 top50·W1~W3·buffer 엔진으로 재작성. (3) 테스트: neutral = 모델 순위 동일, λ 이분 탐색이 목표 상관에 수렴, λ가 validation 데이터에 의존하지 않음, 방향 부호.
- **결과 (2026-09-30, 1회 실행, `reports/personalization/validation_results.csv`)**: W3 neutral 순누적 +65.0%로 항목 45·47 재현(MATCH). λ(train 보정)는 window 간 안정적: conservative 0.714 / 0.740 / 0.729, aggressive 0.727 / 0.711 / 0.714.

  | window | 프로필 | 순누적 | Sharpe | MDD | 수익 std/5일 | 보유 변동성 | IC | 모델 상관 | top-10 겹침 | 진입/구간 |
  |---|---|---|---|---|---|---|---|---|---|---|
  | W1 | conservative | −6.2% | −0.04 | −24.1% | 2.05% | 0.0149 | +0.0650 | 0.78 | 56% | 1.53 |
  | W1 | neutral | +34.8% | 0.52 | −19.5% | 2.49% | 0.0219 | +0.0665 | 1.00 | 100% | 2.54 |
  | W1 | aggressive | +15.4% | 0.29 | −23.0% | 2.60% | 0.0247 | +0.0569 | 0.82 | 81% | 1.37 |
  | W2 | conservative | +23.1% | 0.44 | −29.4% | 2.07% | 0.0141 | +0.0564 | 0.79 | 51% | 1.64 |
  | W2 | neutral | +15.9% | 0.29 | −35.5% | 2.78% | 0.0218 | +0.0458 | 1.00 | 100% | 3.29 |
  | W2 | aggressive | +5.0% | 0.16 | −31.4% | 2.84% | 0.0245 | +0.0337 | 0.81 | 80% | 2.45 |
  | W3 | conservative | +33.0% | 0.47 | −40.7% | 3.38% | 0.0158 | +0.0310 | 0.80 | 50% | 1.89 |
  | W3 | neutral | +65.0% | 0.63 | −43.7% | 4.36% | 0.0244 | +0.0218 | 1.00 | 100% | 3.26 |
  | W3 | aggressive | +68.1% | 0.64 | −44.4% | 4.56% | 0.0292 | +0.0038 | 0.79 | 70% | 3.03 |

  dev(2025-09~2026-06, 보고만): conservative +52.5% / MDD −14.9% / IC +0.0001, neutral +54.7% / −16.2% / −0.0041, aggressive +50.3% / −21.0% / −0.0021.
- **사전등록 판정: conservative·aggressive 모두 통과 → 세 프로필 모두 `recommend.py`에서 선택 가능(기본 neutral).** conservative는 세 window 모두 보유 변동성(약 −30%)과 수익 std가 neutral보다 낮고, aggressive는 보유 변동성이 높음. 모델 상관 0.78~0.82(목표 0.8 유지), IC 모두 ≥ 0.
- **관찰(판정과 별개, 해석용)**:
  1. **aggressive의 IC 여유가 작음**: W3 +0.0038(neutral +0.0218), dev −0.0021. 통과는 했지만 최근 구간일수록 모델 신호를 거의 다 소모함. forward2에서 IC가 음수로 가면 비활성화 대상.
  2. **conservative는 "수익 변동성"을 낮추지 "낙폭"을 보장하지 않음**: W1에서 MDD가 오히려 악화(−19.5% → −24.1%), 수익도 −6.2%. 사용자 설명에서 "손실이 작다"가 아니라 "변동이 작은 종목 위주"로 표현해야 함.
  3. conservative의 IC가 W2·W3·dev에서 neutral보다 높음(저변동성 효과로 보임). 그러나 판정 목적이 아니었고 W1에서는 낮음 → 이를 근거로 기본값을 바꾸지 않음(사후 선택).
  4. conservative·aggressive 모두 회전율이 neutral보다 낮음(진입/구간 1.4~3.0 vs 2.5~3.3) — 변동성·거래량 순위가 모델 점수보다 안정적이기 때문.
- **연결** (`scripts/recommend.py --profile conservative|aggressive`): 고정 모델의 train 구간에서 λ를 매번 다시 계산(W3와 동일 값, conservative 0.729 / aggressive 0.714), 종목별로 모델 순위 점수·변동성 조정·거래량 기여와 최종 점수를 출력. **페이퍼 트레이딩 기록 `reports/daily_picks/<T>.csv`는 neutral 실행만 저장**(사전등록 전략의 기록), 프로필 실행은 `reports/daily_picks_<profile>/`에 따로 저장. 야간 수집(`nightly_ingest.sh`)은 neutral 그대로.
- **바꾸지 않은 것**: forward 평가(항목 50·53), 운용 경로, λ 목표 0.8·판정 기준.
- **다음 단계**: 대기 기간 남은 과제 — Phase L 설문 흐름 설계(프로필 선택을 설문 응답으로 연결), 분기 D 대비 데이터 소스 조사.

57. **투자성향 설문(Phase L) → 프로필 연결 — 설계 확정 및 구현 (2026-09-30, 재훈과 설계)**

- **목적**: 설문 응답으로 항목 56의 세 프로필 중 하나를 고르고, 이 전략이 맞지 않는 사람에게는 추천을 보여주지 않음. 실험이 아니라 설계이며, 경계값(0.4·0.7)과 점수는 데이터로 정한 값이 아닌 설계 선택(검증할 결과 데이터가 아직 없음).
- **문항** (`src/recommendation/survey.py`, 괄호는 점수, ✕ = 추천 불가):

  | # | 영역 | 질문 | 선택지 |
  |---|---|---|---|
  | Q1 | 여력 | 이 투자금이 앞으로 얼마나 오랫동안 필요하지 않은 자금인가요? | 1개월 이내 사용 가능성 ✕ / 1년 이내 사용 가능성 (1) / 1~3년 사용 계획 없음 (2) / 3년 이상 (3) |
  | Q2 | 여력 | 이 투자금의 절반 가까이 손실이 나더라도 생활비나 예정된 중요한 지출에 영향이 없나요? | 영향을 줌 ✕ / 어느 정도 영향 (1) / 거의 없음 (2) / 전혀 없음 (3) |
  | Q3 | 성향 | 1년 동안 투자금 가치가 최대 어느 정도까지 줄어도 투자를 계속 유지할 수 있나요? | 원금 손실 감수 어려움 ✕ / 최대 10% (0, 경고) / 20% (1) / 30% (2) / 40% 이상 (3) |
  | Q4 | 성향 | 보유 종목이 특별한 악재 없이 일주일 만에 약 10% 하락하면? | 대부분·전부 매도 (0) / 일부 매도 (1) / 유지 (2) / 추가 매수 (3) |
  | Q5 | 성향 | 가장 중요하게 달성하고 싶은 목표는? | 원금 보존 (0) / 예·적금보다 조금 높은 수익 (1) / 시장 평균 수준 (2) / 시장 평균을 웃도는 수익 (3) |
  | Q6 | 경험 | 주식 직접 투자 기간은? | 없음 (0) / 1년 미만 (1) / 1~3년 (2) / 3년 이상 (3) |

- **결정 규칙**: 여력 = (Q1 + Q2)/6, 성향 = (Q3 + Q4 + Q5)/9, s = min(여력, 성향) — 낮은 쪽이 결정(모순된 응답은 자동으로 보수적으로 처리). s < 0.4 안정형, 0.4 ≤ s < 0.7 중립형, s ≥ 0.7 이고 Q6 ≥ 1~3년이면 공격형(경험 부족 시 중립형, 항목 56에서 aggressive의 IC 여유가 가장 작았기 때문).
- **Q3 "최대 10%"**: 경고("안정형도 과거 검증 MDD −24%~−41%") 후 확인해야 진행, 진행 시 **안정형으로 상한 고정**(성향 점수만으로는 중립형까지 나올 수 있어서), 거부 시 추천 불가. 저장 파일에 `warning_acknowledged` 기록.
- **위험 고지**: 설문 시작 전에 전략 구조(대형주 50종목 중 상위 10, 5거래일 보유), 과거 MDD −20%~−44%, forward 평가 미완료, 투자 권유 아님을 먼저 보여줌.
- **사용**: `PYTHONPATH=. python scripts/survey.py`(대화형, `--answers`로 비대화형) → `data/user_profile.json` 저장(**gitignore — public 레포에 개인 응답이 올라가지 않음**) → `scripts/recommend.py --profile saved`. 추천 불가 결과가 저장돼 있으면 추천 대신 이유만 출력. 버전(`SURVEY_VERSION`)이 바뀌면 재진단 요구.
- **바꾸지 않은 것**: `recommend.py` 기본값은 neutral, 야간 페이퍼 트레이딩 기록도 그대로 neutral.
- **테스트**: `tests/test_survey.py` 11개(상수 고정, 추천 불가 조건 3개, 10% 경고·상한, min 규칙, 경계값, 경험 조건, 입력 검증, 저장·로드·버전, 설명 문구).
- **다음 단계**: 대기 기간 남은 과제 — 분기 D 대비 뉴스·매크로·수급 데이터 소스 조사. 설문 경계값은 실제 사용자 응답·만족도가 쌓이면 재검토(그 전에는 바꾸지 않음).

58. **KOSPI 지수(ka20006) + 종목별 투자자 수급(ka10059) 수집·정규화·저장 구현 (2026-10-01, forward 대기 기간 데이터 확장 1단계) — 실험 아님, feature/모델 반영 없음**

- **목적**: 분기 D(항목 53) 대비 + 리스크 레이어의 시장 대용 지수(항목 55, 생존편향 있는 유니버스 동일가중)를 실제 지수로 바꿀 수 있게. forward·test 구간을 읽지 않고, 운용 경로·사전등록 판정은 바꾸지 않음. 이 데이터를 쓰는 실험은 별도 사전등록 후 W1~W3에서만, 표본 밖 확인은 forward2.
- **실제 응답 확인** (`scripts/check_kiwoom_flow_index.py`, 2026-10-01 13:18 장중, raw는 `data/raw/kiwoom/probe_flow_index/`):
  - ka20006: 600행/페이지, 연속조회는 과거 방향, KOSPI(001) 1985-01-04~ 10,940일·19페이지에서 종료. 지수 값은 스펙대로 100배 정수. 2000년 이전 OHLC 불일치 봉 9개(1989~1996) — 일봉과 같은 규칙으로 경고 후 제외.
  - ka10059/ka10060: 100행/페이지, 과거 방향, 40페이지로 2010-06-30까지(아직 더 있음, W1 2012~ 충분). 두 API의 수급 값은 3,999일 전부 동일하나 **ka10060의 `acc_trde_prica`는 실제로 거래량**(ka10059 `acc_trde_qty`와 3,999일 일치) → ka10059 채택.
  - **항등식**: 개인 + 외국인 + 기관 세부 8개 + 기타법인 + 내외국인 = 0 이 과거 전 일자에서 반올림 오차(최대 ±4백만원) 내 성립. 장중 당일 행은 +68,419로 불일치(개인·금융투자·사모 0) → 가집계 판별 규칙으로 사용.
  - **`orgn`(기관계) 정의 단절**: 2010~2012년 509일은 기관계에서 국가가 빠져 있음(509일 전부 이 설명으로 정확히 일치), 이후는 포함. feature에는 세부 8개 합(`institution_total`)을 쓰고 `orgn`은 `institution_reported`로 보존만.
- **구현**: `KiwoomClient.get_index_daily_chart_page/get_index_daily_history`, `get_investor_flow_page/get_investor_flow_history`(연속조회 + `stop_date`로 증분 수집), `IndexDailyBar`/`InvestorFlowDay`(내부 필드명), `normalize_ka20006_response`/`normalize_ka10059_response`, `HistoricalStorage.save_raw_kiwoom` + `processed/index/<code>.json`·`processed/investor_flow/<code>.json`(날짜별 병합), `scripts/ingest_kiwoom_flow_index.py`(기본 지수 001·201 + 유니버스, `--lookback-days`로 증분).
- **미완성 행 처리**: 행마다 `retrieved_at`과 `is_complete` 저장. 당일 행은 `SESSION_FINAL_TIME_KST`(18:00, **임시 보수값**) 이후 수집분만 완성, 수급은 추가로 항등식 통과 필요. 미완성 행은 버리지 않고 저장하되 기본 loader에서 제외, 나중 수집의 완성 값이 대체(완성 값을 미완성 값이 덮어쓰지 않음).
- **미결**: (1) 당일 수급·지수가 언제 확정되는지 — 2026-10-01 18시 이후와 10-02 아침에 probe 재실행해 10/01 행 비교 후 `SESSION_FINAL_TIME_KST` 확정. 판단 시점 A에 당일 수급을 쓸 수 있는지가 여기서 결정됨. (2) ~~ka20006 `trde_qty` 단위~~ → **해결(아래)**. (3) 전체 이력 수집(80페이지 상한)과 `nightly_ingest.sh` 연결은 (1) 확인 후.
- **ka20006 `trde_qty` 단위 확정 (2026-10-01, probe raw + 기존 일봉만 사용)**: 스펙은 "단위: 1주"이지만 실제로는 **천주**. 근거: probe 1페이지(2024-04-12~2026-09-28) 중 유니버스 50종목 일봉이 모두 있는 597일 전부에서, top50 종목 거래량 합만으로 KOSPI 지수 `trde_qty`의 46~315배(중앙값 170배) — 1주 단위라면 불가능. 천주로 읽으면 top50 비중 4.6%~31%(중앙값 17%)로 타당. `trde_prica`는 스펙대로 백만원 확인(top50 거래대금 비중 0.39~0.87, 중앙값 0.59 — 1을 넘는 날 없음). → `IndexDailyBar.volume`을 `volume_thousand_shares`로 이름 변경(값은 raw 그대로, 단위를 필드명에 — `trade_value_million_krw`와 같은 방식). processed/index 파일은 아직 만든 적 없어 이전 데이터 변환 불필요. 테스트 단언 1개 추가(거래대금), 테스트 수 변화 없음.
- **전체 이력 수집 + 품질 점검 (2026-10-01 장중 실행, `ingest_kiwoom_flow_index.py` 기본값, 50/50 성공)**:
  - 지수: 001 KOSPI 1985-01-04~ 10,931봉, 201 KOSPI200 1998-07-27~ 6,966봉. 2012~ 거래일이 005930 일봉과 양방향 완전 일치. 미완성은 당일(10/01)뿐.
  - 수급: 50종목 289,154행. 2012~ 일봉 거래일 대비 누락 0일(전 종목).
  - **수급 실데이터는 2006-01-02부터**(003670·035420은 2004-12-01, 이후 상장 종목은 상장일부터). 그 이전은 거래가 있는데도 12개 투자자 값이 모두 0인 채움 행 → 항등식을 자명하게 통과해 `is_complete=True`로 저장됨. **누락을 0 순매수로 오인할 위험** → `InvestorFlowDay.flow_reported`(거래량 > 0인데 전 투자자 0이면 False) 추가, 기본 loader에서 제외(`include_unreported=True`로만 포함). 저장 형식 변경 없음, 재수집 불필요. 해당 행 70,632개. 거래정지일(거래량 0, 수급 0)은 실제 0이라 유지.
  - 함의: daily 학습 구간은 2002-10-29부터지만 **수급 feature를 쓰는 실험은 학습 시작을 2006 이후로** 잡거나 결측 처리 규칙을 사전등록에 명시해야 함.
  - 80페이지 상한에 걸린 18종목은 모두 1995-01-16에서 멈췄고 그 구간은 위의 0 채움 행이라 **실제 손실 없음**.
  - 불균형(미완성) 과거 행: 2006~2009년 74일(대부분 수 ~ 수천 백만원) + 018260 2014-08~11의 31일(잔차가 12의 배수, 상장 전 구간). 2015년 이후 0일.
  - **기존 일봉 데이터 이슈 발견(수정 안 함)**: 018260(삼성SDS)은 KOSPI 상장이 2014-11-14인데 ka10081 일봉은 2014-08-25부터 있음. 재훈 확인(키움 차트): 상장 전 54거래일은 실제 거래 — 2014-08-25 개장한 **K-OTC(장외시장)** 거래(개장 첫날부터 삼성SDS가 대장주로 거래된 것이 당시 보도로 확인됨). 데이터 오류가 아니라 **다른 시장의 가격**이라는 점이 문제: 거래량이 하루 수천 주(상장 후 수백만 주), 수급 내역 없음(위 0 채움·불균형 31일이 이 구간), 시장이 바뀌는 날 종가 377,500 → 327,500(−13%)으로 이어 붙음. KOSPI 종목 대상 모델 입장에서는 유동성·가격 형성 방식이 다른 표본이고, 이 구간 수익률·feature가 고정 모델 학습 데이터(train 2002~2019)에 포함됨. forward 전 고정 모델은 바꾸지 않음 — forward 이후 새 사이클에서 **KRX 상장일 이전 행 제외 규칙**(유니버스 전체 적용) 검토.
- **테스트**: `tests/test_flow_index_data.py` 27개(이후 추가: 진행 콜백 1, `flow_reported` 2)(완성 판정·KST, 100배 복원, legacy 봉, 필드 매핑, 기관 정의 단절, 항등식·허용오차, 저장 병합 규칙, 연속조회·stop_date, 배치 실패 격리), `tests/test_kiwoom_client.py` 6개 추가, 전체 293개 통과.

59. **분기 D 데이터 소스 조사 — 매크로·공시·뉴스 (2026-10-01, 조사만, 구현·실험 없음)**

- **목적**: 항목 53 분기 D(daily 신호 기각 시 새 신호원) 대비. 수급·지수는 항목 58로 확보. 나머지 후보를 "과거 이력이 W1(2012~)부터 있는가 / 판단 시점 A(T 장 마감 후 판단 → T+1 시가 진입)에 그 값이 실제로 알려져 있었는가 / 비용·한도"로 걸러 우선순위를 정함. AGENTS.md 16·17절(근거 없이 변수 추가 금지)에 따라 여기서는 소스만 정하고, 쓸 변수는 실험 사전등록에서 정함.
- **판단 시점 정렬 규칙 (모든 외부 소스 공통, 사전 확정)**: 판단은 T일 20시 이후(야간 수집 후). 국내 시장 데이터(금리·환율·지수·수급)는 T일 값 사용 가능. **미국·해외 시장 데이터는 T-1일(현지 날짜) 값까지만** — 미국 T일 장은 한국 시각 T+1 새벽에 끝나므로 20시 판단 시점엔 미확정. 공시는 접수일 ≤ T.

| 우선 | 소스 | 내용 | 이력 | 시점 문제 | 비용·한도 |
|---|---|---|---|---|---|
| 1 | 한국은행 ECOS Open API | 시장금리(국고채 3·10년, CD 등), 원/달러 환율, 기준금리 — 일별 | 수십 년 | 시장 가격이라 수정 없음, T일 값 사용 가능 | 무료, 인증키 필요 |
| 1 | FRED API (미 연준) | 유가(WTI), 미 국채 금리, VIX, 달러지수 등 — 일별 | 수십 년 | 위 규칙대로 T-1 | 무료, 인증키 필요 |
| 2 | OpenDART 공시검색 API | 공시 목록(보고서명·접수번호·접수일) → 이벤트 feature(유상증자·실적 공시 등) | 1999~ | **접수일자만 제공(시각 없음)** — 판단 시점이 T 장 마감 후라 "접수일 ≤ T"면 충분. 단 장중 공시와 장 마감 후 공시를 구분할 수 없어 당일 반응 분석엔 못 씀 | 무료, 일 20,000회, 회사코드 없이 검색 시 기간 3개월 제한 → 종목별 조회 |
| 3 | 네이버 검색 API(뉴스) | 기사 제목·요약·발행시각 | **최근 기사만**(한 검색어당 최대 약 1,000건까지 넘겨볼 수 있음) | 과거 백테스트 불가 | 무료, 일 호출 한도 있음 |
| 3 | 빅카인즈 등 뉴스 아카이브 | 과거 기사 | 장기 | 발행시각 있음 | 기관·유료 접근 위주 — 확인 필요 |

- **결론(제안, 재훈 확인 전)**:
  1. **다음 구현은 매크로(ECOS + FRED)**. 이력·시점 정합성·비용 모두 문제 없고, 항목 55 리스크 레이어(시장 국면)와 분기 D 둘 다에 쓰임.
  2. **공시(DART)는 그다음**. 이벤트 feature라 종목·날짜별 희소 데이터 — 설계(어떤 보고서 유형을 쓸지)를 먼저 사전등록.
  3. **뉴스는 보류**. 무료 소스로는 과거 이력을 만들 수 없어 W1~W3 검증이 불가능. 지금부터 수집만 쌓으면 forward2 이후에야 검증 가능 → 필요하면 수집기만 먼저 돌려 두는 선택지.
- **필요한 것(재훈)**: ECOS 인증키, FRED API 키, (2단계) OpenDART 인증키 — 각각 발급 후 `.env`에 `ECOS_API_KEY`, `FRED_API_KEY`, `DART_API_KEY`로 추가(커밋 금지, `.env.example`에는 자리만).

- **추가 (2026-10-01 저녁) — 매크로 probe 결과와 결론 수정**: `scripts/check_macro_sources.py` 실행(21:22 KST).
  - ECOS 817Y002(국고채 3·10년, 회사채 AA-, CD91)·731Y001(원/달러) 모두 정상, 이력 2000년 이전부터, 21:22 시점에 T일 값 존재. 원/달러 매매기준율은 전일 거래로 정해지는 값이라 사실상 T-1 정보(누수 아님).
  - **정정 — FRED 시점 규칙은 T-1이 아니라 T-2**: 21:22 KST에 WTI·DGS10·DGS2·VIX 최신값이 미국 9/29(9/30 아님). `last_updated` 기준 미국 d일 값의 FRED 반영 시각 ≈ VIX d+1일 22:37, WTI d+2일 02:18, DGS d+2일 05:16(KST) → T일 20시 판단엔 미국 날짜 ≤ T-2(달력일)만 사용 가능. 1회 관측 기반이라 추가 확인 필요. DTWEXBGS는 주 단위 공표로 지연 큼, SP500은 2016~(W1 미커버), LBMA 금은 시리즈 없음.
  - **결론 수정**: 매크로는 날짜별로 전 종목에 같은 값이라 rank 타깃(횡단면 rank IC)에서는 단독으로 순위를 가를 수 없음 — 위 결론 1의 "분기 D에 쓰임"은 틀림. 매크로의 용도는 시장 국면(리스크 레이어) 쪽이고, 횡단면에 쓰려면 종목별 민감도(예: 환율 베타 × 환율 변화) 같은 파생 feature로 사전등록해야 함. **ECOS만 수집 대상으로 유지, FRED는 보류**(구체적 가설이 생기면 T-2 규칙으로). 분기 D 본선은 종목별 이벤트인 DART 공시로 이동 → 항목 60.

60. **OpenDART probe — 이력·표본 수·point-in-time 확인 (2026-10-01, 조사만, 실험 아님)**

- **목적**: DART 공시/재무를 분기 D 후보로 사전등록하기 전에, 쓸 수 있는 데이터인지 숫자로 확인. 가격·라벨은 읽지 않고, 공시 건수는 validation W1~W3(2012-01-01~2023-06-30)만 셈(test·forward 구간 미접근).
- **스크립트**: `scripts/check_dart_sources.py` (raw·요약 CSV → `data/raw/dart_probe/<ts>/`, gitignored). 확인 항목: (1) top50 종목코드 → corp_code 매핑, (2) 구조화 재무 API(`fnlttSinglAcnt`, `fnlttSinglAcntAll`)가 몇 사업연도부터 응답하는지(W1 커버 여부), (3) 공시 유형별·구간별 건수(정정공시 제외 원본만), (4) 재무 API가 원본 사업보고서를 주는지 정정본을 주는지(point-in-time), (5) 목록 행에 시각 필드가 있는지.
- **판단 기준(결과 보기 전 고정)**: 재무 API가 2012 사업연도를 못 덮으면 재무 feature는 W1 검증 불가 → W2·W3만으로 할지 별도 결정. 이벤트 유형별로 구간당 건수가 수십 건 이하이면 이벤트 feature 후보에서 제외. 재무 API가 정정본을 주면 원본 접수번호 기준 재구성 없이는 사용 금지.
- **테스트**: `tests/test_check_dart_sources.py` 4개(보고서명 정규화·분류, 구간 판정, PIT 판정; 네트워크 없음).
- **결과 (2026-10-02 실행, API 1,238회, raw `data/raw/dart_probe/20261002_181712/`)**:
  1. **매핑**: top50 50/50 corp_code 매핑 성공.
  2. **재무 API 이력**: 005930 기준 `fnlttSinglAcnt`·`fnlttSinglAcntAll` 모두 **2015 사업연도부터**(2010~2014는 013 no data) → **W1(2012~2015) 재무 feature 검증 불가**. 추가 발견: KB금융(105560)·삼성생명(032830)·SK스퀘어(402340)는 2015~2022 전부 no data — 금융업(지주·보험 등) 미지원으로 추정(3종목 관측, 미확인). 맞다면 top50의 은행·보험·증권 약 10종목이 빠짐.
  3. **공시 건수(원본만, 구간별 건수/종목 수)**: 모든 구간 100건 이상 — 잠정실적(911~1026), 정기보고서, 배당(215~311), 5% 대량보유(661~716), 임원·주요주주 소유보고(5012~5898), 최대주주 관련(594~764), 기타 공정공시(115~148), 단일판매·공급계약(230~695, 단 19~22종목에 집중). **구간당 100건 미만** — 자사주 취득(55~69)·처분(58~133)·소각(4~47)·유상증자(51~100)·무상증자(0~4)·CB/BW/EB(6~15)·합병·분할(37~77). 사전등록 기준 "수십 건 이하"를 '구간당 100건 미만'으로 읽었음(기준 문구가 숫자로 고정돼 있지 않았던 점은 한계로 기록 — 경계에 걸리는 건 자사주·유상증자). 참고: 5일 초과수익 표준편차를 약 5%로 보면 60건 평균의 표준오차 ≈ 0.65%라 어차피 검정력이 없음.
  - 잠정실적은 동질적이지 않음: 005930은 분기 잠정실적이 분기당 2건(예비·확정), 005380은 `영업(잠정)실적(공정공시)`가 **월별 판매실적**(138건)이라 같은 이름에 성격이 다른 공시가 섞임. 값은 구조화 API가 아니라 본문에만 있음(파싱 필요).
  - 006800(미래에셋증권) 25,775건은 대부분 ELS 등 파생결합증권 발행 서류(증권발행실적보고서·투자설명서·일괄신고추가서류) — 이벤트 집계에서 노이즈.
  4. **Point-in-time: 실패**. 정정 공시가 있는 사업연도 16건 전부 API가 **최신 정정본**을 반환(원본 반환 0건). 극단 사례: 005380 2015~2020 사업연도 값이 전부 2022-02-17 정정본, 2021·2022는 2024년 정정본(probe의 목록 범위 2023-06 밖이라 'other'로 분류됨). 즉 API 값을 그대로 쓰면 수년 뒤 정보가 섞임 → 사전등록 기준대로 **원본 접수번호 기준 재구성 없이는 사용 금지**.
  5. **시각 필드**: 목록 행 키 `corp_cls, corp_code, corp_name, flr_nm, rcept_dt, rcept_no, report_nm, rm, stock_code` — **날짜만, 시각 없음**(항목 59 예상과 일치).
- **판정**: DART 구조화 재무 API는 (W1 미커버 + 금융업 누락 추정 + PIT 실패)로 **그대로는 사용 불가**. 원본 XBRL/본문 재구성은 비용이 큼. 이벤트 중 표본이 충분한 것은 임원·주요주주 소유보고, 5% 대량보유, 잠정실적(본문 파싱 필요) 정도. 다음 방향은 미결(재훈 결정).
- **후속 결정 (2026-10-03, 재훈)**: DART 공시의 모델 feature화는 **보류**(forward 결과 뒤 재검토). DART는 제품의 공시 카드(항목 61, 참고 정보, 모델 미사용)로만 사용 — 목록·메타데이터만, 구조화 재무값은 PIT 문제로 쓰지 않음.

61. **분석가 패널(제품 레이어) 설계 + 1단계 차트 카드 사전등록 (2026-10-03) — 모델·전략 변경 없음**

- **배경**: 재훈 아이디어 — 웹에서 주가(차트)·시장·뉴스/공시 "전문가"를 클릭하면 각자 분석 결과를 보여 주는 형태. 다듬은 설계를 **AGENTS.md 43절**에 영구 규칙으로 고정.
- **합의된 설계 요약**: (1) 추천 층(퀀트 모델, 유일하게 검증된 층)과 참고 층(차트·시장·공시/뉴스 카드)을 분리 — 참고 카드는 점수·순위·`reports/daily_picks/`에 영향 없음, "모델 미사용" 라벨 필수, 추천 이유로 표현 금지. (2) 차트 카드는 기술적 분석 규칙 대신 **우리 데이터의 과거 통계(base rate)**. (3) 숫자는 코드가 결정적으로 계산, 문장은 템플릿(1차)·LLM(나중, 입력 숫자 외 금지). (4) 카드 간 의견 충돌은 그대로 표시, 검증 없는 종합 점수 금지. (5) 설문 성향은 카드 노출 순서만 바꿈. (6) 공개 유료 서비스 전 유사투자자문업 등 규제 확인.
- **만드는 순서**: 1 퀀트+차트 카드 → 2 공시 카드 → 3 시장 카드(ECOS 수집기) → 4 뉴스 → 5 웹(처음엔 Streamlit 등 간단히).

**1단계 차트 카드 — base rate 정의 (계산 전 고정)**

- **구간**: 2012-01-01 ~ `VALIDATION_END_DATE`(2023-06-30), 마지막 5거래일은 purge(라벨이 2023-07 이후 가격을 쓰지 않게). test·forward 미접근 — 데이터셋을 날짜로 자른 뒤에만 계산.
- **유니버스**: `STOCKLENS_UNIVERSE=top50`(2026-09-21 기준, 생존편향 — 카드에 명시).
- **결과 변수**: `target_return_5d`(T+1 시가 진입 → T+5 종가) − 같은 날 유니버스 평균 = 초과수익.
- **상태 정의 5개 (전부 항상 표시, 골라서 보여 주지 않음)**:
  1. RSI(14): 과매도 <30 / 중립 30~70 / 과매수 ≥70
  2. 60일선 대비 (`price_to_sma_60`): < −10% / −10~0% / 0~+10% / ≥ +10%
  3. 20일 수익률 상대 위치 (`return_20d`, 같은 날 종목 간 5분위): Q1(최약) ~ Q5(최강)
  4. 거래량 (`volume_ratio_20` = 거래량/20일 평균): <0.7 한산 / 0.7~1.5 보통 / 1.5~3 증가 / ≥3 급증
  5. 변동성 (`volatility_20`, 같은 날 종목 간 5분위): Q1(최저) ~ Q5(최고)
- **통계**: 관측 수, 고유 날짜 수(5일 라벨 중첩 — 관측 수가 독립 표본 수를 과대평가), 평균·중앙값 초과수익, 플러스 비율, W1(2012~2015)/W2(2016~2019)/W3(2020~2023H1)별 평균.
- **표시 규칙**: 관측 수 < 100이거나 어느 구간이든 관측 수 < 30이면 "표본 부족". 세 구간 평균의 부호가 모두 같으면 "과거 경향(세 구간 일관)"으로 평균 표시, 다르면 **"일관된 경향 없음"**으로 표시하고 구간별 부호만 보여 줌. 유의성 검정·순위 매김 없음(설명용 기술통계).
- **수급**: 최근 5·20거래일 외국인·기관(세부 8개 합) 순매수(억원)와 같은 기간 거래대금 대비 비율 — **표시만**, base rate 없음(수급 base rate는 데이터 시작 2006·기관 정의 단절(항목 58) 처리 규칙을 정한 뒤 별도 사전등록).
- **해석 한계**: 과거 base rate는 예측이 아님. 상태 간 상관(예: RSI 과매수와 20일 Q5)이 커서 카드 5줄을 독립 근거로 읽으면 안 됨. 생존편향으로 과거 수익이 위로 치우칠 수 있음.
- **구현 계획**: `src/analysts/chart.py`(상태 분류·base rate·카드 데이터·템플릿 문장), `scripts/build_chart_base_rates.py`(→ `data/processed/analysts/chart_base_rates.json`), `scripts/chart_card.py --code <종목>`(최신 판단일 카드 출력 + JSON 저장 `reports/analyst_cards/<T>/<code>.json`), 테스트 `tests/test_analyst_chart.py`.
- **테스트**: `tests/test_analyst_chart.py` 7개(구간 경계·NaN/inf, 날짜 내 5분위, 검증 구간만+마지막 5일 purge, 2023-06 이후 값을 바꿔도 결과 불변, 판정 규칙, 수급 기준일, 카드에 상태 5개 항상 포함·참고 라벨). 전체 통과 수는 재훈 기기 실행 후 기록.
- **결과 (2026-10-03, `build_chart_base_rates.py`, top50)**: 기간 2012-01-01~2023-06-23(마지막 5일 purge), 123,379행, 2,827일.

  | 상태 | 구간 | n | 날짜 | 평균 초과 | 플러스 | W1 | W2 | W3 | 판정 |
  |---|---|---|---|---|---|---|---|---|---|
  | RSI | 과매도(<30) | 5,419 | 1,576 | +0.47%p | 52.0% | +0.25 | +0.61 | +0.56 | 일관 |
  | RSI | 중립 | 112,201 | 2,826 | −0.02 | 46.8% | −0.01 | −0.01 | −0.04 | 일관 |
  | RSI | 과매수(≥70) | 5,759 | 1,941 | −0.10 | 45.2% | −0.13 | −0.41 | +0.15 | 불일치 |
  | 60일선 | −10% 미만 | 12,235 | 2,286 | +0.37 | 51.2% | +0.28 | +0.40 | +0.41 | 일관 |
  | 60일선 | −10~0% | 50,275 | 2,817 | −0.07 | 46.6% | −0.07 | −0.04 | −0.10 | 일관 |
  | 60일선 | 0~+10% | 45,371 | 2,821 | −0.03 | 46.8% | +0.04 | −0.04 | −0.11 | 불일치 |
  | 60일선 | +10% 이상 | 15,498 | 2,697 | +0.04 | 45.4% | −0.11 | −0.09 | +0.20 | 불일치 |
  | 20일 수익률 | Q1(최약) | 23,568 | 2,827 | +0.10 | 48.4% | +0.12 | +0.17 | +0.02 | 일관 |
  | 20일 수익률 | Q2 | 24,439 | 2,827 | −0.02 | 46.9% | −0.04 | +0.01 | −0.03 | 불일치 |
  | 20일 수익률 | Q3 | 25,146 | 2,827 | +0.04 | 47.2% | +0.01 | +0.00 | +0.10 | 일관 |
  | 20일 수익률 | Q4 | 24,458 | 2,827 | −0.04 | 46.4% | −0.05 | −0.07 | +0.02 | 불일치 |
  | 20일 수익률 | Q5(최강) | 25,768 | 2,827 | −0.07 | 46.2% | −0.03 | −0.10 | −0.10 | 일관 |
  | 거래량 | 한산(<0.7) | 34,496 | 2,795 | −0.04 | 46.0% | −0.06 | −0.11 | +0.04 | 불일치 |
  | 거래량 | 보통 | 73,879 | 2,827 | +0.00 | 47.2% | +0.01 | +0.03 | −0.03 | 불일치 |
  | 거래량 | 증가(1.5~3) | 13,439 | 2,668 | +0.12 | 48.5% | +0.14 | +0.16 | +0.07 | 일관 |
  | 거래량 | 급증(≥3) | 1,565 | 1,029 | −0.12 | 44.9% | −0.10 | −0.43 | +0.11 | 불일치 |
  | 변동성 | Q1(최저) | 23,568 | 2,827 | −0.04 | 46.8% | −0.02 | +0.07 | −0.17 | 불일치 |
  | 변동성 | Q2 | 24,440 | 2,827 | −0.06 | 46.8% | −0.10 | −0.04 | −0.05 | 일관 |
  | 변동성 | Q3 | 25,160 | 2,827 | +0.02 | 47.1% | +0.01 | −0.01 | +0.06 | 불일치 |
  | 변동성 | Q4 | 24,440 | 2,827 | +0.07 | 48.0% | +0.10 | +0.08 | +0.03 | 일관 |
  | 변동성 | Q5(최고) | 25,771 | 2,827 | +0.01 | 46.3% | +0.01 | −0.09 | +0.13 | 불일치 |

  - **읽을 만한 것**: 세 구간 일관 + 크기가 의미 있는 건 단기 반전 계열뿐 — RSI 과매도 +0.47%p, 60일선 −10% 미만 +0.37%p, 20일 Q1 +0.10 / Q5 −0.07. 항목 15·17의 "단기 가격 반전" 관찰과 같은 방향. 과매수(RSI ≥70)·거래량 급증은 "과열 경고"로 흔히 읽히지만 우리 데이터에선 구간마다 방향이 달라 **일관된 경향 없음**.
  - **플러스 비율이 거의 다 50% 미만**(평균이 0 근처여도 46~47%): 5일 초과수익 분포가 오른쪽으로 치우쳐 중앙값이 음수라서. 카드에서 플러스 비율을 "승률"로 읽으면 오해 — 평균과 같이 봐야 함.
  - **판정 규칙의 약점(사후 발견, 규칙은 바꾸지 않음)**: "일관" 판정이 크기를 보지 않아 RSI 중립(−0.02%p)·20일 Q3(+0.04%p)처럼 사실상 0인 것도 "과거 경향(세 구간 일관)"으로 표시됨. 결과를 본 뒤 고치면 사후 조정이므로 그대로 두고, 수정은 별도 제안으로 분리(재훈 결정 대기).
  - **카드 실행**: 첫 실행은 `STOCKLEN_UNIVERSE` 오타로 기본 유니버스(core5)가 잡혀 실패 — 코드 문제 아님. 에러 메시지에 유니버스 크기와 환경변수 확인 안내를 추가.
  - 유의성 검정 없음(사전등록대로 기술통계). 5일 라벨 중첩·종목 간 상관 때문에 n이 독립 표본 수보다 훨씬 큼.

62. **데이터 이슈 기록: 장중 미완성 일봉 저장 + 207940 수정주가 재계산 (2026-10-03, 조사만, 수정 없음)**

- **장중 미완성 일봉**: 커밋 `085b23a`(2026-09-28 12:50 KST, 장중)에 50종목 9/28 일봉이 장중 값으로 들어가 있었음(예: 005930 거래량 1,134만 → 확정 2,135만, 종가 272,250 → 270,000). 이후 야간 수집이 확정값으로 덮어써 현재 데이터는 정상. ka10081 일봉에는 수급·지수(항목 58)와 달리 `is_complete` 표시가 없음.
  - **영향**: `reports/daily_picks/20260928.csv`가 9/28 장중(약 12:41 KST) 값으로 만들어짐 — 그날 종가 기준이 아님. 페이퍼 로그 원칙상 파일은 고치지 않고 이 사실만 기록. forward 평가는 확정 일봉으로 계산되므로 직접 영향 없음.
  - **제안(미구현)**: `recommend.py`가 평일 `SESSION_FINAL_TIME_KST`(18:00, 항목 58의 임시값) 전에 당일 봉으로 판단하려 하면 중단하는 가드 + 테스트.
- **207940(삼성바이오로직스) 전 이력 재조정**: 2026-10-01까지 모든 봉의 가격 ×0.99230(범위 0.992296~0.992322), 거래량 ×약 1.0078, 거래대금·등락폭은 그대로. 10-02 봉부터 조정 없음 → **10-02 기준 기업 행위로 키움이 수정주가를 다시 계산**한 것으로 보임(원인 미확인). 다른 49종목의 diff(약 60줄)는 9/28 확정값 교체 + 9/29~10/2 신규 봉뿐.
  - **영향**: 가격·거래량이 전 구간에 같은 비율로 바뀌어 scale-free feature(수익률, 이동평균 비율, `volume_ratio_20` 등)와 라벨은 그대로. `volume_sma_20` 같은 원척도 값만 바뀌지만 모델 feature가 아님. 고정 모델 재학습 결과(`best_iteration`)가 바뀌는지는 다음 `recommend.py` 실행의 경고로 확인.

63. **차트 카드 판정 보완(사후 수정) + 장중 일봉 판단 가드 (2026-10-03) — 모델·전략 변경 없음**

- **(a) 차트 카드 "경향 미미" 판정 — 사후 수정임을 명시**: 항목 61 결과를 **본 뒤** 판정 규칙의 약점(크기를 안 봐서 −0.02%p 같은 값도 "세 구간 일관"으로 표시)을 발견해 고침. 추가 규칙: 세 구간 부호가 같아도 |전체 평균| < 0.1%p(`MIN_EFFECT`)이면 `negligible` → 카드에 "경향 미미". 0.1%p는 표시용 해상도 기준(재훈 합의)이지 유의성 기준이 아님. 카드 끝에 백테스트 가정 왕복 거래비용(수수료 0.015%×2 + 매도세 0.20% + 슬리피지 0.10%×2 ≈ 0.43%, `BaselineConfig` 단일 출처)을 같이 표시 — 이보다 작은 과거 경향은 매매로 이어지지 않는다는 점을 읽는 사람이 판단할 수 있게.
  - 이 수정으로 바뀌는 행(항목 61 수치 기준, 재계산 후 확인 필요): RSI 중립(−0.02), 20일 Q3(+0.04), 60일선 −10~0%(−0.07), 20일 Q5(−0.07), 변동성 Q2(−0.06)·Q4(+0.07) → 경향 미미. 남는 "일관": RSI 과매도(+0.47), 60일선 −10% 미만(+0.37), 20일 Q1(+0.10), 거래량 증가(+0.12). 판정은 표시 문구만 바꾸고 모델·점수와 무관.
- **(b) 장중 일봉 판단 가드** (항목 62 대응): `src/data/session.py` `intraday_bar_error()` — 판단일이 오늘(KST)이고 현재 시각이 `SESSION_FINAL_TIME_KST`(18:00, 항목 58 임시값) 전이면 중단, 미래 날짜도 중단. `scripts/recommend.py`와 `scripts/chart_card.py`가 판단일을 정한 직후 호출. 우회 옵션 없음(장중에 보고 싶으면 `--date`로 전일 지정). 18:00 값이 확정되면 `normalization.py` 한 곳만 바꾸면 됨.
- **테스트**: `tests/test_session_guard.py` 4개(장중 거부·18시 이후/과거일 허용·UTC→KST 변환·미래일/naive 시각), `tests/test_analyst_chart.py` 1개 추가 + 판정 테스트에 negligible 케이스(총 8개). 제 VM(Python 3.10, xgboost 없음)에서 관련 16개 통과, 전체는 재훈 기기에서 확인 필요.
- **재계산 결과 (2026-10-04 19:21)**: 판정 consistent 4 / negligible 6 / inconsistent 11 — 위 (a)의 예상과 정확히 일치. 남은 "과거 경향"은 RSI 과매도 +0.47%p, 60일선 −10% 미만 +0.37%p, 20일 Q1 +0.10%p, 거래량 증가 +0.12%p(왕복 비용 약 0.43%를 넘는 건 RSI 과매도뿐).

64. **당일 값 확정 시각 측정 + 수급·지수 야간 수집 연결 (2026-10-04, 항목 58 미결 (1)(3)) — 모델·전략 변경 없음**

- **배경**: `SESSION_FINAL_TIME_KST`(18:00)는 항목 58의 임시값인데, 지수·수급의 완성 판정과 항목 63의 장중 판단 가드가 모두 이 값에 의존. 또 `nightly_ingest.sh`가 수급·지수를 받지 않아 차트 카드 수급이 10/01에 멈춰 있음.
- **(a) 야간 수집 연결 (구현)**: `nightly_ingest.sh`에 [3/5] 단계 추가 — `ingest_kiwoom_flow_index.py --lookback-days 10`(지수 001·201 + top50 수급, 약 52콜) 매일 실행. 10일을 다시 받으므로 나중에 확정값이 바뀌어도 저장소 병합 규칙(나중 완성값이 이전 완성값 대체, 미완성값은 완성값을 못 덮음)으로 반영됨. 실패해도 다른 단계는 계속(`status=1`만 기록).
- **(b) 확정 시각 probe (구현, 실행 전)**: `scripts/check_session_final_time.py` — `snapshot`이 ka10081(일봉 1페이지)·ka10059(수급)·ka20006(지수)에서 **오늘 행만** 골라 시각별로 저장(`data/raw/kiwoom/session_final_probe/<날짜>/`, 기본 5종목+2지수 = 회당 12콜), `compare`가 필드별 마지막 변경 시각을 보고.
- **측정 계획 (결과 보기 전 고정)**: 거래일 2일(10/5 월, 10/6 화) 각각 15:40~21:30 20분 간격 + 다음 날 아침 1회.
- **판정 규칙 (사전 고정)**:
  1. 두 날·세 API 통틀어 **마지막으로 값이 바뀐 스냅샷 다음 스냅샷 시각**을 "확정 관측 시각"으로 보고, 30분 단위로 올림한 값을 새 `SESSION_FINAL_TIME_KST`로 함(예: 마지막 변경 18:20 → 다음 스냅샷 18:40 → 19:00).
  2. 확정 관측 시각이 nightly 실행 시각(20:00 이후)보다 늦거나, 다음 날 아침 스냅샷에서도 값이 바뀌면 **당일 확정 가정이 깨진 것** → 값을 바꾸지 않고 멈춰서 재훈과 결정(nightly 시각 이동 / 판단을 다음 날 아침 값 기준으로).
  3. 일봉(ka10081)이 NXT(대체거래소, 20시까지) 거래를 포함하는지 여부는 관측 결과로 기록 — 포함하면 20시 이후까지 바뀔 수 있음(규칙 2로 처리).
- **해석 한계**: 2일·5종목 관측이라 지연이 드문 날(시스템 장애 등)은 못 잡음. 규칙 1의 30분 올림은 그 여유분.
- **측정 계획 수정 (2026-10-04, 측정 전, 재훈 사정)**: 10/5는 대체공휴일(휴장)이고, 15:40~21:30 동안 노트북을 켜 둘 수 없음. 그래서 20분 간격 연속 측정 대신 **거래일 2일(10/6 화, 10/7 수) × 2시점**으로 줄임:
  1. 그날 20:30 KST 1회 — cron 자동(`30 20 * * 1-5`, 야간 수집 20:37 직전). 맥은 야간 수집 때문에 어차피 깨어 있어야 하는 시각.
  2. 다음 날 아무 때 1회 — `snapshot --date <그날>`(API 첫 페이지에 그날 행이 들어 있어 시각 제약 없음).
  - **판정 규칙 (수정, 결과 보기 전 고정)**: 두 날·세 API·전 필드에서 20:30 값 = 다음 날 값이면 "20:30에 확정 관측" → `SESSION_FINAL_TIME_KST = 20:30`(원래 규칙 1의 "변경 없는 첫 스냅샷 시각, 30분 단위"와 같은 값). 하나라도 다르면 원래 규칙 2 그대로(값을 바꾸지 않고 멈춰서 재훈과 결정: 야간 수집 시각 이동 / 다음 날 값 기준 판단).
  - **잃는 정보**: 18:00~20:30 사이 언제 확정되는지는 모름. 확정값을 쓰는 곳(지수·수급 완성 판정, 야간 `recommend.py`)은 모두 20:37 이후 실행이라 운용 영향 없음. 대가는 같은 날 18:00~20:30에 `recommend.py`·`chart_card.py`를 수동 실행하면 막히는 것뿐(보수적 방향).
  - 일봉(ka10081)의 NXT(20시까지) 포함 여부는 20:30 값과 다음 날 값이 같은지로만 간접 확인됨(규칙 3).
- **테스트**: `tests/test_check_session_final_time.py` 2개(날짜 행 선택, 순서 섞인 스냅샷에서 마지막 변경 시각·필드).
- **결과**: (측정 후 기록)

65. **레포 전체 감사(2026-10-04, 읽기 전용) 후속 수정 — 작업 체크리스트 (모델·전략·판정 규칙 변경 없음)**

- **배경**: 2026-10-04 Claude가 레포 전체를 읽기 전용으로 감사함(보고서: claude.ai artifact "StockLens 감사 보고서", 노션 제목 `StockLens full repository audit, October 2026`). 핵심 지적: (1) 운용 구성(next_open·top-10·buffer 3.0·best_iteration 9)은 깨끗한 OOS로 평가된 적 없음 — 항목 41의 test는 다른 구성(close 타깃·top_n=2·buffer 없음), dev(2025-09~2026-06)에서 daily IC −0.0041·buffer 순수익 +54.7% < 유니버스 동일가중 +57.6%. (2) forward 판정(IC>0, 차이>0)은 SE≈0.06이라 검정력이 거의 없음. (3) 고정 모델은 실효 feature 4개(`price_to_sma_5`·`return_20d`·`price_to_sma_20`·`high_low_range`), 하루 점수 ≈8종류, 2026-10-02 4~18위 15종목 동점. (4) `recommend.py`는 buffer를 적용하지 않는 스냅샷 top-10. (5) `intraday_ic_diagnostic.py`에 날짜 상한이 없어 재실행하면 forward 분봉을 읽음. (6) 고정 모델 지문이 `best_iteration==9` 하나뿐이고 매 실행 재학습. (7) 문서 불일치 다수.
- **원칙**: forward 데이터를 보지 않는다. 사전등록된 판정 규칙(D2·I6)·전략·파라미터·고정 모델은 바꾸지 않는다. 보고용 추가는 forward를 보기 전에만 하고 여기 기록한다. 판정 규칙 변경이 필요한 것은 "재훈 결정 필요"로 남긴다.
- **체크리스트** (P0 = 결론을 흔드는 문제, P1 = 다음 단계 전):
  - [x] P0-1 forward 우회 경로 차단: `intraday_ic_diagnostic.py`에 날짜 상한(forward 시작 전날) + 분봉 raw를 읽는 스크립트 allowlist 테스트 — `--end`(기본 2026-09-23, forward 이후 거부)·`cap_before_forward()`(라벨 생성 전에 자름), `tests/test_forward_access_guard.py` 5개
  - [x] P0-2 고정 모델 지문: 트리 구조 해시를 `config/frozen_daily_model.json`에 저장, `evaluate_forward_holdout.py`는 불일치 시 forward 읽기 전에 중단, `recommend.py`는 경고 — `run_ml_backtest.frozen_model_fingerprint()`(앞 best_iteration+1개 트리 dump + feature 순서의 sha256), 기록값 `f397507a…f5f6`(best_iteration 9, xgboost 3.4.1, 두 번 학습해 동일 확인). `frozen_model_ok(best_iteration, fingerprint)`. 테스트 4개 추가(지문 결정성·트리 민감도·둘 다 일치 필요·기록 파일 정합)
  - [x] P0-3 top50 forward 분봉 커버리지 재점검(기존 보고서는 core5로 생성됨) — 2026-10-04 실행: 거래일 5일(09-28~10-02) × 50종목 **100%**, 빈 평일 09-24·09-25는 추석 연휴(휴장). `reports/forward_coverage/forward_minute_status.csv` top50 기준으로 갱신
  - [x] P0-4 forward 판정 검정력 정리 + 배포 규칙 보강 — 재훈 승인("배포 조건 강화"). 근거: 판단일 60개 ≈ 비중복 12구간, SE(IC)≈0.06 → 진짜 IC 0.02면 "IC>0" 통과 ≈63%, 진짜 IC 0이어도 50%. 새 규칙: D2·I6 판정은 그대로 기록, "기각되지 않음"은 forward2 후보일 뿐이고 forward2에서도 같은 방향일 때만 운용 반영(항목 53에 주석). `verdicts()` 키 `overlay_deploy` → `overlay_forward2_candidate`, 출력 `DEPLOY:` → `PRODUCTION PATH`/`FORWARD2 CANDIDATE`. 판정값 계산은 불변
  - [x] P1-1 `recommend.py`에 "buffer 미적용 스냅샷" 명시 — docstring + 출력 한 줄("전략과의 차이"). 동작 변경 없음
  - [x] P1-2 forward 보고서에 리밸런싱 위상(시작 offset 0~4) 민감도 추가(해석용, 판정 미사용) — forward를 보기 전에. `evaluate_forward_holdout.py`: `PHASE_OFFSETS=(0,1,2,3,4)`(고정), `phase_offset_part()`, `phase_sensitivity()`, `forward_phase_sensitivity.csv`. 테스트 3개. `diagnose_tie_sensitivity_validation.py --phase-only`로 validation W3(이미 사용한 구간) dry-run:

    | offset | 시작일 | 순누적 | MDD | hit |
    |---|---|---|---|---|
    | 0 (보고 일정) | 2020-01-02 | **+65.0%** | −43.7% | 52.6% |
    | 1 | 2020-01-03 | +63.6% | −41.0% | 55.6% |
    | 2 | 2020-01-06 | **−9.4%** | −43.8% | 49.7% |
    | 3 | 2020-01-07 | +1.4% | −39.4% | 53.2% |
    | 4 | 2020-01-08 | +49.5% | −39.3% | 53.2% |

    **해석(중요)**: 같은 모델·같은 규칙인데 리밸런싱 시작일만 바꿔도 W3 순누적이 −9.4% ~ +65.0%로 갈림. 지금까지 보고한 +65.0%(항목 45·47·55·56)는 다섯 일정 중 최댓값이었음(우연, 일정은 사전에 정해진 엔진 기본값). 비교: 유니버스 동일가중(비용 없음) W3 +43.5%. 즉 W3의 "buffer 전략 흑자" 결론은 일정 하나에 크게 의존하며, 동점 규칙 잡음(항목 51~53, ±18~29%p)과 같은 종류의 경로 잡음이 더 크게 존재함. 판정(IC 기준)에는 영향 없음. W1·W2는 이 스크립트가 고정 모델(W3)만 다뤄 미확인 — 다음 사이클 사전등록에서 위상 평균을 기본 보고값으로 삼는 것을 검토. `reports/tie_sensitivity_validation/validation_phase_sensitivity.csv`
  - [x] P1-3 `split_by_time`에 라벨 purge 옵션 추가(기본 off — 고정 모델 불변, 다음 사이클부터 사용) — `purge_days`(train·validation 각 마지막 N개 거래일 제거). 다음 사이클 사전등록에서 `DEFAULT_TARGET_HORIZON`(5)으로 쓸 것. 테스트 3개
  - [x] P1-4 문서 정합화: 이 파일 1~8절, 항목 55 중복 제거, CLAUDE.md `load_split` 문구, AGENTS 2절·2.3절, README — 1~8절 재작성(빠진 9절 번호 정리: Update Policy를 9절로), 항목 55 앞의 동일 사본 2개 삭제(정리 기록 남김), CLAUDE.md 데이터 로딩·forward 규칙·고정 모델 지문, AGENTS 2절 스냅샷 주석·2.3절 장중 봉 가드 설명, README 현재 상태 절
  - [x] 마무리: 전체 테스트, 변경 파일 목록·`git diff --stat` — 신규 테스트 14개(forward 접근 가드 5, 고정 모델 지문 4, 위상 민감도 3, purge 3; 기존 1개 시그니처 수정), 전체 311 → **325개 통과**(core5·top50 둘 다). 검증: `run_ml_backtest.py` 교차검증 MATCH(+65.0% / −2.2%) + 지문 MATCH, `evaluate_forward_holdout.py` 플래그 없이 실행 시 지문 통과 후 forward 잠금에서 중단(파일 생성 없음)
- **나중 과제(이번 범위 밖, 감사 보고서 14절)**: `recommend.py`를 buffer 보유 상태와 실제로 정합화(보유 상태 파일 설계 필요) / 상장일 이전 행 제외·수정주가 변경 감지(forward 이후) / 모델 해상도·재학습 정책·point-in-time 유니버스·일간 MDD(새 사이클 사전등록) / 운용 코드 `scripts/`→`src/` 이동, `WINDOWS`·비용 단일 출처, 죽은 코드 정리, 의존성·Python 버전 고정 / 분석가 패널·웹·뉴스·DART는 보류.

66. **감사 후속 2단계: 리밸런싱 시작일 진단(W1~W3·dev) + 페이퍼 로그 buffer 보유 재현 + 다음 사이클 사전등록 초안 (2026-10-04~) — 모델·전략·판정 규칙 변경 없음**

- **체크리스트** (재훈 지시 순서: 항목 64 측정 → 위상 진단 → 보유 상태 → 사전등록 초안):
  - [x] (a) 항목 64 측정 계획 수정(측정 전): 10/5 휴장 + 장시간 대기 불가 → 10/6·10/7 × (20:30 cron 1회 + 다음 날 1회). 규칙은 항목 64에 기록. cron 줄은 재훈이 추가.
  - [x] (b) 리밸런싱 시작일 민감도 W1·W2·W3·dev — `scripts/diagnose_rebalance_phase_validation.py`, 결과 아래.
  - [x] (c) `recommend.py` 페이퍼 로그에 buffer 전략 보유 종목 재현(이전 로그 재생, 상태 파일 없음) — 아래
  - [x] (d) 다음 사이클 사전등록 초안(forward 결과와 무관한 부분만, forward 이후 확정) — 항목 67(초안)
- **(b) 결과 (2026-10-04, validation W1~W3 + dev 보고용, 진단 — 결정 변경 없음)**: 시작일(offset 0~4)을 바꾸면 전략뿐 아니라 유니버스 동일가중(비용 없음)도 크게 흔들림(W3 +43.5% ~ +78.6%) → 시작일별 초과수익으로 비교. offset 0은 항목 55 R0와 3구간 모두 MATCH.

  | 구간 | 전략 순누적 범위(평균) | 유니버스를 이긴 시작일 | 평균 초과수익 |
  |---|---|---|---|
  | W1 2012~2015 | −7.9% ~ +46.3% (+24.5%) | 5/5 | +30.3%p |
  | W2 2016~2019 | +15.9% ~ +70.9% (+34.1%) | 4/5 | +14.9%p |
  | W3 2020~2023H1 | −9.4% ~ +65.0% (+34.0%) | **2/5** | **−25.3%p** |
  | dev 2025-09~2026-06 | +44.5% ~ +85.1% (+67.6%) | 3/5 | +1.6%p |

  - **해석**: 지금까지의 "W3에서 buffer 전략 +65.0% > 유니버스 +43.5%"는 시작일 운. 시작일 평균으로는 가장 최근 validation 구간(W3)에서 유니버스 동일가중(비용 없음, 생존편향 동일)에 뒤지고, dev도 사실상 0. W1·W2는 시작일과 무관하게 대부분 우위 → 신호 감쇠(IC 0.066 → 0.046 → 0.022 → −0.004)와 같은 그림. 전략 비교에서 비용 없는 유니버스와 비교하므로 전략에 불리한 비교임은 감안.
  - **forward 보고서 보강(forward 보기 전)**: `phase_sensitivity()`가 시작일별 `univ_ew_gross`·`excess_vs_univ`도 출력(해석용, 판정 미사용). 테스트 1개 보강.
  - **함의(다음 사이클로)**: 백테스트 수익률은 시작일 5개 평균을 기본 보고값으로 할 것(사전등록 초안 (d)에 반영).
  - 결과: `reports/rebalance_phase_validation/phase_sensitivity.csv`.
- **(c) 결과**: 엔진의 보유 규칙을 `src/backtest/buffered.py::select_held()`·`buffer_rank_limit()`로 분리(엔진 동작 불변 — 회귀 테스트·`run_ml_backtest.py` MATCH·지문 MATCH 확인). `src/portfolio/paper_holdings.py`가 이전 중립 로그(`reports/daily_picks/<YYYYMMDD>.csv`, 전 종목 순위 저장)를 날짜순으로 같은 규칙에 재생 → 판단일 T의 전략 보유 종목. `recommend.py` 중립 실행이 보유 목록(유지/신규, 매도)을 출력하고 로그에 `held_buffered` 열 추가(다음 실행부터; 기존 로그는 수정하지 않음). 기록 간격 9일 초과 시 경고(주 1회 기록 vs 엔진 5거래일 일정 차이). 테스트 7개(첫 단계 = 상위 N, 유지·교체 경계, 입력 순서 무관, **엔진 pass-1과 같은 보유 집합**, 로그 로딩, 간격, 입력 검증), 전체 332개 통과.
  - 확인 실행(`--no-save`, 2026-10-02): 9/28 로그에서 재생 → 10/02 전략 보유 10종목 중 5개가 그날 상위 10위 밖(17·21·22·28·29위 유지), 매도 3종목. 페이퍼 로그의 "추천 top-10"과 평가 대상 전략은 이만큼 다름. 첫 로그(9/28)는 장중 봉으로 만들어진 것(항목 62)이라 재생의 출발점에 그 영향이 남음.

- **(e) 의존성 고정 (2026-10-04)**: `requirements.txt`의 모든 패키지를 현재 `.venv` 버전으로 고정(requests 2.34.2, pandas 3.0.5, numpy 2.5.2, python-dotenv 1.2.3, pydantic 2.13.4, scikit-learn 1.9.0, scipy 1.18.1, xgboost 3.4.1, pytest 9.1.1, matplotlib 3.11.2) + Python 3.14.3 주석. `pip install --dry-run` 결과 설치할 것 없음(환경과 일치). forward 평가 전 업그레이드 금지 — 트리 지문이 바뀌면 forward 스크립트가 멈춤.
- **(f) git 위생 — 재훈 결정: 레거시 31개만 추적 해제(2026-10-04, `git rm --cached`, 스테이징만 — 커밋은 재훈), historical JSON은 유지**: ignore 대상인데 추적 중인 파일 31개(약 51MB: `data/processed/` 레거시 CSV 4개, `data/raw/kiwoom/ka10081/` 초기 원본 27개) + ignore 대상이 아닌 `data/processed/historical/*.json` 51개(약 105MB, 매주 전체 재작성). 결정할 것: 공개 레포의 Kiwoom 데이터 재배포(약관), 재현성(다른 기기 재수집 가능 여부), 레포 크기. 추적 해제는 로컬 파일을 지우지 않음(`git rm --cached`). 이미 공개된 이력은 남음(이력 재작성은 권장하지 않음).
67. **[초안 — 확정 아님] 다음 사이클 사전등록 초안 (2026-10-04 작성, forward 평가 후 재훈과 확정)**

- **지위**: forward 결과(항목 53 경우 A~D)와 무관하게 필요한 것만 미리 적음. forward를 본 뒤 이 초안에서 **빼는 것**은 자유지만, 결과를 보고 **더하는 것**은 그 사실을 명시. 확정 전에는 어떤 실험도 실행하지 않음.
- **왜 지금 써 두나**: 1월에 결과를 본 뒤 계획을 쓰면 계획이 결과에 맞춰짐(항목 53과 같은 이유).

**A. 검정력 현실 (계산, 일별 IC 표준편차 ≈ 0.2·5일 라벨 중첩 가정 — 항목 46과 같은 가정)**

  | holdout 판단일 | SE(IC) | IC>0 통과 확률(진짜 IC 0.02) | 진짜 IC 0.04 | t>1.65 통과(진짜 0.02) |
  |---|---|---|---|---|
  | 60 | 0.058 | 64% | 76% | 10% |
  | 120 | 0.041 | 69% | 84% | 12% |
  | 250 | 0.028 | 76% | 92% | 17% |
  | 500 | 0.020 | 84% | 98% | 26% |

  - 단측 5%·검정력 80%로 확인하려면 진짜 IC 0.02는 판단일 약 3,100개(≈12년), 0.04는 약 770개(≈3년) 필요. **현재 신호 크기(W3 0.022, dev −0.004)로는 50종목 holdout을 아무리 기다려도 통계적 확인이 사실상 불가능.**
  - 결론: 다음 사이클의 holdout은 "신호 증명"이 아니라 "해롭지 않음 + 방향 확인"으로만 설계하고, 검정력은 아래 B·C로 키움.

**B. 검정력을 키우는 설계 후보 (재훈 결정 필요)**
  1. **유니버스 확대**: 날짜별 IC 표준편차는 대략 1/√(종목 수)에 비례 [추론, 근사] → KOSPI200 전체(≈200종목)면 표준편차 ≈ 0.1, 필요한 판단일 약 1/4(IC 0.02 ≈ 3년, 0.04 ≈ 9개월). 대가: 수집량 4배(분봉 포함), 소형주 비용·유동성, point-in-time 구성종목 필요(항목 65 나중 과제, 감사 보고서 P2).
  2. **더 큰 신호를 찾는 쪽**: 수급(항목 58, 2006~) 같은 새 정보원. 단 validation W1~W3는 이미 과다 사용 → 새 feature 선택은 아래 C의 dev에서.
  3. 둘 다 아니면: 현 전략은 페이퍼 트레이딩 + 리스크 확인용으로만 유지하고 "검증된 추천"이라는 표현을 쓰지 않음.

**C. 구간 설계 (forward 평가 후 적용)**
  - 모델 선택용 dev: 지금의 forward(2026-09-24 ~ 평가일)와 분봉 dev·semi 구간(2025-09~). W1~W3는 추가 선택에 쓰지 않고 "과거 국면 일관성" 보고만.
  - holdout: forward2 = 평가일 이후 판단일, 최소 개수는 B의 결정에 따라 A 표로 정함(50종목 유지 시 최소 250, 확대 시 별도 계산).
  - 라벨 purge: `split_by_time(purge_days=5)`, 분봉 구간은 기존 `select_segment` 그대로.

**D. 보고 방식 (모든 백테스트, 판정과 별개)**
  - 수익률은 리밸런싱 시작일 5개(offset 0~4)의 평균·범위를 기본 보고값으로(항목 65·66: 한 일정의 수익률은 −9%~+65%처럼 흔들림). 유니버스 동일가중 대비 초과수익도 시작일별로.
  - 동점 처리 민감도(항목 52) 계속 보고. MDD는 일간 equity 기준 추가(엔진 수정 필요).

**E. 모델·운용 (후보 영역만, 구체 값은 확정 시)**
  - 해상도: 점수 8종류·동점 문제(항목 51). 후보 축은 트리 수/학습률/깊이 조합, 동점 해소 규칙. 결정 기준은 dev의 시작일 평균 지표.
  - 재학습 정책: 고정 모델은 2019년까지만 fit. 후보: 평가 시점까지 확장 학습 + 최근 구간 조기종료, 연 1회 갱신. 새 모델은 반드시 새 지문 기록(항목 65 방식).
  - 데이터: KRX 상장일 이전 행 제외(018260 K-OTC), 수정주가 재계산 감지.
  - 리스크 관리: 항목 55의 관찰(고변동 국면 전용 규칙)을 새 후보로 — validation 결과는 증거로 쓰지 않음(항목 55 그대로).

**F. 결정 (2026-10-06, 재훈 — forward 결과를 보기 전)**
  1. **유니버스: KOSPI200 전체(200종목)로 확대.** 데이터는 항목 68부터 수집 중(일봉·분봉·수급·공시). 과거 구간은 여전히 현재 구성 기준(생존편향), forward2부터는 2026-10-04 고정 구성이라 생존편향 없음.
  2. **forward2: 최종 판정 250거래일(약 1년), 판정 기준 단측 t > 1.65(5%) — "IC > 0" 아님.** 6개월(125거래일)에 한 번 중간 점검하되 "해로움"만 봄(IC가 뚜렷하게 음수면 조기 중단, 통과 판정은 하지 않음 — 여러 번 보는 오판 방지). 근거(계산, 진짜 IC 0.03 가정, 통과 확률 / 신호 없을 때 통과 5%): 200종목 낙관(날짜별 IC 표준편차 0.10) 6개월 44%·1년 68%·2년 91%, 보수(0.13) 31%·49%·75%; 참고로 50종목(0.20)은 1년 28%. 200종목의 실제 표준편차는 미지 → **다음 사이클 시작 시 dev에서 실제 날짜별 IC 표준편차를 재고 이 표를 다시 계산해 기간을 확정**하는 단계를 사전등록에 포함(표준편차는 성과와 무관한 값).
  3. **화면 문구: 지금 "모델 참고 순위"로 낮춤** — 항목 77. 결과를 본 뒤 바꾸면 결과에 맞춘 결정이 되므로 forward 전에 결정.

**F-0. 원래 미결 질문 (기록용)**
  1. B-1(유니버스 확대)로 갈지 — 수집·저장 부담과 일정.
  2. forward2 최소 판단일 수와 그 기간 동안의 운용 원칙(페이퍼만?).
  3. 현 전략의 사용자 노출 문구를 "검증 진행 중 참고 순위"로 낮출지.

68. **KOSPI200 전체 수집 확장 — 데이터 확보만 (2026-10-04, 재훈 결정) — 모델·전략·forward 평가 변경 없음**

- **목적**: 항목 67의 검정력 문제(50종목·IC 0.02 → holdout 약 12년) 대비. 날짜별 IC 표준편차는 대략 1/√종목 수 → 약 200종목이면 필요한 판단일 약 1/4(근사). 분봉(ka10080)은 API가 약 1년치만 주므로, 다음 사이클에서 확대를 결정해도 그때는 지난 분봉을 받을 수 없음 → 수집만 지금 시작.
- **사용 금지 범위(사전 고정)**: 추가 종목 데이터는 현재 사이클(항목 46~67)의 어떤 실험·판정·운용에도 쓰지 않음. forward 평가(`evaluate_forward_holdout.py`), 페이퍼 로그(`recommend.py`), 분봉 dev/semi 재현은 top50 그대로. 확대 유니버스를 쓰는 실험은 항목 67 확정 시 새로 사전등록.
- **생존편향**: 구성종목을 2026-10-04 시점으로 고정하고 앞으로 쌓는 데이터(forward2 이후)는 생존편향 없음. 과거 구간(일봉 2002~, 분봉 2025-09~)은 여전히 현재 구성 기준이라 편향 있음.
- **체크리스트**:
  - [x] (a) 보호 장치: 분봉 점수 z-score를 평가 대상 종목(데이터셋 종목)으로 거른 뒤 계산(`build_scores`), `intraday_ic_diagnostic.py`도 유니버스로 거름 — 추가 종목이 top50 결과를 바꾸지 못하게. "추가 종목이 있어도 top50 점수 불변" 테스트 — `build_scores()`가 데이터셋 종목으로 거른 뒤 z-score, `build_panel(codes=)`, `intraday_ic_diagnostic.py --universe`(기본 top50). 테스트 1개. 변경 전 분봉 폴더·패널은 정확히 top50이라 기존 dev·semi 결과 불변
  - [x] (b) 유니버스 파일 `config/universe_kospi200.json`(ka20002 KOSPI200 구성종목, 우선주 제외 전부) + `get_universe("kospi200")` — 2026-10-04 `build_universe.py --top 200`, 200종목(top50 전부 포함). 영숫자 코드 2개(`0126Z0` 삼성에피스홀딩스 시총 9.1조, `0220W0`) → 분봉 수집·`build_panel`의 코드 정규식을 KRX 6자리 영숫자(`[0-9A-Z]{6}`)로 확장. 테스트 2개(상위집합, 코드 형식)
  - [x] (c) 야간 수집: 분봉·일봉·수급은 수집 유니버스(기본 kospi200, top50 포함 상위집합), 추천·커버리지 점검은 top50 그대로 — `nightly_ingest.sh`: `STOCKLENS_COLLECT_UNIVERSE`(기본 kospi200)를 1~3단계에만 적용, `STOCKLENS_UNIVERSE=top50`은 5단계(추천)용으로 유지. 야간 API 호출 약 4배
  - [x] (d) 초기 백필: 추가 종목 분봉 약 1년 + 일봉 전체 이력 + 수급 — 2026-10-04 재훈 터미널에서 실행(분봉은 Claude 실행분 66종목 이어받음). 결과: 분봉 200/200 폴더, 수급 150/150, 일봉 149/150. 영숫자 코드 `0126Z0`(일봉 2025-11-24~)·`0220W0`(2026-08-25~) 정상 수집. **실패 1건: 018880(한온시스템) 일봉 — "Low price exceeds open or close on 2001-12-18"**: `LEGACY_OHLC_TOLERANCE_BEFORE`(2000-01-01) 이후의 OHLC 불일치라 종목 전체 거부, raw도 저장 안 됨. 미결(아래).
  - [x] (e) git: 추가 종목의 processed 파일은 레포에 올리지 않음(.gitignore), top50 historical은 기존대로 — `.gitignore`에 추가 종목 historical 149개 명시(035720은 이미 추적 중이라 제외). index/investor_flow 폴더(약 560MB, API로 재수집 가능)는 `.gitignore`에 추가해 레포에 올리지 않음(2026-10-04)
  - [x] (f) 전체 테스트, 운용 경로 MATCH·지문 MATCH 재확인, 문서 — 335개 통과, `run_ml_backtest.py` MATCH(+65.0% / −2.2%)·지문 MATCH. **분봉 폴더 200종목 상태에서 dev 재현**: 원본 재구성 vs 저장 패널 실행 차이 5e-16(추가 종목 영향 0). 기존 `dev_results.csv`와는 6.3e-8 차이가 있으나 저장 패널로 돌려도 같은 값 → 이번 변경과 무관(그 사이 일봉 갱신, 예: 207940 수정주가 재계산·항목 62로 추정), IC 판정과 무관한 크기.
- **018880 일봉 — 재훈 결정(2026-10-04): 선택지 (2) 적용.** `LEGACY_OHLC_TOLERANCE_BEFORE = date.fromisoformat(TRAIN_START_DATE)`(2002-10-29, `src/data/dataset.py` 단일 출처에서 import). 테스트 1개(기준일 = 학습 시작일, 2001-12-18 봉은 버리고 2002-10-29 봉은 여전히 거부), 336개 통과, `run_ml_backtest.py` MATCH·지문 MATCH. 저장 데이터는 다음 수집부터만 영향(top50·지수는 2000년 이후 불일치 봉이 없어 동일). 018880 재수집은 재훈 터미널에서. 아래는 결정 전 기록 — 선택지 (1) 그대로 둠: 이번 사이클에서 쓰지 않는 종목이라 영향 없음, 대신 매주 금요일 야간 일봉 단계가 이 종목 실패로 `status=1`을 남김. (2) `LEGACY_OHLC_TOLERANCE_BEFORE`를 학습 시작일(2002-10-29, `TRAIN_START_DATE`)로 옮김: 모델이 쓰지 않는 구간의 불일치 봉만 버리는 같은 원칙(항목 29). top50은 2000~2002년에 불일치 봉이 없어(엄격 검증 통과) 저장 데이터·고정 모델 불변 — 단 018880에 2002-10-29 이후 불일치가 더 있으면 여전히 실패. 재훈 결정 대기.
- **018880 재수집 (2026-10-04, 재훈 터미널)**: 기준일 변경 후 `ingest_kiwoom_daily_chart_batch.py 018880` → 성공, 1996-07-31~2026-10-02 7,547봉. 이로써 일봉 200/200. (`.gitignore` 대상이라 레포에는 없음.) 항목 65~68은 커밋 `ee63aee`로 push됨.

69. **퀀트 카드 JSON 출력 (2026-10-05) — 모델·전략 변경 없음 (제품 레이어, 실험 아님)**

- **목적**: AGENTS.md 43절 1단계 "Quant + Chart 카드" 중 퀀트 카드를 JSON으로 남김. 차트 카드(`src/analysts/chart.py`, `<code>_chart.json`)는 이미 있음. 나중에 Streamlit 뷰어가 이 JSON들만 읽도록 하려는 것(뷰어는 이번 범위 아님).
- **구현**: `src/analysts/quant.py` — `build_quant_card(...)`(순수 함수: 학습·예측·파일 IO 없음, `recommend.py`가 이미 계산한 값만 배치), `write_quant_card(card, out_root)` → `reports/analyst_cards/<YYYYMMDD>/<code>_quant.json`(`ensure_ascii=False, indent=1, allow_nan=False`). `scripts/recommend.py`: 중립 + 저장 실행일 때만 그날 점수가 매겨진 전 종목(약 50개)의 카드를 씀(`should_write_cards(profile, no_save)`), `--cards-out`(기본 `reports/analyst_cards`), 저장 후 "카드 저장: … (N개)" 한 줄.
- **JSON 스키마 v1**: 공통 키 `card`("quant"), `layer`("recommendation"), `used_by_model`(true), `stock_code`, `name`, `decision_date`(ISO) / `schema_version` / `model`{`best_iteration`, `fingerprint_match`} / `ranking`{`rank`, `n_stocks`, `percentile`, `score`, `score_note`(예상 수익률 % 아님), `tie_size`, `tied`, `tie_rule`(점수 동점이면 종목코드 오름차순)} / `drivers`[전 feature: `feature`, `label`, `value`, `value_text`(`format_feature_value`), `contribution`, |기여| 내림차순 — 앞 3개가 top3] / `bias` / `shap_check`{`sum_minus_score`} / `strategy`{`held_buffered`, `status`(유지/신규/null), `rule`} / `validation_status`(forward 평가(2027-01) 전 — 표본 밖 성과 미확인) / `disclaimer`(투자 권유 아님). NaN·inf → null.
- **중립만 쓰는 이유**: 카드는 모델 순위 = 추천 층의 기록. 프로필 실행은 순위가 성향 기울기로 바뀌므로 카드를 쓰지 않음.
- **바꾸지 않은 것**: 콘솔 출력·rows·`reports/daily_picks` CSV 저장 코드(변경 줄은 지문 검사 조건 1줄 — 같은 조건을 `model_ok` 변수로 담아 카드에 기록, 출력 동일), 고정 모델, 순위·동점 규칙, buffer 로직, requirements.
- **순서**: 카드 쓰기는 장중 가드 → TreeSHAP 합 검사(1e-4, 실패 시 중단) → (지문 검사, 경고만) → 콘솔 출력·CSV 저장 이후. 지문 불일치는 실행을 막지 않고 카드 `model.fingerprint_match=false`로 기록(기존 `recommend.py` 동작이 경고만이라 그대로 따름).
- **테스트**: `tests/test_analyst_quant.py` 6개(공통 키·층, 기여합+bias = 점수·정렬·전 feature, NaN/inf → null·엄격 JSON, 동점·보유 없음, 저장·재로딩(tmp_path), 카드 쓰기 조건). 전체 336 → **342개 통과**.
- **미확인**: 실제 `recommend.py` 실행 경로(카드 쓰기 블록)는 돌리지 않음(재훈이 직접 실행 — 페이퍼 로그를 만들지 않기 위해). 블록은 위 순수 함수와 조건 함수만 테스트됨.
- **다음 단계**: Streamlit 뷰어(퀀트·차트 카드 JSON 읽기만). **`.venv`에 streamlit 설치 금지** — requirements 고정·트리 지문 때문. 별도 venv에서 실행. 뷰어 조건은 앞서 합의한 것(forward 구간 실현 수익 표시 금지, 검증 상태 배너, UI에서 재계산 금지)을 항목 70으로 기록 후 진행.


70. **Streamlit 분석가 패널 뷰어 1차 (2026-10-05, 재훈 결정: 50종목 전부·전문가는 탭) — 모델·전략 변경 없음 (제품 레이어)**

- **목적**: AGENTS.md 43.8 5단계 "Web UI: simple first (Streamlit) reading the per-stock JSON". 항목 61의 아이디어(종목을 고르면 전문가별 분석을 클릭해서 봄)를 퀀트·차트 카드 JSON 위에 구현.
- **고정 조건 (만들기 전)**:
  1. 읽기 전용: `reports/analyst_cards/<T>/<code>_{quant,chart}.json`과 `data/user_profile.json`만 읽음. 점수·순위·보유를 다시 계산하지 않음.
  2. **forward 성과 비노출**: 가격·수익률·손익·백테스트를 읽거나 계산하지 않음(가격 파일 미접근을 테스트로 고정). 페이퍼 로그의 forward 구간 성과를 화면에서 보지 않게 하기 위함.
  3. 검증 상태 배너 상시 표시(퀀트 카드의 `validation_status`, `disclaimer`).
  4. 두 층 분리(AGENTS 43.1): 퀀트 탭 = 추천 층, 차트·시장·공시 탭 = "참고 정보 — 모델 미사용" 라벨. 종합 점수 없음, 의견 충돌은 그대로(43.5).
  5. 설문 성향은 참고 탭 순서만 바꿈(43.6): 공격형 차트 먼저, 안정형 시장·공시 먼저. 퀀트 탭은 항상 첫 번째.
  6. 개인·로컬 사용(43.7). 공개 배포는 규제 확인 전 금지.
  7. 환경: Streamlit은 별도 venv(`.venv-ui`)에만. `.venv`(고정 모델 환경, requirements 고정)는 건드리지 않음.
- **구성**: 데이터 로직 `src/ui/viewer_data.py`(Streamlit import 없음, `.venv`에서 테스트), 화면 `app/viewer.py`(얇은 Streamlit), 차트 카드 50종목은 `chart_card.py --from-picks 50`(야간 수집 5단계에 추가).
- **체크리스트**:
  - [x] viewer_data + 테스트(카드 로드, 보유·상위 목록, 성향별 탭 순서, 가격 데이터 미접근) — `src/ui/viewer_data.py`, `tests/test_ui_viewer_data.py` 8개(가격·수익률·백테스트·페이퍼 로그 관련 이름이 뷰어 코드에 없음을 검사)
  - [x] app/viewer.py — 사이드바(판단일, 성향 = 참고 탭 순서만), 배너(검증 상태·투자 권유 아님·지문 불일치 경고), 전략 보유 종목(유지/신규)·모델 순위 상위 10(동점 표시), 전 종목 선택 → 탭 4개(퀀트=추천 / 차트·시장·공시=참고, "모델 미사용" 라벨). 시장·공시 탭은 "준비 중". 설문 결과가 추천 불가면 추천을 보여주지 않음(항목 57). `STOCKLENS_CARDS_ROOT` 환경변수는 시험용
  - [x] 야간 수집에 차트 카드 50종목 — `nightly_ingest.sh` 5단계: `recommend.py` 다음 `chart_card.py --from-picks 50`
  - [x] `.venv-ui` 설정 방법·실행 명령, `.gitignore` — `requirements-ui.txt`(streamlit, python-dotenv 1.2.3, requests: `chart.py` → `src.data` 패키지 → API 클라이언트 모듈 import 때문, 호출·키 로딩 없음). 설치 확인: streamlit 1.65.0, `.venv`는 requirements와 그대로 일치(streamlit 없음)
  - [x] 전체 테스트, 문서 — 351개 통과. 헤드리스 확인(`streamlit.testing.v1.AppTest`, 합성 퀀트 카드 3개 + 실제 차트 카드 1개): 예외 없음, 탭 4개, 종목 변경·안정형 탭 순서 정상. **부수 수정**: 항목 68에서 `normalization.py`가 `dataset.py`를 import해 생긴 순환 import(`import src.features.engineering`가 첫 import이면 실패)를 발견 → import 제거, 기준일 `date(2002, 10, 29)` + 기존 동일성 테스트로 단일 출처 유지, 새 프로세스 import 테스트 1개 추가
- **레이아웃 변경: 탭 → "전문가 박스" (2026-10-05, 재훈 지시, UI만 — 모델·전략·카드 JSON 불변)**: 항목 61 원래 아이디어("전문가를 클릭하면 각자 분석")에 맞춤.
  - 페이지 단위 **시장 전문가** 박스(종목과 무관한 환경 카드, 현재 "준비 중") → 보유/상위 10 목록 → 종목 선택 → 종목별 박스 가로 배치(`st.columns` + `st.container(border=True)`): **퀀트(추천)** 항상 첫 번째, **차트·공시/뉴스(참고)** 순서만 성향으로(공격형 차트 먼저, 안정형 공시 먼저 — AGENTS 43.6).
  - 각 박스: 이름, 층 배지(파랑 "추천" / 회색 "참고 · 모델 미사용 · 추천 이유 아님"), 한 줄 요약, "자세히"(`st.expander`)에 기존 탭 내용 그대로. 배지 색은 층 구분만 — 판정 방향 색·종합 점수·"N명 긍정" 집계 없음(43.5).
  - 요약 규칙(`src/ui/viewer_data.py` 순수 함수): `quant_summary`(카드 값 그대로 "순위 r / n · 백분위 · 전략 보유 상태"), `chart_summary`(판정별 개수만 — 특정 상태명 없음, 43.3), `not_built_summary`. `box_order`/`box_layer`가 `tab_order`를 대체(같은 의미: 퀀트 첫 번째, 성향은 참고 순서만), 시장은 `PAGE_BOXES`. 미사용 `REFERENCE_LABEL` 삭제.
  - 테스트: 탭 순서 테스트 → 박스 순서 테스트로 교체(시장은 종목 박스에 없음, 층 구분 포함) + `chart_summary`(개수 합 = 상태 수, 상태명 미포함) + `quant_summary`(카드 숫자 일치) + 준비 중 박스. 뷰어 테스트 8 → 11, 전체 **354개 통과**.
  - 헤드리스 확인(AppTest, 임시 폴더 샘플 카드 — `reports/` 미사용): 예외 없음, 탭 0·"자세히" 펼치기 2개, 박스 순서·배지, 안정형 순서, 차트 카드 없는 종목 모두 정상.
- **미확인**: 실제 퀀트 카드(재훈의 `recommend.py` 실행 후)로 본 화면은 아직 없음. 첫 실행 뒤 `chart_card.py --from-picks 50`까지 돌리고 뷰어로 확인 필요.


71. **`recommend.py` 페이퍼 로그 덮어쓰기 가드 + `--cards-only` (2026-10-05, 재훈 지시) — 모델·전략·순위 규칙 변경 없음 (실험 아님)**

- **배경**: `recommend.py`가 `reports/daily_picks/<T>.csv`를 존재 확인 없이 씀. 일봉은 금요일에만 갱신되므로 주중에 카드용으로 돌리면 판단일이 직전 금요일(10/02)로 잡혀 페이퍼 로그(사전등록 전략의 기록)를 덮어씀. 뷰어(항목 70)용 카드를 로그 없이 만들 경로도 필요.
- **확인 결과**: (1) `buffered_holdings()`는 **T 이전 로그만** 재생(`load_logged_rankings(before=T)`, `trade_date < T`) — T의 순위는 재계산 값. 그래서 `--cards-only`에서 재계산 순위가 로그와 같은지 검사하는 것이 의미 있음. (2) `20261002.csv`에는 `held_buffered` 열 **없음**(항목 66 이전 생성, 열: trade_date, rank, stock_code, name, score, tie_size, top_drivers, profile, personalized_score). `20260928.csv`는 profile 열도 없음.
- **구현** (`scripts/recommend.py`, 순수 함수 + main은 호출만):
  - 판단일 T와 장중 가드를 **학습 전으로** 옮김 → 중립·저장 실행에서 `<T>.csv`가 있으면 학습 전에 중단(종료 코드 **3**, 아무것도 안 씀, 강제 옵션 없음). 프로필 실행 동작은 그대로.
  - `--cards-only`(중립 전용, `--profile`·`--no-save`와 같이 쓰면 종료 코드 **2**): CSV는 절대 쓰지 않고 퀀트 카드만. 장중 가드·TreeSHAP 검사·지문 검사는 그대로. `--date`와 함께 사용 가능. `<T>.csv`가 있으면 종목별 rank·score(허용 1e-9)·종목 구성(+로그에 있으면 held_buffered)을 비교 → 하나라도 다르면 카드를 쓰지 않고 종료 코드 **4**. 로그 없는 판단일은 경고 후 씀. 기존 카드를 덮어쓴 개수 출력.
  - 함수: `cli_error`, `existing_log_path`, `log_exists_message`, `should_write_csv`, `should_write_cards(profile, no_save, cards_only)`, `compare_with_log(day, log, held) -> (차이 목록, held 비교 여부)`, `holdings_note`.
  - 퀀트 카드: 선택 필드 `strategy.note`(`--cards-only`일 때만: "로그에 보유 기록 없음 — 이전 로그를 재생한 보유" / "페이퍼 로그 없는 판단일 — …" / "로그의 보유 기록과 일치"). `schema_version`은 1 유지, 뷰어는 있으면 상세에 표시(없어도 동작).
  - `nightly_ingest.sh`: `recommend.py` 종료 코드 3 → 실패가 아니라 "recommend: skipped (log exists)", 차트 카드 단계는 그대로 실행.
- **바꾸지 않은 것**: 고정 모델, 순위·동점 규칙, buffer 로직, CSV 컬럼·포맷, 기존 콘솔 문구(추가 줄만), 기존 `reports/daily_picks/` 파일.
- **테스트**: `tests/test_recommend_log_guard.py` 8개(로그 있으면 **학습 전** 종료 코드 3·파일 불변 — 학습 함수가 호출되면 실패하도록 대체, 로그 없으면 통과, 옵션 조합 거부·종료 코드 2, CSV 쓰기 조건, 비교: 동일·1e-12 허용·rank/score/종목 구성 검출·held 열 유무, 야간 스크립트 분기 문자열) + `tests/test_analyst_quant.py` 1개(note 선택 필드). 전체 354 → **363개 통과**. 뷰어 헤드리스 예외 없음.
- **미확인**: `--cards-only` 실제 실행(학습 포함 전체 경로)은 재훈이 직접 실행. 10/02 재계산 순위가 로그와 같은지는 그때 판정됨 — 그 사이 데이터 변경(예: 207940 수정주가 재계산, 항목 62)으로 점수가 달라지면 종료 코드 4가 정상 동작. 야간 스크립트의 종료 코드 분기는 문자열만 테스트(셸 실행 테스트 없음).
- **실제 카드 확인 (2026-10-05, 읽기 전용 — 코드 변경 없음)**: 재훈이 `recommend.py --cards-only --date 2026-10-02`(exit 0)와 `chart_card.py --from-picks 50` 실행 후, 파일만 읽어 검증. 항목 70·71의 "미확인(실제 카드로 본 화면)" 닫음.

  | # | 확인 | 결과 | 근거 |
  |---|---|---|---|
  | 1 | 카드 파일 | 통과 | `reports/analyst_cards/20261002/` 퀀트 50·차트 50, 퀀트 종목 집합 = `20261002.csv` 종목 집합, 차트 없는 종목 0 |
  | 2 | 퀀트 카드 ↔ 로그 | 통과 | rank 불일치 0, score 불일치 0(최대 차이 9.4e-17), tie_size 불일치 0 |
  | 3 | 카드 내부 정합 | 통과 | 기여합+bias−score 최대 1.56e-9(직접 재계산 = 카드 `shap_check`, 기준 1e-4), fingerprint_match 전부 true·best_iteration 9, `strategy.note` 50개 전부 "로그에 보유 기록 없음 — 이전 로그를 재생한 보유", 보유 정확히 10개, drivers 카드당 19개 |
  | 4 | 보유 재생 일관성 | 통과 | 보유 = 1·2·3·4·5위(267250 신규, 000150 유지, 316140 신규, 000270 유지, 000810 신규) + 17·21·22·28·29위 유지(267260, 034020, 298040, 010140, 028260) — 항목 66 (c) 확인 실행과 동일. 매도 3종목은 카드에 이전 보유가 없어 카드로는 확인 불가(항목 66 출력: SK하이닉스·LS ELECTRIC·LIG디펜스앤에어로스페이스) |
  | 5 | 뷰어 헤드리스(AppTest, 실제 카드 폴더, 실제 설문 = 중립·추천 가능) | 통과 | 예외 0, 판단일 목록 [2026-10-02], 보유 목록 10행·상위 10 목록 10행, 배너에 validation_status·disclaimer, 박스 순서 중립·공격형 퀀트→차트→공시 / 안정형 퀀트→공시→차트, 50종목 전부 순회 예외 0. 차트 카드 없는 종목 처리는 실제 데이터에 해당 종목이 없어 샘플 카드 시험(항목 70)으로만 확인 |
  | 6 | 화면 문구 | 통과 | 퀀트 요약 = 카드 값 50/50, 차트 요약 판정별 개수만(상태명 없음) 50/50(서로 다른 요약 10종), `strategy.note` 상세 표시 50/50, 시장 박스 50/50 |

72. **공시 전문가(공시 카드) 1차 — 설계 (2026-10-05, 만들기 전 고정) — 모델·전략 변경 없음 (제품 레이어, 참고 층)**

- **목적**: AGENTS.md 43.8 2단계. 분석가 패널의 "공시·뉴스 전문가" 박스를 실제 내용으로(1차는 공시만, 뉴스는 키 발급 후). 43.2: "recent filings (OpenDART list, filtered by category, corrections flagged) ... original link. Summaries only".
- **보여 줄 것**: 판단일 T 기준 최근 30일(달력일, T−29 ~ T) 공시 목록 — 종류별 개수, 정정 공시(`[기재정정]` 등 태그) 표시, 제출인, DART 원문 링크(`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=<접수번호>`). 박스 요약은 "최근 30일 공시 N건 · 정정 k건 · 종류 m개"처럼 개수만.
- **보여 주지 않을 것**: 호재/악재·긍정/부정 판단(검증된 근거 없음, 43.1·43.5), 구조화 재무 수치(DART 재무 API는 point-in-time 아님, 항목 60), 공시 본문 요약(1차 범위 밖).
- **시점**: 목록 API는 접수일만 있고 시각이 없음(항목 60) → 접수일 ≤ T. T 당일 공시가 장 마감 전인지 후인지 구분 불가 — 카드에 명시. 참고 정보라 모델·순위에 영향 없음.
- **분류**: 항목 60의 분류 규칙을 그대로 쓰고, 카드에만 "증권 발행 서류"(증권발행실적보고서·투자설명서·일괄신고서 류 — 006800의 ELS 서류 등) 묶음을 앞에 추가. 조사 스크립트의 분류(항목 60 수치)는 바꾸지 않음. 종류별 표시 이름은 한국어 라벨.
- **구조**:
  1. `src/api/dart_client.py` — 목록(`list.json`, 연속 페이지)·회사코드(`corpCode.xml`) 호출. 키는 `.env` `DART_API_KEY`, 오류 메시지에서 키 제거(조사 스크립트와 같은 방식). 테스트는 네트워크 mock.
  2. `src/analysts/disclosure.py` — 분류 규칙(조사 스크립트에서 이동, 조사 스크립트는 import), `build_disclosure_card`(순수 함수), `write_disclosure_card` → `reports/analyst_cards/<T>/<code>_disclosure.json`(퀀트·차트 카드와 같은 형식, 공통 키 `card="disclosure"`, `layer="reference"`, `used_by_model=false`).
  3. `scripts/ingest_dart_disclosures.py` — 수집 유니버스(kospi200) 공시 목록 증분 수집(`--lookback-days`, 기본 40). raw는 `data/raw/dart/list/<code>/`, 정규화는 `data/processed/disclosures/<code>.json`(접수번호 기준 병합). 회사코드 맵은 `data/processed/dart_corp_codes.json`(30일 지나면 갱신). 둘 다 gitignore.
  4. `scripts/disclosure_card.py --from-picks 50 --date T` — 저장된 목록만 읽어 카드 작성(API 호출 없음).
  5. 야간 수집: 3단계 뒤 공시 목록 증분(매일, 약 200회 호출 — 무료 한도 일 2만 회), 5단계에서 차트 카드 다음 공시 카드.
  6. 뷰어: 공시 박스 요약 + "자세히"에 종류별 개수 표·공시 목록(원문 링크), 데이터 기준일. "준비 중"은 시장 박스만 남음. 뉴스는 여전히 준비 중으로 표기.
- **테스트 계획**: 분류(기존 테스트 유지 + 증권 발행 서류), 30일 창 경계(T 포함·T−30 제외·T 이후 제외), 정정 표시, 개수 합 = 목록 수, 엄격 JSON, 저장 병합(같은 접수번호 중복 없음), API 페이지 처리·키 제거(mock), 뷰어 요약에 판단 문구 없음.
- **체크리스트**:
  - [x] (a) DART 클라이언트 + 테스트 — `src/api/dart_client.py`(`get_filings` 연속 페이지·`last_reprt_at=N`, `get_corp_codes` zip, 오류에서 키 제거), `tests/test_dart_client.py` 5개
  - [x] (b) 분류 이동 + 카드 빌더 + 테스트 — `src/analysts/disclosure.py`(`CATEGORIES` 원본 그대로 이동, 조사 스크립트는 import — 기존 테스트 4개 그대로 통과, 카드 전용 `CARD_CATEGORIES`, 한국어 라벨, `build_disclosure_card`·`write_disclosure_card`), `tests/test_analyst_disclosure.py` 5개(창 경계 T 포함·T−29 포함·T−30 제외·T 이후 제외, 개수 합, 정정, 카드 전용 분류, 판단 단어 없음, 저장)
  - [x] (c) 수집 스크립트 + 저장 + 테스트 — `src/data/disclosures.py`(`DisclosureStorage`: raw 저장, 접수번호 병합, 회사코드 맵 30일 캐시), `scripts/ingest_dart_disclosures.py`(회사코드 없는 종목은 경고만, 실패만 종료 코드 1), `tests/test_disclosure_storage.py` 3개
  - [x] (d) 카드 스크립트 — `scripts/disclosure_card.py`(`chart_card.py`와 같은 판단일·종목 결정, API 호출 없음)
  - [x] (e) 뷰어 공시 박스 + 테스트 — 요약 `disclosure_summary`(개수만), 상세: 기간·수집 시각, 종류별 개수, 공시 목록(DART 원문 링크 열), 주의 문구 3개, "뉴스는 준비 중" 표기. `NOT_BUILT`에는 시장만 남음. 뷰어 테스트 11 → 13
  - [x] (f) 야간 수집 연결, .gitignore, 전체 테스트, 문서 — `nightly_ingest.sh` [3b/5] DART 목록(수집 유니버스, 40일), 5단계에 `disclosure_card.py --from-picks 50`. `.gitignore`에 `data/processed/disclosures/`, `dart_corp_codes.json`. 전체 363 → **378개 통과**
- **실제 API 확인 (2026-10-05, 3종목만)**: `ingest_dart_disclosures.py --only 005930 0126Z0 006800 --lookback-days 40` → 회사코드 맵 3,998개, 3/3 성공(영숫자 코드 0126Z0 매핑됨), 요청 5회. 카드 미리보기(10/02, 저장 안 함): 005930 12건(임원·주요주주 소유 보고 8, 최대주주 관련 3, 기타 1), 006800 108건 중 99건이 "증권 발행 서류"로 묶임(나머지: 5% 대량보유 1, 임원 보고 3, 최대주주 1, 기타 4).
- **미확인**: 전체 200종목 수집과 50종목 카드 저장은 재훈이 실행. 뷰어의 공시 박스를 실제 카드로 본 화면 없음(헤드리스는 다음 확인 때).


73. **뷰어 레이아웃: 요약 박스 + 전체 폭 상세 영역 (2026-10-05, 재훈 결정) — UI만, 카드 JSON·모델 변경 없음**

- **문제(재훈)**: 박스 3개 가로 배치 안에서 "자세히"가 펼쳐져 표가 좁아지고 DART 원문 링크 열까지 옆으로 스크롤해야 함. 새 페이지는 퀀트·차트처럼 내용이 적은 전문가에겐 과함.
- **변경**: 박스는 요약 + "자세히" 버튼만. 누른 전문가의 상세가 박스 줄 **아래 전체 폭 영역 하나**에 표시(한 번에 하나, `st.session_state["expert"]`, 기본 퀀트, 선택된 버튼은 강조). 공시 상세는 표 대신 **공시 제목 자체가 DART 링크**인 목록, 종류별 펼치기(10건 초과 종류는 접힌 상태 — 006800 증권 발행 서류 99건 등). 링크 제목의 `[기재정정]` 같은 대괄호는 이스케이프.
- **버그 수정**: 상세 영역에 `a() if x else b()` 단독 문장을 써서 Streamlit magic이 `None`을 화면에 출력 → if/else로 수정 + 정적 검사 테스트(뷰어 코드에 단독 조건식 문장 없음).
- **함수**: `viewer_data.markdown_link`, `disclosure_groups`(카드 순서·개수 유지, 큰 묶음 접기). 테스트 +3(링크 이스케이프, 묶음, 단독 조건식 검사), 전체 **381개 통과**.
- **헤드리스 확인(실제 카드 폴더, 읽기만)**: 50종목 × 상세 3종(퀀트·차트·공시) 예외 0, `None` 출력 0, 공시 상세 50/50(링크 목록 또는 "공시 없음"), 종목당 공시 묶음 0~5개, 버튼으로 상세 전환 정상.
- 재훈이 이미 실행한 것(확인): 공시 목록 200종목 수집(`data/processed/disclosures/` 200개), 10/02 공시 카드 50개.

74. **시장 전문가(시장 카드) 1차 — 설계 (2026-10-05, 만들기 전 고정) — 모델·전략 변경 없음 (제품 레이어, 참고 층)**

- **목적**: AGENTS.md 43.8 3단계. 43.2: "market environment (ECOS rates/FX, KOSPI, aggregate flows). Market variables are identical for every stock on a date, so this card describes the environment; it does not pick stocks." 뷰어의 페이지 단위 "시장 전문가" 박스를 실제 내용으로.
- **보여 줄 것 (판단일 T 기준, 모두 T 이하 데이터만, 기술 통계만)**:
  1. 지수(Kiwoom ka20006, 이미 수집 중): KOSPI·KOSPI200 종가, 1·5·20거래일 변화율, 200거래일 이동평균 대비 괴리율, 최근 20거래일 실현변동성(연율화).
  2. 금리(ECOS 817Y002): 국고채 3년·10년, 회사채 3년 AA-, CD 91일 — 최근 값과 20거래일 전 대비 변화(bp), 장단기 금리차(10년−3년, bp).
  3. 환율(ECOS 731Y001): 원/달러 매매기준율 최근 값, 5·20거래일 변화율. 매매기준율은 전일 거래로 정해지는 값임을 표시(항목 59).
  4. 대형주 수급(이미 수집 중인 ka10059): top50 합계 외국인·기관 5·20거래일 순매수(억원). "KOSPI200 상위 50종목 합계 — 시장 전체 아님" 명시.
  - 각 값의 데이터 기준일을 함께 표시(신선도).
- **보여 주지 않을 것**: 시장 방향 전망·"위험/양호" 같은 판정, 과거 base rate(1차 범위 밖 — 하려면 사전등록), 종목 추천과의 연결, FRED(T−2 규칙, 항목 59에서 보류).
- **구조**:
  1. `src/api/ecos_client.py` — `StatisticSearch` 일별 시계열(페이지 처리, 키는 URL 경로에 들어가므로 오류 메시지에서 제거). 키 `.env` `ECOS_API_KEY`.
  2. `src/data/macro.py` — ECOS 시계열 저장(raw `data/raw/ecos/<stat>_<item>/`, 정규화 `data/processed/macro/ecos_<stat>_<item>.json`, 날짜 병합 — 나중 값이 대체).
  3. `scripts/ingest_ecos.py` — 5개 시리즈. 처음에는 2000년부터 전체, 이후 `--lookback-days`(기본 30) 증분. 하루 약 5회 호출.
  4. `src/analysts/market.py` — `build_market_card`(순수 함수: 지수 바·ECOS 시계열·수급 목록 → dict), `write_market_card` → `reports/analyst_cards/<T>/market.json`(공통 키 `card="market"`, `layer="reference"`, `used_by_model=false`, 종목 키 없음).
  5. `scripts/market_card.py --date T` — 저장된 데이터만 읽음(API 호출 없음).
  6. 야간 수집: [3c/5] ECOS 증분, 5단계에서 공시 카드 다음 시장 카드.
  7. 뷰어: 페이지 단위 시장 박스 요약(KOSPI 수준·20일 변화, 국고채 3년, 원/달러 — 값만) + "자세히"를 누르면 시장 박스 바로 아래 전체 폭으로 표 4개·데이터 기준일·주의 문구.
- **테스트 계획**: 변화율·이동평균·변동성 계산(합성 시계열 정답), T 이후 값 미사용(T 이후 값을 바꿔도 카드 불변 — 누수 방지 테스트), 데이터 부족 시 None, ECOS 페이지·오류 키 제거(mock), 저장 병합, 엄격 JSON, 판단 단어 없음, 뷰어 요약.
- **체크리스트**:
  - [x] (a) ECOS 클라이언트 + 저장 + 수집 스크립트 + 테스트 — `src/api/ecos_client.py`(페이지, INFO-200 = 데이터 없음, URL 경로의 키 제거), `src/data/macro.py`(`ECOS_SERIES` 5개, 날짜 병합, 빈 값 건너뜀), `scripts/ingest_ecos.py`(처음 2000년부터, 이후 30일 증분), `tests/test_ecos_macro.py` 4개. 실제 첫 수집(2026-10-05): 5/5 성공, 요청 5회, 시리즈당 6,386~6,929개, 최신 10/02
  - [x] (b) 시장 카드 빌더 + 카드 스크립트 + 테스트 — `src/analysts/market.py`(`index_stats`, `series_stats`, `flow_totals`, `build_market_card`, `write_market_card` → `<T>/market.json`), `scripts/market_card.py`, `tests/test_analyst_market.py` 6개(정답 계산, 이력 부족 → None, 금리차·환율·수급, **T 이후 값을 바꿔도 카드 불변**, 판단 단어 없음·엄격 JSON, 데이터 없음)
  - [x] (c) 뷰어 시장 박스 + 테스트 — 페이지 상단 박스 요약(`market_summary`: KOSPI 수준·20일 변화, 국고채 3년, 원/달러 — 값만) + "자세히/접기"로 박스 아래 전체 폭에 지수·금리(+장단기 금리차)·환율·대형주 수급 표와 주의 문구. "준비 중" 헬퍼(`NOT_BUILT`, `not_built_summary`) 삭제 — 남은 준비 중은 뉴스뿐(공시 박스 안 표기). 뷰어 테스트 15 → 17
  - [x] (d) 야간 수집, .gitignore, 전체 테스트, 실제 API 확인, 문서 — `nightly_ingest.sh` [3c/5] ECOS 증분, 5단계에 `market_card.py`. `.gitignore` `data/processed/macro/`. 전체 381 → **392개 통과**
- **실제 데이터 확인 (2026-10-05, 판단일 10/02, 임시 폴더에 카드 작성 — `reports/` 미사용)**: KOSPI 7,003.74(20일 +6.7%, 200일 평균 대비 +10.7%, 20일 변동성 연율 28.8%), KOSPI200 1,109.05(20일 +7.5%), 국고채 3년 3.937·10년 4.365(금리차 42.8bp), 회사채 AA- 4.638, CD91 3.21, 원/달러 1,359.6(5일 −0.03%, 20일 −0.78%), top50 합계 5일 순매수 외국인 −75,457억·기관 −12,225억(10/02, 50종목). 뷰어 헤드리스: 예외 0, 요약·자세히/접기·표 정상, `None` 출력 0.
- **미확인**: `reports/analyst_cards/20261002/market.json`은 재훈이 `market_card.py`로 작성. 브라우저 화면.


75. **뉴스 전문가(뉴스 카드) 1차 — 설계 (2026-10-06, 만들기 전 고정) — 모델·전략 변경 없음 (제품 레이어, 참고 층)**

- **목적**: AGENTS.md 43.8 4단계. 분석가 패널의 "공시·뉴스 전문가" 박스에 뉴스 추가(43.2: "articles, each with the original link. Summaries only; any good/bad reading is labeled as an unvalidated interpretation").
- **API (정정 포함)**: 네이버 검색 API는 **NAVER API HUB로 이관**됨(2026-06-25 출시, 07-31 개발자센터 신규 발급 종료, 2027-06-30 기존 방식 종료 예정). 주소 `https://naverapihub.apigw.ntruss.com/search/v1/news`, 헤더 `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY`, 키는 NCP 콘솔 발급(ID 10자·Secret 40자 형식). 응답 구조(`total`, `items[title, originallink, link, description, pubDate]`)는 기존과 같음. 월 775,000회·50 RPS, 현재 한시 무료. *(Claude가 처음에 "NCP 키라서 잘못 받았다"고 판단한 것은 틀렸음 — 재훈 지적으로 확인·정정.)* `.env` 키 이름은 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET` 유지, `.env.example`에 자리 추가.
- **실제 응답 확인 (2026-10-06 10:24, "삼성전자", 1회)**: 200, `total` 4,483,481, 최신순 100건이 09:36~10:20(**44분 분량**), 제목에 "삼성전자" 포함 33/100, `pubDate` 예 `Tue, 06 Oct 2026 10:20:00 +0900`, 제목·요약에 `<b>` 강조 태그, `link`는 네이버 뉴스(n.news.naver.com) 또는 원문.
- **설계 결정 (위 사실 반영)**:
  1. **기사 수를 지표로 쓰지 않음**: 검색어당 최근 약 1,000건까지만 받을 수 있어 대형주는 하루치도 다 못 모음 → "최근 N일 기사 N건" 같은 개수는 종목 간 비교·시간 비교가 안 됨. 카드는 "수집 시점의 최근 기사 일부"임을 명시.
  2. **관련도 필터**: 제목에 종목명이 들어간 기사만 카드에 표시(태그 제거 후 비교). 그 외 기사는 저장만. 일반 단어와 겹치는 종목명(예: 기아)은 섞일 수 있음을 주의 문구로.
  3. **시점**: 판단 시점 A(T 20:00 KST) 이전 `pubDate`만, 최근 3일(T−2 ~ T 20:00). 과거 기사는 API로 다시 받을 수 없음 → 수집 시작일 이전 판단일 카드는 비어 있을 수 있음(전진 수집만).
  4. **표시**: 최신 기사 최대 20건 — 시각, 언론사 도메인(원문 주소에서), 제목(누르면 기사 링크: 네이버 뉴스 링크 우선, 없으면 원문), 요약 없음(제목만 — 저작권·간결성). 박스 요약은 "뉴스: 최근 3일 제목 일치 기사 k건 표시(수집분 기준)"처럼 수집분 기준임을 함께. 호재/악재·감성 판단 없음.
  5. **수집**: 야간(20:37) top50 종목별 최신순 최대 3페이지(300건), 링크 기준 병합 저장. 하루 약 150회 이하(한도 대비 여유). raw `data/raw/naver_news/<code>/`, 정규화 `data/processed/news/<code>.json`(gitignore).
- **실제 수집 확인 후 보완 (2026-10-06, 카드 만들기 전, 3종목 × 300건)**: 수집 범위 삼성전자 약 3시간(07:36~10:20), 기아 3일, NAVER 5일. 제목 일치 삼성전자 109/290, 기아 74/300, **NAVER 9/300**(국내 기사는 "네이버"로 씀, "NAVER" 검색은 영문 기사까지 섞임). → (1) 종목별 **별칭 표**(언론이 쓰는 이름: 네이버, LG엔솔, 삼성바이오, 한전 등)를 명시적으로 두고 첫 별칭을 검색어로, 모든 별칭을 제목 일치 판정에 사용. 표에 없는 종목은 유니버스 종목명 그대로. (2) 종목당 최대 1,000건(10페이지)으로 늘림 — top50 하루 약 500회(한도 대비 여유). (3) 카드에 실제 수집 범위(가장 이른·늦은 기사 시각)를 표시.
- **구조**: `src/api/naver_news_client.py`(HUB 주소·헤더, 페이지, 오류에서 키 제거), `src/data/news.py`(저장·병합, 태그 제거·HTML 엔티티 복원, pubDate → ISO KST), `scripts/ingest_naver_news.py`, `src/analysts/news.py`(`build_news_card`, `write_news_card` → `<code>_news.json`, 공통 키 `card="news"`, `layer="reference"`, `used_by_model=false`), `scripts/news_card.py`, 뷰어 공시·뉴스 박스에 뉴스 요약·상세 섹션, 야간 수집 연결.
- **테스트 계획**: HUB 헤더·페이지·키 제거(mock), 태그·엔티티 정리, pubDate 파싱, 링크 병합, 시점 경계(T 20:00 이후 제외·T−3 제외), 제목 일치 필터, 판단 단어 없음, 뷰어 요약.
- **체크리스트**:
  - [x] (a) 클라이언트 + 저장 + 수집 스크립트 + 테스트 — `src/api/naver_news_client.py`(HUB 주소·NCP 헤더, 최신순 페이지, 두 키 모두 오류에서 제거), `src/data/news.py`(태그·엔티티 정리, pubDate → ISO, 언론사 도메인, 링크 병합 — 요약문은 저장 안 함), `scripts/ingest_naver_news.py`(검색어 = 별칭 표 첫 이름, 기본 10페이지), `tests/test_naver_news.py` 5개
  - [x] (b) 뉴스 카드 + 카드 스크립트 + 테스트 — `src/analysts/news.py`(`NEWS_ALIASES` 7종목, `window_bounds`: T−2 00:00 ~ T 20:00 KST, 제목 일치만 최신 20건, 실제 수집 범위 `collected_span`, 주의 문구 3개), `scripts/news_card.py`, `tests/test_analyst_news.py` 5개(시점 경계 — 20:01 제외·T−3 제외, 별칭, 표시 상한, 판단 단어 없음, 빈 저장소)
  - [x] (c) 뷰어 + 테스트 — 공시·뉴스 박스 요약 두 줄(공시 개수 / "뉴스: 최근 3일 제목 일치 k건 (수집분 기준)"), 상세를 "공시"·"뉴스" 두 부분으로, 뉴스 제목이 기사 링크, 검색어·수집 범위·주의 문구 표시. "준비 중" 표기 모두 제거. 뷰어 테스트 17 → 18
  - [x] (d) 야간 수집, .gitignore, 전체 테스트, 실제 API 확인, 문서 — `nightly_ingest.sh` [3d/5] 뉴스(top50, 매일 — 지난 기사는 나중에 못 받음), 4단계 백업에 `data/raw/naver_news/` 추가, 5단계에 `news_card.py`. `.gitignore` `data/processed/news/`. 전체 392 → **403개 통과**
- **확인 (2026-10-06)**: 실제 수집 3종목(9회 호출 성공). 판단일 10/02 카드 미리보기: 수집이 10/06에 시작돼 삼성전자·기아 0건(정상 — 지난 기사는 못 받음), NAVER는 시험 수집에 걸린 15건. 뷰어 헤드리스(임시 폴더): 50종목 예외 0, `None` 0, 공시·뉴스 두 부분 표시, 뉴스 링크 15줄. 관찰: 첫 기사가 "10/2 주목할 종목: …NAVER…" 같은 종목 나열 기사 — 제목 일치 필터의 한계(주의 문구에 반영됨).
- **운영**: 의미 있는 뉴스 카드는 오늘 밤(10/06 20:37) 야간 수집부터 쌓이는 기사로, 다음 금요일 판단일(10/09)부터. 맥이 꺼져 있던 날의 기사는 영구히 빠짐(분봉과 같은 성격).


76. **뉴스 카드: 규칙 기반 "이슈 묶기" (2026-10-06, 재훈 결정) — 모델·전략 변경 없음 (제품 레이어, 참고 층, 실험 아님)**

- **배경**: 수집된 기사가 대부분 중복·잡음. 삼성전자 최근 이틀 제목 일치 227건 중 "갤럭시 탭 S12 출시" 한 사건이 50건 이상, 주가·시황 자동기사 32건, 포토·인사 12건. 재훈: 중요한 것만 골라 보고 싶음. LLM 요약 대신 규칙 기반으로 결정(설명 가능, 판단 금지 원칙 유지, 비용 없음 — LLM 요약은 나중에 얹을 수 있음).
- **규칙**:
  1. **잡음 제외**(제목 키워드, 순서대로 첫 일치): 주가·시황 자동기사(장중 시세·등락률·특징주·수급 순매수/순매도 등), 종목 나열(주목할 종목·관련주·테마주), 포토·영상, 인사·부고, 칼럼·사설. 빼지 않고 "제외 N건(종류별)"로 접어 둠 — 펼치면 볼 수 있음.
  2. **같은 사건 묶기**: 제목에서 종목명·[말머리]·문장부호를 지운 뒤 글자 2-gram 유사도(Jaccard)가 기준 이상이면 같은 이슈. 대표 제목은 가장 먼저 나온 기사.
  3. **중요도 = 보도한 매체 수**(서로 다른 언론사 도메인), 같으면 최근 기사 순. "많이 보도됨"이지 좋고 나쁨이 아님.
  4. **종류 태그**(제목 키워드, 최대 2개): 실적, 수주·계약·투자, 자본(자사주·배당·증자), M&A·지배구조, 규제·소송·사고, 신제품·기술, 증권사 의견(목표가 등).
- **기준 조정**: 묶기 유사도 기준과 잡음 키워드는 실제 수집 기사(50종목)를 보고 정함 — 잘못 묶이거나(서로 다른 사건이 합쳐짐) 잘못 빠지는(사건 기사가 잡음으로 분류) 사례를 확인해 아래에 기록. 숫자를 만들어 내는 규칙이 아니라 화면 정리 규칙이므로 사후 조정 금지 원칙(실험용)의 대상은 아님 — 다만 바꿀 때마다 기록.
- **카드 스키마 v2**: `issues`(대표 제목·링크, 첫·마지막 시각, 기사 수, 매체 수, 태그, 같은 이슈 다른 기사 일부), `excluded`(종류별 개수 + 목록). 기존 `articles` 대신. 뷰어는 상위 이슈 10개 + 나머지 접기 + 제외 기사 접기.
- **체크리스트**:
  - [x] (a) 규칙 구현 + 실제 기사로 기준 확인 — `src/analysts/news.py`: `NOISE_RULES`, `ISSUE_TAGS`, `noise_category`, `issue_tags`, `_signature`(종목명·말머리·문장부호 제거 후 글자 2-gram), `cluster_issues`(묶음의 모든 기사와 비교 — 대표 제목 하나와만 비교하면 같은 사건이 갈림)
  - [x] (b) 카드 v2 + 테스트 — `schema_version` 2: `issues`(대표 = 가장 이른 기사, 첫·마지막 시각, 기사 수, 매체 수, 태그 최대 2, 같은 이슈 다른 기사 5개), `n_issues`, `excluded`(종류별 개수 + 목록 최대 100). `tests/test_analyst_news.py` 5 → 7개(잡음 분리, 같은 사건 묶기·매체 수 정렬, 상한·태그)
  - [x] (c) 뷰어 + 테스트, 헤드리스 확인 — 요약 "뉴스: 최근 3일 이슈 N개 · 제목 일치 k건 · 제외 m건 (수집분 기준)", 상세 "많이 보도된 이슈" 상위 10개(매체 수·링크 제목·기사 수·태그·시각) + "나머지 이슈" 접기 + "제외한 기사 m건(종류별)" 접기. 헤드리스(임시 폴더): 50종목 예외 0·`None` 0
  - [x] (d) 전체 테스트, 문서 — 전체 403 → **405개 통과**
- **기준 조정 기록 (실제 수집 기사 50종목, 2026-10-06)**:
  - 처음(유사도 0.35, 대표 제목과만 비교): 같은 사건이 여러 묶음으로 갈림(삼성전자 "용인 과학축제·국가산단" 4개, 기아 "美 분기 판매 50만대" 3개).
  - 묶음의 모든 기사와 비교 + 0.25: 큰 사건이 합쳐짐(삼성 실적 전망 15매체, 기아 3분기 판매 59매체), 무작위 표본에서 다른 사건 혼입 거의 없음. 그래도 기아 "영국 판매 2위" 4개, 한전 "개인정보 노출" 3개로 갈림.
  - 측정: 갈린 같은 사건끼리 유사도 0.09~0.20, 다른 사건 대조 0.00~0.06. 0.18이면 한전 99→120건, 삼성 실적 17→23건으로 합쳐지나 약간 섞임(LG전자 냉각 수주 묶음에 증권사 목표가 기사, 기아 글로벌 판매 묶음에 美 판매 기사). → **0.20으로 결정**(중요 이슈를 보려는 목적상 덜 갈리는 쪽을 택함, 드문 혼입은 주의 문구로).
  - 잡음 규칙 추가: 순위 홍보(`브랜드평판`), 증시 전망(`[마켓`, `증시 전망`, `7000선 안착` 류 지수 수준), 시세 표현 `보합`. 태그 키워드 추가: 판매·수출·점유율(실적·판매), 협약·맞손(계약), 오염·초과·위반(규제·사고).
  - 남은 한계: 표현이 크게 다른 같은 사건은 여전히 갈릴 수 있음, 종목 나열이 아닌 "여러 회사 언급" 기사(예: 3사 비교)는 각 종목에 잡힘, 짧은 이름(LG·SK)은 계열사 기사 포함.

- **버그 수정 (2026-10-06, 재훈 실행 중 발견)**: `scripts/news_card.py`가 v1 키 `card["articles"]`를 읽어 `KeyError` → 출력 줄을 `summary_line(card)`(이슈·제외 개수)로 바꾸고 테스트 1개 추가(v2 카드로 출력 확인). 전체 **406개 통과**. 원인: 카드 형식을 v2로 바꿀 때 스크립트 출력부를 확인하지 않음.

77. **화면 문구: "추천" → "모델 참고 순위" (2026-10-06, 재훈 결정, forward 보기 전) — 모델·전략·판정 변경 없음**

- **근거**: 표본 밖 성과 미확인, 최근 검증 구간 W3에서 리밸런싱 시작일 평균 유니버스 동일가중 대비 −25.3%p(항목 66), 분봉 dev 사실상 0. 이 상태에서 "추천"은 실제보다 강한 표현(항목 67 F-3).
- **구현**: 공통 문구 `src/analysts/notices.py`(`RANK_LABEL` = "모델 참고 순위", `REFERENCE_RANK_NOTICE` = "과거 데이터로 만든 모델의 참고 순위입니다. 표본 밖 성과는 아직 확인되지 않았고(1차 확인 2027년 1월), 최근 검증 구간에서는 시장 평균보다 낮았습니다. 투자 권유가 아닙니다." — 의존성 없음, 뷰어 환경에서도 import 가능). 적용: 뷰어 배너(카드 값 대신 공통 문구)·층 배지("모델 참고 순위" / "참고 · 모델 미사용 · 순위 근거 아님")·제공 불가 안내·사이드바, `recommend.py` 제목·검증 상태 줄, 설문 위험 고지(같은 사실 추가)·프로필 설명·제공 불가 안내, `scripts/survey.py` 안내, 퀀트 카드 `VALIDATION_STATUS`(새 카드부터). 내부 코드 이름·파일 경로·`reports/daily_picks/`는 그대로. 설문 버전은 바꾸지 않음(문항·점수 불변).
- **테스트**: `tests/test_notices.py` 2개(화면 코드 6개 파일의 문자열 상수(독스트링 제외)에 "추천" 없음, 공통 문구에 사실 5가지 포함·설문 고지 반영), `tests/test_survey.py` 문구 1곳 수정. 전체 406 → **408개 통과**. 뷰어 헤드리스: 배너·배지 새 문구 확인.

78. **실험 백로그 정리 — forward 평가 전·후로 할 실험과 준비 작업 (2026-10-06, 재훈과 논의, 계획 목록 — 사전등록 아님)**

- **지위**: 할 일 목록이다. 아래 어느 것도 이 항목만으로 실행하지 않는다. 실행 전에 각각 새 항목으로 **사전등록**(목적, 대상, 구간, 판정 기준, 해석 한계, 구현 계획)한다. 분석가 패널(제품 레이어) 수정은 여기 넣지 않는다.
- **논의 배경 (2026-10-06)**: "test로 이미 검증했는데 왜 미래 데이터를 또 기다리나, 코스닥으로 바로 검증하면 안 되나"라는 질문.
  - test가 다시 못 쓰이는 이유: 모델 가중치는 test를 안 봤지만 **사람이 봤다** — 항목 14·15·30·31·34·41에서 test를 열었고, 그 뒤 타깃(`next_open`)·top_n(2→10)·buffer를 바꿨다. 현재 운용 구성은 깨끗한 표본 밖 평가를 받은 적이 없다(항목 65).
  - 시간 holdout(forward)과 종목 holdout(코스닥·추가 종목)은 **대체재가 아니다**: 종목 holdout은 "top50 우연인가"(일반화)에 답하고, forward는 "앞으로도 통하나"(신호 감쇠 IC 0.066→0.046→0.022→−0.004)에 답한다. 같은 날짜를 쓰는 종목 holdout은 감쇠 질문에 답하지 못한다.
  - forward 평가(2027-01)는 **최종 확인**일 뿐 개발의 관문이 아니다. 평가 후 forward 구간은 바로 다음 사이클 dev가 된다.
  - 외부 의견(ChatGPT, "test로 검증 완료 → 운영 시작")은 "test를 한 번만 열었다"는 전제가 사실과 달라 채택하지 않음. "기다리지 말고 코스닥으로 일반화 검증"이라는 방향은 채택(아래 A1·A2), 단 **고정 모델 1회 점검을 먼저**, 코스닥에서 새 모델 개발(C4)은 그 뒤.

**A. 지금(forward 평가 전, 12월 환경 고정 전까지) — forward 구간을 읽지 않는 것만**

  | # | 내용 | 종류 | 선행 조건 / 결정 필요 |
  |---|---|---|---|
  | A1 | **종목 holdout 점검 ①**: 고정 모델(지문 `f397507a…f5f6`)을 KOSPI200 추가 150종목에 그대로 적용, 1회 | 실험(사전등록) | 항목 68의 "이번 사이클 사용 금지" 해제 — **재훈 결정**. forward2(미래 날짜)는 오염 안 됨 |
  | A2 | **종목 holdout 점검 ②**: 같은 점검을 KOSDAQ150에 | 실험(사전등록) | 상장폐지 종목 데이터 확보 가능 여부(키움) 조사, KOSDAQ150 구성·일봉 수집, 소형주 비용·슬리피지 가정 재검토 |
  | A3 | 엔진에 일간 equity 기준 MDD 보고 추가(항목 67 D) | 엔지니어링 | 기존 숫자 MATCH(`run_ml_backtest.py` +65.0% / −2.2%)·지문 MATCH 확인 |
  | A4 | ~~point-in-time 구성종목(KOSPI200·KOSDAQ150 과거 편입·편출) 이력 확보 가능성 조사~~ **완료(항목 83, 2026-10-08)** | 조사 | — |
  | A5 | ~~수정주가 재계산 감지 스크립트 — 감시·기록만, 데이터 수정 없음(항목 62의 207940 사례)~~ **완료(항목 82, 2026-10-06)** | 엔지니어링 | — |
  | A6 | 다음 사이클 후보 그리드 사전 고정(항목 67 E: 모델 해상도 축, 재학습 정책 후보) — **확정 항목 84 (2026-10-08)** | 설계 | 1월 결과를 보기 전에 고정해야 의미 있음 |

  - **A1·A2 측정 (사전등록 때 확정할 골격)**: 기간별(W1·W2·W3·test 기간 2023-07~2026-09) 날짜별 횡단면 rank IC와 평균·t값, buffer 전략(top-10, buffer 3.0) 비용 반영 순수익을 리밸런싱 시작일 5개 평균·범위로, 같은 유니버스 동일가중 대비 초과수익. 대상 종목만으로 순위를 매김(top50과 섞지 않음).
  - **A1·A2 규칙**: 결과를 보고 고정 모델·운용 경로·forward 판정 규칙을 바꾸지 않는다. 결과는 다음 사이클 설계(유니버스 결정, C4)의 입력. 한 번 보면 그 종목 집합의 과거 구간도 "본 데이터"가 된다.
  - **A1·A2 해석 한계**: 같은 날짜라 시간 안정성은 답하지 못함, 생존편향(특히 코스닥), 학습 분포(대형주 50)와 다름, 분봉 오버레이는 과거 검증 불가(분봉 1년치).
  - 우선순위: A1 → A3·A5 → A4 → A2 → A6. A3·A5는 코드 변경이라 **12월 환경 고정 전에** 끝낸다.

**B. forward 평가 (2027-01 첫 주, 1회)** — 항목 50·53·65 그대로. 이 항목으로 바뀌는 것 없음.

**C. 1월 이후 새 사이클 (항목 67 확정 후, 각각 사전등록)**

  | # | 내용 | 비고 |
  |---|---|---|
  | C1 | 200종목 dev에서 날짜별 IC 표준편차 측정 → forward2 기간 재계산 | 항목 67 F-2, 성과와 무관한 값 |
  | C2 | 모델 해상도 개선(하루 점수 ≈8종류·동점) | 항목 51·67 E |
  | C3 | 재학습 정책(최근 데이터 포함 학습, 연 1회 갱신 등) — 새 모델은 새 지문 | 항목 65·67 E |
  | C4 | 유니버스 비교: 모델 A(코스피만)·B(코스닥만)·C(통합) | A1·A2 결과 뒤, dev에서 선택, 최종 확인은 forward2 |
  | C5 | 새 정보원 feature: 수급(2006~), 공시·뉴스·금리 | dev에서 선택, W1~W3는 일관성 보고만 |
  | C6 | 리스크 관리 새 후보(고변동 국면 전용 규칙) | 항목 55의 validation 결과는 증거로 쓰지 않음 |
  | C7 | 분봉 포함 재학습 | 분봉 2년치(2027-09 이후), 항목 53 경우 B |
  | C8 | 데이터 정리: 상장일 이전 행 제외(018260 K-OTC), `purge_days=5` | 항목 65·67 C·E |
  | C9 | 보고 방식 고정: 시작일 5개 평균·범위, 동점 민감도, 일간 MDD | 항목 67 D |
  | C10 | 포트폴리오 구성: 하위 회피형 vs top-N, 넓은 선택·긴 보유·점수 평활화로 회전율 축소, 비용 차감 편입 문턱, 분위 단조성 보고 | 항목 81 사후 진단 출처(증거 아님), dev·forward2에서 검증 |

**D. 하지 않는 것**
  - test·validation(W1~W3)을 새 선택에 다시 쓰기, 지금 새 데이터(수급·공시·뉴스·금리·추가 종목)로 feature 실험, forward를 여는 새 경로, 잠금 환경변수 켜기.
  - 종목 holdout 결과나 페이퍼 로그를 보고 고정 모델·운용 경로를 바꾸기.

79. **A1 종목 holdout 점검 사전등록(확정): 고정 모델을 KOSPI200 추가 150종목에 1회 적용 (2026-10-06 작성·확정, 항목 78 A1)**

- **지위**: 확정(2026-10-06, 결과 보기 전). 판정 기준·구간·지표·대상은 이후 바꾸지 않는다. 실행은 1회.
- **목적**: 고정 daily 모델(best_iteration 9, 지문 `f397507a…f5f6`)의 순위 신호가 학습·선택에 한 번도 쓰이지 않은 종목(KOSPI200 중 top50 밖 150종목)에서도 나타나는지 본다. 질문은 "top50에 우연히 맞춰진 패턴인가"(종목 일반화)이고, "앞으로도 통하나"(시간 안정성)는 이 점검으로 답하지 않는다(forward 몫, 항목 78).
- **바꾸지 않는 것**: 고정 모델(재학습·튜닝 없음, 학습은 기존대로 top50 train + validation 조기종료), 운용 경로, forward 판정 규칙(D2·I6), top-10·buffer 3.0·비용. 결과가 좋든 나쁘든 운용 경로를 바꾸지 않고, 다음 사이클 설계(항목 67·78 C4)의 입력으로만 쓴다.

**재훈 결정 (2026-10-06 확정 — 둘 다 허용)**
  - 근거(Claude 의견, 재훈 동의): (1) 다음 사이클 유니버스를 200종목으로 확정(항목 67 F)했으므로 1월 이후 이 150종목은 학습 데이터가 됨 → 종목 holdout으로 쓸 수 있는 건 지금뿐. (2) 고정 모델의 best_iteration은 W3 IC로 골랐으므로 W3 판정은 선택 편향이 섞임 → 학습·선택 어디에도 안 쓴 test 기간 날짜가 유일하게 깨끗함. 조건: 환경변수는 이 실행 1회만, top50 test 행은 만들지 않음(아래 구현), 결과가 좋아도 "검증됨" 표현·화면 문구(항목 77) 변경 없음, 시총 분해 외 사후 분해 금지.
  - 원래 질문(기록용):
  1. **항목 68 잠금 해제**: "추가 150종목은 이번 사이클의 어떤 실험·판정에도 쓰지 않음"을 이 점검 1회에 한해 해제할지. 해제해도 forward2(미래 날짜)는 오염되지 않는다. 대가: 이 150종목의 과거 구간(~2026-09-16)은 이후 "본 데이터"가 됨.
  2. **test 기간 날짜 사용**: 주 평가 구간이 daily test 기간(2023-07-01~2026-09-16)이라 `confirm_final_test_use()`를 통과해야 함(`STOCKLENS_CONFIRM_FINAL_TEST=1`, 이 실행 1회). top50의 test 행은 점수를 매기지도 읽지도 않는다(코드·테스트로 강제). 허용하지 않으면 주 평가 구간을 W3로 바꿔야 하는데, W3는 top50 조기종료에 쓴 날짜라 해석이 약해짐(아래 구간 표).

**대상**
  - 종목: `get_universe("kospi200")` − `get_universe("top50")` = 150종목(2026-10-04 구성, 우선주 제외). 영숫자 코드 2개(`0126Z0` 2025-11~, `0220W0` 2026-08~)는 이력이 짧아 feature가 만들어지는 날부터 자동 포함.
  - 순위는 **150종목 안에서만** 매긴다(top50과 섞지 않음). top-10 전략도 150종목 중 상위 10.
  - 날짜별 포함 조건: 그날 점수·라벨이 있는 종목 50개 이상(미만인 날은 IC 계산·전략에서 제외, 제외 일수 보고).
  - 생존편향: 2026-10-04 현재 KOSPI200 구성종목을 과거에 적용 — top50보다 편향이 클 수 있음(중소형 탈락 종목 누락). 결과 수익률은 위로 치우침.

**구간 (전부 보고, 판정은 주 구간 하나로만)**

  | 구간 | 날짜 | 이 모델 입장 | 역할 |
  |---|---|---|---|
  | **주(P)** | test 기간 2023-07-01 ~ 2026-09-16(라벨 purge: 라벨 끝이 2026-09-16 이하) | 학습·조기종료에 안 쓴 날짜 + 안 쓴 종목 | **판정** |
  | 보조(W3) | 2020-01-01 ~ 2023-06-30 | 조기종료에 쓴 날짜(top50), 종목은 처음 | 보고만 |
  | 참고(W1·W2) | 2012~2015, 2016~2019 | 학습에 쓴 날짜(top50), 종목은 처음 | 보고만 — 같은 날짜의 top50 패턴이 섞여 낙관적 |
  - forward(2026-09-24~)와 그 직전(2026-09-17~23)은 읽지 않는다: 데이터셋을 `TEST_END_DATE`로 자른 뒤 라벨 purge.
  - 주 구간 안 연도별(2023H2, 2024, 2025, 2026 1~9월) 평균 IC도 보고(감쇠 확인용, 판정 미사용).

**지표**
  - (1) **날짜별 횡단면 rank IC** (`daily_rank_ic`, 점수 = 고정 모델 `predicted_return`, 라벨 = `target_return_5d`, next_open 진입): 평균, IC>0 비율, 일수.
  - (2) **t값** = 평균 IC / (날짜별 IC 표준편차 / √(일수/5)) — 5일 라벨 중첩을 유효 표본 수 일수/5로 보정(항목 67 A와 같은 가정).
  - (3) buffer 전략(top-10, buffer 3.0, 실제 비용) 순누적·MDD·적중률을 **리밸런싱 시작일 5개(offset 0~4) 평균·범위**로, 같은 150종목 유니버스 동일가중(비용 없음) 대비 초과수익 — `evaluate_forward_holdout.phase_sensitivity()` 재사용.
  - (4) 보조 분해(보고만): 시총 순위 51~100위 / 101~200위(2026-10-04 시총 기준) 각각의 평균 IC.

**판정 (주 구간 P, 지표 (1)(2)만 사용, 결과 보기 전 고정)**

  | 판정 | 조건 | 의미 |
  |---|---|---|
  | **일반화 지지** | 평균 IC > 0 그리고 t > 1.65 | 신호가 top50 밖에서도 통계적으로 확인됨 |
  | **방향만 일치** | 평균 IC > 0, t ≤ 1.65 | 부호는 같으나 확인 안 됨 |
  | **일반화 실패** | 평균 IC ≤ 0 | top50 특이 패턴 가능성 |
  - 수익(지표 3)은 판정에 쓰지 않는다(비용 없는 동일가중과 비교라 전략에 불리, 경로 잡음 큼 — 항목 65·66).
  - 검정력 참고 [추론, 근사]: 날짜별 IC 표준편차를 0.10~0.13(150종목)으로 보면 주 구간 약 790일 → 유효 약 158 → SE ≈ 0.008~0.010. 진짜 IC 0.02면 t ≈ 2 안팎. 즉 이 점검은 forward(SE ≈ 0.06)와 달리 작은 신호도 구분할 힘이 있다. 실제 표준편차는 결과에 함께 기록.

**해석 한계**
  - 시간 안정성 질문에 답하지 않음: 주 구간 날짜는 top50 기준으로 이미 여러 번 본 test 기간이며, 그 기간의 시장 국면(반전 강도)은 150종목과 top50이 공유. "일반화 지지"여도 forward 결과를 대신하지 않는다.
  - 150종목은 top50보다 작고 변동성·비용이 큼 — 단기 반전은 소형주에서 원래 강하므로 IC가 좋아도 비용 후 수익은 별개.
  - 생존편향(위), 구성종목이 2026-10-04 기준(point-in-time 아님, 항목 78 A4).
  - 한 번 실행하면 이 150종목의 ~2026-09-16 구간도 소진된 데이터가 된다. 재실행·추가 분석으로 다른 지표를 찾지 않는다.

**구현 계획 (확정 후)**
  1. `scripts/evaluate_cross_sectional_holdout.py`
     - 순서: top50 데이터셋 → `train_frozen_model()` → `frozen_model_matches()` 불일치면 **추가 종목 데이터를 읽기 전에 중단** → 150종목 일봉 로드(`HistoricalStorage`) → `build_combined_dataset` → `TEST_END_DATE` 이하로 자르고 `split_by_time` → 구간별 예측·지표.
     - test 기간 행을 만들기 직전에 `confirm_final_test_use(CALLER)` 호출. top50 종목의 test 행은 어떤 경로로도 점수 계산 안 함.
     - 1회 가드: 출력 폴더 `reports/cross_sectional_holdout/`에 결과가 있으면 중단(덮어쓰기 옵션 없음).
     - 출력: `summary.csv`(구간별 IC·t·판정), `yearly_ic.csv`, `phase_sensitivity.csv`, `cap_split_ic.csv`, 콘솔에 판정 한 줄.
  2. 순수 함수(테스트 대상): `holdout_codes()`(150개, top50과 교집합 0), `t_stat(ics, horizon=5)`, `verdict(mean_ic, t)`, `eligible_dates(df, min_stocks=50)`, `cap_bucket()`.
  3. 테스트 `tests/test_cross_sectional_holdout.py`: 종목 집합(150·교집합 0), 지문 불일치 시 추가 종목 로더가 호출되지 않음(대체 함수로 확인), 판정 경계(IC 0·t 1.65), t값 합성 데이터 정답, 날짜 상한(2026-09-16 이후 행 없음·라벨 purge), 1회 가드, `select_segment(..., "forward")` 미사용.
  4. 실행 명령(확정·구현 후, 재훈 터미널):
     `STOCKLENS_UNIVERSE=top50 STOCKLENS_CONFIRM_FINAL_TEST=1 PYTHONPATH=. .venv/bin/python scripts/evaluate_cross_sectional_holdout.py`
  5. 결과는 이 항목 아래에 추가 기록(판정·표·해석), 노션 제목 `Frozen model on 150 unseen KOSPI200 stocks`.

- **구현 (2026-10-06, 실행 전)**:
  - `scripts/evaluate_cross_sectional_holdout.py` — 순서: 결과 파일(`reports/cross_sectional_holdout/summary.csv`) 있으면 종료 코드 3(아무것도 안 읽음) → `STOCKLENS_UNIVERSE`가 top50 아니면 2 → top50로 고정 모델 학습(`run_ml_backtest._load_priced_dataset`·`train_frozen_model` 그대로, 지문 재현을 위해 기존 경로 유지) → `frozen_model_ok()` 불일치면 4(추가 종목 미접근) → `confirm_final_test_use()` 실패면 5(추가 종목 미접근) → 150종목 일봉을 `TEST_END_DATE`(2026-09-16)로 **자른 뒤** 데이터셋 생성(`build_stock_dataset`이 라벨 없는 마지막 5행을 버리므로 라벨이 9/16 이후 가격을 읽지 않음) → 이력이 짧아 데이터셋이 비는 종목은 건너뛰고 목록 출력 → 구간 P·W3·W1·W2별로 날짜당 50종목 이상인 날만 → IC·t·판정(P만), `phase_sensitivity()` 재사용 → `summary.csv`(마지막에 저장 = 1회 표시), `phase_sensitivity.csv`, `yearly_ic_P.csv`, `cap_split_ic_P.csv`.
  - top50 test 행: 고정 모델 학습용 데이터셋에는 기존 스크립트처럼 존재하지만 예측·지표 계산 대상이 아님(예측은 150종목 데이터셋에만).
  - 순수 함수: `holdout_codes`, `cap_groups`, `t_stat`(IC 미정의 날 = 0, `summarize_ic`와 같은 규칙), `verdict`, `eligible`, `truncate_bars`, `load_holdout_dataset`, `yearly_ic`, `cap_split_ic`.
  - 테스트 `tests/test_cross_sectional_holdout.py` 12개: 고정 설정, 종목 집합(실제 설정 파일로 150·교집합 0), 시총 그룹, t값 정답·미정의 날, 판정 경계(IC 0, t 1.65), 날짜 필터, 잘라내기·라벨 상한·짧은 이력 건너뜀, 결과 있음 → 3, 지문 불일치 → 4·추가 종목 로더 미호출, 잠금 → 5·미호출, 유니버스 오류 → 2. Claude VM(Python 3.10, xgboost-cpu 3.2)에서 12개 통과 + 가짜 데이터로 전체 흐름 1회(출력·CSV 4개·재실행 차단) 확인. 전체 테스트·실제 실행은 재훈 기기에서.
- **결과 (2026-10-06, 재훈 기기, 1회 실행 — 재실행 불가)**: 지문 MATCH(best_iteration 9), 150종목 중 데이터가 만들어진 종목 148개(시총 그룹 98+50 — 2개는 이력 부족으로 건너뜀, 날짜당 평균 108~144종목), 날짜 제외 0.

  | 구간 | 역할 | 기간 | 일수 | 종목/일 | 평균 IC | IC>0 | IC 표준편차 | t | 판정 |
  |---|---|---|---|---|---|---|---|---|---|
  | **P** | **판정** | 2023-07-03 ~ 2026-09-09 | 777 | 144.4 | **+0.0255** | 55.6% | 0.155 | **+2.05** | **일반화 지지** |
  | W3 | 보고 | 2020-01-02 ~ 2023-06-30 | 865 | 133.4 | +0.0233 | 54.5% | 0.161 | +1.90 | — |
  | W1 | 보고 | 2012-01-02 ~ 2015-12-30 | 988 | 108.6 | +0.0362 | 58.7% | 0.147 | +3.47 | — |
  | W2 | 보고 | 2016-01-04 ~ 2019-12-30 | 979 | 120.2 | +0.0401 | 60.5% | 0.142 | +3.96 | — |

  - P 연도별(보고만): 2023H2 +0.0262 / 2024 +0.0278 / 2025 +0.0156 / 2026(1~9월) +0.0356 — 네 구간 모두 양수, 개별 t는 0.7~1.3.
  - P 시총 그룹(보고만): 150종목 중 상위 50 +0.0278(t 1.74), 나머지 +0.0244(t 1.83) — 크기에 따른 차이 거의 없음.
  - buffer 전략(top-10, buffer 3.0, 실제 비용, 시작일 5개, 보고만):

    | 구간 | 순누적 평균(범위) | 150종목 동일가중(비용 없음) 평균 | 초과 평균(범위) | MDD 평균 | 신규 편입/회 |
    |---|---|---|---|---|---|
    | P | −8.2% (−44.9% ~ +30.6%) | +43.4% | −51.7%p (−83.6 ~ −6.3) | −44.2% | 6.7 |
    | W3 | −23.6% (−43.7% ~ +3.0%) | +31.3% | −54.9%p | −48.5% | 6.6 |
    | W2 | −25.3% (−31.5% ~ −18.1%) | +2.1% | −27.4%p | −42.9% | 6.5 |
    | W1 | +3.9% (−31.3% ~ +31.0%) | +35.0% | −31.0%p | −29.0% | 6.4 |

- **해석**:
  1. **사전등록 판정: 일반화 지지**(IC +0.0255 > 0, t 2.05 > 1.65). 고정 모델의 순위 신호는 학습·선택에 쓰지 않은 KOSPI200 150종목에서도 나타남 → "top50에만 맞춰진 우연한 패턴"일 가능성은 낮아짐. 단 t 2.05는 기준을 조금 넘는 정도이고, t는 일수/5 근사라 IC의 자기상관이 남아 있으면 과대평가될 수 있음.
  2. **감쇠 그림이 top50과 다름(관찰, 판정 아님)**: top50 IC W1 0.066 → W2 0.046 → W3 0.022 → 분봉 dev −0.004(항목 65)인데, 150종목은 W1 0.036 → W2 0.040 → W3 0.023 → P 0.026, P 안 연도별도 모두 양수(2025 +0.016, 2026 +0.036). top50의 최근 소멸은 "신호가 시장 전체에서 사라짐"보다 대형주 50개에 한정된 현상일 가능성을 시사. 기간 정의가 달라(dev 2025-09~2026-06 vs 연도) 직접 비교는 아님. 시간 안정성은 여전히 forward 몫.
  3. **IC는 양수인데 top-10 롱온리 전략은 모든 구간에서 동일가중에 크게 뒤짐**(P −51.7%p, W1~W3 −27 ~ −55%p). 비교 기준이 비용 없는 동일가중이라 불리하지만 크기가 그보다 큼. 회당 신규 편입 6.7종목 × 왕복 비용 약 0.43% ≈ 5일마다 약 0.29%, P 153회면 단순 합 약 44% [추론, 근사] → **비용이 차이의 상당 부분**을 설명. 나머지는 "횡단면 전체 순위 상관은 양수지만 상위 10개 극단에서는 돈이 안 됨"(신호가 하위 회피 쪽에 있을 가능성) 같은 설명이 가능하나 이 점검에서 확인하지 않음(사후 분해 금지 — 아래 다음 사이클로).
  4. **검정력 가정 수정 필요(성과와 무관한 값)**: 150종목의 날짜별 IC 표준편차가 0.14~0.16 — 항목 67 F의 200종목 가정(낙관 0.10, 보수 0.13)보다 큼. 1/√종목 수 근사가 종목 간 공통 움직임 때문에 맞지 않음. 0.155·진짜 IC 0.03 기준 t>1.65 통과 확률은 1년(250일) 약 39%, 2년 약 61% [추론, 근사]. forward2 기간은 항목 67 F-2대로 다음 사이클 시작 시 dev에서 다시 재서 확정하되, 1년으로는 부족할 가능성이 큼.
- **결정에 미치는 영향**: 사전등록대로 고정 모델·운용 경로·forward 판정 규칙·화면 문구(항목 77) 변경 없음. 다음 사이클 입력:
  - 유니버스 200종목 확대(항목 67 F-1)를 지지하는 근거 하나 추가(신호가 추가 종목에서도 존재).
  - **포트폴리오 구성이 약한 고리**: 다음 사이클 사전등록에 분위(예: 10분위) 수익 스프레드, gross vs net 분해, top-N 크기·회전율 제약 비교를 넣을 것(항목 78 C에 추가 후보 — validation이 아니라 dev에서).
  - forward2 기간 재계산(위 4).
- **이 결과로 하지 않는 것**: 150종목 결과를 보고 지표·구간·분해를 추가 계산하지 않음. 이 150종목의 ~2026-09-16 구간은 이제 "본 데이터". — 예외: 항목 81 사후 진단(재훈 결정, 판정 불변·증거 아님).
- 결과 파일: `reports/cross_sectional_holdout/`(summary.csv, yearly_ic_P.csv, cap_split_ic_P.csv, phase_sensitivity.csv).

80. **일간 equity 기준 MDD 보고 추가 (2026-10-06, 항목 78 A3 / 67 D) — 엔진·전략·판정 변경 없음 (보고용 엔지니어링, 실험 아님)**

- **배경**: 엔진은 5거래일 기간마다 한 번 복리 계산하므로 `calculate_performance()['max_drawdown']`은 기간 말 equity만 봄 → 보유 기간 중간의 하락을 놓침. 또 첫 기간의 손실은 running max에 초기 자본이 없어 drawdown으로 잡히지 않음.
- **정의 (`src/backtest/daily_equity.py`, 결과 보기 전 고정)**: 기간 시작 equity E, 포지션 i(가중치 1/top_n, 남는 비중은 현금)에 대해 거래일 d(진입일~청산일)의 가치 = E·(1 + Σ w_i·v_i(d)), v_i(d) = (1 + net_i)·close_i(d)/close_i(청산일) − 1. 청산일 값은 엔진의 기간 수익과 정확히 같고(비용 포함), 중간은 종가 경로를 따름. 기간 사이(청산 종가 → 다음 진입)는 현금 — 엔진과 동일, 그 사이 갭은 반영 안 됨. 하루 봉이 없는 종목은 직전 값 유지. MDD의 시작 고점은 초기 자본(첫 기간 손실 포함).
- **연결 (보고만)**: `evaluate_forward_holdout.py`의 `evaluate()`(daily·overlay 행)와 `phase_sensitivity()`(시작일별)에 `mdd_daily` 열 추가 — forward 데이터를 보기 전 추가, D2·I6 판정 미사용(항목 65의 "보고용 추가는 forward 전에만" 원칙). `phase_sensitivity()`를 쓰는 `diagnose_rebalance_phase_validation.py`·`evaluate_cross_sectional_holdout.py` 출력 CSV에도 열이 생김(재실행하지 않음 — 항목 79는 1회).
- **바꾸지 않은 것**: 엔진(`baseline.py`·`buffered.py`)·거래 기록·`mdd` 값·고정 모델·판정 규칙. `run_ml_backtest.py` 표는 그대로(다음 사이클 보고 방식에서 `mdd_daily`를 기본으로 쓸지 결정, 항목 67 D).
- **테스트**: `tests/test_daily_equity.py` 4개(기본·buffer 엔진 모두 기간 말 일간 값 = 엔진 복리 equity, 최종값 = `total_return`, 일간 MDD ≤ 기간 MDD / 기간 중간 −40% 하락을 일간 MDD가 잡고 기간 MDD는 0 / 빈 입력·첫날 손실), `tests/test_evaluate_forward_holdout.py` 1곳 보강(`mdd_daily` ≤ `mdd`). Claude VM(Python 3.10, pandas 2.3, xgboost-cpu 3.2)에서 전체 408 + 12(항목 79) + 4 = **424개 통과**. 재훈 기기 확인 필요.

81. **항목 79 사후 진단 — P 구간의 점수 분위·buffer 보유·종목별 기여·국면 (2026-10-06, 재훈 요청, 정의는 실행 전 고정) — 판정·모델·운용 변경 없음**

- **지위 (중요)**: **사후(post-hoc) 진단**이다. 항목 79의 판정(일반화 지지)은 그대로이고, 항목 79에 "결과를 보고 지표·분해를 추가 계산하지 않음"이라 적었으나 재훈 결정으로 이 진단을 예외로 추가한다(여기 명시). 목적은 "IC는 양수인데 top-10 전략은 왜 졌나"를 이해하는 것. **여기서 나온 어떤 관찰도 설계 선택의 증거가 아니다** — 아이디어(예: top-N 크기, 롱숏, 회전율 제약)는 다음 사이클에 사전등록하고 dev·forward2에서 검증한다. 150종목의 ~2026-09-16 데이터는 항목 79로 이미 소진됐으므로 이 실행은 같은 행을 다시 읽을 뿐 새 holdout을 쓰지 않음(forward·top50 test 행 미접근, 실행 조건은 항목 79와 동일한 지문·잠금 가드).
- **정의 (실행 전 고정, 모두 P = 2023-07-01~2026-09-16, 날짜당 50종목 이상, 150종목 안에서 순위)**:
  - **A. 점수와 실제 5일 수익**: 날짜별 점수 백분위 순위(동점 평균)로 10분위(D1 최저 ~ D10 최고) — 고정 모델은 하루 점수 종류가 적어 동점이 많으므로 분위 크기가 고르지 않음(하루 평균 고유 점수 수와 분위별 종목 수를 같이 보고). 그룹: D1~D10, top 10%(D10), top 20%(D9+D10), bottom 10%(D1), 엔진의 plain top-10 선택(점수 내림차순, 동점은 종목코드 오름차순), 전체. 수익: `target_return_5d`(T+1 시가 → T+5 종가, 비용 없음) 날짜별 평균과 날짜 평균을 뺀 값, 그 기간 평균과 t(일수/5). long-short = top 10% − bottom 10% 날짜별 차이의 평균.
  - **B. buffer 보유 (보고 일정 offset 0)**: 리밸런싱마다 보유·유지(buffer가 남긴 것)·신규·탈락 수, 유지 종목과 신규 종목의 평균 순위, 유지 종목의 점수 변화(현재 − 진입 시), 유지·신규 포지션 각각의 평균 순수익, 총 교체 수, 보유 기간 분포(중앙값·평균·1기간만 보유 비율).
  - **C. 종목별 기여 (offset 0 상세 + 시작일 5개 요약)**: 종목별 Σ(가중치 × 순수익)(기간 수익의 산술 합 — 복리 총수익과 다름), 가격 변동분(청산가/진입가 − 1)과 비용분으로 분해, 음수 기여 종목 수, 최악 5종목 합과 손실 중 비중, 최악 5종목을 뺀 합, 손실 포지션 비율.
  - **D. 국면 (2023H2 / 2024 / 2025 / 2026, 시작일 5개 평균)**: 평균 IC, buffer top-10 순누적(그 국면 리밸런싱만 복리), 150종목 동일가중(비용 없음), 초과, 리밸런싱당 신규 편입, 기간 MDD와 일간 MDD(항목 80, 국면 시작 equity = 1).
- **해석 규칙 (실행 전 고정)**: 숫자는 기술 통계. 분위·국면·종목을 골라 "이 부분은 된다"는 결론을 운용·판정에 쓰지 않는다. 다음 사이클 후보로 옮길 때는 그 사실과 근거가 사후 진단임을 사전등록에 적는다.
- **구현**: `scripts/diagnose_cross_sectional_holdout.py`(항목 79 스크립트의 로딩·가드 재사용, `_build_held_timeline`·`run_buffered_backtest`·`universe_average_gross`·`daily_max_drawdown` 재사용, 결과 `reports/cross_sectional_holdout/diagnostics/` CSV 6개 + 콘솔). 테스트 `tests/test_diagnose_cross_sectional_holdout.py` 7개(분위 크기·동점은 같은 분위, 엔진 동점 규칙, long-short = top − bottom, 보유: 유지+신규 = 보유·신규 평균 = 엔진 `entries_per_period`, 기여 합·가격 − 비용 = 순, 국면 기간 합 = 전체·초과 정의·일간 MDD ≤ 기간 MDD, 가드 2·4·5). Claude VM에서 7개 통과 + 가짜 데이터로 전체 흐름 1회. 항목 80 patch가 먼저 적용돼야 함(`daily_equity`).
- **결과 (2026-10-06, 재훈 기기 실행, 사후 진단 — 증거 아님)**: P 2023-07-03~2026-09-09, 날짜당 평균 144종목, 하루 고유 점수 수가 적어 분위 크기가 고르지 않음(D1 하루 9종목, D3 32종목; 일부 분위는 동점 때문에 없는 날도 있음).

  **A. 점수 분위별 5일 수익 (비용 없음, 날짜 평균 대비 = 초과)**

  | 그룹 | 종목/일 | 5일 수익 | 날짜 평균 대비 | t |
  |---|---|---|---|---|
  | D1(최저) | 9.1 | −0.09% | **−0.35%** | −0.91 |
  | D2~D4 | 24~32 | +0.05~+0.20% | −0.07 ~ −0.19% | −1.07 ~ −0.26 |
  | D5~D8 | 24~26 | +0.31~+0.54% | **+0.03 ~ +0.16%** | +0.18 ~ +0.77 |
  | D9 | 17.5 | +0.36% | +0.11% | +0.48 |
  | D10(최고) = top 10% | 13.7 | +0.22% | **+0.02%** | +0.11 |
  | top 20% | 27.1 | +0.25% | +0.03% | +0.21 |
  | **엔진 top-10** | 10 | +0.25% | **−0.03%** | −0.16 |
  | 전체 | 144.4 | +0.28% | 0 | — |
  | long-short(top 10% − bottom 10%) | — | +0.30% | — | +0.65 |

  **B. buffer 보유 (offset 0, 154회 리밸런싱)**: 회당 유지 3.4 / 신규 6.6 / 탈락 6.5, 총 교체 1,016회. 포지션의 **67%가 1기간(5일)만 보유**, 보유 기간 중앙값 1기간·평균 1.5기간. 유지 종목 평균 순위 10.7(buffer 한도 30위 안), 신규 4.8위, 유지 종목 점수 변화 ≈ 0. 포지션 평균 순수익: 유지 −0.19%, 신규 −0.24%(둘 다 음수).

  **C. 종목별 기여 (offset 0: 143종목 보유, 1,540 포지션)**: 기여 합(산술) −0.447 = **가격 변동 −0.003 + 비용 −0.444**. 음수 기여 86종목 / 양수 57종목, 손실 포지션 비율 55%, 최악 5종목(이수스페셜티케미컬·포스코DX·에코프로머티·LG이노텍·두산로보틱스)이 손실의 21%, 최악 5종목을 빼도 −0.144. 시작일 5개: 가격 변동 −0.003 ~ +0.861(시작일에 따라 크게 다름), **비용은 0.444~0.460으로 일정**, 최악 5종목 비중 21~34%.

  **D. 국면 (시작일 5개 평균)**

  | 국면 | IC | top-10 순 | 동일가중(비용 없음) | 초과 (범위) | 편입/회 | 기간 MDD | 일간 MDD |
  |---|---|---|---|---|---|---|---|
  | 2023H2 | +0.026 | +0.1% | +3.3% | −3.3%p (−13.8 ~ +7.8) | 6.7 | −16.3% | −18.0% |
  | 2024 | +0.028 | −18.2% | −5.7% | −12.4%p (−22.0 ~ +1.7) | 6.5 | −27.7% | −31.3% |
  | 2025 | +0.016 | +19.4% | +38.1% | −18.8%p (−28.0 ~ −6.0) | 7.0 | −17.3% | −20.1% |
  | 2026(1~9월) | +0.036 | −6.9% | +6.8% | −13.7%p (−28.7 ~ +23.3) | 6.7 | −40.4% | −45.6% |

- **해석 (사후, 다음 사이클 가설로만)**:
  1. **IC 양수의 출처는 "상위 선택"이 아니라 "하위 회피"**: 점수와 초과수익의 관계가 단조가 아니라 산 모양 — 최하위(D1 −0.35%)와 하위권(D2~D4)이 뚜렷이 나쁘고, 중상위(D5~D9)가 약간 좋고, **최상위 D10은 평균과 같음(+0.02%)**. IC는 횡단면 전체 순위 상관이라 하위 쪽 구분만으로도 양수가 됨. 롱온리 top-10은 그 신호를 쓰지 못하는 구조이며, 엔진 top-10은 비용 전에도 평균보다 약간 낮음(−0.03%). long-short도 t 0.65로 통계적으로 약함.
  2. **손실 = 거의 0인 총수익 + 일정한 비용**: offset 0에서 가격 변동 기여 ≈ 0, 비용 −0.44(3.2년, 연 약 14%p, 산술). 시작일에 따라 가격 변동 기여는 0~+0.86으로 흔들리지만 비용은 늘 같음 → 비용이 구조적 손실, 총수익은 경로 잡음.
  3. **buffer가 회전율을 거의 못 줄임**: 포지션 2/3가 5일만 보유. 점수가 단기 반전 feature(5·20일) 기반이라 순위가 빨리 바뀌고, 신규는 늘 상위 5위 안에서 들어옴. buffer 3.0(30위)으로는 부족.
  4. **손실은 소수 종목 사고가 아니라 넓게 분산**: 143종목 중 86개 음수, 포지션 55% 손실, 최악 5종목 비중 21%.
  5. **국면과 무관하게 초과 음수**: 네 국면 모두 IC 양수인데 초과는 평균 음수. 2025 강세장(+38%)에서 가장 크게 뒤짐(−18.8%p, 모든 시작일에서 음수). 2026 일간 MDD −45.6%. 국면 간 IC 크기와 초과 수익은 연결되지 않음.
- **다음 사이클 후보 (항목 78 C10으로 추가 — 사후 진단 출처 명시, dev·forward2에서 검증)**: (a) 하위 회피형 구성(예: 하위 10~20% 제외한 동일가중) vs top-N, (b) 더 넓은 선택(top 20~30%)과 더 긴 보유(10·20일) 또는 점수 평활화로 회전율 축소, (c) 비용 차감 후 기대수익 기준 편입 문턱, (d) 점수 해상도(C2)와 함께 분위 단조성을 기본 보고 지표로(항목 67 D에 추가). top50 운용 경로도 같은 설계라 같은 문제가 있을 가능성이 크나 이 진단은 150종목 대상 [추론].

82. **수정주가 재계산 감지 — 감시·기록만 (2026-10-06, 항목 78 A5 / 항목 62 후속) — 데이터·모델·운용·판정 변경 없음 (엔지니어링, 실험 아님 → 사전등록 판정 없음)**

- **목적**: 금요일 일봉 수집(ka10081, 수정주가 전체 이력)이 `data/processed/historical/<code>.json`을 덮어쓰므로, 키움이 기업 행위 후 과거 가격을 다시 계산해도(항목 62의 207940, 10-01까지 ×0.99230) git diff로 우연히 볼 때만 드러났음. scale-free feature·라벨은 거의 그대로지만 고정 모델 지문, 분석가 카드 과거 통계, 원척도 값은 바뀔 수 있어 바뀌는 순간을 자동으로 기록.
- **분류 규칙 (`src/data/price_adjustment.classify_change(old, new)`, 순수 함수)**: 비교 필드 open·high·low·close·volume, **old와 new에 모두 있는 날짜만** 비교(새로 붙은 최근 봉 무시). 순서대로:
  1. `rows_removed` — 지난번 본 날짜가 사라짐(첫·마지막 사라진 날짜, 개수).
  2. 겹치는 봉이 하나도 안 바뀜 → `unchanged`.
  3. `uniform_rescale` — 종가가 바뀐 날짜들의 close_new/close_old 중앙값 r(|r−1| > 1e-4)에 대해, 겹치는 날짜의 **95% 이상**이 r과 같음. 기록: r, 같은 날짜들의 거래량 비율 중앙값, 첫 날짜·**마지막 적용 날짜**, `n_matched`(r에 맞는 날짜 수; `n_changed − n_matched` = r에 안 맞게 바뀐 날짜).
  4. 나머지 → `partial_change`(바뀐 날짜 수, 첫·마지막 날짜, 바뀐 필드).
  - **허용 오차 — 요청 설계(고정 1e-4)와 다름, 이유**: 가격이 원 단위 정수라 old = round(T), new = round(r·T)의 반올림만으로 비율이 최대 (0.5/r + 0.5)/close_old만큼 흔들림. 005930은 종가 최저 116원, 봉의 52%가 1만 원 미만 → 고정 1e-4면 005930의 실제 재조정이 `partial_change`로 잘못 분류됨(가짜 ×0.5 재조정으로 확인). 그래서 날짜별 허용 오차 = max(1e-4, 그 반올림 한계).
  - **실데이터 확인 (읽기만)**: 207940의 커밋 `5786a94` 전후 파일 → `uniform_rescale`, r = 0.9923, 거래량 ×1.007757, 2016-11-10~2026-09-23(이전 파일 끝의 9/28 봉은 장중 값이 확정값으로 바뀐 것이라 r에 안 맞음 — 항목 62와 일치, 9/24~26은 추석). 같은 커밋의 005930 → `partial_change` 1행(9/28, low·close·volume = 장중 봉 교체).
- **구현**: `scripts/monitor_price_adjustments.py` — 유니버스(`STOCKLENS_UNIVERSE` 또는 `--universe`) 각 종목을 `HistoricalStorage.load_daily_bars()`로 읽어 스냅샷 `data/processed/price_snapshots/<code>.json`(gitignore, 압축 JSON)과 비교 → 바뀐 종목을 `reports/price_adjustments/events.csv`(커밋 대상, 열: detected_at·stock_code·top50·classification·close_ratio·volume_ratio·first_date·last_date·n_overlap·n_changed·n_matched·n_removed·fields — **가격 값 없음**)에 추가 → 스냅샷을 현재 값으로 갱신.
  - 첫 실행(스냅샷 없음) = `new_snapshot`, 경보·이벤트 없음. 현재 일봉 파일이 없거나 비면 `no_data`, 기존 스냅샷 유지. 읽기·쓰기 오류 = `error`(다른 종목은 계속).
  - `--dry-run`: 스냅샷·이벤트 로그 모두 쓰지 않음(첫 스냅샷도 안 만듦; 반복 실행 시 이벤트 중복 방지). `--summary-only`: 한 줄 요약(야간 로그용).
  - top50 종목에 변경이 있으면 "고정 모델 지문 확인 필요: `STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/run_ml_backtest.py`" 출력.
  - 종료 코드: 0 변경 없음 / **4 변경 감지·기록**(실패 아님) / 1 오류.
  - `scripts/nightly_ingest.sh`: [2/5] 일봉 수집 바로 뒤 [2b/5]로 실행 — 같은 `if [[ "$daily" == "1" ]]` 블록이라 금요일(또는 `STOCKLENS_NIGHTLY_DAILY=1`)에만. 수집 유니버스(`$COLLECT`, 기본 kospi200) 그대로. rc 4는 "change recorded" 한 줄만 남기고 status 유지, 그 외 비0만 status=1. 이후 단계는 그대로 진행.
- **바꾸지 않은 것 / 잠금**: `data/raw`·`data/processed/historical`(읽기만)·분봉 `ka10080` 미접근. 가격 동일성 비교만 하고 수익률·feature·라벨·점수를 계산하지 않음, `select_segment` 미사용. 스냅샷에는 forward 기간 일봉 값도 복사되지만 gitignore된 로컬 사본이고 결과를 계산하지 않음. 고정 모델·운용 경로·판정 규칙·requirements·의존성 변경 없음(표준 라이브러리만). 날짜 상수 없음.
- **한계**: `HistoricalStorage.save_daily_bars()`는 날짜별 병합이라 수집으로는 행이 지워지지 않음 → `rows_removed`는 수동 편집·파일 교체 때만 나옴. 또 키움이 이력 일부만 다시 주면 재조정된 최근 구간과 병합되어 남은 옛 구간이 섞여 `partial_change`로 보일 수 있음(병합 정책은 바꾸지 않음). 스냅샷은 실행 시점 기준이라, 수집이 실패해 파일이 안 바뀐 주는 다음 주에 한꺼번에 잡힘.
- **테스트**: `tests/test_price_adjustment_monitor.py` **11개** — 균일 재조정(r 0.9923·거래량 1.0078·마지막 적용 날짜, 이후 3봉 미조정), 저가 이력 반올림 허용(×0.5), 일부 날짜 정정 → partial, 과거 행 삭제 → rows_removed, 최근 봉만 추가 → unchanged, 첫 실행 → 경보 없이 스냅샷, 변경 기록·스냅샷 갱신·종료 코드 4·top50 지문 문구(비top50이면 없음)·재실행 unchanged, `--dry-run` 스냅샷·로그 미기록(첫 스냅샷 포함), 이벤트 CSV에 가격 값 없음, 일봉 파일 없음 → 스냅샷 유지, 야간 스크립트 분기 문자열(일봉 수집 뒤·금요일 블록 안·rc 4 처리). 모두 tmp_path·합성 데이터. 재훈 기기 `.venv`에서 전체 431 + 11 = **442개 통과**. 실데이터 `--dry-run`(kospi200, 기록 없음): 200종목 전부 `new_snapshot`, 약 3초.

83. **A4 조사: point-in-time 구성종목·상장폐지 종목 데이터 확보 가능성 (2026-10-08, 항목 78 A4) — 조사만, 코드·데이터·모델·운용 변경 없음 (실험 아님 → 사전등록 판정 없음)**

- **목적**: 생존편향 해소(KOSPI200 과거 시점별 구성종목, 상장폐지 종목 가격)와 A2(KOSDAQ150 종목 holdout)의 실행 가능 여부 판단.
- **확인한 것**
  1. **키움 REST API (`config/kiwoom-rest-api-spec.json`)**: 날짜를 받는 구성종목 조회 없음. `ka20002`(업종별주가, KOSPI200 `inds_cd=201`)·`ka10099`(종목정보 리스트)는 **현재 시점만**. "편입·편출" 조회 엔드포인트 없음. `kt00003/kt00004`의 `상장폐지조회구분`은 계좌 조회라 무관.
  2. **키움 상장폐지 종목 일봉 (실측, 2026-10-08, `ka10081` 조회만·저장 안 함)**: 상장폐지 3종목 117930(한진해운)·103130(웅진에너지)·067250(STX조선해양) 모두 **빈 응답**(`return_code 0`, 빈 행 1개). 비교로 상장 유지 종목(003620·000040·001520)은 정상 600행. → **키움으로는 상장폐지 종목 가격을 받을 수 없다**(현 데이터 전체가 생존 종목뿐인 이유).
  3. **KRX (Data Marketplace, 구 정보데이터시스템)**: 2025-12-27부터 **로그인 필수**(회원제, 조회는 무료, AI 봇 수집 부하가 개편 사유). pykrx는 `KRX_ID`/`KRX_PW` 환경변수로 대응.
     - 지수 구성종목: pykrx `get_index_portfolio_deposit_file(ticker, date)` — 문서상 **2014-05-02 이후만** 조회 가능("KRX web server does NOT provide data prior to 2014/05/01").
     - 상장폐지 종목 시세: KRX 원천(`get_market_ohlcv(..., adjusted=False)`)은 상장폐지 종목 종가를 주지만 **수정주가가 아님**(키움 수정주가와 섞으면 기업 행위 날짜에 가짜 수익률). 직접 수정하려면 기업 행위 이력이 따로 필요.
  4. **2014-05 이전 구성종목**: 한국거래소 정기변경(6·12월) 보도자료·언론 기사로 편입·편출 목록을 재구성하는 방법뿐(웹 검색으로 2010~2012 원문은 찾지 못함). 유료 DB(FnGuide 등)는 미확인.
- **구간별 결론** (daily 분할 `src/data/dataset.py`: train 2002-10-29~2019-12-31, validation 2020-01-01~2023-06-30, test 2023-07-01~2026-09-16)
  | 구간 | KOSPI200 과거 시점 구성종목 | 상장폐지 종목 가격 |
  |---|---|---|
  | train 2002~2014-04 | 불가(보도자료 수작업 재구성만) | KRX 비수정 종가만 |
  | train 2014-05~2019, W2 일부·W3·test | **KRX 로그인으로 가능** | KRX 비수정 종가만 |
  - W1(2012~2015)은 2014-05 이전 부분이 비어 반쪽만 가능.
- **A2(KOSDAQ150) 영향**: KOSDAQ150은 2015-07 출시라 구성종목 이력이 그 이후뿐이고, 코스닥은 상장폐지가 많아 생존편향이 더 큼 → 상장폐지 종목 가격(수정 포함) 없이는 A2 결과가 낙관 쪽으로 기움. **현재 수단으로는 A2를 깨끗하게 할 수 없다**. 해석 한계를 명시한 제한판(현재 구성종목, 생존 종목만)으로 하거나 보류.
- **결정이 필요한 것 (재훈)**: (1) KRX 회원 계정으로 pykrx를 써서 2014-05 이후 구성종목 이력을 받을지 — 새 외부 의존성(`.venv` 고정 정책상 별도 venv 또는 requirements 변경 필요), 계정 정보는 `.env`에만, 수집 범위·빈도는 KRX 이용약관 확인 후. (2) A2를 제한판으로 할지 보류할지. (3) 2014-05 이전은 생존편향 한계로 문서화만 할지.
- **바꾸지 않은 것**: 코드·데이터·`data/raw`·고정 모델·운용 경로·판정 규칙·requirements. 테스트 변경 없음.
- **출처**: pykrx 소스 `pykrx/stock/stock_api.py`(GitHub sharebook-kr/pykrx), pykrx issue #89(상장폐지 종목 수정주가), #244(KRX 로그인 필수), 글로벌이코노믹 2025-12-07(KRX Data Marketplace 회원제 전환).

84. **[확정 2026-10-08] A6 다음 사이클 후보 그리드 사전 고정 (2026-10-08 작성·확정, 항목 78 A6 / 67 E·F, forward 결과를 보기 전) — 데이터 미열람, 실행 없음**

- **지위**: **A~E 전체 재훈 확정(2026-10-08)** — 이후 수정하지 않음. 1월 forward 결과를 본 뒤 이 항목에서 **빼는 것**은 자유, **더하거나 바꾸는 것**은 그 사실과 이유를 명시(항목 67 규칙 그대로). 항목 81에서 나온 아이디어는 사후 진단 출처이고 증거가 아님.

**A. 재훈 결정 (2026-10-08)**
  1. **제품 형태 유지**: 후보는 top-N 목록(N 10~30)·보유 5~20일 안에서만. 하위 회피형(하위 20% 제외 동일가중)은 판정에 쓰지 않는 **진단 보고**로만(분위 단조성과 함께).
  2. **주 판정 지표 = 비용 차감 후 유니버스 동일가중 대비 초과수익**(리밸런싱 시작일 5개 평균). 횡단면 rank IC는 보조.
  3. **후보 조합 상한 6개, 현 운용 구성은 항상 기준선**. 교체 조건: 시작일 5개 중 **4개 이상에서 기준선보다 초과수익이 높고**, 그 후보의 평균 초과수익 > 0.
  4. **재학습은 사이클 시작 시 1회, forward2 동안 고정**(새 지문 기록). 연 1회 갱신은 다음다음 사이클.
  5. **forward2 기간**: dev에서 200종목 날짜별 IC 표준편차를 다시 재서, 진짜 IC 0.03 가정 시 단측 t>1.65 통과 확률이 **60% 이상** 되는 최소 기간(거래일 단위, 125일 단위로 올림)으로 정함. **상한 2년(500거래일)**. 상한으로도 60%가 안 되면 forward2는 "해로움 점검 + 방향 기록"만 하고 통과 판정을 하지 않음. 6개월마다 해로움만 점검(항목 67 F-2 그대로). 표준편차는 성과와 무관한 값.

**B. 구간 (상수 출처: `src/data/dataset.py`, `src/data/intraday_split.py`)**
  - **선택용 dev = `INTRADAY_DATA_START`(2025-09-01) ~ forward 평가일.** 이 중 2025-09-01 ~ 2026-09-16은 daily test 구간(항목 41에서 소진)이고 150종목은 항목 79에서 한 번 봤음 — "깨끗한 holdout"이 아니라 **선택용 dev**로만 쓴다는 것을 여기서 명시. dev를 읽을 때의 test 잠금(`confirm_final_test_use`) 처리는 확정 시 구현 계획에 적고, 잠금 환경변수는 재훈 확인 후에만 켬.
  - **선택용 학습**: ~ 2025-08-31(`split_by_time(purge_days=5)`), 조기종료용 내부 검증은 학습 구간 마지막 1년. W1~W3는 선택에 쓰지 않고 국면 일관성 보고만.
  - **최종 모델**: 선택 끝난 구성으로 **dev 끝까지 포함해 1회 재학습** → 지문 기록 → forward2 시작부터 고정. (2026-10-08 대화에서 "2026-09-23까지 재학습"이라 했던 것을 정정: 선택 때는 dev 이전까지만 학습해야 dev가 의미 있고, 고정 직전에 dev까지 넣어 다시 학습.)
  - **유니버스**: KOSPI200 200종목(2026-10-04 구성, 항목 68). 과거 구간은 생존편향(항목 83), forward2는 고정 구성이라 없음.

**C. 후보 (6개 — 이 목록 밖은 이번 사이클에서 비교하지 않음)**
  - 모델 2종: **M0** = 현 고정 모델(지문 `f397507a…f5f6`, 재학습 없음). **M1** = 같은 feature·rank 타깃, 해상도 개선 설정(C2): `src/models/predict.py` 현 설정(깊이 2·학습률 0.03·조기종료 30) 그대로 두고 **트리 최소 100개**(100개 전에는 조기종료하지 않음, 이후 내부 검증 rank IC로 조기종료) — 현 모델의 점수 ≈8종류는 트리 10개(best_iteration 9)·깊이 2 때문(항목 51)이라 트리 수 하한이 해상도를 직접 올림. 값은 데이터를 보지 않고 고정.
  - 포트폴리오 3종: **P0** = top-10·보유 5일·buffer 3.0(현 운용) / **P1** = top-20·보유 10일·buffer 3.0 / **P2** = top-30·보유 20일·buffer 3.0. 진입 T+1 시가, 비용·동점 규칙 현행.
  - 조합: **M0P0(기준선)**, M0P1, M0P2, M1P0, M1P1, M1P2. 보유 기간이 다르면 라벨 기간도 다르지만 모델 타깃(5일)은 바꾸지 않음 — 보유 기간만 바꾸는 비교.
  - 이번 사이클에서 뺀 것: 새 정보원 feature(C5), 분봉 재학습(C7, 2027-09 이후), 리스크 규칙(C6), 비용 문턱(C10-c, rank 모델은 기대수익을 주지 않음 — 다음에 회귀 보정과 함께).

**D. 보고 (모든 후보 공통, 판정과 별개)**
  - 시작일 5개 평균·범위의 순수익·초과수익, rank IC 평균·t, 일간 equity MDD(항목 80), 회전율·비용 합계, 동점 민감도(항목 52), 10분위 수익 스프레드와 하위 회피형(진단).
  - dev 200종목의 날짜별 IC 표준편차 → A-5 기간 계산.

**E. 판정 순서 (확정 후 이 순서대로 1회)**
  1. dev에서 6개 계산 → A-3 조건을 통과한 후보 중 평균 초과수익 최대를 채택, 없으면 M0P0 유지(M0는 이미 고정이라 재학습 없음).
  2. 채택 구성으로 최종 재학습(B) → 지문 기록 → A-5로 forward2 기간 확정 → forward2 시작.
  3. 이 과정에서 지표·후보·조건을 바꾸지 않음. 화면 문구(항목 77)는 forward2 판정 전까지 "모델 참고 순위" 유지.

- **해석 한계**: dev는 약 1.3년(시작일 5개)이라 6개 비교도 우연 선택 위험이 남음 — 교체 조건(A-3)이 보수적인 이유. dev 앞부분은 test·항목 79에서 본 날짜. 생존편향(2026-10-04 구성). 보유 20일은 dev에서 독립 기간 수가 적음.
- **확정 시 남긴 실행 조건**: C의 M1·P1·P2 값은 그대로 확정. B의 dev 읽기에 필요한 test 잠금 처리(환경변수 사용 등)는 실행 시점에 재훈 확인 후. "트리 100개 전 조기종료 금지"는 XGBoost 기본 옵션에 없어 콜백 구현·테스트 필요(실행 단계).
