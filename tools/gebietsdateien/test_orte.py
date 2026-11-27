"""Tests fuer orte.py. Die Beispiele in orte_beispiele.txt prueft auch core PoiKindsTest.kt."""

import os
import unittest

import kodierung
import orte

HERE = os.path.dirname(os.path.abspath(__file__))


def beispiele():
    rows = []
    with open(os.path.join(HERE, "orte_beispiele.txt"), encoding="utf-8") as source:
        for line in source:
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            rows.append(line.split("\t"))
    return rows


def angaben(text):
    tags = {}
    for part in text.split(" | "):
        key, value = part.split("=", 1)
        tags[key] = value
    return tags


class OrteTest(unittest.TestCase):
    def test_gemeinsame_beispiele(self):
        rows = beispiele()
        self.assertGreaterEqual(len(rows), 20)
        for row in rows:
            self.assertEqual(len(row), 4, row)
            tags = angaben(row[0])
            kind = orte.classify(tags)
            self.assertEqual(kind, None if row[1] == "-" else row[1], row[0])
            if kind is not None:
                self.assertEqual(orte.name(kind, tags), row[2], row[0])
                self.assertEqual(orte.info(kind, tags), row[3].replace("\\n", "\n"), row[0])

    def test_alle_arten_kommen_vor(self):
        found = {row[1] for row in beispiele()}
        for kind in orte.KINDS:
            self.assertIn(kind, found)

    def test_lange_texte(self):
        tags = {"amenity": "pharmacy", "name": "A\nB " + "x" * 300}
        result = orte.name(orte.PHARMACY, tags)
        self.assertLessEqual(len(result), orte.MAX_TEXT)
        self.assertTrue(result.startswith("A B "))

    def test_zeile(self):
        tags = {"amenity": "toilets", "fee": "no"}
        row = orte.poi_row(50.26120001, 10.96270004, orte.TOILETS, tags)
        self.assertEqual(row, (kodierung.cell_key(50.2612, 10.9627), 50.2612, 10.9627, "toilets", "", "fee=no"))

    def test_filter_schluessel_decken_alle_regeln(self):
        # Jede Regel in classify braucht einen dieser Schluessel, sonst kaeme das Objekt nie bei Python an.
        for row in beispiele():
            if row[1] != "-":
                self.assertTrue(any(key in angaben(row[0]) for key in orte.KEYS), row[0])


if __name__ == "__main__":
    unittest.main()
