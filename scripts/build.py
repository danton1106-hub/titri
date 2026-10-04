#!/usr/bin/env python3
"""Canonical P0 production build: normalized JSON -> docs/ -> GitHub Pages.

Run this file directly. It is the only production build entry point.
"""
from __future__ import annotations

import html
import json
import posixpath
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

from time_service import parse_local_date, today_moscow

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
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


def slug(value):
    return str(value).replace("tmdb:", "tmdb-")


def to_normalized():
    catalog = load(DATA / "catalog.json", {"catalog": [], "upcoming": []})
    rows = catalog.get("catalog", []) + catalog.get("upcoming", [])
    result, seen = [], set()
    for row in rows:
        cid = content_id(row)
        if cid in seen:
            continue
        seen.add(cid)
        kind = row.get("kind", "tv")
        is_anime = bool(row.get("is_anime"))
        content_type = "anime" if is_anime else ("movie" if kind == "movie" else "series")
        result.append({
            "id": cid, "slug": row.get("slug") or slug(cid), "content_type": content_type,
            "title": row.get("title"), "original_title": row.get("original_title"),
            "overview": row.get("overview") or "", "country": row.get("country"),
            "original_language": row.get("language"), "year_start": row.get("year"),
            "status": row.get("status"), "poster": row.get("poster"), "backdrop": row.get("backdrop"),
            "genres": row.get("genres") or [], "genre_ids": row.get("genre_ids") or [],
            "vote": row.get("vote"), "vote_count": row.get("vote_count"),
            "release_date": row.get("release_date") or row.get("first_date"),
            "total_episodes": row.get("n_episodes") or row.get("total"),
            "aired_count": row.get("aired"), "next_episode": row.get("next_ep"),
            "last_episode": row.get("last_ep"), "network": row.get("network"),
            "homepage": row.get("homepage"), "external_ids": {"tmdb": row.get("id")},
        })
    return result


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
    return {
        "id": f'{cid}:{event_type}:{release_date}:{episode.get("season", "")}:{episode.get("ep", "")}:{region.lower()}',
        "content_id": cid, "season_id": None, "episode_id": None, "event_type": event_type,
        "release_date": release_date, "release_at": None, "release_timezone": None,
        "region": region, "country": country, "platform_id": None, "source_id": "tmdb", "source_url": None,
        "verification_status": "imported", "title": title, "season_number": episode.get("season"),
        "episode_number": episode.get("ep"), "episode_name": episode.get("name"),
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
            item["verification_status"] = "editorial"
        elif override.get("content_id") and override.get("release_date"):
            events.append({
                "id": override.get("id") or f'{override["content_id"]}:editorial:{override["release_date"]}',
                "content_id": override["content_id"], "season_id": override.get("season_id"),
                "episode_id": override.get("episode_id"), "event_type": override.get("event_type", "special"),
                "release_date": override["release_date"], "release_at": override.get("release_at"),
                "release_timezone": override.get("release_timezone"),
                "region": override.get("region") or "GLOBAL", "country": override.get("country"),
                "platform_id": override.get("platform_id"), "source_id": "editorial",
                "source_url": override.get("source_url"), "verification_status": "editorial",
                "title": override.get("title", ""), "season_number": override.get("season_number"),
                "episode_number": override.get("episode_number"), "episode_name": override.get("episode_name"),
            })


def save_normalized(contents, events):
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


def rating_map():
    result = {}
    for item in load(DATA / "editorial" / "ratings.json", {"items": []}).get("items", []):
        if item.get("status") == "published":
            result[item.get("content_id")] = item
    return result


def rel(current, target):
    current_dir = "/".join(current.parts)
    start = current_dir or "."
    result = posixpath.relpath(target or ".", start=start)
    if not result.endswith("/") and (not target or target.endswith("/")):
        result += "/"
    return result


def nav(current=Path("")):
    links = [("", "Главная"), ("calendar/", "Календарь"), ("movies/", "Фильмы"), ("series/", "Сериалы"), ("shows/", "Шоу"), ("catalog/", "Каталог"), ("journal/", "Журнал")]
    parts = [f'<a href="{rel(current, href)}">{name}</a>' for href, name in links]
    today = today_moscow()
    today_text = f"{today.day:02d} / {today.month:02d} / {today.year}"
    return f'''<header class="header"><a class="brand" href="{rel(current, '')}">[титры]</a>
<nav class="nav" aria-label="Основная навигация">{''.join(parts)}</nav>
<time class="today" data-current-date datetime="{today.isoformat()}">{today_text}</time>
<a class="bookmark-btn" href="{rel(current, 'my-list/')}">Мой список <span class="count" data-watch-count>0</span></a>
<button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-nav">Меню</button>
<nav id="mobile-nav" class="mobile-nav" aria-label="Мобильная навигация" hidden>{''.join(parts)}<a href="{rel(current, 'my-list/')}">Мой список</a></nav></header>'''


def footer(current=Path("")):
    return '''<footer class="footer"><div class="wrap"><div class="footer-top"><span class="footer-brand">[титры]</span><span class="footer-tagline">Кино заканчивается.<br>Интерес - нет.</span></div><div class="footer-legal"><span>Данные о фильмах и сериалах - TMDB. Расписание серий - TVMaze. Площадки для просмотра - JustWatch.</span><span>Каталог использует открыто доступные данные TMDB с обязательной атрибуцией источника.</span><span>This product uses the TMDB API but is not endorsed or certified by TMDB.</span></div></div></footer>'''


def page(title, body, current=Path(""), description=""):
    prefix = rel(current, "")
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} - титры</title><meta name="description" content="{esc(description)}"><link rel="stylesheet" href="{prefix}titry.css"><script defer src="{prefix}site.js"></script></head><body>{nav(current)}<main>{body}</main>{footer(current)}</body></html>'''


def content_href(item, current):
    return rel(current, f'content/{slug(item["id"])}/')


def status_label(status):
    return {"Returning Series": "Продолжается", "Ended": "Завершён", "Canceled": "Закрыт", "In Production": "В производстве", "Planned": "Анонсирован", "Released": "Вышел"}.get(status, status or "Статус не объявлен")


def progress(item):
    total, aired = item.get("total_episodes"), item.get("aired_count")
    word = EPISODE_WORD.get(item["content_type"], "выпуск")
    if total is None:
        return f'Вышло {aired or 0} {word}ов · количество пока не объявлено'
    if total > 16:
        return f'Вышло {aired or 0} из {total} {word}ов'
    return f'Вышло {aired or 0} из {total} {word}ов'


def after_credits(item, ratings):
    rating = ratings.get(item["id"])
    if not rating:
        return ""
    value = rating["rating"]
    status = "Остаёмся после титров" if value >= 9 else "Стоит досмотреть" if value >= 7 else "На один просмотр" if value >= 5 else "На перемотке" if value >= 3 else "Не доживает до титров"
    bars = "".join(f'<span class="credit-line {"on" if index <= value else ""}" style="--line:{55 + (index * 17) % 39}%"></span>' for index in range(1, 11))
    return f'''<section class="after-credits" aria-label="Рейтинг После титров: {value} из 10 строк"><div class="label dim">После титров</div><strong>{value}/10 строк</strong><span>{status}</span><div class="credit-lines">{bars}</div><p>{esc(rating.get("comment"))}</p></section>'''


def card(item, current, ratings):
    image = f'<img src="{esc(item.get("poster"))}" alt="{esc(item["title"])}" loading="lazy">' if item.get("poster") else ""
    rating = ratings.get(item["id"])
    badge = f'<span class="after-badge">После титров {rating["rating"]}</span>' if rating else ""
    return f'''<article class="card"><a href="{content_href(item, current)}"><div class="card-media">{image}{badge}</div><h2 class="card-title h3">{esc(item["title"])}</h2></a><div class="card-meta">{esc(CONTENT_TYPES.get(item["content_type"], item["content_type"]))} · {esc(item.get("year_start"))}</div><button class="card-mark" type="button" data-watch-id="{esc(item["id"])}" data-watch-type="{esc(item["content_type"])}" data-watch-title="{esc(item["title"])}" data-watch-url="{content_href(item, current)}" aria-label="Добавить в мой список">+</button></article>'''


def list_page(title, items, current, ratings, lead):
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
    content = f'''<section class="band wrap"><div class="label dim">Календарь релизов</div><h1 class="h2">{MONTHS[month - 1].capitalize()} {year}</h1><div class="calendar-nav">{previous_link}<a href="{rel(current, f'calendar/{today_moscow().year}/{today_moscow().month}/')}">Сегодня</a>{following_link}</div>{''.join(rows) or '<p class="lead muted">Подтверждённых релизов пока нет.</p>'}</section>'''
    return page("Календарь", content, current, "Календарь премьер, серий и выпусков")


def my_list_page():
    current = Path("my-list")
    body = '''<section class="band wrap"><div class="label dim">Мой список</div><h1 class="h2">Смотреть позже</h1><p class="lead muted">Список хранится в этом браузере.</p><div class="grid-posters" id="my-list-grid"></div><p class="lead muted" id="my-list-empty">В списке пока нет проектов.</p></section>'''
    return page("Мой список", body, current)


def journal_page():
    current = Path("journal")
    return page("Журнал", '<section class="band wrap"><div class="label dim">Журнал</div><h1 class="h2">Крупным планом</h1><p class="lead muted">Новости, разборы и подборки редакции Титров.</p></section>', current)


def detail_page(item, ratings):
    current = Path("content") / slug(item["id"])
    image = f'<img src="{esc(item.get("backdrop") or item.get("poster"))}" alt="{esc(item["title"])}">' if item.get("backdrop") or item.get("poster") else ""
    next_ep = item.get("next_episode") or {}
    next_text = f'Следующий {EPISODE_WORD.get(item["content_type"], "выпуск")}: {next_ep.get("ep", "")} · {next_ep.get("date", "дата не объявлена")}' if next_ep else ""
    body = f'''<section class="detail-hero"><div class="detail-media">{image}</div><div class="wrap detail-inner"><a class="back" href="{rel(current, 'catalog/')}">← Каталог</a><h1 class="h2 detail-title">{esc(item["title"])}</h1><p class="lead muted">{esc(CONTENT_TYPES.get(item["content_type"], item["content_type"]))} · {esc(status_label(item.get("status")))}</p><p class="lead">{esc(item.get("overview"))}</p><button class="btn btn-cream" type="button" data-watch-id="{esc(item["id"])}" data-watch-type="{esc(item["content_type"])}" data-watch-title="{esc(item["title"])}" data-watch-url="{rel(current, f'content/{slug(item["id"])}/')}">+ В мой список</button>{after_credits(item, ratings)}<section class="facts"><div><b>Выпуски</b><span>{esc(progress(item))}</span></div><div><b>Следующий релиз</b><span>{esc(next_text or 'Дата не объявлена')}</span></div></section></div></section>'''
    return page(item["title"], body, current, item.get("overview", "")[:160])


def write(relative, text):
    path = DOCS / relative / "index.html" if relative else DOCS / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    contents = to_normalized()
    events = build_events(contents)
    apply_overrides(contents, events)
    save_normalized(contents, events)
    ratings = rating_map()
    if DOCS.exists(): shutil.rmtree(DOCS)
    DOCS.mkdir()
    # Assets are source files. Never read a generated file from docs/ during a build.
    source_css = ROOT / "assets" / "titry.css"
    css = source_css.read_text(encoding="utf-8") if source_css.exists() else "body{font-family:system-ui;margin:0}"
    (DOCS / "titry.css").write_text(css + "\n" + CSS_P0, encoding="utf-8")
    (DOCS / "site.js").write_text(SITE_JS, encoding="utf-8")
    write(Path(""), list_page("Что посмотреть", contents[:24], Path(""), ratings, "Бесплатный навигатор по фильмам, сериалам и шоу."))
    write(Path("catalog"), list_page("Каталог", contents, Path("catalog"), ratings, "Вся база Титров."))
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
    for item in contents: write(Path("content") / slug(item["id"]), detail_page(item, ratings))
    (DOCS / ".nojekyll").touch()
    print(f'Built {len(contents)} content pages and {len(events)} release events into {DOCS}')


SITE_JS = r'''(function(){
var KEY='titri-watchlist-v2';
function list(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return[]}}
function save(v){localStorage.setItem(KEY,JSON.stringify(v))}
function update(){var v=list();document.querySelectorAll('[data-watch-count]').forEach(function(n){n.textContent=v.length});document.querySelectorAll('[data-watch-id]').forEach(function(b){var on=v.some(function(x){return x.content_id===b.dataset.watchId});b.classList.toggle('is-saved',on);b.setAttribute('aria-pressed',on);b.textContent=b.classList.contains('card-mark')?(on?'✓':'+'):(on?'✓ Добавлено':'+ В мой список')});var grid=document.getElementById('my-list-grid');if(grid){grid.innerHTML=v.map(function(x){return '<article class="card"><a href="'+x.url+'"><h2 class="card-title h3">'+x.title+'</h2></a><button class="card-mark" type="button" data-watch-id="'+x.content_id+'" data-watch-title="'+x.title+'">✓</button></article>'}).join('');document.getElementById('my-list-empty').hidden=!!v.length}}
document.addEventListener('click',function(e){var b=e.target.closest('[data-watch-id]');if(!b)return;e.preventDefault();var v=list(),id=b.dataset.watchId,i=v.findIndex(function(x){return x.content_id===id});if(i>=0)v.splice(i,1);else v.push({content_id:id,content_type:b.dataset.watchType||'content',added_at:new Date().toISOString(),title:b.dataset.watchTitle||'',url:b.dataset.watchUrl||location.href});save(v);update()});function refreshDate(){var parts=new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',year:'numeric'}).formatToParts(new Date());var v={};parts.forEach(function(p){if(p.type!=='literal')v[p.type]=p.value});document.querySelectorAll('[data-current-date]').forEach(function(n){n.textContent=v.day+' / '+v.month+' / '+v.year})}
function menu(){var t=document.querySelector('.menu-toggle'),n=document.getElementById('mobile-nav');if(!t||!n)return;function set(open){t.setAttribute('aria-expanded',String(open));n.hidden=!open}t.addEventListener('click',function(){set(t.getAttribute('aria-expanded')!=='true')});t.addEventListener('keydown',function(e){if(e.key==='Escape'){set(false);t.focus()}});n.addEventListener('keydown',function(e){if(e.key==='Escape'){set(false);t.focus()}})}
document.addEventListener('DOMContentLoaded',function(){update();refreshDate();menu()})})();'''

CSS_P0 = '''
.menu-toggle,.mobile-nav{display:none}.calendar-nav{display:flex;gap:18px;flex-wrap:wrap;margin:24px 0}.calendar-day{border-top:1px solid var(--line);padding:20px 0}.calendar-day h2{margin:0;font-size:22px}.calendar-day ul{padding-left:18px}.after-credits{margin:28px 0;padding:20px;border:1px solid var(--line);max-width:620px}.after-credits strong{display:block;font-size:30px}.after-credits span{color:var(--text-2)}.credit-lines{display:grid;gap:5px;margin:16px 0}.credit-line{height:5px;width:var(--line);background:var(--line)}.credit-line.on{background:var(--cream)}.after-badge{position:absolute;left:8px;bottom:8px;background:var(--bg-deep);padding:4px 7px;font-size:11px}.card{position:relative}.card-mark{position:absolute;right:8px;top:8px;z-index:2;width:32px;height:32px;border-radius:50%;border:1px solid var(--line);background:var(--bg-deep);color:var(--cream)}.card-mark.is-saved{background:var(--cream);color:var(--ink)}.facts{display:grid;gap:12px;margin:28px 0}.facts div{display:grid;gap:4px}.facts span{color:var(--text-2)}@media(max-width:720px){.nav{display:none}.menu-toggle{display:block;background:none;color:var(--text);border:1px solid var(--line);padding:7px}.mobile-nav[hidden]{display:none}.mobile-nav{display:grid;position:absolute;top:58px;left:0;right:0;background:var(--bg-deep);padding:20px;gap:14px}.header{position:sticky}.bookmark-btn{font-size:0}.bookmark-btn .count{font-size:11px}.grid-posters{grid-template-columns:repeat(2,minmax(0,1fr))}}
'''

if __name__ == "__main__": main()
