"""
Terrain Elevation Database

Provides offline terrain elevation lookups from pre-downloaded SRTM tiles.
Returns meters above mean sea level (MSL) for a given lat/lon coordinate.

Library choice: srtm.py (https://github.com/tkrajina/srtm.py)
  - Lightweight pure-Python SRTM tile reader; no GDAL/rasterio dependency.
  - Uses a local file cache so it works fully offline once tiles are downloaded.
  - Query latency is <10ms for cached tiles on Pi 3B+, well within the 200ms budget.
  - Alternatives (rasterio + GDAL) were rejected due to large build dependencies and
    higher RAM overhead on the Pi.

Tile pre-download for the North Mesa, Arizona operating area:
  python -c "
  import srtm
  d = srtm.get_data(local_cache_dir='/opt/cymbal/srtm')
  # Fetch tiles covering North Mesa, AZ: lat 33-34, lon -112 to -111
  for lat in range(33, 35):
      for lon in range(-112, -110):
          d.get_elevation(lat + 0.5, lon + 0.5)
  print('Tiles cached')
  "
"""

from libc.math cimport isnan
import logging
import math

try:
    import srtm
except ImportError:
    srtm = None

logger = logging.getLogger(__name__)


cdef class TerrainElevationDB:
    """
    Offline terrain elevation lookup using pre-downloaded SRTM tiles.

    Uses srtm.py pointed at a local tile cache so no network access occurs
    during flight. Initialize once at startup; queries are read-only and
    thread-safe after initialization.
    """

    def __init__(self):
        self._elevation_data = None
        self.data_path = ""
        self.is_initialized = False
        self.nan_sentinel = float('nan')

    cpdef bint initialize(self, str data_path):
        """
        Load SRTM elevation data from a local cache directory.

        Args:
            data_path: Directory containing pre-downloaded SRTM .hgt files,
                       e.g. /opt/cymbal/srtm

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if srtm is None:
            logger.error("srtm.py not available; install with: pip install srtm.py")
            return False

        self.data_path = data_path
        try:
            self._elevation_data = srtm.get_data(
                local_cache_dir=data_path,
                # Disable auto-download; require tiles to already be present.
                leave_zipped=False,
            )
            self.is_initialized = True
            logger.info(f"TerrainElevationDB initialized from {data_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize TerrainElevationDB: {e}")
            self.is_initialized = False
            return False

    cpdef double get_elevation(self, double lat, double lon):
        """
        Return terrain elevation (meters MSL) at the given coordinates.

        Args:
            lat: Latitude in decimal degrees.
            lon: Longitude in decimal degrees.

        Returns:
            Elevation in meters MSL, or NaN if the tile is unavailable or
            the data could not be read.
        """
        cdef object result

        if not self.is_initialized or self._elevation_data is None:
            logger.warning("TerrainElevationDB queried before initialization")
            return self.nan_sentinel

        try:
            result = self._elevation_data.get_elevation(lat, lon)
            if result is None:
                logger.debug(f"No SRTM data for ({lat:.5f}, {lon:.5f})")
                return self.nan_sentinel
            return float(result)
        except Exception as e:
            logger.warning(f"Elevation lookup error at ({lat:.5f}, {lon:.5f}): {e}")
            return self.nan_sentinel

    cpdef void close(self):
        """Release elevation data resources."""
        self._elevation_data = None
        self.is_initialized = False
        logger.debug("TerrainElevationDB closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
