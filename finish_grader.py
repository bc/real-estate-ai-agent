"""
Kitchen and bathroom finish quality grader for rental properties.

Downloads listing photos and uses Claude's vision (via the Read tool) to
assess the quality grade of kitchen and bathroom finishes on an A-F scale:
    A — High-end custom (granite/quartz, custom cabinets, pro appliances)
    B — Updated, nice (modern fixtures, decent appliances, recent reno)
    C — Builder grade (functional, stock cabinets, laminate, average)
    D — Dated / worn (old finishes, functional but cosmetically poor)
    F — Poor / gross (broken, heavy wear, mold, deferred maintenance)

Usage:
    python finish_grader.py --url "https://www.zillow.com/homedetails/..."
    python finish_grader.py --photos-dir ./listing_photos
    python finish_grader.py --rubric
    python finish_grader.py --help

Workflow (designed for Claude Code sessions):
    1. Provide a listing URL or a directory of already-downloaded photos
    2. Module identifies kitchen and bathroom images
    3. Claude views each image via Read tool and assigns a grade
    4. Module aggregates grades into an overall finish score
"""

import argparse
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Grading rubric
# ---------------------------------------------------------------------------

GRADES = {
    "A": {
        "label": "High-end custom",
        "rent_multiplier": 1.20,
        "value_impact": "+10-20% vs neighborhood median",
        "kitchen_signals": [
            "Granite, quartz, or marble countertops",
            "Custom or semi-custom cabinetry (soft-close, dovetail)",
            "Professional-grade appliances (Sub-Zero, Wolf, Viking, Thermador)",
            "Pot filler, farmhouse or undermount sink",
            "Designer backsplash (natural stone, hand-laid tile)",
            "Hardwood or high-end tile flooring",
            "Under-cabinet and pendant lighting",
            "Built-in pantry, wine fridge, or butler's pantry",
        ],
        "bathroom_signals": [
            "Floor-to-ceiling tile, natural stone",
            "Frameless glass shower enclosure",
            "Double vanity with stone top",
            "Freestanding soaking tub",
            "Heated floors, towel warmers",
            "Rainfall showerhead, body jets",
            "Designer fixtures (Kohler, Grohe, Brizo)",
            "Custom lighting, mirrors, and hardware",
        ],
    },
    "B": {
        "label": "Updated / nice",
        "rent_multiplier": 1.05,
        "value_impact": "+3-8% vs neighborhood median",
        "kitchen_signals": [
            "Quartz or granite countertops (standard grade)",
            "Shaker-style or modern flat-panel cabinets",
            "Stainless steel appliances (mid-range: Samsung, LG, Whirlpool)",
            "Subway tile or modern backsplash",
            "Vinyl plank or tile flooring (newer)",
            "Updated hardware and fixtures",
            "Recessed or track lighting",
        ],
        "bathroom_signals": [
            "Ceramic or porcelain tile surround",
            "Updated vanity with cultured marble or quartz top",
            "Modern faucets and hardware (Moen, Delta)",
            "Glass shower door (semi-frameless)",
            "Tile floor (porcelain or ceramic)",
            "Updated mirror and lighting",
        ],
    },
    "C": {
        "label": "Builder grade / average",
        "rent_multiplier": 1.00,
        "value_impact": "At neighborhood median",
        "kitchen_signals": [
            "Laminate or basic granite countertops",
            "Builder-grade oak or thermofoil cabinets",
            "Standard appliances (white, black, or basic stainless)",
            "Basic 4-inch backsplash or none",
            "Vinyl, linoleum, or basic tile floor",
            "Standard fixtures, fluorescent lighting",
        ],
        "bathroom_signals": [
            "Fiberglass tub/shower insert",
            "Basic vanity with laminate top",
            "Standard chrome fixtures",
            "Vinyl or basic tile floor",
            "Basic mirror (plate glass, no frame)",
            "Standard lighting (Hollywood bar)",
        ],
    },
    "D": {
        "label": "Dated / worn",
        "rent_multiplier": 0.90,
        "value_impact": "-5-12% vs neighborhood median",
        "kitchen_signals": [
            "Formica or tile countertops (1980s-90s style)",
            "Dated wood cabinets, possibly paint chipping",
            "Older appliances (almond, harvest gold, or mismatched)",
            "Yellowed or cracked backsplash",
            "Worn vinyl or cracked tile floor",
            "Fluorescent box lighting, dated fixtures",
            "Visible wear on handles, drawers sticking",
        ],
        "bathroom_signals": [
            "Yellowed fiberglass or dated tile surround",
            "Old vanity, possibly re-laminated",
            "Brass or gold-tone fixtures (90s era)",
            "Worn or peeling caulk",
            "Outdated wallpaper or paint",
            "Vinyl sheet flooring, possibly lifting",
            "Foggy or chipped mirror",
        ],
    },
    "F": {
        "label": "Poor / gross",
        "rent_multiplier": 0.78,
        "value_impact": "-15-30% vs median; may require reno to rent",
        "kitchen_signals": [
            "Broken or missing countertop pieces",
            "Cabinets falling off hinges, water damage",
            "Non-functional or missing appliances",
            "Mold, grease buildup, visible grime",
            "Badly damaged flooring, exposed subfloor",
            "Broken fixtures, exposed wiring",
            "Pest evidence, odor",
        ],
        "bathroom_signals": [
            "Cracked or broken tiles, holes in walls",
            "Mold/mildew, black stains in grout",
            "Broken or leaking fixtures",
            "Rusted or corroded hardware",
            "Non-functional toilet, sink, or shower",
            "Missing or broken exhaust fan",
            "Water damage, soft spots in floor",
        ],
    },
}


ROOM_KEYWORDS = {
    "kitchen": ["kitchen", "ktchn", "kit ", "counter", "cabinet", "stove",
                "oven", "range", "refrigerator", "fridge", "backsplash",
                "island", "pantry", "dishwasher", "sink"],
    "bathroom": ["bathroom", "bath ", "bthrm", "shower", "tub", "vanity",
                 "toilet", "powder", "ensuite", "master bath", "lavatory"],
}


@dataclass
class RoomGrade:
    room_type: str          # "kitchen" or "bathroom"
    room_label: str         # e.g. "Kitchen", "Primary Bathroom"
    grade: str              # A-F
    grade_label: str
    confidence: str         # "high", "medium", "low"
    photo_path: str
    observations: list[str] = field(default_factory=list)


@dataclass
class FinishReport:
    address: str
    listing_url: str
    total_photos: int
    kitchen_photos: list[str]
    bathroom_photos: list[str]
    grades: list[RoomGrade]
    overall_kitchen_grade: str
    overall_bathroom_grade: str
    overall_grade: str
    rent_multiplier: float
    summary: str


def classify_photo_filename(filename: str) -> str | None:
    """Guess if a photo is kitchen or bathroom based on filename."""
    lower = filename.lower()
    for room, keywords in ROOM_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return room
    return None


def scan_photo_directory(photos_dir: str) -> dict[str, list[str]]:
    """Scan a directory for kitchen and bathroom photos based on filenames."""
    result = {"kitchen": [], "bathroom": [], "unknown": []}
    supported = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}

    for root, dirs, files in os.walk(photos_dir):
        for f in sorted(files):
            ext = Path(f).suffix.lower()
            if ext not in supported:
                continue
            full_path = os.path.join(root, f)
            room = classify_photo_filename(f)
            if room:
                result[room].append(full_path)
            else:
                result["unknown"].append(full_path)

    return result


def avg_grade(grades: list[str]) -> str:
    """Average letter grades. Returns the modal/average grade."""
    if not grades:
        return "C"
    grade_vals = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    val_grades = {v: k for k, v in grade_vals.items()}
    avg = sum(grade_vals.get(g, 2) for g in grades) / len(grades)
    rounded = round(avg)
    return val_grades.get(rounded, "C")


def overall_from_rooms(kitchen_grade: str, bathroom_grade: str) -> str:
    """Combine kitchen and bathroom into overall finish grade."""
    grade_vals = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    val_grades = {v: k for k, v in grade_vals.items()}
    # Kitchen weighted 60%, bathroom 40% (kitchen impacts rent more)
    combined = grade_vals.get(kitchen_grade, 2) * 0.6 + grade_vals.get(bathroom_grade, 2) * 0.4
    return val_grades.get(round(combined), "C")


def print_rubric():
    """Print the full grading rubric."""
    print(f"\n{'=' * 72}")
    print(f"  FINISH QUALITY GRADING RUBRIC (A-F)")
    print(f"{'=' * 72}")

    for grade, info in GRADES.items():
        mult = info["rent_multiplier"]
        sign = "+" if mult >= 1 else ""
        pct = (mult - 1) * 100
        print(f"\n  {'='*68}")
        print(f"  GRADE {grade} — {info['label']}")
        print(f"  Rent adjustment: {sign}{pct:.0f}%  |  Value impact: {info['value_impact']}")
        print(f"  {'='*68}")

        print(f"\n  Kitchen signals:")
        for s in info["kitchen_signals"]:
            print(f"    - {s}")

        print(f"\n  Bathroom signals:")
        for s in info["bathroom_signals"]:
            print(f"    - {s}")

    print(f"\n{'=' * 72}")


def print_grading_workflow(photos_dir: str | None = None, listing_url: str | None = None):
    """Print step-by-step instructions for Claude to grade photos."""
    print(f"\n{'=' * 72}")
    print(f"  FINISH GRADING WORKFLOW")
    print(f"{'=' * 72}\n")

    if listing_url:
        print(f"  Listing: {listing_url}\n")

    print(f"  STEP 1: Get the photos")
    print(f"  -----------------------")
    if listing_url:
        print(f"  a) Use WebFetch to load the listing URL above")
        print(f"  b) Extract all photo/image URLs from the page")
        print(f"  c) Download photos using CompsDB.download_comp_photos(comp_id)")
        print(f"     or use Bash: curl -o photo_001.jpg <URL>")
    if photos_dir:
        print(f"  Photos directory: {photos_dir}")
        scanned = scan_photo_directory(photos_dir)
        print(f"    Kitchen photos found:  {len(scanned['kitchen'])}")
        print(f"    Bathroom photos found: {len(scanned['bathroom'])}")
        print(f"    Unclassified photos:   {len(scanned['unknown'])}")
        if scanned["kitchen"]:
            print(f"\n    Kitchen files:")
            for p in scanned["kitchen"]:
                print(f"      {p}")
        if scanned["bathroom"]:
            print(f"\n    Bathroom files:")
            for p in scanned["bathroom"]:
                print(f"      {p}")
        if scanned["unknown"]:
            print(f"\n    Unclassified (view with Read to identify):")
            for p in scanned["unknown"][:10]:
                print(f"      {p}")
            if len(scanned["unknown"]) > 10:
                print(f"      ... and {len(scanned['unknown']) - 10} more")

    print(f"\n  STEP 2: Identify kitchen and bathroom photos")
    print(f"  -----------------------------------------------")
    print(f"  For each photo, use the Read tool to view it.")
    print(f"  Classify as: kitchen, bathroom, or skip.")
    print(f"  Filename hints: {ROOM_KEYWORDS}")

    print(f"\n  STEP 3: Grade each room photo")
    print(f"  -------------------------------")
    print(f"  View each kitchen/bathroom photo with the Read tool and assess:")
    print(f"    - Countertop material and condition")
    print(f"    - Cabinet style, quality, and condition")
    print(f"    - Appliance brand tier and age")
    print(f"    - Flooring type and condition")
    print(f"    - Fixtures and hardware quality")
    print(f"    - Overall cleanliness and maintenance")
    print(f"    - Any visible damage, wear, or dating")
    print(f"  Assign grade A/B/C/D/F based on the rubric (see --rubric)")

    print(f"\n  STEP 4: Aggregate grades")
    print(f"  -------------------------")
    print(f"  Kitchen weight: 60%  |  Bathroom weight: 40%")
    print(f"  If multiple kitchens/bathrooms: average within each category first")
    print(f"  Use: finish_grader.overall_from_rooms(kitchen_grade, bathroom_grade)")

    print(f"\n  STEP 5: Apply to rent estimate")
    print(f"  --------------------------------")
    print(f"  Use the overall grade with rent_estimator.py --grade <GRADE>")
    print(f"  Grade multipliers:")
    for g, info in GRADES.items():
        mult = info["rent_multiplier"]
        print(f"    {g} ({info['label']:20s}) -> x{mult:.2f}")

    print(f"\n{'=' * 72}")


def print_report(report: FinishReport):
    """Print a finish grading report."""
    w = 38
    print(f"\n{'=' * 66}")
    print(f"  FINISH QUALITY REPORT")
    print(f"{'=' * 66}\n")

    if report.address:
        print(f"  {'Address':{w}s} {report.address}")
    if report.listing_url:
        print(f"  {'Listing':{w}s} {report.listing_url}")
    print(f"  {'Total photos':{w}s} {report.total_photos}")
    print(f"  {'Kitchen photos assessed':{w}s} {len(report.kitchen_photos)}")
    print(f"  {'Bathroom photos assessed':{w}s} {len(report.bathroom_photos)}")
    print()

    if report.grades:
        print(f"  --- Individual Room Grades ---\n")
        for rg in report.grades:
            grade_info = GRADES.get(rg.grade, {})
            print(f"  {rg.room_label:30s}  Grade: {rg.grade} ({rg.grade_label})")
            print(f"    Photo: {rg.photo_path}")
            print(f"    Confidence: {rg.confidence}")
            for obs in rg.observations:
                print(f"    - {obs}")
            print()

    print(f"  --- Overall Assessment ---\n")
    print(f"  {'Kitchen grade':{w}s} {report.overall_kitchen_grade}")
    print(f"  {'Bathroom grade':{w}s} {report.overall_bathroom_grade}")
    print(f"  {'OVERALL FINISH GRADE':{w}s} {report.overall_grade} — {GRADES[report.overall_grade]['label']}")
    print(f"  {'Rent multiplier':{w}s} x{report.rent_multiplier:.2f}")
    print()

    if report.summary:
        print(f"  Summary: {report.summary}")

    print(f"\n{'=' * 66}")


def save_report_json(report: FinishReport, path: str):
    """Save report to JSON."""
    data = asdict(report)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved report to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Grade kitchen and bathroom finish quality from listing photos"
    )
    parser.add_argument("--url", type=str, default=None,
                        help="Listing URL to scrape photos from")
    parser.add_argument("--photos-dir", type=str, default=None,
                        help="Directory containing listing photos")
    parser.add_argument("--rubric", action="store_true",
                        help="Print the full grading rubric")
    parser.add_argument("--workflow", action="store_true",
                        help="Print step-by-step grading workflow for Claude")

    args = parser.parse_args()

    if args.rubric:
        print_rubric()
        return

    if args.workflow or args.photos_dir or args.url:
        print_grading_workflow(args.photos_dir, args.url)
        if args.photos_dir:
            # Also print rubric summary
            print(f"\n  Quick reference — grade by what you SEE:")
            print(f"    A = Wow, this is luxury / magazine-quality")
            print(f"    B = Nice, clearly updated, modern")
            print(f"    C = Fine, nothing special, builder standard")
            print(f"    D = Dated, worn, needs cosmetic refresh")
            print(f"    F = Bad — mold, damage, gross, needs full reno")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
