#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Рейтинги IMDb, Rotten Tomatoes и Metacritic через OMDb.

Ключ берётся из .env (переменная OMDB_API_KEY) и НИКОГДА не попадает в код,
в HTML или в клиентский JavaScript. Рейтинги сохраняются в data/ratings.json
и при сборке вшиваются в страницы как готовые числа.

Почему это безопасно:
  Страницы статические. Ключ используется только на этапе сборки, в Python.
  В браузер уходят уже посчитанные цифры — забрать ключ со страницы нельзя.

Почему обновляем редко:
  Бесплатный тариф OMDb — 1000 запросов в сутки. У нас 209 проектов.
  Рейтинги меняются медленно, поэтому обновляем раз в неделю, а не дважды в день.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import env_service

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_P = os.path.join(ROOT, ".env")
CAT_P = os.path.join(ROOT, "data", "catalog.json")
OUT_P = os.path.join(ROOT, "data", "ratings.json")

env_service.load_dotenv()
KEY = env_service.optional("OMDB_API_KEY")

if not KEY:
    _msg = ("OMDB_API_KEY не задан. Положите ключ в .env в корне проекта "
            "или задайте его в GitHub Secrets.")
    if env_service.allow_cached():
        print("ПРЕДУПРЕЖДЕНИЕ: " + _msg, file=sys.stderr)
        print("Внешние рейтинги не обновляются, data/ratings.json остаётся прежним.", file=sys.stderr)
        raise SystemExit(0)
    print("ОШИБКА: " + _msg, file=sys.stderr)
    print("Файл .env в репозиторий не попадает — он в .gitignore.", file=sys.stderr)
    raise SystemExit(1)

REFRESH_DAYS = 7


def omdb(imdb_id, timeout=25):
    q = urllib.parse.urlencode({"i": imdb_id, "apikey": KEY})
    url = f"https://www.omdbapi.com/?{q}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.2 * (attempt + 1))


def parse(d):
    """Достаём оценки. Чего нет — оставляем None, ничего не выдумываем."""
    out = {"imdb": None, "imdb_votes": None, "rt_critics": None,
           "metacritic": None, "rt_audience": None}
    if not d or d.get("Response") != "True":
        return out

    if d.get("imdbRating") and d["imdbRating"] != "N/A":
        out["imdb"] = d["imdbRating"]
    if d.get("imdbVotes") and d["imdbVotes"] != "N/A":
        out["imdb_votes"] = d["imdbVotes"]
    if d.get("Metascore") and d["Metascore"] != "N/A":
        out["metacritic"] = d["Metascore"]

    for x in d.get("Ratings") or []:
        src, val = x.get("Source"), (x.get("Value") or "")
        if src == "Rotten Tomatoes" and "%" in val:
            out["rt_critics"] = val.replace("%", "").strip()
        elif src == "Metacritic" and "/" in val:
            out["metacritic"] = val.split("/")[0].strip()
        elif src == "Internet Movie Database" and "/" in val:
            out["imdb"] = val.split("/")[0].strip()

    # Зрительский Popcornmeter OMDb не отдаёт — оставляем None.
    # Выдумывать его нельзя: это чужая оценка.
    return out


def main():
    CAT = json.load(open(CAT_P, encoding="utf-8"))
    old = json.load(open(OUT_P, encoding="utf-8")) if os.path.exists(OUT_P) else {}

    projects = CAT["catalog"] + CAT["upcoming"]
    seen = set()
    todo = []
    for r in projects:
        iid = r.get("imdb_id")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        todo.append(iid)

    now = datetime.now(timezone.utc)
    print(f"=== Рейтинги OMDb — {now:%d.%m.%Y %H:%M} UTC ===")
    print(f"проектов с IMDb ID: {len(todo)}")

    # кэш: что собрано меньше REFRESH_DAYS назад — не трогаем
    fresh, stale = {}, []
    for iid in todo:
        rec = old.get(iid)
        if rec and rec.get("at"):
            try:
                age = (now - datetime.fromisoformat(rec["at"])).days
            except Exception:
                age = 999
            if age < REFRESH_DAYS:
                fresh[iid] = rec
                continue
        stale.append(iid)

    print(f"  свежих в кэше: {len(fresh)}")
    print(f"  спросить заново: {len(stale)}")
    if len(stale) > 900:
        print("  ВНИМАНИЕ: больше 900 запросов — можно упереться в суточный лимит OMDb.")

    out = dict(fresh)
    ok = miss = 0
    t0 = time.time()

    for i, iid in enumerate(stale, 1):
        d = omdb(iid)
        rec = parse(d)
        rec["at"] = now.isoformat()
        rec["title"] = (d or {}).get("Title")
        out[iid] = rec
        if rec["imdb"] or rec["rt_critics"] or rec["metacritic"]:
            ok += 1
        else:
            miss += 1
        if i % 40 == 0 or i == len(stale):
            dt = time.time() - t0
            print(f"  {i}/{len(stale)}  получено {ok}, пусто {miss}  ({dt:.0f} с)")
        time.sleep(0.06)

    json.dump(out, open(OUT_P, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # сводка по каталогу
    have_imdb = have_rt = have_mc = 0
    for iid in todo:
        rec = out.get(iid) or {}
        if rec.get("imdb"): have_imdb += 1
        if rec.get("rt_critics"): have_rt += 1
        if rec.get("metacritic"): have_mc += 1

    print("\n=== ИТОГ ===")
    print(f"  IMDb:            {have_imdb} из {len(todo)}")
    print(f"  Томаты критики:  {have_rt} из {len(todo)}")
    print(f"  Metacritic:      {have_mc} из {len(todo)}")
    print(f"  Томаты зрители:  0 — OMDb не отдаёт зрительский балл")
    print(f"  файл: {os.path.getsize(OUT_P)//1024} КБ")
    print("\nКлюч использовался только здесь, в Python. В HTML он не попадает.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
