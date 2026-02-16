---
name: comps-search
description: Shared workflow for searching, scraping, and storing property comps (both sales and rentals) in the SQLite database. Use as a sub-skill when the user wants to find and save comps from Zillow, Redfin, Trulia, etc.
---

# Comps Search — Shared Scraping & Storage Workflow

This is a shared workflow for both sale comps and rental comps. It handles:
1. Generating search URLs for the right comp type
2. Scraping listings from Zillow/Redfin/Trulia/etc.
3. Downloading listing photos
4. Storing everything in the SQLite database (data/comps.db)

## Step 1: Generate search URLs

For **sale** comps (recently sold):
```bash
uv run comp-extractor --type sale --county <COUNTY> --beds <N> --price <N>
```

For **rental** comps:
```bash
uv run comp-extractor --type rental --county <COUNTY> --beds <N>
```

## Step 2: Scrape listings

For each URL generated:
1. Use **WebFetch** to load the page
2. Extract listing data from the HTML:
   - Sale comps: address, sold price, beds, baths, sqft, sold date, lot size, year built
   - Rental comps: address, rent/mo, beds, baths, sqft, available date, deposit
3. Extract ALL photo URLs from each listing page
4. Compute price_per_sqft = price / sqft

## Step 3: Build comp records

Create JSON with an array of objects. For sale comps:
```json
[
  {
    "address": "123 Main St",
    "city": "Denver",
    "county": "denver",
    "zip_code": "80202",
    "latitude": 39.7508,
    "longitude": -104.9965,
    "sale_price": 625000,
    "sale_date": "2026-01-15",
    "beds": 3,
    "baths": 2,
    "sqft": 1800,
    "lot_sqft": 5000,
    "year_built": 2005,
    "price_per_sqft": 347.22,
    "property_type": "sfh",
    "listing_url": "https://...",
    "photo_urls": ["https://...", "https://..."],
    "source": "zillow",
    "days_on_market": 12,
    "garage": "2-car attached",
    "hoa": 0,
    "notes": ""
  }
]
```

Include `latitude` and `longitude` if available from the listing. If not, they can be geocoded later with `uv run comp-extractor --geocode`.

For rental comps, use the same format but `sale_price` = monthly rent.

## Step 4: Save to database

```bash
uv run comp-extractor --load comps.json --type sale --price 625000 --sqft 1800
uv run comp-extractor --load comps.json --type rental --price 3000 --sqft 1600
```

This saves to `data/comps.db` and shows an analysis.

Or programmatically:
```python
from comp_extractor import CompRecord, save_comps_to_db
comps = [CompRecord(address="123 Main St", sale_price=625000, ...)]
save_comps_to_db(comps, comp_type="sale")
```

## Step 5: Download photos for finish grading

```python
from comp_extractor import download_comp_photos
for comp in comps:
    paths = download_comp_photos(comp)
```

Then use the **finish-grade** skill to view and grade kitchen/bathroom photos.

## Step 6: Geocode saved comps

After saving, geocode comps for distance searching:
```bash
uv run comp-extractor --geocode            # batch geocode all missing
uv run comp-extractor --geocode-id <ID>    # geocode a single comp
uv run comps-db geocode                    # via DB CLI
```

## Step 7: Query saved comps

By county/beds:
```bash
uv run comp-extractor --db-query --type sale --county denver --beds 3
uv run comp-extractor --db-query --type rental --county denver --beds 3
uv run comp-extractor --db-stats
```

By distance (requires geocoded comps):
```bash
uv run comp-extractor --db-query --type sale --near "123 Main St, Denver, CO" --radius 1.5
uv run comp-extractor --db-query --type sale --near "39.75,-104.99" --radius 2
uv run comps-db query --type sale --near "39.75,-104.99" --radius 2
```

Full DB CLI:
```bash
uv run comps-db query --type sale --county denver --beds 3 --min-price 500000
uv run comps-db query --type rental --county denver --beds 3 --max-price 3500
uv run comps-db stats
uv run comps-db export --type sale --format csv --output sale_comps.csv
```

## Database schema

The SQLite database (`data/comps.db`) stores both sale and rental comps in a single `comps` table:
- `comp_type`: "sale" or "rental"
- `price`: sale price or monthly rent
- `latitude`/`longitude`: geocoded location for distance search
- Common fields: address, city, county, zip, beds, baths, sqft, etc.
- Sale-specific: sale_date, days_on_market, list_price, sale_to_list
- Rental-specific: lease_type, available_date, deposit, pet_policy
- Photos stored as JSON array of URLs
- Automatic dedup on (comp_type, address, price, source)
- Spatial index on (latitude, longitude) for fast nearby queries
