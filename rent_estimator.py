"""
Denver metro rent estimator.

Estimates monthly rent for residential properties in Denver, Douglas,
Adams, Arapahoe, and Jefferson counties using local median rent data
and property-level adjustments. Also generates scraping URLs for live
rental comps on Zillow, Redfin, Apartments.com, and Trulia.

Usage:
    python rent_estimator.py --county denver --beds 3 --baths 2 --sqft 1800
    python rent_estimator.py --county douglas --beds 4 --baths 3 --sqft 2400 --grade A
    python rent_estimator.py --county denver --beds 3 --baths 2 --sqft 1800 --urls
    python rent_estimator.py --help
"""

import argparse
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Median rent data by county and bedroom count (2025 estimates)
# Sources: Zillow Observed Rent Index, Apartments.com, ACS data
# ---------------------------------------------------------------------------

@dataclass
class CountyRentProfile:
    name: str
    # Median rents by bedroom count
    median_studio: int
    median_1br: int
    median_2br: int
    median_3br: int
    median_4br: int
    median_5br_plus: int
    # Typical price per sq ft for rental
    rent_per_sqft_low: float
    rent_per_sqft_mid: float
    rent_per_sqft_high: float
    # Vacancy rate (%)
    vacancy_rate: float
    notes: list[str]


COUNTY_RENTS: dict[str, CountyRentProfile] = {
    "denver": CountyRentProfile(
        name="Denver (City & County)",
        median_studio=1350, median_1br=1575, median_2br=2050,
        median_3br=2650, median_4br=3200, median_5br_plus=3800,
        rent_per_sqft_low=1.30, rent_per_sqft_mid=1.65, rent_per_sqft_high=2.20,
        vacancy_rate=6.2,
        notes=[
            "Highest rents in metro, especially downtown/LoDo/RiNo/Highlands.",
            "Capitol Hill, Baker, Wash Park command premium for walkability.",
            "Green Valley Ranch, Montbello, Far NE are lowest within Denver.",
        ],
    ),
    "douglas": CountyRentProfile(
        name="Douglas County",
        median_studio=1250, median_1br=1500, median_2br=1950,
        median_3br=2800, median_4br=3500, median_5br_plus=4200,
        rent_per_sqft_low=1.20, rent_per_sqft_mid=1.55, rent_per_sqft_high=2.00,
        vacancy_rate=4.8,
        notes=[
            "Strong SFH rental demand from families (top-rated school districts).",
            "Castle Rock, Parker, Highlands Ranch command premiums.",
            "Newer builds in Sterling Ranch / Meridian rent at top of range.",
        ],
    ),
    "adams": CountyRentProfile(
        name="Adams County",
        median_studio=1100, median_1br=1350, median_2br=1700,
        median_3br=2200, median_4br=2700, median_5br_plus=3200,
        rent_per_sqft_low=1.05, rent_per_sqft_mid=1.35, rent_per_sqft_high=1.75,
        vacancy_rate=6.8,
        notes=[
            "Most affordable in metro. Thornton/Westminster higher than avg.",
            "Commerce City / Federal Heights are budget-tier.",
            "Brighton / rural areas have lower rents but also less demand.",
        ],
    ),
    "arapahoe": CountyRentProfile(
        name="Arapahoe County",
        median_studio=1200, median_1br=1450, median_2br=1850,
        median_3br=2500, median_4br=3100, median_5br_plus=3700,
        rent_per_sqft_low=1.15, rent_per_sqft_mid=1.50, rent_per_sqft_high=1.95,
        vacancy_rate=5.9,
        notes=[
            "Cherry Hills, Greenwood Village at the top. Aurora varies widely.",
            "Centennial / Littleton are mid-to-high range for families.",
            "DTC area commands office-adjacent premium for professional tenants.",
        ],
    ),
    "jefferson": CountyRentProfile(
        name="Jefferson County",
        median_studio=1200, median_1br=1425, median_2br=1800,
        median_3br=2450, median_4br=3000, median_5br_plus=3600,
        rent_per_sqft_low=1.10, rent_per_sqft_mid=1.45, rent_per_sqft_high=1.85,
        vacancy_rate=5.5,
        notes=[
            "Lakewood is the volume market. Golden commands a premium.",
            "Arvada (Old Town) trending up. Wheat Ridge is value play.",
            "Evergreen / mountain communities have seasonal demand swings.",
        ],
    ),
}


# ---------------------------------------------------------------------------
# Finish quality adjustments
# ---------------------------------------------------------------------------

GRADE_ADJUSTMENTS = {
    "A": {"label": "High-end custom", "multiplier": 1.20,
           "desc": "Custom finishes, high-end appliances, designer fixtures, hardwood/stone"},
    "B": {"label": "Updated / nice",  "multiplier": 1.05,
           "desc": "Recent updates, decent appliances, modern but not luxury"},
    "C": {"label": "Builder grade",   "multiplier": 1.00,
           "desc": "Standard builder grade, functional, average condition"},
    "D": {"label": "Dated / worn",    "multiplier": 0.90,
           "desc": "Old finishes, worn but functional, needs cosmetic work"},
    "F": {"label": "Poor condition",  "multiplier": 0.78,
           "desc": "Significant wear, outdated, deferred maintenance"},
}


# ---------------------------------------------------------------------------
# Property type adjustments
# ---------------------------------------------------------------------------

PROPERTY_TYPE_ADJ = {
    "sfh": {"label": "Single-family home", "multiplier": 1.10},
    "townhome": {"label": "Townhome / rowhome", "multiplier": 1.00},
    "condo": {"label": "Condo / apartment", "multiplier": 0.95},
    "duplex": {"label": "Duplex (per unit)", "multiplier": 0.92},
}


# ---------------------------------------------------------------------------
# Extra feature adjustments (additive $/mo)
# ---------------------------------------------------------------------------

FEATURE_ADJUSTMENTS = {
    "garage_1car": 75,
    "garage_2car": 150,
    "garage_3car": 200,
    "finished_basement": 250,
    "fenced_yard": 50,
    "central_ac": 50,
    "in_unit_laundry": 75,
    "updated_kitchen": 100,
    "updated_bathrooms": 75,
    "pet_friendly": 50,
    "mountain_views": 100,
    "pool_hot_tub": 75,
    "new_flooring": 50,
}


@dataclass
class RentEstimate:
    county: str
    base_rent: int
    sqft_adjusted: int
    grade_adjusted: int
    type_adjusted: int
    features_added: int
    final_estimate: int
    low_range: int
    high_range: int
    rent_per_sqft: float
    annual_gross: int
    grade: str
    grade_label: str


def estimate_rent(county_key: str, beds: int, baths: float, sqft: int,
                  grade: str = "C", property_type: str = "sfh",
                  features: list[str] | None = None,
                  year_built: int | None = None) -> RentEstimate:
    """Estimate monthly rent for a property."""
    profile = COUNTY_RENTS[county_key]

    # 1. Base rent from bedroom count
    bed_map = {
        0: profile.median_studio, 1: profile.median_1br,
        2: profile.median_2br, 3: profile.median_3br,
        4: profile.median_4br,
    }
    base = bed_map.get(beds, profile.median_5br_plus)

    # 2. Square footage adjustment
    # Compare to expected sqft for bedroom count and adjust
    expected_sqft = {0: 500, 1: 700, 2: 1000, 3: 1400, 4: 2000, 5: 2500}
    expected = expected_sqft.get(beds, 2500)
    sqft_diff = sqft - expected
    # Adjust at mid-range $/sqft for the overage/underage
    sqft_adj = int(sqft_diff * profile.rent_per_sqft_mid * 0.4)
    sqft_adjusted = base + sqft_adj

    # 3. Finish grade
    grade_info = GRADE_ADJUSTMENTS.get(grade.upper(), GRADE_ADJUSTMENTS["C"])
    grade_adjusted = int(sqft_adjusted * grade_info["multiplier"])

    # 4. Property type
    type_info = PROPERTY_TYPE_ADJ.get(property_type, PROPERTY_TYPE_ADJ["sfh"])
    type_adjusted = int(grade_adjusted * type_info["multiplier"])

    # 5. Feature add-ons
    feat_total = 0
    for f in (features or []):
        feat_total += FEATURE_ADJUSTMENTS.get(f, 0)
    final = type_adjusted + feat_total

    # 6. Year built penalty (pre-1970 gets a small haircut)
    if year_built and year_built < 1970:
        final = int(final * 0.95)
    elif year_built and year_built > 2015:
        final = int(final * 1.03)

    # Range: +/- 12%
    low = int(final * 0.88)
    high = int(final * 1.12)

    return RentEstimate(
        county=profile.name,
        base_rent=base,
        sqft_adjusted=sqft_adjusted,
        grade_adjusted=grade_adjusted,
        type_adjusted=type_adjusted,
        features_added=feat_total,
        final_estimate=final,
        low_range=low,
        high_range=high,
        rent_per_sqft=round(final / sqft, 2) if sqft else 0,
        annual_gross=final * 12,
        grade=grade.upper(),
        grade_label=grade_info["label"],
    )


def fmt(val) -> str:
    return f"${val:,}"


def print_estimate(est: RentEstimate, beds: int, baths: float, sqft: int,
                   property_type: str, features: list[str] | None,
                   year_built: int | None):
    """Print formatted rent estimate."""
    w = 38
    print(f"\n{'=' * 66}")
    print(f"  RENT ESTIMATE — {est.county}")
    print(f"{'=' * 66}\n")

    print(f"  --- Property ---")
    ptype = PROPERTY_TYPE_ADJ.get(property_type, {}).get("label", property_type)
    print(f"  {'Type':{w}s} {ptype}")
    print(f"  {'Bedrooms':{w}s} {beds}")
    print(f"  {'Bathrooms':{w}s} {baths}")
    print(f"  {'Square feet':{w}s} {sqft:,}")
    if year_built:
        print(f"  {'Year built':{w}s} {year_built}")
    print(f"  {'Finish grade':{w}s} {est.grade} — {est.grade_label}")
    if features:
        print(f"  {'Features':{w}s} {', '.join(features)}")
    print()

    print(f"  --- Estimate Breakdown ---")
    print(f"  {'Base (median for {0}BR)'.format(beds):{w}s} {fmt(est.base_rent)}/mo")
    print(f"  {'After sq ft adjustment':{w}s} {fmt(est.sqft_adjusted)}/mo")
    print(f"  {'After grade adjustment ({0})'.format(est.grade):{w}s} {fmt(est.grade_adjusted)}/mo")
    print(f"  {'After property type':{w}s} {fmt(est.type_adjusted)}/mo")
    if est.features_added:
        print(f"  {'Feature add-ons':{w}s} +{fmt(est.features_added)}/mo")
    print()

    print(f"  --- Final Estimate ---")
    print(f"  {'ESTIMATED RENT':{w}s} {fmt(est.final_estimate)}/mo")
    print(f"  {'Range (±12%)':{w}s} {fmt(est.low_range)} — {fmt(est.high_range)}/mo")
    print(f"  {'Rent per sq ft':{w}s} ${est.rent_per_sqft:.2f}/sqft")
    print(f"  {'Annual gross rent':{w}s} {fmt(est.annual_gross)}/yr")
    print(f"{'=' * 66}")


# ---------------------------------------------------------------------------
# Scraping URLs for live rental comps
# ---------------------------------------------------------------------------

RENTAL_SITES = {
    "zillow": {
        "name": "Zillow Rentals",
        "search_pattern": "https://www.zillow.com/{slug}/rentals/?searchQueryState=%7B%22pagination%22%3A%7B%7D%2C%22mapBounds%22%3A%7B%7D%2C%22filterState%22%3A%7B%22beds%22%3A%7B%22min%22%3A{beds}%2C%22max%22%3A{beds}%7D%2C%22fr%22%3A%7B%22value%22%3Atrue%7D%2C%22fsba%22%3A%7B%22value%22%3Afalse%7D%2C%22fsbo%22%3A%7B%22value%22%3Afalse%7D%2C%22nc%22%3A%7B%22value%22%3Afalse%7D%2C%22cmsn%22%3A%7B%22value%22%3Afalse%7D%2C%22auc%22%3A%7B%22value%22%3Afalse%7D%2C%22fore%22%3A%7B%22value%22%3Afalse%7D%7D%7D",
        "notes": "Best for SFH rentals. Filter by beds/price. Photos included.",
    },
    "redfin": {
        "name": "Redfin Rentals",
        "search_pattern": "https://www.redfin.com/county/{county_id}/filter/min-beds={beds},max-beds={beds},property-type=house+townhouse,include=forsale+mlsfsbo+construction+foreclosed+sold-all",
        "notes": "Detailed listing data. Good photo galleries.",
    },
    "trulia": {
        "name": "Trulia Rentals",
        "search_pattern": "https://www.trulia.com/for_rent/{slug}/",
        "notes": "Owned by Zillow. Neighborhood-level insights.",
    },
    "apartments_com": {
        "name": "Apartments.com",
        "search_pattern": "https://www.apartments.com/houses/{slug}/",
        "notes": "Strong for multifamily. Also lists SFH. Includes rent history.",
    },
    "rentometer": {
        "name": "Rentometer (free lookup)",
        "search_pattern": "https://www.rentometer.com/",
        "notes": "Enter address for free quick estimate. 1 free lookup/day.",
    },
    "craigslist": {
        "name": "Craigslist Denver",
        "search_pattern": "https://denver.craigslist.org/search/apa?min_bedrooms={beds}&max_bedrooms={beds}&availabilityMode=0",
        "notes": "FSBO/private landlord comps. Useful for market floor pricing.",
    },
}

COUNTY_SLUGS = {
    "denver": {"zillow": "denver-co", "trulia": "Denver,CO",
               "apartments": "denver-co", "redfin_id": "570"},
    "douglas": {"zillow": "douglas-county-co", "trulia": "Douglas_County,CO",
                "apartments": "castle-rock-co", "redfin_id": "571"},
    "adams": {"zillow": "adams-county-co", "trulia": "Adams_County,CO",
              "apartments": "thornton-co", "redfin_id": "567"},
    "arapahoe": {"zillow": "arapahoe-county-co", "trulia": "Arapahoe_County,CO",
                 "apartments": "centennial-co", "redfin_id": "568"},
    "jefferson": {"zillow": "jefferson-county-co", "trulia": "Jefferson_County,CO",
                  "apartments": "lakewood-co", "redfin_id": "582"},
}


def generate_rental_urls(county_key: str, beds: int) -> list[dict]:
    """Generate scraping URLs for rental comps."""
    slugs = COUNTY_SLUGS.get(county_key, COUNTY_SLUGS["denver"])
    urls = []

    urls.append({
        "site": "Zillow Rentals",
        "url": f"https://www.zillow.com/{slugs['zillow']}/rentals/{beds}-_beds/",
        "notes": "Filter by price, sqft, type. Click listings for photos.",
    })
    urls.append({
        "site": "Trulia Rentals",
        "url": f"https://www.trulia.com/for_rent/{slugs['trulia']}/{beds}p_beds/",
        "notes": "Neighborhood insights. Photo galleries on each listing.",
    })
    urls.append({
        "site": "Apartments.com",
        "url": f"https://www.apartments.com/houses/{slugs['apartments']}/{beds}-bedrooms/",
        "notes": "Houses for rent. Includes rent trends and nearby comps.",
    })
    urls.append({
        "site": "Craigslist Denver",
        "url": f"https://denver.craigslist.org/search/apa?min_bedrooms={beds}&max_bedrooms={beds}",
        "notes": "Private landlord pricing. Good for market floor.",
    })
    urls.append({
        "site": "Rentometer",
        "url": "https://www.rentometer.com/",
        "notes": "Enter address for free quick rent estimate.",
    })

    return urls


def print_rental_urls(county_key: str, beds: int):
    """Print rental comp scraping URLs."""
    profile = COUNTY_RENTS[county_key]
    urls = generate_rental_urls(county_key, beds)

    print(f"\n{'=' * 72}")
    print(f"  RENTAL COMP URLS — {profile.name} — {beds}BR")
    print(f"{'=' * 72}\n")

    for u in urls:
        print(f"  {u['site']}")
        print(f"    {u['url']}")
        print(f"    {u['notes']}")
        print()

    print(f"  TIP: Use Bright Data MCP or WebFetch to scrape these pages.")
    print(f"  For each listing, extract: address, rent, beds, baths, sqft, photos.")
    print(f"{'=' * 72}")


def print_all_grades():
    """Print the finish quality grading rubric."""
    print(f"\n{'=' * 60}")
    print(f"  FINISH QUALITY GRADING RUBRIC")
    print(f"{'=' * 60}\n")
    for grade, info in GRADE_ADJUSTMENTS.items():
        mult = info["multiplier"]
        sign = "+" if mult >= 1 else ""
        pct = (mult - 1) * 100
        print(f"  {grade}  {info['label']:25s}  {sign}{pct:.0f}% rent adj")
        print(f"     {info['desc']}")
        print()
    print(f"{'=' * 60}")


def query_rental_comps(county_key: str, beds: int | None = None,
                       min_rent: int | None = None, max_rent: int | None = None,
                       limit: int = 20):
    """Query rental comps from the SQLite database."""
    from comps_db import CompsDB, print_query_results
    with CompsDB() as db:
        comps = db.query(
            comp_type="rental", county=county_key,
            beds=beds, min_price=min_rent, max_price=max_rent,
            limit=limit,
        )
        print_query_results(comps, "rental")
        return comps


def main():
    county_choices = list(COUNTY_RENTS.keys())
    parser = argparse.ArgumentParser(
        description="Estimate rent for Denver metro area rental properties"
    )
    parser.add_argument("--county", "-c", choices=county_choices, default="denver",
                        help="County (default: denver)")
    parser.add_argument("--beds", "-b", type=int, default=3,
                        help="Number of bedrooms (default: 3)")
    parser.add_argument("--baths", type=float, default=2.0,
                        help="Number of bathrooms (default: 2)")
    parser.add_argument("--sqft", "-s", type=int, default=1600,
                        help="Square footage (default: 1600)")
    parser.add_argument("--grade", "-g", choices=["A", "B", "C", "D", "F"], default="C",
                        help="Finish quality grade A/B/C/D/F (default: C)")
    parser.add_argument("--type", "-t", choices=list(PROPERTY_TYPE_ADJ.keys()), default="sfh",
                        help="Property type (default: sfh)")
    parser.add_argument("--year-built", type=int, default=None,
                        help="Year built (affects adjustment)")
    parser.add_argument("--features", nargs="*", default=None,
                        choices=list(FEATURE_ADJUSTMENTS.keys()),
                        help="Extra features (space-separated)")
    parser.add_argument("--urls", action="store_true",
                        help="Show rental comp scraping URLs")
    parser.add_argument("--grades", action="store_true",
                        help="Show the finish grading rubric")
    parser.add_argument("--db-comps", action="store_true",
                        help="Query rental comps from the database")

    args = parser.parse_args()

    if args.grades:
        print_all_grades()
        return

    if args.db_comps:
        query_rental_comps(args.county, args.beds)
        return

    est = estimate_rent(
        county_key=args.county, beds=args.beds, baths=args.baths,
        sqft=args.sqft, grade=args.grade, property_type=args.type,
        features=args.features, year_built=args.year_built,
    )
    print_estimate(est, args.beds, args.baths, args.sqft,
                   args.type, args.features, args.year_built)

    if args.urls:
        print_rental_urls(args.county, args.beds)


if __name__ == "__main__":
    main()
