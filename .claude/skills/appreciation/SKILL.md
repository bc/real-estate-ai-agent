---
name: appreciation
description: Look up property appreciation rates by zip code for Denver metro counties. Use when the user asks about home price trends, appreciation, home values over time, ZHVI, or how much a property has appreciated in a given zip code or area.
---

# Property Appreciation Tracker

Look up historical home price appreciation by zip code using Zillow Home Value Index (ZHVI) data synced locally.

## First-time setup

If data hasn't been synced yet:
```bash
python appreciation_tracker.py --sync
```
This downloads Zillow ZHVI data (~60MB CSV) to the `data/` directory.

## Single zip code lookup

```bash
python appreciation_tracker.py --zip <ZIPCODE>
```

Shows current home value and appreciation over 1, 3, 5, and 10 years with CAGR.

## Compare multiple zip codes

```bash
python appreciation_tracker.py --zip 80202 80204 80211 80205
```

Shows side-by-side comparison table sorted by CAGR.

## All zips in a county

```bash
python appreciation_tracker.py --county denver
python appreciation_tracker.py --county douglas
python appreciation_tracker.py --county adams
python appreciation_tracker.py --county arapahoe
python appreciation_tracker.py --county jefferson
```

## Custom time windows

```bash
python appreciation_tracker.py --zip 80202 --years 1 3 5 7 10 15 20
```

## Data refresh

Re-sync to get latest monthly ZHVI values:
```bash
python appreciation_tracker.py --sync
```

Data source: Zillow ZHVI All Homes (SFR, Condo/Co-op), Middle Tier, Smoothed, Seasonally Adjusted.

## After running

Present the results and note:
1. CAGR (compound annual growth rate) is the most comparable metric across periods
2. Past appreciation does not guarantee future returns
3. Micro-market variation within a zip code can be significant
4. For investment analysis, combine with rent_estimator.py for yield calculations
