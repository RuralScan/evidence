"""Keep citations as plain text when embedding the read-only publication."""

from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "recipe_release")]
from public_workbook.publish import render  # noqa: E402


class DataElement(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.text = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts.append(dict(attrs))
            self.inside = dict(attrs).get("id") == "publication"

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.text.append(data)


class EmbeddedDataTests(unittest.TestCase):
    def test_markup_in_a_citation_survives_as_data(self):
        records = {"citation": 'A & B <section> "</script>" and café'}
        template = (HERE / "workbook.html").read_text(encoding="utf-8")
        result = DataElement()
        result.feed(render(template, records))
        self.assertEqual(json.loads("".join(result.text)), records)
        self.assertEqual(len(result.scripts), 2)
        self.assertFalse(any("src" in script for script in result.scripts))

    def test_missing_or_duplicate_publication_slots_fail(self):
        for template in ("no data", "@@DATA@@@@DATA@@"):
            with self.assertRaisesRegex(ValueError, "one publication"):
                render(template, {})
