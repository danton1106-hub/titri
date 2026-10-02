# -*- coding: utf-8 -*-
"""Сборка страниц «титры»: главная, каталог 2026, «скоро выходят», карточки проектов.

В интерфейсе нет пометок о демонстрации или шаблонности.
Чего нет в источнике — то «данные не объявлены», а не выдумано.
"""
import html, json, os, re, shutil
from datetime import date, datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREV = os.path.join(ROOT, "preview")
SITE = ROOT
D = json.load(open(os.path.join(ROOT, "data", "home.json"), encoding="utf-8"))
CAT = json.load(open(os.path.join(ROOT, "data", "catalog.json"), encoding="utf-8"))
# Рейтинги IMDb / Томаты / Metacritic — собраны заранее скриптом fetch_ratings.py.
# Ключ OMDb живёт в .env и в браузер не попадает: сюда приходят готовые числа.
RATINGS_P = os.path.join(ROOT, "data", "ratings.json")
RATINGS = json.load(open(RATINGS_P, encoding="utf-8")) if os.path.exists(RATINGS_P) else {}


def omdb_of(r):
    return RATINGS.get(r.get("imdb_id") or "") or {}
TODAY = datetime.now(ZoneInfo("Europe/Moscow")).date()
PREFIX = ""   # переопределяется перед сборкой карточек проектов

MONTHS = ["января","февраля","марта","апреля","мая","июня",
          "июля","августа","сентября","октября","ноября","декабря"]
WD = ["пн","вт","ср","чт","пт","сб","вс"]
COUNTRIES = {"US":"США","JP":"Япония","GB":"Великобритания","KR":"Южная Корея","FR":"Франция",
             "MX":"Мексика","CN":"Китай","CA":"Канада","TH":"Таиланд","HK":"Гонконг",
             "ZA":"ЮАР","BR":"Бразилия","DE":"Германия","ES":"Испания","IT":"Италия",
             "AU":"Австралия","IN":"Индия","RU":"Россия","SE":"Швеция","DK":"Дания",
             "NO":"Норвегия","PL":"Польша","TR":"Турция","NL":"Нидерланды"}
LANGS = {"en":"английский","ja":"японский","ko":"корейский","ru":"русский","fr":"французский",
         "es":"испанский","de":"немецкий","zh":"китайский","it":"итальянский","th":"тайский"}

# --- иероглифы и «нет букв»: чистим названия ---
CJK = re.compile(r'[\u2e80-\u9fff\u3040-\u30ff\uac00-\ud7af]')
HAS_LETTERS = re.compile(r'[A-Za-zА-Яа-яЁё]')


def clean_title(t, fallback=""):
    """Название для показа.

    В TMDB у части зарубежных проектов русского названия нет — возвращаются
    иероглифы или арабица. Показывать такое русскому читателю нельзя,
    выдумывать перевод — тем более. Поэтому: если букв нет, берём оригинальное
    название на латинице, а если и его нет — проект не показываем.
    """
    t = (t or "").strip()
    if CJK.search(t):
        t = CJK.sub(" ", t)
        t = re.sub(r"\s{2,}", " ", t).strip(" -–—:")
    if not HAS_LETTERS.search(t):
        fb = (fallback or "").strip()
        if HAS_LETTERS.search(fb):
            return fb
        return None
    return t


def e(s):
    return html.escape(str(s if s is not None else ""))


def dt(iso):
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def ru(iso):
    d = dt(iso)
    return f"{d.day} {MONTHS[d.month-1]} {d.year}" if d else "дата не объявлена"


def ru_short(iso):
    d = dt(iso)
    return f"{d.day:02d}.{d.month:02d}.{d.year}" if d else "—"


def month_tag(iso):
    d = dt(iso)
    return f"{MONTHS[d.month-1]} {d.year}" if d else "дата не объявлена"


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11: return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14): return f"{n} {few}"
    return f"{n} {many}"


# ---------- иконки ----------
ICONS = {
    "bookmark": '<path d="M6 3.5h8a1.5 1.5 0 0 1 1.5 1.5v12.2a.5.5 0 0 1-.77.42L12 15.6l-2.73 1.82a.5.5 0 0 1-.77-.42V5A1.5 1.5 0 0 1 6 3.5Z"/>',
    "chevron": '<path d="m5 8 5 5 5-5"/>',
    "chevron-down": '<path d="m5 8 5 5 5-5"/>',
    "calendar": '<path d="M4 6.5h12v11H4z"/><path d="M4 10h12M8 4v4M12 4v4"/>',
    "clock": '<circle cx="10" cy="10" r="7"/><path d="M10 6v4.3l2.6 1.5"/>',
    "arrow-up": '<path d="M10 15V5m0 0L6 9m4-4 4 4"/>',
    "arrow-left": '<path d="M15 10H5m0 0 4-4m-4 4 4 4"/>',
    "plus": '<path d="M10 5v10M5 10h10"/>',
    "search": '<circle cx="9" cy="9" r="5.5"/><path d="m13.2 13.2 3.3 3.3"/>',
    "star": '<path d="m10 3 2.1 4.3 4.7.7-3.4 3.3.8 4.7-4.2-2.2-4.2 2.2.8-4.7L3.2 8l4.7-.7z"/>',
}

def icon(name, size=16, extra=""):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 20 20" fill="none" '
            f'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true"{extra}>{ICONS[name]}</svg>')

BOOKMARK_SOLID = ('<svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">'
                  '<path d="M6 3.5h8a1.5 1.5 0 0 1 1.5 1.5v12.2a.5.5 0 0 1-.77.42L12 15.6l-2.73 1.82a.5.5 0 0 1-.77-.42V5A1.5 1.5 0 0 1 6 3.5Z"/></svg>')


# ---------- каркас ----------
NAV = [("", "Что посмотреть"), ("catalog.html", "Все фильмы и сериалы"),
       ("upcoming.html", "Скоро выходят"), ("journal.html", "Журнал")]


def header(cur=""):
    links = []
    for href, name in NAV:
        cls = ' class="on"' if href == cur else ""
        badge = ""
        if href == "catalog.html":
            badge = '<em class="nav-year">2026</em>'
        links.append(f'<a href="{PREFIX}{href}"{cls}>{badge}{e(name)}</a>')
    return f'''<header class="header">
  <a class="brand" href="{PREFIX}index.html">[титры]</a>
  <nav class="nav">{"".join(links)}</nav>
  <div class="head-right">
    <button class="bookmark-btn">{BOOKMARK_SOLID}Мой список</button>
    <span class="count" id="list-count">0</span>
  </div>
</header>'''


def footer():
    return f'''<footer class="footer">
  <div class="wrap">
    <div class="footer-top">
      <span class="footer-brand">[титры]</span>
      <span class="footer-tagline">Кино заканчивается.<br>Интерес — нет.</span>
      <a class="up" href="#" onclick="scrollTo({{top:0,behavior:'smooth'}});return false">Наверх <span class="ring">{icon("arrow-up", 18)}</span></a>
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


def head(title, desc="", extra="", prefix=""):
    return f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="stylesheet" href="{PREFIX}titry.css">
{extra}
</head>'''


# ---------- рейтинги ----------
def rating_block(r):
    """Рейтинги со всех доступных источников.

    TMDB — напрямую. IMDb, Томаты (критики) и Metacritic — из OMDb.
    Кинопоиск и зрительский Popcornmeter недоступны легально, поэтому
    показываются прочерком с пояснением. Ничего не выдумываем.
    """
    R = r.get("ratings") or {}
    O = omdb_of(r)

    tmdb = R.get("tmdb")
    cnt = R.get("tmdb_count") or 0
    imdb = O.get("imdb")
    imdb_votes = O.get("imdb_votes")
    rt = O.get("rt_critics")
    mc = O.get("metacritic")
    rt_aud = O.get("rt_audience") or R.get("rt_audience")
    kp = R.get("kinopoisk")

    def cell(label, value, sub="", why=None):
        if value in (None, "", 0):
            return (f'<div class="score unavail"><span class="score-label">{e(label)}</span>'
                    f'<span class="score-value">—</span>'
                    f'<span class="score-sub">{e(why or "нет данных")}</span></div>')
        return (f'<div class="score"><span class="score-label">{e(label)}</span>'
                f'<span class="score-value">{e(value)}</span>'
                f'<span class="score-sub">{e(sub)}</span></div>')

    # у IMDb в OMDb число голосов строкой «3,235,958»
    votes_txt = ""
    if imdb_votes:
        votes_txt = f"{imdb_votes} оценок"

    return f'''<div class="scores">
  {cell("TMDB", tmdb, plural(cnt, "голос", "голоса", "голосов") if cnt else "")}
  {cell("IMDb", imdb, votes_txt)}
  {cell("Томаты · критики", rt, "%" if rt else "")}
  {cell("Metacritic", mc, "из 100" if mc else "")}
  {cell("Томаты · зрители", rt_aud, "%" if rt_aud else "",
        why="публичного доступа нет" if not rt_aud else None)}
  {cell("Кинопоиск", kp, "", why="только по договору" if not kp else None)}
</div>'''


# ---------- карточка для сеток ----------
def card_html(r, ctx="catalog"):
    title = clean_title(r["title"], r.get("original_title"))
    if not title:
        return ""
    img = f'<img src="{e(r["poster"])}" alt="{e(title)}" loading="lazy">' if r.get("poster") else ""
    vote = r.get("vote") or 0
    rate = (f'<span class="badge-rate">{vote} <em>TMDB</em></span>' if vote
            else '<span class="badge-rate">— <em>TMDB</em></span>')

    typ = "Сериал" if r["kind"] == "tv" else "Фильм"
    genre = (r.get("genres") or [""])[0] or typ
    year = r.get("year") or ""

    if ctx == "upcoming":
        date_txt = r.get("release_date") or ""
        if r["kind"] == "tv" and r.get("next_ep"):
            date_txt = r["next_ep"].get("date") or date_txt
        meta = f'{ru(date_txt)} · {typ}'
        tag = f'<span class="card-tag"><span class="dot"></span><span class="t">{e(month_tag(date_txt))}</span></span>'
    else:
        meta = f'{year} · {typ} · {e(genre)}'
        if r.get("new_ep_today"):
            tag = '<span class="card-tag"><span class="dot"></span><span class="t">Новая серия сегодня</span></span>'
        elif r.get("next_ep"):
            tag = (f'<span class="card-tag"><span class="dot"></span><span class="t">'
                   f'Новая серия {e(ru(r["next_ep"].get("date")))}</span></span>')
        elif r["kind"] == "tv" and r.get("status") == "Ended":
            tag = '<span class="card-tag"><span class="t">Сериал завершён</span></span>'
        elif r["kind"] == "movie":
            tag = '<span class="card-tag"><span class="t">В прокате</span></span>'
        else:
            tag = f'<span class="card-tag"><span class="t muted">{e(r.get("status") or "Выходит")}</span></span>'

    flags = " ".join([
        f'data-kind="{r["kind"]}"',
        f'data-anime="{"1" if r.get("is_anime") else "0"}"',
        f'data-animation="{"1" if r.get("is_animation") else "0"}"',
        f'data-country="{e(r.get("country") or "")}"',
        f'data-lang="{e(r.get("language") or "")}"',
        f'data-vote="{vote}"',
        f'data-votes="{r.get("vote_count") or 0}"',
        f'data-year="{e(year)}"',
        f'data-date="{e(r.get("release_date") or "")}"',
        f'data-genres="{",".join(str(g) for g in (r.get("genre_ids") or []))}"',
        f'data-title="{e(title.lower())}"',
    ])

    return f'''<a class="card" href="{PREFIX}{r["kind"]}/{e(r["slug"])}.html" {flags}>
  <div class="card-media">
    {img}
    {rate}
    <span class="card-mark" role="button" tabindex="0" aria-label="В мой список">{icon("bookmark", 14)}</span>
  </div>
  <div class="card-title h3">{e(title)}</div>
  <div class="card-meta">{meta}</div>
  <div class="card-meta" style="margin-top:10px">{tag}</div>
</a>'''


# ---------- фильтры ----------
def filter_bar(genres, countries, kinds=True, sort_label="По рейтингу"):
    gchips = "".join(
        f'<button class="chip" data-genre="{gid}" aria-pressed="false">{e(gname)}</button>'
        for gid, gname in genres)
    cchips = "".join(
        f'<button class="chip" data-country="{code}" aria-pressed="false">{e(COUNTRIES.get(code, code))}</button>'
        for code in countries)
    type_chips = ""
    if kinds:
        type_chips = '''<div class="chips" id="type-chips">
      <button class="chip" data-type="all" aria-pressed="true">Всё</button>
      <button class="chip" data-type="tv" aria-pressed="false">Сериалы</button>
      <button class="chip" data-type="movie" aria-pressed="false">Фильмы</button>
      <button class="chip" data-type="anime" aria-pressed="false">Аниме</button>
      <button class="chip" data-type="animation" aria-pressed="false">Мультфильмы</button>
    </div>'''
    return f'''<div class="filters">
  <div class="filter-row">
    {type_chips}
    <div class="selects">
      <button class="select" data-sort="rating" aria-pressed="true">{e(sort_label)} {icon("chevron", 14)}</button>
      <button class="select" data-sort="date" aria-pressed="false">По дате {icon("chevron", 14)}</button>
      <button class="select" data-sort="votes" aria-pressed="false">По голосам {icon("chevron", 14)}</button>
      <button class="select" id="reset-btn">Сбросить</button>
    </div>
  </div>
  <div class="filter-row" style="margin-top:12px">
    <div class="chips" id="genre-chips">
      <button class="chip" data-genre="" aria-pressed="true">Все жанры</button>
      {gchips}
    </div>
  </div>
  <div class="filter-row" style="margin-top:12px">
    <div class="chips" id="country-chips">
      <button class="chip" data-country="" aria-pressed="true">Все страны</button>
      {cchips}
    </div>
  </div>
  <div class="filter-row" style="margin-top:12px">
    <div class="chips">
      <button class="chip" data-flag="rating8" aria-pressed="false">Рейтинг 8+</button>
      <button class="chip" data-flag="new" aria-pressed="false">Новые серии</button>
      <label class="search search-slim">
        {icon("search", 16)}
        <input type="search" id="q" placeholder="Поиск по названию" aria-label="Поиск">
      </label>
    </div>
  </div>
  <div class="filter-status"><span id="found"></span></div>
</div>'''


FILTER_JS = '''<script>
(function () {
  var grid = document.getElementById('grid');
  if (!grid) return;
  var cards = [].slice.call(grid.querySelectorAll('.card'));
  var empty = document.getElementById('empty');
  var found = document.getElementById('found');
  var typeChips = [].slice.call(document.querySelectorAll('#type-chips .chip'));
  var genreChips = [].slice.call(document.querySelectorAll('#genre-chips .chip'));
  var countryChips = [].slice.call(document.querySelectorAll('#country-chips .chip'));
  var flagChips = [].slice.call(document.querySelectorAll('.chip[data-flag]'));
  var sortBtns = [].slice.call(document.querySelectorAll('.select[data-sort]'));
  var st = { type: 'all', genre: '', country: '', q: '', r8: false, newep: false, sort: 'rating' };

  function press(list, active) {
    list.forEach(function (c) { c.setAttribute('aria-pressed', c === active ? 'true' : 'false'); });
  }
  function val(card, k) { return card.dataset[k] || ''; }

  function match(c) {
    if (st.type === 'tv' && val(c, 'kind') !== 'tv') return false;
    if (st.type === 'movie' && val(c, 'kind') !== 'movie') return false;
    if (st.type === 'anime' && val(c, 'anime') !== '1') return false;
    if (st.type === 'animation' && val(c, 'animation') !== '1') return false;
    if (st.genre && val(c, 'genres').split(',').indexOf(st.genre) === -1) return false;
    if (st.country && val(c, 'country') !== st.country) return false;
    if (st.r8 && parseFloat(val(c, 'vote')) < 8) return false;
    if (st.newep && val(c, 'newep') !== '1') return false;
    if (st.q && val(c, 'title').indexOf(st.q) === -1) return false;
    return true;
  }
  function apply() {
    var shown = 0;
    cards.forEach(function (c) { var ok = match(c); c.hidden = !ok; if (ok) shown++; });
    if (empty) empty.hidden = shown > 0;
    if (found) found.textContent = shown
      ? 'Найдено ' + shown + ' ' + plural(shown)
      : 'Ничего не найдено';
    grid.style.display = shown > 0 ? '' : 'none';
  }
  function plural(n) {
    var a = n % 10, b = n % 100;
    if (a === 1 && b !== 11) return 'проект';
    if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return 'проекта';
    return 'проектов';
  }
  function sort() {
    var key = st.sort;
    var arr = cards.slice().sort(function (a, b) {
      if (key === 'rating') return (parseFloat(val(b,'vote'))||0) - (parseFloat(val(a,'vote'))||0);
      if (key === 'votes') return (parseInt(val(b,'votes'))||0) - (parseInt(val(a,'votes'))||0);
      var da = val(a,'date') || '9999', db = val(b,'date') || '9999';
      return da < db ? -1 : da > db ? 1 : 0;
    });
    arr.forEach(function (c) { grid.appendChild(c); });
  }

  typeChips.forEach(function (ch) {
    ch.addEventListener('click', function () { press(typeChips, ch); st.type = ch.dataset.type; apply(); });
  });
  genreChips.forEach(function (ch) {
    ch.addEventListener('click', function () { press(genreChips, ch); st.genre = ch.dataset.genre; apply(); });
  });
  countryChips.forEach(function (ch) {
    ch.addEventListener('click', function () { press(countryChips, ch); st.country = ch.dataset.country; apply(); });
  });
  flagChips.forEach(function (ch) {
    ch.addEventListener('click', function () {
      var on = ch.getAttribute('aria-pressed') === 'true';
      ch.setAttribute('aria-pressed', on ? 'false' : 'true');
      if (ch.dataset.flag === 'rating8') st.r8 = !on;
      if (ch.dataset.flag === 'new') st.newep = !on;
      apply();
    });
  });
  sortBtns.forEach(function (b) {
    b.addEventListener('click', function () { press(sortBtns, b); st.sort = b.dataset.sort; sort(); apply(); });
  });
  var q = document.getElementById('q');
  if (q) q.addEventListener('input', function () { st.q = q.value.trim().toLowerCase(); apply(); });
  var rst = document.getElementById('reset-btn');
  if (rst) rst.addEventListener('click', function () {
    st = { type:'all', genre:'', country:'', q:'', r8:false, newep:false, sort:'rating' };
    if (q) q.value = '';
    press(typeChips, document.querySelector('#type-chips .chip[data-type="all"]'));
    press(genreChips, document.querySelector('#genre-chips .chip[data-genre=""]'));
    press(countryChips, document.querySelector('#country-chips .chip[data-country=""]'));
    press(sortBtns, document.querySelector('.select[data-sort="rating"]'));
    flagChips.forEach(function (c) { c.setAttribute('aria-pressed','false'); });
    sort(); apply();
  });
  sort(); apply();
})();
</script>'''

LIST_JS = '''<script>
(function () {
  var count = document.getElementById('list-count');
  var n = 0;
  document.querySelectorAll('.card-mark').forEach(function (m) {
    m.addEventListener('click', function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      var on = m.dataset.on === '1';
      m.dataset.on = on ? '0' : '1';
      m.style.background = on ? '' : 'var(--cream)';
      m.style.color = on ? '' : 'var(--ink)';
      n += on ? -1 : 1;
      count.textContent = n;
    });
  });
})();
</script>'''


# ---------- страницы ----------
def build_catalog():
    rows = [r for r in CAT["catalog"] if clean_title(r["title"], r.get("original_title"))]
    cards = "".join(card_html(r, "catalog") for r in rows)

    from collections import Counter
    gc = Counter()
    for r in rows:
        for gid, gname in zip(r.get("genre_ids") or [], r.get("genres") or []):
            if gname:
                gc[(gid, gname)] += 1
    genres = [k for k, v in gc.most_common(14)]
    countries = [c for c, _ in Counter(r["country"] for r in rows if r["country"]).most_common(9)]

    n_tv = sum(1 for r in rows if r["kind"] == "tv")
    n_mv = sum(1 for r in rows if r["kind"] == "movie")
    n_an = sum(1 for r in rows if r["is_anime"])

    body = f'''<body>
{header("/catalog.html")}
<main>
<section class="band wrap page-head">
  <div class="label dim">2026 / Каталог</div>
  <h1 class="h2" style="margin-top:14px">Все фильмы<br>и сериалы 2026</h1>
  <p class="lead muted" style="margin-top:18px;max-width:60ch">
    {plural(len(rows), "проект", "проекта", "проектов")} года: {n_tv} сериалов, {n_mv} фильмов,
    {n_an} аниме. Сюда попадают и сериалы прошлых лет, если новый сезон выходит в 2026-м.
  </p>
</section>
<section class="band wrap" style="padding-top:0">
  {filter_bar(genres, countries)}
  <div class="grid-posters" id="grid">{cards}</div>
  <div class="empty" id="empty" hidden>
    <div class="h3">Ничего не нашлось</div>
    <div class="muted body" style="margin-bottom:20px">Сбросьте фильтры или измените запрос.</div>
  </div>
</section>
</main>
{footer()}
{FILTER_JS}
{LIST_JS}
</body></html>'''
    return head("Все фильмы и сериалы 2026 — титры",
                "Каталог фильмов и сериалов 2026 года с рейтингами и фильтрами") + body


def build_upcoming():
    rows = [r for r in CAT["upcoming"] if clean_title(r["title"], r.get("original_title"))]

    def dose(r):
        d = r.get("release_date") or ""
        if r["kind"] == "tv" and r.get("next_ep") and r["next_ep"].get("date"):
            d = min([x for x in (d, r["next_ep"]["date"]) if x] or [d])
        return d
    rows.sort(key=dose)
    cards = "".join(card_html(r, "upcoming") for r in rows)

    from collections import Counter
    gc = Counter()
    for r in rows:
        for gid, gname in zip(r.get("genre_ids") or [], r.get("genres") or []):
            if gname:
                gc[(gid, gname)] += 1
    genres = [k for k, v in gc.most_common(14)]
    countries = [c for c, _ in Counter(r["country"] for r in rows if r["country"]).most_common(9)]

    months = Counter(month_tag(dose(r)) for r in rows)
    n_tv = sum(1 for r in rows if r["kind"] == "tv")
    n_mv = sum(1 for r in rows if r["kind"] == "movie")
    y27 = sum(1 for r in rows if dose(r).startswith("2027"))

    body = f'''<body>
{header("/upcoming.html")}
<main>
<section class="band wrap page-head">
  <div class="label dim">Октябрь 2026 — 2027</div>
  <h1 class="h2" style="margin-top:14px">Скоро<br>выходят</h1>
  <p class="lead muted" style="margin-top:18px;max-width:60ch">
    {plural(len(rows), "проект", "проекта", "проектов")}: {n_tv} сериалов и {n_mv} фильмов,
    включая {plural(y27, "проект", "проекта", "проектов")} с датой в 2027 году.
    Даты уточняются — следим за переносами.
  </p>
</section>
<section class="band wrap" style="padding-top:0">
  {filter_bar(genres, countries, sort_label="По дате")}
  <div class="grid-posters" id="grid">{cards}</div>
  <div class="empty" id="empty" hidden>
    <div class="h3">Ничего не нашлось</div>
    <div class="muted body" style="margin-bottom:20px">Сбросьте фильтры или измените запрос.</div>
  </div>
</section>
</main>
{footer()}
{FILTER_JS}
{LIST_JS}
</body></html>'''
    return head("Скоро выходят — титры",
                "Фильмы, сериалы и аниме, которые выходят в 2026–2027 годах") + body


def build_detail(r):
    title = clean_title(r["title"], r.get("original_title"))
    if not title:
        return None
    typ = "Сериал" if r["kind"] == "tv" else "Фильм"
    facts = []
    if r.get("year"): facts.append(("Год", r["year"]))
    facts.append(("Тип", "Аниме" if r.get("is_anime") else ("Мультфильм" if r.get("is_animation") and r["kind"] == "movie" else typ)))
    if r.get("status"): facts.append(("Статус", r["status"]))
    if r.get("country"): facts.append(("Страна", COUNTRIES.get(r["country"], r["country"])))
    if r.get("language"): facts.append(("Язык", LANGS.get(r["language"], r["language"])))
    if r.get("network"): facts.append(("Канал" if r["kind"] == "tv" else "Студия", r["network"]))
    if r["kind"] == "tv" and r.get("n_seasons"): facts.append(("Сезонов", r["n_seasons"]))
    if r["kind"] == "tv" and r.get("n_episodes"): facts.append(("Серий", r["n_episodes"]))
    if r.get("runtime"): facts.append(("Длительность", f"{r['runtime']} мин"))
    if r.get("release_date"): facts.append(("Дата выхода", ru(r["release_date"])))
    if r.get("next_ep") and r["next_ep"].get("date"):
        ne = r["next_ep"]
        facts.append(("Следующая серия", f'S{ne["season"]}E{ne["ep"]} · {ru(ne["date"])}'))
    if r.get("genres"): facts.append(("Жанры", ", ".join(g for g in r["genres"] if g)))

    facts_html = "".join(
        f'<div class="fact"><span class="fact-k">{e(k)}</span><span class="fact-v">{e(v)}</span></div>'
        for k, v in facts)

    # полное описание: короткое видно, остальное раскрывается
    ov = r.get("overview") or ""
    short = ov[:200].rsplit(" ", 1)[0] + "…" if len(ov) > 220 else ov
    expandable = len(ov) > 220
    if not ov:
        desc = '<p class="lead muted">Описание пока не добавлено — источник ещё не опубликовал его.</p>'
    elif expandable:
        desc = f'''<p class="lead desc" id="desc">{e(short)}</p>
<p class="lead desc" id="desc-full" hidden>{e(ov)}</p>
<button class="btn btn-ghost more-btn" id="more">Читать полностью {icon("chevron", 14)}</button>'''
    else:
        desc = f'<p class="lead desc">{e(ov)}</p>'

    bd = r.get("backdrop") or r.get("poster") or ""
    is_up = bool(r.get("upcoming") and not r.get("catalog"))
    back_link = "upcoming.html" if is_up else "catalog.html"
    back_name = "Скоро выходят" if is_up else "Все фильмы и сериалы"

    related = [x for x in (CAT["catalog"] + CAT["upcoming"])
               if x["kind"] == r["kind"] and x["id"] != r["id"]
               and set(x.get("genre_ids") or []) & set(r.get("genre_ids") or [])]
    seen, rel = set(), []
    for x in sorted(related, key=lambda z: -(z.get("vote") or 0)):
        if x["id"] in seen: continue
        t = clean_title(x["title"], x.get("original_title"))
        if not t: continue
        seen.add(x["id"]); rel.append(x)
        if len(rel) == 6: break
    rel_html = "".join(card_html(x) for x in rel)

    body = f'''<body>
{header()}
<main>
<section class="detail-hero">
  <div class="detail-media"><img src="{e(bd)}" alt="{e(title)}"></div>
  <div class="wrap detail-inner">
    <a class="back" href="{PREFIX}{back_link}">{icon("arrow-left", 16)} {e(back_name)}</a>
    <div class="detail-cols">
      <div class="detail-poster">
        {'<img src="' + e(r["poster"]) + '" alt="' + e(title) + '">' if r.get("poster") else ''}
      </div>
      <div>
        <h1 class="h2 detail-title">{e(title)}</h1>
        {f'<div class="lead muted" style="margin-top:10px">{e(r["original_title"])}</div>' if r.get("original_title") and r["original_title"] != title else ""}
        <div class="detail-meta">
          <span>{e(r.get("year") or "")}</span>
          <span>·</span><span>{e("Аниме" if r.get("is_anime") else typ)}</span>
          {f'<span>·</span><span>{e(COUNTRIES.get(r.get("country"), r.get("country") or ""))}</span>' if r.get("country") else ""}
        </div>
        <div style="margin-top:22px">{desc}</div>
        <div class="detail-actions" style="margin-top:22px">
          <button class="btn btn-cream">В мой список</button>
          {f'<a class="btn btn-ghost" href="{e(r["homepage"])}" target="_blank" rel="noopener">Официальный сайт</a>' if r.get("homepage") else ""}
        </div>
      </div>
    </div>
  </div>
</section>

<section class="band wrap">
  <div class="label dim">Рейтинги</div>
  {rating_block(r)}
  <p class="sm muted" style="margin-top:16px;max-width:70ch">
    TMDB, IMDb, Томаты (критики) и Метакритик — реальные данные из источников.
    Зрительский балл Томатов и рейтинг Кинопоиска не показаны: публичного доступа
    к ним нет, а ставить вместо них произвольные цифры мы не станем.
  </p>
</section>

<section class="band wrap" style="padding-top:0">
  <div class="label dim">Известно на сегодня</div>
  <div class="facts">{facts_html}</div>
</section>

{f'''<section class="band wrap" style="padding-top:0">
  <div class="label dim">Похожее</div>
  <div class="grid-posters" style="margin-top:24px">{rel_html}</div>
</section>''' if rel_html else ""}
</main>
{footer()}
<script>
(function () {{
  var btn = document.getElementById('more');
  if (!btn) return;
  btn.addEventListener('click', function () {{
    var s = document.getElementById('desc'), f = document.getElementById('desc-full');
    var open = f.hidden;
    f.hidden = !open; s.hidden = open;
    btn.firstChild.textContent = open ? 'Свернуть ' : 'Читать полностью ';
  }});
}})();
</script>
{LIST_JS}
</body></html>'''

    og = f'<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e((r.get("overview") or "")[:160])}">'
    return head(f"{title} — титры", (r.get("overview") or "")[:160], og) + body


# ---------- сохраняем ----------
os.makedirs(os.path.join(SITE, "tv"), exist_ok=True)
os.makedirs(os.path.join(SITE, "movie"), exist_ok=True)

open(os.path.join(SITE, "catalog.html"), "w", encoding="utf-8").write(build_catalog())
open(os.path.join(SITE, "upcoming.html"), "w", encoding="utf-8").write(build_upcoming())

made = 0
seen_slug = set()
for r in CAT["catalog"] + CAT["upcoming"]:
    sub = "tv" if r["kind"] == "tv" else "movie"
    slug = r["slug"]
    if (sub, slug) in seen_slug:
        slug = f'{slug}-{r["id"]}'
    seen_slug.add((sub, slug))
    PREFIX = "../"
    page = build_detail(r)
    if page:
        open(os.path.join(SITE, sub, f"{slug}.html"), "w", encoding="utf-8").write(page)
        made += 1
PREFIX = ""

_css_src = os.path.join(PREV, "titry.css")
_css_dst = os.path.join(SITE, "titry.css")
if os.path.exists(_css_src) and os.path.abspath(_css_src) != os.path.abspath(_css_dst):
    shutil.copy(_css_src, _css_dst)
else:
    print("CSS уже на месте:", os.path.relpath(_css_dst, ROOT))

# главная: берём собранный home.html и переводим его на новый CSS и навигацию
home = open(os.path.join(PREV, "home.html"), encoding="utf-8").read()
home = home.replace('<link rel="stylesheet" href="titry.css">',
                    '<link rel="stylesheet" href="titry.css">')
open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(home)

open(os.path.join(SITE, ".nojekyll"), "w").close()

# Инструкции кладём рядом с сайтом — они нужны тем, кто будет его вести.
for doc in ("UPDATES.md", "EDITORIAL.md", "MASTER.md", "CLAUDE.md"):
    _src = os.path.join(ROOT, doc)
    _dst = os.path.join(SITE, doc)
    if os.path.exists(_src) and os.path.abspath(_src) != os.path.abspath(_dst):
        shutil.copy(_src, _dst)
print(f"каталог: {len(CAT['catalog'])} | скоро: {len(CAT['upcoming'])} | карточек проектов: {made}")
print("сайт собран в", SITE)
