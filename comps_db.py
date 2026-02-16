"""
SQLite database for storing and querying property comps.

Stores both rental comps and sale comps in a single database with a
shared schema. Supports insert, query, dedup, and analysis operations.

The database is stored at data/comps.db (created on first use).
Both comp_extractor.py and rent_estimator.py write to and read from this DB.

Usage as a library:
    from comps_db import CompsDB, CompRow
    db = CompsDB()
    db.insert(CompRow(comp_type="sale", address="123 Main St", ...))
    results = db.query(comp_type="sale", county="denver", beds=3)
    db.stats()

Usage as CLI:
    python comps_db.py stats
    python comps_db.py query --type sale --county denver --beds 3
    python comps_db.py query --type rental --county denver --min-price 2000
    python comps_db.py export --type sale --format json
    python comps_db.py export --type rental --format csv
    python comps_db.py import --file comps.json --type sale
"""

import argparse
import csv as csv_mod
import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "comps.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS comps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comp_type       TEXT NOT NULL,           -- 'sale' or 'rental'
    address         TEXT NOT NULL DEFAULT '',
    city            TEXT NOT NULL DEFAULT '',
    county          TEXT NOT NULL DEFAULT '',
    zip_code        TEXT NOT NULL DEFAULT '',
    state           TEXT NOT NULL DEFAULT 'CO',

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
"""


@dataclass
class CompRow:
    """A comp record for the database. Used for both sales and rentals."""
    comp_type: str = "sale"
    address: str = ""
    city: str = ""
    county: str = ""
    zip_code: str = ""
    state: str = "CO"
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
        self.conn.executescript(SCHEMA)
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
                    price, price_per_sqft, beds, baths, sqft, lot_sqft, year_built,
                    property_type, listing_url, source, photo_urls, photo_count,
                    sale_date, days_on_market, list_price, sale_to_list,
                    lease_type, available_date, deposit, pet_policy,
                    garage, hoa, finish_grade, notes, scraped_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
            """, (
                comp.comp_type, comp.address, comp.city, comp.county,
                comp.zip_code, comp.state,
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

        return {
            "total": total,
            "sales": sales,
            "rentals": rentals,
            "avg_sale_price": avg_sale,
            "avg_rental_price": avg_rental,
            "by_county": county_counts,
            "by_source": source_counts,
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
    q.add_argument("--limit", type=int, default=50)
    q.add_argument("--order", type=str, default="price DESC",
                   help="Order by (e.g. 'price DESC', 'sqft ASC')")

    # export
    e = sub.add_parser("export", help="Export comps to file")
    e.add_argument("--type", choices=["sale", "rental"], default=None)
    e.add_argument("--format", choices=["json", "csv"], default="json")
    e.add_argument("--output", "-o", type=str, default=None)

    # import
    i = sub.add_parser("import", help="Import comps from JSON file")
    i.add_argument("--file", "-f", type=str, required=True)
    i.add_argument("--type", choices=["sale", "rental"], required=True)

    args = parser.parse_args()

    with CompsDB() as db:
        if args.command == "stats":
            print_stats(db)

        elif args.command == "query":
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

        else:
            parser.print_help()


if __name__ == "__main__":
    main()
