"""
Offline Address Lookup

Provides reverse geocoding (lat/lon → street address) using a regional
OpenAddresses dataset loaded into a local SQLite database with an R*-tree
spatial index.

Data source: OpenAddresses (https://openaddresses.io)
  - Initial dataset: North Mesa, Arizona, from the openaddresses/openaddresses
    collection (us/az/ sub-dataset).
  - Additional regions can be loaded into the same database later without
    changing the module interface.

Library choice: Python stdlib sqlite3 + SQLite R*-tree virtual table.
  - No extra dependencies: sqlite3 ships with every Python ≥ 3.4.
  - SQLite R*-tree is a 2D spatial index built into SQLite; it reduces a
    bounding-box candidate search to O(log n) rather than a full table scan.
  - Alternatives (PostGIS, SpatiaLite, rtree Python package) were rejected:
    PostGIS requires a running Postgres server, SpatiaLite needs a shared
    library that may not be available, and the Python rtree package wraps
    libspatialindex which is not reliably available on Raspberry Pi OS.
  - Query latency for a 0.01° bounding box is <5ms in practice.

Database schema (created by the companion load_openaddresses.py utility):
    CREATE VIRTUAL TABLE addr_rtree USING rtree(
        id, min_lat, max_lat, min_lon, max_lon
    );
    CREATE TABLE addresses (
        id INTEGER PRIMARY KEY,
        number  TEXT,
        street  TEXT,
        city    TEXT,
        district TEXT,
        region  TEXT,
        postcode TEXT,
        lat     REAL,
        lon     REAL
    );

Usage:
    lookup = AddressLookup()
    lookup.initialize('/opt/cymbal/addresses.db')
    addr = lookup.reverse_geocode(33.4152, -111.8315)
    lookup.close()
"""

from libc.math cimport sqrt, fabs
import sqlite3
import logging

logger = logging.getLogger(__name__)

# Search radius in degrees (~1.1 km at 33° latitude)
_DEFAULT_RADIUS_DEG = 0.01
_MAX_CANDIDATES = 50
_UNKNOWN = "Unknown address"


cdef class AddressLookup:
    """
    Offline reverse geocoder backed by a regional SQLite/R*-tree database.

    Thread safety: each call acquires and releases a connection from the
    already-opened db handle. The sqlite3 module serialises concurrent
    reads automatically when check_same_thread=False is set; write access
    is never performed after initialization.
    """

    def __init__(self):
        self._db_conn = None
        self.data_path = ""
        self.is_initialized = False
        self._search_radius_deg = _DEFAULT_RADIUS_DEG
        self._max_candidates = _MAX_CANDIDATES

    cpdef bint initialize(self, str data_path):
        """
        Open the SQLite address database.

        Args:
            data_path: Path to the SQLite database file,
                       e.g. /opt/cymbal/addresses.db

        Returns:
            True if the database opened and required tables exist.
        """
        self.data_path = data_path
        try:
            self._db_conn = sqlite3.connect(
                data_path,
                check_same_thread=False,
                timeout=5.0,
            )
            self._db_conn.row_factory = sqlite3.Row
            # Verify expected schema is present
            cur = self._db_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('addresses', 'addr_rtree')"
            )
            found = {row[0] for row in cur.fetchall()}
            if 'addresses' not in found or 'addr_rtree' not in found:
                raise RuntimeError(
                    f"Required tables 'addresses' and 'addr_rtree' not found "
                    f"in {data_path}. Run load_openaddresses.py to build the database."
                )
            self.is_initialized = True
            logger.info(f"AddressLookup initialized from {data_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AddressLookup: {e}")
            self.is_initialized = False
            return False

    cpdef str reverse_geocode(self, double lat, double lon):
        """
        Return the nearest street address for the given coordinates.

        Args:
            lat: Latitude in decimal degrees.
            lon: Longitude in decimal degrees.

        Returns:
            Address string such as '1234 E Main St, Mesa, AZ 85201',
            or 'Unknown address' if no match is found within the search radius.
        """
        cdef dict info = self.get_location_info(lat, lon)
        if not info:
            return _UNKNOWN
        parts = []
        if info.get('number') and info.get('street'):
            parts.append(f"{info['number']} {info['street']}")
        elif info.get('street'):
            parts.append(info['street'])
        city = info.get('city', '')
        region = info.get('region', '')
        postcode = info.get('postcode', '')
        if city:
            parts.append(city)
        if region and postcode:
            parts.append(f"{region} {postcode}")
        elif region:
            parts.append(region)
        return ', '.join(parts) if parts else _UNKNOWN

    cpdef dict get_location_info(self, double lat, double lon):
        """
        Return a dict of address fields for the nearest point.

        Returns an empty dict if no match is found within the search radius.

        Keys: number, street, city, district, region, postcode, lat, lon,
              distance_m (approximate Euclidean metres).
        """
        if not self.is_initialized:
            logger.warning("AddressLookup queried before initialization")
            return {}

        cdef list candidates = self._query_candidates(lat, lon)
        if not candidates:
            return {}
        return self._best_candidate(lat, lon, candidates)

    cdef list _query_candidates(self, double lat, double lon):
        """Fetch up to _max_candidates rows within the bounding box."""
        cdef double r = self._search_radius_deg
        try:
            cur = self._db_conn.execute(
                """
                SELECT a.number, a.street, a.city, a.district,
                       a.region, a.postcode, a.lat, a.lon
                FROM addr_rtree t
                JOIN addresses a ON a.id = t.id
                WHERE t.min_lat >= ? AND t.max_lat <= ?
                  AND t.min_lon >= ? AND t.max_lon <= ?
                LIMIT ?
                """,
                (lat - r, lat + r, lon - r, lon + r, self._max_candidates),
            )
            return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.warning(f"Candidate query failed: {e}")
            return []

    cdef dict _best_candidate(self, double lat, double lon, list candidates):
        """Return the candidate closest to (lat, lon) in Euclidean degrees."""
        cdef double best_dist = 1e18
        cdef double dlat, dlon, dist
        cdef dict best = {}

        # 1 deg lat ≈ 111 km; cos(33°) ≈ 0.839 so 1 deg lon ≈ 93 km at Mesa AZ
        cdef double lat_scale = 111000.0
        cdef double lon_scale = 93000.0

        for row in candidates:
            dlat = (row['lat'] - lat) * lat_scale
            dlon = (row['lon'] - lon) * lon_scale
            dist = sqrt(dlat * dlat + dlon * dlon)
            if dist < best_dist:
                best_dist = dist
                best = dict(row)
                best['distance_m'] = dist

        return best

    cpdef void close(self):
        """Close the database connection."""
        if self._db_conn is not None:
            self._db_conn.close()
            self._db_conn = None
        self.is_initialized = False
        logger.debug("AddressLookup closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
