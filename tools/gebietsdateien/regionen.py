"""Tabelle der Gebiete: Kennung -> Name und Quelle bei Geofabrik.

Erweitern: einfach eine Zeile anhaengen. Die Kennung wird zum Dateinamen (<kennung>.sqlite.gz)
und darf nur Kleinbuchstaben, Ziffern und Bindestriche enthalten.
"""

GEOFABRIK = "https://download.geofabrik.de/"

# Kennung: (Name fuer die Anzeige, Pfad bei Geofabrik ohne "-latest.osm.pbf")
REGIONEN = {
    "baden-wuerttemberg": ("Baden-Württemberg", "europe/germany/baden-wuerttemberg"),
    "bayern": ("Bayern", "europe/germany/bayern"),
    "berlin": ("Berlin", "europe/germany/berlin"),
    "brandenburg": ("Brandenburg", "europe/germany/brandenburg"),
    "bremen": ("Bremen", "europe/germany/bremen"),
    "hamburg": ("Hamburg", "europe/germany/hamburg"),
    "hessen": ("Hessen", "europe/germany/hessen"),
    "mecklenburg-vorpommern": ("Mecklenburg-Vorpommern", "europe/germany/mecklenburg-vorpommern"),
    "niedersachsen": ("Niedersachsen", "europe/germany/niedersachsen"),
    "nordrhein-westfalen": ("Nordrhein-Westfalen", "europe/germany/nordrhein-westfalen"),
    "rheinland-pfalz": ("Rheinland-Pfalz", "europe/germany/rheinland-pfalz"),
    "saarland": ("Saarland", "europe/germany/saarland"),
    "sachsen": ("Sachsen", "europe/germany/sachsen"),
    "sachsen-anhalt": ("Sachsen-Anhalt", "europe/germany/sachsen-anhalt"),
    "schleswig-holstein": ("Schleswig-Holstein", "europe/germany/schleswig-holstein"),
    "thueringen": ("Thüringen", "europe/germany/thueringen"),
    "germany": ("Deutschland", "europe/germany"),
    "austria": ("Österreich", "europe/austria"),
    "switzerland": ("Schweiz", "europe/switzerland"),
}


def name(region_id):
    return REGIONEN[region_id][0]


def url(region_id):
    return GEOFABRIK + REGIONEN[region_id][1] + "-latest.osm.pbf"


def auswahl(text):
    """Liest die Eingabe "bayern, berlin" oder "alle". Unbekannte Kennungen sind ein Fehler."""
    wanted = [part.strip().lower() for part in text.replace(";", ",").replace(" ", ",").split(",")]
    wanted = [part for part in wanted if part]
    if not wanted or wanted == ["alle"]:
        return list(REGIONEN)
    unknown = [part for part in wanted if part not in REGIONEN]
    if unknown:
        raise ValueError(
            "Unbekannte Region: %s. Bekannt sind: %s" % (", ".join(unknown), ", ".join(REGIONEN))
        )
    # Reihenfolge behalten, Doppelte entfernen
    return list(dict.fromkeys(wanted))
