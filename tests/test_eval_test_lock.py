from __future__ import annotations

import pytest

from src.eval.test_lock import TestSetLockedError, confirm_final_test_use, _ENV_VAR


def test_raises_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV_VAR, raising=False)
    with pytest.raises(TestSetLockedError):
        confirm_final_test_use("some_script.py")


def test_raises_when_env_var_is_not_exactly_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV_VAR, "true")
    with pytest.raises(TestSetLockedError):
        confirm_final_test_use("some_script.py")


def test_passes_when_env_var_is_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV_VAR, "1")
    confirm_final_test_use("some_script.py")  # must not raise


def test_error_message_names_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV_VAR, raising=False)
    with pytest.raises(TestSetLockedError, match="some_script.py"):
        confirm_final_test_use("some_script.py")
