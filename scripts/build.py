#!/usr/bin/env python3
"""Canonical P0 production build: normalized JSON -> docs/ -> GitHub Pages.

Run this file directly. It is the only production build entry point.
"""
from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import env_service
from time_service import parse_local_date, relative_day, today_moscow

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
MONTHS_GEN = ("январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
CONTENT_TYPES = {
    "movie": "фильм", "series": "сериал", "reality": "реалити", "competition": "соревнование",
    "game_show": "игровое шоу", "talk_show": "ток-шоу", "comedy_show": "юмористическое шоу",
    "web_show": "web-проект", "anime": "аниме", "special": "спецвыпуск",
}
EPISODE_WORD = {
    "series": "серия", "anime": "серия", "movie": "релиз", "reality": "выпуск",
    "competition": "выпуск", "game_show": "выпуск", "talk_show": "выпуск",
    "comedy_show": "выпуск", "web_show": "выпуск", "special": "спецвыпуск",
}


def load(path: Path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def esc(value):
    return html.escape(str(value or ""))


def content_id(item):
    external = item.get("external_ids") or {}
    if external.get("tmdb"):
        return f'tmdb:{external["tmdb"]}'
    if item.get("id") is not None:
        return f'tmdb:{item["id"]}'
    return item["content_id"]


def has_letters(text):
    """Есть ли в строке хотя бы одна буква — в любой письменности.

    Иероглифы, хангыль, арабица и деванагари относятся к категории Lo,
    латиница и кириллица — к Lu и Ll. Проверяем категорию символа, а не
    диапазон конкретного алфавита: список алфавитов всегда окажется неполным.
    """
    return any(unicodedata.category(ch).startswith("L") for ch in (text or ""))


def readable_title(title, fallback=""):
    """Название для карточки. Проект не выбрасываем — это была реальная потеря контента.

    Раньше: если в названии нет кириллицы или латиницы, проект молча исчезал
    из базы. Так пропадали 17 позиций: японское аниме, корейские сериалы,
    индийские фильмы. Теперь приоритет такой:

    1. название на кириллице или латинице;
    2. оригинальное название, если оно читаемо;
    3. исходное название как есть — иероглифы лучше пустой карточки.

    Иероглифы из названия больше не вырезаются: это часть имени проекта.
    """
    text = (title or "").strip()
    if text and has_letters(text):
        return text
    alternative = (fallback or "").strip()
    if alternative and has_letters(alternative):
        return alternative
    return text or alternative


def path_slug(item):
    """Адрес проекта: транслит названия, а не числовой ID.

    Так адреса читаемые и совпадают с прежними ссылками вида /tv/akademiya-vedm/.
    """
    slug = (item.get("slug") or "").strip()
    if slug:
        return slug
    return str(item["id"]).replace("tmdb:", "tmdb-")


def to_normalized():
    """Каталог -> нормализованный content.

    Ничего не выбрасываем молча: если проект всё же не попадает,
    он записывается в data/rejected.json, а сборка сообщает об этом.
    """
    catalog = load(DATA / "catalog.json", {"catalog": [], "upcoming": []})
    rows = catalog.get("catalog", []) + catalog.get("upcoming", [])
    result, seen, rejected = [], set(), []
    for row in rows:
        cid = content_id(row)
        if cid in seen:
            continue
        seen.add(cid)
        kind = row.get("kind", "tv")
        is_anime = bool(row.get("is_anime"))
        content_type = "anime" if is_anime else ("movie" if kind == "movie" else "series")
        title = readable_title(row.get("title"), row.get("original_title"))
        if not title:
            rejected.append({
                "content_id": cid, "tmdb_id": row.get("id"), "kind": kind,
                "title": row.get("title"), "original_title": row.get("original_title"),
                "reason": "нет ни одного названия с буквами",
            })
            continue
        result.append({
            "id": cid, "slug": row.get("slug") or slug(cid), "content_type": content_type,
            "title": readable_title(row.get("title"), row.get("original_title")),
            "original_title": row.get("original_title"),
            "overview": row.get("overview") or "", "country": row.get("country"),
            "original_language": row.get("language"), "year_start": row.get("year"),
            "status": row.get("status"), "poster": row.get("poster"), "backdrop": row.get("backdrop"),
            "genres": row.get("genres") or [], "genre_ids": row.get("genre_ids") or [],
            "vote": row.get("vote"), "vote_count": row.get("vote_count"),
            "popularity": row.get("popularity") or 0,
            "release_date": row.get("release_date") or row.get("first_date"),
            "total_episodes": row.get("n_episodes") or row.get("total") or None,
            "aired_count": row.get("aired") or None,
            "aired_season": None, "next_episode": row.get("next_ep"),
            "last_episode": row.get("last_ep"), "network": row.get("network"),
            "n_seasons": row.get("n_seasons"), "seasons_total": row.get("n_seasons"),
            "homepage": row.get("homepage"), "external_ids": {"tmdb": row.get("id")},
        })
    return result, rejected


def build_events(contents):
    events = []
    for item in contents:
        cid = item["id"]
        if item["content_type"] == "movie" and item.get("release_date"):
            events.append(event(cid, "movie_digital", item["release_date"], item["title"]))
        elif item.get("release_date"):
            events.append(event(cid, "series_premiere", item["release_date"], item["title"]))
        for key, event_type in (("last_episode", "episode"), ("next_episode", "episode")):
            ep = item.get(key) or {}
            if ep.get("date"):
                events.append(event(cid, event_type, ep["date"], item["title"], ep))
    unique = {}
    for item in events:
        unique[(item["content_id"], item["event_type"], item["release_date"], item.get("episode_number"))] = item
    return sorted(unique.values(), key=lambda x: (x["release_date"], x["title"]))


def event(cid, event_type, release_date, title, episode=None, region="GLOBAL", country=None):
    episode = episode or {}
    source_number = episode.get("ep")
    # Некоторые долгие передачи получают у агрегатора глобальный номер 821
    # вместо номера внутри сезона. Такой номер сохраняем для аудита, но не
    # выводим как номер серии и не используем в сезонном progress.
    season_number = episode.get("season")
    episode_number = source_number if isinstance(source_number, int) and source_number <= 100 else None
    return {
        "id": f'{cid}:{event_type}:{release_date}:{season_number or ""}:{source_number or ""}:{region.lower()}',
        "content_id": cid, "season_id": None, "episode_id": None, "event_type": event_type,
        "release_date": release_date, "release_at": None, "release_timezone": None,
        "region": region, "country": country, "platform_id": None, "source_id": "tmdb", "source_url": None,
        "verification_status": "aggregator_confirmed", "title": title, "season_number": season_number,
        "episode_number": episode_number, "source_episode_number": source_number,
        "episode_name": episode.get("name"),
    }


def apply_overrides(contents, events):
    overrides = load(DATA / "editorial" / "content_overrides.json", {"items": []}).get("items", [])
    by_id = {item["id"]: item for item in contents}
    for override in overrides:
        item = by_id.get(override.get("content_id"))
        if item and override.get("field") in {"total_episodes", "status", "content_type"}:
            item[override["field"]] = override.get("value")
    releases = load(DATA / "editorial" / "release_overrides.json", {"items": []}).get("items", [])
    by_event = {(item["content_id"], item["event_type"], item["release_date"]): item for item in events}
    for override in releases:
        key = (override.get("content_id"), override.get("event_type"), override.get("release_date"))
        item = by_event.get(key)
        if item:
            item.update({k: v for k, v in override.items() if k in item and v is not None})
            item["verification_status"] = "editorial_verified"
        elif override.get("content_id") and override.get("release_date"):
            events.append({
                "id": override.get("id") or f'{override["content_id"]}:editorial:{override["release_date"]}',
                "content_id": override["content_id"], "season_id": override.get("season_id"),
                "episode_id": override.get("episode_id"), "event_type": override.get("event_type", "special"),
                "release_date": override["release_date"], "release_at": override.get("release_at"),
                "release_timezone": override.get("release_timezone"),
                "region": override.get("region") or "GLOBAL", "country": override.get("country"),
                "platform_id": override.get("platform_id"), "source_id": "editorial",
                "source_url": override.get("source_url"), "verification_status": "editorial_verified",
                "title": override.get("title", ""), "season_number": override.get("season_number"),
                "episode_number": override.get("episode_number"), "episode_name": override.get("episode_name"),
            })


def save_rejected(rejected):
    """Отчёт о выпавших проектах. Пустой список тоже пишем: это доказательство, а не тишина."""
    (DATA / "rejected.json").write_text(
        json.dumps({"schema_version": 1, "items": rejected}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(rejected)


def save_normalized(contents, events, seasons=None):
    """Сохранить нормализованные сущности P0 без потери состава каталога."""
    DATA.mkdir(exist_ok=True)
    (DATA / "content.json").write_text(json.dumps({"schema_version": 1, "items": contents}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "release_events.json").write_text(json.dumps({"schema_version": 1, "items": events}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    external_ids = []
    for item in contents:
        external = item.get("external_ids") or {}
        external_ids.append({
            "content_id": item["id"], "tmdb_id": external.get("tmdb"),
            "tvmaze_id": external.get("tvmaze"), "imdb_id": external.get("imdb"),
            "tvdb_id": external.get("tvdb"),
        })
    (DATA / "external_ids.json").write_text(json.dumps({"schema_version": 1, "items": external_ids}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # P0 уже хранит сезон как отдельную сущность. Unknown total остаётся null:
    # нельзя подставлять общее число эпизодов сериала вместо числа серий сезона.
    season_rows = []
    for content_key, data in (seasons or {}).items():
        if not data or not data.get("season"):
            continue
        next_event = data.get("next_event") or {}
        season_rows.append({
            "id": f"{content_key}:season:{data['season']}",
            "content_id": content_key,
            "season_number": data["season"],
            "aired_count": data.get("season_aired"),
            "total_episodes": data.get("season_total"),
            "next_episode_number": next_event.get("episode_number"),
            "next_release_date": data["next_date"].isoformat() if data.get("next_date") else None,
        })
    (DATA / "seasons.json").write_text(json.dumps({"schema_version": 1, "items": season_rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Сохраняем только известные записи событий. Полный импорт всех серий — отдельная
    # ingestion-задача, но эти records уже пригодны для будущего user_episode_state.
    episode_rows = []
    seen = set()
    for event in events:
        number = event.get("episode_number")
        season_number = event.get("season_number")
        if not number or not season_number:
            continue
        key = (event["content_id"], season_number, number, event.get("release_date"))
        if key in seen:
            continue
        seen.add(key)
        episode_rows.append({
            "id": event.get("episode_id") or f"{event['content_id']}:season:{season_number}:episode:{number}",
            "content_id": event["content_id"],
            "season_number": season_number,
            "episode_number": number,
            "title": event.get("episode_name"),
            "release_date": event.get("release_date"),
            "source_id": event.get("source_id"),
            "verification_status": event.get("verification_status"),
        })
    (DATA / "episodes.json").write_text(json.dumps({"schema_version": 1, "items": episode_rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compute_aired(contents, events, today):
    """Сколько выпусков уже вышло на сегодня.

    Считаем по событиям-эпизодам, а не по количеству записей в API:
    будущая серия может существовать, но ещё не иметь даты, и тогда
    «0 из 20» вместо реальной картины. Номер последнего вышедшего
    выпуска и есть число вышедших.
    """
    counters = {}
    for event in events:
        released = parse_local_date(event.get("release_date"))
        if released is None or released > today:
            continue
        if event.get("event_type") not in {"episode", "show_episode", "reality_episode", "finale"}:
            continue
        number = event.get("episode_number")
        if not number:
            continue
        season = event.get("season_number")
        key = event["content_id"]
        best = counters.get(key)
        # Берём последнюю вышедшую серию: по номеру внутри сезона и по сезону.
        if best is None or (season or 0, int(number)) > (best[0] or 0, best[1]):
            counters[key] = (season, int(number))
    for item in contents:
        measured = counters.get(item["id"])
        if measured:
            season, number = measured
            item["aired_count"] = number
            item["aired_season"] = season
        elif item.get("last_episode") and item["last_episode"].get("ep"):
            item["aired_count"] = int(item["last_episode"]["ep"])
            item["aired_season"] = item["last_episode"].get("season")


def refresh_next_episode(contents, events, today):
    """Ближайший релиз берём из событий, а не из поля API.

    TMDB часто держит уже вышедшую серию в next_episode, пока не обновит
    данные сезона. Тогда на странице появляется «Следующий релиз: серия 1»
    у проекта, который уже стартовал. Источник истины для расписания —
    release_events, поэтому поле пересчитываем здесь.
    """
    upcoming = defaultdict(list)
    for event in events:
        released = parse_local_date(event.get("release_date"))
        if released is None or released <= today:
            continue
        if event.get("event_type") not in {"episode", "show_episode", "reality_episode", "finale", "movie_digital", "movie_streaming", "movie_theatrical"}:
            continue
        upcoming[event["content_id"]].append((released, event))
    for item in contents:
        rows = sorted(upcoming.get(item["id"], []), key=lambda pair: pair[0])
        if not rows:
            item["next_episode"] = None
            continue
        released, event = rows[0]
        item["next_episode"] = {
            "ep": event.get("episode_number"),
            "season": event.get("season_number"),
            "date": released.isoformat(),
            "name": event.get("episode_name"),
        }


def rating_map():
    """Оценки «После титров» по проектам: список голосов, а не одно значение.

    Редакторов может быть несколько. Каждый голосует целым числом 1-10,
    а итог считается средним и может быть дробным.
    """
    result = {}
    for item in load(DATA / "editorial" / "ratings.json", {"items": []}).get("items", []):
        if item.get("status") != "published":
            continue
        if not isinstance(item.get("rating"), int):
            continue
        result.setdefault(item.get("content_id"), []).append(item)
    return result


def aggregate_rating(entries):
    """Среднее по голосам. Целые на входе, дробное на выходе: 8, 9, 9 -> 8,7."""
    values = [entry["rating"] for entry in entries or [] if isinstance(entry.get("rating"), int)]
    if not values:
        return None
    return sum(values) / len(values)


def rating_status(value):
    """Эмоциональный статус оценки. Число остаётся главным."""
    if value >= 9:
        return "Остаёмся после титров"
    if value >= 7:
        return "Стоит досмотреть"
    if value >= 5:
        return "На один просмотр"
    if value >= 3:
        return "На перемотке"
    return "Не доживает до титров"


def rating_text(value):
    """8 -> «8», 8.666 -> «8,7». Одна цифра после запятой."""
    rounded = round(value, 1)
    if abs(rounded - round(rounded)) < 0.05:
        return str(int(round(rounded)))
    return f"{rounded:.1f}".replace(".", ",")


def rel(current, target):
    current_dir = "/".join(current.parts)
    start = current_dir or "."
    result = posixpath.relpath(target or ".", start=start)
    if not result.endswith("/") and (not target or target.endswith("/")):
        result += "/"
    return result


def watch_panel(current):
    """Раскрывающаяся панель «Мой список» в шапке.

    Содержимое рисует site.js из localStorage: сервер не знает списка
    до появления личного кабинета. Разметка общая для всех страниц.
    """
    return f'''<div class="watch" data-watch-root>
<button class="bookmark-btn" type="button" aria-expanded="false" aria-controls="watch-panel" aria-haspopup="true">Мой список <span class="count" data-watch-count>0</span></button>
<div class="watch-panel" id="watch-panel" hidden>
<div class="watch-head"><span class="label dim">Мой список</span><a class="watch-all" href="{rel(current, 'my-list/')}">Открыть страницу</a></div>
<ul class="watch-list" data-watch-list></ul>
<p class="watch-empty" data-watch-empty>Пока пусто. Нажмите <b>+</b> на карточке, чтобы добавить проект.</p>
</div>
</div>'''


def nav(current=Path("")):
    """Шапка: навигация, дата по Москве, мой список, мобильное меню."""
    links = [("", "Главная"), ("calendar/", "Календарь"), ("movies/", "Фильмы"), ("series/", "Сериалы"),
             ("shows/", "Шоу"), ("catalog/", "Каталог"), ("journal/", "Журнал")]
    parts = [f'<a href="{rel(current, href)}">{name}</a>' for href, name in links]
    today = today_moscow()
    today_text = f"{today.day:02d} / {today.month:02d} / {today.year}"
    return f'''<header class="header"><a class="brand" href="{rel(current, '')}">[титры]</a>
<nav class="nav" aria-label="Основная навигация">{''.join(parts)}</nav>
<time class="today" data-current-date datetime="{today.isoformat()}">{today_text}</time>
{watch_panel(current)}
<button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-nav">Меню</button>
<nav id="mobile-nav" class="mobile-nav" aria-label="Мобильная навигация" hidden>{''.join(parts)}<a href="{rel(current, 'my-list/')}">Мой список</a></nav></header>'''


def footer(current=Path("")):
    """Подвал: пользовательский текст по-русски, обязательная атрибуция — на отдельной странице."""
    return (
        '<footer class="footer"><div class="wrap">'
        '<div class="footer-top"><span class="footer-brand">[титры]</span>'
        '<span class="footer-tagline">Кино заканчивается.<br>Интерес остаётся.</span></div>'
        '<div class="footer-legal">'
        '<span>Данные о фильмах и сериалах — TMDB (The Movie Database).</span>'
        '<span>Каталог использует открытые данные TMDB с обязательной атрибуцией источника. '
        f'<a href="{rel(current, "credits/")}">Источники и атрибуция</a></span>'
        '<span>Портал «Титры» — бесплатный навигатор по фильмам, сериалам и шоу.</span>'
        '<span>Все названия, постеры и описания принадлежат их правообладателям '
        'и показаны исключительно в информационных целях.</span>'
        '</div></div></footer>'
    )


def credits_page(current=Path("credits")):
    """Источники и атрибуция. Обязательный notice TMDB живёт здесь, а не в подвале."""
    body = (
        '<section class="band wrap">'
        '<div class="label dim">Источники и атрибуция</div>'
        '<h1 class="h2">Откуда берутся данные</h1>'
        '<p class="lead muted">Портал «Титры» использует открытые данные источников, '
        'подключённых к текущей версии сборки. Обязательные упоминания собраны на этой странице.</p>'
        '<div class="credits-block">'
        '<article class="credit-source">'
        '<h2 class="h3">TMDB (The Movie Database)</h2>'
        '<p class="lead muted">Метаданные фильмов и сериалов: названия, описания, постеры, кадры, '
        'жанры, сезоны, а также идентификаторы проектов.</p>'
        '<p class="credit-notice">This product uses the TMDB API but is not endorsed or certified by TMDB.</p>'
        '</article>'
        '</div>'
        '<p class="cal-note">TVMaze и JustWatch будут добавлены в этот список после включения '
        'соответствующих источников в production pipeline.</p>'
        '</section>'
    )
    return page("Источники и атрибуция", body, current, "Источники данных и атрибуция портала «Титры»")


SITE_URL = "https://danton1106-hub.github.io/titri"


def page(title, body, current=Path(""), description="", extra_script="", canonical=None):
    """SITE_URL нужен для canonical: поддомен GitHub Pages фиксирован."""
    prefix = rel(current, "")
    script = f"<script defer>{extra_script}</script>" if extra_script else ""
    canonical_url = canonical if canonical is not None else f"{SITE_URL}/{('/'.join(current.parts) + '/') if current.parts else ''}"
    canonical_tag = f'<link rel="canonical" href="{esc(canonical_url)}">' if canonical_url else ""
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} - титры</title>{canonical_tag}<meta name="description" content="{esc(description)}"><link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="{prefix}titry.css"><script defer src="{prefix}site.js"></script>{script}</head><body>{nav(current)}<main>{body}</main>{footer(current)}</body></html>'''


def section_of(item):
    """Раздел проекта: фильмы отдельно, весь сериальный контент — в /tv/.

    Так адрес остаётся читаемым и совпадает с прежними ссылками сайта:
    /movie/maykl/ и /tv/akademiya-vedm/.
    """
    return "movie" if item["content_type"] == "movie" else "tv"


def detail_path(item):
    return Path(section_of(item)) / path_slug(item)


def content_href(item, current):
    return rel(current, f'{section_of(item)}/{path_slug(item)}/')


def status_label(status):
    return {"Returning Series": "Продолжается", "Ended": "Завершён", "Canceled": "Закрыт", "In Production": "В производстве", "Planned": "Анонсирован", "Released": "Вышел"}.get(status, status or "Статус не объявлен")


def plural(number, forms):
    """Русская форма слова по числу: 1 серия, 2 серии, 5 серий."""
    one, few, many = forms
    n = abs(int(number))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


EPISODE_FORMS = {
    "серия": ("серия", "серии", "серий"),
    "выпуск": ("выпуск", "выпуска", "выпусков"),
    "релиз": ("релиз", "релиза", "релизов"),
    "спецвыпуск": ("спецвыпуск", "спецвыпуска", "спецвыпусков"),
}


def episode_word(number, content_type):
    """Слово для одного числа: 1 серия, 3 серии, 145 серий."""
    base = EPISODE_WORD.get(content_type, "выпуск")
    return plural(number, EPISODE_FORMS.get(base, ("выпуск", "выпуска", "выпусков")))


def section_head(number, kicker, title, note=""):
    """Один заголовок раздела: номер, рубрика, H2 и необязательная строка справа."""
    note_html = f'<span class="section-note">{esc(note)}</span>' if note else ""
    return (
        f'<div class="section-head">'
        f'<div class="section-head-text">'
        f'<span class="label dim">{esc(number)} / {esc(kicker)}</span>'
        f'<h2 class="h2">{esc(title)}</h2>'
        f'</div>{note_html}</div>'
    )


def progress_visual(item, season=None):
    """Живая линейка текущего сезона, а не всего сериала.

    Номер следующего эпизода никогда не подставляется вместо числа вышедших,
    а неизвестное общее количество показывается словами, не нулём.
    """
    data = season or {}
    aired = data.get("season_aired")
    total = data.get("season_total")
    season_no = data.get("season")
    word = item["content_type"]
    prefix = f"Сезон {season_no} · " if season_no and (item.get("n_seasons") or 1) > 1 else ""

    if aired is None:
        return f'<p class="prog-note">{prefix}серии объявлены не полностью</p>'

    next_event = data.get("next_event") or {}
    next_ep = next_event.get("episode_number")

    if not total:
        note = (f'<p class="prog-note">{prefix}вышло {aired} {episode_word(aired, word)}'
                f' · количество пока не объявлено</p>')
        if next_ep:
            released = data.get("next_date")
            when = f"{released.day} {month_name(released.month)}" if released else "дата не объявлена"
            note += f'<span class="prog-next">{next_label(next_ep, word)} · {when}</span>'
        return note

    if total <= 16:
        dots = []
        for index in range(1, total + 1):
            cls = "prog-dot"
            if index <= aired:
                cls += " is-aired"
            elif next_ep and index == next_ep:
                cls += " is-next"
            dots.append(f'<span class="{cls}"></span>')
        visual = f'<div class="prog-dots" role="img" aria-label="Вышло {aired} из {total}">{"" .join(dots)}</div>'
    else:
        percent = int(round(aired / total * 100))
        visual = (f'<div class="prog-bar" role="img" aria-label="Вышло {aired} из {total}">'
                  f'<span style="--fill:{percent}%"></span></div>')

    lines = [visual, f'<span class="prog-count">{prefix}вышло {aired} из {total} {episode_word(total, word)}</span>']
    if next_ep:
        released = data.get("next_date")
        when = f"{released.day} {month_name(released.month)}" if released else "дата не объявлена"
        lines.append(f'<span class="prog-next">{next_label(next_ep, word)} · {when}</span>')
    return "".join(lines)


def next_label(number, content_type):
    """«Следующая серия 4» и «Следующий выпуск 3» — род и число согласованы."""
    base = EPISODE_WORD.get(content_type, "выпуск")
    if base in {"серия"}:
        return f"Следующая {base} {number}"
    return f"Следующий {base} {number}"





def is_season_relative_episode(event):
    """Отличить номер серии в сезоне от глобального счётчика ежедневного шоу.

    TMDB у части длинных передач кладёт в episode_number 821 или 1215 при
    season_number=1. Это полезно как внешний идентификатор, но его нельзя
    показывать пользователю как «серия 821 сезона 1» и нельзя включать в
    сезонный progress. До появления полного episode ingestion такие значения
    остаются в release_events, но не участвуют в сезонной арифметике.
    """
    number = event.get("episode_number")
    return isinstance(number, int) and 1 <= number <= 100


def season_index(contents, events, today):
    """Сезонная модель: прогресс всегда относится к текущему сезону, а не ко всему сериалу.

    Раньше карточка AHS показывала «Вышло 4 из 145»: 4 серии текущего сезона
    сравнивались с 145 сериями за все сезоны. Это неверно и вводит в заблуждение.

    Теперь для каждого проекта считаем:
      season          — текущий сезон (последний, у которого есть события);
      season_aired    — сколько серий этого сезона уже вышло;
      season_total    — сколько серий объявлено в этом сезоне (или None);
      next_event      — ближайшее событие строго после сегодняшней даты.
    """
    by_content = defaultdict(list)
    for event in events:
        released = parse_local_date(event.get("release_date"))
        if released is None:
            continue
        by_content[event["content_id"]].append((released, event))

    index = {}
    for item in contents:
        # У фильма нет сезона. Для них остаются premiere events, но в Data Core
        # не создаётся фиктивная сущность season:1.
        if item.get("content_type") == "movie":
            index[item["id"]] = None
            continue
        rows = sorted(by_content.get(item["id"], []), key=lambda pair: pair[0])
        if not rows:
            index[item["id"]] = None
            continue

        # Текущий сезон — тот, у которого есть сезонные эпизодные события.
        # Глобальные номера ежедневных шоу остаются в release_events, но не
        # искажают сезонный прогресс и пользовательские подписи.
        episode_rows = [(d, e) for d, e in rows if is_season_relative_episode(e)]
        season = None
        if episode_rows:
            season = max((e.get("season_number") or 1) for _, e in episode_rows)
        elif rows:
            season = rows[-1][1].get("season_number") or 1

        season_rows = [(d, e) for d, e in rows if (e.get("season_number") or season) == season]
        ep_rows = [(d, e) for d, e in season_rows if is_season_relative_episode(e)]
        aired = len({e["episode_number"] for d, e in ep_rows if d <= today})

        # Объявленное количество: только если сериал односезонный, иначе честно None.
        total = None
        if item.get("seasons_total") == 1 or item.get("n_seasons") == 1:
            declared = item.get("total_episodes")
            if declared and declared <= 60:
                total = declared
        if total is None and ep_rows:
            known = max(e["episode_number"] for _, e in ep_rows)
            # Если все объявленные серии уже вышли и сериал завершён — знаем итог.
            if item.get("status") in {"Ended", "Released"} and aired == known:
                total = known

        future = [(d, e) for d, e in season_rows if d > today] or [(d, e) for d, e in rows if d > today]
        next_event = min(future, key=lambda pair: pair[0]) if future else None
        public_next_event = None
        if next_event:
            public_next_event = dict(next_event[1])
            if not is_season_relative_episode(public_next_event):
                public_next_event["episode_number"] = None

        index[item["id"]] = {
            "season": season,
            "season_aired": aired,
            "season_total": total,
            "next_date": next_event[0] if next_event else None,
            "next_event": public_next_event,
        }
    return index


def progress(item):
    """Сколько вышло. Неизвестное количество показываем честно, а не нулём."""
    total, aired = item.get("total_episodes"), item.get("aired_count")
    aired = aired or 0
    if not total:
        return (f'Вышло {aired} {episode_word(aired, item["content_type"])}'
                f' · количество пока не объявлено')
    return (f'Вышло {aired} из {total} {episode_word(total, item["content_type"])}')


def after_credits(item, ratings, variant="normal"):
    """Единый компонент рейтинга «После титров».

    Голоса целые, агрегат дробный. Дробная часть показывается частичной
    заливкой следующей строки, но точное число всегда написано текстом.
    """
    entries = ratings.get(item["id"]) or []
    value = aggregate_rating(entries)
    if value is None:
        return ""
    shown = rating_text(value)
    lines = []
    for index in range(1, 11):
        whole = int(value)
        if index <= whole:
            fill = 100
        elif index == whole + 1:
            fill = int(round((value - whole) * 100))
        else:
            fill = 0
        lines.append(f'<span class="credit-line" style="--fill:{fill}%;--len:{58 + (index * 17) % 38}%"></span>')
    if abs(value - round(value)) < 0.05:
        label = f"Рейтинг После титров: {int(round(value))} из 10 строк"
    else:
        label = f"Рейтинг После титров: {shown} из 10"
    comment = next((entry.get("comment") for entry in entries if entry.get("comment")), "")
    return (
        f'<section class="after-credits after-credits--{variant}" aria-label="{esc(label)}">'
        f'<div class="label dim">После титров</div>'
        f'<strong>{esc(shown)}/10 строк</strong>'
        f'<span class="after-status">{esc(rating_status(value))}</span>'
        f'<div class="credit-lines" role="img" aria-label="{esc(label)}">{"".join(lines)}</div>'
        + (f'<p class="after-comment">{esc(comment)}</p>' if comment else "")
        + '</section>'
    )


def count_label(number, forms):
    """«1 проект», «2 проекта», «5 проектов» — для счётчика найденного."""
    return f"{number} {plural(number, forms)}"


def card(item, current, ratings, with_data=False):
    """Карточка проекта. С with_data добавляет признаки для фильтров каталога.

    Признаки берутся из нормализованной модели, поэтому фильтр работает
    одинаково для любого проекта, а не по списку конкретных названий.
    """
    image = f'<img src="{esc(item.get("poster"))}" alt="{esc(item["title"])}" loading="lazy">' if item.get("poster") else ""
    value = aggregate_rating(ratings.get(item["id"]))
    badge = f'<span class="after-badge">После титров {rating_text(value)}</span>' if value is not None else ""
    data = ""
    if with_data:
        genres = ",".join(str(g) for g in (item.get("genre_ids") or []))
        data = (
            f' data-kind="{esc("movie" if item["content_type"] == "movie" else "tv")}"'
            f' data-anime="{1 if item["content_type"] == "anime" else 0}"'
            f' data-animation="{1 if 16 in (item.get("genre_ids") or []) else 0}"'
            f' data-genres="{esc(genres)}"'
            f' data-country="{esc(item.get("country"))}"'
            f' data-vote="{esc(item.get("vote") or 0)}"'
            f' data-votes="{esc(item.get("vote_count") or 0)}"'
            f' data-date="{esc(item.get("release_date"))}"'
            f' data-newep="{1 if item.get("next_episode") else 0}"'
            f' data-title="{esc(str(item.get("title") or "").lower())}"'
            f' data-original="{esc(str(item.get("original_title") or "").lower())}"'
        )
    return f'''<article class="card"{data}><a href="{content_href(item, current)}"><div class="card-media">{image}{badge}</div><h3 class="card-title">{esc(item["title"])}</h3></a><div class="card-meta">{esc(CONTENT_TYPES.get(item["content_type"], item["content_type"]))} · {esc(item.get("year_start"))}</div><button class="card-mark" type="button" data-watch-id="{esc(item["id"])}" data-watch-type="{esc(item["content_type"])}" data-watch-title="{esc(item["title"])}" data-watch-url="{content_href(item, current)}" data-watch-poster="{esc(item.get("poster"))}" aria-label="Добавить в мой список">+</button></article>'''


GENRE_LABELS = {
    35: "комедия", 18: "драма", 16: "мультфильм", 28: "боевик", 10759: "боевик и приключения",
    10765: "фантастика и фэнтези", 12: "приключения", 80: "криминал", 53: "триллер",
    9648: "детектив", 10751: "семейный", 878: "фантастика", 14: "фэнтези", 10749: "мелодрама",
    27: "ужасы", 99: "документальный", 10752: "военный", 36: "история", 10770: "телефильм",
    37: "вестерн", 10402: "музыка", 10764: "реалити", 10767: "ток-шоу", 10763: "новости",
}
COUNTRY_LABELS = {
    "US": "США", "GB": "Великобритания", "RU": "Россия", "JP": "Япония", "KR": "Корея",
    "FR": "Франция", "DE": "Германия", "IT": "Италия", "ES": "Испания", "CA": "Канада",
    "CN": "Китай", "IN": "Индия", "MX": "Мексика", "TH": "Таиланд", "AU": "Австралия",
    "BR": "Бразилия", "TR": "Турция", "SE": "Швеция", "DK": "Дания", "NL": "Нидерланды",
    "PL": "Польша", "UA": "Украина", "AR": "Аргентина", "BE": "Бельгия", "NO": "Норвегия",
}


def catalog_filters(items):
    """Панель фильтров каталога. Список жанров и стран строится из самих данных,
    поэтому в панели нет пустых категорий, которых нет в базе."""
    genre_counts = defaultdict(int)
    country_counts = defaultdict(int)
    for item in items:
        for genre in item.get("genre_ids") or []:
            genre_counts[genre] += 1
        if item.get("country"):
            country_counts[item["country"]] += 1

    types = [
        ("all", "Всё"), ("tv", "Сериалы"), ("movie", "Фильмы"),
        ("anime", "Аниме"), ("animation", "Мультфильмы"),
    ]
    type_chips = "".join(
        f'<button class="chip" type="button" data-type="{value}" aria-pressed="{"true" if value == "all" else "false"}">{esc(label)}</button>'
        for value, label in types
    )
    genre_chips = '<button class="chip" type="button" data-genre="" aria-pressed="true">Все жанры</button>' + "".join(
        f'<button class="chip" type="button" data-genre="{genre}" aria-pressed="false">{esc(GENRE_LABELS.get(genre, str(genre)))}</button>'
        for genre, _ in sorted(genre_counts.items(), key=lambda pair: -pair[1])[:14]
    )
    country_chips = '<button class="chip" type="button" data-country="" aria-pressed="true">Все страны</button>' + "".join(
        f'<button class="chip" type="button" data-country="{esc(code)}" aria-pressed="false">{esc(COUNTRY_LABELS.get(code, code))}</button>'
        for code, _ in sorted(country_counts.items(), key=lambda pair: -pair[1])[:10]
    )
    return (
        '<div class="filters">'
        '<div class="filter-row"><div class="chips" id="type-chips">' + type_chips + '</div>'
        '<div class="selects">'
        '<button class="select" type="button" data-sort="rating" aria-pressed="true">По рейтингу</button>'
        '<button class="select" type="button" data-sort="date" aria-pressed="false">По дате</button>'
        '<button class="select" type="button" data-sort="votes" aria-pressed="false">По голосам</button>'
        '<button class="select" type="button" data-sort="title" aria-pressed="false">По названию</button>'
        '<button class="select" type="button" id="reset-btn">Сбросить</button>'
        '</div></div>'
        '<div class="filter-row" style="margin-top:12px"><div class="chips" id="genre-chips">' + genre_chips + '</div></div>'
        '<div class="filter-row" style="margin-top:12px"><div class="chips" id="country-chips">' + country_chips + '</div></div>'
        '<div class="filter-row" style="margin-top:12px">'
        '<label class="search-slim" for="q"><input type="search" id="q" placeholder="Поиск по названию" aria-label="Поиск по названию"></label>'
        '<div class="chips">'
        '<button class="chip" type="button" data-flag="rating8" aria-pressed="false">Рейтинг 8+</button>'
        '<button class="chip" type="button" data-flag="new" aria-pressed="false">Скоро серия</button>'
        '</div></div>'
        '</div>'
        '<p class="filter-status" id="found"></p>'
        '<p class="lead muted" id="empty" hidden>Ничего не найдено. Попробуйте изменить фильтры.</p>'
    )


def list_page(title, items, current, ratings, lead, filters=False):
    """Страница-список. С filters=True добавляется панель фильтрации каталога."""
    cards = "".join(card(item, current, ratings, with_data=filters) for item in items)
    grid_id = ' id="grid"' if filters else ""
    panel = catalog_filters(items) if filters else ""
    return page(
        title,
        f'<section class="band wrap"><div class="label dim">Титры</div>'
        f'<h1 class="h2">{esc(title)}</h1><p class="lead muted">{esc(lead)}</p>'
        f'<div class="filters-wrap">{panel}</div>'
        f'<div class="grid-posters"{grid_id}>{cards}</div></section>',
        current,
        lead,
        extra_script=CATALOG_JS if filters else "",
    )



    cards = "".join(card(item, current, ratings) for item in items)
    return page(title, f'<section class="band wrap"><div class="label dim">Титры</div><h1 class="h2">{esc(title)}</h1><p class="lead muted">{esc(lead)}</p><div class="grid-posters">{cards}</div></section>', current, lead)


def calendar_page(year, month, events, contents, ratings, current=None, available_months=None):
    current = current or Path("calendar") / str(year) / str(month)
    available_months = sorted(available_months or {(year, month)})
    by_id = {item["id"]: item for item in contents}
    days = defaultdict(list)
    for item in events:
        released = parse_local_date(item["release_date"])
        if released and released.year == year and released.month == month:
            days[released.day].append(item)
    current_key = (year, month)
    index = available_months.index(current_key) if current_key in available_months else 0
    previous = available_months[index - 1] if index else None
    following = available_months[index + 1] if index + 1 < len(available_months) else None
    previous_link = f'<a href="{rel(current, f"calendar/{previous[0]}/{previous[1]}/")}">← Предыдущий месяц</a>' if previous else '<span>← Предыдущий месяц</span>'
    following_link = f'<a href="{rel(current, f"calendar/{following[0]}/{following[1]}/")}">Следующий месяц →</a>' if following else '<span>Следующий месяц →</span>'
    rows = []
    for day in sorted(days):
        grouped = defaultdict(list)
        for item in days[day]: grouped[(item["content_id"], item["event_type"])].append(item)
        blocks = []
        for (_, kind), group in grouped.items():
            item = by_id.get(group[0]["content_id"])
            if not item: continue
            label = "все серии" if len(group) > 1 else (EPISODE_WORD.get(item["content_type"], "выпуск") + (f' {group[0]["episode_number"]}' if group[0].get("episode_number") else ""))
            blocks.append(f'<li><a href="{content_href(item, current)}">{esc(item["title"])}</a> · {esc(label)}</li>')
        rows.append(f'<section class="calendar-day"><h2>{day} {MONTHS[month - 1]}</h2><ul>{"".join(blocks)}</ul></section>')
    content = f'''<section class="band wrap"><div class="label dim">Календарь релизов</div><h1 class="h2">{MONTHS_GEN[month - 1].capitalize()} {year}</h1><div class="calendar-nav">{previous_link}<a href="{rel(current, f'calendar/{today_moscow().year}/{today_moscow().month}/')}">Сегодня</a>{following_link}</div>{''.join(rows) or '<p class="lead muted">Подтверждённых релизов пока нет.</p>'}</section>'''
    return page("Календарь", content, current, "Календарь премьер, серий и выпусков")


def my_list_page():
    current = Path("my-list")
    body = '''<section class="band wrap"><div class="label dim">Мой список</div><h1 class="h2">Смотреть позже</h1><p class="lead muted">Список хранится в этом браузере.</p><div class="grid-posters" id="my-list-grid"></div><p class="lead muted" id="my-list-empty">В списке пока нет проектов.</p>
<p class="lead muted">Всего сохранено: <b id="my-list-total">0</b></p></section>'''
    return page("Мой список", body, current)


def journal_page():
    current = Path("journal")
    return page("Журнал", '<section class="band wrap"><div class="label dim">Журнал</div><h1 class="h2">Крупным планом</h1><p class="lead muted">Новости, разборы и подборки редакции Титров.</p></section>', current)


def detail_page(item, ratings, season=None):
    current = detail_path(item)
    image = f'<img src="{esc(item.get("backdrop") or item.get("poster"))}" alt="{esc(item["title"])}">' if item.get("backdrop") or item.get("poster") else ""
    data = season or {}
    next_event = data.get("next_event") or {}
    next_date = data.get("next_date")
    number = next_event.get("episode_number")
    if next_date and number:
        next_text = f"{next_label(number, item['content_type'])} · {next_date.day} {month_name(next_date.month)}"
    elif next_date:
        next_text = f"Премьера · {next_date.day} {month_name(next_date.month)}"
    else:
        next_text = ""
    body = f'''<section class="detail-hero"><div class="detail-media">{image}</div><div class="wrap detail-inner"><a class="back" href="{rel(current, 'catalog/')}">← Каталог</a><h1 class="h2 detail-title">{esc(item["title"])}</h1><p class="lead muted">{esc(CONTENT_TYPES.get(item["content_type"], item["content_type"]))} · {esc(status_label(item.get("status")))}</p><p class="lead">{esc(item.get("overview"))}</p><button class="btn btn-cream" type="button" data-watch-id="{esc(item["id"])}" data-watch-type="{esc(item["content_type"])}" data-watch-title="{esc(item["title"])}" data-watch-poster="{esc(item.get("poster"))}" data-watch-url="{rel(current, f'{section_of(item)}/{path_slug(item)}/')}">+ В мой список</button>{after_credits(item, ratings)}<section class="facts"><div><b>Выпуски</b><span>{progress_visual(item, data) if item["content_type"] != "movie" else esc(progress(item))}</span></div><div><b>Следующий релиз</b><span>{esc(next_text or 'Дата не объявлена')}</span></div></section></div></section>'''
    return page(item["title"], body, current, item.get("overview", "")[:160])


def month_name(month):
    return MONTHS[month - 1]


def editorial_banner_ids():
    """Редакторский порядок баннеров из data/editorial/featured.json."""
    document = load(DATA / "editorial" / "featured.json", {"banner_ids": []})
    return [str(x) for x in (document.get("banner_ids") or []) if x]


PREMIERE_EVENTS = {"series_premiere", "season_premiere", "movie_theatrical", "movie_digital", "movie_streaming", "show_episode", "reality_episode", "special"}


def month_candidates(contents, events, year, month):
    """Проекты с релизом в месяце и признаки, по которым выбираем баннер."""
    by_id = {item["id"]: item for item in contents}
    found = {}
    for event in events:
        released = parse_local_date(event.get("release_date"))
        if not released or released.year != year or released.month != month:
            continue
        item = by_id.get(event["content_id"])
        if not item or not (item.get("backdrop") or item.get("poster")):
            continue
        entry = found.setdefault(item["id"], {"item": item, "kinds": set(), "dates": []})
        entry["kinds"].add(event.get("event_type"))
        entry["dates"].append(released)
    result = []
    for entry in found.values():
        item = entry["item"]
        is_premiere = bool(entry["kinds"] & PREMIERE_EVENTS)
        # «Премьера месяца» — это проект, который стартовал в этом году,
        # а не многолетний сериал, у которого просто вышла очередная серия.
        fresh = str(item.get("year_start") or "") == str(year)
        result.append({
            "item": item,
            "is_premiere": is_premiere,
            "fresh": fresh,
            "first_date": min(entry["dates"]),
        })
    return result


def popular_of_month(contents, events, year, month, limit=6):
    """До 6 баннеров: сначала премьеры этого года, затем остальные релизы месяца.

    Внутри каждой группы — по популярности. Проекты без постера и кадра
    не участвуют: пустой баннер выглядит сломанным.
    """
    candidates = month_candidates(contents, events, year, month)

    # Сначала редакторские пины из data/editorial/featured.json: редактор
    # решает, что важно, ровно как в ТЗ (override выше автоматики).
    pinned = []
    by_id = {row["item"]["id"]: row["item"] for row in candidates}
    for content_id in editorial_banner_ids():
        item = by_id.get(content_id)
        if item and item not in pinned:
            pinned.append(item)

    # Остальные места добираем автоматически: проект месяца с голосами.
    # Проект без единой оценки баннер не занимает — карточка без рейтинга
    # читается как ошибка отбора.
    rated = [row for row in candidates if (row["item"].get("vote_count") or 0) > 0]
    pool = rated or candidates
    pool.sort(key=lambda row: (
        0 if row["fresh"] else 1,
        0 if row["is_premiere"] else 1,
        -float(row["item"].get("popularity") or 0),
        -float(row["item"].get("vote") or 0),
    ))
    result = list(pinned)
    for row in pool:
        if len(result) >= limit:
            break
        if row["item"] not in result:
            result.append(row["item"])
    return result[:limit]


def release_status_line(item, events, today):
    """Что происходит с проектом прямо сейчас: короткая честная строка для hero.

    Собирается из событий, а не из догадок: серия, сезон или полный сезон.
    """
    rows = sorted(
        ((released, e) for e in events
         if e.get("content_id") == item["id"]
         and (released := parse_local_date(e.get("release_date")))),
        key=lambda pair: pair[0],
    )
    word = EPISODE_WORD.get(item["content_type"], "выпуск")
    total = item.get("total_episodes")
    aired = item.get("aired_count") or 0

    if total and aired >= total and rows and rows[-1][0] <= today:
        return f"Все {episode_word(total, item['content_type'])} уже доступны"

    today_rows = [e for d, e in rows if d == today]
    if today_rows:
        event = today_rows[0]
        number, season = event.get("episode_number"), event.get("season_number")
        if len(today_rows) > 1:
            return f"Сегодня выходит весь сезон · {episode_word(len(today_rows), item['content_type'])}"
        if number and season:
            return f"Сегодня {word} {number} сезона {season}"
        if number:
            return f"Сегодня {word} {number}"
        return "Сегодня премьера"

    future = [(d, e) for d, e in rows if d > today]
    if future:
        released, event = future[0]
        number, season = event.get("episode_number"), event.get("season_number")
        when = f"{released.day} {month_name(released.month)}"
        if number and season:
            return f"Новая {word} {number} · сезон {season} · {when}"
        if number:
            return f"Новая {word} {number} · {when}"
        return f"Премьера · {when}"

    if aired:
        return f"Вышло {aired} {episode_word(aired, item['content_type'])}"
    return ""


def banner_slider(contents, events, current, year, month):
    """Баннер-слайдер: до шести проектов с релизом в этом месяце.

    Порядок: редакторские пины, затем актуальность релиза, популярность
    и оценки. Счётчик вида «24 / 13» в hero не используется.
    """
    slides = popular_of_month(contents, events, year, month)
    if not slides:
        return ""
    month_title = month_name(month).capitalize()
    today = today_moscow()
    articles = []
    for index, item in enumerate(slides):
        image = esc(item.get("backdrop") or item.get("poster"))
        active = " is-active" if index == 0 else ""
        hidden = "" if index == 0 else ' aria-hidden="true"'
        loading = "" if index == 0 else ' loading="lazy"'
        meta = " · ".join(
            part for part in (
                CONTENT_TYPES.get(item["content_type"], item["content_type"]),
                esc(status_label(item.get("status"))),
                esc(item.get("network")),
            ) if part
        )
        status = release_status_line(item, events, today)
        original = (item.get("original_title") or "").strip()
        title_block = f'<h2 class="slide-title">{esc(item["title"])}</h2>'
        if original and original.lower() != (item.get("title") or "").strip().lower():
            title_block += f'<p class="slide-original">{esc(original)}</p>'
        link = content_href(item, current)
        articles.append(
            f'<article class="slide{active}" data-slide{hidden}>'
            f'<div class="slide-bg"><img src="{image}" alt="{esc(item["title"])}"{loading}></div>'
            f'<div class="slide-inner wrap">'
            f'<span class="label dim">Премьера месяца · {month_title}</span>'
            f'{title_block}'
            + (f'<p class="slide-status">{esc(status)}</p>' if status else "")
            + f'<p class="slide-lead">{esc((item.get("overview") or "")[:190])}</p>'
            f'<div class="slide-meta label dim">{meta}</div>'
            f'<div class="slide-actions">'
            f'<a class="btn btn-cream" href="{link}">О проекте</a>'
            f'<button class="btn btn-ghost slide-watch" type="button" data-watch-id="{esc(item["id"])}"'
            f' data-watch-type="{esc(item["content_type"])}" data-watch-title="{esc(item["title"])}"'
            f' data-watch-poster="{esc(item.get("poster"))}" data-watch-url="{link}">+ В мой список</button>'
            f'</div></div></article>'
        )
    dot_parts = []
    for index, item in enumerate(slides):
        dot_class = " is-active" if index == 0 else ""
        current_attr = ' aria-current="true"' if index == 0 else ""
        dot_parts.append(
            f'<button class="slide-dot{dot_class}" type="button"'
            f' data-slide-to="{index}" aria-label="Баннер {index + 1}: {esc(item["title"])}"'
            f'{current_attr}></button>'
        )
    dots = "".join(dot_parts)
    arrows = (
        '<button class="slide-arrow slide-prev" type="button" data-slide-prev aria-label="Предыдущий баннер">←</button>'
        '<button class="slide-arrow slide-next" type="button" data-slide-next aria-label="Следующий баннер">→</button>'
    ) if len(slides) > 1 else ""
    return (
        '<section class="hero-banner" data-slider aria-roledescription="карусель"'
        ' aria-label="Премьеры месяца">'
        + "".join(articles)
        + f'<div class="slide-controls wrap">{arrows}<div class="slide-dots" role="tablist">{dots}</div></div>'
        + "</section>"
    )


def episode_line(event, today):
    """Живая линейка: что уже вышло, что выходит сегодня, что впереди."""
    released = parse_local_date(event.get("release_date"))
    number = event.get("episode_number")
    season = event.get("season_number")
    if released is None:
        return "дата не объявлена"
    if released < today:
        verb = "Вышла"
    elif released == today:
        verb = "Выходит сегодня"
    else:
        verb = "Выйдет"
    stamp = f"{released.day} {month_name(released.month)}"
    if verb == "Выходит сегодня":
        return "Выходит сегодня"
    if number and season:
        return f"{verb} серия {number} · сезон {season} · {stamp}"
    if number:
        return f"{verb} серия {number} · {stamp}"
    return f"{verb} · {stamp}"


def genres_of(item, limit=2):
    """Читаемые жанры проекта из genre_ids. Пустой список, если жанров нет."""
    return [GENRE_LABELS[g] for g in (item.get("genre_ids") or []) if g in GENRE_LABELS][:limit]


def season_progress(events, item, season, today):
    """Сколько серий сезона уже вышло и сколько заявлено.

    Вышедшие считаем по событиям: серия с датой не позже сегодня. Заявленное
    берём из модели сезона; если оно неизвестно, честно возвращаем None,
    а не подставляем выдуманное число.
    """
    aired = 0
    for event in events:
        if event.get("content_id") != item["id"]:
            continue
        if event.get("season_number") != season or not event.get("episode_number"):
            continue
        released = parse_local_date(event.get("release_date"))
        if released and released <= today:
            aired = max(aired, event["episode_number"])
    return aired


def hero_stage(contents, events, current, today, year, month):
    """Первый экран: заголовок, поиск, теги и карточка «В центре внимания»."""
    slides = popular_of_month(contents, events, year, month, limit=6)
    if not slides:
        return ""
    featured = slides[0]
    image = esc(featured.get("backdrop") or featured.get("poster"))
    vote = featured.get("vote")
    rating = f'<b>{esc(rating_text(vote))}</b> <em>TMDB</em>' if vote else ""
    genre = genres_of(featured, 1)
    facts = " · ".join(part for part in (
        esc(featured.get("year_start")),
        esc(CONTENT_TYPES.get(featured["content_type"], featured["content_type"]).capitalize()),
        esc(genre[0].capitalize()) if genre else "",
    ) if part)
    status = release_status_line(featured, events, today)
    link = content_href(featured, current)
    catalog = rel(current, "catalog/")
    chips = (
        '<div class="hero-chips">'
        f'<a class="chip" href="{catalog}?type=tv">Сериалы</a>'
        f'<a class="chip" href="{catalog}?type=movie">Фильмы</a>'
        f'<a class="chip" href="{catalog}?flag=rating8">Рейтинг 8+</a>'
        f'<a class="chip" href="{catalog}?flag=new">Новая серия</a>'
        "</div>"
    )
    return (
        '<section class="hero-stage" id="hero">'
        f'<div class="hero-stage-bg"><img src="{image}" alt="{esc(featured["title"])}"></div>'
        '<div class="hero-stage-grid wrap">'
        '<div class="hero-stage-main">'
        '<div class="hero-stage-top"><span class="label dim">Кино и сериалы в одном месте</span>'
        f'<time class="hero-stage-date" datetime="{today.isoformat()}">{today.day:02d} / {today.month:02d} / {today.year}</time></div>'
        '<h1 class="hero-stage-title">Что смотрим сегодня?</h1>'
        '<p class="hero-stage-lead">Найдите своё кино. Оценки, даты выхода и новые серии — всё под рукой.</p>'
        f'<form class="hero-search" action="{catalog}" method="get" role="search">'
        '<span class="hero-search-icon" aria-hidden="true">⌕</span>'
        '<input type="search" name="q" placeholder="Фильм, сериал или настроение" aria-label="Поиск по каталогу">'
        '<button class="hero-search-btn" type="submit">Найти</button></form>'
        + chips
        + "</div>"
        '<aside class="hero-feature">'
        '<span class="label dim">В центре внимания</span>'
        f'<span class="hero-feature-count"><b>01</b> /{len(slides):02d}</span>'
        f'<a class="hero-feature-link" href="{link}"><h2 class="hero-feature-title">{esc(featured["title"])}</h2></a>'
        f'<div class="hero-feature-meta">{rating}<span>{facts}</span></div>'
        + (f'<p class="hero-feature-status">• {esc(status)}</p>' if status else "")
        + f'<a class="btn btn-cream hero-feature-btn" href="{link}">О сериале <span aria-hidden="true">+</span></a>'
        "</aside></div></section>"
    )


def today_ticker(events, contents, current, today):
    """Тонкая строка «Сегодня вышло» под первым экраном."""
    by_id = {item["id"]: item for item in contents}
    found = []
    for event in events:
        if parse_local_date(event.get("release_date")) != today:
            continue
        if event.get("verification_status") not in VERIFIED_STATUSES:
            continue
        item = by_id.get(event["content_id"])
        if item and item not in found:
            found.append(item)
    if not found:
        text = "Сегодня подтверждённых релизов нет"
    else:
        first = found[0]
        text = f"«{esc(first['title'])}»"
        if len(found) > 1:
            text += f" и ещё {len(found) - 1}"
    return (
        '<section class="ticker"><div class="wrap ticker-inner">'
        f'<span class="ticker-label">Сегодня вышло</span>'
        f'<span class="ticker-text">{text}</span>'
        f'<a class="ticker-link" href="{rel(current, "calendar/")}" aria-label="Календарь выхода">▤</a>'
        '<span class="ticker-note">Хорошее кино продолжается.</span>'
        "</div></section>"
    )


def showcase_card(item, events, current, today):
    """Карточка блока 01: постер с оценкой TMDB, метрика и нижняя строка."""
    vote = item.get("vote")
    badge = f'<span class="badge-rate">{esc(rating_text(vote))} <em>TMDB</em></span>' if vote else ""
    poster = item.get("poster")
    image = f'<img src="{esc(poster)}" alt="{esc(item["title"])}" loading="lazy">' if poster else ""
    genre = genres_of(item, 1)
    meta = " · ".join(part for part in (
        esc(item.get("year_start")),
        esc(CONTENT_TYPES.get(item["content_type"], item["content_type"]).capitalize()),
        esc(genre[0].capitalize()) if genre else "",
    ) if part)
    line = release_status_line(item, events, today)
    bullet = "• " if line.startswith(("Сегодня", "Новая", "Выйдет", "Выйд")) else ""
    tag = f'<span class="dot" aria-hidden="true"></span><span class="t">{esc(bullet + line)}</span>' if line else ""
    link = content_href(item, current)
    return (
        f'<article class="card film-card"><a href="{link}"><div class="card-media">{image}{badge}</div>'
        f'<h3 class="card-title">{esc(item["title"])}</h3></a>'
        f'<div class="card-meta">{meta}</div>'
        + (f'<div class="card-tag">{tag}</div>' if tag else "")
        + f'<button class="card-mark" type="button" data-watch-id="{esc(item["id"])}"'
          f' data-watch-type="{esc(item["content_type"])}" data-watch-title="{esc(item["title"])}"'
          f' data-watch-url="{link}" data-watch-poster="{esc(item.get("poster"))}"'
          ' aria-label="Добавить в мой список">+</button></article>'
    )


def showcase_home(contents, events, current, today, year, month):
    """Блок 01: «Что посмотреть» — фильтры-строки и сетка постеров."""
    items = popular_of_month(contents, events, year, month, limit=6)
    if not items:
        return ""
    cards = "".join(showcase_card(item, events, current, today) for item in items)
    catalog = rel(current, "catalog/")
    return (
        '<section class="band wrap" id="showcase">'
        + section_head("01", "Что посмотреть", "На вашем экране", "Истории, на которые стоит потратить вечер")
        + '<div class="showcase-row"><div class="chips">'
          f'<a class="chip chip-on" href="{catalog}">Всё</a>'
          f'<a class="chip" href="{catalog}?type=tv">Сериалы</a>'
          f'<a class="chip" href="{catalog}?type=movie">Фильмы</a>'
          '</div><div class="selects">'
          f'<a class="select" href="{catalog}">Все жанры</a>'
          f'<a class="select" href="{catalog}?sort=rating">Популярное</a>'
          '</div></div>'
        + f'<div class="grid-posters">{cards}</div></section>'
    )


def journal_block(contents, events, ratings, current, today):
    """Блок 03: «После титров» — разборы с обложкой, меткой и описанием."""
    scored = [item for item in contents if aggregate_rating(ratings.get(item["id"])) is not None]
    scored.sort(key=lambda item: (-aggregate_rating(ratings.get(item["id"])), item["title"]))
    rows, seen = [], set()
    for item in scored:
        rows.append(item)
        seen.add(item["id"])
    if len(rows) < 3:
        for item in popular_of_month(contents, events, today.year, today.month, limit=8):
            if item["id"] in seen:
                continue
            rows.append(item)
            seen.add(item["id"])
            if len(rows) >= 3:
                break
    cards = []
    for item in rows[:3]:
        value = aggregate_rating(ratings.get(item["id"]))
        image = esc(item.get("backdrop") or item.get("poster"))
        badge = "Разбор" if value is not None else CONTENT_TYPES.get(item["content_type"], "проект").capitalize()
        line = release_status_line(item, events, today) or "Материал готовится"
        meta = f"После титров · {rating_text(value)} из 10" if value is not None else line
        link = content_href(item, current)
        cards.append(
            f'<article class="journal-card"><a href="{link}">'
            f'<div class="journal-media"><img src="{image}" alt="" loading="lazy"><span class="journal-badge">{esc(badge)}</span></div>'
            f'<span class="journal-meta">{esc(meta)}</span>'
            f'<h3 class="journal-title">{esc(item["title"])}</h3></a>'
            f'<p class="journal-lead">{esc((item.get("overview") or "")[:150])}</p></article>'
        )
    return (
        '<section class="band wrap" id="closeup">'
        + section_head("03", "Крупным планом", "После титров", "Детали, которые делают историю интереснее")
        + f'<div class="journal-grid">{"".join(cards)}</div>'
        + f'<p class="cal-note"><a href="{rel(current, "journal/")}">Все материалы Журнала</a></p>'
        + "</section>"
    )


def calendar_spotlight(events, contents, current, today, seasons=None):
    """Блок 02: светлый недельный календарь «Не пропустите продолжение».

    Слева — релиз выбранного дня, справа — ближайшая серия с прогрессом сезона.
    Числа берутся из событий: вышедшие серии считаются по датам, заявленное
    количество — из модели сезона. Неизвестное не подменяется выдумкой.
    """
    by_id = {item["id"]: item for item in contents}
    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=index) for index in range(7)]
    events_by_day = defaultdict(list)
    for event in events:
        released = parse_local_date(event.get("release_date"))
        if released in week_days and event.get("verification_status") in VERIFIED_STATUSES:
            item = by_id.get(event.get("content_id"))
            if item:
                events_by_day[released].append((item, event))

    def priority(pair):
        item, event = pair
        return (
            1 if event.get("episode_number") else 0,
            item.get("vote") or 0,
            item.get("popularity") or 0,
        )

    available = [day for day in week_days if events_by_day.get(day)]
    selected_day = next((day for day in reversed(week_days) if events_by_day.get(day)), week_days[0])

    # Ближайшая серия: событие с эпизодом и датой строго впереди.
    upcoming = None
    for event in events:
        if not event.get("episode_number"):
            continue
        if event.get("verification_status") not in VERIFIED_STATUSES:
            continue
        released = parse_local_date(event.get("release_date"))
        if not released or released <= today:
            continue
        if upcoming is None or released < parse_local_date(upcoming.get("release_date")):
            upcoming = event

    def next_series(item, event):
        season = event.get("season_number")
        episode = event.get("episode_number") or 0
        model = (seasons or {}).get(item["id"]) or {}
        season = model.get("season") or season
        aired = model.get("season_aired")
        if aired is None:
            aired = season_progress(events, item, season, today)
        total = model.get("season_total")
        released = parse_local_date(event.get("release_date"))
        genre = genres_of(item, 1)
        facts = " · ".join(part for part in (
            f"Сезон {season}" if season else "",
            esc(item.get("network") or ""),
            esc(genre[0].capitalize()) if genre else "",
        ) if part)
        when = ""
        if released:
            stamp = f"{released.day} {month_name(released.month)}"
            relative = relative_day(released.isoformat(), today)
            when = f"{relative.capitalize()}, {stamp}" if relative else stamp
        # Сколько квадратов нарисовать: объявленный размер сезона, иначе — по
        # последней известной серии. Это визуальный ориентир, а не утверждение
        # о длине сезона, поэтому рядом всегда стоит подпись со смыслом.
        span = total if total else max(episode, aired)
        squares = []
        for number in range(1, min(span, 24) + 1):
            cls = " is-aired" if number <= aired else ""
            if number == episode:
                cls += " is-next"
            squares.append(f'<span class="cal-square{cls}">{number:02d}</span>')
        if total:
            count_block = (f'<div class="cal-count"><b>{aired:02d}</b><span>/{total:02d}</span></div>'
                           '<p class="cal-count-note">серий уже вышло</p>')
        else:
            count_block = (f'<div class="cal-count"><b>{aired:02d}</b></div>'
                           '<p class="cal-count-note">серий уже вышло · размер сезона пока не объявлен</p>')
        return (
            '<div class="cal-right">'
            + '<div class="cal-right-head"><span class="cal-label">Следующая серия</span>'
            + '<span class="cal-clock" aria-hidden="true">◷</span></div>'
            + f'<a class="cal-right-link" href="{content_href(item, current)}"><h3>{esc(item["title"])}</h3></a>'
            + f'<p class="cal-right-facts">{facts}</p>'
            + count_block
            + f'<div class="cal-squares" role="img" aria-label="Вышло {aired} серий">{"".join(squares)}</div>'
            + '<div class="cal-next-row"><div><span class="cal-label">'
            + f'Эпизод {episode}</span>'
            + f'<b>{when or "дата уточняется"}</b></div>'
            + f'<a class="cal-round" href="{content_href(item, current)}" aria-label="Добавить в мой список">+</a></div>'
            + "</div>"
        )

    def panel(day):
        best = max(events_by_day.get(day, []), key=priority, default=None)
        left = ""
        if best:
            item, event = best
            poster = item.get("poster")
            image = f'<img src="{esc(poster)}" alt="" loading="lazy">' if poster else ""
            season = event.get("season_number")
            episode = event.get("episode_number")
            parts = []
            if season:
                parts.append(f"Сезон {season}")
            if episode:
                parts.append(f"{episode_word(episode, item['content_type']).capitalize()} {episode}")
            if event.get("episode_name") and not str(event["episode_name"]).startswith("Эпизод"):
                parts.append(f"«{event['episode_name']}»")
            subtitle = " · ".join(parts) or "Премьера"
            left = (
                '<div class="cal-left">'
                f'<a class="cal-release" href="{content_href(item, current)}">'
                f'<span class="cal-poster">{image}</span>'
                f'<span><b>{esc(item["title"])}</b><small>{esc(subtitle)}</small></span></a>'
                f'<span class="cal-network">{esc(item.get("network") or "")}</span>'
                f'<button class="cal-plus" type="button" data-watch-id="{esc(item["id"])}"'
                f' data-watch-type="{esc(item["content_type"])}" data-watch-title="{esc(item["title"])}"'
                f' data-watch-url="{content_href(item, current)}" data-watch-poster="{esc(item.get("poster"))}"'
                ' aria-label="Добавить в мой список">+</button></div>'
            )
        right = ""
        if upcoming:
            target = by_id.get(upcoming.get("content_id"))
            if target:
                right = next_series(target, upcoming)
        hidden = "" if day == selected_day else " hidden"
        return f'<div class="cal-body" data-cal-panel="{day.isoformat()}"{hidden}>{left}{right}</div>'

    weekday = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
    day_buttons = []
    for index, day in enumerate(week_days):
        active = " is-active" if day == selected_day else ""
        pressed = "true" if day == selected_day else "false"
        has = " has-release" if events_by_day.get(day) else ""
        day_buttons.append(
            f'<button class="cal-day{active}{has}" type="button" data-cal-day="{day.isoformat()}"'
            f' aria-pressed="{pressed}"><span class="cal-day-num">{day.day:02d}</span>'
            f'<span class="cal-day-name">{weekday[index]}</span>'
            '<span class="cal-day-dot" aria-hidden="true"></span></button>'
        )
    panels = "".join(panel(day) for day in week_days)
    month_href = rel(current, f"calendar/{today.year}/{today.month}/")
    note = ("" if upcoming else
            '<p class="cal-note">Ближайшая серия пока без объявленной даты — покажем, как только появится.</p>')
    return (
        '<section class="calendar-band wrap" id="calendar">'
        '<div class="cal-head"><div class="cal-head-main">'
        '<span class="cal-kicker">02 / Календарь выхода</span>'
        '<h2 class="cal-title">Не пропустите<br>продолжение.</h2></div>'
        '<div class="cal-head-side"><p>Когда новая серия?<br>Здесь всё по датам.</p>'
        f'<a class="cal-cta" href="{month_href}">Весь {MONTHS_GEN[today.month - 1]} <span aria-hidden="true">▤</span></a>'
        '</div></div>'
        f'<div class="cal-week"><span class="cal-range">{week_start.day} {month_name(week_start.month)} — {week_days[-1].day} {month_name(week_days[-1].month)}</span>'
        f'<span class="cal-year">{today.year}</span></div>'
        f'<div class="cal-days" role="group" aria-label="Неделя релизов">{"".join(day_buttons)}</div>'
        f'<div class="cal-panels" data-cal-panels>{"".join(panels)}</div>'
        + note
        + "</section>"
    )


def calendar_inline(events, contents, current, today, year, month, available=None):
    """Блок 01: календарь выходов.

    Главный продуктовый блок страницы. Строится только из release_events,
    поэтому в него попадают сериалы, аниме, реалити, шоу и премьеры сезонов.
    Каждое название — ссылка на внутреннюю страницу проекта.
    """
    by_id = {item["id"]: item for item in contents}
    days = defaultdict(list)
    for event in events:
        released = parse_local_date(event.get("release_date"))
        if released and released.year == year and released.month == month:
            days[released.day].append(event)
    rows = []
    for day in sorted(days):
        lines = []
        seen = set()
        by_project = defaultdict(list)
        for event in days[day]:
            by_project[event["content_id"]].append(event)
        for content_key, group in by_project.items():
            item = by_id.get(content_key)
            if not item:
                continue
            group.sort(key=lambda e: (e.get("season_number") or 0, e.get("episode_number") or 0))
            event = group[0]
            # Премьера сериала и первая серия одного дня — одно событие для читателя,
            # а не две строки подряд про один и тот же проект.
            kinds = {e.get("event_type") for e in group}
            if len(group) > 1 and kinds & PREMIERE_EVENTS and len(group) <= 2:
                group = [next((e for e in group if e.get("episode_number")), group[0])]
            poster = item.get("poster")
            thumb = f'<img class="thumb" src="{esc(poster)}" alt="" loading="lazy">' if poster else '<span class="thumb"></span>'
            # Пять и более серий в один день — это полный сезон, а не пять строк подряд.
            if len(group) >= 5:
                sub = f'Весь сезон · {episode_word(len(group), item["content_type"])}'
            elif len(group) > 1:
                numbers = [e.get("episode_number") for e in group if e.get("episode_number")]
                season = event.get("season_number")
                label = f"сезон {season} · " if season else ""
                sub = f'{label}{episode_word(len(numbers) or len(group), item["content_type"])} {", ".join(str(n) for n in numbers)}'
            elif event.get("event_type") in {"series_premiere", "season_premiere"}:
                season = event.get("season_number")
                sub = f"Премьера сезона {season} · {episode_line(event, today)}" if season else f"Премьера · {episode_line(event, today)}"
            else:
                sub = episode_line(event, today)
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            lines.append(
                f'<li class="rel"><span class="rel-day">{day}</span>'
                f'<a class="rel-link" href="{content_href(item, current)}">{thumb}'
                f'<span class="rel-text"><b>{esc(item["title"])}</b>'
                f'<span class="rel-sub">{esc(sub)}</span></span></a></li>'
            )
        if lines:
            rows.append(f'<ul class="rel-day-group">{"".join(lines)}</ul>')
    body = "".join(rows) or '<p class="lead muted">В этом месяце подтверждённых релизов пока нет.</p>'
    month_href = rel(current, f"calendar/{year}/{month}/")
    return (
        f'<section class="band wrap" id="calendar">'
        + section_head("01", "Календарь выхода", f"{MONTHS_GEN[month - 1].capitalize()} {year}: что выходит")
        + f'<div class="calendar-nav">{calendar_links(current, year, month, available)}'
          f'<a class="cal-month-link" href="{month_href}">Весь {MONTHS_GEN[month - 1]}</a></div>'
        + f'<div class="cal-lines">{body}</div>'
        + f'<p class="cal-note">Не пропустите продолжение: даты серий сверяются с официальными источниками, '
          f'затем с TVMaze и TMDB. Неподтверждённая дата не показывается как состоявшийся релиз.</p>'
        + '</section>'
    )


def month_link(current, target_year, target_month, label, available):
    """Ссылка на месяц, если он собран. Иначе — просто подпись без ссылки."""
    if available and (target_year, target_month) not in set(available):
        return f'<span class="cal-off">{label}</span>'
    return f'<a href="{rel(current, f"calendar/{target_year}/{target_month}/")}">{label}</a>'


def calendar_links(current, year, month, available=None):
    """Навигация по месяцам: назад, сегодня, вперёд."""
    first = date(year, month, 1)
    previous = first - timedelta(days=1)
    following = (first + timedelta(days=32)).replace(day=1)
    today = today_moscow()
    return (
        month_link(current, previous.year, previous.month, "← Предыдущий месяц", available)
        + month_link(current, today.year, today.month, "Сегодня", available)
        + month_link(current, following.year, following.month, "Следующий месяц →", available)
    )


VERIFIED_STATUSES = {"official", "editorial_verified", "aggregator_confirmed"}


def today_block(events, contents, current, today):
    """Что вышло сегодня. Только подтверждённые события, без догадок.

    Дата берётся по Москве. Событие без верификации в этот блок не попадает:
    «сегодня» — утверждение, которое нужно подтверждать.
    """
    by_id = {item["id"]: item for item in contents}
    items, seen = [], set()
    for event in events:
        if parse_local_date(event.get("release_date")) != today:
            continue
        if event.get("verification_status") not in VERIFIED_STATUSES:
            continue
        item = by_id.get(event["content_id"])
        if not item:
            continue
        marker = item["id"] if event.get("episode_number") in (None, 1) else (item["id"], event.get("episode_number"))
        if marker in seen:
            continue
        seen.add(marker)
        items.append((item, event))

    heading = f"Сегодня, {today.day} {month_name(today.month)}"
    if not items:
        inner = (
            '<p class="lead muted">Сегодня новых подтверждённых серий нет.</p>'
            f'<p class="cal-note"><a href="{rel(current, "calendar/")}">Посмотреть ближайшие релизы</a></p>'
        )
        return (
            f'<section class="band wrap" id="today">'
            f'<div class="label dim">Сегодня вышло</div>'
            f'<h2 class="h2">{esc(heading)}</h2>'
            f'{inner}</section>'
        )

    shown = items[:8]
    rows = []
    for item, event in shown:
        number, season = event.get("episode_number"), event.get("season_number")
        word = EPISODE_WORD.get(item["content_type"], "выпуск")
        parts = []
        if season:
            parts.append(f"сезон {season}")
        if number:
            parts.append(f"{word} {number}")
        if len([e for e in events if e.get("content_id") == item["id"] and parse_local_date(e.get("release_date")) == today]) > 1:
            parts = [f"весь сезон"]
        detail = " · ".join(parts) or "премьера"
        poster = item.get("poster")
        thumb = f'<img class="thumb" src="{esc(poster)}" alt="" loading="lazy">' if poster else '<span class="thumb"></span>'
        rows.append(
            f'<li class="today-item"><a class="rel-link" href="{content_href(item, current)}">{thumb}'
            f'<span class="rel-text"><b>{esc(item["title"])}</b>'
            f'<span class="rel-sub">{esc(detail)}'
            + (f' · {esc(item.get("network"))}' if item.get("network") else "")
            + '</span></span></a></li>'
        )
    inner = f'<ul class="today-list">{"".join(rows)}</ul>'
    rest = len(items) - len(shown)
    if rest > 0:
        inner += (f'<p class="cal-note">Ещё {rest} {plural(rest, ("релиз", "релиза", "релизов"))} — '
                  f'<a href="{rel(current, "calendar/")}">в календаре на сегодня</a></p>')
    return (
        f'<section class="band wrap" id="today">'
        f'<div class="label dim">Сегодня вышло</div>'
        f'<h2 class="h2">{esc(heading)}</h2>'
        f'{inner}</section>'
    )


def editorial_block(contents, ratings, limit=3):
    """Блок 03: «Крупным планом». Название «После титров» закреплено за рейтингом."""
    scored = [item for item in contents if aggregate_rating(ratings.get(item["id"])) is not None]
    scored.sort(key=lambda item: (-aggregate_rating(ratings.get(item["id"])), item["title"]))
    rows = []
    for item in scored[:limit]:
        rows.append(
            f'<article class="closeup">'
            f'<div class="label dim">{esc(CONTENT_TYPES.get(item["content_type"], item["content_type"]))}</div>'
            f'<h3 class="closeup-title"><a href="{content_href(item, Path(""))}">{esc(item["title"])}</a></h3>'
            + after_credits(item, ratings, variant="compact")
            + '</article>'
        )
    body = "".join(rows) or '<p class="lead muted">Редакционные материалы готовятся.</p>'
    return (
        '<section class="band wrap" id="closeup">'
        + section_head("03", "Крупным планом", "Истории, за которые стоит остаться")
        + f'<div class="closeup-grid">{body}</div>'
        + '<p class="cal-note"><a href="journal/">Все материалы Журнала</a></p>'
        + '</section>'
    )


def home_page(contents, events, ratings, year, month, available=None, seasons=None):
    """Главная: hero, «Сегодня вышло», календарь, витрина, «Крупным планом».

    Календарь — первый полноценный блок после шапки и тикера: он показывает,
    что выходит, когда и за чем следить.
    """
    today = today_moscow()
    featured = popular_of_month(contents, events, year, month, limit=12)
    if len(featured) < 12:
        extra = sorted(
            (item for item in contents if item not in featured),
            key=lambda x: (x.get("popularity") or 0, x.get("vote") or 0),
            reverse=True,
        )
        featured = featured + extra[: 12 - len(featured)]
    cards = "".join(card(item, Path(""), ratings) for item in featured)
    showcase = (
        '<section class="band wrap" id="showcase">'
        + section_head("02", "Что смотрим сегодня", "На вашем экране")
        + f'<div class="grid-posters">{cards}</div></section>'
    )
    intro = (
        '<section class="band wrap intro">'
        '<h1 class="h2">Что смотреть: календарь выходов и премьеры месяца</h1>'
        '<p class="lead muted">Бесплатный навигатор по фильмам, сериалам и шоу. '
        'Что выходит сегодня, что будет дальше и за чем стоит следить.</p>'
        '</section>'
    )
    return page(
        "Что смотреть",
        hero_stage(contents, events, Path(""), today, year, month)
        + today_ticker(events, contents, Path(""), today)
        + showcase_home(contents, events, Path(""), today, year, month)
        + calendar_spotlight(events, contents, Path(""), today, seasons)
        + journal_block(contents, events, ratings, Path(""), today),
        Path(""),
        "Бесплатный навигатор по фильмам, сериалам и шоу: что выходит, когда и за чем стоит следить.",
    )


def write(relative, text):
    path = DOCS / relative / "index.html" if relative else DOCS / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    env_service.load_dotenv()  # одно место чтения .env для всей сборки
    contents, rejected = to_normalized()
    dropped = save_rejected(rejected)
    events = build_events(contents)
    apply_overrides(contents, events)
    build_today = today_moscow()
    compute_aired(contents, events, build_today)
    refresh_next_episode(contents, events, build_today)
    season_model = season_index(contents, events, build_today)
    save_normalized(contents, events, season_model)
    ratings = rating_map()
    if DOCS.exists(): shutil.rmtree(DOCS)
    DOCS.mkdir()
    # Ассеты — исходники. Сборка никогда не читает сгенерированный docs/.
    (DOCS / "titry.css").write_text(
        read_asset("titry.css", "body{font-family:system-ui;margin:0}")
        + "\n" + read_asset("site.css"),
        encoding="utf-8",
    )
    (DOCS / "site.js").write_text(read_asset("site.js"), encoding="utf-8")
    # Шрифты: файлы, а не подключение с CDN. Без этого копирования @font-face в
    # собранном docs/ ссылается на несуществующий путь, и сайт теряет Onest.
    fonts_src = ROOT / "assets" / "fonts"
    if fonts_src.exists():
        shutil.copytree(fonts_src, DOCS / "fonts")
    # favicon: SVG, чтобы не тащить бинарник и не ловить 404 в консоли.
    favicon = ROOT / "assets" / "favicon.svg"
    if favicon.exists():
        shutil.copy2(favicon, DOCS / "favicon.svg")
    home_today = today_moscow()
    home_months = {(home_today.year, home_today.month)}
    write(Path(""), home_page(contents, events, ratings, home_today.year, home_today.month, home_months, season_model))
    write(Path("catalog"), list_page(
        "Каталог",
        contents,
        Path("catalog"),
        ratings,
        f'Вся база Титров: {count_label(len(contents), ("проект", "проекта", "проектов"))}. '
        f'Фильтры по типу, жанру, стране, рейтингу и поиску.',
        filters=True,
    ))
    for route, content_type, title in (("movies", "movie", "Фильмы"), ("series", "series", "Сериалы"), ("shows", None, "Шоу"), ("anime", "anime", "Аниме")):
        items = [x for x in contents if x["content_type"] == content_type] if content_type else [x for x in contents if x["content_type"] not in {"movie", "series", "anime"}]
        write(Path(route), list_page(title, items, Path(route), ratings, f"{title} в базе Титров."))
    current = today_moscow()
    end_year = current.year + 1
    months = {(current.year, current.month)}
    months |= {
        (released.year, released.month)
        for event in events
        if (released := parse_local_date(event.get("release_date")))
        and (released.year == current.year or (released.year == end_year and released.month <= 3))
        and released >= date(current.year, current.month, 1)
    }
    for year, month in sorted(months):
        write(Path("calendar") / str(year) / str(month), calendar_page(year, month, events, contents, ratings, available_months=months))
    write(Path("calendar"), calendar_page(today_moscow().year, today_moscow().month, events, contents, ratings, Path("calendar"), months))
    write(Path("my-list"), my_list_page())
    write(Path("journal"), journal_page())
    write(Path("credits"), credits_page())
    for item in contents:
        write(detail_path(item), detail_page(item, ratings, season_model.get(item["id"])))
        # Редирект со старого адреса /content/<id>/, чтобы внешние ссылки не ломались.
        legacy = Path("content") / str(item["id"]).replace("tmdb:", "tmdb-")
        target = "/".join(detail_path(item).parts)
        write(legacy, redirect_page(item["title"], f"../../{target}/"))
    (DOCS / ".nojekyll").touch()
    print(f'Built {len(contents)} content pages and {len(events)} release events into {DOCS}')
    if dropped:
        print(f'ВНИМАНИЕ: {dropped} проектов не попали в каталог, подробности в data/rejected.json',
              file=sys.stderr)


def redirect_page(title, target):
    """Страница-перенаправление для старого адреса.

    Не заглушка: canonical указывает на актуальную страницу, поэтому
    поисковики не считают старую ссылку отдельным документом.
    """
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        f'<title>{esc(title)} — титры</title>'
        f'<link rel="canonical" href="{SITE_URL}/{target.lstrip("./")}">'
        f'<meta http-equiv="refresh" content="0; url={esc(target)}">'
        f'<meta name="robots" content="noindex, follow">'
        '</head><body>'
        f'<p>Проект переехал: <a href="{esc(target)}">{esc(title)}</a></p>'
        '</body></html>'
    )


CATALOG_JS = r'''(function () {
  "use strict";
  var grid = document.getElementById("grid");
  if (!grid) return;
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".card"));
  var empty = document.getElementById("empty");
  var found = document.getElementById("found");
  var typeChips = Array.prototype.slice.call(document.querySelectorAll("#type-chips .chip"));
  var genreChips = Array.prototype.slice.call(document.querySelectorAll("#genre-chips .chip"));
  var countryChips = Array.prototype.slice.call(document.querySelectorAll("#country-chips .chip"));
  var flagChips = Array.prototype.slice.call(document.querySelectorAll(".chip[data-flag]"));
  var sortButtons = Array.prototype.slice.call(document.querySelectorAll(".select[data-sort]"));
  var search = document.getElementById("q");
  var state = { type: "all", genre: "", country: "", query: "", rating8: false, newep: false, sort: "rating" };

  function press(list, active) {
    list.forEach(function (chip) { chip.setAttribute("aria-pressed", chip === active ? "true" : "false"); });
  }
  function value(card, key) { return card.dataset[key] || ""; }

  function matches(card) {
    if (state.type === "tv" && value(card, "kind") !== "tv") return false;
    if (state.type === "movie" && value(card, "kind") !== "movie") return false;
    if (state.type === "anime" && value(card, "anime") !== "1") return false;
    if (state.type === "animation" && value(card, "animation") !== "1") return false;
    if (state.genre && value(card, "genres").split(",").indexOf(state.genre) === -1) return false;
    if (state.country && value(card, "country") !== state.country) return false;
    if (state.rating8 && parseFloat(value(card, "vote") || 0) < 8) return false;
    if (state.newep && value(card, "newep") !== "1") return false;
    if (state.query) {
      var haystack = value(card, "title") + " " + value(card, "original");
      if (haystack.indexOf(state.query) === -1) return false;
    }
    return true;
  }

  function words(number) {
    var tail = number % 10, hundred = number % 100;
    if (tail === 1 && hundred !== 11) return "проект";
    if (tail >= 2 && tail <= 4 && (hundred < 12 || hundred > 14)) return "проекта";
    return "проектов";
  }

  function apply() {
    var shown = 0;
    cards.forEach(function (card) {
      var ok = matches(card);
      card.hidden = !ok;
      if (ok) shown += 1;
    });
    if (empty) empty.hidden = shown > 0;
    if (found) found.textContent = shown ? "Найдено " + shown + " " + words(shown) : "Ничего не найдено";
    grid.style.display = shown > 0 ? "" : "none";
  }

  function sort() {
    var key = state.sort;
    var sorted = cards.slice().sort(function (a, b) {
      if (key === "rating") return (parseFloat(value(b, "vote")) || 0) - (parseFloat(value(a, "vote")) || 0);
      if (key === "votes") return (parseInt(value(b, "votes"), 10) || 0) - (parseInt(value(a, "votes"), 10) || 0);
      if (key === "title") return value(a, "title").localeCompare(value(b, "title"), "ru");
      var left = value(a, "date") || "9999-99-99", right = value(b, "date") || "9999-99-99";
      return left < right ? -1 : left > right ? 1 : 0;
    });
    sorted.forEach(function (card) { grid.appendChild(card); });
  }

  typeChips.forEach(function (chip) {
    chip.addEventListener("click", function () { press(typeChips, chip); state.type = chip.dataset.type; apply(); });
  });
  genreChips.forEach(function (chip) {
    chip.addEventListener("click", function () { press(genreChips, chip); state.genre = chip.dataset.genre; apply(); });
  });
  countryChips.forEach(function (chip) {
    chip.addEventListener("click", function () { press(countryChips, chip); state.country = chip.dataset.country; apply(); });
  });
  flagChips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var on = chip.getAttribute("aria-pressed") === "true";
      chip.setAttribute("aria-pressed", on ? "false" : "true");
      if (chip.dataset.flag === "rating8") state.rating8 = !on;
      if (chip.dataset.flag === "new") state.newep = !on;
      apply();
    });
  });
  sortButtons.forEach(function (button) {
    button.addEventListener("click", function () { press(sortButtons, button); state.sort = button.dataset.sort; sort(); apply(); });
  });
  if (search) search.addEventListener("input", function () { state.query = search.value.trim().toLowerCase(); apply(); });

  var reset = document.getElementById("reset-btn");
  if (reset) reset.addEventListener("click", function () {
    state = { type: "all", genre: "", country: "", query: "", rating8: false, newep: false, sort: "rating" };
    if (search) search.value = "";
    press(typeChips, document.querySelector('#type-chips .chip[data-type="all"]'));
    press(genreChips, document.querySelector('#genre-chips .chip[data-genre=""]'));
    press(countryChips, document.querySelector('#country-chips .chip[data-country=""]'));
    press(sortButtons, document.querySelector('.select[data-sort="rating"]'));
    flagChips.forEach(function (chip) { chip.setAttribute("aria-pressed", "false"); });
    sort(); apply();
  });

  /* Параметры адреса: поиск и теги с первого экрана приходят как ?q=, ?type=, ?flag=. */
  var params = new URLSearchParams(location.search);
  var initial = params.get("q");
  if (initial && search) { search.value = initial; state.query = initial.trim().toLowerCase(); }
  var initialType = params.get("type");
  if (initialType) {
    var match = typeChips.filter(function (chip) { return chip.dataset.type === initialType; })[0];
    if (match) { press(typeChips, match); state.type = initialType; }
  }
  var initialFlag = params.get("flag");
  if (initialFlag) {
    var flag = flagChips.filter(function (chip) { return chip.dataset.flag === initialFlag; })[0];
    if (flag) {
      flag.setAttribute("aria-pressed", "true");
      if (initialFlag === "rating8") state.rating8 = true;
      if (initialFlag === "new") state.newep = true;
    }
  }
  var initialSort = params.get("sort");
  if (initialSort) {
    var sortChip = sortButtons.filter(function (button) { return button.dataset.sort === initialSort; })[0];
    if (sortChip) { press(sortButtons, sortChip); state.sort = initialSort; sort(); }
  }

  sort(); apply();
})();'''


def read_asset(name, fallback=""):
    """Читает ассет из assets/. Сборка никогда не берёт шаблоны из docs/."""
    path = ROOT / "assets" / name
    return path.read_text(encoding="utf-8") if path.exists() else fallback


if __name__ == "__main__": main()
