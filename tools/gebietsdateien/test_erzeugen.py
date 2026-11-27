"""Tests fuer das Schreiben der Datei und den ganzen Ablauf mit einem winzigen Kartenauszug.

Der Ablauf-Test braucht das Paket osmium und wird ohne es uebersprungen.
"""

import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest

import datenbank
import erzeugen
import kodierung
import orte
import regionen

try:
    import osmium  # noqa: F401
    HAS_OSMIUM = True
except ImportError:
    HAS_OSMIUM = False

# Kleiner Auszug: 2 Adressen als Punkt (eine unbrauchbar), 1 Gebaeude mit Adresse, 4 Linien mit highway
# (eine nicht abgefragte Art, eine mit fehlendem Punkt), 1 Relation mit Adresse (zaehlt nicht).
# Orte: Apotheke als Punkt, Spielplatz als Linie, Wartehaeuschen (kein Ort), Parkplatz als Linie (kein Ort),
# Krankenhaus als Relation (bleibt aus).
FIXTURE = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.0000000" lon="10.0000000"/>
  <node id="2" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.0010000" lon="10.0020000"/>
  <node id="3" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.0020000" lon="10.0020000"/>
  <node id="10" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.2612000" lon="10.9627000">
    <tag k="addr:street" v="Marktplatz"/>
    <tag k="addr:housenumber" v="3"/>
    <tag k="addr:postcode" v="96450"/>
    <tag k="addr:city" v="Coburg"/>
  </node>
  <node id="11" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.2613000" lon="10.9628000">
    <tag k="addr:housenumber" v="5"/>
  </node>
  <node id="20" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.0000000" lon="10.0000000"/>
  <node id="21" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.0002000" lon="10.0000000"/>
  <node id="22" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.0002000" lon="10.0004000"/>
  <node id="23" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.0001000" lon="10.0000500"/>
  <way id="100" version="1" timestamp="2024-02-03T04:05:06Z">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/>
    <tag k="highway" v="residential"/>
    <tag k="name" v="Marktplatz"/>
    <tag k="oneway" v="yes"/>
  </way>
  <way id="101" version="1" timestamp="2024-01-01T00:00:00Z">
    <nd ref="1"/><nd ref="3"/>
    <tag k="highway" v="motorway"/>
    <tag k="ref" v="A 73"/>
  </way>
  <way id="102" version="1" timestamp="2024-01-01T00:00:00Z">
    <nd ref="1"/><nd ref="2"/>
    <tag k="highway" v="construction"/>
  </way>
  <way id="103" version="1" timestamp="2024-01-01T00:00:00Z">
    <nd ref="1"/><nd ref="999"/>
    <tag k="highway" v="service"/>
  </way>
  <way id="200" version="1" timestamp="2024-01-01T00:00:00Z">
    <nd ref="20"/><nd ref="21"/><nd ref="22"/><nd ref="23"/><nd ref="20"/>
    <tag k="building" v="yes"/>
    <tag k="addr:place" v="Oberdorf"/>
    <tag k="addr:housenumber" v="7"/>
  </way>
  <node id="30" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.2600000" lon="10.9600000">
    <tag k="amenity" v="pharmacy"/>
    <tag k="name" v="Löwen-Apotheke"/>
    <tag k="opening_hours" v="Mo-Fr 08:00-18:00"/>
  </node>
  <node id="31" version="1" timestamp="2024-01-01T00:00:00Z" lat="50.2601000" lon="10.9601000">
    <tag k="amenity" v="shelter"/>
    <tag k="shelter_type" v="public_transport"/>
  </node>
  <way id="210" version="1" timestamp="2024-01-01T00:00:00Z">
    <nd ref="20"/><nd ref="21"/><nd ref="22"/><nd ref="20"/>
    <tag k="leisure" v="playground"/>
  </way>
  <way id="211" version="1" timestamp="2024-01-01T00:00:00Z">
    <nd ref="20"/><nd ref="21"/><nd ref="22"/><nd ref="20"/>
    <tag k="amenity" v="parking"/>
  </way>
  <relation id="301" version="1" timestamp="2024-01-01T00:00:00Z">
    <member type="way" ref="211" role="outer"/>
    <tag k="type" v="multipolygon"/>
    <tag k="amenity" v="hospital"/>
  </relation>
  <relation id="300" version="1" timestamp="2024-01-01T00:00:00Z">
    <member type="way" ref="200" role="outer"/>
    <tag k="type" v="multipolygon"/>
    <tag k="addr:street" v="Nirgendwo"/>
    <tag k="addr:housenumber" v="1"/>
  </relation>
</osm>
"""


class DatenbankTest(unittest.TestCase):
    def test_schema_indexe_meta(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "x.sqlite")
            target = datenbank.Gebietsdatei(path)
            target.add_address(kodierung.address(50.2612, 10.9627, {"addr:street": "Marktplatz", "addr:housenumber": "3"}))
            row = kodierung.way_row(7, {"highway": "residential"}, [1, 2], [500000000, 500010000], [100000000, 100020000])
            target.add_way(row)
            target.add_way(row)  # doppelte Kennung wird uebergangen
            target.add_poi(orte.poi_row(50.1, 10.5, orte.TOILETS, {"amenity": "toilets", "fee": "no"}))
            meta = target.finish("x", "Testgebiet", "2024-01-01T00:00:00Z")
            self.assertEqual(meta["way_count"], "1")

            db = sqlite3.connect(path)
            columns = lambda table: [(r[1], r[2]) for r in db.execute("PRAGMA table_info(%s)" % table)]
            self.assertEqual(columns("addr"), [("cell", "INTEGER"), ("lat", "REAL"), ("lon", "REAL"), ("text", "TEXT")])
            self.assertEqual(
                [c[0] for c in columns("way")],
                ["id", "rank", "kind", "flags", "oneway", "name", "south", "west", "north", "east", "nodes"],
            )
            self.assertEqual(columns("poi"), [
                ("cell", "INTEGER"), ("lat", "REAL"), ("lon", "REAL"), ("kind", "TEXT"), ("name", "TEXT"), ("info", "TEXT"),
            ])
            indexes = dict(db.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"))
            # Wortgleich mit OfflineAddressStore.kt und RoadStore.kt
            self.assertEqual(indexes, {
                "addr_cell": "CREATE INDEX addr_cell ON addr (cell)",
                "way_south": "CREATE INDEX way_south ON way (south)",
                "poi_cell": "CREATE INDEX poi_cell ON poi (cell)",
            })
            self.assertEqual(db.execute("SELECT * FROM addr").fetchall(), [(150261210962, 50.2612, 10.9627, "Marktplatz 3")])
            self.assertEqual(db.execute("SELECT typeof(nodes), length(nodes) FROM way").fetchall(), [("blob", 32)])
            self.assertEqual(db.execute("SELECT * FROM poi").fetchall(), [(150100210500, 50.1, 10.5, "toilets", "", "fee=no")])
            self.assertEqual(dict(db.execute("SELECT key, value FROM meta")), {
                "format": "1", "region_id": "x", "region_name": "Testgebiet",
                "bbox_south": "50.0", "bbox_west": "10.0", "bbox_north": "50.2612", "bbox_east": "10.9627",
                "osm_timestamp": "2024-01-01T00:00:00Z", "addr_count": "1", "way_count": "1", "poi_count": "1",
                "indexes": "1",
            })
            db.close()

    def test_gzip_und_pruefsumme(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "a")
            with open(source, "wb") as out:
                out.write(b"abc" * 1000)
            size, sha = datenbank.gzip_file(source, source + ".gz")
            with open(source + ".gz", "rb") as packed:
                data = packed.read()
            self.assertEqual(size, len(data))
            self.assertEqual(sha, hashlib.sha256(data).hexdigest())
            self.assertEqual(gzip.decompress(data), b"abc" * 1000)
            # Gleiche Daten ergeben dieselbe Datei
            self.assertEqual(datenbank.gzip_file(source, source + ".2.gz"), (size, sha))

    def test_zu_gross_bricht_ab(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "a")
            with open(path, "wb") as out:
                out.write(b"x" * 100)
            self.assertEqual(datenbank.check_size(path, 101), 100)
            with self.assertRaises(SystemExit) as raised:
                datenbank.check_size(path, 100)
            self.assertIn("FEHLER", str(raised.exception))


class RegionenTest(unittest.TestCase):
    def test_tabelle(self):
        self.assertEqual(len(regionen.REGIONEN), 19)
        self.assertEqual(regionen.url("bayern"), "https://download.geofabrik.de/europe/germany/bayern-latest.osm.pbf")
        self.assertEqual(regionen.url("germany"), "https://download.geofabrik.de/europe/germany-latest.osm.pbf")
        self.assertEqual(regionen.url("austria"), "https://download.geofabrik.de/europe/austria-latest.osm.pbf")
        for region_id in regionen.REGIONEN:
            self.assertRegex(region_id, "^[a-z0-9-]+$")

    def test_auswahl(self):
        self.assertEqual(regionen.auswahl("bayern"), ["bayern"])
        self.assertEqual(regionen.auswahl(" Bayern, berlin bayern "), ["bayern", "berlin"])
        self.assertEqual(regionen.auswahl("alle"), list(regionen.REGIONEN))
        self.assertEqual(regionen.auswahl(""), list(regionen.REGIONEN))
        self.assertEqual(regionen.auswahl("deutschland"), regionen.BUNDESLAENDER)
        self.assertEqual(regionen.auswahl("Deutschland, bayern, austria"), regionen.BUNDESLAENDER + ["austria"])
        self.assertEqual(len(regionen.BUNDESLAENDER), 16)
        self.assertEqual(regionen.land("bayern"), "de")
        self.assertEqual(regionen.land("germany"), "")
        self.assertEqual(regionen.land("austria"), "")
        with self.assertRaises(ValueError):
            regionen.auswahl("bayern,atlantis")


@unittest.skipUnless(HAS_OSMIUM, "Paket osmium fehlt")
class AblaufTest(unittest.TestCase):
    def test_vom_auszug_bis_zum_index(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "klein.osm")
            with open(source, "w", encoding="utf-8") as out:
                out.write(FIXTURE)
            ziel = os.path.join(folder, "out")
            erzeugen.main(["bauen", source, "--region", "bayern", "--ziel", ziel])
            self.assertEqual(sorted(os.listdir(ziel)), ["bayern.info.json", "bayern.sqlite.gz"])

            with open(os.path.join(ziel, "bayern.sqlite.gz"), "rb") as packed:
                data = packed.read()
            sqlite_path = os.path.join(folder, "bayern.sqlite")
            with open(sqlite_path, "wb") as out:
                out.write(gzip.decompress(data))
            db = sqlite3.connect(sqlite_path)

            # Adressen: Punkt 10 und Gebaeude 200 (Mitte des Rechtecks). Punkt 11 hat keine Strasse,
            # die Relation 300 fragt die App nicht ab.
            self.assertEqual(db.execute("SELECT cell, lat, lon, text FROM addr ORDER BY text").fetchall(), [
                (150261210962, 50.2612, 10.9627, "Marktplatz 3, 96450 Coburg"),
                (150000210000, 50.0001, 10.0002, "Oberdorf 7"),
            ])
            # Strassen: 100 und 101. 102 ist keine abgefragte Art, bei 103 fehlt ein Punkt.
            ways = db.execute(
                "SELECT id, rank, kind, flags, oneway, name, south, west, north, east, hex(nodes) FROM way ORDER BY id"
            ).fetchall()
            self.assertEqual(ways, [
                (100, 1, 6, 0, 1, "Marktplatz", 50.0, 10.0, 50.002, 10.002,
                 "00000000000000011DCD650005F5E100" "00000000000000021DCD8C1005F62F20" "00000000000000031DCDB32005F62F20"),
                (101, 3, 0, 6, 1, "A 73", 50.0, 10.0, 50.002, 10.002,
                 "00000000000000011DCD650005F5E100" "00000000000000031DCDB32005F62F20"),
            ])
            # Orte: Apotheke (Punkt) und Spielplatz (Linie, Mitte des Rechtecks). Wartehaeuschen und Parkplatz sind
            # keine Orte, das Krankenhaus als Relation bleibt aus.
            self.assertEqual(db.execute("SELECT cell, lat, lon, kind, name, info FROM poi ORDER BY kind").fetchall(), [
                (150260210960, 50.26, 10.96, "pharmacy", "Löwen-Apotheke", "oh=Mo-Fr 08:00-18:00"),
                (150000210000, 50.0001, 10.0002, "playground", "", ""),
            ])
            meta = dict(db.execute("SELECT key, value FROM meta"))
            db.close()
            self.assertEqual(meta["region_name"], "Bayern")
            self.assertEqual(meta["addr_count"], "2")
            self.assertEqual(meta["way_count"], "2")
            self.assertEqual(meta["poi_count"], "2")
            # Kein Zeitstempel im Dateikopf: juengste Aenderung der gelesenen Objekte
            self.assertEqual(meta["osm_timestamp"], "2024-02-03T04:05:06Z")

            erzeugen.main(["index", ziel])
            with open(os.path.join(ziel, "index.json"), encoding="utf-8") as source_file:
                index = json.load(source_file)
            self.assertEqual(index["format"], 1)
            self.assertEqual(len(index["gebiete"]), 1)
            entry = index["gebiete"][0]
            self.assertEqual(
                sorted(entry),
                ["adressen", "bbox", "bytes", "bytes_entpackt", "datei", "datum", "format", "id", "land", "name", "orte",
                 "sha256", "wege"],
            )
            self.assertEqual(entry["id"], "bayern")
            self.assertEqual(entry["datei"], "bayern.sqlite.gz")
            self.assertEqual(entry["bytes"], len(data))
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(entry["bbox"], [50.0, 10.0, 50.2612, 10.9627])
            self.assertEqual(entry["datum"], "2024-02-03T04:05:06Z")
            self.assertEqual(entry["orte"], 2)
            self.assertEqual(entry["land"], "de")

    def test_leerer_auszug_ist_ein_fehler(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "leer.osm")
            with open(source, "w", encoding="utf-8") as out:
                out.write("<?xml version='1.0'?><osm version=\"0.6\"><node id=\"1\" lat=\"1\" lon=\"1\"/></osm>")
            with self.assertRaises(SystemExit):
                erzeugen.main(["bauen", source, "--region", "x", "--ziel", os.path.join(folder, "out")])


if __name__ == "__main__":
    unittest.main()
