"""Kodierungen der Gebietsdateien, 1:1 aus dem Kotlin-Code der App nachgebaut.

Diese Datei braucht nur die Standardbibliothek. Jede Funktion nennt die Kotlin-Stelle,
die sie spiegelt. Wer dort etwas aendert, muss es hier genauso aendern (und umgekehrt).

Quellen:
  core/src/main/kotlin/de/gpsstandort/core/OfflineAddresses.kt  (Adressen)
  core/src/main/kotlin/de/gpsstandort/core/Roads.kt             (Strassen)
  app/src/main/java/de/gpsstandort/jetzt/RoadStore.kt           (Spalten der Tabelle way)
"""

import math
import struct

# --------------------------------------------------------------------------------------
# Adressen (OfflineAddresses.kt)
# --------------------------------------------------------------------------------------

# OfflineAddresses.CELL: etwa 110 m in Nord-Sued-Richtung
CELL = 0.001


def cell_key(latitude, longitude):
    """Fach einer Adresse. Spiegelt OfflineAddresses.cellKey und OfflineAddresses.key:

        key(floor(latitude / CELL).toLong(), floor(longitude / CELL).toLong())
        key(row, column) = (row + 100_000L) * 1_000_000L + (column + 200_000L)

    Wichtig: geteilt wird durch 0.001 (nicht mit 1000 malgenommen), sonst kippen
    Werte genau auf einer Fachgrenze in ein anderes Fach.
    """
    row = math.floor(latitude / CELL)
    column = math.floor(longitude / CELL)
    return (row + 100_000) * 1_000_000 + (column + 200_000)


def csv_line(latitude, longitude, tags):
    """Baut die Zeile, die der Kartendienst fuer OfflineAddresses.query liefern wuerde:

        Breite|Laenge|addr:street|addr:place|addr:housenumber|addr:postcode|addr:city

    Breite und Laenge mit 7 Nachkommastellen, fehlende Angaben leer.
    """
    fields = [
        "%.7f" % latitude,
        "%.7f" % longitude,
        tags.get("addr:street", ""),
        tags.get("addr:place", ""),
        tags.get("addr:housenumber", ""),
        tags.get("addr:postcode", ""),
        tags.get("addr:city", ""),
    ]
    return "|".join(fields)


def parse_line(line):
    """Liest eine Zeile wie OfflineAddresses.parseLine.

    @return (latitude, longitude, text) oder None.
    Gespiegelt: mindestens 5 Felder; Strasse = addr:street, sonst addr:place; Strasse und
    Hausnummer muessen da sein; Ort = PLZ und Ort mit Leerzeichen verbunden;
    Text = "Strasse Nummer" oder "Strasse Nummer, PLZ Ort".
    """
    # Die App liest zeilenweise: nach einem Zeilenumbruch in einer Angabe zaehlt nur der Anfang.
    line = line.split("\n", 1)[0].rstrip("\r")
    parts = line.split("|")
    if len(parts) < 5:
        return None
    try:
        latitude = float(parts[0].strip())
        longitude = float(parts[1].strip())
    except ValueError:
        return None
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None
    street = parts[2].strip() or parts[3].strip()
    number = parts[4].strip()
    if not street or not number:
        return None
    town_parts = [
        parts[5].strip() if len(parts) > 5 else "",
        parts[6].strip() if len(parts) > 6 else "",
    ]
    town = " ".join(p for p in town_parts if p)
    text = "%s %s" % (street, number) if not town else "%s %s, %s" % (street, number, town)
    return latitude, longitude, text


def address(latitude, longitude, tags):
    """Eine Zeile der Tabelle addr: (cell, lat, lon, text) oder None.

    Geht bewusst den Umweg ueber csv_line + parse_line, damit auch Sonderfaelle
    (z.B. ein "|" in einer Angabe) genauso herauskommen wie heute in der App.
    """
    parsed = parse_line(csv_line(latitude, longitude, tags))
    if parsed is None:
        return None
    lat, lon, text = parsed
    return cell_key(lat, lon), lat, lon, text


def way_center(lat_e7_list, lon_e7_list):
    """Mittelpunkt eines Gebaeude-Umrisses wie "out center" des Kartendienstes:
    Mitte des umschliessenden Rechtecks (nicht der Schwerpunkt).

    Eingabe: Koordinaten als ganze Zahlen in 1e-7 Grad. @return (lat, lon) als Gleitkommazahl.
    """
    lat = (min(lat_e7_list) / 1e7 + max(lat_e7_list) / 1e7) / 2
    lon = (min(lon_e7_list) / 1e7 + max(lon_e7_list) / 1e7) / 2
    return lat, lon


# --------------------------------------------------------------------------------------
# Strassen (Roads.kt)
# --------------------------------------------------------------------------------------

# Roads.NO_CAR usw.
NO_CAR = 1
NO_BIKE = 2
NO_FOOT = 4
ROUNDABOUT = 8

# Roads.kinds: die Stelle in der Liste ist die Nummer der Strassenart
KINDS = [
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "living_street", "service", "track", "path", "footway", "cycleway", "pedestrian", "steps",
]

# Roads.query: genau diese highway-Werte fragt die App beim Kartendienst an
QUERY_HIGHWAYS = frozenset(KINDS + [
    "road", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
])

_CLOSED = ("no", "private")
_MOTOR_BLOCKED = ("no", "private", "agricultural", "forestry")


def kind_of(highway):
    """Nummer der Strassenart, -1 wenn unbekannt. Spiegelt Roads.kindOf:
    "road" -> 5, sonst Stelle in der Liste nach Abschneiden von "_link"."""
    if highway == "road":
        return 5
    if highway.endswith("_link"):
        highway = highway[: -len("_link")]
    try:
        return KINDS.index(highway)
    except ValueError:
        return -1


def rank(kind):
    """Wichtigkeit. Spiegelt Roads.rank: 0..3 -> 3; 4,5 -> 2; 6,7,8,12 -> 1; sonst 0."""
    if kind in (0, 1, 2, 3):
        return 3
    if kind in (4, 5):
        return 2
    if kind in (6, 7, 8, 12):
        return 1
    return 0


def from_tags(tags, node_count):
    """Art, Verbote, Einbahn und Name einer Strasse. Spiegelt Roads.fromTags.

    @return (kind, flags, oneway, name) oder None, wenn die Strasse nicht nutzbar ist.
    Die Pruefung der Punktlisten (gleich lang) entfaellt hier: es gibt nur eine Liste.
    """
    highway = tags.get("highway", "")
    kind = kind_of(highway)
    if kind < 0 or node_count < 2:
        return None
    if tags.get("area") == "yes":
        return None
    access = tags.get("access")
    flags = 0

    # val motor = tags["motor_vehicle"] ?: tags["vehicle"]
    motor = tags.get("motor_vehicle")
    if motor is None:
        motor = tags.get("vehicle")
    car_blocked = (
        motor in _MOTOR_BLOCKED
        or (access in _CLOSED and motor != "yes")
        or (kind == 9 and motor != "yes")
        or kind >= 10
    )
    if car_blocked:
        flags |= NO_CAR

    bicycle = tags.get("bicycle")
    bike_blocked = (
        bicycle == "no"
        or (access in _CLOSED and bicycle != "yes" and bicycle != "designated")
        or kind <= 1
        or (tags.get("vehicle") in _CLOSED and bicycle is None)
        or kind == 14
    )
    if bike_blocked:
        flags |= NO_BIKE

    foot = tags.get("foot")
    foot_blocked = (
        foot == "no"
        or (access in _CLOSED and foot != "yes" and foot != "designated")
        or kind <= 1
    )
    if foot_blocked:
        flags |= NO_FOOT

    junction = tags.get("junction")
    is_roundabout = junction == "roundabout" or junction == "circular"
    if is_roundabout:
        flags |= ROUNDABOUT

    oneway_tag = tags.get("oneway")
    if oneway_tag in ("yes", "true", "1"):
        oneway = 1
    elif oneway_tag in ("-1", "reverse"):
        oneway = -1
    elif oneway_tag == "no":
        oneway = 0
    else:
        # if (isRoundabout || kind == 0 && !highway.endsWith("_link")) 1 else 0
        oneway = 1 if (is_roundabout or (kind == 0 and not highway.endswith("_link"))) else 0

    # val name = tags["name"] ?: tags["ref"].orEmpty()
    name = tags.get("name")
    if name is None:
        name = tags.get("ref", "")
    return kind, flags, oneway, name


def round_to_int(value):
    """Wie Kotlin Double.roundToInt(): zur naechsten ganzen Zahl, bei genau .5 nach oben
    (auch bei negativen Zahlen: -2.5 -> -2), begrenzt auf den Bereich eines Int."""
    if math.isnan(value):
        raise ValueError("NaN kann nicht gerundet werden")
    if value >= 2147483647.0:
        return 2147483647
    if value <= -2147483648.0:
        return -2147483648
    lower = math.floor(value)
    return lower + 1 if value - lower >= 0.5 else lower


def encode_nodes(node_ids, lats, lons):
    """Packt die Punkte einer Strasse ein. Spiegelt Roads.encodeNodes:

        buffer.putLong(nodeIds[i])                    8 Byte, hoechstwertiges Byte zuerst
        buffer.putInt((lats[i] * 1e7).roundToInt())   4 Byte
        buffer.putInt((lons[i] * 1e7).roundToInt())   4 Byte

    java.nio.ByteBuffer schreibt ohne weitere Angabe big-endian, mit Vorzeichen.
    """
    out = bytearray()
    for node_id, lat, lon in zip(node_ids, lats, lons):
        out += struct.pack(">qii", node_id, round_to_int(lat * 1e7), round_to_int(lon * 1e7))
    return bytes(out)


def decode_nodes(blob):
    """Gegenstueck zu encode_nodes, spiegelt Roads.decode. @return (ids, lats, lons)."""
    ids, lats, lons = [], [], []
    for offset in range(0, len(blob) // 16 * 16, 16):
        node_id, lat, lon = struct.unpack_from(">qii", blob, offset)
        ids.append(node_id)
        lats.append(lat / 1e7)
        lons.append(lon / 1e7)
    return ids, lats, lons


def way_row(way_id, tags, node_ids, lat_e7_list, lon_e7_list):
    """Eine Zeile der Tabelle way, oder None. Spiegelt RoadStore.readAnswer (Spalten) und
    die Auswahl aus Roads.query.

    Eingabe: Koordinaten als ganze Zahlen in 1e-7 Grad, wie sie in den Kartendaten stehen.
    @return (id, rank, kind, flags, oneway, name, south, west, north, east, nodes)
    """
    if tags.get("highway") not in QUERY_HIGHWAYS:
        return None
    parsed = from_tags(tags, len(node_ids))
    if parsed is None:
        return None
    kind, flags, oneway, name = parsed
    # Die App liest die Koordinaten als Dezimalzahl mit 7 Stellen: das ist dieselbe Gleitkommazahl.
    lats = [v / 1e7 for v in lat_e7_list]
    lons = [v / 1e7 for v in lon_e7_list]
    return (
        way_id, rank(kind), kind, flags, oneway, name,
        min(lats), min(lons), max(lats), max(lons),
        encode_nodes(node_ids, lats, lons),
    )
