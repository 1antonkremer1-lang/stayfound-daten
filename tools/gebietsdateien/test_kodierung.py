"""Tests der Kodierungen. Die erwarteten Werte sind von Hand aus dem Kotlin-Code abgeleitet
(OfflineAddresses.kt und Roads.kt), nicht aus dem Python-Code berechnet."""

import unittest

import kodierung as k


class CellKeyTest(unittest.TestCase):
    def test_coburg(self):
        # floor(50.2612 / 0.001) = 50261, floor(10.9627 / 0.001) = 10962
        # (50261 + 100000) * 1000000 + (10962 + 200000) = 150261210962
        self.assertEqual(k.cell_key(50.2612, 10.9627), 150261210962)

    def test_negative_rundet_nach_unten(self):
        # floor(-0.5) = -1: (-1 + 100000) * 1000000 + (-1 + 200000)
        self.assertEqual(k.cell_key(-0.0005, -0.0005), 99999199999)

    def test_fachgrenze_wie_in_der_app(self):
        # 11.575 / 0.001 ergibt als Gleitkommazahl 11574.999999999998, also Spalte 11574 (nicht 11575).
        # Die App rechnet genauso; mit "mal 1000" kaeme hier ein anderes Fach heraus.
        self.assertEqual(k.cell_key(48.137, 11.575), 148137211574)

    def test_null(self):
        self.assertEqual(k.cell_key(0.0, 0.0), 100000200000)

    def test_groesste_werte(self):
        # floor(89.9995 / 0.001) = 89999, floor(179.9995 / 0.001) = 179999
        self.assertEqual(k.cell_key(89.9995, 179.9995), 189999379999)


class ParseLineTest(unittest.TestCase):
    def test_mit_ort(self):
        self.assertEqual(
            k.parse_line("50.2612000|10.9627000|Marktplatz||3|96450|Coburg"),
            (50.2612, 10.9627, "Marktplatz 3, 96450 Coburg"),
        )

    def test_ohne_ort(self):
        self.assertEqual(k.parse_line("50.1|10.2|Hauptstraße||12a||")[2], "Hauptstraße 12a")

    def test_nur_plz_oder_nur_ort(self):
        self.assertEqual(k.parse_line("50.1|10.2|Weg||1|96450|")[2], "Weg 1, 96450")
        self.assertEqual(k.parse_line("50.1|10.2|Weg||1||Coburg")[2], "Weg 1, Coburg")

    def test_ortsteil_statt_strasse(self):
        self.assertEqual(k.parse_line("50.1|10.2||Oberdorf|7|96450|Coburg")[2], "Oberdorf 7, 96450 Coburg")

    def test_strasse_geht_vor_ortsteil(self):
        self.assertEqual(k.parse_line("50.1|10.2|Weg|Oberdorf|7||")[2], "Weg 7")

    def test_leerzeichen_werden_abgeschnitten(self):
        self.assertEqual(k.parse_line(" 50.1 | 10.2 | Weg ||  7 | 96450 | Coburg ")[2], "Weg 7, 96450 Coburg")

    def test_fuenf_felder_reichen(self):
        self.assertEqual(k.parse_line("50.1|10.2|Weg||7")[2], "Weg 7")

    def test_unbrauchbar(self):
        self.assertIsNone(k.parse_line("50.1|10.2|Weg|"))            # zu wenig Felder
        self.assertIsNone(k.parse_line("50.1|10.2|||7||"))           # keine Strasse
        self.assertIsNone(k.parse_line("50.1|10.2|Weg||||"))         # keine Hausnummer
        self.assertIsNone(k.parse_line("abc|10.2|Weg||7||"))         # keine Zahl
        self.assertIsNone(k.parse_line("91.0|10.2|Weg||7||"))        # Breite ausserhalb
        self.assertIsNone(k.parse_line("50.1|180.5|Weg||7||"))       # Laenge ausserhalb


class AddressTest(unittest.TestCase):
    def test_zeile_fuer_tabelle(self):
        tags = {"addr:street": "Marktplatz", "addr:housenumber": "3", "addr:postcode": "96450", "addr:city": "Coburg"}
        self.assertEqual(
            k.address(50.2612, 10.9627, tags),
            (150261210962, 50.2612, 10.9627, "Marktplatz 3, 96450 Coburg"),
        )

    def test_csv_zeile(self):
        self.assertEqual(
            k.csv_line(50.2612, 10.9627, {"addr:place": "Oberdorf", "addr:housenumber": "7"}),
            "50.2612000|10.9627000||Oberdorf|7||",
        )

    def test_ohne_strasse_keine_zeile(self):
        self.assertIsNone(k.address(50.0, 10.0, {"addr:housenumber": "7", "addr:city": "Coburg"}))

    def test_trennzeichen_in_angabe_wie_in_der_app(self):
        # Ein "|" in der Hausnummer verschiebt die Felder, genau wie beim Lesen in der App.
        tags = {"addr:street": "Weg", "addr:housenumber": "1|2", "addr:postcode": "96450", "addr:city": "Coburg"}
        self.assertEqual(k.address(50.0, 10.0, tags)[3], "Weg 1, 2 96450")

    def test_mitte_des_rechtecks(self):
        # Umriss von 50.0000000..50.0002000 und 10.0000000..10.0004000
        lat, lon = k.way_center([500000000, 500002000, 500001000], [100000000, 100004000, 100000500])
        self.assertEqual("%.7f" % lat, "50.0001000")
        self.assertEqual("%.7f" % lon, "10.0002000")


class KindRankTest(unittest.TestCase):
    def test_kind_of(self):
        expected = {
            "motorway": 0, "trunk": 1, "primary": 2, "secondary": 3, "tertiary": 4, "unclassified": 5,
            "residential": 6, "living_street": 7, "service": 8, "track": 9, "path": 10, "footway": 11,
            "cycleway": 12, "pedestrian": 13, "steps": 14,
            "road": 5, "motorway_link": 0, "trunk_link": 1, "primary_link": 2, "secondary_link": 3,
            "tertiary_link": 4,
            "bus_stop": -1, "": -1, "_link": -1, "construction": -1,
        }
        for highway, kind in expected.items():
            self.assertEqual(k.kind_of(highway), kind, highway)

    def test_rank(self):
        expected = [3, 3, 3, 3, 2, 2, 1, 1, 1, 0, 0, 0, 1, 0, 0]
        self.assertEqual([k.rank(kind) for kind in range(15)], expected)
        self.assertEqual(k.rank(-1), 0)

    def test_abfrage_enthaelt_genau_21_werte(self):
        # 15 Arten + road + 5 Auffahrten, wie in Roads.query
        self.assertEqual(len(k.QUERY_HIGHWAYS), 21)
        self.assertNotIn("residential_link", k.QUERY_HIGHWAYS)


class FromTagsTest(unittest.TestCase):
    def check(self, tags, expected):
        self.assertEqual(k.from_tags(tags, 2), expected, tags)

    def test_wohnstrasse(self):
        self.check({"highway": "residential", "name": "Marktplatz"}, (6, 0, 0, "Marktplatz"))

    def test_autobahn(self):
        # kind <= 1: Rad und Fuss gesperrt (2 + 4); ohne oneway-Angabe Einbahn; Name aus ref
        self.check({"highway": "motorway", "ref": "A 73"}, (0, 6, 1, "A 73"))

    def test_autobahn_auffahrt_ist_keine_einbahn(self):
        self.check({"highway": "motorway_link"}, (0, 6, 0, ""))

    def test_autobahn_oneway_no(self):
        self.check({"highway": "motorway", "oneway": "no"}, (0, 6, 0, ""))

    def test_name_geht_vor_ref(self):
        self.check({"highway": "primary", "name": "Bamberger Straße", "ref": "B 4"}, (2, 0, 0, "Bamberger Straße"))

    def test_feldweg(self):
        self.check({"highway": "track"}, (9, k.NO_CAR, 0, ""))
        self.check({"highway": "track", "motor_vehicle": "yes"}, (9, 0, 0, ""))
        # vehicle zaehlt nur, wenn motor_vehicle fehlt
        self.check({"highway": "track", "vehicle": "yes"}, (9, 0, 0, ""))

    def test_wege_ohne_auto(self):
        self.check({"highway": "path"}, (10, 1, 0, ""))
        self.check({"highway": "footway"}, (11, 1, 0, ""))
        self.check({"highway": "cycleway"}, (12, 1, 0, ""))
        self.check({"highway": "pedestrian"}, (13, 1, 0, ""))
        # Treppe: zusaetzlich kein Rad
        self.check({"highway": "steps"}, (14, 3, 0, ""))

    def test_access_private(self):
        self.check({"highway": "residential", "access": "private"}, (6, 7, 0, ""))
        self.check({"highway": "residential", "access": "no", "foot": "yes"}, (6, 3, 0, ""))
        self.check({"highway": "residential", "access": "no", "bicycle": "designated"}, (6, 5, 0, ""))
        self.check({"highway": "residential", "access": "private", "motor_vehicle": "yes"}, (6, 6, 0, ""))
        # andere Werte von access sperren nichts
        self.check({"highway": "residential", "access": "destination"}, (6, 0, 0, ""))

    def test_vehicle(self):
        # vehicle=no: Auto gesperrt (motor = vehicle), Rad gesperrt (keine bicycle-Angabe)
        self.check({"highway": "residential", "vehicle": "no"}, (6, 3, 0, ""))
        self.check({"highway": "residential", "vehicle": "no", "bicycle": "yes"}, (6, 1, 0, ""))
        # motor_vehicle geht vor vehicle, das Rad bleibt gesperrt
        self.check({"highway": "residential", "vehicle": "private", "motor_vehicle": "yes"}, (6, 2, 0, ""))

    def test_motor_vehicle_werte(self):
        for value in ("no", "private", "agricultural", "forestry"):
            self.check({"highway": "service", "motor_vehicle": value}, (8, 1, 0, ""))
        self.check({"highway": "service", "motor_vehicle": "destination"}, (8, 0, 0, ""))

    def test_einzelverbote(self):
        self.check({"highway": "tertiary", "bicycle": "no"}, (4, 2, 0, ""))
        self.check({"highway": "tertiary", "foot": "no"}, (4, 4, 0, ""))
        self.check({"highway": "trunk", "foot": "yes", "bicycle": "yes"}, (1, 6, 0, ""))

    def test_kreisverkehr(self):
        self.check({"highway": "tertiary", "junction": "roundabout"}, (4, 8, 1, ""))
        self.check({"highway": "tertiary", "junction": "circular"}, (4, 8, 1, ""))
        self.check({"highway": "tertiary", "junction": "roundabout", "oneway": "no"}, (4, 8, 0, ""))

    def test_einbahn(self):
        for value in ("yes", "true", "1"):
            self.check({"highway": "residential", "oneway": value}, (6, 0, 1, ""))
        for value in ("-1", "reverse"):
            self.check({"highway": "residential", "oneway": value}, (6, 0, -1, ""))
        self.check({"highway": "residential", "oneway": "alternating"}, (6, 0, 0, ""))

    def test_nicht_nutzbar(self):
        self.assertIsNone(k.from_tags({"highway": "pedestrian", "area": "yes"}, 5))
        self.assertIsNone(k.from_tags({"highway": "bus_stop"}, 5))
        self.assertIsNone(k.from_tags({"name": "ohne Art"}, 5))
        self.assertIsNone(k.from_tags({"highway": "residential"}, 1))


class RoundToIntTest(unittest.TestCase):
    def test_wie_kotlin(self):
        # Kotlin: 2.5.roundToInt() == 3, (-2.5).roundToInt() == -2, (-2.6).roundToInt() == -3
        self.assertEqual(k.round_to_int(2.5), 3)
        self.assertEqual(k.round_to_int(-2.5), -2)
        self.assertEqual(k.round_to_int(-2.6), -3)
        self.assertEqual(k.round_to_int(2.4), 2)
        self.assertEqual(k.round_to_int(0.49999999999999994), 0)
        self.assertEqual(k.round_to_int(1e12), 2147483647)
        self.assertEqual(k.round_to_int(-1e12), -2147483648)


class EncodeNodesTest(unittest.TestCase):
    def test_ein_punkt(self):
        # id 1 -> 00 00 00 00 00 00 00 01
        # 50.0 * 1e7 = 500000000 = 0x1DCD6500;  10.0 * 1e7 = 100000000 = 0x05F5E100
        self.assertEqual(k.encode_nodes([1], [50.0], [10.0]).hex(), "00000000000000011dcd650005f5e100")

    def test_zwei_punkte_je_16_byte(self):
        # 255 = 0xFF; 1 Grad = 10000000 = 0x00989680; 2 Grad = 20000000 = 0x01312D00
        blob = k.encode_nodes([255, 256], [1.0, 2.0], [2.0, 1.0])
        self.assertEqual(
            blob.hex(),
            "00000000000000ff" "00989680" "01312d00"
            "0000000000000100" "01312d00" "00989680",
        )

    def test_negative_koordinaten_im_zweierkomplement(self):
        # -1e-7 Grad -> -1 -> FF FF FF FF;  -180 Grad -> -1800000000 = 0x94B62E00
        blob = k.encode_nodes([0x0102030405060708], [-0.0000001], [-180.0])
        self.assertEqual(blob.hex(), "0102030405060708" "ffffffff" "94b62e00")

    def test_grosse_kennung(self):
        # 12345678901 = 0x2DFDC1C35
        self.assertEqual(k.encode_nodes([12345678901], [0.0], [0.0]).hex(), "00000002dfdc1c35" + "00" * 8)

    def test_leer(self):
        self.assertEqual(k.encode_nodes([], [], []), b"")

    def test_hin_und_zurueck(self):
        ids = [1, 2, 13000000000]
        lats = [50.2612345, 47.0000001, -33.8567844]
        lons = [10.9627891, 9.9999999, 151.2152967]
        self.assertEqual(k.decode_nodes(k.encode_nodes(ids, lats, lons)), (ids, lats, lons))


class WayRowTest(unittest.TestCase):
    def test_zeile_fuer_tabelle(self):
        row = k.way_row(
            4711, {"highway": "residential", "name": "Marktplatz", "oneway": "yes"},
            [1, 2], [500000000, 500010000], [100020000, 100000000],
        )
        self.assertEqual(row[:6], (4711, 1, 6, 0, 1, "Marktplatz"))
        # Sued, West, Nord, Ost
        self.assertEqual(row[6:10], (50.0, 10.0, 50.001, 10.002))
        # 500010000 = 0x1DCD8C10; 100020000 = 0x05F62F20
        self.assertEqual(row[10].hex(), "0000000000000001" "1dcd6500" "05f62f20" "0000000000000002" "1dcd8c10" "05f5e100")

    def test_nur_abgefragte_arten(self):
        nodes = ([1, 2], [500000000, 500010000], [100000000, 100020000])
        # Roads.kindOf wuerde "residential_link" annehmen, aber Roads.query fragt es nicht ab.
        self.assertIsNone(k.way_row(1, {"highway": "residential_link"}, *nodes))
        self.assertIsNone(k.way_row(1, {"highway": "construction"}, *nodes))
        self.assertIsNone(k.way_row(1, {"building": "yes"}, *nodes))
        self.assertIsNone(k.way_row(1, {"highway": "pedestrian", "area": "yes"}, *nodes))
        self.assertIsNotNone(k.way_row(1, {"highway": "road"}, *nodes))


if __name__ == "__main__":
    unittest.main()
