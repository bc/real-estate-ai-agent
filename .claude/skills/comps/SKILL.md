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
python comp_extractor.py --type sale --county <COUNTY> --beds <N> --price <N>
```

## For rental comps

```bash
python comp_extractor.py --type rental --county <COUNTY> --beds <N>
```

## Check existing database first

```bash
python comp_extractor.py --db-query --type sale --county <COUNTY> --beds <N>
python comp_extractor.py --db-query --type rental --county <COUNTY> --beds <N>
python comp_extractor.py --db-stats
```

## Full database CLI

```bash
python comps_db.py stats                                          # overview
python comps_db.py query --type sale --county denver --beds 3     # filter
python comps_db.py query --type rental --min-price 2000           # by rent
python comps_db.py export --type sale --format csv -o comps.csv   # export
python comps_db.py import --file scraped.json --type sale         # import
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
- Connect to rent_estimator.py for income projections
- Connect to refinance_analyzer.py for cash flow modeling
