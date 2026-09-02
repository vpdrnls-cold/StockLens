"""Check Kiwoom REST authentication and current-price lookup.

Usage:
    python3 scripts/check_kiwoom_quote.py 005930
"""

from __future__ import annotations

import argparse
import ipaddress
import logging
from pathlib import Path
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient, KiwoomClientError
from src.utils.config import ConfigurationError, KiwoomSettings


PUBLIC_IP_CHECK_URL = "https://api.ipify.org"


def _get_public_ip() -> str | None:
    """Return the outbound public IP for comparison with the portal registration."""
    try:
        request = Request(PUBLIC_IP_CHECK_URL, headers={"User-Agent": "StockLens/0.1"})
        with urlopen(request, timeout=5) as response:
            public_ip = response.read().decode("utf-8").strip()
        return str(ipaddress.ip_address(public_ip))
    except (OSError, URLError, ValueError):
        return None


def _print_diagnostics(settings: KiwoomSettings, client: KiwoomClient) -> None:
    """Print safe environment diagnostics before an API request."""
    context = client.diagnostic_context()
    print(f"environment={context['environment']}")
    print(f"base_url={context['base_url']}")
    print(f"app_key_fingerprint={context['app_key_fingerprint']}")

    public_ip = _get_public_ip()
    if public_ip is None:
        print("public_ip=unavailable")
    else:
        print(f"public_ip={public_ip}")

    registered_ip = settings.registered_ip
    if registered_ip is None:
        print("registered_ip=not configured")
        print("registered_ip_match=not_checked")
    else:
        print("registered_ip=configured")
        print(
            "registered_ip_match="
            + (str(public_ip == registered_ip).lower() if public_ip else "not_checked")
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authenticate with Kiwoom and request ka10001 stock information."
    )
    parser.add_argument("stock_code", help="Kiwoom stock code, for example 005930")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Print safe production/mock, App Key fingerprint, and IP diagnostics.",
    )
    arguments = parser.parse_args()

    try:
        settings = KiwoomSettings.from_env()
        client = KiwoomClient(settings)
        if arguments.diagnose:
            _print_diagnostics(settings, client)
        quote = client.get_current_quote(arguments.stock_code)
    except (ConfigurationError, KiwoomClientError, ValueError) as error:
        print(f"Kiwoom connectivity check failed: {error}", file=sys.stderr)
        return 1

    print(f"{quote.stock_code} {quote.stock_name}".strip())
    print(f"current_price={quote.current_price}")
    print(f"change_from_previous_day={quote.change_from_previous_day}")
    print(f"change_rate={quote.change_rate}")
    print(f"volume={quote.volume}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
