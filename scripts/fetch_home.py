# -*- coding: utf-8 -*-
"""Данные для главной «титры»: карточки для живого фильтра, честный тикер, календарь.

Тикер собирается из серий, которые реально выходят СЕГОДНЯ, — не из заглушки.
Карточек 18: 12 сериалов (включая аниме) и 6 фильмов, чтобы фильтрам было что фильтровать.
"""
import json, os, urllib.request, urllib.parse

from datetime import timedelta

from time_service import today_moscow

KEY = os.environ.get("TMDB_API_READ_TOKEN", "").strip()
if not KEY:
    raise SystemExit("TMDB_API_READ_TOKEN is required. Set it in .env locally or GitHub Secrets in CI.")
BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = today_moscow().isoformat()


def get(path, **p):
    p.setdefault("language", "ru-RU")
    q = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in p.items())
    request = urllib.request.Request(
        f"{BASE}{path}?{q}", headers={"Authorization": f"Bearer {KEY}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        return {"__error__": str(e)}


# Жанры на русском: id -> название
GENRES = {}
for kind in ("tv", "movie"):
    g = get(f"/genre/{kind}/list")
    for x in g.get("genres", []):
        GENRES[x["id"]] = x["name"]


def image(path, size):
    return f"{IMG}/{size}{path}" if path else None


def card_tv(tid):
    d = get(f"/tv/{tid}")
    if "__error__" in d or not d.get("name"):
        return None
    seasons = [s for s in d.get("seasons", []) if s.get("season_number", 0) > 0]
    last = seasons[-1] if seasons else None
    total = aired = 0
    next_ep = last_ep = None
    if last:
        sd = get(f"/tv/{tid}/season/{last['season_number']}")
        eps = [e for e in sd.get("episodes", []) if e.get("air_date")]
        total = len(eps)
        past = [e for e in eps if e["air_date"] <= TODAY]
        future = [e for e in eps if e["air_date"] > TODAY]
        aired = len(past)
        if past:
            p = past[-1]
            last_ep = {"ep": p["episode_number"], "date": p["air_date"],
                       "name": p.get("name"), "season": last["season_number"]}
        if future:
            f = future[0]
            next_ep = {"ep": f["episode_number"], "date": f["air_date"],
                       "name": f.get("name"), "season": last["season_number"]}
    gids = [g["id"] for g in d.get("genres", [])]
    return {
        "kind": "tv", "id": tid, "title": d.get("name"),
        "poster": image(d.get("poster_path"), "w342"),
        "backdrop": image(d.get("backdrop_path"), "w1280"),
        "year": (d.get("first_air_date") or "")[:4],
        "vote": round(d.get("vote_average") or 0, 1),
        "genre_ids": gids,
        "genres": [GENRES.get(i, "") for i in gids][:2],
        "is_anime": 16 in gids and d.get("original_language") == "ja",
        "is_animation": 16 in gids,
        "country": (d.get("origin_country") or [""])[0],
        "network": (d.get("networks") or [{}])[0].get("name", ""),
        "season": last["season_number"] if last else None,
        "total": total, "aired": aired,
        "all_aired": total > 0 and aired == total,
        "next_ep": next_ep,
        "last_ep": last_ep,
        "new_today": bool(last_ep and last_ep["date"] == TODAY),
        "status": d.get("status"),
    }


def card_movie(mid):
    d = get(f"/movie/{mid}")
    if "__error__" in d or not d.get("title"):
        return None
    gids = [g["id"] for g in d.get("genres", [])]
    return {
        "kind": "movie", "id": mid, "title": d.get("title"),
        "poster": image(d.get("poster_path"), "w342"),
        "backdrop": image(d.get("backdrop_path"), "w1280"),
        "year": (d.get("release_date") or "")[:4],
        "vote": round(d.get("vote_average") or 0, 1),
        "genre_ids": gids,
        "genres": [GENRES.get(i, "") for i in gids][:2],
        "is_anime": False,
        "is_animation": 16 in gids,
        "country": (d.get("production_countries") or [{}])[0].get("iso_3166_1", ""),
        "network": "", "season": None, "total": 0, "aired": 0, "all_aired": False,
        "next_ep": None, "last_ep": None, "new_today": False,
        "status": "Released",
        "release_date": d.get("release_date"),
        "runtime": d.get("runtime"),
    }


# --- Сериалы: текущие + добор из популярных ---
# Список ID для витрины главной вынесен в data/featured.json.
# Если файла нет — очередь строится только по popularity из TMDB.
TV_IDS = list(json.load(open(os.path.join(ROOT, "data", "featured.json"), encoding="utf-8")).get("tv_ids", [])) \
    if os.path.exists(os.path.join(ROOT, "data", "featured.json")) else []
try:
    pop = get("/tv/popular", page=1).get("results", [])
    for x in pop:
        if len(TV_IDS) >= 11:
            break
        if x["id"] not in TV_IDS and x.get("vote_average", 0) >= 6.5:
            TV_IDS.append(x["id"])
except Exception:
    pass

# Аниме — отдельным блоком, чтобы фильтр «Аниме» не был пустым
try:
    anime = get("/discover/tv", with_genres=16, with_original_language="ja",
                sort_by="popularity.desc", page=1).get("results", [])
    for x in anime:
        if len(TV_IDS) >= 13:
            break
        if x["id"] not in TV_IDS:
            TV_IDS.append(x["id"])
except Exception:
    pass

cards = []
for tid in TV_IDS:
    c = card_tv(tid)
    if c:
        cards.append(c)

# --- Фильмы ---
MOVIE_IDS = []
try:
    for x in get("/movie/now_playing", region="RU", page=1).get("results", []):
        if len(MOVIE_IDS) >= 6:
            break
        MOVIE_IDS.append(x["id"])
except Exception:
    pass

for mid in MOVIE_IDS:
    c = card_movie(mid)
    if c:
        cards.append(c)

# --- Тикер: что реально вышло сегодня ---
today_items = []
for c in cards:
    if c["kind"] == "tv" and c.get("last_ep") and c["last_ep"]["date"] == TODAY:
        today_items.append({
            "kind": "tv", "title": c["title"], "season": c["last_ep"]["season"],
            "ep": c["last_ep"]["ep"], "ep_name": c["last_ep"]["name"],
            "network": c["network"],
        })
# фильмы, вышедшие сегодня
for c in cards:
    if c["kind"] == "movie" and c.get("release_date") == TODAY:
        today_items.append({"kind": "movie", "title": c["title"], "network": ""})

# --- Календарь: текущая неделя по Москве, понедельник — воскресенье ---
_today = today_moscow()
_mon = _today - timedelta(days=_today.weekday())
_sun = _mon + timedelta(days=6)
_w0, _w1 = _mon.isoformat(), _sun.isoformat()
week = {}
for c in cards:
    if c["kind"] == "tv" and c.get("next_ep"):
        d = c["next_ep"]["date"]
        if _w0 <= d <= _w1:
            week.setdefault(d, []).append({
                "title": c["title"], "poster": c["poster"], "season": c["next_ep"]["season"],
                "ep": c["next_ep"]["ep"], "ep_name": c["next_ep"]["name"], "network": c["network"],
            })

# --- Следующая серия для карточки календаря ---
next_up = None
for c in cards:
    if c["kind"] == "tv" and c.get("next_ep"):
        if next_up is None or c["next_ep"]["date"] < next_up["next_ep"]["date"]:
            next_up = c
hero = next((c for c in cards if c.get("backdrop")), cards[0] if cards else None)

out = {
    "cards": cards,
    "today": today_items,
    "calendar": [{"date": d, "items": v} for d, v in sorted(week.items())],
    "next_episode": next_up,
    "hero": hero,
    "genres": GENRES,
    "today_date": TODAY,
}

p = os.path.join(ROOT, "data", "home.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"карточек: {len(cards)}  (сериалов {sum(1 for c in cards if c['kind']=='tv')}, "
      f"фильмов {sum(1 for c in cards if c['kind']=='movie')}, "
      f"аниме {sum(1 for c in cards if c['is_anime'])})")
print(f"сегодня вышло: {len(today_items)}")
for t in today_items:
    tail_txt = f' · {t["season"]} сезон, {t["ep"]} серия' if t["kind"] == "tv" else ""
    print(f'   {t["title"]}{tail_txt}')
print(f"календарь: {len(out['calendar'])} дней")
for d in out["calendar"]:
    for it in d["items"][:2]:
        print(f'   {d["date"]}  {it["title"]} S{it["season"]}E{it["ep"]}')
print("следующая серия:", (next_up or {}).get("title"), (next_up or {}).get("next_ep"))
print("в центре внимания:", (hero or {}).get("title"))
print("файл:", os.path.getsize(p), "байт")
