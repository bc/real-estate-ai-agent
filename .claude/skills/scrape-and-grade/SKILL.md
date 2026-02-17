---
name: scrape-and-grade
description: End-to-end workflow for scraping rental or sale comps, downloading photos, and grading finish quality. Use when the user wants comp data AND finish grading in one pass.
---

# Scrape and Grade — Comps + Photos + Finish Grading

End-to-end workflow that combines comp scraping, photo collection, and finish quality grading into a single pipeline.

## Gather from user

| Parameter | Required | Description |
|---|---|---|
| Zip code | Yes | Target zip code for comp search |
| County | Yes | denver, douglas, adams, arapahoe, or jefferson |
| Bedrooms | Yes | Number of bedrooms to filter |
| Comp type | Yes | "rental" or "sale" |
| Subject address | No | For distance-based filtering of comps |

## Workflow

### Step 1: Scrape comps

Use the stealth browser scraper to collect listings with photos:
```bash
uv run browser-scraper --rental --zip <ZIP> --beds <N> --county <COUNTY> --photos
```

Or for sold comps:
```bash
uv run browser-scraper --sold --zip <ZIP> --beds <N> --price <PRICE> --county <COUNTY> --photos
```

If the browser scraper hits CAPTCHAs, fall back to **WebFetch** on Trulia/Craigslist search pages:
1. Fetch the search page with WebFetch
2. Extract listing data and photo URLs from the HTML
3. Save as JSON, then load: `uv run comp-extractor --load comps.json --type rental`

### Step 2: Sync and download photos

After comps are in the database, sync photo URLs and download:
```bash
uv run comps-db photos --sync
uv run comps-db photos --download-all --max 10
```

Or download photos for a specific comp:
```bash
uv run comps-db photos --download <COMP_ID> --max 20
```

Photos are saved to `data/photos/<comp_id>/photo_000.jpg`.

### Step 3: Geocode and filter by distance

```bash
uv run comps-db geocode
uv run comps-db query --type rental --near "<ADDRESS>" --radius 2
```

### Step 4: Grade finish quality

For each nearby comp with photos:

1. **List photos**: `uv run comps-db photos --list <COMP_ID>`
2. **View photos**: Use the Read tool to view each photo in `data/photos/<comp_id>/`
3. **Identify rooms**: Determine which photos show kitchens vs bathrooms
4. **Grade each room**: Apply the A-F rubric from `uv run finish-grader --rubric`
5. **Compute overall grade**:
   ```python
   from finish_grader import overall_from_rooms, GRADES
   grade = overall_from_rooms("B", "C")  # Kitchen B, Bath C -> overall B
   multiplier = GRADES[grade]["rent_multiplier"]
   ```

### Step 5: Adjust rent estimates

Use the finish grade to get an accurate rent estimate:
```bash
uv run rent-estimator --county <COUNTY> --beds <N> --baths <N> --sqft <N> --grade <GRADE>
```

### Step 6: Present results

For each graded comp, show:
- Address, distance from subject, rent/price
- Beds, baths, sqft
- Kitchen grade, bathroom grade, overall grade
- Grade-adjusted rent estimate

Then present the subject property analysis with the appropriate grade applied.

## Grade rubric quick reference

| Grade | Label | Rent multiplier |
|---|---|---|
| A | High-end custom | x1.20 (+20%) |
| B | Updated / nice | x1.05 (+5%) |
| C | Builder grade | x1.00 (baseline) |
| D | Dated / worn | x0.90 (-10%) |
| F | Poor condition | x0.78 (-22%) |

Kitchen weight: 60% | Bathroom weight: 40%
