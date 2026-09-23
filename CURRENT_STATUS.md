StockLens Current Project Status

  이 파일은 변경 가능한 프로젝트 상태 기록이다. 의미 있는 구현 작업이
  끝날 때마다 갱신한다. 영구적인 개발 규칙은 이 파일이 아니라
  AGENTS.md에 둔다.

------------------------------------------------------------------------

1. Current Project Goal

StockLens는 개인화된 주식 분석/추천 시스템으로 개발 중이다.

최종 제품 목표:

사용자 투자성향 설문 → 시장 정보로 종목 분석 → 종목별 신호/예측 생성 →
사용자 투자성향에 맞게 개인화 랭킹 → 설명이 포함된 Top 5 추천 +
보유 종목 HOLD/SELL 판단.

인트라데이, 뉴스, 매크로, 사용자 행동 피드백은 최종 비전에 포함되지만
현재 구현 범위(MVP)는 아니다.

------------------------------------------------------------------------

2. Current MVP Scope and Verdict

MVP 질문:

일별 OHLCV에서 만든 기술적 feature가 out-of-sample에서 유의미한 예측
신호를 만들고, 단순 규칙 기반 baseline보다 나은가?

MVP 평가 결과(항목 14, 15, 24, 25 기준): 현재로선 **아니오**.

-   ML 전략(19개 scale-free feature, XGBoost)은 테스트 구간(2023-07~
    2026-09)에서 룰베이스 모멘텀 baseline(+24.08%)을 넘지 못함
    (+3.42% 수준).
-   cross-sectional rank IC는 validation 기준 +0.01~+0.04 수준으로 0에
    가까움.
-   Filter/Wrapper/Embedded 재실행 결과, 3개 walk-forward 구간에서
    안정적으로 반복되는 feature 조합이 없음. 19개 전체를 유지.
-   따라서 daily 기술 feature만으로는 baseline을 안정적으로 이기는
    신호가 확인되지 않았고, 원인 후보로 5종목 유니버스의 통계적 한계가
    있음(아직 검증 전).

범위 확장 이력: 항목 16에서 최종 산출물의 소비자 레이어(개인화 재랭킹,
HOLD/SELL 판단, Explanation)를 신호 데이터 소스 확장(Phase H~J)보다
먼저 구현하기로 순서를 조정했다. 이 레이어들은 신호가 무엇이든 그 위에
얹히는 구조이며, 인트라데이/뉴스/매크로는 여전히 범위 밖이다.

------------------------------------------------------------------------

3. Completed Work

3.1 Kiwoom REST API 연동 — 완료

-   인증, 현재가 조회, 일봉(ka10081) 조회, 응답 정규화, 에러 처리
-   `cont-yn`/`next-key` 자동 pagination, rate-limit retry/backoff
-   mock 응답 기반 테스트, 실제 API 통신 검증 완료

3.2 일별 과거 데이터 수집 — 완료

-   core5(기본 유니버스): 000660, 005380, 005930, 035420, 035720
-   top50(KOSPI200 시가총액 상위 50, 항목 28): `config/universe_kospi200_top50.json`을
    `scripts/build_universe.py`로 생성한 뒤 `STOCKLENS_UNIVERSE=top50`으로 선택.
    데이터 수집은 미완료.
-   종목당 약 6k~11k bar(약 23~44년), 2002-10 ~ 2026-09
-   분할: train 2002-10-29~2019-12-31 / validation 2020-01-01~
    2023-06-30 / test 2023-07-01~2026-09-16
    (`src/data/dataset.py`가 분할 상수의 단일 기준)

3.3 데이터 품질 유의사항

장중에 ka10081을 호출하면 당일 미완성 캔들이 포함될 수 있다. 학습/백테스트는
완성된 일봉만 사용한다. 실시간 추론에서는 예측 시점이 명시적으로 정의된
경우에 한해 진행 중인 캔들을 쓸 수 있으므로, "항상 전일 데이터만 사용"이라는
일괄 규칙은 두지 않는다.

3.4 Feature Engineering — 완료

-   `FEATURE_COLUMNS` 27개(원래 25개 + `atr_pct`, `macd_hist_pct`)
-   그중 raw price-scale 8개(`sma_5, sma_20, sma_60, macd, macd_signal,
    macd_hist, atr_14, volume_sma_20`)를 제외한 scale-free 19개가 현재
    `SELECTED_FEATURES`(임시 확장, 항목 14). 정식 선택 결과가 아니라
    "더 좁힐 근거가 없어 전체 유지"한 상태(항목 15).
-   pooled 다종목 모델에서는 scale-free feature만 사용해야 함(항목 14 교훈).

3.5 Baseline / ML / 백테스트 — 완료

-   룰베이스 모멘텀 baseline과 공용 백테스트 엔진 `src/backtest/baseline.py`
    (`src/ml/backtest.py`는 이를 호출하는 얇은 어댑터)
-   XGBoost 일별 모델(`src/models/predict.py`), early stopping,
    cross-sectional rank IC 평가
-   leakage 방지: `src/feature_selection/data_loading.py`(분할 강제)
-   재현성: walk-forward/실험 스크립트는 `tree_method="exact"`,
    `n_jobs=1` 고정 시 두 기기(Linux x86_64 / macOS arm64)에서 비트 단위
    일치 확인(항목 23~25). 전역 `DEFAULT_PARAMS`는 아직 `hist` 유지.

3.6 소비자 레이어 — 구현됨(라이브러리 수준)

-   개인화 재랭킹 `src/recommendation/scoring.py`(항목 16)
-   HOLD/SELL 판단 `src/portfolio/optimizer.py`: 기본값은 손절
    3.0x ATR%만 활성. signal-reversal(absolute/percentile)은 walk-forward
    검증 실패로 opt-in 전용(항목 17~26)
-   Explanation `src/explanation/`(항목 19), 한국어 텍스트 출력
-   CLI/API 진입점(`app.py`)에는 아직 연결되지 않음(스캐폴드 상태)

3.7 테스트 — 전체 136개 통과(`pytest.ini`로 `tests/`만 수집)

------------------------------------------------------------------------

4. Known Open Issues

-   Window1(train ..2011, val 2012~2015) 모델이 `best_iteration` 0~1로 사실상
    미학습됨. 원인 미조사(항목 18, 20, 24). walk-forward 스크립트는
    `best_iteration < 10`이면 해당 구간을 신뢰 불가로 제외(항목 27).
-   `walk_forward_position_thresholds.py`는 아직 미학습 구간 제외 로직이
    없고 경고 출력만 함.
-   전역 `DEFAULT_PARAMS`를 `tree_method="exact"`로 바꿀지 미결정. 단일 split에서
    IC가 +0.0289 → +0.0113으로 하락한 신호가 있어 walk-forward 검증 필요(항목 23).
-   5종목 유니버스: 날짜당 랭킹 표본이 5개라 rank IC 분산이 크고, percentile
    규칙의 granularity가 20%로 제한됨. 유니버스 확장 필요 여부가 다음 핵심 판단.
    (항목 28에서 확장 인프라 구현 완료, 데이터 수집 후 평가 대기)
-   생존편향(AGENTS.md 23절): core5와 top50 모두 "현재 시점의 대형주"라서, 과거 구간
    성과의 절대 수치는 낙관적. ML vs 모멘텀의 상대 비교만 신뢰.
-   HOLD/SELL 실험 스크립트(`evaluate_position_thresholds.py`, `walk_forward_position_
    thresholds.py`, `evaluate_signal_reversal_thresholds.py`, `walk_forward_signal_
    reversal.py`)는 아직 core5 전용. 자체 결정 그리드가 공통 날짜 inner join에 의존하며
    partial 유니버스는 미지원.

------------------------------------------------------------------------

5. Next Steps (우선순위 순)

1.  유니버스 확장(KOSPI200 시총 상위 50): 인프라 완료(항목 28). 남은 일: (a)
    `build_universe.py`로 종목 확정, (b) `ingest_kiwoom_daily_chart_batch.py`로 수집,
    (c) `check_data_coverage.py`로 종목별 이력 확인, (d) `tree_method="exact"` 기준
    IC·백테스트를 3개 walk-forward 구간에서 재평가(top_n은 5~10도 함께 확인).
2.  Window1 `best_iteration` 이상 원인 조사.
3.  모델링 방향 재검토: rank/분류 타겟, 모멘텀과 ML 점수의 앙상블.
4.  위 1~3 이후에도 daily 기술 feature로 안 되면 Phase H~J(인트라데이,
    뉴스, 매크로).
5.  Explanation 레이어를 CLI/API 진입점에 연결(신호가 약한 동안은 낮은 우선순위).

------------------------------------------------------------------------

6. Future Work, NOT CURRENT SCOPE

구현되지 않았음. 최종 비전에만 있음.

-   Intraday: Kiwoom 분봉(1/3/5/10/15/30/45/60분). 일봉으로 분봉을 복원할 수 없음.
-   News: 뉴스량, 감성, 이벤트 유형/강도, 관련성, 최신성. 과거 뉴스는 실제로
    확인 가능했던 시각에 맞춰 정렬해야 함.
-   Macro: 금리, USD/KRW, 유가, 금, KOSPI/KOSDAQ, 해외 지수. 시점 정렬 필수.
-   Integrated model: daily + intraday + news + macro → 통합 스코어링. 새 데이터
    소스 추가 시 재학습이 필요할 수 있음. 현재 daily 모델은 baseline/구성요소로
    재사용 가능.
-   Real-time recommendation: 실행 시점의 시장 스냅샷 → feature 갱신 → 예측 →
    개인화 → Top 5 → 설명. 과거 학습 데이터는 각 시점에 실제로 존재했던
    정보만 사용해야 함.
-   User feedback / outcome learning: 추천 → 사용자 선택 → 보유/청산 결과 →
    선호 학습. 한 번의 거래 결과로 시장 예측 모델을 바로 바꾸지 않으며,
    시장 예측과 사용자 선호 학습은 개념적으로 분리한다.
-   설문 기반 개인화(Phase L)의 사용자 프로필 수집 흐름: 현재는 프로필이 코드
    상수(`PROFILES`)로만 존재함.

------------------------------------------------------------------------

7. Current Project Position

Kiwoom API → 완료
일별 과거 데이터 → 완료(5종목, 2002~2026)
Daily feature engineering → 완료(27개, 그중 19개 사용)
예측 문제 정의(target_return_5d, 5일 horizon) → 완료
Rule-based baseline → 완료
Feature Selection → 수행 완료, 안정적 개선 없음(항목 15)
ML 모델 → 구현 완료, baseline 미달(항목 14, 15)
Out-of-sample 평가 → 수행 완료(테스트 구간은 최종 확인용으로만 사용)
재현성 → 해결(항목 23~25)
개인화 / HOLD-SELL / Explanation → 라이브러리 수준 구현 완료
MVP 통과 → 미달(daily 기술 feature 단독으로는 baseline 초과 신호 미확인)
유니버스 확장, Phase H~J → 다음 단계

------------------------------------------------------------------------

8. Current Priority

당장의 우선순위는 인트라데이 수집, 뉴스/매크로 API, 실시간 아키텍처, UI가
아니다. 우선순위는 "현재 신호가 약한 이유가 5종목 표본의 한계인지, 신호
자체의 부재인지"를 유니버스 확장으로 가려내는 것이다.

최종 비전에 있다는 이유만으로 범위를 넓히지 않는다.

------------------------------------------------------------------------

10. Update Policy

의미 있는 작업이 끝날 때마다:

1.  이 파일을 갱신한다.
2.  "다음 단계"의 항목을 "완료"로 옮긴다.
3.  중요한 발견과 미해결 이슈를 기록한다.
4.  미래 아이디어와 구현된 기능을 명확히 분리한다.
5.  진행 상황 갱신만을 위해 AGENTS.md를 고치지 않는다.
6.  아래 항목 11번부터는 시간순 작업 로그다. 새 작업은 마지막에 번호를 이어서
    추가하고, 위의 요약 절(1~8)도 함께 최신 상태로 맞춘다.

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
