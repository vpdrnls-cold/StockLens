"""Item 64 probe: row picking and stability report (no network)."""
from __future__ import annotations

from scripts import check_session_final_time as probe


def test_pick_row_matches_date_exactly() -> None:
    resp = {"stk_invsr_orgn": [{"dt": "20261005", "frgnr_invsr": "1"}, {"dt": "20261002", "frgnr_invsr": "2"}]}
    assert probe.pick_row(resp, "stk_invsr_orgn", "20261005") == {"dt": "20261005", "frgnr_invsr": "1"}
    assert probe.pick_row(resp, "stk_invsr_orgn", "20261006") is None
    assert probe.pick_row({}, "stk_invsr_orgn", "20261005") is None


def _snap(t: str, flow: dict | None, bar: dict | None) -> dict:
    return {"retrieved_at": t, "rows": {"ka10059": {"005930": flow}, "ka10081": {"005930": bar}, "ka20006": {}}}


def test_stability_report_finds_last_change() -> None:
    snaps = [
        _snap("2026-10-05T18:40:00+09:00", {"dt": "x", "frgnr": "5"}, {"dt": "x", "cur": "100"}),
        _snap("2026-10-05T15:40:00+09:00", None, {"dt": "x", "cur": "99"}),  # out of order on purpose
        _snap("2026-10-05T17:00:00+09:00", {"dt": "x", "frgnr": "3"}, {"dt": "x", "cur": "100"}),
        _snap("2026-10-05T20:00:00+09:00", {"dt": "x", "frgnr": "5"}, {"dt": "x", "cur": "100"}),
    ]
    rep = probe.stability_report(snaps)
    flow = rep["ka10059"]["codes"]["005930"]
    assert flow["first_seen"] == "2026-10-05T17:00:00+09:00"
    assert flow["last_change"] == "2026-10-05T18:40:00+09:00" and flow["changed_fields"] == ["frgnr"]
    bar = rep["ka10081"]["codes"]["005930"]
    assert bar["last_change"] == "2026-10-05T17:00:00+09:00"
    assert rep["ka10059"]["latest_change"] == "2026-10-05T18:40:00+09:00"
    assert rep["ka20006"]["latest_change"] is None
    assert rep["snapshot_times"][0].startswith("2026-10-05T15:40")
