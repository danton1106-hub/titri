# -*- coding: utf-8 -*-
"""Загрузка переменных окружения из .env без внешних зависимостей.

Порядок приоритета (первое найденное значение выигрывает):
  1. реальные переменные окружения (GitHub Secrets, export в оболочке);
  2. файл .env в корне проекта;
  3. файл .env.local в корне проекта.

Секреты никогда не попадают в данные или в собранный сайт: здесь только
чтение в память процесса.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (ROOT / ".env", ROOT / ".env.local")
_loaded = False


def _parse(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, raw = line.partition("=")
        name = name.strip()
        value = raw.strip().strip('"').strip("'")
        if name:
            values[name] = value
    return values


def load_dotenv() -> None:
    """Подхватить .env/.env.local, не перезатирая уже заданные переменные."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for path in reversed(CANDIDATES):
        for name, value in _parse(path).items():
            os.environ.setdefault(name, value)


def require(name: str, hint: str = "") -> str:
    """Вернуть обязательную переменную или завершиться понятной ошибкой."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    message = f"{name} не задан."
    if hint:
        message += " " + hint
    raise SystemExit(message)


def optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def allow_cached() -> bool:
    """Разрешить сборку из уже сохранённых данных, когда ключа нет."""
    return os.environ.get("TITRI_ALLOW_CACHED_DATA", "").strip().lower() in {"1", "true", "yes"}
