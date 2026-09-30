# -*- coding: utf-8 -*-
"""Сбор новостей из RSS и создание ЧЕРНОВИКОВ для редактора.

Что этот скрипт делает и чего не делает:

  ДЕЛАЕТ: скачивает RSS, убирает дубли, фильтрует по теме,
          собирает черновик с ссылкой на первоисточник и списком задач для редактора.
  НЕ ДЕЛАЕТ: не переводит чужие статьи и не публикует их автоматически.

Почему не переводит и не публикует:
  1. Перевод статьи — производное произведение, нужен разрешение правообладателя.
     RSS разрешает распространение заголовка и ссылки, но не текста.
  2. Google относит массовый машинный перевод к «scaled content abuse» —
     тот же фильтр, что и у потока сгенерированных SEO-страниц.
  3. Так решено в MASTER.md: только собственная редакция.

Поэтому конвейер останавливается на черновике. Текст пишет человек.
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_P = os.path.join(ROOT, "data", "sources.json")
SEEN_P = os.path.join(ROOT, "data", "articles_seen.json")
DRAFTS = os.path.join(ROOT, "articles", "drafts")
UA = "Mozilla/5.0 (compatible; TitryBot/0.1; +https://github.com/danton1106-hub/titri)"

CFG = json.load(open(SRC_P, encoding="utf-8"))
SEEN = json.load(open(SEEN_P, encoding="utf-8")) if os.path.exists(SEEN_P) else {}
LIM = CFG.get("limits", {})
KW = CFG["keywords"]

os.makedirs(DRAFTS, exist_ok=True)

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s{2,}")
# Google News отдаёт заголовок в виде «Заголовок - Издание»
GNEWS_TAIL = re.compile(r"\s+-\s+[^-]{2,40}$")


def strip_tags(s):
    if not s:
        return ""
    s = html.unescape(s)
    s = TAG_RE.sub(" ", s)
    s = html.unescape(s)
    return WS_RE.sub(" ", s).strip()


def norm_title(t):
    """Нормализация для поиска дублей: без пунктуации, регистра, лишних пробелов."""
    t = (t or "").lower()
    t = GNEWS_TAIL.sub("", t)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return WS_RE.sub(" ", t).strip()


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as ex:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


def parse_feed(raw):
    """Понимает и RSS 2.0, и Atom. Возвращает список записей."""
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # часть фидов отдаёт мусор перед XML — пробуем отрезать
        i = raw.find(b"<?xml")
        j = raw.find(b"<rss")
        k = raw.find(b"<feed")
        start = min([x for x in (i, j, k) if x >= 0] or [-1])
        if start < 0:
            return items
        try:
            root = ET.fromstring(raw[start:])
        except ET.ParseError:
            return items

    def txt(el, *names):
        for n in names:
            found = el.find(n)
            if found is not None and (found.text or found.get("href")):
                return (found.text or found.get("href") or "").strip()
        # пространства имён Atom
        for child in el:
            tag = child.tag.split("}")[-1]
            if tag in names:
                if child.text:
                    return child.text.strip()
                if child.get("href"):
                    return child.get("href")
        return ""

    # RSS
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title = strip_tags(txt(it, "title"))
        link = txt(it, "link")
        if not link:
            for child in it:
                if child.tag.split("}")[-1] == "link":
                    link = child.get("href") or child.text or ""
                    if link:
                        break
        desc = strip_tags(txt(it, "description", "summary", "content", "encoded"))
        date = txt(it, "pubDate", "published", "updated", "date")
        if title and link:
            items.append({"title": title, "link": link.strip(),
                          "summary": desc, "date": date})
    return items


def relevance(title, summary):
    """Насколько новость про кино: 2 — сильное совпадение, 1 — слабое, 0 — мимо."""
    t = f"{title} {summary}".lower()
    if any(k.lower() in t for k in KW["strong"]):
        return 2
    if any(k.lower() in t for k in KW["weak"]):
        return 1
    return 0


def slugify(s):
    TR = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i',
          'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
          'у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y',
          'ь':'','э':'e','ю':'yu','я':'ya'}
    out = []
    for ch in (s or "").lower():
        if ch in TR:
            out.append(TR[ch])
        elif ch.isalnum() and ord(ch) < 128:
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-{2,}", "-", "".join(out)).strip("-")
    return slug[:60] or "news"


DRAFT_TPL = """# Черновик: {title}

**Источник:** {source} — <{link}>
**Опубликовано:** {date}
**Забрано:** {grabbed} (автоматически, cron)
**Тема:** {topic} · релевантность: {rel}

---

## Служебное — НЕ ПУБЛИКОВАТЬ

Краткое содержание от источника, только чтобы понять суть.
Текст чужой статьи. Копировать и переводить запрещено.

> {summary}

---

## Задачи редактору

1. Открыть первоисточник по ссылке выше, прочитать целиком.
2. Если новость значимая — сверить минимум по двум изданиям.
3. Написать свой текст: 2–4 абзаца. Факты свободны, форма — наша.
4. Тон: резковатый, с собственным мнением. Оценка важнее пересказа.
5. Поставить ссылки на источники.
6. Заполнить метаданные ниже, убрать пометку «черновик».
7. Перенести файл в `articles/published/`.

## Текст

<!-- пиши здесь -->

## Метаданные

- slug: `{slug}`
- title:
- description:
- связанные проекты:
- статус: **черновик**

---

*Автоматическая публикация запрещена. Конвейер останавливается на этом файле.*
"""


def main():
    run_at = datetime.now(timezone.utc)
    print(f"=== Сбор новостей: {run_at:%Y-%m-%d %H:%M} UTC ===")

    per_source = int(LIM.get("per_source", 25))
    max_drafts = int(LIM.get("drafts_per_run", 20))
    sum_chars = int(LIM.get("summary_chars", 400))

    collected = []
    stats = []

    for src in CFG["sources"]:
        try:
            raw = fetch(src["url"])
            items = parse_feed(raw)[:per_source]
        except Exception as ex:
            stats.append((src["name"], "ошибка: " + type(ex).__name__, 0))
            print(f'  {src["name"]:<28} ошибка: {type(ex).__name__}')
            continue

        new = 0
        for it in items:
            key = norm_title(it["title"])
            if not key or key in SEEN:
                continue
            rel = relevance(it["title"], it["summary"])
            if rel == 0:
                SEEN[key] = {"seen": run_at.isoformat(), "rel": 0}
                continue
            collected.append({
                "title": it["title"], "link": it["link"],
                "summary": it["summary"][:sum_chars],
                "date": it["date"], "source": src["name"],
                "topic": src.get("topic", "кино"), "rel": rel, "key": key,
            })
            SEEN[key] = {"seen": run_at.isoformat(), "rel": rel, "link": it["link"]}
            new += 1
        stats.append((src["name"], f"новых {new}", len(items)))

    # сильные совпадения вперёд
    collected.sort(key=lambda x: (-x["rel"], x["source"]))
    picked = collected[:max_drafts]

    made = []
    for i, news in enumerate(picked, 1):
        base = slugify(news["title"])
        slug = base
        n = 2
        while os.path.exists(os.path.join(DRAFTS, f"{slug}.md")):
            slug = f"{base}-{n}"
            n += 1
        body = DRAFT_TPL.format(
            title=news["title"], source=news["source"], link=news["link"],
            date=news["date"] or "дата не указана",
            grabbed=f"{run_at:%d.%m.%Y %H:%M} UTC",
            topic=news["topic"], rel="высокая" if news["rel"] == 2 else "средняя",
            summary=news["summary"] or "(источник не дал описания — смотри по ссылке)",
            slug=slug,
        )
        open(os.path.join(DRAFTS, f"{slug}.md"), "w", encoding="utf-8").write(body)
        made.append(slug)

    json.dump(SEEN, open(SEEN_P, "w", encoding="utf-8"), ensure_ascii=False)

    print("\n--- источники ---")
    for name, note, total in stats:
        print(f"  {name:<28} {note:<20} в фиде {total}")
    print(f"\nсобрано новых релевантных: {len(collected)}")
    print(f"черновиков создано: {len(made)}")
    for s in made[:8]:
        print(f"   articles/drafts/{s}.md")
    if len(made) > 8:
        print(f"   ... ещё {len(made)-8}")

    print("\nПубликация не выполнялась: конвейер останавливается на черновике.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
