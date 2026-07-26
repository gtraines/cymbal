"""
Unit tests for AddressLookup offline reverse geocoder.

Tests run against an in-memory SQLite database that mimics the production
schema, so no external database files are required.
"""

import math
import sqlite3
import sys
import types
import unittest


# ---------------------------------------------------------------------------
# Build a helpers to create and populate a test database.
# ---------------------------------------------------------------------------

def _make_test_db(records):
    """
    Create an in-memory SQLite database with addr_rtree and addresses tables
    populated from a list of dicts:
        [{'id': int, 'number': str, 'street': str, 'city': str,
          'district': str, 'region': str, 'postcode': str,
          'lat': float, 'lon': float}, ...]
    Returns the database path string ':memory:' via a monkey-patched connect.
    The returned conn should be injected into the lookup's _db_conn.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE VIRTUAL TABLE addr_rtree USING rtree(
            id, min_lat, max_lat, min_lon, max_lon
        )
    """)
    conn.execute("""
        CREATE TABLE addresses (
            id       INTEGER PRIMARY KEY,
            number   TEXT,
            street   TEXT,
            city     TEXT,
            district TEXT,
            region   TEXT,
            postcode TEXT,
            lat      REAL,
            lon      REAL
        )
    """)
    for r in records:
        conn.execute(
            "INSERT INTO addresses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r['id'], r['number'], r['street'], r['city'],
             r['district'], r['region'], r['postcode'],
             r['lat'], r['lon']),
        )
        conn.execute(
            "INSERT INTO addr_rtree VALUES (?, ?, ?, ?, ?)",
            (r['id'], r['lat'], r['lat'], r['lon'], r['lon']),
        )
    conn.commit()
    return conn


MESA_RECORDS = [
    {'id': 1, 'number': '1234', 'street': 'E Main St',
     'city': 'Mesa', 'district': 'Maricopa',
     'region': 'AZ', 'postcode': '85201',
     'lat': 33.4152, 'lon': -111.8315},
    {'id': 2, 'number': '500', 'street': 'N Dobson Rd',
     'city': 'Mesa', 'district': 'Maricopa',
     'region': 'AZ', 'postcode': '85202',
     'lat': 33.4200, 'lon': -111.8900},
    {'id': 3, 'number': '99', 'street': 'W University Dr',
     'city': 'Mesa', 'district': 'Maricopa',
     'region': 'AZ', 'postcode': '85201',
     'lat': 33.4155, 'lon': -111.8310},
]


class TestAddressLookupFormatting(unittest.TestCase):
    """Test reverse_geocode address string formatting."""

    def _make_lookup_with_db(self, records):
        from cymbal.geo.address_lookup import AddressLookup
        lookup = AddressLookup()
        lookup._db_conn = _make_test_db(records)
        lookup.is_initialized = True
        return lookup

    def test_full_address_returned(self):
        lookup = self._make_lookup_with_db(MESA_RECORDS)
        # Query very close to record 1
        result = lookup.reverse_geocode(33.4152, -111.8315)
        self.assertIn("1234", result)
        self.assertIn("E Main St", result)
        self.assertIn("Mesa", result)
        self.assertIn("AZ", result)

    def test_nearest_of_two_close_records(self):
        lookup = self._make_lookup_with_db(MESA_RECORDS)
        # Record 3 is the nearest to this query
        result = lookup.reverse_geocode(33.4155, -111.8310)
        self.assertIn("99", result)
        self.assertIn("W University Dr", result)

    def test_no_match_returns_unknown(self):
        lookup = self._make_lookup_with_db(MESA_RECORDS)
        # Query far outside any record's radius
        result = lookup.reverse_geocode(40.0, -100.0)
        self.assertEqual(result, "Unknown address")

    def test_uninitialized_returns_empty_dict(self):
        from cymbal.geo.address_lookup import AddressLookup
        lookup = AddressLookup()
        # Do NOT call initialize — simulate not-ready state
        info = lookup.get_location_info(33.4, -111.8)
        self.assertEqual(info, {})


class TestAddressLookupLocationInfo(unittest.TestCase):

    def _make_lookup_with_db(self, records):
        from cymbal.geo.address_lookup import AddressLookup
        lookup = AddressLookup()
        lookup._db_conn = _make_test_db(records)
        lookup.is_initialized = True
        return lookup

    def test_get_location_info_fields(self):
        lookup = self._make_lookup_with_db(MESA_RECORDS)
        info = lookup.get_location_info(33.4152, -111.8315)
        self.assertEqual(info['number'], '1234')
        self.assertEqual(info['street'], 'E Main St')
        self.assertEqual(info['city'], 'Mesa')
        self.assertEqual(info['region'], 'AZ')
        self.assertEqual(info['postcode'], '85201')
        self.assertIn('distance_m', info)
        self.assertAlmostEqual(info['distance_m'], 0.0, places=0)

    def test_distance_m_increases_with_offset(self):
        lookup = self._make_lookup_with_db(MESA_RECORDS)
        info_close = lookup.get_location_info(33.4152, -111.8315)
        info_far = lookup.get_location_info(33.4160, -111.8315)
        self.assertGreater(info_far['distance_m'], info_close['distance_m'])

    def test_empty_result_outside_radius(self):
        lookup = self._make_lookup_with_db(MESA_RECORDS)
        info = lookup.get_location_info(40.0, -100.0)
        self.assertEqual(info, {})


class TestAddressLookupInit(unittest.TestCase):

    def test_initialize_fails_on_nonexistent_file(self):
        from cymbal.geo.address_lookup import AddressLookup
        lookup = AddressLookup()
        result = lookup.initialize("/nonexistent/path/addresses.db")
        self.assertFalse(result)
        self.assertFalse(lookup.is_initialized)

    def test_close_safe_when_not_initialized(self):
        from cymbal.geo.address_lookup import AddressLookup
        lookup = AddressLookup()
        # Should not raise
        lookup.close()
        self.assertFalse(lookup.is_initialized)


if __name__ == '__main__':
    unittest.main()
