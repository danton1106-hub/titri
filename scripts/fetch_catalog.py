# -*- coding: utf-8 -*-
"""Сбор данных TMDB для «титры»: весь 2026 год + то, что выходит до конца 2027.

Каталог (2026): сериалы и фильмы, у которых есть эфир или премьера в 2026 году.
  Важно: попадают и сериалы прошлых лет, если у них вышел новый сезон в 2026.
Скоро (2026→2027): проекты с датой выхода с сегодняшнего дня до конца 2027.

Рейтинги: TMDB — есть всегда. Остальные источники требуют ключей и
партнёрских договоров, поэтому слоты заполняются только при наличии ключа.
Данные не выдумываются: чего нет — то None.
"""
import json, os, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from time_service import today_moscow

KEY = os.environ.get("TMDB_API_READ_TOKEN", "").strip()
if not KEY:
    raise SystemExit("TMDB_API_READ_TOKEN is required. Set it in .env locally or GitHub Secrets in CI.")
OMDB_KEY = os.environ.get("OMDB_API_KEY", "").strip()
BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_P = os.path.join(ROOT, "data", "cache.json")
TODAY = today_moscow().isoformat()

os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
CACHE = json.load(open(CACHE_P, encoding="utf-8")) if os.path.exists(CACHE_P) else {}
CACHE_LOCK = threading.Lock()
HITS = {"fresh": 0, "cached": 0}
COUNTER = {"n": 0}


def get(path, **p):
    p.setdefault("language", "ru-RU")
    q = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in sorted(p.items()))
    url = f"{BASE}{path}?{q}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}"})
    with CACHE_LOCK:
        if url in CACHE:
            HITS["cached"] += 1
            return CACHE[url]
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as r:
                d = json.load(r)
            with CACHE_LOCK:
                CACHE[url] = d
                HITS["fresh"] += 1
            return d
        except Exception as e:
            if attempt == 2:
                return {"__error__": str(e)}
            time.sleep(1.5 * (attempt + 1))


def save_cache():
    """Пишем снимок под блокировкой — иначе потоки меняют словарь во время обхода."""
    with CACHE_LOCK:
        snapshot = dict(CACHE)
    tmp = CACHE_P + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)
    os.replace(tmp, CACHE_P)


# ---------- транслитерация для slug ----------
TR = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i',
      'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
      'у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y',
      'ь':'','э':'e','ю':'yu','я':'ya'}


def slugify(s):
    out = []
    for ch in (s or "").lower():
        if ch in TR:
            out.append(TR[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in " -_/.,:!?'\"()":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:64] or "title"


# ---------- жанры ----------
GENRES = {}
for _k in ("tv", "movie"):
    for _g in get(f"/genre/{_k}/list").get("genres", []):
        GENRES[_g["id"]] = _g["name"]

# ---------- сбор кандидатов ----------
def paged(path, pages=2, **p):
    ids = []
    for pg in range(1, pages + 1):
        d = get(path, page=pg, **p)
        for x in d.get("results", []):
            ids.append(x["id"])
        if pg >= (d.get("total_pages") or 1):
            break
    return ids


cat_tv, cat_mv, up_tv, up_mv = [], [], [], []

# --- каталог: сериалы 2026 (включая новые сезоны старых сериалов) ---
cat_tv += paged("/discover/tv", pages=3, sort_by="popularity.desc",
                **{"air_date.gte": "2026-01-01", "air_date.lte": "2026-12-31",
                   "vote_count.gte": 25})
cat_tv += paged("/discover/tv", pages=2, sort_by="vote_average.desc",
                **{"first_air_date.gte": "2026-01-01", "first_air_date.lte": "2026-12-31",
                   "vote_count.gte": 25})
cat_tv += paged("/tv/on_the_air", pages=2)
cat_tv += paged("/discover/tv", pages=2, sort_by="popularity.desc",
                with_genres=16, with_original_language="ja",
                **{"air_date.gte": "2026-01-01", "air_date.lte": "2026-12-31"})

# --- каталог: фильмы 2026 ---
cat_mv += paged("/discover/movie", pages=3, sort_by="vote_average.desc",
                **{"primary_release_date.gte": "2026-01-01",
                   "primary_release_date.lte": "2026-12-31", "vote_count.gte": 80})
cat_mv += paged("/discover/movie", pages=2, sort_by="popularity.desc",
                **{"primary_release_date.gte": "2026-01-01",
                   "primary_release_date.lte": "2026-12-31", "vote_count.gte": 40})
cat_mv += paged("/movie/now_playing", pages=1, region="RU")
cat_mv += paged("/discover/movie", pages=1, sort_by="popularity.desc",
                with_genres=16, with_original_language="ja",
                **{"primary_release_date.gte": "2026-01-01",
                   "primary_release_date.lte": "2026-12-31"})

# --- скоро: 2026-10-01 … 2027-12-31 ---
up_tv += paged("/discover/tv", pages=2, sort_by="popularity.desc",
               **{"first_air_date.gte": "2026-10-01", "first_air_date.lte": "2027-12-31"})
up_tv += paged("/discover/tv", pages=2, sort_by="popularity.desc",
               **{"air_date.gte": "2026-10-01", "air_date.lte": "2027-12-31"})
up_mv += paged("/discover/movie", pages=3, sort_by="popularity.desc",
               **{"primary_release_date.gte": "2026-10-01",
                  "primary_release_date.lte": "2027-12-31"})
up_mv += paged("/discover/movie", pages=1, sort_by="popularity.desc",
               with_genres=16,
               **{"primary_release_date.gte": "2026-10-01",
                  "primary_release_date.lte": "2027-12-31"})

cat_tv, cat_mv = list(dict.fromkeys(cat_tv)), list(dict.fromkeys(cat_mv))
up_tv, up_mv = list(dict.fromkeys(up_tv)), list(dict.fromkeys(up_mv))

print(f"кандидаты: каталог ТВ {len(cat_tv)}, фильмы {len(cat_mv)} | "
      f"скоро ТВ {len(up_tv)}, фильмы {len(up_mv)}")

ALL = ([("tv", i, True, False) for i in cat_tv] + [("movie", i, True, False) for i in cat_mv] +
       [("tv", i, False, True) for i in up_tv] + [("movie", i, False, True) for i in up_mv])

# схлопываем дубли: один item может быть и в каталоге, и в «скоро»
merged = {}
for kind, tid, in_cat, in_up in ALL:
    k = (kind, tid)
    if k in merged:
        merged[k]["catalog"] |= in_cat
        merged[k]["upcoming"] |= in_up
    else:
        merged[k] = {"kind": kind, "id": tid, "catalog": in_cat, "upcoming": in_up}

print("уникальных проектов:", len(merged))


def omdb_ratings(imdb_id):
    """Rotten Tomatoes и IMDb через OMDb. Только если задан ключ — иначе None."""
    if not OMDB_KEY or not imdb_id:
        return {}
    q = urllib.parse.urlencode({"i": imdb_id, "apikey": OMDB_KEY})
    try:
        with urllib.request.urlopen(f"https://www.omdbapi.com/?{q}", timeout=30) as r:
            d = json.load(r)
    except Exception:
        return {}
    out = {}
    for x in d.get("Ratings", []):
        src, val = x.get("Source"), x.get("Value", "")
        if src == "Rotten Tomatoes":
            out["rt_critics"] = val.replace("%", "")
        elif src == "Metacritic":
            out["metacritic"] = val.split("/")[0]
        elif src == "Internet Movie Database":
            out["imdb"] = val.split("/")[0]
    if d.get("imdbRating") and "imdb" not in out:
        out["imdb"] = d["imdbRating"]
    return out


def build(item):
    kind, tid = item["kind"], item["id"]
    d = get(f"/{kind}/{tid}", append_to_response="external_ids")
    if "__error__" in d:
        return None
    title = d.get("name") or d.get("title")
    if not title:
        return None

    gids = [g["id"] for g in d.get("genres", [])]
    is_anim = 16 in gids
    lang = d.get("original_language")

    if kind == "tv":
        first = d.get("first_air_date") or ""
        last = d.get("last_air_date") or ""
        nxt = d.get("next_episode_to_air")
        lst = d.get("last_episode_to_air")
        seasons = [s for s in d.get("seasons", []) if s.get("season_number", 0) > 0]
        countries = d.get("origin_country") or []
        network = (d.get("networks") or [{}])[0].get("name", "")
        runtime = (d.get("episode_run_time") or [None])[0]
        n_seasons = len(seasons)
        n_eps = sum(s.get("episode_count") or 0 for s in seasons)
    else:
        first = d.get("release_date") or ""
        last = first
        nxt = lst = None
        countries = [c.get("iso_3166_1") for c in (d.get("production_countries") or [])]
        network = (d.get("production_companies") or [{}])[0].get("name", "")
        runtime = d.get("runtime")
        n_seasons = n_eps = 0

    # «актуально выходит в 2026»: эфир в 2026 или премьера в 2026
    airing_2026 = bool(first and first[:4] == "2026")
    new_season_2026 = bool(kind == "tv" and last and last >= "2026-01-01"
                           and first and first[:4] != "2026")
    released_2026 = bool(kind == "tv" and last and last >= "2026-01-01") or \
                    bool(kind == "movie" and first[:4] == "2026")

    imdb_id = d.get("imdb_id") or (d.get("external_ids") or {}).get("imdb_id")

    return {
        "kind": kind, "id": tid,
        "title": title,
        "original_title": d.get("original_name") or d.get("original_title") or "",
        "slug": slugify(title),
        "poster": f"{IMG}/w342{d['poster_path']}" if d.get("poster_path") else None,
        "backdrop": f"{IMG}/w780{d['backdrop_path']}" if d.get("backdrop_path") else None,
        "overview": (d.get("overview") or "").strip(),
        "tagline": (d.get("tagline") or "").strip(),
        "year": (first or "")[:4],
        "first_date": first, "last_date": last,
        "vote": round(d.get("vote_average") or 0, 1),
        "vote_count": d.get("vote_count") or 0,
        "popularity": round(d.get("popularity") or 0, 1),
        "genre_ids": gids,
        "genres": [GENRES.get(g, "") for g in gids],
        "country": countries[0] if countries else "",
        "countries": countries,
        "language": lang,
        "is_animation": is_anim,
        "is_anime": is_anim and lang == "ja",
        "status": d.get("status") or "",
        "network": network,
        "runtime": runtime,
        "n_seasons": n_seasons, "n_episodes": n_eps,
        "next_ep": ({"ep": nxt.get("episode_number"), "season": nxt.get("season_number"),
                     "date": nxt.get("air_date"), "name": nxt.get("name")} if nxt else None),
        "last_ep": ({"ep": lst.get("episode_number"), "season": lst.get("season_number"),
                     "date": lst.get("air_date"), "name": lst.get("name")} if lst else None),
        "imdb_id": imdb_id,
        "homepage": d.get("homepage") or "",
        "catalog": item["catalog"], "upcoming": item["upcoming"],
        "airing_2026": airing_2026, "new_season_2026": new_season_2026,
        "released_2026": released_2026,
        "release_date": first,
        # Рейтинги. TMDB — реальные данные. Остальные — только при наличии
        # легального источника. Ничего не выдумываем.
        "ratings": {
            "tmdb": round(d.get("vote_average") or 0, 1),
            "tmdb_count": d.get("vote_count") or 0,
            "kinopoisk": None,      # официальный API только по партнёрскому договору
            "rt_critics": None,     # OMDb, если задан OMDB_API_KEY
            "rt_audience": None,    # публичного API нет
            **omdb_ratings(imdb_id),
        },
    }


records = []
with ThreadPoolExecutor(max_workers=6) as ex:
    futs = {ex.submit(build, it): it for it in merged.values()}
    done = 0
    for f in as_completed(futs):
        done += 1
        r = f.result()
        if r:
            records.append(r)
        if done % 40 == 0:
            print(f"  обработано {done}/{len(merged)}  (API {HITS['fresh']}, из кэша {HITS['cached']})")
            save_cache()

save_cache()
print(f"всего записей: {len(records)}  (API {HITS['fresh']}, из кэша {HITS['cached']})")


def rank(r):
    """Сортировка по рейтингу с учётом количества голосов."""
    return r["vote"] * min(1.0, (r["vote_count"] / 300) ** 0.5) if r["vote_count"] else 0


# --- каталог: только 2026 ---
catalog = [r for r in records if r["catalog"] and (r["airing_2026"] or r["released_2026"])]
tv_c = sorted([r for r in catalog if r["kind"] == "tv"], key=rank, reverse=True)
mv_c = sorted([r for r in catalog if r["kind"] == "movie"], key=rank, reverse=True)
anime_c = [r for r in tv_c if r["is_anime"]][:24]
cat_final = tv_c[:72] + mv_c[:60]
# добираем аниме, если не попало в топ
have = {r["id"] for r in cat_final}
for a in anime_c:
    if a["id"] not in have:
        cat_final.append(a)
        have.add(a["id"])
cat_final.sort(key=rank, reverse=True)

# --- скоро: с сегодня до конца 2027 ---
def soon(r):
    d = r["release_date"]
    if r["kind"] == "tv" and r.get("next_ep") and r["next_ep"].get("date"):
        d = min([x for x in (d, r["next_ep"]["date"]) if x] or [d])
    return d or ""


upcoming = [r for r in records if r["upcoming"] and soon(r) >= TODAY and soon(r) <= "2027-12-31"]
up_tv = sorted([r for r in upcoming if r["kind"] == "tv"],
               key=lambda r: (soon(r), -r["popularity"]))
up_mv = sorted([r for r in upcoming if r["kind"] == "movie"],
               key=lambda r: (soon(r), -r["popularity"]))
up_final = up_tv[:48] + up_mv[:48]
up_final.sort(key=soon)

# slug-и уникальны: при коллизии добавляем id
seen = {}
for r in cat_final + up_final:
    key = (r["kind"], r["slug"])
    if key in seen:
        r["slug"] = f'{r["slug"]}-{r["id"]}'
    seen[key] = r["id"]

out = {
    "generated": TODAY,
    "catalog": cat_final,
    "upcoming": up_final,
    "counts": {
        "catalog": len(cat_final),
        "catalog_tv": sum(1 for r in cat_final if r["kind"] == "tv"),
        "catalog_movie": sum(1 for r in cat_final if r["kind"] == "movie"),
        "catalog_anime": sum(1 for r in cat_final if r["is_anime"]),
        "upcoming": len(up_final),
        "upcoming_tv": sum(1 for r in up_final if r["kind"] == "tv"),
        "upcoming_movie": sum(1 for r in up_final if r["kind"] == "movie"),
    },
    "genres": GENRES,
}
p = os.path.join(ROOT, "data", "catalog.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False)
print("\n=== ИТОГ ===")
for k, v in out["counts"].items():
    print(f"  {k}: {v}")
print(f"файл: {os.path.getsize(p)//1024} КБ")
print("\nтоп каталога:")
for r in cat_final[:8]:
    print(f'  {r["vote"]:>4} ({r["vote_count"]:>5}) {r["title"][:44]:<44} '
          f'{"сериал" if r["kind"]=="tv" else "фильм"}{" · аниме" if r["is_anime"] else ""}')
print("\nскоро:")
for r in up_final[:8]:
    print(f'  {soon(r)}  {r["title"][:40]:<40} {"сериал" if r["kind"]=="tv" else "фильм"}')
