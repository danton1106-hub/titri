# -*- coding: utf-8 -*-
"""Полное обновление сайта: данные, страницы, черновики статей.

Запускается дважды в день — в 10:00 и 19:00 по Москве.
Что делает:
  1. Тянет изменения TMDB (главная: серии, календарь).
  2. Пересобирает каталог 2026 и «скоро выходят».
  3. Обновляет рейтинги IMDb / Томатов / Metacritic через OMDb.
     Внутри свой кэш: раз в 7 дней, чтобы не тратить лимит 1000/сутки.
  4. Пересобирает все страницы.
  5. Забирает RSS и создаёт черновики статей для редактора.

Чего НЕ делает: не публикует статьи. Конвейер останавливается на черновике —
текст пишет человек (см. MASTER.md).
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSK = timezone(timedelta(hours=3))

STEPS = [
    ("Данные главной (TMDB)", ["python3", "scripts/fetch_home.py"], True),
    ("Каталог 2026 и «скоро» (TMDB)", ["python3", "scripts/fetch_catalog.py"], True),
    ("Рейтинги IMDb и Томатов (OMDb)", ["python3", "scripts/fetch_ratings.py"], False),
    ("Сборка главной", ["python3", "scripts/build_home.py"], True),
    ("Сборка страниц сайта", ["python3", "scripts/build_site.py"], True),
    ("Черновики статей (RSS)", ["python3", "scripts/collect_articles.py"], False),
]


def run(cmd, required):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    dt = time.time() - t0
    tail = (p.stdout or "").strip().splitlines()
    last = tail[-1] if tail else ""
    status = "OK " if p.returncode == 0 else ("СБОЙ" if required else "пропуск")
    print(f'  [{status}] {cmd[1]:<32} {dt:6.1f} с  {last[:70]}')
    if p.returncode != 0 and p.stderr:
        print(f'         {p.stderr.strip().splitlines()[-1][:110]}')
    return p.returncode == 0


def main():
    now = datetime.now(MSK)
    print("=" * 72)
    print(f"ОБНОВЛЕНИЕ САЙТА — {now:%d.%m.%Y %H:%M} МСК")
    print("=" * 72)
    t0 = time.time()
    failed = []
    for name, cmd, required in STEPS:
        print(f"\n{name}")
        ok = run(cmd, required)
        if not ok and required:
            failed.append(name)
    dt = time.time() - t0
    print("\n" + "=" * 72)
    if failed:
        print(f"ЗАВЕРШЕНО С ОШИБКАМИ за {dt:.0f} с. Не прошло: {', '.join(failed)}")
        print("Сайт остался в предыдущем состоянии — данные не потеряны.")
        return 1
    print(f"ГОТОВО за {dt:.0f} с. Черновики статей ждут редактора.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
