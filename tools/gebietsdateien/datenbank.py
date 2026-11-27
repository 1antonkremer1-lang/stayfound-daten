"""Schreibt eine Gebietsdatei (SQLite) und packt sie mit gzip. Nur Standardbibliothek.

Aufbau der Datei (Format 1):
  addr(cell INTEGER, lat REAL, lon REAL, text TEXT)            wie adressen.db, ohne Spalte area
  way(id INTEGER PRIMARY KEY, rank, kind, flags, oneway, name, south, west, north, east, nodes BLOB)
                                                               wie strassen.db, ohne Spalte area
  poi(cell INTEGER, lat REAL, lon REAL, kind TEXT, name TEXT, info TEXT)
                                                               Orte auf der Karte (orte.py), wie orte.db (PoiStore),
                                                               ohne Spalte area; cell wie bei addr
  meta(key TEXT PRIMARY KEY, value TEXT)
Indexe wie in der App: addr_cell (OfflineAddressStore), way_south (RoadStore) und poi_cell (PoiStore).
Die Tabelle poi kam spaeter dazu. Das Format bleibt 1: Die App uebernimmt nur die Tabellen, die sie kennt
(INSERT ... SELECT FROM gebiet.addr / gebiet.way), eine zusaetzliche Tabelle stoert aeltere Versionen nicht.
Die Indexe der App auf "area" entfallen, weil es die Spalte in der Datei nicht gibt.
"""

import gzip
import hashlib
import os
import shutil
import sqlite3

FORMAT = 1

# Groesste Datei, die als Anhang einer Veroeffentlichung bei GitHub erlaubt ist, mit etwas Abstand.
MAX_ASSET_BYTES = 2_000_000_000

_BATCH = 50_000


class Gebietsdatei:
    """Sammelt Adressen, Strassen und Orte und schreibt sie in eine neue SQLite-Datei."""

    def __init__(self, path):
        if os.path.exists(path):
            os.remove(path)
        self.path = path
        self.db = sqlite3.connect(path)
        # Die Datei entsteht in einem Rutsch und wird bei einem Fehler weggeworfen: Tempo vor Sicherheit.
        self.db.execute("PRAGMA journal_mode = OFF")
        self.db.execute("PRAGMA synchronous = OFF")
        self.db.execute("CREATE TABLE addr (cell INTEGER, lat REAL, lon REAL, text TEXT)")
        self.db.execute(
            "CREATE TABLE way (id INTEGER PRIMARY KEY, rank INTEGER, kind INTEGER, flags INTEGER, "
            "oneway INTEGER, name TEXT, south REAL, west REAL, north REAL, east REAL, nodes BLOB)"
        )
        self.db.execute("CREATE TABLE poi (cell INTEGER, lat REAL, lon REAL, kind TEXT, name TEXT, info TEXT)")
        self.db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        self._addr = []
        self._way = []
        self._poi = []
        self.addr_count = 0
        self.way_count = 0
        self.poi_count = 0
        # Rechteck um alle Daten: Sued, West, Nord, Ost
        self.bbox = [90.0, 180.0, -90.0, -180.0]

    def _grow(self, south, west, north, east):
        box = self.bbox
        if south < box[0]: box[0] = south
        if west < box[1]: box[1] = west
        if north > box[2]: box[2] = north
        if east > box[3]: box[3] = east

    def add_address(self, row):
        """row = (cell, lat, lon, text), siehe kodierung.address."""
        self._addr.append(row)
        self.addr_count += 1
        self._grow(row[1], row[2], row[1], row[2])
        if len(self._addr) >= _BATCH:
            self._flush()

    def add_way(self, row):
        """row = (id, rank, kind, flags, oneway, name, south, west, north, east, nodes), siehe kodierung.way_row."""
        self._way.append(row)
        self._grow(row[6], row[7], row[8], row[9])
        if len(self._way) >= _BATCH:
            self._flush()

    def add_poi(self, row):
        """row = (cell, lat, lon, kind, name, info), siehe orte.poi_row."""
        self._poi.append(row)
        self.poi_count += 1
        self._grow(row[1], row[2], row[1], row[2])
        if len(self._poi) >= _BATCH:
            self._flush()

    def _flush(self):
        if self._addr:
            self.db.executemany("INSERT INTO addr (cell, lat, lon, text) VALUES (?, ?, ?, ?)", self._addr)
            self._addr = []
        if self._way:
            # Wie in der App: eine doppelte Kennung wird uebergangen.
            self.db.executemany(
                "INSERT OR IGNORE INTO way (id, rank, kind, flags, oneway, name, south, west, north, east, nodes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._way,
            )
            self._way = []
        if self._poi:
            self.db.executemany("INSERT INTO poi (cell, lat, lon, kind, name, info) VALUES (?, ?, ?, ?, ?, ?)", self._poi)
            self._poi = []
        self.db.commit()

    def finish(self, region_id, region_name, osm_timestamp, with_indexes=True):
        """Schreibt Indexe und Angaben zur Datei, raeumt auf und schliesst. @return die Angaben als dict."""
        self._flush()
        self.way_count = self.db.execute("SELECT count(*) FROM way").fetchone()[0]
        if with_indexes:
            self.db.execute("CREATE INDEX addr_cell ON addr (cell)")
            self.db.execute("CREATE INDEX way_south ON way (south)")
            self.db.execute("CREATE INDEX poi_cell ON poi (cell)")
        empty = self.addr_count == 0 and self.way_count == 0 and self.poi_count == 0
        box = [0.0, 0.0, 0.0, 0.0] if empty else self.bbox
        meta = {
            "format": str(FORMAT),
            "region_id": region_id,
            "region_name": region_name,
            "bbox_south": repr(box[0]),
            "bbox_west": repr(box[1]),
            "bbox_north": repr(box[2]),
            "bbox_east": repr(box[3]),
            "osm_timestamp": osm_timestamp,
            "addr_count": str(self.addr_count),
            "way_count": str(self.way_count),
            "poi_count": str(self.poi_count),
            "indexes": "1" if with_indexes else "0",
        }
        self.db.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", sorted(meta.items()))
        self.db.commit()
        self.db.execute("VACUUM")
        self.db.close()
        return meta


def gzip_file(source, target):
    """Packt source nach target. @return (Bytes gepackt, sha256 der gepackten Datei).

    Ohne Dateinamen und Zeitstempel im Kopf, damit gleiche Daten dieselbe Datei ergeben.
    """
    with open(source, "rb") as raw, open(target, "wb") as out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=out, compresslevel=6, mtime=0) as packed:
            shutil.copyfileobj(raw, packed, 1 << 20)
    digest = hashlib.sha256()
    with open(target, "rb") as packed:
        for block in iter(lambda: packed.read(1 << 20), b""):
            digest.update(block)
    return os.path.getsize(target), digest.hexdigest()


def check_size(path, limit=MAX_ASSET_BYTES):
    """Bricht mit klarer Meldung ab, wenn die Datei zu gross fuer einen Anhang ist."""
    size = os.path.getsize(path)
    if size >= limit:
        raise SystemExit(
            "FEHLER: %s ist %d Bytes gross, erlaubt sind weniger als %d Bytes (Grenze fuer Anhaenge "
            "bei GitHub: 2 GB). Bitte die Region in kleinere Gebiete teilen." % (path, size, limit)
        )
    return size
