"""
Unit Tests for src/geo.py.
Verifies accurate geographic resolution and confirms that locations never
fall back to company headquarters.
"""

import unittest
from src.geo import resolve_country_from_location


class TestGeoResolution(unittest.TestCase):
    def test_multilingual_european_cities(self):
        """Verify city aliases across European tech hubs resolve to the correct country."""
        # Germany
        self.assertEqual(resolve_country_from_location("Munich, Bavaria")[0], "Germany")
        self.assertEqual(resolve_country_from_location("München, Germany")[0], "Germany")
        self.assertEqual(resolve_country_from_location("Dresden Tech Hub")[0], "Germany")
        self.assertEqual(resolve_country_from_location("Parsdorf R&D Center")[0], "Germany")

        # Netherlands
        self.assertEqual(resolve_country_from_location("Eindhoven High Tech Campus")[0], "Netherlands")
        self.assertEqual(resolve_country_from_location("Delft, South Holland")[0], "Netherlands")
        self.assertEqual(resolve_country_from_location("Hengelo Facility")[0], "Netherlands")
        self.assertEqual(resolve_country_from_location("Veldhoven HQ")[0], "Netherlands")

        # France
        self.assertEqual(resolve_country_from_location("Toulouse Aerospace Valley")[0], "France")
        self.assertEqual(resolve_country_from_location("Sophia-Antipolis, Côte d'Azur")[0], "France")
        self.assertEqual(resolve_country_from_location("Mérignac, France")[0], "France")
        self.assertEqual(resolve_country_from_location("Grenoble R&D")[0], "France")

        # Austria & Switzerland
        self.assertEqual(resolve_country_from_location("Wien, Österreich")[0], "Austria")
        self.assertEqual(resolve_country_from_location("Vienna, Austria")[0], "Austria")
        self.assertEqual(resolve_country_from_location("Gratkorn Technology Center")[0], "Austria")
        self.assertEqual(resolve_country_from_location("Zürich, Switzerland")[0], "Switzerland")
        self.assertEqual(resolve_country_from_location("Geneva Lab")[0], "Switzerland")

        # Ireland & UK
        self.assertEqual(resolve_country_from_location("Cork, Ireland")[0], "Ireland")
        self.assertEqual(resolve_country_from_location("Limerick Campus")[0], "Ireland")
        self.assertEqual(resolve_country_from_location("Cambridge, UK")[0], "UK")
        self.assertEqual(resolve_country_from_location("Bristol Engineering Center")[0], "UK")

    def test_asian_and_global_hubs(self):
        """Verify Asian tech hubs resolve to their actual country, not company HQ."""
        self.assertEqual(resolve_country_from_location("Shenzhen, China")[0], "China")
        self.assertEqual(resolve_country_from_location("Penang, Malaysia")[0], "Malaysia")
        self.assertEqual(resolve_country_from_location("Taguig, Philippines")[0], "Philippines")
        self.assertEqual(resolve_country_from_location("Bengaluru, India")[0], "India")
        self.assertEqual(resolve_country_from_location("Istanbul, Turkey")[0], "Turkey")
        self.assertEqual(resolve_country_from_location("Brno, Czech Republic")[0], "Czech Republic")

    def test_usa_cities_and_states(self):
        """Verify US states and cities resolve to USA."""
        self.assertEqual(resolve_country_from_location("Austin, TX")[0], "USA")
        self.assertEqual(resolve_country_from_location("San Jose, CA")[0], "USA")
        self.assertEqual(resolve_country_from_location("Seattle, Washington")[0], "USA")
        self.assertEqual(resolve_country_from_location("Boston, Massachusetts")[0], "USA")
        self.assertEqual(resolve_country_from_location("Broomfield, Colorado")[0], "USA")

    def test_remote_anywhere(self):
        """Verify remote-anywhere flags are detected."""
        country, conf, is_remote = resolve_country_from_location("Remote - Anywhere in the World")
        self.assertTrue(is_remote)

        country2, conf2, is_remote2 = resolve_country_from_location("Global Remote (EMEA)")
        self.assertTrue(is_remote2)

    def test_unknown_never_defaults_to_company(self):
        """Verify unknown locations return 'Unknown' with 0 confidence, never defaulting."""
        country, conf, is_remote = resolve_country_from_location("Random Gibberish Suite 404")
        self.assertEqual(country, "Unknown")
        self.assertEqual(conf, 0.0)

        country_empty, conf_empty, _ = resolve_country_from_location("")
        self.assertEqual(country_empty, "Unknown")
        self.assertEqual(conf_empty, 0.0)


if __name__ == "__main__":
    unittest.main()
