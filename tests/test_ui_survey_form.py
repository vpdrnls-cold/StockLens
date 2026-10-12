"""Web survey page data side (CURRENT_STATUS item 91) -- tmp_path only, no Streamlit."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.recommendation import survey as sv
from src.ui import survey_form as sf
from src.ui import viewer_data as vd

ROOT = Path(__file__).resolve().parents[1]


def S(*one_based: int | None) -> dict[str, int | None]:
    """Widget selections as 1-based option numbers for Q1..Q6 (None = not chosen)."""
    return {q.key: (None if i is None else i - 1) for q, i in zip(sv.QUESTIONS, one_based)}


def test_unanswered_questions_block_scoring():
    sel = S(4, None, 3, 3, None, 3)
    assert sf.unanswered(sel) == ["Q2", "Q5"]
    assert "Q2, Q5" in sf.form_problem(sel, None)
    with pytest.raises(ValueError):
        sf.score_form(sel, None)
    assert sf.unanswered({}) == [q.key for q in sv.QUESTIONS]


def test_ten_percent_warning_needs_an_answer():
    sel = S(4, 4, 2, 4, 4, 4)  # Q3 = max 10% -> warning
    assert sf.form_problem(sel, None) is not None
    assert sf.ack_value(None) is None
    no = sf.score_form(sel, sf.ACK_OPTIONS[1])
    assert not no.eligible and no.warning_acknowledged is False
    yes = sf.score_form(sel, sf.ACK_OPTIONS[0])
    assert yes.eligible and yes.profile == "conservative" and yes.warning_acknowledged is True


def test_warning_answer_ignored_when_no_warning():
    sel = S(4, 4, 4, 3, 3, 3)
    assert sf.form_problem(sel, None) is None
    assert sf.score_form(sel, sf.ACK_OPTIONS[1]).warning_acknowledged is None


@pytest.mark.parametrize("answers,ack", [
    ((4, 4, 5, 4, 4, 4), None),  # aggressive
    ((3, 3, 3, 3, 3, 1), None),  # neutral
    ((2, 2, 3, 2, 2, 2), None),  # conservative
    ((1, 4, 5, 4, 4, 4), None),  # not eligible
    ((4, 4, 2, 4, 4, 4), True),  # 10% acknowledged -> capped
])
def test_same_result_as_cli(tmp_path, answers, ack):
    out = tmp_path / "cli.json"
    cmd = [sys.executable, "scripts/survey.py", "--answers", ",".join(map(str, answers)), "--out", str(out)]
    if ack:
        cmd.append("--acknowledge-warning")
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, env={"PYTHONPATH": str(ROOT)})
    cli = json.loads(out.read_text(encoding="utf-8"))

    web = sf.score_form(S(*answers), sf.ACK_OPTIONS[0] if ack else None).to_json()
    drop = {"created_at"}
    assert {k: v for k, v in web.items() if k not in drop} == {k: v for k, v in cli.items() if k not in drop}


def test_saved_result_is_what_the_viewer_reads(tmp_path, monkeypatch):
    monkeypatch.setenv(sf.PROFILE_PATH_ENV, str(tmp_path / "p.json"))
    path = sf.profile_path(ROOT)
    assert path == tmp_path / "p.json"
    sv.save(sf.score_form(S(2, 2, 3, 2, 2, 2), None), path)
    assert vd.load_profile(path)["profile"] == "conservative"
    assert vd.load_profile(path)["eligible"] is True
    monkeypatch.delenv(sf.PROFILE_PATH_ENV)
    assert sf.profile_path(ROOT) == ROOT / vd.PROFILE_PATH


def test_no_streamlit_import():
    src = (ROOT / "src/ui/survey_form.py").read_text(encoding="utf-8")
    assert "streamlit" not in src.split('"""', 2)[2]
