# Инструкция для деплоя Python/TypeScript-скриптов в Trigger.dev

Эта инструкция нужна Codex для повторяемых задач вида: взять произвольный локальный скрипт на Python или TypeScript, превратить его в Trigger.dev task, проверить сборку и задеплоить в проект Trigger.dev.

## Базовые правила

- Работать от текущего состояния репозитория: сначала прочитать `package.json`, `trigger.config.ts`, `src/trigger/*`, `.env.example` и существующие тесты.
- Использовать текущий стек проекта: Trigger.dev SDK `4.4.x`, CLI `trigger.dev`, `@trigger.dev/python`, TypeScript tasks в `src/trigger`.
- Следовать существующему стилю импортов проекта. В этом репозитории уже используется `@trigger.dev/sdk/v3`.
- Не коммитить и не печатать секреты из `.env`, токены, cookies, credentials и содержимое production env.
- Для live-деплоя всегда сначала выполнить dry-run. `trigger:deploy` запускать только когда код, env-контракт и dry-run проверены.
- Если пользователь просит “просто задеплой скрипт”, по умолчанию делать manual task через `task()`. Расписание через `schedules.task()` добавлять только если пользователь попросил cron/periodic run.

## Быстрый маршрут

1. Определить контракт скрипта:
   - какие входные параметры нужны;
   - какие env vars и файлы-секреты нужны;
   - какие внешние сервисы вызываются;
   - какой результат должен вернуться в Trigger.dev run;
   - какие операции не должны выполняться параллельно.

2. Выбрать тип task:
   - `task()` для ручных запусков, webhook/backend trigger и разовых jobs;
   - `schedules.task()` для cron;
   - orchestrator + processor, если расписание только ищет элементы, а тяжелая обработка должна идти отдельными task с idempotency keys.

3. Положить код в ожидаемые места:
   - TypeScript task: `src/trigger/<task-name>.ts`;
   - Python wrapper/script: `src/trigger/<script-name>.py` или существующий Python-пакет под `src/<package>`;
   - shared TypeScript helpers: рядом в `src/trigger/<name>Runtime.ts`;
   - Python tests: `tests/test_<name>.py`;
   - Trigger/Node tests: `src/trigger/<name>.test.ts`.

4. Обновить `trigger.config.ts`:
   - проверить, что `dirs` включает `./src/trigger`;
   - для Python проверить `pythonExtension({ scripts: ["./src/**/*.py"], requirements: [...] })`;
   - добавить Python-зависимости в массив `pythonRequirements` или в поле `requirements`, если скрипту нужны новые пакеты;
   - держать `maxDuration`, retries и runtime в явном виде.

5. Добавить env-контракт:
   - новые non-secret env vars добавить в `.env.example`;
   - секреты описать в README/плане без реальных значений;
   - file secrets в Trigger.dev лучше передавать как base64 env vars и материализовать во временную директорию во время run.

6. Добавить тесты и локальные проверки:
   - Python: unit test для wrapper/аргументов и smoke `python <script>.py --help`, если применимо;
   - TypeScript: тесты helper-функций, env materialization и payload/date formatting;
   - Trigger build: `npm run trigger:dry-run`.

7. Деплой:
   - проверить production env в Trigger.dev;
   - выполнить `npm run trigger:deploy`;
   - открыть Trigger.dev Dashboard, найти task/run/schedule и проверить, что новая версия видна;
   - для manual task сделать тестовый run с безопасным payload.

## Шаблон TypeScript manual task

```ts
import { logger, task } from "@trigger.dev/sdk/v3";

type Payload = {
  input: string;
};

export const exampleTask = task({
  id: "example-task",
  queue: {
    concurrencyLimit: 1,
  },
  maxDuration: 3600,
  run: async (payload: Payload) => {
    logger.info("Запуск example-task", { input: payload.input });

    return {
      ok: true,
      input: payload.input,
    };
  },
});
```

## Шаблон scheduled task

```ts
import { logger, schedules } from "@trigger.dev/sdk/v3";

export const exampleScheduledTask = schedules.task({
  id: "example-scheduled-task",
  cron: {
    pattern: "0 * * * *",
    timezone: "Europe/Moscow",
    environments: ["PRODUCTION"],
  },
  queue: {
    concurrencyLimit: 1,
  },
  ttl: "10m",
  maxDuration: 3600,
  run: async (payload) => {
    logger.info("Запуск scheduled task", {
      scheduledAt: payload.timestamp,
      lastScheduledAt: payload.lastTimestamp,
    });

    return {
      scheduledAt: payload.timestamp,
    };
  },
});
```

## Шаблон запуска Python из Trigger task

```ts
import { logger, task } from "@trigger.dev/sdk/v3";
import { python } from "@trigger.dev/python";

export const pythonScriptTask = task({
  id: "python-script-task",
  queue: {
    concurrencyLimit: 1,
  },
  maxDuration: 3600,
  run: async (payload: { input: string }) => {
    const result = await python.runScript(
      "./src/trigger/run_python_script.py",
      ["--input", payload.input],
      {
        env: {
          ...process.env,
        },
      },
    );

    if (result.stdout) {
      logger.info("python stdout", { stdout: result.stdout });
    }

    if (result.stderr) {
      logger.warn("python stderr", { stderr: result.stderr });
    }

    return {
      stdout: result.stdout,
      stderr: result.stderr,
    };
  },
});
```

```py
from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(args.input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Материализация file secrets

Если скрипту нужен JSON/cookie/token-файл, не хранить его в репозитории и не ожидать абсолютный локальный путь в Trigger.dev. Использовать схему:

- локально файл лежит в `credentials/` или `data/`, но игнорируется git;
- для Trigger.dev Production значение хранится как env var с base64, например `SERVICE_ACCOUNT_JSON_BASE64`;
- task создает временную директорию, декодирует файл туда и передает путь скрипту через env var или CLI-аргумент;
- в результате run можно вернуть только путь временной директории или технический статус, но не содержимое секрета.

Мини-шаблон для TypeScript helper:

```ts
import { mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

export async function materializeBase64File(
  envName: string,
  fileName: string,
): Promise<string | undefined> {
  const value = process.env[envName];
  if (!value) {
    return undefined;
  }

  const runtimeDir = await mkdtemp(join(tmpdir(), "trigger-runtime-"));
  const filePath = join(runtimeDir, fileName);
  await writeFile(filePath, Buffer.from(value, "base64"));
  return filePath;
}
```

## Команды проверки

```powershell
npm run test:trigger
python -m pytest
npm run trigger:dry-run
```

Если есть отдельный Python wrapper:

```powershell
python src/trigger/<script-name>.py --help
python -m pytest tests/test_<script-name>.py -v
```

Деплой:

```powershell
npm run trigger:deploy
```

## Production env checklist

Перед deploy проверить, что в Trigger.dev Production есть все переменные, которые task реально читает:

```powershell
npx trigger.dev env list --env prod
```

Если нужно добавить/обновить секреты, использовать Trigger.dev Dashboard или CLI, но не записывать значения в git. После изменения declarative schedules или env-контракта выполнить новый deploy.

## Типовые ошибки

- Python script импортирует локальный пакет, но `sys.path` не включает `src`. Добавить wrapper, который кладет `src` в `sys.path`, или запускать установленный package entrypoint.
- Новая Python-зависимость добавлена в `requirements.txt`, но не добавлена в `pythonExtension({ requirements })`.
- Task лежит вне `dirs`, поэтому Trigger.dev не видит экспорт.
- Cron task создан без `environments: ["PRODUCTION"]`, и расписание появляется не там, где ожидалось.
- Секретный файл передан абсолютным Windows-путем, который не существует в Trigger.dev runtime.
- Несколько scheduled runs обрабатывают один и тот же ресурс. Добавить `queue.concurrencyLimit`, `ttl` и idempotency key на уровне processor task.

## Критерий готовности

Задача считается законченной, когда:

- task экспортируется из файла в `src/trigger` и попадает в Trigger.dev dry-run;
- все новые env vars документированы без секретных значений;
- локальные тесты и `npm run trigger:dry-run` проходят;
- `npm run trigger:deploy` завершился успешно;
- в Dashboard виден task/schedule, а тестовый run возвращает ожидаемый результат или понятную ошибку внешнего сервиса.
