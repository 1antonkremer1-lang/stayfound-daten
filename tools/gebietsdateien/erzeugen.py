#!/usr/bin/env python3
"""Erzeugt Gebietsdateien fuer die App aus OpenStreetMap-Auszuegen (.osm.pbf).

Aufrufe:
  erzeugen.py bauen <auszug.osm.pbf> --region bayern --ziel out/
        schreibt out/bayern.sqlite.gz und out/bayern.info.json
  erzeugen.py index <ordner> [--ziel index.json]
        fasst alle *.info.json eines Ordners zu index.json zusammen
  erzeugen.py matrix "bayern,berlin" | "deutschland" | "alle"
        gibt die Regionen als JSON-Liste aus (fuer den Arbeitsablauf bei GitHub)
  erzeugen.py url bayern
        gibt die Adresse des Auszugs bei Geofabrik aus

Nur "bauen" braucht das Paket osmium (pyosmium, ab Version 4).
"""

import argparse
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datenbank  # noqa: E402
import kodierung  # noqa: E402
import orte  # noqa: E402
import regionen  # noqa: E402


def read_pbf(path, target, index_spec):
    """Liest den Auszug und fuellt die Gebietsdatei. @return Zeitstempel der Kartendaten (oder "")."""
    import osmium

    # Nur Punkte und Linien: Die App fragt Adressen und Orte als node und way ab, Strassen als way.
    # Relationen (z.B. ein Krankenhaus als Multipolygon) bleiben aus, wie bei der Abfrage in der App.
    # Der Filter laesst nur Objekte mit passender Angabe bis zu Python durch; die Lage aller
    # Punkte merkt sich osmium vorher selbst (with_locations), sonst wuerde es viel zu langsam.
    processor = (
        osmium.FileProcessor(path, osmium.osm.NODE | osmium.osm.WAY)
        .with_locations(index_spec)
        .with_filter(osmium.filter.KeyFilter("addr:housenumber", *orte.KEYS))
    )
    timestamp = processor.header.get("osmosis_replication_timestamp") or processor.header.get("timestamp") or ""
    newest = None

    for obj in processor:
        tags = obj.tags
        if not timestamp:
            # Ohne Angabe im Dateikopf: juengste Aenderung der gelesenen Objekte nehmen.
            changed = obj.timestamp
            if newest is None or changed > newest:
                newest = changed
        if obj.is_node():
            if not obj.location.valid():
                continue
            if "addr:housenumber" in tags:
                row = kodierung.address(obj.location.y / 1e7, obj.location.x / 1e7, _address_tags(tags))
                if row is not None:
                    target.add_address(row)
            kind = orte.classify(tags)
            if kind is not None:
                target.add_poi(orte.poi_row(obj.location.y / 1e7, obj.location.x / 1e7, kind, tags))
            continue
        if not obj.is_way():
            continue

        # Viele Linien (Parkplaetze, Sportplaetze, Feldwege ...) braucht keiner: gar nicht erst die Punkte holen.
        has_address = "addr:housenumber" in tags
        is_road = tags.get("highway") in kodierung.QUERY_HIGHWAYS
        kind = orte.classify(tags)
        if not has_address and not is_road and kind is None:
            continue

        ids, lat_e7, lon_e7 = [], [], []
        complete = True
        for node in obj.nodes:
            location = node.location
            if not location.valid():
                complete = False
                continue
            ids.append(node.ref)
            lat_e7.append(location.y)
            lon_e7.append(location.x)

        if has_address and lat_e7:
            # Wie "out center": Mitte des Rechtecks um den Umriss, auf 7 Stellen ausgegeben.
            lat, lon = kodierung.way_center(lat_e7, lon_e7)
            row = kodierung.address(lat, lon, _address_tags(tags))
            if row is not None:
                target.add_address(row)

        if kind is not None and lat_e7:
            # Ort als Linie (z.B. Spielplatz, Tankstelle): Mitte wie bei den Adressen.
            lat, lon = kodierung.way_center(lat_e7, lon_e7)
            target.add_poi(orte.poi_row(lat, lon, kind, tags))

        # Wie RoadStore.readWay: fehlt ein Punkt, wird die ganze Strasse ausgelassen.
        if complete and is_road:
            row = kodierung.way_row(obj.id, dict((tag.k, tag.v) for tag in tags), ids, lat_e7, lon_e7)
            if row is not None:
                target.add_way(row)

    if not timestamp and newest is not None:
        timestamp = newest.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return timestamp


_ADDRESS_KEYS = ("addr:street", "addr:place", "addr:housenumber", "addr:postcode", "addr:city")


def _address_tags(tags):
    found = {}
    for key in _ADDRESS_KEYS:
        value = tags.get(key)
        if value is not None:
            found[key] = value
    return found


def bauen(args):
    region_id = args.region
    region_name = args.name or (regionen.name(region_id) if region_id in regionen.REGIONEN else region_id)
    os.makedirs(args.ziel, exist_ok=True)
    sqlite_path = os.path.join(args.ziel, region_id + ".sqlite")
    gz_path = sqlite_path + ".gz"
    info_path = os.path.join(args.ziel, region_id + ".info.json")

    target = datenbank.Gebietsdatei(sqlite_path)
    with tempfile.TemporaryDirectory(dir=args.ziel) as scratch:
        # Lage der Punkte: in einer Datei statt im Arbeitsspeicher, damit auch ganze Laender gehen.
        index_spec = args.knotenindex or "sparse_file_array," + os.path.join(scratch, "knoten.idx")
        timestamp = read_pbf(args.pbf, target, index_spec)
    if args.datum:
        timestamp = args.datum
    meta = target.finish(region_id, region_name, timestamp, with_indexes=not args.ohne_index)
    if meta["addr_count"] == "0" and meta["way_count"] == "0":
        raise SystemExit("FEHLER: In %s wurden weder Adressen noch Strassen gefunden." % args.pbf)

    raw_bytes = os.path.getsize(sqlite_path)
    packed_bytes, sha256 = datenbank.gzip_file(sqlite_path, gz_path)
    if not args.sqlite_behalten:
        os.remove(sqlite_path)
    datenbank.check_size(gz_path, args.max_bytes)

    info = {
        "id": region_id,
        "name": region_name,
        "datei": os.path.basename(gz_path),
        "bytes": packed_bytes,
        "sha256": sha256,
        "bbox": [float(meta["bbox_south"]), float(meta["bbox_west"]), float(meta["bbox_north"]), float(meta["bbox_east"])],
        "datum": timestamp,
        "format": datenbank.FORMAT,
        "bytes_entpackt": raw_bytes,
        "adressen": int(meta["addr_count"]),
        "wege": int(meta["way_count"]),
        "orte": int(meta["poi_count"]),
    }
    # Bundeslaender tragen ihr Land, damit die App "Ganz Deutschland" aus den Teilen zusammensetzen kann.
    if regionen.land(region_id):
        info["land"] = regionen.land(region_id)
    with open(info_path, "w", encoding="utf-8") as out:
        json.dump(info, out, ensure_ascii=False, indent=1)
        out.write("\n")
    print(json.dumps(info, ensure_ascii=False))


def index(args):
    """Fasst die Angaben aller Gebiete zusammen. Die Reihenfolge folgt der Tabelle in regionen.py."""
    entries = []
    for file_name in sorted(os.listdir(args.ordner)):
        if not file_name.endswith(".info.json"):
            continue
        with open(os.path.join(args.ordner, file_name), encoding="utf-8") as source:
            entries.append(json.load(source))
    order = list(regionen.REGIONEN)
    entries.sort(key=lambda e: (order.index(e["id"]) if e["id"] in order else len(order), e["id"]))
    result = {
        "format": datenbank.FORMAT,
        "erzeugt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gebiete": entries,
    }
    target = args.ziel or os.path.join(args.ordner, "index.json")
    with open(target, "w", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=1)
        out.write("\n")
    print("%d Gebiete in %s" % (len(entries), target))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gebietsdateien fuer die App erzeugen")
    commands = parser.add_subparsers(dest="befehl", required=True)

    p = commands.add_parser("bauen", help="eine Gebietsdatei aus einem .osm.pbf erzeugen")
    p.add_argument("pbf")
    p.add_argument("--region", required=True, help="Kennung, wird zum Dateinamen")
    p.add_argument("--name", help="Name fuer die Anzeige (sonst aus der Tabelle)")
    p.add_argument("--ziel", default=".", help="Ordner fuer die Ergebnisse")
    p.add_argument("--datum", help="Zeitstempel der Kartendaten, falls er nicht in der Datei steht")
    p.add_argument("--knotenindex", help="Ablage der Punkte fuer osmium, z.B. flex_mem (alles im Arbeitsspeicher)")
    p.add_argument("--ohne-index", action="store_true", help="Indexe weglassen (die App muss sie dann selbst anlegen)")
    p.add_argument("--sqlite-behalten", action="store_true", help="die ungepackte Datei nicht loeschen")
    p.add_argument("--max-bytes", type=int, default=datenbank.MAX_ASSET_BYTES)
    p.set_defaults(run=bauen)

    p = commands.add_parser("index", help="index.json aus allen *.info.json bauen")
    p.add_argument("ordner")
    p.add_argument("--ziel")
    p.set_defaults(run=index)

    p = commands.add_parser("matrix", help="Regionen als JSON-Liste ausgeben")
    p.add_argument("auswahl")
    p.set_defaults(run=lambda a: print(json.dumps(regionen.auswahl(a.auswahl))))

    p = commands.add_parser("url", help="Adresse des Auszugs bei Geofabrik")
    p.add_argument("region")
    p.set_defaults(run=lambda a: print(regionen.url(a.region)))

    args = parser.parse_args(argv)
    try:
        args.run(args)
    except (ValueError, KeyError) as error:
        raise SystemExit("FEHLER: %s" % error)


if __name__ == "__main__":
    main()
