"""Configuration loading for StockLens."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class KiwoomSettings:
    """Settings needed by the Kiwoom REST client."""

    app_key: str
    secret_key: str
    base_url: str = "https://api.kiwoom.com"
    timeout_seconds: float = 10.0
    registered_ip: str | None = None

    @property
    def environment(self) -> str:
        """Classify the documented production and mock API domains."""
        if self.base_url == "https://api.kiwoom.com":
            return "production"
        if self.base_url == "https://mockapi.kiwoom.com":
            return "mock"
        return "custom"

    @classmethod
    def from_env(cls) -> "KiwoomSettings":
        """Load Kiwoom credentials from the environment and a local ``.env`` file."""
        load_dotenv()

        app_key = os.getenv("KIWOOM_APP_KEY", "").strip()
        secret_key = os.getenv("KIWOOM_SECRET_KEY", "").strip()
        base_url = os.getenv("KIWOOM_BASE_URL", cls.base_url).rstrip("/")
        registered_ip = os.getenv("KIWOOM_REGISTERED_IP", "").strip() or None

        missing = [
            name
            for name, value in (
                ("KIWOOM_APP_KEY", app_key),
                ("KIWOOM_SECRET_KEY", secret_key),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Missing required environment variable(s): " + ", ".join(missing)
            )
        if not base_url.startswith(("https://", "http://")):
            raise ConfigurationError("KIWOOM_BASE_URL must be an HTTP(S) URL.")
        if registered_ip:
            try:
                ipaddress.ip_address(registered_ip)
            except ValueError as error:
                raise ConfigurationError("KIWOOM_REGISTERED_IP must be a valid IP address.") from error

        return cls(
            app_key=app_key,
            secret_key=secret_key,
            base_url=base_url,
            registered_ip=registered_ip,
        )
