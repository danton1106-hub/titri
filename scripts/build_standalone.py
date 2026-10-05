# -*- coding: utf-8 -*-
"""Сборка автономной версии главной: CSS и шрифт вшиваются внутрь HTML.

Результат:
  preview/titry-home-standalone.html  — открывается двойным кликом, без сервера
  docs/index.html                     — то же для GitHub Pages
"""
import base64, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def build():
    html = open(os.path.join(ROOT, "preview", "home.html"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "preview", "titry.css"), encoding="utf-8").read()
    ttf = open(os.path.join(ROOT, "assets", "fonts", "Onest-Variable.ttf"), "rb").read()

    b64 = base64.b64encode(ttf).decode()

    # Onest внутрь CSS как data-URI: OFL разрешает встраивание,
    # так шрифт работает без папки fonts и без сети.
    css_in = css.replace(
        "src: url('fonts/Onest-Variable.ttf') format('truetype-variations');",
        f"src: url(data:font/ttf;base64,{b64}) format('truetype-variations');"
    )
    if "base64" not in css_in:
        raise SystemExit("ОШИБКА: шрифт не встроился — проверь строку src в titry.css")

    out = html.replace('<link rel="stylesheet" href="titry.css">',
                       "<style>\n" + css_in + "\n</style>")
    if "<style>" not in out or "titry.css" in out:
        raise SystemExit("ОШИБКА: CSS не встроился")

    # встроенный вариант для Tilda: короткий, без шрифта в base64
    tilda = html.replace('<link rel="stylesheet" href="titry.css">',
                         "<!-- Tilda: подключи титры.css отдельно или вставь в T123 -->\n"
                         "<style>/* ВСТАВЬ СОДЕРЖИМОЕ preview/titry.css */</style>")

    paths = {
        "preview/titry-home-standalone.html": out,
        "docs/index.html": out,
    }
    for rel, data in paths.items():
        p = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(data)
        print(f"{rel}: {os.path.getsize(p)//1024} КБ")

    ext = sorted(set(re.findall(r'(?:src|href)="(https?://[^/"]+)', out)))
    print("внешние источники:", ext)
    assert ext == ["https://image.tmdb.org"], "появился неожиданный внешний источник"
    print("проверка: шрифт вшит, CSS внутри, снаружи только CDN TMDB")

if __name__ == "__main__":
    build()
