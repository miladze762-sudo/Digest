from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_env_example_documents_required_digest_variables() -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    required_names = {
        "TRIGGER_PROJECT_REF",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_STRING",
        "TELEGRAM_SOURCE_CHANNEL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_TARGET_CHAT_ID",
        "NOTEBOOKLM_AUTH_JSON",
        "NOTEBOOKLM_ACCOUNT_EMAIL",
        "NOTEBOOKLM_MAX_NOTEBOOKS",
        "NOTEBOOKLM_CLEANUP_THRESHOLD",
        "NOTEBOOKLM_CLEANUP_TARGET",
        "NOTEBOOKLM_KEEP_RECENT_DAYS",
        "STATE_DATABASE_URL",
        "DIGEST_STATE_TABLE",
        "DIGEST_TIMEZONE",
        "DIGEST_CRON",
        "DIGEST_RANDOM_DELAY_MINUTES_MIN",
        "DIGEST_RANDOM_DELAY_MINUTES_MAX",
        "AUDIO_OVERVIEW_TIMEOUT_SECONDS",
        "TELEGRAM_LINK_LIMIT",
    }

    missing = [name for name in sorted(required_names) if f"{name}=" not in env_text]
    assert missing == []


def test_trigger_python_requirements_include_digest_dependencies() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package_name in [
        "telethon",
        "notebooklm-py",
        "httpx",
        "psycopg[binary]",
    ]:
        assert package_name in requirements
