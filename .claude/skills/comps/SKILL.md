---
name: comps
description: Find comparable properties (sales or rentals) in the Denver metro area. Use when the user asks about comps, comparable sales, recently sold properties, rental comps, neighborhood data, or property valuation from Redfin/Zillow/Trulia. Routes to sold-comps or rental comps as needed.
---

# Comps — Sales & Rental Comparable Properties

This skill handles both **sale comps** (recently sold) and **rental comps** (active/recent rentals). All comps are stored in a shared SQLite database at `data/comps.db`.

## Determine comp type

Ask the user or infer from context:
- **Sale comps**: "what did houses sell for", "recently sold", "value my property"
- **Rental comps**: "what would this rent for", "rental comps", "comparable rents"

## For sale comps

Use the **sold-comps** skill, or run directly:
```bash
uv run comp-extractor --type sale --county <COUNTY> --beds <N> --price <N>
```

## For rental comps

```bash
uv run comp-extractor --type rental --county <COUNTY> --beds <N>
```

## Check existing database first

```bash
uv run comp-extractor --db-query --type sale --county <COUNTY> --beds <N>
uv run comp-extractor --db-query --type rental --county <COUNTY> --beds <N>
uv run comp-extractor --db-stats
```

## Distance search (nearby comps)

Search by proximity to a lat/lng point or address:
```bash
uv run comp-extractor --db-query --type sale --near "39.75,-104.99" --radius 2
uv run comp-extractor --db-query --near "123 Main St, Denver, CO" --radius 1.5
uv run comps-db query --type sale --near "39.75,-104.99" --radius 2
```

## Geocode comps

Comps are geocoded via OpenStreetMap Nominatim (free, no API key):
```bash
uv run comp-extractor --geocode            # batch geocode all missing
uv run comp-extractor --geocode-id 5       # geocode a single comp
uv run comps-db geocode                    # same via DB CLI
uv run comps-db geocode --id 5
```

## Full database CLI

```bash
uv run comps-db stats                                          # overview
uv run comps-db query --type sale --county denver --beds 3     # filter
uv run comps-db query --type rental --min-price 2000           # by rent
uv run comps-db query --type sale --near "1600 Pennsylvania Ave, Denver" --radius 1
uv run comps-db export --type sale --format csv -o comps.csv   # export
uv run comps-db import --file scraped.json --type sale         # import
uv run comps-db geocode                                        # geocode missing
```

## Scraping workflow

Follow the **comps-search** sub-skill for the full scrape-and-store pipeline:
1. Generate URLs for sale or rental
2. Scrape with WebFetch / Bright Data MCP
3. Extract listing data + all photo URLs
4. Save to JSON -> load into DB
5. Download photos -> finish-grade for kitchen/bathroom quality

## After running

Present comp analysis and remind user:
- Comps are saved in `data/comps.db` for future queries
- Use `--db-query` to search without re-scraping
- Use `--near` + `--radius` for distance-based search around a property
- Run `--geocode` to geocode comps that lack lat/lng
- Connect to rent-estimator for income projections
- Connect to refinance-analyzer for cash flow modeling
