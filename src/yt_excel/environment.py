"""API key validation with .env file support."""

import os

from dotenv import load_dotenv


def validate_api_key() -> str:
    """Load and validate the OPENAI_API_KEY environment variable.

    Loads .env file with override=False so system environment variables
    take precedence. Validates that the key exists and is not empty.

    Returns:
        The validated API key string.

    Raises:
        SystemExit: If the API key is not set or is empty.
    """
    load_dotenv(override=False)

    api_key = os.environ.get("OPENAI_API_KEY")

    if api_key is None:
        raise SystemExit(
            "\u274c ERROR: OPENAI_API_KEY is not set.\n"
            "\n"
            "Set it with one of:\n"
            '  1. Create a .env file:  echo OPENAI_API_KEY=sk-... > .env\n'
            '  2. Export directly:      export OPENAI_API_KEY="sk-..."  (Linux/macOS)\n'
            '                           $env:OPENAI_API_KEY="sk-..."    (PowerShell)\n'
            "\n"
            "Aborting."
        )

    if not api_key.strip():
        raise SystemExit(
            "\u274c ERROR: OPENAI_API_KEY is set but empty.\n"
            "Aborting."
        )

    return api_key
