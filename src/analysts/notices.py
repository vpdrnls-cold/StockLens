"""User-facing wording of the model ranking (CURRENT_STATUS item 77). No dependencies.

Decided 2026-10-06, before the forward evaluation: the model output is shown as a
"model reference ranking", not a "recommendation", because its out-of-sample
performance is unconfirmed and in the latest validation window (W3, averaged over
rebalance start dates, item 66) and the intraday dev period it did not beat the
equal-weight universe. One source for the viewer, recommend.py, the survey and the
quant card, so the wording cannot drift apart.
"""

RANK_LABEL = "모델 참고 순위"
REFERENCE_RANK_NOTICE = (
    "과거 데이터로 만든 모델의 참고 순위입니다. 표본 밖 성과는 아직 확인되지 않았고(1차 확인 2027년 1월), "
    "최근 검증 구간에서는 시장 평균보다 낮았습니다. 투자 권유가 아닙니다."
)
