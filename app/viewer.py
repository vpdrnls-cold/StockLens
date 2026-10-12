"""StockLens viewer router (CURRENT_STATUS items 70/91, AGENTS.md 43). Local only.

Run with the separate UI environment (never install streamlit into .venv -- it is
pinned to the frozen model's environment):

    .venv-ui/bin/streamlit run app/viewer.py

Pages: the analyst panel (app/panel.py, read-only card JSON) and the investor-profile
survey (app/survey_page.py, writes only data/user_profile.json).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="StockLens", layout="wide")
st.navigation([
    st.Page("panel.py", icon="📊", default=True),
    st.Page("survey_page.py", title="투자성향 진단", icon="📝"),
]).run()
