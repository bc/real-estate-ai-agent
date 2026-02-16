---
name: finish-grade
description: Grade the kitchen and bathroom finish quality of a property from listing photos. Use when the user asks about finish quality, kitchen quality, bathroom condition, renovation grade, or wants to assess a property's interior condition from photos.
---

# Finish Quality Grader

Assess kitchen and bathroom finish quality on an A-F scale from listing photos.

## Grading Scale

- **A** — High-end custom: granite/quartz, custom cabinets, pro appliances, designer tile
- **B** — Updated / nice: modern fixtures, decent stainless appliances, recent updates
- **C** — Builder grade: laminate counters, stock cabinets, basic appliances, functional
- **D** — Dated / worn: old finishes, brass fixtures, worn but functional, needs cosmetic work
- **F** — Poor / gross: damage, mold, broken fixtures, deferred maintenance, needs full reno

## Workflow

### Option A: From a listing URL

1. Get the listing URL from the user
2. Use WebFetch to load the listing page
3. Extract all photo URLs from the page HTML
4. Download photos to a local directory:
   ```bash
   mkdir -p listing_photos
   curl -o listing_photos/photo_001.jpg "https://..."
   ```
5. Proceed to grading (step 4 below)

### Option B: From a photos directory

1. Scan the directory:
   ```bash
   uv run finish-grader --photos-dir ./listing_photos --workflow
   ```
2. This identifies kitchen/bathroom photos by filename

### Step 3: View and identify room photos

For EACH photo in the directory, use the **Read tool** to view the image:
```
Read tool -> /path/to/listing_photos/photo_001.jpg
```

Claude can see images! Classify each as: **kitchen**, **bathroom**, or **skip**.

### Step 4: Grade each kitchen and bathroom photo

For each kitchen/bathroom photo, view it with Read and assess:

**Kitchen — look for:**
- Countertop material (granite/quartz = A-B, laminate = C, formica = D, damaged = F)
- Cabinet quality (custom = A, shaker = B, builder oak = C, dated/peeling = D-F)
- Appliances (Sub-Zero/Wolf = A, stainless mid-range = B, white/black basic = C, old/missing = D-F)
- Backsplash (designer stone = A, subway tile = B, basic/none = C, cracked = D-F)
- Flooring (hardwood = A-B, vinyl plank = B-C, linoleum = C-D, damaged = F)

**Bathroom — look for:**
- Tile work (floor-to-ceiling stone = A, modern ceramic = B, fiberglass insert = C, cracked = D-F)
- Vanity (custom double = A, modern single = B, basic = C, old laminate = D, broken = F)
- Fixtures (designer = A, modern chrome = B, standard = C, brass/gold 90s = D, corroded = F)
- Shower/tub (frameless glass = A, semi-frameless = B, curtain rod = C, yellowed = D, moldy = F)

### Step 5: Aggregate and report

```python
from finish_grader import overall_from_rooms, GRADES
overall = overall_from_rooms("B", "C")  # kitchen=B, bath=C -> overall
multiplier = GRADES[overall]["rent_multiplier"]
```

Kitchen is weighted 60%, bathroom 40%.

### Step 6: Connect to rent estimate

Use the overall grade with the rent estimator:
```bash
uv run rent-estimator --county denver --beds 3 --sqft 1800 --grade <OVERALL_GRADE>
```

## Quick reference

Print the full rubric:
```bash
uv run finish-grader --rubric
```
