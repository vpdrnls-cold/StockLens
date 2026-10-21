"""Guard against deciding on an unfinished daily bar (CURRENT_STATUS item 63).

The ka10081 daily bars carry no completeness flag (unlike index/flow rows,
item 58). On 2026-09-28 a recommendation was produced around 12:41 KST from
that day's in-progress bar (item 62). A decision on day T must use T's FINAL
close, so a bar dated today is usable only after ``SESSION_FINAL_TIME_KST``
-- the same rule ``is_complete_for_retrieval`` applies to index/flow rows.
"""

from __future__ import annotations

from datetime import date, datetime, time

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


# Item 99 (audit D-6): SESSION_FINAL_TIME_KST (18:00) was never measured (item 64) and the
# NXT after-market runs until 20:00, so FETCHING stays on the after-market close until
# item 64 settles it. Same cut-off as the minute-bar script.
FETCH_FINAL_TIME_KST = time(20, 0)


def daily_fetch_error(base_date: date, now: datetime) -> str | None:
    """Message if fetching ka10081 up to ``base_date`` at ``now`` would store today's
    unfinished bar (item 98), else None.

    Cut-off ``FETCH_FINAL_TIME_KST`` (item 99). Kiwoom returns bars up to today even for a
    later base date, so only an earlier base date is safe before the cut-off. Weekends
    have no session; a weekday holiday is still refused (use --force).
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware.")
    local = now.astimezone(KST)
    if base_date < local.date() or local.weekday() >= 5 or local.time() >= FETCH_FINAL_TIME_KST:
        return None
    return (
        f"지금은 {local:%H:%M} KST 입니다. 일봉(ka10081)에는 확정 표시가 없어 {FETCH_FINAL_TIME_KST:%H:%M} 이전에 받으면 "
        f"오늘({local.date()}) 봉이 미확정 값으로 저장됩니다(항목 62·97·99). {FETCH_FINAL_TIME_KST:%H:%M} 이후에 다시 실행하거나, "
        "오늘이 휴장일이거나 알고 있다면 --force 를 붙이세요."
    )
