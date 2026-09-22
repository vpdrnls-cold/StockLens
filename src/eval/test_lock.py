"""Structural guard against accidental reuse of the final test period.

AGENTS.md section 13 says the test period must not be used to
repeatedly make design decisions. In practice this project has already
touched the test split more than once anyway (CURRENT_STATUS.md items
14, 30, 31) simply by re-running a script that had a "one-time test
check" section at the bottom for an unrelated reason (e.g. fixing the
IC-bias bug in item 30) -- the discipline was documented in comments
and print statements, but nothing actually stopped the script from
running that section again.

This module makes touching the test split require an explicit,
one-shot opt-in per invocation, the same way
``src/feature_selection/data_loading.py`` makes leakage structurally
hard rather than relying on remembering not to read ml_dataset.csv
directly (see learnings.md: "Data leakage is structurally prevented,
not just fixed").

Usage, right before the first line of code in a script that reads the
test split (never at the top of the script -- so validation-only
reruns never need the flag):

    from src.eval.test_lock import confirm_final_test_use
    confirm_final_test_use("run_ml_backtest.py")
    # ... only now touch splits.test / load_split("test") ...

Set STOCKLENS_CONFIRM_FINAL_TEST=1 in the environment to allow the
call through for exactly that run. Anything else raises.
"""

from __future__ import annotations

import os

_ENV_VAR = "STOCKLENS_CONFIRM_FINAL_TEST"


class TestSetLockedError(RuntimeError):
    """Raised when code tries to touch the test split without explicit confirmation."""


def confirm_final_test_use(caller: str) -> None:
    """Raise unless the test split has been explicitly unlocked for this run.

    Parameters
    ----------
    caller : str
        Name of the script/function requesting test access, used only
        to make the error/print message actionable.
    """
    if os.environ.get(_ENV_VAR) != "1":
        raise TestSetLockedError(
            f"{caller} tried to read the final test period "
            f"(2023-07-01~) without confirmation. This is a hard stop, "
            f"not a suggestion (AGENTS.md section 13 / "
            f"CURRENT_STATUS.md item 34): every validation-only "
            f"experiment for the current decision must be finished "
            f"first, and the test split may then be checked exactly "
            f"once. If this really is that one final check, rerun "
            f"with {_ENV_VAR}=1 in the environment."
        )
    print(
        f"[{caller}] {_ENV_VAR}=1 is set -- proceeding to read the "
        f"final test period. Make sure every validation-only "
        f"experiment for this decision is actually done first."
    )
