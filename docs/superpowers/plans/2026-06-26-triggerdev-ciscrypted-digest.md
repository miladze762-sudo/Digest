# План реализации ежедневного дайджеста ciscrypted

> **Для агентных исполнителей:** ОБЯЗАТЕЛЬНЫЙ SUB-SKILL: используйте `superpowers:subagent-driven-development` (рекомендуется) или `superpowers:executing-plans`, чтобы выполнять план по задачам. Для отслеживания шагов используется синтаксис checkbox (`- [ ]`).

**Цель:** Построить Trigger.dev-пайплайн, который ежедневно берет последний дайджест `ciscrypted`, извлекает текст постов из других Telegram-каналов по ссылкам в дайджесте, создает NotebookLM-блокнот, генерирует Audio Overview и отправляет MP3 в Telegram без дублей при повторах.

**Архитектура:** TypeScript отвечает за Trigger.dev schedule wrapper, idempotent processor task и запуск Python CLI через `@trigger.dev/python`. Python-пакет `digest` содержит доменную модель, чтение Telegram, извлечение ссылок на Telegram-посты, чтение связанных постов через Telethon, `state_store`, NotebookLM/Telegram-клиенты, preflight и orchestration. Внешние side effects идут через явные checkpoints в `state_store`: cleanup, создание блокнота, добавление источников, генерация/скачивание аудио и отправка MP3. Внешние сайты по ссылкам не скачиваются: ссылки первого поста считаются ссылками на посты в других Telegram-каналах.

**Технологический стек:** Trigger.dev SDK `4.4.x`, `@trigger.dev/sdk/v3`, `@trigger.dev/python`, TypeScript, Vitest, Python 3.11+, pytest, Telethon, httpx, notebooklm-py, psycopg, ffmpeg.

---

## Источники

- Спека: `docs/superpowers/specs/2026-06-26-triggerdev-telegram-notebooklm-digest-design.md`
- Уточнение пользователя от 2026-06-26: ссылки в первом посте ведут на посты в других Telegram-каналах; данные нужно извлекать из этих Telegram-постов, а не с сайтов.
- Локальная инструкция деплоя: `docs/triggerdev-script-deploy-instructions.md`
- `notebooklm-py` Python API: `https://github.com/teng-lin/notebooklm-py/blob/main/docs/python-api.md` (`NotebookLMClient.from_storage()`, `client.notebooks.create()`, `client.sources.add_text()`, `client.artifacts.generate_audio()`, `client.artifacts.wait_for_completion()`, `client.artifacts.download_audio()`).
- Расширение Trigger.dev для Python: `https://trigger.dev/docs/config/extensions/pythonExtension` (`pythonExtension({ scripts, requirementsFile })`, `python.runScript()`).
- Расширение Trigger.dev для FFmpeg: `https://trigger.dev/docs/config/extensions/ffmpeg`.

## Граница этого плана

Этот план дает рабочую версию без извлечения внешних сайтов: пайплайн получает последний дайджест-пост `ciscrypted`, берет из него `https://t.me/.../...` ссылки, читает соответствующие посты других Telegram-каналов через Telethon и добавляет их текст в NotebookLM. `TELEGRAM_SESSION_STRING` должен принадлежать аккаунту, который имеет доступ к связанным каналам. Ссылки, которые не являются публичными ссылками на Telegram-посты или недоступны текущей Telegram-сессии, фиксируются как ошибки извлечения в отчете и Trigger.dev metadata.

## Архитектурное решение по retries и дублям

`notebooklm-py` делает `client.notebooks.create()` retry-safe, но `client.sources.add_text()` не является retry-safe: у текстового источника нет надежного server-side dedupe key. Поэтому план не пытается повторно добавлять текстовые источники в уже частично заполненный блокнот. Если run прервался в статусе `sources_adding`, следующий запуск сначала удаляет частичный блокнот и создает новый. Trade-off: мы платим дополнительным удалением/пересозданием блокнота и возможной ручной очисткой, если удаление недоступно, зато финальный блокнот не получает дубликаты источников.

Для `forceReprocess` используется новый attempt id: обычный run имеет ключ `ciscrypted:YYYY-MM-DD`, а forced run — `ciscrypted:YYYY-MM-DD:force:<uuid>`. `state_store` хранит записи по `idempotency_key`, а текущий активный результат выбирается по `target_date` среди записей, не помеченных `superseded`. При forced run предыдущая активная запись помечается `superseded`, новая становится активной.

## Структура файлов

- Создать: `package.json` — npm scripts и зависимости Trigger.dev/Vitest.
- Создать: `tsconfig.json` — TypeScript настройки для Trigger.dev и тестов.
- Создать: `trigger.config.ts` — конфиг проекта Trigger.dev, `pythonExtension`, `ffmpeg`.
- Создать: `.env.example` — публичный env-контракт без секретов.
- Создать: `.gitignore` — локальные env, Python cache и runtime-артефакты.
- Создать: `requirements.txt` — Python зависимости, которые реально читает Trigger.dev.
- Создать: `pytest.ini` — pytest path и async-режим.
- Создать: `pyproject.toml` — минимальная конфигурация Python-инструментов.
- Создать: `src/digest/__init__.py` — пакет Python-пайплайна.
- Создать: `src/digest/models.py` — статусы, dataclass-модели и JSON helpers.
- Создать: `src/digest/config.py` — чтение env и валидация настроек.
- Создать: `src/digest/url_extractor.py` — извлечение и дедупликация URL.
- Создать: `src/digest/telegram_reader.py` — выбор дневного Telegram-сообщения.
- Создать: `src/digest/state_store.py` — durable state interface и PostgreSQL-реализация.
- Создать: `src/digest/telegram_post_extractor.py` — разбор ссылок `t.me` и извлечение текста связанных Telegram-постов.
- Создать: `src/digest/run_report.py` — сжатая metadata-проекция для Trigger.dev.
- Создать: `src/digest/notebook_cleanup.py` — выбор старых NotebookLM-блокнотов для удаления.
- Создать: `src/digest/notebooklm_client.py` — NotebookLM-адаптер, загрузка источников, Audio Overview, MP3-конвертация.
- Создать: `src/digest/telegram_bot_sender.py` — отправка через Telegram Bot API и HTML-подпись.
- Создать: `src/digest/preflight.py` — проверка runtime-контракта до side effects.
- Создать: `src/digest/pipeline.py` — orchestration с idempotency checkpoints.
- Создать: `src/trigger/digestSchedule.ts` — вычисление дат, окна запуска и idempotency key.
- Создать: `src/trigger/ciscryptedDigest.ts` — `scheduleDigestWindow` и `processDigestForDate`.
- Создать: `src/trigger/run_ciscrypted_digest.py` — CLI-точка входа для Trigger.dev.
- Создать: `scripts/notebooklm_smoke.py` — безопасный NotebookLM smoke-test.
- Создать: `scripts/telegram_bot_smoke.py` — безопасный Telegram Bot smoke-test.
- Создать: `scripts/dry_run_digest.py` — integration dry-run без NotebookLM и MP3.
- Создать: `tests/*.py` — Python unit-тесты.
- Создать: `src/trigger/*.test.ts` — TypeScript unit-тесты.
- Создать: `README.md` — локальный запуск, env, dry-run и deploy checklist.

### Задача 1: Каркас проекта и runtime-контракт

**Файлы:**
- Создать: `package.json`
- Создать: `tsconfig.json`
- Создать: `trigger.config.ts`
- Создать: `.env.example`
- Создать: `.gitignore`
- Создать: `requirements.txt`
- Создать: `pytest.ini`
- Создать: `pyproject.toml`
- Создать: `src/digest/__init__.py`
- Тест: `tests/test_env_contract.py`

- [ ] **Шаг 1: Написать падающий тест env-контракта**

Создать `tests/test_env_contract.py`:

```python
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
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Команда: `python -m pytest tests/test_env_contract.py -v`

Ожидаемо: FAIL, потому что `.env.example` и `requirements.txt` еще не существуют.

- [ ] **Шаг 3: Добавить файлы каркаса**

Создать `package.json`:

```json
{
  "name": "ciscrypted-digest-triggerdev",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run && python -m pytest",
    "test:trigger": "vitest run src/trigger",
    "test:python": "python -m pytest",
    "trigger:dry-run": "npx trigger.dev@4.4.6 deploy --dry-run",
    "trigger:deploy": "npx trigger.dev@4.4.6 deploy"
  },
  "dependencies": {
    "@trigger.dev/python": "4.4.6",
    "@trigger.dev/sdk": "4.4.6",
    "luxon": "3.5.0"
  },
  "devDependencies": {
    "@trigger.dev/build": "4.4.6",
    "@types/node": "22.13.1",
    "typescript": "5.7.3",
    "trigger.dev": "4.4.6",
    "vitest": "2.1.8"
  }
}
```

Создать `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "types": ["node", "vitest/globals"]
  },
  "include": ["src/**/*.ts", "trigger.config.ts"]
}
```

Создать `trigger.config.ts`:

```ts
import { defineConfig } from "@trigger.dev/sdk/v3";
import { pythonExtension } from "@trigger.dev/python/extension";
import { ffmpeg } from "@trigger.dev/build/extensions/core";

const project = process.env.TRIGGER_PROJECT_REF;

if (!project) {
  throw new Error("TRIGGER_PROJECT_REF обязателен для Trigger.dev build");
}

export default defineConfig({
  project,
  dirs: ["./src/trigger"],
  build: {
    extensions: [
      pythonExtension({
        scripts: ["./src/**/*.py", "./scripts/**/*.py"],
        requirementsFile: "./requirements.txt",
      }),
      ffmpeg(),
    ],
  },
});
```

Создать `.env.example`:

```env
TRIGGER_PROJECT_REF=

TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION_STRING=
TELEGRAM_SOURCE_CHANNEL=ciscrypted

TELEGRAM_BOT_TOKEN=
TELEGRAM_TARGET_CHAT_ID=

NOTEBOOKLM_AUTH_JSON=
NOTEBOOKLM_ACCOUNT_EMAIL=
NOTEBOOKLM_MAX_NOTEBOOKS=50
NOTEBOOKLM_CLEANUP_THRESHOLD=45
NOTEBOOKLM_CLEANUP_TARGET=40
NOTEBOOKLM_KEEP_RECENT_DAYS=7
NOTEBOOKLM_AUDIO_LANGUAGE=ru

STATE_DATABASE_URL=
DIGEST_STATE_TABLE=digest_runs

DIGEST_TIMEZONE=Europe/Moscow
DIGEST_CRON=0 2 * * *
DIGEST_RANDOM_WINDOW_START=02:00
DIGEST_RANDOM_WINDOW_END=04:00
DIGEST_RANDOM_DELAY_MINUTES_MIN=0
DIGEST_RANDOM_DELAY_MINUTES_MAX=120
AUDIO_OVERVIEW_TIMEOUT_SECONDS=1200
TELEGRAM_LINK_LIMIT=50
```

Создать `.gitignore`:

```gitignore
.env
.env.*
!.env.example
node_modules/
.trigger/
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
*.pyc
*.mp3
*.mp4
runtime/
credentials/
```

Создать `requirements.txt`:

```text
telethon
notebooklm-py
httpx
psycopg[binary]
pytest
pytest-asyncio
```

Создать `pytest.ini`:

```ini
[pytest]
pythonpath = src
asyncio_mode = auto
```

Создать `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
```

Создать `src/digest/__init__.py`:

```python
"""Пайплайн ежедневного дайджеста ciscrypted."""
```

- [ ] **Шаг 4: Запустить тест каркаса и убедиться, что он проходит**

Команда: `python -m pytest tests/test_env_contract.py -v`

Ожидаемо: PASS.

- [ ] **Шаг 5: Закоммитить каркас**

Команда:

```powershell
git status --short
git add package.json tsconfig.json trigger.config.ts .env.example .gitignore requirements.txt pytest.ini pyproject.toml src/digest/__init__.py tests/test_env_contract.py
git commit -m "chore: scaffold Trigger.dev digest project"
```

Ожидаемо: коммит проходит. Если `git status` сообщает, что каталог не является Git-репозиторием, зафиксировать список измененных файлов в отчете и продолжить без коммита.

### Задача 2: Доменные модели и конфигурация

**Файлы:**
- Создать: `src/digest/models.py`
- Создать: `src/digest/config.py`
- Тест: `tests/test_config.py`
- Тест: `tests/test_models.py`

- [ ] **Шаг 1: Написать падающие тесты для config и сериализации моделей**

Создать `tests/test_config.py`:

```python
from __future__ import annotations

import pytest

from digest.config import DigestSettings


def test_settings_from_env_reads_numbers_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_TARGET_CHAT_ID", "42")
    monkeypatch.setenv("NOTEBOOKLM_AUTH_JSON", '{"cookies":[],"origins":[]}')
    monkeypatch.setenv("NOTEBOOKLM_ACCOUNT_EMAIL", "user@example.com")
    monkeypatch.setenv("STATE_DATABASE_URL", "postgresql://user:pass@localhost:5432/digest")

    settings = DigestSettings.from_env()

    assert settings.telegram_api_id == 123
    assert settings.telegram_source_channel == "ciscrypted"
    assert settings.digest_timezone == "Europe/Moscow"
    assert settings.notebooklm_cleanup_threshold == 45
    assert settings.telegram_link_limit == 50


def test_settings_rejects_missing_required_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)

    with pytest.raises(ValueError, match="TELEGRAM_API_HASH"):
        DigestSettings.from_env()
```

Создать `tests/test_models.py`:

```python
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from digest.models import ExtractedTelegramPost, PostStatus, TelegramDigestMessage


def test_post_metadata_excludes_full_text() -> None:
    post = ExtractedTelegramPost(
        url="https://t.me/otherchannel/123",
        channel="otherchannel",
        message_id=123,
        title="Заголовок",
        text="Очень длинный текст поста",
        extraction_method="telegram",
        status=PostStatus.EXTRACTED,
        error=None,
    )

    assert post.to_metadata() == {
        "url": "https://t.me/otherchannel/123",
        "channel": "otherchannel",
        "messageId": 123,
        "title": "Заголовок",
        "status": "extracted",
        "extractionMethod": "telegram",
        "textLength": 25,
        "error": None,
    }


def test_digest_message_builds_public_url() -> None:
    message = TelegramDigestMessage(
        message_id=12345,
        text="https://t.me/otherchannel/123",
        published_at=datetime(2026, 6, 25, 21, 10, tzinfo=ZoneInfo("Europe/Moscow")),
        urls=["https://t.me/otherchannel/123"],
    )

    assert message.public_url == "https://t.me/ciscrypted/12345"
```

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Команда: `python -m pytest tests/test_config.py tests/test_models.py -v`

Ожидаемо: FAIL, потому что `digest.config` и `digest.models` еще не существуют.

- [ ] **Шаг 3: Реализовать модели**

Создать `src/digest/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal


class PostStatus(StrEnum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED_EXTRACTION = "failed_extraction"
    ADDED_TO_NOTEBOOK = "added_to_notebook"


class NotebookStatus(StrEnum):
    PENDING = "pending"
    CREATED = "created"
    FAILED = "failed"


class AudioStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    DOWNLOADED = "downloaded"
    SENT_TO_TELEGRAM = "sent_to_telegram"
    FAILED = "failed"


class RunStatus(StrEnum):
    PENDING = "pending"
    NO_DIGEST_MESSAGE = "no_digest_message"
    NO_VALID_POSTS = "no_valid_posts"
    CLEANUP_REQUIRED = "cleanup_required"
    NOTEBOOK_CREATED = "notebook_created"
    SOURCES_ADDING = "sources_adding"
    SOURCES_ADDED = "sources_added"
    AUDIO_DOWNLOADED = "audio_downloaded"
    TELEGRAM_SENDING = "telegram_sending"
    SENT_TO_TELEGRAM = "sent_to_telegram"
    FAILED = "failed"
    SUPERSEDED = "superseded"


ExtractionMethod = Literal["telegram"]


@dataclass(frozen=True)
class TelegramDigestMessage:
    message_id: int
    text: str
    published_at: datetime
    urls: list[str]

    @property
    def public_url(self) -> str:
        return f"https://t.me/ciscrypted/{self.message_id}"


@dataclass(frozen=True)
class TelegramPostLink:
    url: str
    channel: str
    message_id: int


@dataclass
class ExtractedTelegramPost:
    url: str
    channel: str
    message_id: int
    title: str | None
    text: str
    extraction_method: ExtractionMethod
    status: PostStatus
    error: str | None = None

    @property
    def text_length(self) -> int:
        return len(self.text)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "channel": self.channel,
            "messageId": self.message_id,
            "title": self.title,
            "status": self.status.value,
            "extractionMethod": self.extraction_method,
            "textLength": self.text_length,
            "error": self.error,
        }


@dataclass
class DigestRunState:
    target_date: str
    idempotency_key: str
    status: RunStatus = RunStatus.PENDING
    digest_message_id: int | None = None
    digest_message_url: str | None = None
    notebook_id: str | None = None
    notebook_url: str | None = None
    notebook_name: str | None = None
    notebook_protected: bool = False
    notebook_source_count: int = 0
    cleanup_required: bool = False
    audio_file_path: str | None = None
    audio_file_size_bytes: int | None = None
    audio_telegram_message_id: int | None = None
    post_count: int = 0
    post_error_count: int = 0
    last_error: str | None = None
    superseded_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def completed(self) -> bool:
        return self.status == RunStatus.SENT_TO_TELEGRAM and self.audio_telegram_message_id is not None

    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        for key in ["created_at", "updated_at"]:
            if isinstance(data[key], datetime):
                data[key] = data[key].isoformat()
        return data


@dataclass(frozen=True)
class NotebookInfo:
    id: str
    url: str
    name: str
    account_email: str


@dataclass(frozen=True)
class AudioInfo:
    path: str
    file_size_bytes: int


@dataclass(frozen=True)
class CleanupSummary:
    notebook_count_before: int
    deleted_notebook_count: int
    notebook_count_after: int
    deleted_notebook_ids: list[str]
    cleanup_required: bool = False
```

- [ ] **Шаг 4: Реализовать config**

Создать `src/digest/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise ValueError(f"{name} is required")
    return value


def _int_env(name: str, default: int | None = None) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        if default is None:
            raise ValueError(f"{name} is required")
        return default
    return int(value)


@dataclass(frozen=True)
class DigestSettings:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_string: str
    telegram_source_channel: str
    telegram_link_limit: int
    telegram_bot_token: str
    telegram_target_chat_id: str
    notebooklm_auth_json: str
    notebooklm_account_email: str
    notebooklm_max_notebooks: int
    notebooklm_cleanup_threshold: int
    notebooklm_cleanup_target: int
    notebooklm_keep_recent_days: int
    notebooklm_audio_language: str
    state_database_url: str
    digest_state_table: str
    digest_timezone: str
    digest_cron: str
    random_delay_min_minutes: int
    random_delay_max_minutes: int
    audio_overview_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "DigestSettings":
        return cls(
            telegram_api_id=_int_env("TELEGRAM_API_ID"),
            telegram_api_hash=_required("TELEGRAM_API_HASH"),
            telegram_session_string=_required("TELEGRAM_SESSION_STRING"),
            telegram_source_channel=os.getenv("TELEGRAM_SOURCE_CHANNEL", "ciscrypted"),
            telegram_link_limit=_int_env("TELEGRAM_LINK_LIMIT", 50),
            telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
            telegram_target_chat_id=_required("TELEGRAM_TARGET_CHAT_ID"),
            notebooklm_auth_json=_required("NOTEBOOKLM_AUTH_JSON"),
            notebooklm_account_email=_required("NOTEBOOKLM_ACCOUNT_EMAIL"),
            notebooklm_max_notebooks=_int_env("NOTEBOOKLM_MAX_NOTEBOOKS", 50),
            notebooklm_cleanup_threshold=_int_env("NOTEBOOKLM_CLEANUP_THRESHOLD", 45),
            notebooklm_cleanup_target=_int_env("NOTEBOOKLM_CLEANUP_TARGET", 40),
            notebooklm_keep_recent_days=_int_env("NOTEBOOKLM_KEEP_RECENT_DAYS", 7),
            notebooklm_audio_language=os.getenv("NOTEBOOKLM_AUDIO_LANGUAGE", "ru"),
            state_database_url=_required("STATE_DATABASE_URL"),
            digest_state_table=os.getenv("DIGEST_STATE_TABLE", "digest_runs"),
            digest_timezone=os.getenv("DIGEST_TIMEZONE", "Europe/Moscow"),
            digest_cron=os.getenv("DIGEST_CRON", "0 2 * * *"),
            random_delay_min_minutes=_int_env("DIGEST_RANDOM_DELAY_MINUTES_MIN", 0),
            random_delay_max_minutes=_int_env("DIGEST_RANDOM_DELAY_MINUTES_MAX", 120),
            audio_overview_timeout_seconds=_int_env("AUDIO_OVERVIEW_TIMEOUT_SECONDS", 1200),
        )
```

- [ ] **Шаг 5: Запустить тесты и убедиться, что они проходят**

Команда: `python -m pytest tests/test_config.py tests/test_models.py -v`

Ожидаемо: PASS.

- [ ] **Шаг 6: Закоммитить модели и config**

Команда:

```powershell
git add src/digest/models.py src/digest/config.py tests/test_config.py tests/test_models.py
git commit -m "feat: add digest domain models and config"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 3: Извлечение URL и выбор Telegram-сообщения

**Файлы:**
- Создать: `src/digest/url_extractor.py`
- Создать: `src/digest/telegram_reader.py`
- Тест: `tests/test_url_extractor.py`
- Тест: `tests/test_telegram_reader.py`

- [ ] **Шаг 1: Написать падающие тесты извлечения URL**

Создать `tests/test_url_extractor.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from digest.url_extractor import extract_urls


@dataclass(frozen=True)
class Entity:
    offset: int
    length: int
    url: str | None = None


def test_extract_urls_deduplicates_and_preserves_order() -> None:
    text = (
        "Первое https://t.me/channelone/101, второе https://t.me/channeltwo/202 "
        "и дубль https://t.me/channelone/101."
    )

    assert extract_urls(text) == ["https://t.me/channelone/101", "https://t.me/channeltwo/202"]


def test_extract_urls_reads_text_url_entities() -> None:
    text = "Читать пост"
    entities = [Entity(offset=0, length=11, url="https://t.me/channelone/303")]

    assert extract_urls(text, entities=entities) == ["https://t.me/channelone/303"]


def test_extract_urls_ignores_invalid_schemes() -> None:
    text = "ftp://t.me/channelone/101 https://t.me/channelone/101"

    assert extract_urls(text) == ["https://t.me/channelone/101"]
```

- [ ] **Шаг 2: Написать падающие тесты выбора Telegram-сообщения**

Создать `tests/test_telegram_reader.py`:

```python
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from digest.models import TelegramDigestMessage
from digest.telegram_reader import select_latest_digest_message


MSK = ZoneInfo("Europe/Moscow")


def test_select_latest_digest_message_for_target_date() -> None:
    messages = [
        TelegramDigestMessage(1, "https://t.me/oldchannel/10", datetime(2026, 6, 25, 9, 0, tzinfo=MSK), ["https://t.me/oldchannel/10"]),
        TelegramDigestMessage(2, "без ссылок", datetime(2026, 6, 25, 10, 0, tzinfo=MSK), []),
        TelegramDigestMessage(3, "https://t.me/newchannel/20", datetime(2026, 6, 25, 21, 0, tzinfo=MSK), ["https://t.me/newchannel/20"]),
        TelegramDigestMessage(4, "https://t.me/tomorrowchannel/30", datetime(2026, 6, 26, 1, 0, tzinfo=MSK), ["https://t.me/tomorrowchannel/30"]),
    ]

    selected = select_latest_digest_message(messages, target_date="2026-06-25", timezone_name="Europe/Moscow")

    assert selected is not None
    assert selected.message_id == 3


def test_select_latest_digest_message_returns_none_when_no_links() -> None:
    messages = [
        TelegramDigestMessage(1, "без ссылок", datetime(2026, 6, 25, 9, 0, tzinfo=MSK), []),
    ]

    assert select_latest_digest_message(messages, target_date="2026-06-25", timezone_name="Europe/Moscow") is None
```

- [ ] **Шаг 3: Запустить тесты и убедиться, что они падают**

Команда: `python -m pytest tests/test_url_extractor.py tests/test_telegram_reader.py -v`

Ожидаемо: FAIL, потому что модули еще не созданы.

- [ ] **Шаг 4: Реализовать извлечение URL**

Создать `src/digest/url_extractor.py`:

```python
from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlparse


URL_RE = re.compile(r"https?://[^\s<>'\"`]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?)]}»"


def _clean_url(url: str) -> str:
    return url.rstrip(TRAILING_PUNCTUATION)


def _is_valid_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _entity_url(entity: Any, text: str) -> str | None:
    explicit_url = getattr(entity, "url", None)
    if explicit_url:
        return str(explicit_url)
    offset = getattr(entity, "offset", None)
    length = getattr(entity, "length", None)
    if isinstance(offset, int) and isinstance(length, int):
        return text[offset : offset + length]
    return None


def extract_urls(text: str, entities: Iterable[Any] | None = None) -> list[str]:
    candidates: list[str] = []
    candidates.extend(match.group(0) for match in URL_RE.finditer(text or ""))

    for entity in entities or []:
        entity_url = _entity_url(entity, text or "")
        if entity_url:
            candidates.append(entity_url)

    seen: set[str] = set()
    urls: list[str] = []
    for candidate in candidates:
        cleaned = _clean_url(candidate)
        if _is_valid_http_url(cleaned) and cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    return urls
```

- [ ] **Шаг 5: Реализовать выбор сообщения в telegram_reader и Telethon adapter**

Создать `src/digest/telegram_reader.py`:

```python
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from telethon import TelegramClient
from telethon.sessions import StringSession

from digest.models import TelegramDigestMessage
from digest.url_extractor import extract_urls


def select_latest_digest_message(
    messages: list[TelegramDigestMessage],
    *,
    target_date: str,
    timezone_name: str,
) -> TelegramDigestMessage | None:
    timezone = ZoneInfo(timezone_name)
    candidates: list[TelegramDigestMessage] = []
    for message in messages:
        published_date = message.published_at.astimezone(timezone).date().isoformat()
        if published_date == target_date and message.urls:
            candidates.append(message)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.published_at, item.message_id))


async def fetch_channel_messages_for_date(
    *,
    api_id: int,
    api_hash: str,
    session_string: str,
    channel: str,
    target_date: str,
    timezone_name: str,
    limit: int = 200,
) -> list[TelegramDigestMessage]:
    timezone = ZoneInfo(timezone_name)
    day = datetime.fromisoformat(target_date).date()
    start = datetime.combine(day, time.min, tzinfo=timezone)
    end = datetime.combine(day, time.max, tzinfo=timezone)

    messages: list[TelegramDigestMessage] = []
    async with TelegramClient(StringSession(session_string), api_id, api_hash) as client:
        async for raw_message in client.iter_messages(channel, limit=limit):
            published_at = raw_message.date.astimezone(timezone)
            if published_at < start:
                break
            if start <= published_at <= end:
                text = raw_message.message or ""
                urls = extract_urls(text, entities=getattr(raw_message, "entities", None))
                messages.append(
                    TelegramDigestMessage(
                        message_id=int(raw_message.id),
                        text=text,
                        published_at=published_at,
                        urls=urls,
                    )
                )
    return messages
```

- [ ] **Шаг 6: Запустить тесты и убедиться, что они проходят**

Команда: `python -m pytest tests/test_url_extractor.py tests/test_telegram_reader.py -v`

Ожидаемо: PASS.

- [ ] **Шаг 7: Закоммитить URL extraction и выбор Telegram-сообщения**

Команда:

```powershell
git add src/digest/url_extractor.py src/digest/telegram_reader.py tests/test_url_extractor.py tests/test_telegram_reader.py
git commit -m "feat: select ciscrypted digest message"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 4: Trigger helpers расписания и tasks

**Файлы:**
- Создать: `src/trigger/digestSchedule.ts`
- Создать: `src/trigger/ciscryptedDigest.ts`
- Тест: `src/trigger/digestSchedule.test.ts`

- [ ] **Шаг 1: Написать падающие TypeScript-тесты расписания**

Создать `src/trigger/digestSchedule.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  buildDigestIdempotencyKey,
  chooseRandomDelayMinutes,
  plannedStartAt,
  targetDateForScheduledRun,
} from "./digestSchedule.js";

describe("digest schedule helpers", () => {
  it("computes previous Moscow calendar date", () => {
    const scheduledAt = new Date("2026-06-26T00:30:00.000Z");

    expect(targetDateForScheduledRun(scheduledAt, "Europe/Moscow")).toBe("2026-06-25");
  });

  it("builds the global idempotency key", () => {
    expect(buildDigestIdempotencyKey("2026-06-25")).toBe("ciscrypted:2026-06-25");
  });

  it("keeps random delay inside the configured inclusive range", () => {
    const value = chooseRandomDelayMinutes(0, 120, () => 77);

    expect(value).toBe(77);
  });

  it("computes planned start from schedule timestamp and delay", () => {
    const scheduledAt = new Date("2026-06-25T23:00:00.000Z");

    expect(plannedStartAt(scheduledAt, 77).toISOString()).toBe("2026-06-26T00:17:00.000Z");
  });
});
```

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Команда: `npm run test:trigger`

Ожидаемо: FAIL, потому что `digestSchedule.ts` еще не существует.

- [ ] **Шаг 3: Реализовать helpers расписания**

Создать `src/trigger/digestSchedule.ts`:

```ts
import { randomInt } from "node:crypto";
import { DateTime } from "luxon";

export type RandomIntFn = (minInclusive: number, maxExclusive: number) => number;

export function targetDateForScheduledRun(timestamp: Date, timezone: string): string {
  const scheduled = DateTime.fromJSDate(timestamp, { zone: "utc" }).setZone(timezone);
  const target = scheduled.minus({ days: 1 }).toISODate();
  if (!target) {
    throw new Error("Не удалось вычислить target date");
  }
  return target;
}

export function buildDigestIdempotencyKey(targetDate: string): string {
  return `ciscrypted:${targetDate}`;
}

export function chooseRandomDelayMinutes(
  minMinutes: number,
  maxMinutes: number,
  random: RandomIntFn = randomInt,
): number {
  if (minMinutes < 0) {
    throw new Error("minMinutes must be non-negative");
  }
  if (maxMinutes < minMinutes) {
    throw new Error("maxMinutes must be greater than or equal to minMinutes");
  }
  return random(minMinutes, maxMinutes + 1);
}

export function plannedStartAt(scheduledAt: Date, delayMinutes: number): Date {
  return new Date(scheduledAt.getTime() + delayMinutes * 60_000);
}
```

- [ ] **Шаг 4: Реализовать Trigger.dev tasks**

Создать `src/trigger/ciscryptedDigest.ts`:

```ts
import { randomUUID } from "node:crypto";
import { idempotencyKeys, logger, schedules, task } from "@trigger.dev/sdk/v3";
import { python } from "@trigger.dev/python";
import {
  buildDigestIdempotencyKey,
  chooseRandomDelayMinutes,
  plannedStartAt,
  targetDateForScheduledRun,
} from "./digestSchedule.js";

type ProcessDigestPayload = {
  targetDate: string;
  plannedStartAt: string;
  randomDelayMinutes: number;
  forceReprocess?: boolean;
  forceAttemptId?: string;
};

function intEnv(name: string, defaultValue: number): number {
  const value = process.env[name];
  return value ? Number.parseInt(value, 10) : defaultValue;
}

export const processDigestForDate = task({
  id: "process-ciscrypted-digest-for-date",
  queue: {
    concurrencyLimit: 1,
  },
  retry: {
    maxAttempts: 2,
  },
  maxDuration: 7200,
  run: async (payload: ProcessDigestPayload) => {
    const args = [
      "--target-date",
      payload.targetDate,
      "--planned-start-at",
      payload.plannedStartAt,
      "--random-delay-minutes",
      String(payload.randomDelayMinutes),
    ];

    if (payload.forceReprocess) {
      args.push("--force-reprocess");
      args.push("--force-attempt-id");
      args.push(payload.forceAttemptId ?? randomUUID());
    }

    const result = await python.runScript("./src/trigger/run_ciscrypted_digest.py", args, {
      env: {
        ...process.env,
      },
    });

    if (result.stderr) {
      logger.warn("digest python stderr", { stderr: result.stderr });
    }

    const output = JSON.parse(result.stdout || "{}");
    logger.info("digest completed", output);
    return output;
  },
});

export const scheduleDigestWindow = schedules.task({
  id: "schedule-ciscrypted-digest-window",
  cron: {
    pattern: process.env.DIGEST_CRON ?? "0 2 * * *",
    timezone: process.env.DIGEST_TIMEZONE ?? "Europe/Moscow",
    environments: ["PRODUCTION"],
  },
  ttl: "30m",
  run: async (payload) => {
    const timezone = process.env.DIGEST_TIMEZONE ?? "Europe/Moscow";
    const targetDate = targetDateForScheduledRun(payload.timestamp, timezone);
    const randomDelayMinutes = chooseRandomDelayMinutes(
      intEnv("DIGEST_RANDOM_DELAY_MINUTES_MIN", 0),
      intEnv("DIGEST_RANDOM_DELAY_MINUTES_MAX", 120),
    );
    const planned = plannedStartAt(payload.timestamp, randomDelayMinutes);
    const rawKey = buildDigestIdempotencyKey(targetDate);
    const idempotencyKey = await idempotencyKeys.create(rawKey, { scope: "global" });

    const handle = await processDigestForDate.trigger(
      {
        targetDate,
        plannedStartAt: planned.toISOString(),
        randomDelayMinutes,
      },
      {
        delay: `${randomDelayMinutes}m`,
        idempotencyKey,
        idempotencyKeyTTL: "35d",
      },
    );

    const metadata = {
      targetDate,
      sourceChannel: process.env.TELEGRAM_SOURCE_CHANNEL ?? "ciscrypted",
      schedule: {
        plannedStartAt: planned.toISOString(),
        randomDelayMinutes,
      },
      processorRunId: handle.id,
    };

    logger.info("scheduled ciscrypted digest processor", metadata);
    return metadata;
  },
});
```

- [ ] **Шаг 5: Запустить TypeScript-тесты**

Команда: `npm run test:trigger`

Ожидаемо: PASS.

- [ ] **Шаг 6: Закоммитить Trigger schedule tasks**

Команда:

```powershell
git add src/trigger/digestSchedule.ts src/trigger/ciscryptedDigest.ts src/trigger/digestSchedule.test.ts
git commit -m "feat: add Trigger.dev digest schedule"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 5: State store и metadata запуска

**Файлы:**
- Создать: `src/digest/state_store.py`
- Создать: `src/digest/run_report.py`
- Тест: `tests/test_state_store.py`
- Тест: `tests/test_run_report.py`

- [ ] **Шаг 1: Написать падающие тесты state_store**

Создать `tests/test_state_store.py`:

```python
from __future__ import annotations

import pytest

from digest.models import RunStatus
from digest.state_store import InMemoryStateStore


@pytest.mark.asyncio
async def test_get_or_create_run_is_idempotent() -> None:
    store = InMemoryStateStore()

    first = await store.get_or_create_run("2026-06-25", "ciscrypted:2026-06-25")
    first.status = RunStatus.SENT_TO_TELEGRAM
    first.audio_telegram_message_id = 98765
    await store.save_run(first)

    second = await store.get_or_create_run("2026-06-25", "ciscrypted:2026-06-25")

    assert second.status == RunStatus.SENT_TO_TELEGRAM
    assert second.audio_telegram_message_id == 98765


@pytest.mark.asyncio
async def test_force_reprocess_creates_attempt_key() -> None:
    store = InMemoryStateStore()

    original = await store.get_or_create_run("2026-06-25", "ciscrypted:2026-06-25")
    forced = await store.get_or_create_run("2026-06-25", "ciscrypted:2026-06-25:force:abc")

    assert forced.idempotency_key == "ciscrypted:2026-06-25:force:abc"
    superseded = await store.get_run_by_key(original.idempotency_key)
    assert superseded is not None
    assert superseded.status == RunStatus.SUPERSEDED
    assert superseded.superseded_by == forced.idempotency_key


@pytest.mark.asyncio
async def test_lists_protected_notebook_ids() -> None:
    store = InMemoryStateStore()
    state = await store.get_or_create_run("2026-06-25", "ciscrypted:2026-06-25")
    state.notebook_id = "protected-nb"
    state.notebook_protected = True
    await store.save_run(state)

    assert await store.list_protected_notebook_ids() == {"protected-nb"}
```

Создать `tests/test_run_report.py`:

```python
from __future__ import annotations

from digest.models import CleanupSummary, ExtractedTelegramPost, NotebookInfo, PostStatus, RunStatus
from digest.run_report import build_trigger_metadata


def test_metadata_omits_full_post_text() -> None:
    post = ExtractedTelegramPost(
        url="https://t.me/otherchannel/123",
        channel="otherchannel",
        message_id=123,
        title="A",
        text="Секретный полный текст",
        extraction_method="telegram",
        status=PostStatus.EXTRACTED,
    )

    metadata = build_trigger_metadata(
        target_date="2026-06-25",
        source_channel="ciscrypted",
        run_status=RunStatus.NOTEBOOK_CREATED,
        posts=[post],
        notebook=NotebookInfo("nb1", "https://notebooklm.google.com/notebook/nb1", "ciscrypted 2026-06-25", "user@example.com"),
        cleanup=CleanupSummary(45, 5, 40, ["old1"]),
        schedule={"randomDelayMinutes": 77},
    )

    assert metadata["posts"][0]["textLength"] == 22
    assert "Секретный полный текст" not in str(metadata)
```

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Команда: `python -m pytest tests/test_state_store.py tests/test_run_report.py -v`

Ожидаемо: FAIL, потому что модули еще не созданы.

- [ ] **Шаг 3: Реализовать state_store**

Создать `src/digest/state_store.py`:

```python
from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from digest.models import DigestRunState, RunStatus


TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_table_name(table_name: str) -> str:
    if not TABLE_NAME_RE.match(table_name):
        raise ValueError(f"Некорректное имя таблицы state_store: {table_name}")
    return table_name


def _is_force_key(idempotency_key: str) -> bool:
    return ":force:" in idempotency_key


def _new_state(target_date: str, idempotency_key: str) -> DigestRunState:
    now = datetime.now(timezone.utc)
    return DigestRunState(
        target_date=target_date,
        idempotency_key=idempotency_key,
        created_at=now,
        updated_at=now,
    )


class StateStore(Protocol):
    async def ensure_schema(self) -> None:
        ...

    async def get_or_create_run(self, target_date: str, idempotency_key: str) -> DigestRunState:
        ...

    async def get_run_by_key(self, idempotency_key: str) -> DigestRunState | None:
        ...

    async def get_current_run(self, target_date: str) -> DigestRunState | None:
        ...

    async def list_protected_notebook_ids(self) -> set[str]:
        ...

    async def save_run(self, state: DigestRunState) -> None:
        ...


class InMemoryStateStore:
    def __init__(self) -> None:
        self._runs_by_key: dict[str, DigestRunState] = {}

    async def ensure_schema(self) -> None:
        return None

    async def get_or_create_run(self, target_date: str, idempotency_key: str) -> DigestRunState:
        exact = await self.get_run_by_key(idempotency_key)
        if exact is not None:
            return exact

        if _is_force_key(idempotency_key):
            await self._supersede_active_run(target_date, idempotency_key)
        else:
            current = await self.get_current_run(target_date)
            if current is not None:
                return current

        state = _new_state(target_date, idempotency_key)
        self._runs_by_key[idempotency_key] = deepcopy(state)
        return deepcopy(state)

    async def get_run_by_key(self, idempotency_key: str) -> DigestRunState | None:
        state = self._runs_by_key.get(idempotency_key)
        return deepcopy(state) if state is not None else None

    async def get_current_run(self, target_date: str) -> DigestRunState | None:
        candidates = [
            state
            for state in self._runs_by_key.values()
            if state.target_date == target_date and state.status != RunStatus.SUPERSEDED
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda state: state.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return deepcopy(candidates[0])

    async def list_protected_notebook_ids(self) -> set[str]:
        return {
            state.notebook_id
            for state in self._runs_by_key.values()
            if state.notebook_protected and state.notebook_id
        }

    async def save_run(self, state: DigestRunState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        self._runs_by_key[state.idempotency_key] = deepcopy(state)

    async def _supersede_active_run(self, target_date: str, superseded_by: str) -> None:
        for key, state in list(self._runs_by_key.items()):
            if state.target_date == target_date and state.status != RunStatus.SUPERSEDED:
                state.status = RunStatus.SUPERSEDED
                state.superseded_by = superseded_by
                state.updated_at = datetime.now(timezone.utc)
                self._runs_by_key[key] = deepcopy(state)


class PostgresStateStore:
    def __init__(self, database_url: str, table_name: str) -> None:
        self.database_url = database_url
        self.table_name = _validate_table_name(table_name)

    async def ensure_schema(self) -> None:
        query = f"""
        create table if not exists {self.table_name} (
            idempotency_key text primary key,
            target_date text not null,
            status text not null,
            state jsonb not null,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
        """
        index_query = f"create index if not exists {self.table_name}_target_date_idx on {self.table_name} (target_date)"
        async with await psycopg.AsyncConnection.connect(self.database_url) as conn:
            await conn.execute(query)
            await conn.execute(index_query)

    async def get_or_create_run(self, target_date: str, idempotency_key: str) -> DigestRunState:
        await self.ensure_schema()
        async with await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row) as conn:
            exact = await self._get_run_by_key(conn, idempotency_key)
            if exact is not None:
                return exact

            if _is_force_key(idempotency_key):
                await self._supersede_active_runs(conn, target_date, idempotency_key)
            else:
                current = await self._get_current_run(conn, target_date)
                if current is not None:
                    return current

            initial = _new_state(target_date, idempotency_key)
            await conn.execute(
                f"""
                insert into {self.table_name} (idempotency_key, target_date, status, state, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (idempotency_key) do nothing
                """,
                (
                    idempotency_key,
                    target_date,
                    initial.status.value,
                    json.dumps(initial.to_json_dict()),
                    initial.created_at,
                    initial.updated_at,
                ),
            )
            created = await self._get_run_by_key(conn, idempotency_key)
            if created is None:
                raise RuntimeError(f"state row не найдена для {idempotency_key}")
            return created

    async def get_run_by_key(self, idempotency_key: str) -> DigestRunState | None:
        await self.ensure_schema()
        async with await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row) as conn:
            return await self._get_run_by_key(conn, idempotency_key)

    async def get_current_run(self, target_date: str) -> DigestRunState | None:
        await self.ensure_schema()
        async with await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row) as conn:
            return await self._get_current_run(conn, target_date)

    async def list_protected_notebook_ids(self) -> set[str]:
        await self.ensure_schema()
        async with await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row) as conn:
            rows = await (
                await conn.execute(f"select state from {self.table_name} where status <> %s", (RunStatus.SUPERSEDED.value,))
            ).fetchall()
        protected: set[str] = set()
        for row in rows:
            state = _state_from_json(row["state"])
            if state.notebook_protected and state.notebook_id:
                protected.add(state.notebook_id)
        return protected

    async def save_run(self, state: DigestRunState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        async with await psycopg.AsyncConnection.connect(self.database_url) as conn:
            await conn.execute(
                f"""
                update {self.table_name}
                set status = %s, state = %s, updated_at = now()
                where idempotency_key = %s
                """,
                (state.status.value, json.dumps(state.to_json_dict()), state.idempotency_key),
            )

    async def _get_run_by_key(self, conn: psycopg.AsyncConnection, idempotency_key: str) -> DigestRunState | None:
        row = await (
            await conn.execute(f"select state from {self.table_name} where idempotency_key = %s", (idempotency_key,))
        ).fetchone()
        return _state_from_json(row["state"]) if row is not None else None

    async def _get_current_run(self, conn: psycopg.AsyncConnection, target_date: str) -> DigestRunState | None:
        row = await (
            await conn.execute(
                f"""
                select state
                from {self.table_name}
                where target_date = %s and status <> %s
                order by created_at desc
                limit 1
                """,
                (target_date, RunStatus.SUPERSEDED.value),
            )
        ).fetchone()
        return _state_from_json(row["state"]) if row is not None else None

    async def _supersede_active_runs(
        self,
        conn: psycopg.AsyncConnection,
        target_date: str,
        superseded_by: str,
    ) -> None:
        rows = await (
            await conn.execute(
                f"select state from {self.table_name} where target_date = %s and status <> %s",
                (target_date, RunStatus.SUPERSEDED.value),
            )
        ).fetchall()
        for row in rows:
            state = _state_from_json(row["state"])
            state.status = RunStatus.SUPERSEDED
            state.superseded_by = superseded_by
            state.updated_at = datetime.now(timezone.utc)
            await conn.execute(
                f"""
                update {self.table_name}
                set status = %s, state = %s, updated_at = now()
                where idempotency_key = %s
                """,
                (state.status.value, json.dumps(state.to_json_dict()), state.idempotency_key),
            )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _state_from_json(data: dict[str, object] | str) -> DigestRunState:
    raw = json.loads(data) if isinstance(data, str) else data
    def pick(camel: str, snake: str, default: object = None) -> object:
        return raw[camel] if camel in raw else raw.get(snake, default)

    return DigestRunState(
        target_date=str(pick("targetDate", "target_date")),
        idempotency_key=str(pick("idempotencyKey", "idempotency_key")),
        status=RunStatus(str(raw.get("status", RunStatus.PENDING.value))),
        digest_message_id=pick("digestMessageId", "digest_message_id"),
        digest_message_url=pick("digestMessageUrl", "digest_message_url"),
        notebook_id=pick("notebookId", "notebook_id"),
        notebook_url=pick("notebookUrl", "notebook_url"),
        notebook_name=pick("notebookName", "notebook_name"),
        notebook_protected=bool(pick("notebookProtected", "notebook_protected", False)),
        notebook_source_count=int(pick("notebookSourceCount", "notebook_source_count", 0) or 0),
        cleanup_required=bool(pick("cleanupRequired", "cleanup_required", False)),
        audio_file_path=pick("audioFilePath", "audio_file_path"),
        audio_file_size_bytes=pick("audioFileSizeBytes", "audio_file_size_bytes"),
        audio_telegram_message_id=pick("audioTelegramMessageId", "audio_telegram_message_id"),
        post_count=int(pick("postCount", "post_count", 0) or 0),
        post_error_count=int(pick("postErrorCount", "post_error_count", 0) or 0),
        last_error=pick("lastError", "last_error"),
        superseded_by=pick("supersededBy", "superseded_by"),
        created_at=_parse_datetime(pick("createdAt", "created_at")),
        updated_at=_parse_datetime(pick("updatedAt", "updated_at")),
        extra=dict(raw.get("extra") or {}),
    )
```

- [ ] **Шаг 4: Реализовать сборку run metadata**

Создать `src/digest/run_report.py`:

```python
from __future__ import annotations

from typing import Any

from digest.models import AudioInfo, CleanupSummary, ExtractedTelegramPost, NotebookInfo, RunStatus, TelegramDigestMessage


def build_trigger_metadata(
    *,
    target_date: str,
    source_channel: str,
    run_status: RunStatus,
    posts: list[ExtractedTelegramPost],
    notebook: NotebookInfo | None,
    cleanup: CleanupSummary | None,
    schedule: dict[str, Any],
    digest_message: TelegramDigestMessage | None = None,
    audio: AudioInfo | None = None,
    audio_telegram_message_id: int | None = None,
    max_posts: int = 50,
) -> dict[str, Any]:
    post_metadata = [post.to_metadata() for post in posts[:max_posts]]
    metadata: dict[str, Any] = {
        "targetDate": target_date,
        "sourceChannel": source_channel,
        "status": run_status.value,
        "schedule": schedule,
        "posts": post_metadata,
        "postCount": len(posts),
        "postErrorCount": sum(1 for post in posts if post.error),
    }
    if digest_message:
        metadata["digestMessage"] = {
            "telegramMessageId": digest_message.message_id,
            "publishedAt": digest_message.published_at.isoformat(),
            "url": digest_message.public_url,
            "urlCount": len(digest_message.urls),
        }
    if notebook:
        metadata["notebook"] = {
            "status": "created",
            "id": notebook.id,
            "url": notebook.url,
            "accountEmail": notebook.account_email,
            "name": notebook.name,
        }
    if audio:
        metadata["audio"] = {
            "status": "sent_to_telegram" if audio_telegram_message_id else "downloaded",
            "fileSizeBytes": audio.file_size_bytes,
            "telegramMessageId": audio_telegram_message_id,
        }
    if cleanup:
        metadata["cleanup"] = {
            "notebookCountBefore": cleanup.notebook_count_before,
            "deletedNotebookCount": cleanup.deleted_notebook_count,
            "notebookCountAfter": cleanup.notebook_count_after,
            "cleanupRequired": cleanup.cleanup_required,
        }
    return metadata
```

- [ ] **Шаг 5: Запустить тесты и убедиться, что они проходят**

Команда: `python -m pytest tests/test_state_store.py tests/test_run_report.py -v`

Ожидаемо: PASS.

- [ ] **Шаг 6: Закоммитить state_store и metadata**

Команда:

```powershell
git add src/digest/state_store.py src/digest/run_report.py tests/test_state_store.py tests/test_run_report.py
git commit -m "feat: add durable digest state"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 6: Извлечение связанных Telegram-постов

**Файлы:**
- Создать: `src/digest/telegram_post_extractor.py`
- Тест: `tests/test_telegram_post_extractor.py`

- [ ] **Шаг 1: Написать падающие тесты разбора и чтения Telegram-постов**

Создать `tests/test_telegram_post_extractor.py`:

```python
from __future__ import annotations

import pytest

from digest.models import ExtractedTelegramPost, PostStatus, TelegramPostLink
from digest.telegram_post_extractor import (
    TelegramPostExtractor,
    collect_telegram_post_links,
    parse_telegram_post_url,
)


class FakePostClient:
    def __init__(self, posts: dict[tuple[str, int], str | None]) -> None:
        self.posts = posts

    async def get_post_text(self, channel: str, message_id: int) -> str | None:
        return self.posts.get((channel, message_id))


def test_parse_public_telegram_post_url() -> None:
    link = parse_telegram_post_url("https://t.me/otherchannel/123?single")

    assert link == TelegramPostLink(
        url="https://t.me/otherchannel/123",
        channel="otherchannel",
        message_id=123,
    )


def test_collect_links_reports_unsupported_urls_and_deduplicates() -> None:
    items = collect_telegram_post_links(
        [
            "https://t.me/otherchannel/123",
            "https://example.com/not-telegram",
            "https://t.me/otherchannel/123",
            "https://t.me/c/123456/789",
        ],
        limit=50,
    )

    assert items[0] == TelegramPostLink("https://t.me/otherchannel/123", "otherchannel", 123)
    assert isinstance(items[1], ExtractedTelegramPost)
    assert items[1].status == PostStatus.FAILED_EXTRACTION
    assert items[1].error == "ссылка не является публичным Telegram-постом"
    assert isinstance(items[2], ExtractedTelegramPost)


@pytest.mark.asyncio
async def test_extracts_linked_telegram_post_text() -> None:
    client = FakePostClient({("otherchannel", 123): "Заголовок поста\n\nПолный текст новости из Telegram."})
    extractor = TelegramPostExtractor(client=client)

    post = await extractor.extract(TelegramPostLink("https://t.me/otherchannel/123", "otherchannel", 123))

    assert post.status == PostStatus.EXTRACTED
    assert post.extraction_method == "telegram"
    assert post.title == "Заголовок поста"
    assert "Полный текст новости" in post.text


@pytest.mark.asyncio
async def test_reports_missing_or_empty_telegram_post() -> None:
    client = FakePostClient({("otherchannel", 123): None})
    extractor = TelegramPostExtractor(client=client)

    post = await extractor.extract(TelegramPostLink("https://t.me/otherchannel/123", "otherchannel", 123))

    assert post.status == PostStatus.FAILED_EXTRACTION
    assert post.error == "Telegram-пост пустой или недоступен"
```

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Команда: `python -m pytest tests/test_telegram_post_extractor.py -v`

Ожидаемо: FAIL, потому что `digest.telegram_post_extractor` еще не существует.

- [ ] **Шаг 3: Реализовать разбор ссылок и Telethon-извлечение постов**

Создать `src/digest/telegram_post_extractor.py`:

```python
from __future__ import annotations

import re
from typing import Protocol

from telethon import TelegramClient
from telethon.sessions import StringSession

from digest.models import ExtractedTelegramPost, PostStatus, TelegramPostLink


TELEGRAM_POST_RE = re.compile(
    r"^https?://t\.me/(?:s/)?(?P<channel>[A-Za-z0-9_]+)/(?P<message_id>\d+)(?:[?#].*)?$",
    re.IGNORECASE,
)


class TelegramPostClient(Protocol):
    async def get_post_text(self, channel: str, message_id: int) -> str | None:
        ...


def _failed_post(url: str, error: str) -> ExtractedTelegramPost:
    return ExtractedTelegramPost(
        url=url,
        channel="",
        message_id=0,
        title=None,
        text="",
        extraction_method="telegram",
        status=PostStatus.FAILED_EXTRACTION,
        error=error,
    )


def parse_telegram_post_url(url: str) -> TelegramPostLink | None:
    match = TELEGRAM_POST_RE.match(url)
    if not match:
        return None
    channel = match.group("channel")
    message_id = int(match.group("message_id"))
    return TelegramPostLink(
        url=f"https://t.me/{channel}/{message_id}",
        channel=channel,
        message_id=message_id,
    )


def collect_telegram_post_links(urls: list[str], *, limit: int) -> list[TelegramPostLink | ExtractedTelegramPost]:
    items: list[TelegramPostLink | ExtractedTelegramPost] = []
    seen_posts: set[tuple[str, int]] = set()
    seen_urls: set[str] = set()

    for url in urls[:limit]:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        link = parse_telegram_post_url(url)
        if link is None:
            items.append(_failed_post(url, "ссылка не является публичным Telegram-постом"))
            continue
        key = (link.channel.lower(), link.message_id)
        if key in seen_posts:
            continue
        seen_posts.add(key)
        items.append(link)
    return items


def _title_from_text(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return None


class TelegramPostExtractor:
    def __init__(self, *, client: TelegramPostClient) -> None:
        self.client = client

    async def extract(self, link: TelegramPostLink) -> ExtractedTelegramPost:
        try:
            text = await self.client.get_post_text(link.channel, link.message_id)
            if not text or not text.strip():
                return _failed_post(link.url, "Telegram-пост пустой или недоступен")
            return ExtractedTelegramPost(
                url=link.url,
                channel=link.channel,
                message_id=link.message_id,
                title=_title_from_text(text),
                text=text.strip(),
                extraction_method="telegram",
                status=PostStatus.EXTRACTED,
            )
        except Exception as exc:
            return _failed_post(link.url, f"Не удалось прочитать Telegram-пост: {exc}")


class TelethonPostClient:
    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    async def get_post_text(self, channel: str, message_id: int) -> str | None:
        message = await self.client.get_messages(channel, ids=message_id)
        if message is None:
            return None
        return message.message or getattr(message, "text", None)


async def fetch_linked_telegram_posts(
    *,
    api_id: int,
    api_hash: str,
    session_string: str,
    urls: list[str],
    limit: int,
) -> list[ExtractedTelegramPost]:
    items = collect_telegram_post_links(urls, limit=limit)
    posts: list[ExtractedTelegramPost] = []

    async with TelegramClient(StringSession(session_string), api_id, api_hash) as client:
        extractor = TelegramPostExtractor(client=TelethonPostClient(client))
        for item in items:
            if isinstance(item, ExtractedTelegramPost):
                posts.append(item)
            else:
                posts.append(await extractor.extract(item))
    return posts
```

- [ ] **Шаг 4: Запустить тесты и убедиться, что они проходят**

Команда: `python -m pytest tests/test_telegram_post_extractor.py -v`

Ожидаемо: PASS.

- [ ] **Шаг 5: Закоммитить извлечение Telegram-постов**

Команда:

```powershell
git add src/digest/telegram_post_extractor.py tests/test_telegram_post_extractor.py
git commit -m "feat: extract linked Telegram posts"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 7: NotebookLM-клиент, очистка и конвертация аудио

**Файлы:**
- Создать: `src/digest/notebook_cleanup.py`
- Создать: `src/digest/notebooklm_client.py`
- Тест: `tests/test_notebook_cleanup.py`
- Тест: `tests/test_notebooklm_client.py`

- [ ] **Шаг 1: Написать падающие тесты cleanup**

Создать `tests/test_notebook_cleanup.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from digest.notebook_cleanup import select_notebooks_to_delete


@dataclass(frozen=True)
class Notebook:
    id: str
    title: str


def test_selects_oldest_unprotected_ciscrypted_notebooks() -> None:
    notebooks = [
        Notebook("a", "ciscrypted 2026-06-01"),
        Notebook("b", "ciscrypted 2026-06-02"),
        Notebook("c", "manual notes"),
        Notebook("d", "ciscrypted 2026-06-25"),
    ]

    selected = select_notebooks_to_delete(
        notebooks,
        current_target_date="2026-06-25",
        protected_ids={"b"},
        keep_recent_days=7,
        cleanup_target=1,
        today="2026-06-26",
    )

    assert [item.id for item in selected] == ["a"]
```

Создать `tests/test_notebooklm_client.py`:

```python
from __future__ import annotations

from pathlib import Path

from digest.notebooklm_client import build_source_content, ensure_mp3_path


def test_build_source_content_contains_required_fields() -> None:
    content = build_source_content(
        title="Telegram-пост",
        url="https://t.me/otherchannel/123",
        target_date="2026-06-25",
        text="Полный текст",
    )

    assert "Заголовок: Telegram-пост" in content
    assert "Источник Telegram: https://t.me/otherchannel/123" in content
    assert "Дата дайджеста: 2026-06-25" in content
    assert "Полный текст" in content


def test_ensure_mp3_path_keeps_existing_mp3(tmp_path: Path) -> None:
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"mp3")

    assert ensure_mp3_path(audio) == audio
```

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Команда: `python -m pytest tests/test_notebook_cleanup.py tests/test_notebooklm_client.py -v`

Ожидаемо: FAIL, потому что модули еще не созданы.

- [ ] **Шаг 3: Реализовать выбор блокнотов для cleanup**

Создать `src/digest/notebook_cleanup.py`:

```python
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Protocol


CISCRYPTED_TITLE_RE = re.compile(r"^ciscrypted (\d{4}-\d{2}-\d{2})$")


class ListedNotebook(Protocol):
    id: str
    title: str


def _title_date(title: str) -> date | None:
    match = CISCRYPTED_TITLE_RE.match(title)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def select_notebooks_to_delete(
    notebooks: list[ListedNotebook],
    *,
    current_target_date: str,
    protected_ids: set[str],
    keep_recent_days: int,
    cleanup_target: int,
    today: str,
) -> list[ListedNotebook]:
    today_date = date.fromisoformat(today)
    current_date = date.fromisoformat(current_target_date)
    candidates: list[tuple[date, ListedNotebook]] = []
    for notebook in notebooks:
        notebook_date = _title_date(notebook.title)
        if notebook_date is None:
            continue
        if notebook.id in protected_ids:
            continue
        if notebook_date == current_date:
            continue
        if (today_date - notebook_date).days < keep_recent_days:
            continue
        candidates.append((notebook_date, notebook))

    candidates.sort(key=lambda item: item[0])
    total_ciscrypted = sum(1 for notebook in notebooks if _title_date(notebook.title) is not None)
    delete_count = max(0, total_ciscrypted - cleanup_target)
    return [notebook for _, notebook in candidates[:delete_count]]
```

- [ ] **Шаг 4: Реализовать NotebookLM-адаптер и MP3-конвертацию**

Создать `src/digest/notebooklm_client.py`:

```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from notebooklm import AudioFormat, AudioLength, NotebookLMClient

from digest.models import AudioInfo, CleanupSummary, ExtractedTelegramPost, NotebookInfo
from digest.notebook_cleanup import select_notebooks_to_delete


def build_source_content(*, title: str | None, url: str, target_date: str, text: str) -> str:
    display_title = title or url
    return "\n".join(
        [
            f"Заголовок: {display_title}",
            f"Источник Telegram: {url}",
            f"Дата дайджеста: {target_date}",
            "",
            text,
        ]
    )


def ensure_mp3_path(path: Path) -> Path:
    if path.suffix.lower() == ".mp3":
        return path
    output = path.with_suffix(".mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-vn", "-codec:a", "libmp3lame", "-b:a", "128k", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


class NotebookLmDigestClient:
    def __init__(self, *, account_email: str, audio_language: str, audio_timeout_seconds: int) -> None:
        self.account_email = account_email
        self.audio_language = audio_language
        self.audio_timeout_seconds = audio_timeout_seconds

    async def cleanup_old_notebooks(
        self,
        *,
        current_target_date: str,
        protected_ids: set[str],
        keep_recent_days: int,
        cleanup_threshold: int,
        cleanup_target: int,
        max_notebooks: int,
        today: str,
    ) -> CleanupSummary:
        async with NotebookLMClient.from_storage() as client:
            notebooks = await client.notebooks.list()
            ciscrypted_count = sum(1 for notebook in notebooks if notebook.title.startswith("ciscrypted "))
            if ciscrypted_count < cleanup_threshold:
                return CleanupSummary(
                    ciscrypted_count,
                    0,
                    ciscrypted_count,
                    [],
                    cleanup_required=ciscrypted_count >= max_notebooks,
                )
            selected = select_notebooks_to_delete(
                notebooks,
                current_target_date=current_target_date,
                protected_ids=protected_ids,
                keep_recent_days=keep_recent_days,
                cleanup_target=cleanup_target,
                today=today,
            )
            deleted_ids: list[str] = []
            for notebook in selected:
                try:
                    await client.notebooks.delete(notebook.id)
                    deleted_ids.append(notebook.id)
                except Exception:
                    continue
            count_after = ciscrypted_count - len(deleted_ids)
            return CleanupSummary(
                notebook_count_before=ciscrypted_count,
                deleted_notebook_count=len(deleted_ids),
                notebook_count_after=count_after,
                deleted_notebook_ids=deleted_ids,
                cleanup_required=count_after >= max_notebooks,
            )

    async def create_notebook(self, *, target_date: str) -> NotebookInfo:
        notebook_name = f"ciscrypted {target_date}"
        async with NotebookLMClient.from_storage() as client:
            notebook = await client.notebooks.create(notebook_name)
            notebook_url = await client.notebooks.get_share_url(notebook.id)
            return NotebookInfo(notebook.id, notebook_url, notebook_name, self.account_email)

    async def delete_notebook(self, notebook_id: str) -> None:
        async with NotebookLMClient.from_storage() as client:
            await client.notebooks.delete(notebook_id)

    async def add_posts_to_notebook(
        self,
        *,
        notebook_id: str,
        target_date: str,
        posts: list[ExtractedTelegramPost],
        extraction_errors: list[ExtractedTelegramPost],
    ) -> int:
        added_count = 0
        async with NotebookLMClient.from_storage() as client:
            for post in posts:
                content = build_source_content(
                    title=post.title,
                    url=post.url,
                    target_date=target_date,
                    text=post.text,
                )
                await client.sources.add_text(
                    notebook_id,
                    post.title or post.url,
                    content,
                    idempotent=True,
                    wait=True,
                    wait_timeout=120,
                )
                added_count += 1
            if extraction_errors:
                error_lines = [f"- {post.url}: {post.error}" for post in extraction_errors]
                await client.sources.add_text(
                    notebook_id,
                    "Ошибки извлечения",
                    "\n".join(error_lines),
                    idempotent=True,
                    wait=True,
                    wait_timeout=120,
                )
                added_count += 1
        return added_count

    async def generate_and_download_audio(self, notebook_id: str, output_dir: Path) -> AudioInfo:
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = output_dir / f"{notebook_id}-audio.mp3"
        async with NotebookLMClient.from_storage() as client:
            status = await client.artifacts.generate_audio(
                notebook_id,
                source_ids=None,
                instructions="Сделай связный аудиообзор дневного дайджеста для личного прослушивания.",
                audio_format=AudioFormat.DEEP_DIVE,
                audio_length=AudioLength.DEFAULT,
                language=self.audio_language,
            )
            final = await client.artifacts.wait_for_completion(
                notebook_id,
                status.task_id,
                timeout=self.audio_timeout_seconds,
                initial_interval=5,
            )
            if not final.is_complete:
                raise TimeoutError(f"Audio Overview завершился ошибкой со статусом {final.status}")
            downloaded = Path(await client.artifacts.download_audio(notebook_id, str(raw_path)))
        mp3_path = ensure_mp3_path(downloaded)
        return AudioInfo(path=str(mp3_path), file_size_bytes=os.path.getsize(mp3_path))
```

- [ ] **Шаг 5: Запустить тесты и убедиться, что они проходят**

Команда: `python -m pytest tests/test_notebook_cleanup.py tests/test_notebooklm_client.py -v`

Ожидаемо: PASS.

- [ ] **Шаг 6: Закоммитить NotebookLM client**

Команда:

```powershell
git add src/digest/notebook_cleanup.py src/digest/notebooklm_client.py tests/test_notebook_cleanup.py tests/test_notebooklm_client.py
git commit -m "feat: add NotebookLM digest client"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 8: Отправка через Telegram Bot API

**Файлы:**
- Создать: `src/digest/telegram_bot_sender.py`
- Тест: `tests/test_telegram_bot_sender.py`

- [ ] **Шаг 1: Написать падающие тесты Telegram sender**

Создать `tests/test_telegram_bot_sender.py`:

```python
from __future__ import annotations

from digest.telegram_bot_sender import build_audio_caption


def test_build_audio_caption_uses_html_links_without_raw_urls() -> None:
    caption = build_audio_caption(
        target_date="2026-06-25",
        processed_count=10,
        error_count=2,
        digest_message_url="https://t.me/ciscrypted/12345",
        notebook_url="https://notebooklm.google.com/notebook/abc",
        notebook_account_email="user@example.com",
    )

    assert '<a href="https://t.me/ciscrypted/12345">Оригинальный Telegram-пост</a>' in caption
    assert '<a href="https://notebooklm.google.com/notebook/abc">Блокнот NotebookLM [user@example.com]</a>' in caption
    assert "Markdown" not in caption
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Команда: `python -m pytest tests/test_telegram_bot_sender.py -v`

Ожидаемо: FAIL, потому что `digest.telegram_bot_sender` еще не существует.

- [ ] **Шаг 3: Реализовать Telegram sender**

Создать `src/digest/telegram_bot_sender.py`:

```python
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import httpx


TELEGRAM_AUDIO_CAPTION_LIMIT = 1024


def build_audio_caption(
    *,
    target_date: str,
    processed_count: int,
    error_count: int,
    digest_message_url: str,
    notebook_url: str,
    notebook_account_email: str,
) -> str:
    return "\n".join(
        [
            f"Дайджест ciscrypted за {html.escape(target_date)}",
            f"Посты: {processed_count} обработано, {error_count} с ошибками",
            "",
            f'<a href="{html.escape(digest_message_url, quote=True)}">Оригинальный Telegram-пост</a>',
            f'<a href="{html.escape(notebook_url, quote=True)}">Блокнот NotebookLM [{html.escape(notebook_account_email)}]</a>',
        ]
    )


class TelegramBotSender:
    def __init__(self, *, bot_token: str, target_chat_id: str, client: httpx.AsyncClient | None = None) -> None:
        self.bot_token = bot_token
        self.target_chat_id = target_chat_id
        self.client = client or httpx.AsyncClient(timeout=60)

    @property
    def base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"

    async def send_text(self, text: str, *, parse_mode: str | None = "HTML") -> int | None:
        response = await self.client.post(
            f"{self.base_url}/sendMessage",
            data={
                "chat_id": self.target_chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": "true",
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("result", {}).get("message_id")

    async def send_audio_with_report(self, *, audio_path: Path, caption: str, full_report: str | None = None) -> int:
        short_caption = caption
        report_to_send = full_report
        if len(caption) > TELEGRAM_AUDIO_CAPTION_LIMIT:
            short_caption = "\n".join(caption.splitlines()[:2])
            report_to_send = full_report or caption

        with audio_path.open("rb") as audio_file:
            response = await self.client.post(
                f"{self.base_url}/sendAudio",
                data={
                    "chat_id": self.target_chat_id,
                    "caption": short_caption,
                    "parse_mode": "HTML",
                },
                files={"audio": (audio_path.name, audio_file, "audio/mpeg")},
            )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        message_id = int(payload["result"]["message_id"])

        if report_to_send:
            await self.send_text(report_to_send, parse_mode="HTML")
        return message_id
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Команда: `python -m pytest tests/test_telegram_bot_sender.py -v`

Ожидаемо: PASS.

- [ ] **Шаг 5: Закоммитить Telegram sender**

Команда:

```powershell
git add src/digest/telegram_bot_sender.py tests/test_telegram_bot_sender.py
git commit -m "feat: add Telegram bot sender"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 9: Preflight и orchestration пайплайна

**Файлы:**
- Создать: `src/digest/preflight.py`
- Создать: `src/digest/pipeline.py`
- Создать: `src/trigger/run_ciscrypted_digest.py`
- Тест: `tests/test_preflight.py`
- Тест: `tests/test_pipeline.py`

- [ ] **Шаг 1: Написать падающие тесты preflight и pipeline**

Создать `tests/test_preflight.py`:

```python
from __future__ import annotations

import pytest

from digest.preflight import PreflightError, check_required_imports


def test_check_required_imports_reports_missing_module() -> None:
    with pytest.raises(PreflightError, match="missing_module_for_digest_test"):
        check_required_imports(["json", "missing_module_for_digest_test"])
```

Создать `tests/test_pipeline.py`:

```python
from __future__ import annotations

import pytest

from digest.models import DigestRunState, RunStatus
from digest.pipeline import DigestPipeline
from digest.state_store import InMemoryStateStore


class FakeTelegramSender:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_text(self, text: str, *, parse_mode: str | None = "HTML") -> int:
        self.messages.append(text)
        return 1


class FakeNotebookClient:
    def __init__(self) -> None:
        self.deleted_ids: list[str] = []

    async def delete_notebook(self, notebook_id: str) -> None:
        self.deleted_ids.append(notebook_id)


@pytest.mark.asyncio
async def test_pipeline_stops_before_side_effects_when_run_completed() -> None:
    store = InMemoryStateStore()
    state = DigestRunState(
        target_date="2026-06-25",
        idempotency_key="ciscrypted:2026-06-25",
        status=RunStatus.SENT_TO_TELEGRAM,
        audio_telegram_message_id=999,
    )
    await store.save_run(state)
    sender = FakeTelegramSender()
    pipeline = DigestPipeline(state_store=store, telegram_sender=sender)

    result = await pipeline.run_completed_short_circuit("2026-06-25", "ciscrypted:2026-06-25")

    assert result["status"] == "sent_to_telegram"
    assert sender.messages == []


@pytest.mark.asyncio
async def test_pipeline_notifies_when_digest_missing() -> None:
    store = InMemoryStateStore()
    sender = FakeTelegramSender()
    pipeline = DigestPipeline(state_store=store, telegram_sender=sender)

    state = await pipeline.mark_no_digest("2026-06-25", "ciscrypted:2026-06-25")

    assert state.status == RunStatus.NO_DIGEST_MESSAGE
    assert sender.messages == ["Дайджест ciscrypted за 2026-06-25 не найден."]


@pytest.mark.asyncio
async def test_pipeline_stops_after_unknown_telegram_audio_send() -> None:
    store = InMemoryStateStore()
    sender = FakeTelegramSender()
    pipeline = DigestPipeline(state_store=store, telegram_sender=sender)
    state = DigestRunState(
        target_date="2026-06-25",
        idempotency_key="ciscrypted:2026-06-25",
        status=RunStatus.TELEGRAM_SENDING,
    )
    await store.save_run(state)

    stopped = await pipeline.stop_after_unknown_telegram_send(state)

    assert stopped.status == RunStatus.CLEANUP_REQUIRED
    assert stopped.cleanup_required is True
    assert "могла уже выполниться" in sender.messages[0]


@pytest.mark.asyncio
async def test_pipeline_deletes_partial_notebook_before_retrying_sources() -> None:
    store = InMemoryStateStore()
    sender = FakeTelegramSender()
    pipeline = DigestPipeline(state_store=store, telegram_sender=sender)
    notebook_client = FakeNotebookClient()
    state = DigestRunState(
        target_date="2026-06-25",
        idempotency_key="ciscrypted:2026-06-25",
        status=RunStatus.SOURCES_ADDING,
        notebook_id="partial-nb",
        notebook_url="https://notebooklm.google.com/notebook/partial-nb",
        notebook_name="ciscrypted 2026-06-25",
    )

    reset = await pipeline.reset_partial_notebook(state=state, notebook_client=notebook_client)

    assert notebook_client.deleted_ids == ["partial-nb"]
    assert reset.status == RunStatus.PENDING
    assert reset.notebook_id is None
```

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Команда: `python -m pytest tests/test_preflight.py tests/test_pipeline.py -v`

Ожидаемо: FAIL, потому что модули еще не созданы.

- [ ] **Шаг 3: Реализовать preflight**

Создать `src/digest/preflight.py`:

```python
from __future__ import annotations

import importlib
import os
import shutil

from notebooklm import NotebookLMClient

from digest.config import DigestSettings
from digest.state_store import PostgresStateStore


class PreflightError(RuntimeError):
    pass


def check_required_imports(module_names: list[str]) -> None:
    missing: list[str] = []
    for module_name in module_names:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    if missing:
        raise PreflightError(f"Не найдены Python-модули: {', '.join(missing)}")


async def run_preflight(settings: DigestSettings) -> None:
    check_required_imports(["telethon", "notebooklm", "httpx", "psycopg"])
    if shutil.which("ffmpeg") is None:
        raise PreflightError("ffmpeg binary is not available")
    os.environ["NOTEBOOKLM_AUTH_JSON"] = settings.notebooklm_auth_json
    async with NotebookLMClient.from_storage() as client:
        await client.refresh_auth()
        await client.notebooks.list()
    store = PostgresStateStore(settings.state_database_url, settings.digest_state_table)
    await store.ensure_schema()
```

- [ ] **Шаг 4: Реализовать orchestration skeleton с idempotent short-circuits**

Создать `src/digest/pipeline.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from digest.config import DigestSettings
from digest.models import AudioInfo, CleanupSummary, DigestRunState, NotebookInfo, PostStatus, RunStatus
from digest.notebooklm_client import NotebookLmDigestClient
from digest.run_report import build_trigger_metadata
from digest.state_store import StateStore
from digest.telegram_bot_sender import TelegramBotSender, build_audio_caption
from digest.telegram_post_extractor import fetch_linked_telegram_posts
from digest.telegram_reader import fetch_channel_messages_for_date, select_latest_digest_message


class DigestPipeline:
    def __init__(self, *, state_store: StateStore, telegram_sender: Any) -> None:
        self.state_store = state_store
        self.telegram_sender = telegram_sender

    async def run_completed_short_circuit(self, target_date: str, idempotency_key: str) -> dict[str, Any] | None:
        state = await self.state_store.get_or_create_run(target_date, idempotency_key)
        if state.completed:
            return state.to_json_dict()
        return None

    async def mark_no_digest(self, target_date: str, idempotency_key: str) -> DigestRunState:
        state = await self.state_store.get_or_create_run(target_date, idempotency_key)
        state.status = RunStatus.NO_DIGEST_MESSAGE
        await self.state_store.save_run(state)
        await self.telegram_sender.send_text(f"Дайджест ciscrypted за {target_date} не найден.")
        return state

    async def stop_after_unknown_telegram_send(self, state: DigestRunState) -> DigestRunState:
        state.status = RunStatus.CLEANUP_REQUIRED
        state.cleanup_required = True
        state.last_error = (
            "Предыдущий запуск прервался во время sendAudio. "
            "Автоматический повтор остановлен, чтобы не отправить MP3 дважды."
        )
        await self.state_store.save_run(state)
        await self.telegram_sender.send_text(
            f"Проверьте Telegram вручную: отправка MP3 за {state.target_date} могла уже выполниться."
        )
        return state

    async def reset_partial_notebook(
        self,
        *,
        state: DigestRunState,
        notebook_client: NotebookLmDigestClient,
    ) -> DigestRunState:
        if state.status != RunStatus.SOURCES_ADDING:
            return state
        if not state.notebook_id:
            state.status = RunStatus.PENDING
            await self.state_store.save_run(state)
            return state
        try:
            await notebook_client.delete_notebook(state.notebook_id)
        except Exception as exc:
            state.status = RunStatus.CLEANUP_REQUIRED
            state.cleanup_required = True
            state.last_error = f"Не удалось удалить частично заполненный NotebookLM-блокнот: {exc}"
            await self.state_store.save_run(state)
            await self.telegram_sender.send_text(
                f"Нужна ручная очистка NotebookLM: частичный блокнот за {state.target_date} не удален."
            )
            return state
        state.notebook_id = None
        state.notebook_url = None
        state.notebook_name = None
        state.notebook_source_count = 0
        state.status = RunStatus.PENDING
        await self.state_store.save_run(state)
        return state


def _cleanup_to_metadata(cleanup: CleanupSummary) -> dict[str, Any]:
    return {
        "notebookCountBefore": cleanup.notebook_count_before,
        "deletedNotebookCount": cleanup.deleted_notebook_count,
        "notebookCountAfter": cleanup.notebook_count_after,
        "deletedNotebookIds": cleanup.deleted_notebook_ids,
        "cleanupRequired": cleanup.cleanup_required,
    }


def _notebook_from_state(state: DigestRunState, account_email: str) -> NotebookInfo | None:
    if not state.notebook_id or not state.notebook_url or not state.notebook_name:
        return None
    return NotebookInfo(state.notebook_id, state.notebook_url, state.notebook_name, account_email)


async def run_digest_for_date(
    *,
    settings: DigestSettings,
    state_store: StateStore,
    target_date: str,
    planned_start_at: str,
    random_delay_minutes: int,
    force_reprocess: bool = False,
    force_attempt_id: str | None = None,
) -> dict[str, Any]:
    idempotency_key = f"ciscrypted:{target_date}"
    if force_reprocess:
        if not force_attempt_id:
            raise ValueError("force_attempt_id обязателен для force_reprocess")
        idempotency_key = f"{idempotency_key}:force:{force_attempt_id}"

    sender = TelegramBotSender(
        bot_token=settings.telegram_bot_token,
        target_chat_id=settings.telegram_target_chat_id,
    )
    pipeline = DigestPipeline(state_store=state_store, telegram_sender=sender)
    completed = await pipeline.run_completed_short_circuit(target_date, idempotency_key)
    if completed:
        return completed

    state = await state_store.get_or_create_run(target_date, idempotency_key)
    notebook_client = NotebookLmDigestClient(
        account_email=settings.notebooklm_account_email,
        audio_language=settings.notebooklm_audio_language,
        audio_timeout_seconds=settings.audio_overview_timeout_seconds,
    )

    if state.status == RunStatus.CLEANUP_REQUIRED:
        return state.to_json_dict()

    if state.status == RunStatus.TELEGRAM_SENDING and state.audio_telegram_message_id is None:
        state = await pipeline.stop_after_unknown_telegram_send(state)
        return state.to_json_dict()

    state = await pipeline.reset_partial_notebook(state=state, notebook_client=notebook_client)
    if state.status == RunStatus.CLEANUP_REQUIRED:
        return state.to_json_dict()

    messages = await fetch_channel_messages_for_date(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telegram_session_string,
        channel=settings.telegram_source_channel,
        target_date=target_date,
        timezone_name=settings.digest_timezone,
    )
    digest_message = select_latest_digest_message(messages, target_date=target_date, timezone_name=settings.digest_timezone)
    if digest_message is None:
        state = await pipeline.mark_no_digest(target_date, idempotency_key)
        return state.to_json_dict()

    state.digest_message_id = digest_message.message_id
    state.digest_message_url = digest_message.public_url
    await state_store.save_run(state)

    posts = await fetch_linked_telegram_posts(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telegram_session_string,
        urls=digest_message.urls,
        limit=settings.telegram_link_limit,
    )

    extracted = [post for post in posts if post.status == PostStatus.EXTRACTED]
    errors = [post for post in posts if post.status == PostStatus.FAILED_EXTRACTION]
    state.post_count = len(extracted)
    state.post_error_count = len(errors)
    await state_store.save_run(state)

    if not extracted:
        state.status = RunStatus.NO_VALID_POSTS
        await state_store.save_run(state)
        await sender.send_text(f"В дайджесте ciscrypted за {target_date} нет Telegram-постов, которые удалось извлечь.")
        return state.to_json_dict()

    cleanup: CleanupSummary | None = None
    notebook = _notebook_from_state(state, settings.notebooklm_account_email)
    if notebook is None:
        protected_ids = await state_store.list_protected_notebook_ids()
        cleanup = await notebook_client.cleanup_old_notebooks(
            current_target_date=target_date,
            protected_ids=protected_ids,
            keep_recent_days=settings.notebooklm_keep_recent_days,
            cleanup_threshold=settings.notebooklm_cleanup_threshold,
            cleanup_target=settings.notebooklm_cleanup_target,
            max_notebooks=settings.notebooklm_max_notebooks,
            today=(date.fromisoformat(target_date) + timedelta(days=1)).isoformat(),
        )
        state.extra["cleanup"] = _cleanup_to_metadata(cleanup)
        if cleanup.cleanup_required:
            state.status = RunStatus.CLEANUP_REQUIRED
            state.cleanup_required = True
            state.last_error = "Достигнут лимит NotebookLM-блокнотов, автоматическая очистка недостаточна"
            await state_store.save_run(state)
            await sender.send_text("Нужна ручная очистка NotebookLM: новый блокнот ciscrypted не создан.")
            return state.to_json_dict()
        await state_store.save_run(state)

        notebook = await notebook_client.create_notebook(target_date=target_date)
        state.notebook_id = notebook.id
        state.notebook_url = notebook.url
        state.notebook_name = notebook.name
        state.status = RunStatus.NOTEBOOK_CREATED
        await state_store.save_run(state)

    if state.status == RunStatus.NOTEBOOK_CREATED:
        state.status = RunStatus.SOURCES_ADDING
        await state_store.save_run(state)
        try:
            source_count = await notebook_client.add_posts_to_notebook(
                notebook_id=notebook.id,
                target_date=target_date,
                posts=extracted,
                extraction_errors=errors,
            )
        except Exception as exc:
            state.last_error = f"Добавление источников в NotebookLM прервано: {exc}"
            await state_store.save_run(state)
            raise
        for post in extracted:
            post.status = PostStatus.ADDED_TO_NOTEBOOK
        state.notebook_source_count = source_count
        state.status = RunStatus.SOURCES_ADDED
        await state_store.save_run(state)

    for post in extracted:
        if state.status in {RunStatus.SOURCES_ADDED, RunStatus.AUDIO_DOWNLOADED, RunStatus.SENT_TO_TELEGRAM}:
            post.status = PostStatus.ADDED_TO_NOTEBOOK

    audio: AudioInfo
    existing_audio_path = Path(state.audio_file_path) if state.audio_file_path else None
    if state.status == RunStatus.AUDIO_DOWNLOADED and existing_audio_path and existing_audio_path.exists():
        audio = AudioInfo(path=str(existing_audio_path), file_size_bytes=state.audio_file_size_bytes or 0)
    else:
        audio = await notebook_client.generate_and_download_audio(notebook.id, Path("runtime") / target_date)
        state.audio_file_path = audio.path
        state.audio_file_size_bytes = audio.file_size_bytes
        state.status = RunStatus.AUDIO_DOWNLOADED
        await state_store.save_run(state)

    if state.audio_telegram_message_id is not None:
        state.status = RunStatus.SENT_TO_TELEGRAM
        await state_store.save_run(state)
        return state.to_json_dict()

    caption = build_audio_caption(
        target_date=target_date,
        processed_count=len(extracted),
        error_count=len(errors),
        digest_message_url=digest_message.public_url,
        notebook_url=notebook.url,
        notebook_account_email=notebook.account_email,
    )
    state.status = RunStatus.TELEGRAM_SENDING
    await state_store.save_run(state)
    message_id = await sender.send_audio_with_report(audio_path=Path(audio.path), caption=caption)
    state.audio_telegram_message_id = message_id
    state.status = RunStatus.SENT_TO_TELEGRAM
    await state_store.save_run(state)

    return build_trigger_metadata(
        target_date=target_date,
        source_channel=settings.telegram_source_channel,
        run_status=state.status,
        posts=posts,
        notebook=notebook,
        cleanup=cleanup,
        schedule={
            "plannedStartAt": planned_start_at,
            "randomDelayMinutes": random_delay_minutes,
        },
        digest_message=digest_message,
        audio=audio,
        audio_telegram_message_id=message_id,
    )
```

- [ ] **Шаг 5: Реализовать Trigger Python CLI**

Создать `src/trigger/run_ciscrypted_digest.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json

from digest.config import DigestSettings
from digest.pipeline import run_digest_for_date
from digest.preflight import run_preflight
from digest.state_store import PostgresStateStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--planned-start-at", required=True)
    parser.add_argument("--random-delay-minutes", required=True, type=int)
    parser.add_argument("--force-reprocess", action="store_true")
    parser.add_argument("--force-attempt-id")
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    settings = DigestSettings.from_env()
    await run_preflight(settings)
    state_store = PostgresStateStore(settings.state_database_url, settings.digest_state_table)
    result = await run_digest_for_date(
        settings=settings,
        state_store=state_store,
        target_date=args.target_date,
        planned_start_at=args.planned_start_at,
        random_delay_minutes=args.random_delay_minutes,
        force_reprocess=args.force_reprocess,
        force_attempt_id=args.force_attempt_id,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Шаг 6: Запустить тесты и CLI help**

Команда:

```powershell
python -m pytest tests/test_preflight.py tests/test_pipeline.py -v
python src/trigger/run_ciscrypted_digest.py --help
```

Ожидаемо: pytest дает PASS; help печатает CLI-опции и завершается с кодом 0.

- [ ] **Шаг 7: Закоммитить pipeline**

Команда:

```powershell
git add src/digest/preflight.py src/digest/pipeline.py src/trigger/run_ciscrypted_digest.py tests/test_preflight.py tests/test_pipeline.py
git commit -m "feat: orchestrate digest pipeline"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 10: Smoke-скрипты и документация деплоя

**Файлы:**
- Создать: `scripts/notebooklm_smoke.py`
- Создать: `scripts/telegram_bot_smoke.py`
- Создать: `scripts/dry_run_digest.py`
- Создать: `README.md`

- [ ] **Шаг 1: Создать NotebookLM smoke-скрипт**

Создать `scripts/notebooklm_smoke.py`:

```python
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from digest.notebooklm_client import NotebookLmDigestClient
from digest.models import ExtractedTelegramPost, PostStatus


async def main() -> int:
    client = NotebookLmDigestClient(
        account_email=os.environ["NOTEBOOKLM_ACCOUNT_EMAIL"],
        audio_language=os.getenv("NOTEBOOKLM_AUDIO_LANGUAGE", "ru"),
        audio_timeout_seconds=int(os.getenv("AUDIO_OVERVIEW_TIMEOUT_SECONDS", "1200")),
    )
    post = ExtractedTelegramPost(
        url="https://t.me/notebooklm_smoke/1",
        channel="notebooklm_smoke",
        message_id=1,
        title="NotebookLM smoke-тест",
        text="Это короткий тестовый текст Telegram-поста для проверки создания блокнота и Audio Overview.",
        extraction_method="telegram",
        status=PostStatus.EXTRACTED,
    )
    notebook = await client.create_notebook(target_date="2099-01-01")
    await client.add_posts_to_notebook(
        notebook_id=notebook.id,
        target_date="2099-01-01",
        posts=[post],
        extraction_errors=[],
    )
    audio = await client.generate_and_download_audio(notebook.id, Path("runtime") / "smoke")
    print({"notebookUrl": notebook.url, "audioPath": audio.path, "fileSizeBytes": audio.file_size_bytes})
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Шаг 2: Создать Telegram smoke-скрипт**

Создать `scripts/telegram_bot_smoke.py`:

```python
from __future__ import annotations

import asyncio
import os

from digest.telegram_bot_sender import TelegramBotSender


async def main() -> int:
    sender = TelegramBotSender(
        bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        target_chat_id=os.environ["TELEGRAM_TARGET_CHAT_ID"],
    )
    message_id = await sender.send_text("Smoke-тест Telegram Bot API для ciscrypted digest.")
    print({"messageId": message_id})
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Шаг 3: Создать dry-run скрипт**

Создать `scripts/dry_run_digest.py`:

```python
from __future__ import annotations

import argparse
import asyncio

from digest.config import DigestSettings
from digest.telegram_post_extractor import fetch_linked_telegram_posts
from digest.telegram_reader import fetch_channel_messages_for_date, select_latest_digest_message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date", required=True)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = DigestSettings.from_env()
    messages = await fetch_channel_messages_for_date(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telegram_session_string,
        channel=settings.telegram_source_channel,
        target_date=args.target_date,
        timezone_name=settings.digest_timezone,
    )
    digest_message = select_latest_digest_message(messages, target_date=args.target_date, timezone_name=settings.digest_timezone)
    if digest_message is None:
        print({"targetDate": args.target_date, "status": "no_digest_message"})
        return 0
    posts = await fetch_linked_telegram_posts(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telegram_session_string,
        urls=digest_message.urls,
        limit=settings.telegram_link_limit,
    )
    print(
        {
            "targetDate": args.target_date,
            "digestMessageId": digest_message.message_id,
            "linkCount": len(digest_message.urls),
            "extractedPostCount": sum(1 for post in posts if post.text),
            "failedPostCount": sum(1 for post in posts if post.error),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Шаг 4: Создать README**

Создать `README.md`:

```markdown
# Дайджест ciscrypted для Trigger.dev

Ежедневный Trigger.dev-пайплайн для дайджеста `ciscrypted`: Telegram → связанные Telegram-посты → NotebookLM Audio Overview → Telegram Bot API.

## Локальная установка

```powershell
npm install
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполнить `.env` локальными значениями. Секреты не коммитить.

## Проверки

```powershell
npm run test
python scripts/dry_run_digest.py --target-date 2026-06-25
python scripts/telegram_bot_smoke.py
python scripts/notebooklm_smoke.py
npm run trigger:dry-run
```

## Деплой

Перед production-деплоем проверить, что в Trigger.dev Production заданы env vars из `.env.example`.

```powershell
npx trigger.dev@4.4.6 env list --env prod
npm run trigger:deploy
```

## Связанные Telegram-посты

Ссылки из дайджеста считаются ссылками на публичные посты в других Telegram-каналах в формате `https://t.me/<channel>/<message_id>`. Внешние сайты не скачиваются. Ссылки другого вида попадут в отчет как ошибки извлечения.
```

- [ ] **Шаг 5: Запустить help/import проверки smoke-скриптов**

Команда:

```powershell
python scripts/dry_run_digest.py --help
python -m pytest -v
npm run test:trigger
```

Ожидаемо: help печатает опции; тесты дают PASS.

- [ ] **Шаг 6: Запустить Trigger dry-run**

Команда:

```powershell
if (-not $env:TRIGGER_PROJECT_REF) { throw "Перед dry-run задайте TRIGGER_PROJECT_REF в текущем shell" }
npm run trigger:dry-run
```

Ожидаемо: Trigger.dev build видит `src/trigger/ciscryptedDigest.ts`, копирует Python-скрипты через `pythonExtension`, устанавливает `requirements.txt` и включает `ffmpeg`.

- [ ] **Шаг 7: Закоммитить документацию и скрипты**

Команда:

```powershell
git add scripts/notebooklm_smoke.py scripts/telegram_bot_smoke.py scripts/dry_run_digest.py README.md
git commit -m "docs: add digest smoke checks"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

## Самопроверка

- Покрытие спеки: расписание, target date, выбор Telegram-сообщения, извлечение URL, извлечение связанных Telegram-постов, cleanup NotebookLM, создание NotebookLM, загрузка источников, скачивание аудио, отправка в Telegram, idempotency в state, metadata, env-контракт, preflight и deploy-контракт покрыты.
- Проверка placeholder-маркеров: запрещенных маркеров из раздела No Placeholders не найдено.
- Согласованность типов: имена `RunStatus`, `PostStatus`, `ExtractedTelegramPost`, `TelegramPostLink`, `DigestRunState`, `NotebookInfo`, `AudioInfo`, `CleanupSummary`, `build_trigger_metadata()` и `run_digest_for_date()` согласованы между задачами.
- Retry-модель: `client.sources.add_text(..., idempotent=True)` не повторяется вслепую; частичный блокнот удаляется перед повтором, а неизвестная отправка MP3 переводит run в `cleanup_required` для ручной сверки.

План готов и сохранен в `docs/superpowers/plans/2026-06-26-triggerdev-ciscrypted-digest.md`. Два варианта исполнения:

**1. Subagent-Driven (рекомендуется)** - запускать свежего subagent на каждую задачу и делать review между задачами

**2. Inline Execution** - выполнять задачи в этой сессии через executing-plans, пакетами с контрольными точками

Какой вариант выбираем?
