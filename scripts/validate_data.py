#!/usr/bin/env python3
"""P0 validation for normalized JSON and editorial inputs."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCHEMAS = DATA / "schemas"
ALLOWED_TYPES = {"movie", "series", "reality", "competition", "game_show", "talk_show", "comedy_show", "web_show", "anime", "special"}
ALLOWED_EVENTS = {"movie_theatrical", "movie_digital", "movie_streaming", "series_premiere", "season_premiere", "episode", "full_season_drop", "show_episode", "reality_episode", "special", "finale"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_schema(errors, filename, data):
    schema = load(SCHEMAS / filename)
    for error in Draft202012Validator(schema).iter_errors(data):
        path = ".".join(str(part) for part in error.absolute_path) or "root"
        errors.append(f"{filename}:{path}: {error.message}")


def secret_leaks(errors):
    """Ни одно значение ключа не должно попасть в собранный сайт."""
    import os

    from env_service import load_dotenv

    load_dotenv()
    secrets = {
        name: os.environ.get(name, "").strip()
        for name in ("TMDB_API_READ_TOKEN", "OMDB_API_KEY")
    }
    secrets = {name: value for name, value in secrets.items() if len(value) >= 12}
    if not secrets:
        return
    docs = ROOT / "docs"
    if not docs.exists():
        return
    for page in docs.rglob("*"):
        if not page.is_file() or page.suffix not in {".html", ".js", ".css", ".json"}:
            continue
        try:
            text = page.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, value in secrets.items():
            if value and value in text:
                errors.append(f"SECRET LEAK: {name} найден в {page.relative_to(ROOT)}")


def main():
    errors = []
    content_document = load(DATA / "content.json")
    events_document = load(DATA / "release_events.json")
    ratings_document = load(DATA / "editorial" / "ratings.json")
    external_ids_document = load(DATA / "external_ids.json")
    validate_schema(errors, "content.schema.json", content_document)
    validate_schema(errors, "release_event.schema.json", events_document)
    validate_schema(errors, "editorial_rating.schema.json", ratings_document)
    validate_schema(errors, "external_ids.schema.json", external_ids_document)
    content = content_document.get("items", [])
    events = events_document.get("items", [])
    ratings = ratings_document.get("items", [])
    ids = set()
    for item in content:
        cid = item.get("id")
        if not cid or cid in ids:
            errors.append(f"duplicate or empty content id: {cid}")
        ids.add(cid)
        if not item.get("title"):
            errors.append(f"content without title: {cid}")
        if item.get("content_type") not in ALLOWED_TYPES:
            errors.append(f"unknown content type: {cid}")
        total, aired = item.get("total_episodes"), item.get("aired_count")
        if total is not None and (not isinstance(total, int) or total < 0):
            errors.append(f"invalid total_episodes: {cid}")
        if aired is not None and (not isinstance(aired, int) or aired < 0):
            errors.append(f"invalid aired_count: {cid}")
        if total is not None and aired is not None and aired > total:
            errors.append(f"aired_count exceeds total_episodes: {cid}")
        next_ep = item.get("next_episode") or {}
        last_ep = item.get("last_episode") or {}
        aired_season = item.get("aired_season")
        if aired is not None and next_ep.get("ep"):
            # Номер следующей серии сравниваем с вышедшими только внутри
            # одного сезона: 21 серия 25-го сезона и серия 1 двадцать шестого
            # — это не противоречие, а новый сезон.
            same_season = (
                next_ep.get("season") is None
                or aired_season is None
                or next_ep.get("season") == aired_season
            )
            if same_season and next_ep["ep"] <= aired:
                errors.append(f"next episode is not after aired count: {cid}")
    for item in events:
        if item.get("content_id") not in ids:
            errors.append(f"release event references missing content: {item.get('id')}")
        if item.get("event_type") not in ALLOWED_EVENTS:
            errors.append(f"unknown release event type: {item.get('id')}")
        if not valid_date(item.get("release_date")):
            errors.append(f"invalid release date: {item.get('id')}")
    for rating in ratings:
        value = rating.get("rating")
        if not isinstance(value, int) or not 1 <= value <= 10:
            errors.append(f"editorial rating must be integer 1..10: {rating.get('content_id')}")
        if rating.get("status") == "published" and not rating.get("comment"):
            errors.append(f"published editorial rating needs comment: {rating.get('content_id')}")
    seen_external = set()
    for record in external_ids_document.get("items", []):
        if record.get("content_id") not in ids:
            errors.append(f"external id record references missing content: {record.get('content_id')}")
        for provider in ("tmdb_id", "tvmaze_id", "imdb_id", "tvdb_id"):
            value = record.get(provider)
            if value is None:
                continue
            marker = (provider, str(value))
            if marker in seen_external:
                errors.append(f"duplicate external id: {provider}={value}")
            seen_external.add(marker)
    secret_leaks(errors)
    if errors:
        print("P0 validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"P0 validation passed: {len(content)} content, {len(events)} release events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
