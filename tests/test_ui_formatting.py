"""Price-change display in Korean convention (CURRENT_STATUS item 100). No Streamlit."""
from __future__ import annotations

from src.ui.formatting import change_markdown


def test_up_is_red_with_triangle_and_plus() -> None:
    assert change_markdown(21.5, 0.84) == ":red[▲ +21.50 (+0.84%)]"


def test_down_is_blue_with_real_minus_sign() -> None:
    assert change_markdown(-3000, -1.2, digits=0, unit="원") == ":blue[▼ −3,000원 (−1.20%)]"


def test_flat_and_missing() -> None:
    assert change_markdown(0.0, 0.0) == ":gray[보합 0.00 (0.00%)]"
    assert change_markdown(None, None) == ""


def test_direction_falls_back_to_change_and_rate_alone_is_shown() -> None:
    assert change_markdown(-5.0, None) == ":blue[▼ −5.00]"
    assert change_markdown(None, 1.5) == ":red[▲ +1.50%]"
