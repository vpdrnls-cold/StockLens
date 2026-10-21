"""Display formatting shared by the viewer pages (CURRENT_STATUS item 100). No Streamlit.

Price direction follows the Korean convention -- up red, down blue -- and always
carries a symbol (▲/▼, +/−) so colour is never the only cue. The colour marks the
price direction only, never a view on the stock (AGENTS.md 43.5).
"""

from __future__ import annotations

MINUS = "−"  # U+2212, a real minus sign for display


def _signed(x: float, digits: int) -> str:
    text = f"{abs(x):,.{digits}f}"
    return f"+{text}" if x > 0 else (f"{MINUS}{text}" if x < 0 else text)


def change_markdown(change: float | None, rate: float | None, digits: int = 2, unit: str = "") -> str:
    """Streamlit markdown for a change versus the previous close, e.g. ':red[▲ +12.34 (+0.84%)]'.

    Direction comes from ``rate`` (or ``change`` when the rate is missing); '' if both are None.
    """
    direction = rate if rate is not None else change
    if direction is None:
        return ""
    parts = []
    if change is not None:
        parts.append(f"{_signed(change, digits)}{unit}")
    if rate is not None:
        parts.append(f"({_signed(rate, 2)}%)" if parts else f"{_signed(rate, 2)}%")
    body = " ".join(parts)
    if direction > 0:
        return f":red[▲ {body}]"
    if direction < 0:
        return f":blue[▼ {body}]"
    return f":gray[보합 {body}]"
