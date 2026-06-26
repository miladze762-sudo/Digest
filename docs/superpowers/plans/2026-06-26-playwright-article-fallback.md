# План реализации Playwright fallback для статей

> **Для агентных исполнителей:** ОБЯЗАТЕЛЬНЫЙ SUB-SKILL: используйте `superpowers:subagent-driven-development` (рекомендуется) или `superpowers:executing-plans`, чтобы выполнять план по задачам. Для отслеживания шагов используется синтаксис checkbox (`- [ ]`).

**Цель:** Добавить Playwright browser fallback к HTTP-first извлечению статей и закрыть Trigger.dev runtime-контракт для Chromium.

**Архитектура:** Trigger.dev build устанавливает Playwright runtime через `@trigger.dev/build/extensions/playwright`, а Python-пайплайн использует async Playwright только при провале HTTP-слоя. Версия Playwright закрепляется одинаково в Node dependency, Python dependency и Trigger.dev extension, чтобы Chromium build-контракт был воспроизводимым. Preflight проверяет запуск Chromium до чтения Telegram и до создания NotebookLM, чтобы отсутствие браузера считалось deploy-контрактной ошибкой.

**Технологический стек:** Trigger.dev SDK `4.4.x`, `@trigger.dev/build` Playwright extension, Node `playwright`, Python `playwright`, Chromium, httpx, trafilatura, readability-lxml, pytest-asyncio.

---

## Предусловие

Сначала выполнить основной план `docs/superpowers/plans/2026-06-26-triggerdev-ciscrypted-digest.md` до конца. Этот план модифицирует уже созданные файлы `package.json`, `trigger.config.ts`, `requirements.txt`, `.env.example`, `src/digest/config.py`, `src/digest/article_extractor.py`, `src/digest/preflight.py`, `src/digest/pipeline.py` и добавляет `src/digest/playwright_article_extractor.py`.

## Что уже дает основной план

- `DigestSettings` уже содержит `enable_playwright_fallback`, а `.env.example` уже документирует `ENABLE_PLAYWRIGHT_FALLBACK=false`. В этом плане не добавлять это поле повторно; нужно только обновить значение флага при включении fallback и добавить новые поля `playwright_timeout_ms` и `playwright_wait_until`.
- `src/digest/article_extractor.py` уже содержит `ArticleFallback`, `DisabledBrowserFallback`, `HttpArticleExtractor` и критерии вызова fallback: пустой текст, короткий текст, JS-заглушка или HTTP-ошибка.
- `src/digest/pipeline.py` уже создает `HttpArticleExtractor` с `DisabledBrowserFallback()`. Этот план заменяет только создание fallback через factory, не переписывая orchestration.
- `src/digest/preflight.py` уже проверяет Python imports, `ffmpeg` и `state_store`. Этот план добавляет браузерный smoke-check только когда `ENABLE_PLAYWRIGHT_FALLBACK=true`.

Trade-off: Playwright повышает надежность извлечения JS-страниц, но увеличивает размер build image, время dry-run/deploy и runtime-стоимость. Поэтому HTTP-слой остается первым, а браузер запускается только как fallback и только при включенном флаге.

## Источники

- Расширение Trigger.dev для Playwright: `https://trigger.dev/docs/config/extensions/playwright`.
- Документация Playwright по установке и runtime браузеров: `https://playwright.dev/docs/browsers`.

## Структура файлов

- Изменить: `package.json` — оставить `@trigger.dev/build` в `devDependencies` и добавить Node `playwright` той же версии, что Python-пакет.
- Изменить: `package-lock.json` — зафиксировать lockfile после `npm install`, если он создается или уже существует.
- Изменить: `trigger.config.ts` — добавить `playwright({ browsers: ["chromium"], headless: true, version: PLAYWRIGHT_VERSION })`.
- Изменить: `requirements.txt` — добавить Python-пакет `playwright` той же версии, что Node dependency.
- Изменить: `.env.example` — включить browser fallback flags.
- Создать: `src/digest/playwright_article_extractor.py` — async Chromium extractor.
- Изменить: `src/digest/article_extractor.py` — выбирать Playwright fallback по config.
- Изменить: `src/digest/preflight.py` — запускать browser smoke-check при `ENABLE_PLAYWRIGHT_FALLBACK=true`.
- Тест: `tests/test_playwright_article_extractor.py`
- Тест: `tests/test_preflight_playwright.py`
- Изменить: `README.md` — добавить локальную установку браузера для dev mode.

### Задача 1: Trigger.dev build-контракт для Playwright

**Файлы:**
- Изменить: `package.json`
- Изменить: `package-lock.json`
- Изменить: `trigger.config.ts`
- Изменить: `requirements.txt`
- Изменить: `.env.example`
- Тест: `tests/test_env_contract.py`

- [ ] **Шаг 1: Расширить тест env-контракта**

Изменить `tests/test_env_contract.py`, чтобы файл импортировал `json`:

```python
import json
```

Изменить `test_env_example_documents_required_digest_variables`, чтобы он включал эти имена:

```python
required_names.update(
    {
        "ENABLE_PLAYWRIGHT_FALLBACK",
        "PLAYWRIGHT_TIMEOUT_MS",
        "PLAYWRIGHT_WAIT_UNTIL",
    }
)
```

Изменить `test_trigger_python_requirements_include_digest_dependencies`, чтобы список включал:

```python
"playwright==1.49.1",
```

Добавить тест build-контракта версии Playwright:

```python
def test_playwright_runtime_versions_are_pinned_together() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    trigger_config = (ROOT / "trigger.config.ts").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert package["devDependencies"]["playwright"] == "1.49.1"
    assert 'const PLAYWRIGHT_VERSION = "1.49.1";' in trigger_config
    assert "version: PLAYWRIGHT_VERSION" in trigger_config
    assert "playwright==1.49.1" in requirements
```

- [ ] **Шаг 2: Запустить сфокусированный тест и убедиться, что он падает**

Команда: `python -m pytest tests/test_env_contract.py -v`

Ожидаемо: FAIL, потому что `PLAYWRIGHT_TIMEOUT_MS`, `PLAYWRIGHT_WAIT_UNTIL`, `playwright==1.49.1` и Node `playwright` еще не задокументированы.

- [ ] **Шаг 3: Добавить Trigger.dev Playwright extension**

Изменить `package.json`, чтобы `devDependencies` содержал Node Playwright той же версии, что Python-пакет:

```json
"playwright": "1.49.1"
```

Запустить:

```powershell
npm install
```

Ожидаемо: npm устанавливает зависимости и создает или обновляет `package-lock.json`.

Изменить `trigger.config.ts` до такого точного содержимого:

```ts
import { defineConfig } from "@trigger.dev/sdk/v3";
import { pythonExtension } from "@trigger.dev/python/extension";
import { ffmpeg } from "@trigger.dev/build/extensions/core";
import { playwright } from "@trigger.dev/build/extensions/playwright";

const project = process.env.TRIGGER_PROJECT_REF;
const PLAYWRIGHT_VERSION = "1.49.1";

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
      playwright({
        browsers: ["chromium"],
        headless: true,
        version: PLAYWRIGHT_VERSION,
      }),
      ffmpeg(),
    ],
  },
});
```

- [ ] **Шаг 4: Добавить Python-зависимость и env-флаги**

Добавить в `requirements.txt`:

```text
playwright==1.49.1
```

Обновить `.env.example`:

```env
ENABLE_PLAYWRIGHT_FALLBACK=true
PLAYWRIGHT_TIMEOUT_MS=25000
PLAYWRIGHT_WAIT_UNTIL=domcontentloaded
```

- [ ] **Шаг 5: Запустить сфокусированный тест и убедиться, что он проходит**

Команда:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests/test_env_contract.py -v
```

Ожидаемо: PASS.

- [ ] **Шаг 6: Закоммитить build-контракт**

Команда:

```powershell
git add package.json trigger.config.ts requirements.txt .env.example tests/test_env_contract.py
if (Test-Path package-lock.json) { git add package-lock.json }
git commit -m "feat: add Playwright runtime contract"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 2: Playwright-экстрактор статей

**Файлы:**
- Создать: `src/digest/playwright_article_extractor.py`
- Тест: `tests/test_playwright_article_extractor.py`

- [ ] **Шаг 1: Написать падающие тесты helpers браузерного извлечения**

Создать `tests/test_playwright_article_extractor.py`:

```python
from __future__ import annotations

from digest.models import ArticleStatus
from digest.playwright_article_extractor import extract_text_from_rendered_html, rendered_title


def test_extract_text_from_rendered_html_uses_article_body() -> None:
    html = """
    <html>
      <head><title>JS статья</title></head>
      <body>
        <main>
          <article>
            <h1>JS статья</h1>
            <p>Первый длинный абзац после выполнения JavaScript.</p>
            <p>Второй длинный абзац с полезным текстом.</p>
          </article>
        </main>
      </body>
    </html>
    """

    text = extract_text_from_rendered_html(html, "https://example.com/js")

    assert "Первый длинный абзац" in text
    assert "Второй длинный абзац" in text


def test_rendered_title_reads_title_or_h1() -> None:
    assert rendered_title("<html><head><title>A</title></head><body></body></html>") == "A"
    assert rendered_title("<html><body><h1>B</h1></body></html>") == "B"
```

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Команда: `python -m pytest tests/test_playwright_article_extractor.py -v`

Ожидаемо: FAIL, потому что модуль еще не создан.

- [ ] **Шаг 3: Реализовать Playwright extractor**

Создать `src/digest/playwright_article_extractor.py`:

```python
from __future__ import annotations

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
import trafilatura

from digest.models import ArticleStatus, ExtractedArticle


def extract_text_from_rendered_html(html: str, url: str) -> str:
    extracted = trafilatura.extract(html, url=url, include_comments=False, include_tables=False)
    if extracted:
        return extracted.strip()
    soup = BeautifulSoup(html, "lxml")
    article = soup.find("article") or soup.find("main") or soup.body
    return article.get_text("\n", strip=True) if article else soup.get_text("\n", strip=True)


def rendered_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(" ", strip=True) if h1 else None


class PlaywrightArticleExtractor:
    def __init__(
        self,
        *,
        timeout_ms: int,
        wait_until: str,
        min_text_length: int,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.wait_until = wait_until
        self.min_text_length = min_text_length

    async def extract(self, url: str) -> ExtractedArticle:
        try:
            async with async_playwright() as runtime:
                browser = None
                context = None
                browser = await runtime.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0.0.0 Safari/537.36"
                        )
                    )
                    page = await context.new_page()
                    await page.goto(url, wait_until=self.wait_until, timeout=self.timeout_ms)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 5000))
                    except PlaywrightTimeoutError:
                        pass
                    html = await page.content()
                finally:
                    if context is not None:
                        await context.close()
                    if browser is not None:
                        await browser.close()
            text = extract_text_from_rendered_html(html, url)
            if len(text) < self.min_text_length:
                return ExtractedArticle(
                    url=url,
                    title=rendered_title(html),
                    text=text,
                    extraction_method="playwright",
                    status=ArticleStatus.FAILED_EXTRACTION,
                    error=f"rendered text shorter than {self.min_text_length}",
                )
            return ExtractedArticle(
                url=url,
                title=rendered_title(html),
                text=text,
                extraction_method="playwright",
                status=ArticleStatus.EXTRACTED,
            )
        except Exception as exc:
            return ExtractedArticle(
                url=url,
                title=None,
                text="",
                extraction_method="playwright",
                status=ArticleStatus.FAILED_EXTRACTION,
                error=str(exc),
            )
```

- [ ] **Шаг 4: Запустить helper-тесты**

Команда: `python -m pytest tests/test_playwright_article_extractor.py -v`

Ожидаемо: PASS.

- [ ] **Шаг 5: Запустить локальную установку браузера и smoke import**

Команда:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python -c "from digest.playwright_article_extractor import PlaywrightArticleExtractor; print(PlaywrightArticleExtractor(timeout_ms=1000, wait_until='domcontentloaded', min_text_length=10))"
```

Ожидаемо: Chromium устанавливается локально, import печатает объект `PlaywrightArticleExtractor`.

- [ ] **Шаг 6: Закоммитить Playwright extractor**

Команда:

```powershell
git add src/digest/playwright_article_extractor.py tests/test_playwright_article_extractor.py
git commit -m "feat: add Playwright article extractor"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 3: Подключение fallback к HTTP-экстрактору и пайплайну

**Файлы:**
- Изменить: `src/digest/config.py`
- Изменить: `src/digest/article_extractor.py`
- Изменить: `src/digest/pipeline.py`
- Тест: `tests/test_config.py`
- Тест: `tests/test_article_extractor.py`

- [ ] **Шаг 1: Расширить config- и fallback-тесты**

Изменить `tests/test_config.py`:

```python
def test_settings_reads_playwright_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_TARGET_CHAT_ID", "42")
    monkeypatch.setenv("NOTEBOOKLM_AUTH_JSON", '{"cookies":[],"origins":[]}')
    monkeypatch.setenv("NOTEBOOKLM_ACCOUNT_EMAIL", "user@example.com")
    monkeypatch.setenv("STATE_DATABASE_URL", "postgresql://user:pass@localhost:5432/digest")
    monkeypatch.setenv("ENABLE_PLAYWRIGHT_FALLBACK", "true")
    monkeypatch.setenv("PLAYWRIGHT_TIMEOUT_MS", "25000")
    monkeypatch.setenv("PLAYWRIGHT_WAIT_UNTIL", "domcontentloaded")

    settings = DigestSettings.from_env()

    assert settings.enable_playwright_fallback is True
    assert settings.playwright_timeout_ms == 25000
    assert settings.playwright_wait_until == "domcontentloaded"
```

Изменить `tests/test_article_extractor.py`, чтобы проверить factory для браузерного fallback:

```python
from digest.article_extractor import DisabledBrowserFallback, build_article_fallback
from digest.playwright_article_extractor import PlaywrightArticleExtractor


def test_build_article_fallback_returns_disabled_fallback_when_flag_off() -> None:
    fallback = build_article_fallback(
        enabled=False,
        timeout_ms=25000,
        wait_until="domcontentloaded",
        min_text_length=600,
    )

    assert isinstance(fallback, DisabledBrowserFallback)


def test_build_article_fallback_returns_playwright_fallback_when_flag_on() -> None:
    fallback = build_article_fallback(
        enabled=True,
        timeout_ms=25000,
        wait_until="domcontentloaded",
        min_text_length=600,
    )

    assert isinstance(fallback, PlaywrightArticleExtractor)
```

- [ ] **Шаг 2: Запустить config- и fallback-тесты и убедиться, что они падают**

Команда: `python -m pytest tests/test_config.py tests/test_article_extractor.py -v`

Ожидаемо: FAIL, потому что `DigestSettings` пока не содержит `playwright_timeout_ms` и `playwright_wait_until`, а `build_article_fallback` еще не существует.

- [ ] **Шаг 3: Добавить поля config**

Изменить `src/digest/config.py` dataclass fields:

```python
    playwright_timeout_ms: int
    playwright_wait_until: str
```

Не добавлять `enable_playwright_fallback` повторно: это поле уже создано основным планом.

Изменить `DigestSettings.from_env()`:

```python
            playwright_timeout_ms=_int_env("PLAYWRIGHT_TIMEOUT_MS", 25000),
            playwright_wait_until=os.getenv("PLAYWRIGHT_WAIT_UNTIL", "domcontentloaded"),
```

- [ ] **Шаг 4: Добавить fallback factory**

Добавить в `src/digest/article_extractor.py`:

```python
def build_article_fallback(*, enabled: bool, timeout_ms: int, wait_until: str, min_text_length: int) -> ArticleFallback:
    if not enabled:
        return DisabledBrowserFallback()
    from digest.playwright_article_extractor import PlaywrightArticleExtractor

    return PlaywrightArticleExtractor(
        timeout_ms=timeout_ms,
        wait_until=wait_until,
        min_text_length=min_text_length,
    )
```

Изменить `src/digest/pipeline.py` import:

```python
from digest.article_extractor import HttpArticleExtractor, build_article_fallback
```

Изменить создание extractor в `run_digest_for_date()`:

```python
        extractor = HttpArticleExtractor(
            client=client,
            min_text_length=settings.article_min_text_length,
            fallback=build_article_fallback(
                enabled=settings.enable_playwright_fallback,
                timeout_ms=settings.playwright_timeout_ms,
                wait_until=settings.playwright_wait_until,
                min_text_length=settings.article_min_text_length,
            ),
        )
```

- [ ] **Шаг 5: Запустить сфокусированные тесты**

Команда:

```powershell
python -m pytest tests/test_config.py tests/test_article_extractor.py tests/test_pipeline.py -v
```

Ожидаемо: PASS.

- [ ] **Шаг 6: Закоммитить подключение fallback**

Команда:

```powershell
git add src/digest/config.py src/digest/article_extractor.py src/digest/pipeline.py tests/test_config.py tests/test_article_extractor.py tests/test_pipeline.py
git commit -m "feat: wire Playwright fallback into extraction"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 4: Playwright preflight

**Файлы:**
- Изменить: `src/digest/preflight.py`
- Тест: `tests/test_preflight_playwright.py`

- [ ] **Шаг 1: Написать падающий preflight-тест**

Создать `tests/test_preflight_playwright.py`:

```python
from __future__ import annotations

import pytest

from digest.preflight import PreflightError, validate_playwright_wait_until


def test_validate_playwright_wait_until_accepts_known_values() -> None:
    validate_playwright_wait_until("commit")
    validate_playwright_wait_until("domcontentloaded")
    validate_playwright_wait_until("load")
    validate_playwright_wait_until("networkidle")


def test_validate_playwright_wait_until_rejects_unknown_value() -> None:
    with pytest.raises(PreflightError, match="PLAYWRIGHT_WAIT_UNTIL"):
        validate_playwright_wait_until("after-party")
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Команда: `python -m pytest tests/test_preflight_playwright.py -v`

Ожидаемо: FAIL, потому что `validate_playwright_wait_until` еще не существует.

- [ ] **Шаг 3: Реализовать Playwright preflight helpers**

Добавить в `src/digest/preflight.py`:

```python
VALID_PLAYWRIGHT_WAIT_UNTIL = {"commit", "domcontentloaded", "load", "networkidle"}


def validate_playwright_wait_until(value: str) -> None:
    if value not in VALID_PLAYWRIGHT_WAIT_UNTIL:
        raise PreflightError(f"PLAYWRIGHT_WAIT_UNTIL must be one of {sorted(VALID_PLAYWRIGHT_WAIT_UNTIL)}")


async def check_playwright_browser() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as runtime:
        browser = None
        browser = await runtime.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content("<html><body>ok</body></html>")
            text = await page.text_content("body")
        finally:
            if browser is not None:
                await browser.close()
    if text != "ok":
        raise PreflightError("Playwright Chromium smoke check вернул неожиданный текст")
```

Изменить `run_preflight(settings)`:

```python
    if settings.enable_playwright_fallback:
        check_required_imports(["playwright"])
        validate_playwright_wait_until(settings.playwright_wait_until)
        await check_playwright_browser()
```

- [ ] **Шаг 4: Запустить preflight-тесты**

Команда:

```powershell
python -m pytest tests/test_preflight.py tests/test_preflight_playwright.py -v
```

Ожидаемо: PASS.

- [ ] **Шаг 5: Запустить локальный browser smoke-check**

Команда:

```powershell
python -m playwright install chromium
@'
import asyncio
from digest.preflight import check_playwright_browser
asyncio.run(check_playwright_browser())
print("playwright ok")
'@ | python -
```

Ожидаемо: команда печатает `playwright ok`.

- [ ] **Шаг 6: Закоммитить preflight**

Команда:

```powershell
git add src/digest/preflight.py tests/test_preflight_playwright.py
git commit -m "feat: verify Playwright runtime in preflight"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

### Задача 5: Документация и Trigger dry-run

**Файлы:**
- Изменить: `README.md`

- [ ] **Шаг 1: Обновить README локальной настройкой Playwright**

Добавить в `README.md`:

````markdown
## Playwright fallback

Для локального dev mode Trigger.dev build extension не устанавливает браузер автоматически, поэтому один раз выполнить:

```powershell
python -m playwright install chromium
```

В Production Chromium устанавливает Trigger.dev build extension:

```ts
const PLAYWRIGHT_VERSION = "1.49.1";

playwright({
  browsers: ["chromium"],
  headless: true,
  version: PLAYWRIGHT_VERSION,
})
```

Проверка:

```powershell
$env:ENABLE_PLAYWRIGHT_FALLBACK="true"
python -m pytest tests/test_playwright_article_extractor.py tests/test_preflight_playwright.py -v
npm run trigger:dry-run
```
````

- [ ] **Шаг 2: Запустить полный локальный набор тестов**

Команда:

```powershell
python -m pytest -v
npm run test:trigger
```

Ожидаемо: PASS.

- [ ] **Шаг 3: Запустить Trigger dry-run с включенным Playwright**

Команда:

```powershell
if (-not $env:TRIGGER_PROJECT_REF) { throw "Перед dry-run задайте TRIGGER_PROJECT_REF в текущем shell" }
$env:ENABLE_PLAYWRIGHT_FALLBACK="true"
npm run trigger:dry-run
```

Ожидаемо: Trigger.dev build устанавливает Python-зависимости, `ffmpeg` и зависимости Playwright Chromium; dry-run завершается успешно.

- [ ] **Шаг 4: Закоммитить документацию**

Команда:

```powershell
git add README.md
git commit -m "docs: document Playwright fallback"
```

Ожидаемо: коммит проходит; если Git-репозиторий отсутствует, зафиксировать это в отчете и продолжить без коммита.

## Самопроверка

- Покрытие спеки: Playwright fallback срабатывает, когда HTTP-извлечение пустое, слишком короткое, похоже на JS-заглушку или завершилось ошибкой; Trigger.dev runtime устанавливает Chromium; Node/Python версии Playwright закреплены одинаково; preflight запускает браузер до Telegram/NotebookLM side effects.
- Проверка placeholder-маркеров: запрещенных маркеров из раздела No Placeholders не найдено.
- Согласованность типов: `PlaywrightArticleExtractor.extract()` возвращает `ExtractedArticle` с `extraction_method="playwright"`, подключается к протоколу `ArticleFallback` из основного плана, а `DigestSettings` расширяется только новыми полями `playwright_timeout_ms` и `playwright_wait_until`.

План готов и сохранен в `docs/superpowers/plans/2026-06-26-playwright-article-fallback.md`. Два варианта исполнения:

**1. Subagent-Driven (рекомендуется)** - запускать свежего subagent на каждую задачу и делать review между задачами

**2. Inline Execution** - выполнять задачи в этой сессии через executing-plans, пакетами с контрольными точками

Какой вариант выбираем?
