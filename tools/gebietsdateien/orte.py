"""Orte auf der Karte (Apotheke, WC, Spielplatz ...): Erkennen aus den Angaben von OpenStreetMap.

1:1 nachgebaut aus core/src/main/kotlin/de/gpsstandort/core/PoiKinds.kt (classify, name, info).
Wer dort etwas aendert, muss es hier genauso aendern (und umgekehrt). Beide Seiten pruefen dieselben
Beispiele aus orte_beispiele.txt (test_orte.py und PoiKindsTest.kt).

Die Funktionen lesen die Angaben nur mit tags.get(...): Das geht mit einem dict und direkt mit der
Angabenliste von osmium, ohne sie vorher umzubauen (das spart beim Lesen ganzer Laender viel Zeit).
"""

import kodierung

# Schluessel der Arten (PoiKinds.kt). Polizei fehlt hier: Sie kommt aus der festen Liste der App.
HOSPITAL = "hospital"
PHARMACY = "pharmacy"
DEFIBRILLATOR = "defibrillator"
EMERGENCY_POINT = "emergency_point"
FUEL = "fuel"
CHARGING_CAR = "charging_car"
CHARGING_BIKE = "charging_bike"
BICYCLE_REPAIR = "bicycle_repair"
TRANSIT_STOP = "transit_stop"
TOILETS = "toilets"
DRINKING_WATER = "drinking_water"
SHELTER = "shelter"
VENDING = "vending"
SKATEPARK = "skatepark"
FITNESS = "fitness"
PLAYGROUND = "playground"

KINDS = (
    HOSPITAL, PHARMACY, DEFIBRILLATOR, EMERGENCY_POINT, FUEL, CHARGING_CAR, CHARGING_BIKE, BICYCLE_REPAIR,
    TRANSIT_STOP, TOILETS, DRINKING_WATER, SHELTER, VENDING, SKATEPARK, FITNESS, PLAYGROUND,
)

# Nur Objekte mit einer dieser Angaben koennen ein Ort sein (fuer den Filter beim Lesen).
KEYS = ("amenity", "emergency", "leisure", "highway", "railway", "public_transport")

_AMENITY = {
    "hospital": HOSPITAL,
    "pharmacy": PHARMACY,
    "fuel": FUEL,
    "bicycle_repair_station": BICYCLE_REPAIR,
    "toilets": TOILETS,
    "drinking_water": DRINKING_WATER,
    "vending_machine": VENDING,
}
_TRANSIT_RAILWAY = ("station", "halt", "tram_stop")
_LEISURE = {"skatepark": SKATEPARK, "fitness_station": FITNESS, "playground": PLAYGROUND}

# PoiKinds.MAX_TEXT
MAX_TEXT = 120

VENDING_NAMES = {
    "drinks": "Getränke",
    "coffee": "Kaffee",
    "cigarettes": "Zigaretten",
    "sweets": "Süßigkeiten",
    "food": "Essen",
    "snacks": "Snacks",
    "water": "Wasser",
    "milk": "Milch",
    "eggs": "Eier",
    "bread": "Brot",
    "ice_cream": "Eis",
    "parking_tickets": "Parkscheine",
    "public_transport_tickets": "Fahrkarten",
    "condoms": "Kondome",
    "excrement_bags": "Hundekotbeutel",
    "bicycle_tube": "Fahrradschläuche",
    "newspapers": "Zeitungen",
    "stamps": "Briefmarken",
}


def classify(tags):
    """Art eines Objekts oder None. Spiegelt PoiKinds.classify (die Reihenfolge der Pruefungen zaehlt)."""
    access = tags.get("access")
    if access == "private" or access == "no":
        return None
    if tags.get("emergency") == "defibrillator":
        return DEFIBRILLATOR
    amenity = tags.get("amenity")
    if amenity is not None:
        found = _AMENITY.get(amenity)
        if found is not None:
            return found
        if amenity == "charging_station":
            if tags.get("bicycle") == "yes" and tags.get("motorcar") != "yes":
                return CHARGING_BIKE
            return CHARGING_CAR
        # Wartehaeuschen an Haltestellen sind keine Schutzhuetten; die Haltestelle prueft der naechste Schritt.
        if amenity == "shelter" and tags.get("shelter_type") != "public_transport":
            return SHELTER
    highway = tags.get("highway")
    if highway == "emergency_access_point":
        return EMERGENCY_POINT
    if highway == "bus_stop" or tags.get("railway") in _TRANSIT_RAILWAY or tags.get("public_transport") == "station":
        return TRANSIT_STOP
    leisure = tags.get("leisure")
    if leisure is not None:
        found = _LEISURE.get(leisure)
        if found is not None:
            return found
        if leisure == "pitch" and any(s.strip() == "skateboard" for s in (tags.get("sport") or "").split(";")):
            return SKATEPARK
    return None


def _clean(value):
    """Spiegelt PoiKinds.clean: ohne Zeilenumbrueche und Raender, hoechstens MAX_TEXT Zeichen."""
    if value is None:
        return ""
    flat = value.replace("\r", " ").replace("\n", " ").strip()
    return flat[:MAX_TEXT].strip() if len(flat) > MAX_TEXT else flat


def _first(tags, *keys):
    for key in keys:
        value = tags.get(key)
        if value is not None:
            return value
    return None


def name(kind, tags):
    """Spiegelt PoiKinds.name: beim Rettungspunkt die Nummer (ref), sonst name oder Marke."""
    if kind == EMERGENCY_POINT:
        return _clean(_first(tags, "ref", "name"))
    return _clean(_first(tags, "name", "brand"))


def _extra(kind, tags):
    if kind == HOSPITAL:
        return "mit Notaufnahme" if tags.get("emergency") == "yes" else ""
    if kind == DEFIBRILLATOR:
        where = _clean(tags.get("defibrillator:location"))
        if where:
            return where
        return "im Gebäude" if tags.get("indoor") == "yes" else ""
    if kind == TRANSIT_STOP:
        railway = tags.get("railway")
        if railway == "station":
            return "Bahnhof"
        if railway == "halt":
            return "Bahnhalt"
        if railway == "tram_stop":
            return "Straßenbahn"
        if tags.get("highway") == "bus_stop":
            return "Bus"
        return "Station"
    if kind == VENDING:
        parts = [p.strip() for p in (tags.get("vending") or "").split(";")]
        return _clean(", ".join(VENDING_NAMES.get(p, p.replace("_", " ")) for p in parts if p))
    return ""


def info(kind, tags):
    """Spiegelt PoiKinds.info und PoiInfo.encode: Zeilen "Schluessel=Wert", leere fehlen."""
    fields = (
        ("z", _extra(kind, tags)),
        ("oh", _clean(tags.get("opening_hours"))),
        ("tel", _clean(_first(tags, "phone", "contact:phone"))),
        ("fee", _clean(tags.get("fee"))),
        ("wc", _clean(tags.get("wheelchair"))),
    )
    return "\n".join(f"{key}={value}" for key, value in fields if value)


def poi_row(latitude, longitude, kind, tags):
    """Zeile fuer die Tabelle poi: (cell, lat, lon, kind, name, info). Fach wie bei den Adressen (auf 7 Stellen)."""
    lat = round(latitude, 7)
    lon = round(longitude, 7)
    return (kodierung.cell_key(lat, lon), lat, lon, kind, name(kind, tags), info(kind, tags))
