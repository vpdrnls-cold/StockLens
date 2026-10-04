"""Guard against deciding on an unfinished daily bar (CURRENT_STATUS item 63).

The ka10081 daily bars carry no completeness flag (unlike index/flow rows,
item 58). On 2026-09-28 a recommendation was produced around 12:41 KST from
that day's in-progress bar (item 62). A decision on day T must use T's FINAL
close, so a bar dated today is usable only after ``SESSION_FINAL_TIME_KST``
-- the same rule ``is_complete_for_retrieval`` applies to index/flow rows.
"""

from __future__ import annotations

from datetime import date, datetime

from src.data.normalization import KST, SESSION_FINAL_TIME_KST


def intraday_bar_error(decision_date: date, now: datetime) -> str | None:
    """Message if ``decision_date``'s bar cannot be final yet at ``now``, else None."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware.")
    local = now.astimezone(KST)
    if decision_date > local.date():
        return f"판단일 {decision_date}이 현재 날짜({local.date()})보다 미래입니다."
    if decision_date == local.date() and local.time() < SESSION_FINAL_TIME_KST:
        return (
            f"판단일 {decision_date}의 일봉은 아직 확정 전입니다(현재 {local:%H:%M} KST, "
            f"확정 기준 {SESSION_FINAL_TIME_KST:%H:%M}). 장중 값으로 판단하지 않습니다 — "
            f"{SESSION_FINAL_TIME_KST:%H:%M} 이후 일봉을 갱신하고 다시 실행하거나, "
            "--date 로 이전 판단일을 지정하세요."
        )
    return None
