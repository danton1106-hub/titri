# -*- coding: utf-8 -*-
"""Сборка главной «титры». Референс: макет заказчика (desktop + mobile).

Счётчик недели в «В центре внимания» показывает реальные события
недели с понедельника по воскресенье:
  первое число  — сколько новых серий выходит на этой неделе
  второе число  — сколько премьер сериалов и фильмов на этой неделе
Счётчик пересчитывается при каждой сборке, то есть каждую неделю заново.
"""
import json, html, os
from datetime import date, datetime
from zoneinfo import ZoneInfo, datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "data", "home.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "preview")
TODAY = datetime.now(ZoneInfo("Europe/Moscow")).date()

MONTHS = ["января","февраля","марта","апреля","мая","июня",
          "июля","августа","сентября","октября","ноября","декабря"]
MONTHS_GEN = ["январь","февраль","март","апрель","май","июнь",
              "июль","август","сентябрь","октябрь","ноябрь","декабрь"]
WD = ["пн","вт","ср","чт","пт","сб","вс"]

# Жанры, которые не считаем кино и сериалами: новости, ток-шоу, реалити
NON_CINEMA = {10763, 10767, 10764, 10766, 10768}


def e(s): return html.escape(str(s if s is not None else ""))


def dt(iso):
    if not iso: return None
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def ru(iso, short=False):
    d = dt(iso)
    if not d: return "дата не объявлена"
    return f"{d.day:02d}.{d.month:02d}.{d.year}" if short else f"{d.day} {MONTHS[d.month-1]}"


def tail(iso):
    """«Завтра, 1 октября» / «Через 3 дня, 4 октября»"""
    d = dt(iso)
    if not d: return "дата не объявлена"
    delta = (d - TODAY).days
    if delta < 0:
        return f"{d.day} {MONTHS[d.month-1]}"
    when = ("сегодня" if delta == 0 else "завтра" if delta == 1 else
            "послезавтра" if delta == 2 else f"через {delta} дня")
    return f"{when.capitalize()}, {d.day} {MONTHS[d.month-1]}"


def n_eps(n, one, few, many):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11: return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14): return f"{n} {few}"
    return f"{n} {many}"


# ---------- неделя: понедельник — воскресенье ----------
def week_bounds(any_day=None):
    d = any_day or TODAY
    mon = d - timedelta(days=d.weekday())
    return mon, mon + timedelta(days=6)


def week_events():
    """Реальные события недели из каталога.

    Серии — по last_ep и next_ep, у которых дата попадает в текущую неделю.
    Премьеры — сериалы, у которых первая серия этой недели, и фильмы,
    у которых дата выхода на этой неделе.
    Ток-шоу, новости и реалити не считаем — это не кино.
    """
    cat_p = os.path.join(ROOT, "data", "catalog.json")
    mon, sun = week_bounds()
    empty = {"eps": 0, "premieres": 0, "mon": mon, "sun": sun,
             "films": 0, "new_shows": 0, "titles": []}
    if not os.path.exists(cat_p):
        return empty

    CAT = json.load(open(cat_p, encoding="utf-8"))
    w0, w1 = mon.isoformat(), sun.isoformat()
    rows = CAT["catalog"] + CAT["upcoming"]

    seen_ep, eps_titles = set(), []
    for r in rows:
        if r["kind"] != "tv":
            continue
        if set(r.get("genre_ids") or []) & NON_CINEMA:
            continue
        for key in ("last_ep", "next_ep"):
            ep = r.get(key)
            if not ep or not ep.get("date"):
                continue
            if not (w0 <= ep["date"] <= w1):
                continue
            mark = (r["id"], ep.get("season"), ep.get("ep"))
            if mark in seen_ep:
                continue
            seen_ep.add(mark)
            eps_titles.append(r["title"])

    # премьеры: сериал начался на этой неделе
    new_shows, film_prem = [], []
    for r in rows:
        if set(r.get("genre_ids") or []) & NON_CINEMA:
            continue
        d = r.get("release_date") or ""
        if not d:
            continue
        if r["kind"] == "tv" and w0 <= d <= w1:
            new_shows.append(r["title"])
        elif r["kind"] == "movie" and w0 <= d <= w1:
            film_prem.append(r["title"])

    return {
        "eps": len(seen_ep),
        "films": len(film_prem),
        "new_shows": len(new_shows),
        "premieres": len(film_prem) + len(new_shows),
        "mon": mon, "sun": sun,
        "titles": eps_titles,
    }


def week_label(mon, sun):
    """«29 сентября — 5 октября» или «28 сентября — 4 октября»"""
    if mon.month == sun.month:
        return f"{mon.day}–{sun.day} {MONTHS[sun.month-1]}"
    return f"{mon.day} {MONTHS[mon.month-1]} — {sun.day} {MONTHS[sun.month-1]}"


# ---------- иконки ----------
def icon(name, size=16, extra=""):
    p = {
        "bookmark": '<path d="M6 3.5h8a1.5 1.5 0 0 1 1.5 1.5v12.2a.5.5 0 0 1-.77.42L12 15.6l-2.73 1.82a.5.5 0 0 1-.77-.42V5A1.5 1.5 0 0 1 6 3.5Z"/>',
        "chevron": '<path d="m5 8 5 5 5-5"/>',
        "calendar": '<path d="M4 6.5h12v11H4z"/><path d="M4 10h12M8 4v4M12 4v4"/>',
        "clock": '<circle cx="10" cy="10" r="7"/><path d="M10 6v4.3l2.6 1.5"/>',
        "arrow-up": '<path d="M10 15V5m0 0L6 9m4-4 4 4"/>',
        "plus": '<path d="M10 5v10M5 10h10"/>',
        "search": '<circle cx="9" cy="9" r="5.5"/><path d="m13.2 13.2 3.3 3.3"/>',
    }[name]
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 20 20" fill="none" '
            f'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true"{extra}>{p}</svg>')


BOOKMARK_SOLID = ('<svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">'
                  '<path d="M6 3.5h8a1.5 1.5 0 0 1 1.5 1.5v12.2a.5.5 0 0 1-.77.42L12 15.6l-2.73 1.82a.5.5 0 0 1-.77-.42V5A1.5 1.5 0 0 1 6 3.5Z"/></svg>')

NAV = [("index.html", "Что посмотреть"), ("catalog.html", "Все фильмы и сериалы"),
       ("upcoming.html", "Скоро выходят"), ("journal.html", "Журнал")]


def header():
    links = ""
    for h, n in NAV:
        badge = '<em class="nav-year">2026</em>' if h == "catalog.html" else ""
        links += f'<a href="{h}">{badge}{e(n)}</a>'
    return f'''<header class="header">
  <a class="brand" href="index.html">[титры]</a>
  <nav class="nav">{links}</nav>
  <div class="head-right">
    <button class="bookmark-btn">{BOOKMARK_SOLID}Мой список</button>
    <span class="count" id="list-count">0</span>
  </div>
</header>'''


def section_head(no, kicker, title, right=None):
    r = f'<div class="lead muted" style="max-width:38ch">{e(right)}</div>' if right else ""
    return f'''<div class="section-head">
  <div>
    <div class="label dim">${e(no)} серий / ${e(kicker)} релизов на неделю</div>
    <h2 class="h2" style="margin-top:14px">{e(title)}</h2>
  </div>
</div>''
    <h2 class="h2" style="margin-top:14px">{e(title)}</h2>
  </div>
  {r}
</div>'''


def card(c):
    """Карточка для живого фильтра. Признаки фильтрации — в data-атрибутах."""
    kind = c["kind"]
    is_tv = kind == "tv"
    img = f'<img src="{e(c["poster"])}" alt="{e(c["title"])}" loading="lazy">' if c.get("poster") else ""
    rate = (f'<span class="badge-rate">{c["vote"]} <em>TMDB</em></span>'
            if c.get("vote") else '<span class="badge-rate">— <em>TMDB</em></span>')

    genre = (c.get("genres") or [""])[0] or ("Фильм" if not is_tv else "Сериал")
    type_word = "Фильм" if not is_tv else "Сериал"
    meta = f'{e(c["year"])} · {type_word} · {e(genre)}'

    if not is_tv:
        status = "В прокате" if (c.get("release_date") or "") <= D["today_date"] else f'Премьера {ru(c.get("release_date"))}'
        tag_html = f'<span class="card-tag"><span class="t">{e(status)}</span></span>'
        sort_date = c.get("release_date") or ""
    elif c.get("new_today"):
        tag_html = ('<span class="card-tag"><span class="dot"></span>'
                    '<span class="t">Новая серия сегодня</span></span>')
        sort_date = c["last_ep"]["date"]
    elif c.get("next_ep"):
        ne = c["next_ep"]
        tag_html = (f'<span class="card-tag"><span class="dot"></span>'
                    f'<span class="t">Новая серия {e(ru(ne["date"]))}</span></span>')
        sort_date = ne["date"]
    elif c.get("all_aired") and c.get("total"):
        tag_html = '<span class="card-tag"><span class="t">Весь сезон вышел</span></span>'
        sort_date = (c.get("last_ep") or {}).get("date") or ""
    else:
        tag_html = (f'<span class="card-tag"><span class="t muted">'
                    f'Вышло {c.get("aired", 0)} из {c.get("total", 0)}</span></span>')
        sort_date = ""

    flags = " ".join([
        f'data-kind="{kind}"',
        f'data-anime="{"1" if c.get("is_anime") else "0"}"',
        f'data-animation="{"1" if c.get("is_animation") else "0"}"',
        f'data-country="{e(c.get("country") or "")}"',
        f'data-vote="{c.get("vote") or 0}"',
        f'data-allaired="{"1" if c.get("all_aired") else "0"}"',
        f'data-new="{"1" if c.get("new_today") else "0"}"',
        f'data-genres="{",".join(str(g) for g in (c.get("genre_ids") or []))}"',
        f'data-date="{e(sort_date)}"',
        f'data-title="{e(c["title"])}"',
    ])

    return f'''<a class="card" href="#" {flags}>
  <div class="card-media">
    {img}
    {rate}
    <span class="card-mark" role="button" tabindex="0" aria-label="В мой список">{icon("bookmark", 14)}</span>
  </div>
  <div class="card-title h3">{e(c["title"])}</div>
  <div class="card-meta">{meta}</div>
  <div class="card-meta" style="margin-top:10px">{tag_html}</div>
</a>'''


# ================= ГЕРОЙ СО СЧЁТЧИКОМ НЕДЕЛИ =================
def build_hero():
    hero = D.get("hero") or {}
    bg = hero.get("backdrop") or hero.get("poster") or ""
    g = hero.get("genres") or []
    parts = [hero.get("year", "")]
    if g:
        parts.append(g[0])
    parts.append("18+")
    meta = " · ".join([p for p in parts if p])

    W = week_events()
    mon, sun = W["mon"], W["sun"]
    eps, prem = W["eps"], W["premieres"]

    # Счётчик: новые серии / премьеры на текущей неделе.
    # Обновляется каждую неделю — считается заново при каждой сборке.
    counter_left = f'{eps:02d}'
    counter_right = f'{prem:02d}'
    week_txt = week_label(mon, sun)

    total = hero.get("total") or 0
    if hero.get("all_aired"):
        status = f'Все {n_eps(total, "серия", "серии", "серий")} вышли'
    else:
        status = f'Вышло {hero.get("aired", 0)} из {total}'

    return f'''<section class="hero" id="top">
  <div class="hero-media"><img src="{e(bg)}" alt="{e(hero.get("title",""))}"></div>
  <div class="hero-inner wrap">
    <div class="hero-top">
      <span class="label dim">Кино и сериалы в одном месте</span>
      <span class="label dim">{mon.day:02d} / {mon.month:02d} / {mon.year}</span>
    </div>
    <div class="hero-cols">
      <div>
        <h1 class="hero-title">Что смотрим<br>сегодня?</h1>
        <p class="lead muted" style="margin-top:22px;max-width:44ch">
          Найдите своё кино. Оценки, даты выхода и&nbsp;новые серии — всё под рукой.
        </p>
        <div class="search">
          {icon("search", 18)}
          <input type="search" id="q" placeholder="Фильм, сериал или настроение" aria-label="Поиск по каталогу">
          <button class="btn btn-dark" id="q-go">Найти</button>
        </div>
        <div class="chips">
          <button class="chip" data-quick="tv" aria-pressed="false">Сериалы</button>
          <button class="chip" data-quick="movie" aria-pressed="false">Фильмы</button>
          <button class="chip" data-quick="anime" aria-pressed="false">Аниме</button>
          <button class="chip" data-quick="rating8" aria-pressed="false">Рейтинг 8+</button>
          <button class="chip" data-quick="allaired" aria-pressed="false">Весь сезон вышел</button>
        </div>
      </div>
      <div class="spotlight">
        <div class="spotlight-count">{counter_left} <small>/ {counter_right}</small></div>
        <div class="spotlight-week">
          <span class="label dim">{e(week_txt)}</span>
          <span class="sm muted">{n_eps(eps, "новая серия", "новые серии", "новых серий")}
            · {n_eps(W["new_shows"] + W["films"], "новый сериал или фильм", "новых сериала или фильма", "новых сериалов и фильмов")}</span>
        </div>
        <h2 class="h2">{e(hero.get("title",""))}</h2>
        <div class="meta">
          <span class="h3" style="font-size:20px">{e(hero.get("vote",""))}</span>
          <span class="label dim">TMDB</span>
          <span class="sm muted">{e(meta)}</span>
        </div>
        <div class="spotlight-cta">
          <span class="card-tag"><span class="dot"></span><span class="t">{e(status)}</span></span>
          <span style="display:flex;align-items:center;gap:14px">
            <button class="btn btn-cream">О сериале</button>
            <button class="plus" aria-label="Добавить в список">{icon("plus", 18)}</button>
          </span>
        </div>
      </div>
    </div>
  </div>
</section>'''


def build_ticker():
    """«Сегодня вышло» — из данных, а не из заглушки."""
    items = D.get("today") or []
    parts = []
    for t in items:
        if t["kind"] == "tv":
            txt = f'«{t["title"]}» · {t["season"]} сезон, {t["ep"]} серия'
        else:
            txt = f'«{t["title"]}»'
        parts.append(f'<span class="sm">{e(txt)}</span>')

    if parts:
        main = '<span class="ticker-sep">·</span>'.join(parts)
        left = f'<span class="label dim">Сегодня вышло</span>{main}{icon("calendar", 15)}'
    else:
        left = (f'<span class="label dim">Сегодня вышло</span>'
                f'<span class="sm muted">Ничего нового — самое время догнать пропущенное.</span>')

    return f'''<div class="ticker">
  <div class="ticker-main">{left}</div>
  <span class="sm dim">Хорошее кино продолжается.</span>
</div>'''


# ================= 01 / ЧТО ПОСМОТРЕТЬ =================
def active_genres():
    seen = {}
    for c in D["cards"]:
        for gid, gname in zip(c.get("genre_ids") or [], c.get("genres") or []):
            if gname and gid not in seen:
                seen[gid] = gname
    order = ["драма", "криминал", "комедия", "триллер", "фантастика",
             "боевик", "ужасы", "детектив", "мультфильм", "приключения"]
    items = sorted(seen.items(), key=lambda kv: (order.index(kv[1].lower())
                                                 if kv[1].lower() in order else 99))
    return items[:10]


def build_look():
    cards = "".join(card(c) for c in D["cards"] if card(c))
    gen_btns = "".join(
        f'<button class="chip" data-genre="{gid}" aria-pressed="false">{e(gname)}</button>'
        for gid, gname in active_genres())

    return f'''<section class="band wrap" id="look">
  {section_head("01", "Что посмотреть", "На вашем экране",
                "Истории, на которые стоит потратить вечер")}

  <div class="filter-row">
    <div class="chips" id="type-chips">
      <button class="chip" data-type="all" aria-pressed="true">Всё</button>
      <button class="chip" data-type="tv" aria-pressed="false">Сериалы</button>
      <button class="chip" data-type="movie" aria-pressed="false">Фильмы</button>
    </div>
    <div class="selects">
      <button class="select" id="sort-btn">Популярное {icon("chevron", 14)}</button>
      <button class="select" id="reset-btn">Сбросить</button>
    </div>
  </div>

  <div class="filter-row" style="margin-top:14px">
    <div class="chips" id="genre-chips">
      <button class="chip" data-genre="" aria-pressed="true">Все жанры</button>
      {gen_btns}
    </div>
  </div>

  <div class="grid-posters" id="grid">{cards}</div>

  <div class="empty" id="empty" hidden>
    <div class="h3">Пока ничего не нашлось</div>
    <div class="muted body" style="margin-bottom:20px">Попробуйте другой жанр или сбросьте фильтры.</div>
    <button class="btn btn-ghost" id="reset-btn-2">Сбросить фильтры</button>
  </div>
</section>'''


# ================= 02 / КАЛЕНДАРЬ =================
def build_calendar():
    mon, sun = week_bounds()
    week_days = [mon + timedelta(days=i) for i in range(7)]
    days_html = "".join(
        f'<button class="day" data-day="{cur.isoformat()}" '
        f'aria-pressed="{"true" if i == 0 else "false"}">'
        f'<b>{cur.day}</b><s>{e(WD[cur.weekday()])}</s></button>'
        for i, cur in enumerate(week_days))

    day_blocks = []
    for day in D.get("calendar", []):
        rows = []
        for it in day["items"]:
            thumb = (f'<img class="thumb" src="{e(it["poster"])}" alt="" loading="lazy">'
                     if it.get("poster") else '<span class="thumb"></span>')
            ep_title = it.get("ep_name") or f'Серия {it["ep"]}'
            rows.append(f'''<div class="cal-row">
  {thumb}
  <div class="txt">
    <b>{e(it["title"])}</b>
    <div class="sm" style="color:var(--ink-2);margin-top:2px">
      {e(it.get("network") or "")} · Сезон {it["season"]} · Серия {it["ep"]} {e(ep_title)}
    </div>
  </div>
  <button class="plus" aria-label="Подробнее" style="border-color:var(--line-ink);color:var(--ink)">{icon("plus", 16)}</button>
</div>''')
        first = day is D["calendar"][0]
        day_blocks.append(f'<div class="day-list" data-day-list="{day["date"]}"'
                          f'{" hidden" if not first else ""}>{"".join(rows)}</div>')

    if not day_blocks:
        day_blocks.append('<div class="cal-note">На этой неделе новых серий нет.</div>')

    nx = D.get("next_episode") or {}
    ne = nx.get("next_ep") or {}
    total = nx.get("total") or 0
    aired = nx.get("aired") or 0
    eps_html = "".join(
        f'<i class="{"now" if i == ne.get("ep") else ("done" if i <= aired else "")}">{i}</i>'
        for i in range(1, min(total, 20) + 1))
    ep_line = (f'Эпизод {ne.get("ep")}' if ne.get("ep") else "Следующая серия")
    when = tail(ne["date"]) if ne.get("date") else "дата не объявлена"
    net = (nx.get("network") or "")
    genre = (nx.get("genres") or [""])[0]

    return f'''<section class="calendar wrap" id="calendar">
  <div class="cal-card">
    <div class="cal-head">
      <div>
        <div class="label label-ink">02 / Календарь выхода</div>
        <h2 class="h2" style="margin-top:14px;color:var(--ink)">Не пропустите<br>продолжение.</h2>
      </div>
      <div style="text-align:right">
        <div class="body" style="color:var(--ink-2)">Когда новая серия?<br>Здесь всё по датам.</div>
        <button class="btn btn-dark" style="margin-top:14px">Весь октябрь {icon("calendar", 14)}</button>
      </div>
    </div>

    <div class="cal-cols">
      <div>
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <span class="sm" style="color:var(--ink-2)">{e(week_label(mon, sun))}</span>
          <span class="label label-ink">{sun.year}</span>
        </div>
        <div class="days">{days_html}</div>
        <div id="day-lists">{''.join(day_blocks)}</div>
      </div>

      <div>
        <div class="next-head">
          <span class="label label-ink">Следующая серия</span>
          {icon("clock", 16)}
        </div>
        <h3 class="h3 next-title" style="color:var(--ink)">{e(nx.get("title", ""))}</h3>
        <div class="sm" style="color:var(--ink-2);margin-top:8px">
          Сезон {nx.get("season", "")} · {e(net)} · {e(genre)}
        </div>

        <div class="next-bottom">
          <div>
            <div class="numeral">
              <b>{ne.get("ep", "—")}</b><span>/{total}</span>
            </div>
            <div class="sm" style="color:var(--ink-2);margin-top:8px">серий уже вышло</div>
          </div>
        </div>
        <div class="eps">{eps_html}</div>

        <div class="next-cta">
          <div>
            <div class="label label-ink">{e(ep_line)}</div>
            <div class="h3" style="color:var(--ink);font-size:19px;margin-top:6px">{e(when)}</div>
          </div>
          <button class="plus" aria-label="Добавить в список" style="background:var(--ink);color:var(--cream);border-color:var(--ink)">{icon("plus", 18)}</button>
        </div>
      </div>
    </div>
  </div>
</section>'''


# ================= 03 / КРУПНЫМ ПЛАНОМ =================
AFTER = [
    ("Разбор", "5 минут · Без спойлеров", "Как выбрать сериал на один вечер",
     "Рейтинг — только начало. На что ещё смотреть, чтобы найти свою историю."),
    ("Гид", "3 минуты · Полезное", "Смотреть сразу или ждать весь сезон?",
     "Разбираемся в графиках выхода и выбираем удобный ритм просмотра."),
    ("Детали", "4 минуты · Без спойлеров", "Почему стоит досмотреть до конца титров",
     "Посвящения, музыка и сцены после финала — ещё одна часть большого кино."),
]


def build_after():
    backdrops = [c for c in D["cards"] if c.get("backdrop")]
    tiles = []
    for i, (kicker, meta, title, text) in enumerate(AFTER):
        bd = backdrops[i % len(backdrops)]["backdrop"] if backdrops else ""
        tiles.append(f'''<a class="still" href="#">
  <div class="still-media">
    <img src="{e(bd)}" alt="" loading="lazy">
    <span class="still-chip">{e(kicker)}</span>
  </div>
  <div class="meta label dim" style="margin-top:16px">{e(meta)}</div>
  <h3 class="h3" style="margin-top:10px">{e(title)}</h3>
  <p style="margin-top:10px;color:var(--text-2)">{e(text)}</p>
</a>''')
    return f'''<section class="band wrap" id="after">
  {section_head("03", "Крупным планом", "После титров",
                "Детали, которые делают историю интереснее")}
  <div class="grid-stills">{''.join(tiles)}</div>
</section>'''


# ================= ПОДВАЛ =================
def build_footer():
    return f'''<footer class="footer">
  <div class="wrap">
    <div class="footer-top">
      <span class="footer-brand">[титры]</span>
      <span class="footer-tagline">Кино заканчивается.<br>Интерес — нет.</span>
      <a class="up" href="#top">Наверх <span class="ring">{icon("arrow-up", 18)}</span></a>
    </div>
    <div class="footer-legal">
      <span>Бесплатный навигатор по кино и сериалам</span>
      <span>© [титры] 2026</span>
    </div>
    <div class="footer-legal" style="border-top:0;padding-top:8px;margin-top:8px;font-size:12.5px">
      <span>Данные — TMDB. Расписание — TVMaze. Площадки — JustWatch.</span>
      <span>This product uses the TMDB API but is not endorsed or certified by TMDB.</span>
    </div>
  </div>
</footer>'''


# ================= ЖИВОЙ ФИЛЬТР =================
SCRIPT = '''<script>
(function () {
  var grid = document.getElementById('grid');
  var empty = document.getElementById('empty');
  if (!grid) return;
  var cards = [].slice.call(grid.querySelectorAll('.card'));
  var typeChips = [].slice.call(document.querySelectorAll('#type-chips .chip'));
  var genreChips = [].slice.call(document.querySelectorAll('#genre-chips .chip'));
  var quickChips = [].slice.call(document.querySelectorAll('.chips .chip[data-quick]'));
  var state = { type: 'all', genre: '', q: '', anime: false, rating8: false, allaired: false };

  function setPressed(list, active) {
    list.forEach(function (c) { c.setAttribute('aria-pressed', c === active ? 'true' : 'false'); });
  }
  function toggle(chip) {
    var on = chip.getAttribute('aria-pressed') === 'true';
    chip.setAttribute('aria-pressed', on ? 'false' : 'true');
    return !on;
  }
  function apply() {
    var shown = 0, q = state.q.trim().toLowerCase();
    cards.forEach(function (c) {
      var ok = true;
      if (state.type !== 'all' && c.dataset.kind !== state.type) ok = false;
      if (ok && state.anime && c.dataset.anime !== '1') ok = false;
      if (ok && state.rating8 && parseFloat(c.dataset.vote) < 8) ok = false;
      if (ok && state.allaired && c.dataset.allaired !== '1') ok = false;
      if (ok && state.genre && (c.dataset.genres || '').split(',').indexOf(state.genre) === -1) ok = false;
      if (ok && q && c.dataset.title.toLowerCase().indexOf(q) === -1) ok = false;
      c.hidden = !ok;
      if (ok) shown++;
    });
    if (empty) empty.hidden = shown > 0;
    grid.style.display = shown > 0 ? '' : 'none';
  }

  typeChips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      setPressed(typeChips, chip); state.type = chip.dataset.type; apply();
    });
  });
  genreChips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      setPressed(genreChips, chip); state.genre = chip.dataset.genre; apply();
    });
  });
  quickChips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      var on = toggle(chip), k = chip.dataset.quick;
      if (k === 'anime') state.anime = on;
      if (k === 'rating8') state.rating8 = on;
      if (k === 'allaired') state.allaired = on;
      if (k === 'tv' || k === 'movie') {
        var target = document.querySelector('#type-chips .chip[data-type="' + k + '"]');
        quickChips.forEach(function (o) {
          if (o !== chip && (o.dataset.quick === 'tv' || o.dataset.quick === 'movie'))
            o.setAttribute('aria-pressed', 'false');
        });
        setPressed(typeChips, on ? target : document.querySelector('#type-chips .chip[data-type="all"]'));
        state.type = on ? k : 'all';
      }
      apply();
    });
  });

  var input = document.getElementById('q');
  if (input) input.addEventListener('input', function () { state.q = input.value; apply(); });
  var go = document.getElementById('q-go');
  if (go) go.addEventListener('click', function () {
    state.q = input.value; apply();
    document.getElementById('look').scrollIntoView({ behavior: 'smooth' });
  });

  function reset() {
    state = { type: 'all', genre: '', q: '', anime: false, rating8: false, allaired: false };
    if (input) input.value = '';
    setPressed(typeChips, document.querySelector('#type-chips .chip[data-type="all"]'));
    setPressed(genreChips, document.querySelector('#genre-chips .chip[data-genre=""]'));
    quickChips.forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
    apply();
  }
  var r1 = document.getElementById('reset-btn'), r2 = document.getElementById('reset-btn-2');
  if (r1) r1.addEventListener('click', reset);
  if (r2) r2.addEventListener('click', reset);

  var days = [].slice.call(document.querySelectorAll('.day'));
  days.forEach(function (b) {
    b.addEventListener('click', function () {
      setPressed(days, b);
      var d = b.dataset.day;
      [].slice.call(document.querySelectorAll('[data-day-list]')).forEach(function (blk) {
        blk.hidden = blk.dataset.dayList !== d;
      });
    });
  });

  var count = document.getElementById('list-count'), n = 0;
  document.querySelectorAll('.card-mark').forEach(function (m) {
    m.addEventListener('click', function (ev) {
      ev.preventDefault();
      var on = m.dataset.on === '1';
      m.dataset.on = on ? '0' : '1';
      m.style.color = on ? '' : 'var(--ink)';
      m.style.background = on ? '' : 'var(--cream)';
      n += on ? -1 : 1;
      if (count) count.textContent = n;
    });
  });
})();
</script>'''


if __name__ == "__main__":
    body = (header() + build_hero() + build_ticker() + build_look()
            + build_calendar() + build_after() + build_footer())
    page = f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>титры — найдётся ваше кино</title>
<link rel="stylesheet" href="titry.css">
</head>
<body>
{body}
{SCRIPT}
</body>
</html>'''
    p = os.path.join(OUT, "home.html")
    open(p, "w", encoding="utf-8").write(page)
    W = week_events()
    print(f"home.html {os.path.getsize(p)} байт | карточек {len(D['cards'])}")
    print(f"неделя {W['mon']} — {W['sun']}: серий {W['eps']}, премьер {W['premieres']} "
          f"(сериалов {W['new_shows']}, фильмов {W['films']})")
