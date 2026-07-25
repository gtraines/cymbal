#!/usr/bin/env python3
"""
load_openaddresses.py — Build the offline address SQLite database from
an OpenAddresses CSV export for the North Mesa, Arizona operating area.

Usage:
    python3 load_openaddresses.py \
        --input /path/to/openaddresses-us-az.csv \
        --output /opt/cymbal/addresses.db \
        [--bbox 33.3,33.55,-111.95,-111.60]

Data source:
    https://batch.openaddresses.io  (download us/az or us/az/maricopa county)

The CSV is expected to have at minimum these columns (OpenAddresses standard):
    LON, LAT, NUMBER, STREET, CITY, DISTRICT, REGION, POSTCODE

The script creates the following schema in the output SQLite file:
    - addresses(id, number, street, city, district, region, postcode, lat, lon)
    - addr_rtree USING rtree(id, min_lat, max_lat, min_lon, max_lon)
"""

import argparse
import csv
import logging
import sqlite3

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
log = logging.getLogger(__name__)

# Default bounding box: North Mesa / Gilbert area, AZ
DEFAULT_BBOX = (33.3, 33.55, -111.95, -111.60)

DDL = """
CREATE TABLE IF NOT EXISTS addresses (
    id       INTEGER PRIMARY KEY,
    number   TEXT,
    street   TEXT,
    city     TEXT,
    district TEXT,
    region   TEXT,
    postcode TEXT,
    lat      REAL NOT NULL,
    lon      REAL NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS addr_rtree USING rtree(
    id,
    min_lat, max_lat,
    min_lon, max_lon
);
"""


def parse_bbox(s):
    parts = [float(x.strip()) for x in s.split(',')]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be: min_lat,max_lat,min_lon,max_lon")
    return tuple(parts)


def load(csv_path, db_path, bbox):
    min_lat, max_lat, min_lon, max_lon = bbox
    log.info(f"Loading {csv_path} -> {db_path}")
    log.info(f"Bounding box: lat [{min_lat}, {max_lat}], lon [{min_lon}, {max_lon}]")

    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)

    inserted = 0
    skipped = 0
    batch = []
    BATCH_SIZE = 5000

    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    lat = float(row.get('LAT') or row.get('lat') or 0)
                    lon = float(row.get('LON') or row.get('lon') or 0)
                except (ValueError, TypeError):
                    skipped += 1
                    continue

                if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                    skipped += 1
                    continue

                number = (row.get('NUMBER') or row.get('number') or '').strip()
                street = (row.get('STREET') or row.get('street') or '').strip()
                city = (row.get('CITY') or row.get('city') or '').strip()
                district = (row.get('DISTRICT') or row.get('district') or '').strip()
                region = (row.get('REGION') or row.get('region') or '').strip()
                postcode = (row.get('POSTCODE') or row.get('postcode') or '').strip()

                batch.append((number, street, city, district, region, postcode, lat, lon))

                if len(batch) >= BATCH_SIZE:
                    _flush(conn, batch)
                    inserted += len(batch)
                    batch = []
                    log.info(f"  {inserted} records inserted...")

        if batch:
            _flush(conn, batch)
            inserted += len(batch)

        conn.commit()
        log.info(f"Done: {inserted} addresses inserted, {skipped} rows skipped.")

    finally:
        conn.close()


def _flush(conn, batch):
    cur = conn.execute("SELECT COALESCE(MAX(id), 0) FROM addresses")
    next_id = cur.fetchone()[0] + 1

    addr_rows = [
        (next_id + i, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7])
        for i, r in enumerate(batch)
    ]
    rtree_rows = [
        (next_id + i, r[6], r[6], r[7], r[7])
        for i, r in enumerate(batch)
    ]

    conn.executemany(
        "INSERT INTO addresses VALUES (?,?,?,?,?,?,?,?,?)", addr_rows
    )
    conn.executemany(
        "INSERT INTO addr_rtree VALUES (?,?,?,?,?)", rtree_rows
    )


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--input', required=True, help='OpenAddresses CSV input file')
    p.add_argument('--output', required=True, help='Output SQLite database path')
    p.add_argument('--bbox', type=parse_bbox,
                   default=DEFAULT_BBOX,
                   help='Bounding box: min_lat,max_lat,min_lon,max_lon '
                        f'(default: {",".join(str(x) for x in DEFAULT_BBOX)})')
    args = p.parse_args()
    load(args.input, args.output, args.bbox)


if __name__ == '__main__':
    main()
