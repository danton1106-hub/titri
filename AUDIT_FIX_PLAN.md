# P0: стабилизация портала «Титры»

## Статус и границы

- Production до завершения P0: GitHub Pages из `main/docs`.
- Canonical build: `data/` и редакторские JSON -> `scripts/build.py` -> `docs/` -> GitHub Pages.
- `docs/` является generated output. Исходники и шаблоны правятся в `scripts/`, данные — в `data/`.
- Backup production: tag `p0-start-backup` и ветка `backup/pre-p0` на `11e1d3a`.
- Разработка ведётся в `staging`; `main` обновляется только после проверок.
- P0 использует нормализованные JSON. PostgreSQL/Supabase начинается на P1.

## Production-файлы текущего проекта

| Назначение | Текущие файлы | P0-решение |
|---|---|---|
| Импорт данных | `scripts/fetch_home.py`, `scripts/fetch_catalog.py` | Убрать hardcoded дату и credential fallback; нормализовать выходные данные. |
| Редакторские данные | отсутствуют | `data/editorial/*.json`, schema validation, приоритет выше importer. |
| Сборка | `scripts/build_home.py`, `scripts/build_site.py`, `preview/` | Одна команда `scripts/build.py`; output только `docs/`. |
| Публикация | `update.yml` в корне | `.github/workflows/update.yml`, расписание 6 часов + `workflow_dispatch`. |
| Published site | `docs/` | Полностью очищается и генерируется build-командой. |

## Порядок P0

1. Создать `time_service.py`; считать UI-дату и относительные подписи в `Europe/Moscow`.
2. Убрать секреты и дату `2026-09-30` из importers; обязательный `TMDB_API_READ_TOKEN` берётся только из env.
3. Создать P0 JSON-модель: content, seasons, episodes, release_events, editorial overrides, editorial ratings.
4. Сформировать `release_events` из текущих данных и overrides. Календарь читает только `release_events`.
5. Ввести единый build в `docs/`: главная, каталог, детали, `/calendar/YYYY/MM/`, `/my-list/`, Journal.
6. Реализовать единый localStorage contract с namespaced `content_id` и самостоятельной страницей списка.
7. Добавить «После титров»: целые редакторские оценки, комментарий, статус и 10 строк разной длины.
8. Перенести workflow, добавить validation, link checker и smoke checks HTML.
9. Собрать staging, выполнить проверки и подготовить PR/merge staging -> main.

## Окружение и секреты

Единая точка чтения конфигурации — `scripts/env_service.py`. Свой разбор `.env` больше нигде не дублируется.

Порядок приоритета: реальные переменные окружения → `.env` → `.env.local`.

| Переменная | Назначение | Обязательна |
|---|---|---|
| `TMDB_API_READ_TOKEN` | каталог и витрина главной | для обновления данных |
| `OMDB_API_KEY` | IMDb, Rotten Tomatoes, Metacritic | нет |
| `TITRI_ALLOW_CACHED_DATA` | сборка из сохранённых JSON без ключа | нет |
| `TITRI_TIMEZONE` | бизнес-часовой пояс | нет, по умолчанию `Europe/Moscow` |

`.env` и `.env.local` в репозиторий не попадают. GitHub Actions берёт значения из GitHub Secrets с теми же именами. Локально: `cp .env.example .env`.

Validation дополнительно проверяет, что значение ключа не попало в `docs/`. При обнаружении сборка падает с `SECRET LEAK`.

## Команды P0

- Production build: `python3 scripts/build.py`
- Проверка данных: `python3 scripts/validate_data.py`
- Проверка ссылок: `python3 scripts/check_links.py`
- Тесты: `python3 -m unittest discover -s tests -p 'test_*.py'`
- Сборка без ключа: `TITRI_ALLOW_CACHED_DATA=1 python3 scripts/build.py`

`scripts/build_production.py` — тонкая обёртка для совместимости. `build_home.py` и `build_site.py` больше не запускаются как самостоятельные pipelines.

## Ветки

- `main` — production, GitHub Pages публикуется только отсюда.
- `staging` — проверка изменений без публикации.
- `backup/pre-p0` и tag `p0-start-backup` — резервная точка до P0.

## Риски и защита

- API keys: старый TMDB credential должен быть отозван владельцем и заменён GitHub Secret. История Git на P0 не переписывается.
- Даты: release date без времени остаётся календарной датой и не преобразуется в UTC midnight.
- Конфликты источников: override/official > TVMaze > TMDB; низкоприоритетный импорт не перезаписывает override.
- Production: build очищает generated HTML перед записью, поэтому root/preview не могут стать источником Pages.
- Catalog: P0 не ограничивает модель типами `movie`/`tv`, но полный глобальный ingestion остаётся P2.

## Критерии приёмки P0

- Ни один скрипт бизнес-логики не содержит фиксированную дату `2026-09-30`.
- В production есть только generated `docs/`; build не зависит от `preview/`.
- Workflow лежит в `.github/workflows/`, запускается по расписанию каждые 6 часов и вручную.
- Календарь генерируется из `release_events`; есть маршруты месяцев и навигация.
- `aired_count`, `next_episode_number` и `total_episodes` разделены; неизвестный total остаётся `null`.
- Все content types используют централизованные термины «серия»/«выпуск».
- В HTML отсутствуют `$01`, `$03`, `''`, дублированные section headings; одна `h1` на страницу.
- Journal, Calendar и My List существуют; все internal links проходят проверку.
- My List сохраняется после reload, использует namespaced external ID и открывается по `/my-list/`.
- Рейтинг «После титров» хранится в JSON, содержит integer score и комментарий, не смешивается с внешними рейтингами.
- `TMDB_API_READ_TOKEN` не находится в коде и не печатается в логах.
