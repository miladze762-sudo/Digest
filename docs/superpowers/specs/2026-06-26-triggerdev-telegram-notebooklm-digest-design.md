# Спецификация: ежедневный дайджест ciscrypted в NotebookLM и Telegram

## Статус

Утверждено пользователем: 2026-06-26.

## Цель

Нужна программа для Trigger.dev, которая один раз в день обрабатывает дайджест из Telegram-канала `ciscrypted`, переходит по ссылкам из последнего дневного сообщения, извлекает полный текст статей, загружает материалы в отдельный блокнот NotebookLM, генерирует Audio Overview и отправляет MP3 в личный чат Telegram-бота.

Правило результата: один день = один блокнот NotebookLM = один MP3-подкаст.

## Источники и внешние зависимости

- Telegram-канал: `https://t.me/ciscrypted`.
- Чтение Telegram: MTProto через `Telethon`.
- Оркестрация: Trigger.dev scheduled task.
- Python-зависимости в Trigger.dev: `pythonExtension`.
- NotebookLM: неофициальная библиотека `notebooklm-py` из `https://github.com/teng-lin/notebooklm-py`.
- Генерация аудио: встроенный NotebookLM Audio Overview через `notebooklm-py`.
- Отправка результата: Telegram Bot API.
- Состояние обработки: легковесное постоянное хранилище `state_store`, например PostgreSQL/Supabase/Neon или другой durable SQL/KV backend, доступный из Trigger.dev.
- Runtime-инструменты: Playwright browser runtime для fallback-извлечения статей и `ffmpeg` для приведения аудио к MP3.

Важно: `notebooklm-py` использует неофициальные/недокументированные механизмы NotebookLM. В спецификации это считается осознанным техническим риском: при изменениях NotebookLM интеграция может потребовать правки.

## Архитектура

Система состоит из scheduled wrapper task в Trigger.dev, отдельной processor task для обработки конкретной даты, Python-пайплайна и постоянного `state_store`.

Trigger.dev отвечает за:

- ежедневный запуск по расписанию с рандомизированным окном старта;
- передачу даты обработки;
- хранение секретов;
- run logs;
- run metadata;
- timeout и retry;
- global idempotency key для обработки конкретной даты;
- ограничение параллельности processor task.

Python-пайплайн отвечает за:

- чтение сообщений Telegram через Telethon;
- выбор дневного дайджест-сообщения;
- извлечение ссылок;
- скачивание и очистку полного текста статей;
- чтение и обновление `state_store` перед внешними side effects;
- циклическую очистку старых NotebookLM-блокнотов перед созданием нового;
- создание блокнота NotebookLM;
- загрузку статей в NotebookLM;
- запуск и скачивание Audio Overview;
- отправку MP3 через Telegram Bot API.

Логические модули:

- `scheduleDigestWindow` — плановый запуск, вычисление целевой даты и случайной задержки внутри окна.
- `processDigestForDate` — обработка конкретной даты с global idempotency key и ограничением параллельности.
- `telegram_reader` — подключение к `ciscrypted`, поиск последнего сообщения за дату со ссылками.
- `url_extractor` — извлечение и дедупликация URL с сохранением порядка.
- `article_extractor` — извлечение текста статей через HTTP-парсер и Playwright fallback.
- `notebooklm_client` — создание блокнота, добавление источников, запуск Audio Overview, скачивание MP3.
- `notebook_cleanup` — учет блокнотов `ciscrypted`, циклическое удаление старых блокнотов при приближении к лимиту.
- `telegram_bot_sender` — отправка MP3 и текстовых уведомлений.
- `state_store` — постоянное состояние обработки дат, внешних side effects и recovery-флагов.
- `run_report` — сбор статистики, ошибок и данных для Trigger.dev metadata.

## Расписание и дата обработки

Задача запускается ночью за прошедший календарный день по московскому времени. Время фактического запуска обработки должно быть разным и попадать в окно с `02:00` до `04:00` по `Europe/Moscow`.

Требование:

- запуск обработки должен происходить ночью в окне `02:00-04:00` по `Europe/Moscow`;
- время запуска не должно быть фиксированным: каждый день Trigger.dev выбирает задержку внутри окна;
- рандомизация должна выполняться на уровне Trigger.dev, а не через долгий `sleep` внутри Python-пайплайна;
- целевая дата всегда вычисляется по `Europe/Moscow`, а не по timezone сервера;
- пример: запуск 2026-06-26 в 03:30 по Москве обрабатывает 2026-06-25.

Рекомендуемая схема:

1. Scheduled task `scheduleDigestWindow` запускается каждый день в `02:00 Europe/Moscow`.
2. Она вычисляет случайную задержку `0-120` минут.
3. Она запускает основную task `processDigestForDate` через Trigger.dev `delay` или `wait.for`.
4. Основная task получает `targetDate`, `plannedStartAt`, `randomDelayMinutes` и global idempotency key `ciscrypted:YYYY-MM-DD`.
5. `processDigestForDate` работает с `queue.concurrencyLimit: 1` и перед любыми внешними side effects читает/создает запись в `state_store` по `targetDate`.

Если Trigger.dev cron настроен в UTC, cron должен соответствовать `02:00` по Москве. Например, для Москвы без перехода на летнее время это `23:00 UTC` предыдущего календарного дня.

Чтобы время действительно не выглядело одинаковым изо дня в день, выбранная задержка записывается в run metadata. Если реализация может прочитать metadata прошлого успешного запуска, она должна избегать повторения того же `randomDelayMinutes`; если это невозможно, достаточно криптографически случайного выбора внутри окна.

## Выбор Telegram-сообщения

Источник только один: `https://t.me/ciscrypted`.

Алгоритм:

1. Подключиться к Telegram через Telethon.
2. Получить сообщения канала за целевую дату в `Europe/Moscow`.
3. Найти сообщения, содержащие хотя бы одну валидную ссылку.
4. Выбрать последнее сообщение за день со ссылками.
5. Считать это сообщение дневным дайджестом.

Если сообщение не найдено, блокнот и MP3 не создаются. Бот отправляет текстовое уведомление о том, что дайджест за дату не найден.

Ссылка на оригинальный пост формируется так:

```text
https://t.me/ciscrypted/<telegram_message_id>
```

## Извлечение ссылок

Из выбранного сообщения извлекаются все URL.

Требования:

- удалить дубликаты;
- сохранить порядок появления в сообщении;
- игнорировать невалидные URL;
- учитывать ссылки из текста сообщения и, если Telethon их предоставляет, из message entities.

## Извлечение статей

Извлечение работает в два слоя.

Первый слой: обычный HTTP-запрос и парсер основного текста статьи, например `trafilatura` или `readability`.

Второй слой: Playwright fallback. Он используется, если:

- HTTP-слой вернул пустой текст;
- текст слишком короткий;
- страница похожа на JavaScript-заглушку;
- HTTP-слой вернул ошибку, но URL потенциально можно открыть браузером.

Для каждой ссылки фиксируется:

- URL;
- заголовок, если удалось извлечь;
- метод извлечения: `http` или `playwright`;
- длина текста;
- статус;
- ошибка, если есть.

Если статью не удалось извлечь полностью, запуск продолжается. Успешные статьи все равно загружаются в NotebookLM, а проблемные ссылки попадают в отчет и Trigger.dev metadata.

## Создание NotebookLM-блокнота

На каждую целевую дату создается отдельный блокнот.

Формат названия:

```text
ciscrypted YYYY-MM-DD
```

Пример:

```text
ciscrypted 2026-06-25
```

В блокнот добавляются успешно извлеченные статьи как отдельные текстовые источники. Каждый источник должен содержать:

- заголовок статьи;
- оригинальный URL статьи;
- дату дайджеста;
- полный извлеченный текст.

Если есть проблемные ссылки, допускается добавить отдельный текстовый источник `Ошибки извлечения`, где перечислены URL и причины ошибок. Это помогает понимать неполноту дневного набора внутри самого NotebookLM.

После создания блокнота программа сохраняет:

- `notebookId`;
- `notebookUrl`;
- email Google-аккаунта, через который создан блокнот.

Email берется из переменной `NOTEBOOKLM_ACCOUNT_EMAIL`.

## Управление лимитом NotebookLM-блокнотов

Для проекта устанавливается операционный лимит: максимум `50` NotebookLM-блокнотов с префиксом `ciscrypted `. Даже если лимит аккаунта выше, спецификация считает `50` рабочим пределом, чтобы оставить запас для ручных блокнотов и изменений тарифов NotebookLM.

Перед созданием нового блокнота `notebook_cleanup` выполняет циклическую очистку:

1. Получает список NotebookLM-блокнотов, доступных аккаунту `NOTEBOOKLM_ACCOUNT_EMAIL`.
2. Оставляет только блокноты с названием формата `ciscrypted YYYY-MM-DD`.
3. Сверяет найденные блокноты с `state_store` по `notebookId` и `targetDate`.
4. Если количество блокнотов `ciscrypted` больше или равно `NOTEBOOKLM_CLEANUP_THRESHOLD`, удаляет самые старые блокноты до уровня `NOTEBOOKLM_CLEANUP_TARGET`.
5. Не удаляет блокнот текущей даты, блокноты с флагом `protected=true` в `state_store` и блокноты моложе `NOTEBOOKLM_KEEP_RECENT_DAYS`.
6. Записывает список удаленных блокнотов в `state_store` и краткую сводку в Trigger.dev metadata.

Рекомендуемые значения для MVP:

```env
NOTEBOOKLM_MAX_NOTEBOOKS=50
NOTEBOOKLM_CLEANUP_THRESHOLD=45
NOTEBOOKLM_CLEANUP_TARGET=40
NOTEBOOKLM_KEEP_RECENT_DAYS=7
```

Если `notebooklm-py` или текущие учетные данные не позволяют удалить блокнот, а количество блокнотов уже достигло `NOTEBOOKLM_MAX_NOTEBOOKS`, новая обработка не создает блокнот и бот отправляет текстовое уведомление о необходимости ручной очистки. Это лучше, чем создать частичный результат и потерять управляемость лимита.

## Audio Overview

Аудио генерируется встроенной функцией NotebookLM Audio Overview через `notebooklm-py`.

Требования:

- не использовать внешний TTS в MVP;
- не требовать точной длительности;
- ориентироваться на подкаст примерно 15-20 минут, но фактическая длительность определяется NotebookLM по объему и содержанию источников;
- ждать готовности Audio Overview через polling с общим лимитом ожидания;
- скачать готовое аудио;
- привести итоговый файл к MP3 перед отправкой в Telegram. Если NotebookLM или `notebooklm-py` вернет другой аудиоформат, пайплайн должен конвертировать файл в MP3, например через `ffmpeg`.

Если Audio Overview не готов за отведенное время, бот отправляет текстовое уведомление об ошибке. Если блокнот уже создан, уведомление должно содержать ссылку на него.

## Отправка в Telegram

Готовый MP3 отправляется через Telegram Bot API в личный чат пользователя.

Требуются:

- `TELEGRAM_BOT_TOKEN`;
- `TELEGRAM_TARGET_CHAT_ID`.

Подпись к MP3 должна иметь такой вид:

```text
Дайджест ciscrypted за 2026-06-25
Статьи: 10 обработано, 2 с ошибками

Оригинальный Telegram-пост
Блокнот NotebookLM [nicolaibaskow@gmail.com]
```

Правила подписи:

- строка `Оригинальный Telegram-пост` кликабельна и ведет на оригинальный Telegram-пост;
- строка `Блокнот NotebookLM [nicolaibaskow@gmail.com]` кликабельна и ведет на созданный блокнот NotebookLM;
- email внутри квадратных скобок берется из `NOTEBOOKLM_ACCOUNT_EMAIL`;
- для кликабельных ссылок используется `parse_mode=HTML`;
- пользователь в Telegram не должен видеть голые URL, HTML-теги или Markdown-скобки.

Пример HTML-представления:

```html
Дайджест ciscrypted за 2026-06-25
Статьи: 10 обработано, 2 с ошибками

<a href="https://t.me/ciscrypted/12345">Оригинальный Telegram-пост</a>
<a href="https://notebooklm.google.com/notebook/...">Блокнот NotebookLM [nicolaibaskow@gmail.com]</a>
```

Если подпись слишком длинная для Telegram, MP3 отправляется с короткой подписью, а полный отчет отправляется отдельным текстовым сообщением.

## Состояние и наблюдаемость в Trigger.dev

В MVP не хранится постоянный архив полных текстов статей и MP3. Полные материалы живут во внешних системах: блокнот в NotebookLM и MP3 в Telegram.

При этом операционное состояние обязательно хранится в `state_store`. Trigger.dev metadata является только краткой проекцией для run logs и dashboard, а не источником истины для повторов.

Минимальная запись `state_store` для одной даты:

```json
{
  "targetDate": "2026-06-25",
  "idempotencyKey": "ciscrypted:2026-06-25",
  "status": "sent_to_telegram",
  "digestMessageId": 12345,
  "digestMessageUrl": "https://t.me/ciscrypted/12345",
  "notebookId": "notebook-id",
  "notebookUrl": "https://notebooklm.google.com/notebook/...",
  "notebookName": "ciscrypted 2026-06-25",
  "notebookProtected": false,
  "audioTelegramMessageId": 98765,
  "articleCount": 12,
  "articleErrorCount": 2,
  "lastError": null,
  "createdAt": "2026-06-26T03:17:00+03:00",
  "updatedAt": "2026-06-26T03:58:00+03:00"
}
```

Правила записи состояния:

- `targetDate` является уникальным ключом;
- перед созданием блокнота pipeline проверяет, нет ли уже `notebookId` для даты;
- перед отправкой MP3 pipeline проверяет, нет ли уже `audioTelegramMessageId`;
- повтор completed-run возвращает существующее состояние и не создает новый блокнот, не добавляет источники повторно и не отправляет MP3 повторно;
- если внешний side effect успешно выполнен, запись в `state_store` обновляется сразу после него;
- если `state_store` недоступен, обработка не начинает внешние side effects.

Trigger.dev metadata должна включать короткий снимок состояния:

```json
{
  "targetDate": "2026-06-25",
  "sourceChannel": "ciscrypted",
  "schedule": {
    "windowStart": "2026-06-26T02:00:00+03:00",
    "windowEnd": "2026-06-26T04:00:00+03:00",
    "plannedStartAt": "2026-06-26T03:17:00+03:00",
    "randomDelayMinutes": 77
  },
  "digestMessage": {
    "telegramMessageId": 12345,
    "publishedAt": "2026-06-25T21:10:00+03:00",
    "url": "https://t.me/ciscrypted/12345",
    "urlCount": 12
  },
  "articles": [
    {
      "url": "https://example.com/article",
      "title": "Название статьи",
      "status": "added_to_notebook",
      "extractionMethod": "http",
      "textLength": 18420,
      "error": null
    },
    {
      "url": "https://example.com/broken",
      "title": null,
      "status": "failed_extraction",
      "extractionMethod": "playwright",
      "textLength": 0,
      "error": "timeout"
    }
  ],
  "notebook": {
    "status": "created",
    "id": "notebook-id",
    "url": "https://notebooklm.google.com/notebook/...",
    "accountEmail": "nicolaibaskow@gmail.com",
    "name": "ciscrypted 2026-06-25"
  },
  "audio": {
    "status": "sent_to_telegram",
    "fileSizeBytes": 24500000,
    "telegramMessageId": 98765
  },
  "cleanup": {
    "notebookCountBefore": 45,
    "deletedNotebookCount": 5,
    "notebookCountAfter": 40
  }
}
```

Статусы статей:

- `pending`;
- `extracting`;
- `extracted`;
- `failed_extraction`;
- `added_to_notebook`.

Статусы блокнота:

- `pending`;
- `created`;
- `failed`.

Статусы аудио:

- `pending`;
- `generating`;
- `downloaded`;
- `sent_to_telegram`;
- `failed`.

Trigger.dev metadata не должна содержать полные тексты статей, полные списки больших ошибок и большие HTML-фрагменты. Если список ссылок слишком большой, metadata хранит только счетчики и первые несколько ошибок, а полный отчет отправляется отдельным текстовым сообщением в Telegram или сохраняется в `state_store` в сжатом виде.

## Idempotency и повторы

Каждая обработка даты должна иметь global idempotency key:

```text
ciscrypted:YYYY-MM-DD
```

Idempotency применяется на двух уровнях:

- Trigger.dev processor task `processDigestForDate` запускается с global idempotency key `ciscrypted:YYYY-MM-DD` и `queue.concurrencyLimit: 1`;
- `state_store` хранит `targetDate` как уникальный ключ и проверяется перед каждым внешним side effect.

Поведение при повторе:

- если дата уже в статусе `sent_to_telegram`, task завершает run без повторной отправки;
- если блокнот уже создан, но аудио не отправлено, task переиспользует `notebookId` и продолжает с генерации/скачивания аудио;
- если MP3 уже отправлен, но run завершился ошибкой после отправки, task не отправляет MP3 повторно и помечает дату как `sent_to_telegram` после сверки с `audioTelegramMessageId`;
- ручной повтор с намеренным пересозданием результата требует явного флага `forceReprocess=true`, который создает новый idempotency key с суффиксом попытки и помечает старый результат как superseded.

Trade-off: `state_store` добавляет одну внешнюю зависимость и env-настройку, зато убирает главный риск дублей после retry и делает восстановление после частичных сбоев наблюдаемым.

## Ошибки

Сценарии:

1. Нет дайджест-сообщения за день.
   - Блокнот не создается.
   - MP3 не создается.
   - Бот отправляет текстовое уведомление.

2. В дайджест-сообщении нет валидных ссылок.
   - Блокнот не создается.
   - MP3 не создается.
   - Бот отправляет текстовый отчет.

3. Часть статей не извлечена.
   - Запуск продолжается.
   - Успешные статьи добавляются в NotebookLM.
   - Проблемные ссылки видны в metadata и отчете.

4. NotebookLM недоступен или `notebooklm-py` сломался.
   - Ошибка фиксируется в Trigger.dev logs и metadata.
   - Бот отправляет уведомление, если это возможно.

5. Audio Overview не создан за лимит времени.
   - Бот получает текстовое уведомление.
   - Если блокнот создан, сообщение содержит кликабельную ссылку на блокнот.

6. MP3 слишком большой для Telegram Bot API.
   - Бот отправляет текстовое уведомление.
   - Постоянное object storage в MVP не используется, поэтому внешняя ссылка на MP3 не создается.

7. `state_store` недоступен.
   - Внешние side effects не начинаются.
   - Ошибка фиксируется в Trigger.dev logs.
   - Если Telegram Bot API доступен, бот отправляет текстовое уведомление.

8. Количество блокнотов `ciscrypted` достигло `NOTEBOOKLM_MAX_NOTEBOOKS`, а удалить старые блокноты не удалось.
   - Новый блокнот не создается.
   - Бот отправляет уведомление о необходимости ручной очистки NotebookLM.
   - В `state_store` фиксируется статус `cleanup_required`.

9. В runtime Trigger.dev отсутствует Playwright browser runtime или `ffmpeg`.
   - Task завершается на preflight-проверке до чтения Telegram и создания NotebookLM.
   - Ошибка фиксируется как ошибка деплой-контракта, а не как ошибка конкретной статьи.

## Секреты и конфигурация

Все чувствительные данные хранятся в Trigger.dev environment variables / secrets.

Минимальный набор:

```env
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION_STRING=
TELEGRAM_SOURCE_CHANNEL=ciscrypted

TELEGRAM_BOT_TOKEN=
TELEGRAM_TARGET_CHAT_ID=

NOTEBOOKLM_AUTH=
NOTEBOOKLM_ACCOUNT_EMAIL=
NOTEBOOKLM_MAX_NOTEBOOKS=50
NOTEBOOKLM_CLEANUP_THRESHOLD=45
NOTEBOOKLM_CLEANUP_TARGET=40
NOTEBOOKLM_KEEP_RECENT_DAYS=7

STATE_DATABASE_URL=
DIGEST_STATE_TABLE=digest_runs

DIGEST_TIMEZONE=Europe/Moscow
DIGEST_CRON=0 2 * * *
DIGEST_RANDOM_WINDOW_START=02:00
DIGEST_RANDOM_WINDOW_END=04:00
DIGEST_RANDOM_DELAY_MINUTES_MIN=0
DIGEST_RANDOM_DELAY_MINUTES_MAX=120
AUDIO_OVERVIEW_TARGET_MINUTES=15-20
```

`DIGEST_CRON=0 2 * * *` означает запуск wrapper-task в `02:00`, если Trigger.dev schedule настраивается в timezone `Europe/Moscow`. Если расписание задается в UTC, эквивалент для Москвы: `0 23 * * *`. Фактический запуск обработки происходит позже, после случайной задержки от 0 до 120 минут.

`TELEGRAM_SESSION_STRING` нужен для Telethon, чтобы Trigger.dev не проходил интерактивную авторизацию Telegram при каждом запуске.

`NOTEBOOKLM_AUTH` является абстрактным именем для учетных данных NotebookLM. Конкретный формат зависит от версии и требований `notebooklm-py`. Реализация должна включать отдельный setup-скрипт или инструкцию для получения и проверки этих учетных данных до деплоя.

`STATE_DATABASE_URL` является секретом. В `state_store` нельзя хранить полные тексты статей, MP3, cookies, Telegram session string или учетные данные NotebookLM.

## Runtime и деплой-контракт Trigger.dev

Реализация должна явно описывать все runtime-зависимости в `trigger.config.ts`, а не полагаться на локальную машину разработчика.

Обязательные элементы:

- TypeScript task лежат в `src/trigger` и экспортируются из файлов, которые попадают в `dirs`;
- Python-пайплайн попадает в `pythonExtension` через `scripts: ["./src/**/*.py"]` или эквивалент текущего проекта;
- Python-зависимости добавлены в `pythonExtension({ requirements: [...] })` или requirements-файл, который реально читает Trigger.dev build;
- Playwright fallback использует Trigger.dev Playwright extension и устанавливает Chromium/runtime-браузер во время build;
- конвертация аудио использует установленный binary `ffmpeg` через Trigger.dev `ffmpeg` extension или `aptGet`/system packages;
- `maxDuration` processor task покрывает худший случай: извлечение статей, загрузку в NotebookLM, ожидание Audio Overview, скачивание и конвертацию MP3;
- preflight-шаг проверяет доступность `ffmpeg`, импорт Python-зависимостей, auth NotebookLM, подключение к `state_store` и возможность запустить Playwright browser.

Минимальные Python-зависимости:

```text
telethon
notebooklm-py
trafilatura
readability-lxml
playwright
httpx
beautifulsoup4
lxml
```

Если выбран другой HTTP-парсер или другой NotebookLM-клиент, список зависимостей обновляется в спецификации и в `trigger.config.ts` одновременно.

## Тестирование

Unit-тесты:

- извлечение URL из текста Telegram-сообщения;
- дедупликация URL с сохранением порядка;
- выбор последнего сообщения за дату;
- расчет `targetDate` по `Europe/Moscow`;
- формирование HTML-подписи Telegram;
- формирование Trigger.dev metadata;
- обновление статусов статей;
- расчет случайной задержки запуска внутри окна `02:00-04:00 Europe/Moscow`;
- формирование global idempotency key `ciscrypted:YYYY-MM-DD`;
- переходы состояния в `state_store` без повторных side effects;
- выбор старых NotebookLM-блокнотов для удаления при `NOTEBOOKLM_CLEANUP_THRESHOLD`.

Integration dry-run:

- подключиться к `ciscrypted`;
- найти дайджест за указанную дату;
- извлечь ссылки;
- скачать тексты статей;
- не создавать NotebookLM-блокнот;
- не отправлять MP3.

NotebookLM smoke-test:

- создать тестовый блокнот с 1-2 короткими текстами;
- запустить Audio Overview;
- скачать MP3;
- проверить получение `notebookUrl`.

Telegram Bot smoke-test:

- отправить тестовое текстовое сообщение;
- отправить небольшой тестовый MP3;
- проверить, что строки `Оригинальный Telegram-пост` и `Блокнот NotebookLM [...]` отображаются как кликабельный текст.

Trigger.dev staging run:

- ручной запуск task за конкретную дату;
- проверка run metadata;
- проверка global idempotency key;
- повторный запуск той же даты не создает второй блокнот и не отправляет второй MP3;
- проверка, что scheduled wrapper планирует обработку внутри окна `02:00-04:00 Europe/Moscow`;
- проверка статусов успешных и проблемных ссылок;
- проверка preflight для Python-зависимостей, Playwright, `ffmpeg` и `state_store`;
- проверка NotebookLM cleanup на тестовых блокнотах или dry-run cleanup mode.

## Критерии приемки

MVP считается готовым, если ручной запуск Trigger.dev за прошедший день:

1. Находит последнее сообщение со ссылками в `ciscrypted` за целевую дату.
2. Извлекает ссылки без дублей и в исходном порядке.
3. Получает полный текст доступных статей.
4. Не останавливается из-за отдельных проблемных ссылок.
5. Создает один блокнот NotebookLM с названием `ciscrypted YYYY-MM-DD`.
6. Добавляет все успешно извлеченные статьи в блокнот.
7. Генерирует Audio Overview через NotebookLM.
8. Скачивает MP3.
9. Отправляет MP3 в личный чат через Telegram Bot API.
10. Отправляет подпись в согласованном формате с кликабельным оригинальным постом и кликабельным блокнотом NotebookLM.
11. Показывает в Trigger.dev metadata, какие ссылки обработаны и какие не обработаны.
12. Записывает durable state по `targetDate` и не дублирует блокнот/MP3 при повторном запуске той же даты.
13. Выполняет preflight runtime-зависимостей Trigger.dev: Python requirements, Playwright browser runtime, `ffmpeg`, NotebookLM auth и `state_store`.
14. При количестве NotebookLM-блокнотов `ciscrypted` от `NOTEBOOKLM_CLEANUP_THRESHOLD` удаляет старые блокноты до `NOTEBOOKLM_CLEANUP_TARGET` или останавливается с понятным уведомлением, если удаление невозможно.

## Ограничения MVP

- Только один Telegram-канал: `ciscrypted`.
- Только одно дайджест-сообщение в день: последнее сообщение за день со ссылками.
- Нет постоянного собственного архива полных текстов и MP3.
- Нет интерактивных команд Telegram-бота.
- Нет внешнего TTS.
- Есть только легковесное постоянное состояние для idempotency/recovery; полные тексты статей и MP3 в нем не хранятся.
- `notebooklm-py` неофициальный и может потребовать обновления при изменениях NotebookLM.
