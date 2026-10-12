"""Investor-profile survey page (CURRENT_STATUS item 91, item 57 rules). Local only.

Opened through the router ``app/viewer.py``. Questions, scoring and wording come
from src/recommendation/survey.py; widget handling from src/ui/survey_form.py.
The result only changes the order of the reference boxes in the panel (AGENTS 43.6),
never the model ranking.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.recommendation import survey as sv
from src.ui import survey_form as sf
from src.ui import viewer_data as vd

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = sf.profile_path(ROOT)

st.title("투자성향 진단 (6문항)")
st.info(sv.RISK_NOTICE)

saved = vd.load_profile(PROFILE_PATH)
if saved:
    current = vd.PROFILE_LABELS[saved["profile"]] if saved["eligible"] else "제공 불가"
    st.caption(f"현재 저장된 결과: {current} (진단 {saved['created_at'][:10]}) — 다시 진단하면 덮어씁니다.")

selections: dict[str, int | None] = {}
for q in sv.QUESTIONS:
    selections[q.key] = st.radio(
        f"**{q.key}.** {q.text}", range(len(q.options)), index=None,
        format_func=lambda i, q=q: q.options[i][0], key=f"survey_{q.key}",
    )

ack_choice = None
if sv.needs_warning(selections):
    st.warning(sv.WARNING_TEXT)
    ack_choice = st.radio("경고 확인", sf.ACK_OPTIONS, index=None, key="survey_ack", horizontal=True)

if st.button("진단하기", type="primary"):
    problem = sf.form_problem(selections, ack_choice)
    if problem:
        st.error(problem)
    else:
        result = sf.score_form(selections, ack_choice)
        sv.save(result, PROFILE_PATH)
        lines = sv.explain(result).splitlines()
        if result.eligible:
            st.success(lines[0])
        else:
            st.error(lines[0])
        st.markdown("\n".join(f"- {line.strip().lstrip('- ')}" for line in lines[1:]))
        st.caption("저장했습니다 (data/user_profile.json, git에 올라가지 않음).")
        if result.eligible:
            st.page_link("panel.py", label="분석가 패널에서 보기", icon="📊")
