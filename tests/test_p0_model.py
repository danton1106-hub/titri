import json
import re
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build import EPISODE_WORD, CONTENT_TYPES, progress
from time_service import parse_local_date, relative_day


class TimeServiceTests(unittest.TestCase):
    def test_date_only_is_a_date_not_a_utc_timestamp(self):
        self.assertEqual(parse_local_date("2026-10-02"), date(2026, 10, 2))

    def test_relative_day_uses_given_moscow_business_day(self):
        self.assertEqual(relative_day("2026-10-03", date(2026, 10, 2)), "завтра")


class ContentModelTests(unittest.TestCase):
    def test_required_p0_content_types_have_labels(self):
        expected = {"movie", "series", "reality", "competition", "game_show", "talk_show", "comedy_show", "web_show", "anime", "special"}
        self.assertTrue(expected.issubset(CONTENT_TYPES))
        self.assertTrue(expected.issubset(EPISODE_WORD))

    def test_unknown_total_is_not_replaced_with_zero(self):
        item = {"content_type": "reality", "total_episodes": None, "aired_count": 47}
        self.assertIn("пока не объявлено", progress(item))
        self.assertIn("47", progress(item))

    def test_next_episode_is_not_used_as_aired_count(self):
        item = {"content_type": "series", "total_episodes": 13, "aired_count": 3, "next_episode": {"ep": 4}}
        self.assertIn("3", progress(item))
        self.assertNotIn("4 из 13", progress(item))


class SeasonModelTests(unittest.TestCase):
    """Сезонный progress не смешивает текущий сезон со всем сериалом."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_season_and_episode_models_are_written(self):
        seasons = json.loads((self.root / "data" / "seasons.json").read_text(encoding="utf-8"))["items"]
        episodes = json.loads((self.root / "data" / "episodes.json").read_text(encoding="utf-8"))["items"]
        self.assertGreater(len(seasons), 0)
        self.assertGreater(len(episodes), 0)
        for season in seasons:
            self.assertTrue(season["id"].startswith(season["content_id"] + ":season:"))
            total, aired = season.get("total_episodes"), season.get("aired_count")
            if total is not None and aired is not None:
                self.assertLessEqual(aired, total)

    def test_global_episode_numbers_do_not_become_season_records(self):
        episodes = json.loads((self.root / "data" / "episodes.json").read_text(encoding="utf-8"))["items"]
        self.assertFalse(any(item["episode_number"] > 100 for item in episodes))

    def test_home_calendar_renders_current_week_and_month_link(self):
        home = self.root / "docs" / "index.html"
        if not home.exists():
            self.skipTest("docs/index.html отсутствует")
        text = home.read_text(encoding="utf-8")
        self.assertIn('class="calendar-spotlight', text)
        self.assertIn("28 сентября — 4 октября", text)
        self.assertIn("Весь октябрь", text)
        self.assertIn("2026", text)


class SmokeHtml(unittest.TestCase):
    """Проверки собранного HTML: артефакты шаблонов не должны попадать в production."""

    @classmethod
    def setUpClass(cls):
        cls.docs = Path(__file__).resolve().parents[1] / "docs"
        cls.home = cls.docs / "index.html"

    def test_no_template_artifacts(self):
        if not self.home.exists():
            self.skipTest("docs/index.html отсутствует, сначала запустите scripts/build.py")
        text = self.home.read_text(encoding="utf-8")
        for artifact in ("$01", "$02", "$03", "''"):
            self.assertNotIn(artifact, text, f"в собранной главной остался артефакт {artifact}")

    def test_single_h1_and_unique_h2_per_section(self):
        if not self.home.exists():
            self.skipTest("docs/index.html отсутствует")
        text = self.home.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"<h1\b", text)), 1, "на главной должен быть ровно один H1")
        for block in re.findall(r'<div class="section-head">.*?</div></div>', text, re.S):
            self.assertLessEqual(len(re.findall(r"<h2\b", block)), 1, "в заголовке раздела два H2")

    def test_internal_nav_has_no_dead_links(self):
        if not self.home.exists():
            self.skipTest("docs/index.html отсутствует")
        text = self.home.read_text(encoding="utf-8")
        self.assertNotIn('href="#"', text, "внутренняя ссылка ведёт в никуда")


if __name__ == "__main__":
    unittest.main()
