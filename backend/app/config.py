"""Load local server configuration without exposing it to the browser."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_local_env() -> None:
    if os.environ.get("ALEM_LOAD_ENV", "1") != "0":
        # Explicit process settings take precedence; values are never executed.
        load_dotenv(PROJECT_ROOT / ".env", override=False, interpolate=False)
