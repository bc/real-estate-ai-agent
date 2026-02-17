"""
SQLite database for storing and querying property comps.

Stores both rental comps and sale comps in a single database with a
shared schema. Supports insert, query, dedup, distance search, and
analysis operations. Comps carry latitude/longitude for radius queries.

The database is stored at data/comps.db (created on first use).
Both comp_extractor.py and rent_estimator.py write to and read from this DB.

Usage as a library:
    from comps_db import CompsDB, CompRow
    db = CompsDB()
    db.insert(CompRow(comp_type="sale", address="123 Main St", latitude=39.75, longitude=-104.99, ...))
    results = db.query(comp_type="sale", county="denver", beds=3)
    nearby = db.query_nearby(39.75, -104.99, radius_miles=2, comp_type="sale")
    db.geocode_missing()   # batch geocode comps without lat/lng
    db.stats()

Usage as CLI:
    python comps_db.py stats
    python comps_db.py query --type sale --county denver --beds 3
    python comps_db.py query --type sale --near "39.75,-104.99" --radius 2
    python comps_db.py geocode                           # geocode all missing
    python comps_db.py geocode --id 5                    # geocode one record
    python comps_db.py export --type sale --format json
    python comps_db.py import --file comps.json --type sale
"""

import argparse
import csv as csv_mod
import json
import math
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "comps.db")
PHOTOS_DIR = os.path.join(DB_DIR, "photos")

SCHEMA = """
CREATE TABLE IF NOT EXISTS comps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comp_type       TEXT NOT NULL,           -- 'sale' or 'rental'
    address         TEXT NOT NULL DEFAULT '',
    city            TEXT NOT NULL DEFAULT '',
    county          TEXT NOT NULL DEFAULT '',
    zip_code        TEXT NOT NULL DEFAULT '',
    state           TEXT NOT NULL DEFAULT 'CO',

    -- Geocoded location
    latitude        REAL    NOT NULL DEFAULT 0,
    longitude       REAL    NOT NULL DEFAULT 0,

    price           INTEGER NOT NULL DEFAULT 0,  -- sale price or monthly rent
    price_per_sqft  REAL    NOT NULL DEFAULT 0,
    beds            INTEGER NOT NULL DEFAULT 0,
    baths           REAL    NOT NULL DEFAULT 0,
    sqft            INTEGER NOT NULL DEFAULT 0,
    lot_sqft        INTEGER NOT NULL DEFAULT 0,
    year_built      INTEGER NOT NULL DEFAULT 0,

    property_type   TEXT NOT NULL DEFAULT '',    -- sfh, condo, townhome, etc.
    listing_url     TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',    -- zillow, redfin, trulia, etc.
    photo_urls      TEXT NOT NULL DEFAULT '[]',  -- JSON array of URLs
    photo_count     INTEGER NOT NULL DEFAULT 0,

    -- Sale-specific
    sale_date       TEXT NOT NULL DEFAULT '',
    days_on_market  INTEGER NOT NULL DEFAULT 0,
    list_price      INTEGER NOT NULL DEFAULT 0,
    sale_to_list    REAL    NOT NULL DEFAULT 0,

    -- Rental-specific
    lease_type      TEXT NOT NULL DEFAULT '',     -- annual, month-to-month, short-term
    available_date  TEXT NOT NULL DEFAULT '',
    deposit         INTEGER NOT NULL DEFAULT 0,
    pet_policy      TEXT NOT NULL DEFAULT '',

    -- Common
    garage          TEXT NOT NULL DEFAULT '',
    hoa             INTEGER NOT NULL DEFAULT 0,
    finish_grade    TEXT NOT NULL DEFAULT '',     -- A, B, C, D, F
    notes           TEXT NOT NULL DEFAULT '',

    -- Metadata
    scraped_at      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(comp_type, address, price, source)
);

CREATE INDEX IF NOT EXISTS idx_comps_type       ON comps(comp_type);
CREATE INDEX IF NOT EXISTS idx_comps_county     ON comps(county);
CREATE INDEX IF NOT EXISTS idx_comps_zip        ON comps(zip_code);
CREATE INDEX IF NOT EXISTS idx_comps_beds       ON comps(beds);
CREATE INDEX IF NOT EXISTS idx_comps_price      ON comps(price);
CREATE INDEX IF NOT EXISTS idx_comps_type_county ON comps(comp_type, county);
CREATE INDEX IF NOT EXISTS idx_comps_lat_lng    ON comps(latitude, longitude);

CREATE TABLE IF NOT EXISTS comp_photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comp_id         INTEGER NOT NULL,
    url             TEXT NOT NULL DEFAULT '',
    local_path      TEXT NOT NULL DEFAULT '',
    room_type       TEXT NOT NULL DEFAULT '',   -- kitchen, bathroom, exterior, bedroom, living, other, unknown
    position        INTEGER NOT NULL DEFAULT 0, -- photo order in listing (0-indexed)
    width           INTEGER NOT NULL DEFAULT 0,
    height          INTEGER NOT NULL DEFAULT 0,
    downloaded      INTEGER NOT NULL DEFAULT 0, -- 1 = downloaded locally
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (comp_id) REFERENCES comps(id) ON DELETE CASCADE,
    UNIQUE(comp_id, url)
);

CREATE INDEX IF NOT EXISTS idx_photos_comp_id   ON comp_photos(comp_id);
CREATE INDEX IF NOT EXISTS idx_photos_room_type ON comp_photos(room_type);
"""

# Migration for existing databases that lack the geo columns
MIGRATIONS = [
    "ALTER TABLE comps ADD COLUMN latitude  REAL NOT NULL DEFAULT 0",
    "ALTER TABLE comps ADD COLUMN longitude REAL NOT NULL DEFAULT 0",
]


# ---------------------------------------------------------------------------
# Geocoding (OpenStreetMap Nominatim — free, no API key)
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "real-estate-ai-agent/1.0 (property comp tool)"}


def geocode_address(address: str, city: str = "", state: str = "CO",
                    zip_code: str = "") -> tuple[float, float] | None:
    """Geocode a street address using OpenStreetMap Nominatim.

    Returns (latitude, longitude) or None if not found.
    Rate limit: 1 request/second (Nominatim policy).
    """
    parts = [address]
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    if zip_code:
        parts.append(zip_code)
    query = ", ".join(p for p in parts if p)

    params = urllib.parse.urlencode({
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "us",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers=NOMINATIM_HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two lat/lon points in miles."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


@dataclass
class CompRow:
    """A comp record for the database. Used for both sales and rentals."""
    comp_type: str = "sale"
    address: str = ""
    city: str = ""
    county: str = ""
    zip_code: str = ""
    state: str = "CO"
    latitude: float = 0.0
    longitude: float = 0.0
    price: int = 0
    price_per_sqft: float = 0
    beds: int = 0
    baths: float = 0
    sqft: int = 0
    lot_sqft: int = 0
    year_built: int = 0
    property_type: str = ""
    listing_url: str = ""
    source: str = ""
    photo_urls: list[str] = field(default_factory=list)
    photo_count: int = 0
    sale_date: str = ""
    days_on_market: int = 0
    list_price: int = 0
    sale_to_list: float = 0
    lease_type: str = ""
    available_date: str = ""
    deposit: int = 0
    pet_policy: str = ""
    garage: str = ""
    hoa: int = 0
    finish_grade: str = ""
    notes: str = ""
    scraped_at: str = ""
    # Read-only fields set by DB
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""


class CompsDB:
    """SQLite database for property comps."""

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._run_migrations()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _run_migrations(self):
        """Apply schema migrations for existing databases."""
        existing_cols = {row[1] for row in
                        self.conn.execute("PRAGMA table_info(comps)").fetchall()}
        for sql in MIGRATIONS:
            # Extract column name from ALTER TABLE ... ADD COLUMN <name> ...
            col = sql.split("ADD COLUMN")[1].strip().split()[0]
            if existing_cols and col not in existing_cols:
                try:
                    self.conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # column already exists or table doesn't exist yet
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def insert(self, comp: CompRow) -> int:
        """Insert a comp record. Returns the row ID. Skips duplicates."""
        photos_json = json.dumps(comp.photo_urls) if isinstance(comp.photo_urls, list) else comp.photo_urls
        photo_count = len(comp.photo_urls) if isinstance(comp.photo_urls, list) else comp.photo_count
        scraped = comp.scraped_at or datetime.now().isoformat()

        try:
            cur = self.conn.execute("""
                INSERT OR IGNORE INTO comps (
                    comp_type, address, city, county, zip_code, state,
                    latitude, longitude,
                    price, price_per_sqft, beds, baths, sqft, lot_sqft, year_built,
                    property_type, listing_url, source, photo_urls, photo_count,
                    sale_date, days_on_market, list_price, sale_to_list,
                    lease_type, available_date, deposit, pet_policy,
                    garage, hoa, finish_grade, notes, scraped_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
            """, (
                comp.comp_type, comp.address, comp.city, comp.county,
                comp.zip_code, comp.state,
                comp.latitude, comp.longitude,
                comp.price, comp.price_per_sqft, comp.beds, comp.baths,
                comp.sqft, comp.lot_sqft, comp.year_built,
                comp.property_type, comp.listing_url, comp.source,
                photos_json, photo_count,
                comp.sale_date, comp.days_on_market, comp.list_price, comp.sale_to_list,
                comp.lease_type, comp.available_date, comp.deposit, comp.pet_policy,
                comp.garage, comp.hoa, comp.finish_grade, comp.notes, scraped,
            ))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return 0

    def insert_many(self, comps: list[CompRow]) -> int:
        """Insert multiple comps. Returns count of newly inserted rows."""
        count = 0
        for comp in comps:
            row_id = self.insert(comp)
            if row_id:
                count += 1
        return count

    def query(self, comp_type: str | None = None, county: str | None = None,
              zip_code: str | None = None, beds: int | None = None,
              min_price: int | None = None, max_price: int | None = None,
              min_sqft: int | None = None, max_sqft: int | None = None,
              source: str | None = None, finish_grade: str | None = None,
              property_type: str | None = None,
              limit: int = 100, order_by: str = "price DESC"
              ) -> list[CompRow]:
        """Query comps with flexible filters."""
        clauses = []
        params = []

        if comp_type:
            clauses.append("comp_type = ?")
            params.append(comp_type)
        if county:
            clauses.append("county = ?")
            params.append(county)
        if zip_code:
            clauses.append("zip_code = ?")
            params.append(zip_code)
        if beds is not None:
            clauses.append("beds = ?")
            params.append(beds)
        if min_price is not None:
            clauses.append("price >= ?")
            params.append(min_price)
        if max_price is not None:
            clauses.append("price <= ?")
            params.append(max_price)
        if min_sqft is not None:
            clauses.append("sqft >= ?")
            params.append(min_sqft)
        if max_sqft is not None:
            clauses.append("sqft <= ?")
            params.append(max_sqft)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if finish_grade:
            clauses.append("finish_grade = ?")
            params.append(finish_grade)
        if property_type:
            clauses.append("property_type = ?")
            params.append(property_type)

        where = " AND ".join(clauses) if clauses else "1=1"
        # Validate order_by to prevent injection
        allowed_orders = {"price DESC", "price ASC", "price_per_sqft DESC",
                          "price_per_sqft ASC", "sqft DESC", "sqft ASC",
                          "sale_date DESC", "sale_date ASC", "created_at DESC",
                          "beds ASC", "beds DESC", "address ASC"}
        if order_by not in allowed_orders:
            order_by = "price DESC"

        sql = f"SELECT * FROM comps WHERE {where} ORDER BY {order_by} LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_comp(r) for r in rows]

    def query_nearby(self, lat: float, lng: float, radius_miles: float = 1.0,
                     comp_type: str | None = None, beds: int | None = None,
                     min_price: int | None = None, max_price: int | None = None,
                     limit: int = 50) -> list[tuple[CompRow, float]]:
        """Find comps within radius_miles of a lat/lng point.

        Returns list of (CompRow, distance_miles) tuples sorted by distance.
        Uses a bounding box pre-filter then exact Haversine for precision.
        """
        # Bounding box pre-filter (rough, fast)
        lat_delta = radius_miles / 69.0  # ~69 miles per degree latitude
        lng_delta = radius_miles / (69.0 * math.cos(math.radians(lat)))

        clauses = [
            "latitude != 0", "longitude != 0",
            "latitude BETWEEN ? AND ?",
            "longitude BETWEEN ? AND ?",
        ]
        params: list = [
            lat - lat_delta, lat + lat_delta,
            lng - lng_delta, lng + lng_delta,
        ]

        if comp_type:
            clauses.append("comp_type = ?")
            params.append(comp_type)
        if beds is not None:
            clauses.append("beds = ?")
            params.append(beds)
        if min_price is not None:
            clauses.append("price >= ?")
            params.append(min_price)
        if max_price is not None:
            clauses.append("price <= ?")
            params.append(max_price)

        where = " AND ".join(clauses)
        sql = f"SELECT * FROM comps WHERE {where}"
        rows = self.conn.execute(sql, params).fetchall()

        # Exact Haversine filter and sort
        results = []
        for row in rows:
            comp = self._row_to_comp(row)
            dist = haversine_miles(lat, lng, comp.latitude, comp.longitude)
            if dist <= radius_miles:
                results.append((comp, round(dist, 2)))

        results.sort(key=lambda x: x[1])
        return results[:limit]

    def geocode_record(self, record_id: int) -> bool:
        """Geocode a single comp by its ID. Returns True if successful."""
        row = self.conn.execute(
            "SELECT id, address, city, state, zip_code FROM comps WHERE id = ?",
            (record_id,)
        ).fetchone()
        if not row:
            return False

        result = geocode_address(row["address"], row["city"], row["state"], row["zip_code"])
        if result:
            lat, lng = result
            self.conn.execute(
                "UPDATE comps SET latitude = ?, longitude = ?, updated_at = datetime('now') WHERE id = ?",
                (lat, lng, record_id),
            )
            self.conn.commit()
            return True
        return False

    def geocode_missing(self, limit: int = 100, delay: float = 1.1) -> int:
        """Batch geocode comps that have no lat/lng. Returns count geocoded.

        Respects Nominatim rate limit (1 req/sec) via delay parameter.
        """
        rows = self.conn.execute(
            "SELECT id, address, city, state, zip_code FROM comps "
            "WHERE (latitude = 0 OR longitude = 0) AND address != '' "
            "LIMIT ?",
            (limit,)
        ).fetchall()

        count = 0
        for i, row in enumerate(rows):
            result = geocode_address(row["address"], row["city"], row["state"], row["zip_code"])
            if result:
                lat, lng = result
                self.conn.execute(
                    "UPDATE comps SET latitude = ?, longitude = ?, updated_at = datetime('now') WHERE id = ?",
                    (lat, lng, row["id"]),
                )
                count += 1
                print(f"  [{i+1}/{len(rows)}] {row['address']}: {lat:.6f}, {lng:.6f}")
            else:
                print(f"  [{i+1}/{len(rows)}] {row['address']}: NOT FOUND")

            if i < len(rows) - 1:
                time.sleep(delay)

        self.conn.commit()
        return count

    # ------------------------------------------------------------------
    # Photo management
    # ------------------------------------------------------------------

    def save_photo_urls(self, comp_id: int, urls: list[str]) -> int:
        """Save photo URLs for a comp. Returns count of newly inserted rows."""
        count = 0
        for i, url in enumerate(urls):
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO comp_photos (comp_id, url, position) VALUES (?, ?, ?)",
                    (comp_id, url, i),
                )
                count += 1
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()
        return count

    def get_photos(self, comp_id: int, room_type: str | None = None) -> list[dict]:
        """Get photos for a comp. Optionally filter by room_type."""
        sql = "SELECT * FROM comp_photos WHERE comp_id = ?"
        params: list = [comp_id]
        if room_type:
            sql += " AND room_type = ?"
            params.append(room_type)
        sql += " ORDER BY position"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def set_photo_room_type(self, photo_id: int, room_type: str):
        """Tag a photo with its room type (kitchen, bathroom, etc)."""
        self.conn.execute(
            "UPDATE comp_photos SET room_type = ? WHERE id = ?",
            (room_type, photo_id),
        )
        self.conn.commit()

    def download_comp_photos(self, comp_id: int, max_photos: int = 30) -> list[str]:
        """Download photos for a comp into data/photos/{comp_id}/.

        Returns list of local file paths. Skips already-downloaded photos.
        """
        dest_dir = os.path.join(PHOTOS_DIR, str(comp_id))
        os.makedirs(dest_dir, exist_ok=True)

        rows = self.conn.execute(
            "SELECT id, url, position, downloaded FROM comp_photos "
            "WHERE comp_id = ? ORDER BY position LIMIT ?",
            (comp_id, max_photos),
        ).fetchall()

        paths = []
        for row in rows:
            if row["downloaded"]:
                lp = self.conn.execute(
                    "SELECT local_path FROM comp_photos WHERE id = ?", (row["id"],)
                ).fetchone()
                if lp and lp["local_path"] and os.path.exists(lp["local_path"]):
                    paths.append(lp["local_path"])
                    continue

            url = row["url"]
            ext = "jpg"
            if ".png" in url:
                ext = "png"
            elif ".webp" in url:
                ext = "webp"
            fname = f"photo_{row['position']:03d}.{ext}"
            fpath = os.path.join(dest_dir, fname)

            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                })
                with urllib.request.urlopen(req, timeout=15) as resp:
                    with open(fpath, "wb") as f:
                        f.write(resp.read())
                self.conn.execute(
                    "UPDATE comp_photos SET local_path = ?, downloaded = 1 WHERE id = ?",
                    (fpath, row["id"]),
                )
                paths.append(fpath)
            except Exception as e:
                print(f"  WARNING: Failed to download photo {row['position']}: {e}")

        self.conn.commit()
        return paths

    def sync_photo_urls_from_comps(self) -> int:
        """Populate comp_photos table from photo_urls JSON in comps table.

        For comps that have photo_urls but no entries in comp_photos yet.
        Returns count of photos added.
        """
        rows = self.conn.execute(
            "SELECT id, photo_urls FROM comps WHERE photo_urls != '[]' AND photo_urls != ''"
        ).fetchall()
        total = 0
        for row in rows:
            try:
                urls = json.loads(row["photo_urls"]) if isinstance(row["photo_urls"], str) else row["photo_urls"]
            except (json.JSONDecodeError, TypeError):
                continue
            if urls:
                total += self.save_photo_urls(row["id"], urls)
        return total

    def photo_stats(self) -> dict:
        """Get photo statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM comp_photos").fetchone()[0]
        downloaded = self.conn.execute(
            "SELECT COUNT(*) FROM comp_photos WHERE downloaded = 1"
        ).fetchone()[0]
        comps_with_photos = self.conn.execute(
            "SELECT COUNT(DISTINCT comp_id) FROM comp_photos"
        ).fetchone()[0]
        by_room = {}
        for row in self.conn.execute(
            "SELECT room_type, COUNT(*) as cnt FROM comp_photos GROUP BY room_type ORDER BY cnt DESC"
        ).fetchall():
            by_room[row["room_type"] or "untagged"] = row["cnt"]
        return {
            "total_photos": total,
            "downloaded": downloaded,
            "comps_with_photos": comps_with_photos,
            "by_room_type": by_room,
        }

    def count(self, comp_type: str | None = None, county: str | None = None) -> int:
        """Count comps matching filters."""
        clauses = []
        params = []
        if comp_type:
            clauses.append("comp_type = ?")
            params.append(comp_type)
        if county:
            clauses.append("county = ?")
            params.append(county)
        where = " AND ".join(clauses) if clauses else "1=1"
        row = self.conn.execute(f"SELECT COUNT(*) FROM comps WHERE {where}", params).fetchone()
        return row[0]

    def stats(self) -> dict:
        """Get summary statistics."""
        total = self.count()
        sales = self.count("sale")
        rentals = self.count("rental")

        county_counts = {}
        for row in self.conn.execute(
            "SELECT county, comp_type, COUNT(*) as cnt FROM comps GROUP BY county, comp_type"
        ).fetchall():
            key = f"{row['county']}_{row['comp_type']}"
            county_counts[key] = row["cnt"]

        source_counts = {}
        for row in self.conn.execute(
            "SELECT source, COUNT(*) as cnt FROM comps GROUP BY source ORDER BY cnt DESC"
        ).fetchall():
            source_counts[row["source"] or "unknown"] = row["cnt"]

        avg_sale = 0
        avg_rental = 0
        if sales:
            row = self.conn.execute(
                "SELECT AVG(price) FROM comps WHERE comp_type='sale' AND price > 0"
            ).fetchone()
            avg_sale = int(row[0] or 0)
        if rentals:
            row = self.conn.execute(
                "SELECT AVG(price) FROM comps WHERE comp_type='rental' AND price > 0"
            ).fetchone()
            avg_rental = int(row[0] or 0)

        geocoded = self.conn.execute(
            "SELECT COUNT(*) FROM comps WHERE latitude != 0 AND longitude != 0"
        ).fetchone()[0]

        photo_info = self.photo_stats()

        return {
            "total": total,
            "sales": sales,
            "rentals": rentals,
            "geocoded": geocoded,
            "avg_sale_price": avg_sale,
            "avg_rental_price": avg_rental,
            "by_county": county_counts,
            "by_source": source_counts,
            "photos": photo_info,
            "db_path": self.db_path,
        }

    def delete_all(self, comp_type: str | None = None):
        """Delete all comps, optionally filtered by type."""
        if comp_type:
            self.conn.execute("DELETE FROM comps WHERE comp_type = ?", (comp_type,))
        else:
            self.conn.execute("DELETE FROM comps")
        self.conn.commit()

    def export_json(self, comp_type: str | None = None) -> str:
        """Export comps as a JSON string."""
        comps = self.query(comp_type=comp_type, limit=100000)
        data = []
        for c in comps:
            d = asdict(c)
            d.pop("id", None)
            data.append(d)
        return json.dumps(data, indent=2)

    def export_csv_rows(self, comp_type: str | None = None) -> list[dict]:
        """Export comps as a list of flat dicts (for CSV)."""
        comps = self.query(comp_type=comp_type, limit=100000)
        rows = []
        for c in comps:
            d = asdict(c)
            d.pop("id", None)
            d["photo_urls"] = json.dumps(d["photo_urls"])
            rows.append(d)
        return rows

    def _row_to_comp(self, row: sqlite3.Row) -> CompRow:
        """Convert a sqlite3.Row to a CompRow."""
        d = dict(row)
        photos = d.pop("photo_urls", "[]")
        try:
            d["photo_urls"] = json.loads(photos) if isinstance(photos, str) else photos
        except (json.JSONDecodeError, TypeError):
            d["photo_urls"] = []
        return CompRow(**d)


# ---------------------------------------------------------------------------
# CLI formatting
# ---------------------------------------------------------------------------

def fmt(val) -> str:
    return f"${val:,}"


def print_stats(db: CompsDB):
    """Print database statistics."""
    s = db.stats()
    print(f"\n{'=' * 60}")
    print(f"  COMPS DATABASE — {s['db_path']}")
    print(f"{'=' * 60}\n")
    print(f"  {'Total records':<30s} {s['total']:,}")
    print(f"  {'Sale comps':<30s} {s['sales']:,}")
    print(f"  {'Rental comps':<30s} {s['rentals']:,}")
    print(f"  {'Geocoded (lat/lng)':<30s} {s['geocoded']:,}")
    if s["avg_sale_price"]:
        print(f"  {'Avg sale price':<30s} {fmt(s['avg_sale_price'])}")
    if s["avg_rental_price"]:
        print(f"  {'Avg monthly rent':<30s} {fmt(s['avg_rental_price'])}")

    if s["by_county"]:
        print(f"\n  --- By County & Type ---")
        for key, count in sorted(s["by_county"].items()):
            print(f"    {key:<30s} {count:,}")

    if s["by_source"]:
        print(f"\n  --- By Source ---")
        for src, count in s["by_source"].items():
            print(f"    {src:<30s} {count:,}")

    p = s.get("photos", {})
    if p.get("total_photos", 0):
        print(f"\n  --- Photos ---")
        print(f"    {'Total photo links':<30s} {p['total_photos']:,}")
        print(f"    {'Downloaded locally':<30s} {p['downloaded']:,}")
        print(f"    {'Comps with photos':<30s} {p['comps_with_photos']:,}")
        if p.get("by_room_type"):
            for room, cnt in p["by_room_type"].items():
                print(f"    {'  ' + room:<30s} {cnt:,}")

    print(f"\n{'=' * 60}")


def print_query_results(comps: list[CompRow], comp_type: str | None = None):
    """Print query results as a table."""
    if not comps:
        print("  No comps found matching your filters.")
        return

    is_rental = comp_type == "rental" or (comps and comps[0].comp_type == "rental")
    price_label = "Rent/mo" if is_rental else "Price"

    print(f"\n  {'Address':35s} {price_label:>12s} {'$/sqft':>8s} {'Bed':>4s} {'Bath':>5s} {'Sqft':>7s} {'Source':>10s} {'Grade':>5s}")
    print(f"  {'-'*35} {'-'*12} {'-'*8} {'-'*4} {'-'*5} {'-'*7} {'-'*10} {'-'*5}")
    for c in comps:
        addr = (c.address[:33] + "..") if len(c.address) > 35 else c.address
        ppsf = f"${c.price_per_sqft:.2f}" if c.price_per_sqft else "-"
        grade = c.finish_grade or "-"
        print(f"  {addr:35s} {fmt(c.price):>12s} {ppsf:>8s} {c.beds:>4d} {c.baths:>5.1f} {c.sqft:>7,} {c.source:>10s} {grade:>5s}")

    print(f"\n  {len(comps)} results")


def print_nearby_results(results: list[tuple[CompRow, float]], lat: float, lng: float,
                         radius: float, comp_type: str | None = None):
    """Print nearby query results with distance."""
    if not results:
        print(f"  No comps found within {radius} miles of ({lat:.4f}, {lng:.4f}).")
        print(f"  Try: python comps_db.py geocode   (to geocode existing comps first)")
        return

    is_rental = comp_type == "rental" or results[0][0].comp_type == "rental"
    price_label = "Rent/mo" if is_rental else "Price"

    print(f"\n  Comps within {radius} mi of ({lat:.4f}, {lng:.4f})")
    print(f"\n  {'Address':30s} {'Dist':>6s} {price_label:>12s} {'$/sqft':>8s} {'Bed':>4s} {'Sqft':>7s} {'Lat':>10s} {'Lng':>11s}")
    print(f"  {'-'*30} {'-'*6} {'-'*12} {'-'*8} {'-'*4} {'-'*7} {'-'*10} {'-'*11}")
    for comp, dist in results:
        addr = (comp.address[:28] + "..") if len(comp.address) > 30 else comp.address
        ppsf = f"${comp.price_per_sqft:.2f}" if comp.price_per_sqft else "-"
        print(f"  {addr:30s} {dist:>5.2f}m {fmt(comp.price):>12s} {ppsf:>8s} {comp.beds:>4d} {comp.sqft:>7,} {comp.latitude:>10.5f} {comp.longitude:>11.5f}")

    print(f"\n  {len(results)} results within {radius} miles")


def _parse_near(value: str) -> tuple[float | None, float | None]:
    """Parse a --near value as 'lat,lng' or geocode an address string."""
    # Try parsing as lat,lng
    parts = value.split(",")
    if len(parts) == 2:
        try:
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except ValueError:
            pass
    # Treat as address and geocode
    result = geocode_address(value)
    if result:
        return result
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Comps database CLI")
    sub = parser.add_subparsers(dest="command")

    # stats
    sub.add_parser("stats", help="Show database statistics")

    # query
    q = sub.add_parser("query", help="Query comps")
    q.add_argument("--type", choices=["sale", "rental"], default=None)
    q.add_argument("--county", type=str, default=None)
    q.add_argument("--zip", type=str, default=None)
    q.add_argument("--beds", type=int, default=None)
    q.add_argument("--min-price", type=int, default=None)
    q.add_argument("--max-price", type=int, default=None)
    q.add_argument("--min-sqft", type=int, default=None)
    q.add_argument("--max-sqft", type=int, default=None)
    q.add_argument("--source", type=str, default=None)
    q.add_argument("--grade", type=str, default=None)
    q.add_argument("--property-type", type=str, default=None)
    q.add_argument("--near", type=str, default=None,
                   help="Lat,lng or address for distance search (e.g. '39.75,-104.99' or '123 Main St, Denver, CO')")
    q.add_argument("--radius", type=float, default=1.0,
                   help="Search radius in miles (default: 1.0, used with --near)")
    q.add_argument("--limit", type=int, default=50)
    q.add_argument("--order", type=str, default="price DESC",
                   help="Order by (e.g. 'price DESC', 'sqft ASC')")

    # geocode
    g = sub.add_parser("geocode", help="Geocode comps that lack lat/lng")
    g.add_argument("--id", type=int, default=None,
                   help="Geocode a single comp by ID")
    g.add_argument("--limit", type=int, default=100,
                   help="Max comps to geocode in batch (default: 100)")
    g.add_argument("--delay", type=float, default=1.1,
                   help="Delay between requests in seconds (default: 1.1)")

    # export
    e = sub.add_parser("export", help="Export comps to file")
    e.add_argument("--type", choices=["sale", "rental"], default=None)
    e.add_argument("--format", choices=["json", "csv"], default="json")
    e.add_argument("--output", "-o", type=str, default=None)

    # import
    i = sub.add_parser("import", help="Import comps from JSON file")
    i.add_argument("--file", "-f", type=str, required=True)
    i.add_argument("--type", choices=["sale", "rental"], required=True)

    # photos
    p = sub.add_parser("photos", help="Manage comp photos")
    p.add_argument("--sync", action="store_true",
                   help="Populate comp_photos table from photo_urls in comps")
    p.add_argument("--download", type=int, default=None, metavar="COMP_ID",
                   help="Download photos for a specific comp ID")
    p.add_argument("--download-all", action="store_true",
                   help="Download photos for all comps that have URLs")
    p.add_argument("--list", type=int, default=None, metavar="COMP_ID",
                   help="List photos for a comp ID")
    p.add_argument("--max", type=int, default=30,
                   help="Max photos to download per comp (default: 30)")

    args = parser.parse_args()

    with CompsDB() as db:
        if args.command == "stats":
            print_stats(db)

        elif args.command == "query":
            if args.near:
                # Parse --near as "lat,lng" or as an address to geocode
                lat, lng = _parse_near(args.near)
                if lat is None:
                    print(f"  Could not resolve location: {args.near}")
                    return
                results = db.query_nearby(
                    lat, lng, radius_miles=args.radius,
                    comp_type=args.type, beds=args.beds,
                    min_price=args.min_price, max_price=args.max_price,
                    limit=args.limit,
                )
                print_nearby_results(results, lat, lng, args.radius, args.type)
            else:
                comps = db.query(
                    comp_type=args.type, county=args.county, zip_code=args.zip,
                    beds=args.beds, min_price=args.min_price, max_price=args.max_price,
                    min_sqft=args.min_sqft, max_sqft=args.max_sqft,
                    source=args.source, finish_grade=args.grade,
                    property_type=args.property_type,
                    limit=args.limit, order_by=args.order,
                )
                print_query_results(comps, args.type)

        elif args.command == "export":
            if args.format == "json":
                data = db.export_json(args.type)
                if args.output:
                    with open(args.output, "w") as f:
                        f.write(data)
                    print(f"  Exported to {args.output}")
                else:
                    print(data)
            elif args.format == "csv":
                rows = db.export_csv_rows(args.type)
                if not rows:
                    print("  No data to export.")
                    return
                out = args.output or f"comps_{args.type or 'all'}.csv"
                with open(out, "w", newline="") as f:
                    writer = csv_mod.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"  Exported {len(rows)} rows to {out}")

        elif args.command == "import":
            with open(args.file) as f:
                data = json.load(f)
            comps = []
            for d in data:
                d["comp_type"] = args.type
                comps.append(CompRow(**{k: v for k, v in d.items()
                                       if k in CompRow.__dataclass_fields__}))
            count = db.insert_many(comps)
            print(f"  Imported {count} new comps ({len(comps)} total in file)")

        elif args.command == "geocode":
            if args.id:
                ok = db.geocode_record(args.id)
                if ok:
                    comp = db.query(limit=100000)
                    match = [c for c in comp if c.id == args.id]
                    if match:
                        c = match[0]
                        print(f"  Geocoded: {c.address} -> ({c.latitude:.6f}, {c.longitude:.6f})")
                else:
                    print(f"  Failed to geocode record {args.id}")
            else:
                missing = db.conn.execute(
                    "SELECT COUNT(*) FROM comps WHERE (latitude = 0 OR longitude = 0) AND address != ''"
                ).fetchone()[0]
                print(f"\n  {missing} comps need geocoding (limit: {args.limit})")
                if missing:
                    count = db.geocode_missing(limit=args.limit, delay=args.delay)
                    print(f"\n  Geocoded {count} comps successfully")

        elif args.command == "photos":
            if args.sync:
                count = db.sync_photo_urls_from_comps()
                print(f"  Synced {count} photo URLs to comp_photos table")
            elif args.download is not None:
                paths = db.download_comp_photos(args.download, max_photos=args.max)
                print(f"  Downloaded {len(paths)} photos for comp {args.download}")
                for p in paths:
                    print(f"    {p}")
            elif args.download_all:
                comp_ids = [row[0] for row in db.conn.execute(
                    "SELECT DISTINCT comp_id FROM comp_photos WHERE downloaded = 0"
                ).fetchall()]
                total = 0
                for cid in comp_ids:
                    paths = db.download_comp_photos(cid, max_photos=args.max)
                    total += len(paths)
                    if paths:
                        print(f"  Comp {cid}: downloaded {len(paths)} photos")
                print(f"\n  Total: downloaded {total} photos for {len(comp_ids)} comps")
            elif args.list is not None:
                photos = db.get_photos(args.list)
                if not photos:
                    print(f"  No photos for comp {args.list}")
                else:
                    print(f"\n  Photos for comp {args.list}:")
                    for p in photos:
                        dl = "Y" if p["downloaded"] else "N"
                        room = p["room_type"] or "-"
                        local = p["local_path"] or "-"
                        print(f"    [{p['position']:3d}] {room:<10s} DL={dl}  {local}")
                        print(f"          {p['url'][:100]}")
            else:
                ps = db.photo_stats()
                print(f"\n  --- Photo Stats ---")
                print(f"  {'Total photo links':<30s} {ps['total_photos']:,}")
                print(f"  {'Downloaded locally':<30s} {ps['downloaded']:,}")
                print(f"  {'Comps with photos':<30s} {ps['comps_with_photos']:,}")
                print(f"  {'Photos directory':<30s} {PHOTOS_DIR}")
                if ps.get("by_room_type"):
                    print(f"\n  --- By Room Type ---")
                    for room, cnt in ps["by_room_type"].items():
                        print(f"    {room:<30s} {cnt:,}")

        else:
            parser.print_help()


if __name__ == "__main__":
    main()
