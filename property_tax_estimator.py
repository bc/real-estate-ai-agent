"""
Colorado property tax estimator for Denver metro area counties.

Covers Denver, Douglas, Adams, Arapahoe, and Jefferson counties.
Uses Colorado's split assessment rate system (2025+):
  - 6.25% for local government mill levies
  - 7.05% for school district mill levies

Each county has representative default mill levies that can be overridden.
For exact figures, look up your parcel on the county assessor site.

Usage:
    python property_tax_estimator.py --county denver --value 625000
    python property_tax_estimator.py --county douglas --value 750000 --school-mills 52.1
    python property_tax_estimator.py --all --value 625000
    python property_tax_estimator.py --vendors
    python property_tax_estimator.py --reports
    python property_tax_estimator.py --help
"""

import argparse
from dataclasses import dataclass, field


# Colorado statewide assessment rates (2025 tax year)
RESIDENTIAL_LOCAL_RATE = 0.0625   # 6.25% for local government
RESIDENTIAL_SCHOOL_RATE = 0.0705  # 7.05% for school districts
COMMERCIAL_RATE = 0.27            # 27% for commercial/vacant/industrial


@dataclass
class CountyTaxProfile:
    name: str
    # Mill levy components (representative defaults — actual varies by parcel)
    county_mills: float
    school_mills: float
    city_mills: float           # 0 if unincorporated
    fire_mills: float
    water_sewer_mills: float
    other_mills: float          # metro districts, library, parks, drainage, etc.
    # Lookup URLs
    assessor_search_url: str
    treasurer_search_url: str
    assessor_home_url: str
    notes: list[str] = field(default_factory=list)

    @property
    def local_mills(self) -> float:
        """All non-school mills combined."""
        return (self.county_mills + self.city_mills + self.fire_mills +
                self.water_sewer_mills + self.other_mills)

    @property
    def total_mills(self) -> float:
        return self.local_mills + self.school_mills


# ---------------------------------------------------------------------------
# County profiles with representative mill levies
# ---------------------------------------------------------------------------

COUNTIES: dict[str, CountyTaxProfile] = {
    "denver": CountyTaxProfile(
        name="Denver (City & County)",
        county_mills=27.328,
        school_mills=52.274,
        city_mills=0.0,        # Denver is a consolidated city-county
        fire_mills=0.0,        # included in county_mills
        water_sewer_mills=0.0,
        other_mills=0.0,
        assessor_search_url="https://www.denvergov.org/Property",
        treasurer_search_url="https://www.denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Department-of-Finance/Our-Divisions/Treasury/Property-Taxes",
        assessor_home_url="https://denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Department-of-Finance/Our-Divisions/Assessors-Office",
        notes=[
            "Denver is a consolidated city-county; no separate city/fire levies.",
            "2025 combined mill levy: 79.602 mills.",
            "Effective rate ~0.54% of market value.",
        ],
    ),
    "douglas": CountyTaxProfile(
        name="Douglas County",
        county_mills=13.980,
        school_mills=52.116,
        city_mills=8.752,
        fire_mills=0.0,
        water_sewer_mills=0.693,
        other_mills=0.0,
        assessor_search_url="https://apps.douglas.co.us/assessor/web/",
        treasurer_search_url="https://apps.douglas.co.us/treasurer/treasurerweb/search.jsp?guest=true",
        assessor_home_url="https://www.douglas.co.us/assessor/",
        notes=[
            "Sample total mill levy: 75.541 mills. Varies widely by metro district.",
            "Newer developments with metro districts can have significantly higher levies.",
            "Median effective rate ~0.64% of market value.",
        ],
    ),
    "adams": CountyTaxProfile(
        name="Adams County",
        county_mills=22.0,
        school_mills=69.071,
        city_mills=0.0,
        fire_mills=10.0,
        water_sewer_mills=0.0,
        other_mills=23.884,
        assessor_search_url="https://adamscountyco.gov/service/search-real-property/",
        treasurer_search_url="https://adcotax.com/treasurer/web/login.jsp",
        assessor_home_url="https://adamscountyco.gov/property-assessment-process",
        notes=[
            "Example local mills ~55.884, school mills ~69.071.",
            "Mill levies vary significantly between municipalities.",
            "Median effective rate ~0.57-0.60% of market value.",
        ],
    ),
    "arapahoe": CountyTaxProfile(
        name="Arapahoe County",
        county_mills=15.855,
        school_mills=55.0,
        city_mills=0.0,
        fire_mills=12.0,
        water_sewer_mills=0.0,
        other_mills=10.0,
        assessor_search_url="https://www.arapahoeco.gov/your_county/county_departments/assessor/property_search/index.php",
        treasurer_search_url="https://www.arapahoeco.gov/your_county/county_departments/treasurer/tax_search.php",
        assessor_home_url="https://www.arapahoeco.gov/your_county/county_departments/assessor/index.php",
        notes=[
            "County levy: 15.855 mills (2025). Total depends on all overlapping districts.",
            "School district portion is typically 45-50% of total tax bill.",
            "Median effective rate ~0.52% of market value.",
        ],
    ),
    "jefferson": CountyTaxProfile(
        name="Jefferson County",
        county_mills=23.332,
        school_mills=47.075,
        city_mills=4.310,
        fire_mills=14.925,
        water_sewer_mills=0.0,
        other_mills=0.997,      # urban drainage
        assessor_search_url="https://propertysearch.jeffco.us/propertyrecordssearch/address",
        treasurer_search_url="https://treasurerpropertysearch.jeffco.us/",
        assessor_home_url="https://www.jeffco.us/2497/Property-Taxes",
        notes=[
            "Sample total mill levy: 90.639 mills. Varies by area.",
            "Fire district levy is a significant component (~15 mills).",
            "Median effective rate ~0.51% of market value.",
        ],
    ),
}


# ---------------------------------------------------------------------------
# Vendors — real estate service providers across the Denver metro
# ---------------------------------------------------------------------------

VENDORS = {
    "title_companies": {
        "label": "Title Companies",
        "cost_range": "~0.5-1.0% of purchase price for owner's policy",
        "entries": [
            {"name": "Land Title Guarantee Company", "url": "https://www.ltgc.com/",
             "notes": "Colorado's largest locally-owned. 50+ offices, 50k+ closings/yr."},
            {"name": "Chicago Title Colorado", "url": "https://www.chicagotitle.com/",
             "notes": "Part of Fidelity National Financial. Largest national underwriter."},
            {"name": "First American Title", "url": "https://www.firstam.com/",
             "notes": "National 'Big Four' underwriter with strong Denver metro presence."},
            {"name": "Heritage Title Company", "url": "https://www.heritagetitleco.com/",
             "notes": "Serving Colorado since 1977. Local presence across metro."},
            {"name": "First Integrity Title Company", "url": "https://www.firstintegritytitle.com/",
             "notes": "Covers Adams, Arapahoe, Denver, Douglas, Jefferson + more."},
        ],
    },
    "appraisers": {
        "label": "Residential Appraisers",
        "cost_range": "$450-$800 standard; $800-$1,200 complex/luxury",
        "entries": [
            {"name": "Colorado Appraisal Consultants", "url": "https://www.appraisalcolorado.com/",
             "notes": "Residential + commercial. Also handles tax appeal appraisals."},
            {"name": "Premier Appraisal Services", "url": "https://www.premierappraisalsvcs.com/",
             "notes": "20+ years, Denver metro and Front Range."},
            {"name": "Skyline Appraisal", "url": "https://www.skylineappraisalcorp.com/",
             "notes": "Northern CO and entire Denver metro. 5,000+ sq mi coverage."},
            {"name": "Colorado Appraisal Xperts", "url": "https://www.coloradoappraisalxperts.com/",
             "notes": "20+ years. Specializes in trust/estate, divorce, PMI removal."},
        ],
    },
    "inspectors": {
        "label": "Home Inspection Companies",
        "cost_range": "$310-$720 by sq ft; radon add $100-200; sewer scope add $100-250",
        "entries": [
            {"name": "Axium Inspections", "url": "https://axiuminspections.com/",
             "notes": "Colorado's largest. 6,000+ 5-star reviews. Same-day scheduling."},
            {"name": "A-Pro Home Inspection Denver", "url": "https://www.a-prohomeinspection.com/",
             "notes": "Since 1994. 500-point inspections. CHI/PHI/ITI certified."},
            {"name": "HouseMaster Denver North", "url": "https://housemaster.com/denvernorth",
             "notes": "National franchise. Next-day reports with photos."},
            {"name": "Inspections Over Coffee", "url": "https://www.inspectionsovercoffee.com/",
             "notes": "360-degree snapshots. Structural, mechanical, environmental."},
        ],
    },
    "insurance": {
        "label": "Rental / Investment Property Insurance",
        "cost_range": "$900-$2,900/yr; Colorado avg ~$1,600/yr (hail/fire risk)",
        "entries": [
            {"name": "Steadily", "url": "https://www.steadily.com/states/colorado",
             "notes": "Online-first landlord platform. Single/multi/short-term rental."},
            {"name": "NREIG", "url": "https://nreig.com/insurance-by-state/colorado/",
             "notes": "Investment-property specialist. Month-to-month, no lock-in."},
            {"name": "Associated Agents Insurance", "url": "https://www.insurecolo.com/real-estate-investor/",
             "notes": "Lakewood, CO. Shops multiple carriers. Portfolios welcome."},
            {"name": "Wexford Insurance", "url": "https://www.wexfordins.com/investment/colorado",
             "notes": "Investment property specialist. $700-$5,000/yr typical."},
        ],
    },
    "property_management": {
        "label": "Property Management Companies",
        "cost_range": "8-12% of rent/mo; tenant placement 50-100% of 1 month",
        "entries": [
            {"name": "Grace Property Management", "url": "https://www.rentgrace.com/",
             "notes": "Since 1978. Ranked #1 Denver by PropertyManagement.com."},
            {"name": "Laureate LTD", "url": "https://www.laureateltd.com/",
             "notes": "Since 1982. 1,000+ properties. 24-hour emergency service."},
            {"name": "Pioneer Property Management", "url": "https://rentmedenver.com/",
             "notes": "17+ years. Best PM company 8 years running."},
            {"name": "Real Property Mgmt Colorado", "url": "https://realpropertymanagementcolorado.com/",
             "notes": "From $125/mo. 29-day rental promise (avg 25.7 days)."},
        ],
    },
    "tax_appeal": {
        "label": "Property Tax Appeal Consultants",
        "cost_range": "Contingency: 25-50% of first-year tax savings (no upfront fee)",
        "entries": [
            {"name": "Paramount Property Tax Appeal", "url": "https://www.paramountpropertytaxappeal.com/",
             "notes": "Contingency basis. Full-service protest + representation."},
            {"name": "Downey & Associates, PC", "url": "https://coloradopropertytaxattorney.com/",
             "notes": "30+ years CO property tax law. Precedent-setting cases."},
            {"name": "Catalyst Property Tax Consultants", "url": "https://catalystpropertytax.com/",
             "notes": "Colorado-based, local market knowledge."},
            {"name": "Ryan (Denver Office)", "url": "https://ryan.com/practice-areas/property-tax/denver/",
             "notes": "Large national firm. 8-30+ yr experienced Denver consultants."},
        ],
    },
}

# ---------------------------------------------------------------------------
# Reports — public data sources, market reports, assessment documents
# ---------------------------------------------------------------------------

COUNTY_REPORTS = {
    "denver": {
        "abstract_of_assessment": "https://denver.prelive.opencities.com/files/assets/public/v/2/finance/documents/assessor/2025/denver-2024_abstract.pdf",
        "assessor_forms": "https://denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Department-of-Finance/Our-Divisions/Assessors-Office/View-and-Download-Forms",
        "protest_info": "Online protest at denvergov.org/Property; email assmt.protest@denvergov.org; phone 720-913-4164",
    },
    "douglas": {
        "abstract_of_assessment": "https://www.douglas.co.us/assessor/taxing-authorities/",
        "tax_levy_certification": "https://www.douglas.co.us/budget/certification-tax-levy/",
        "tax_calculations": "https://www.douglas.co.us/assessor/residential-property-tax-calculations/",
        "protest_info": "Online, mail, or in person at 100 Third Street, Castle Rock, CO 80104",
    },
    "adams": {
        "abstract_of_assessment": "https://www.adcogov.org/abstract-assessment",
        "mill_levy_certification": "https://adamscountyco.gov/our-county/budget-finance/mill-levy-certification/",
        "protest_info": "Email assessor@adamscountyco.gov; phone 720-523-6038; office 4430 S. Adams County Pkwy, Suite C2100, Brighton",
    },
    "arapahoe": {
        "abstract_of_assessment": "https://www.arapahoeco.gov/your_county/county_departments/assessor/assessment_resources/index.php",
        "mill_levies_and_districts": "https://www.arapahoeco.gov/your_county/county_departments/assessor/mill_levies_and_tax_districts.php",
        "certification_of_levies": "https://files.arapahoeco.gov/Assessor/Certification%20of%20Levies%20and%20Revenues/2024%20Certification%20of%20Levies%20and%20Revenues.pdf",
        "protest_info": "Phone 303-795-4600; online at arapahoeco.gov Assessor portal",
    },
    "jefferson": {
        "abstract_of_assessment": "https://www.jeffco.us/446/Abstract-of-Assessments",
        "tax_authority_reports": "https://www.jeffco.us/3887/Tax-Authority-Information-and-Reports",
        "tax_levy_certification": "https://www.jeffco.us/3804/Certification-of-Tax-Levies",
        "valuation_appeal_info": "https://www.jeffco.us/4593/20232024-Property-Valuation",
        "protest_info": "Phone 303-271-8666; office 100 Jefferson County Parkway, Suite 2500, Golden",
    },
}

STATEWIDE_REPORTS = {
    "DOLA Annual Report": "https://dpt.colorado.gov/annual-reports",
    "Statewide Abstract of Assessment": "https://dpt.colorado.gov/news-article/2024-abstract-of-assessment-report-and-certification-of-values",
    "CO Assessed Values Manuals": "https://dpt.colorado.gov/colorado-assessed-values-manuals",
    "CO Property Tax Map (interactive)": "https://dpt.colorado.gov/property-tax-map",
    "Understanding CO Property Taxes": "https://dpt.colorado.gov/understanding-property-taxes-in-colorado",
    "Protests & Appeals Guide": "https://dpt.colorado.gov/protests-and-appeals",
    "DMAR Market Trends": "https://www.dmarealtors.com/market-trends-reports",
    "CO Assoc of Realtors Stats": "https://coloradorealtors.com/market-trends/regional-and-statewide-statistics/",
    "HB24-1302 Mill Levy Dashboard": "https://dlg.colorado.gov/hb24-1302-mill-levy-public-information",
}

APPEAL_DEADLINES = {
    "notice_of_valuation": "Mailed ~May 1 (reappraisal years: odd years)",
    "protest_deadline": "June 8 (or next business day)",
    "cboe_appeal": "Within 30 days of Notice of Determination",
    "state_board_appeal": "Within 30 days of CBOE decision",
    "arbitration_fee": "$150 (binding)",
}


@dataclass
class TaxEstimate:
    county: str
    market_value: float
    local_assessed: float
    school_assessed: float
    local_mills: float
    school_mills: float
    local_tax: float
    school_tax: float
    total_tax: float
    effective_rate: float       # total_tax / market_value
    monthly_estimate: float


def estimate_tax(market_value: float, profile: CountyTaxProfile,
                 school_mills_override: float | None = None,
                 local_mills_override: float | None = None) -> TaxEstimate:
    """Estimate annual property tax using Colorado's split assessment system."""
    local_mills = local_mills_override if local_mills_override is not None else profile.local_mills
    school_mills = school_mills_override if school_mills_override is not None else profile.school_mills

    local_assessed = market_value * RESIDENTIAL_LOCAL_RATE
    school_assessed = market_value * RESIDENTIAL_SCHOOL_RATE

    local_tax = local_assessed * local_mills / 1000
    school_tax = school_assessed * school_mills / 1000
    total_tax = local_tax + school_tax

    return TaxEstimate(
        county=profile.name,
        market_value=market_value,
        local_assessed=local_assessed,
        school_assessed=school_assessed,
        local_mills=local_mills,
        school_mills=school_mills,
        local_tax=local_tax,
        school_tax=school_tax,
        total_tax=total_tax,
        effective_rate=total_tax / market_value if market_value else 0,
        monthly_estimate=total_tax / 12,
    )


def fmt(val: float) -> str:
    return f"${val:,.2f}"


def print_estimate(est: TaxEstimate, profile: CountyTaxProfile, verbose: bool = True):
    """Print a formatted tax estimate for one county."""
    w = 40
    print(f"\n{'=' * 62}")
    print(f"  {profile.name.upper()} — PROPERTY TAX ESTIMATE")
    print(f"{'=' * 62}\n")

    print(f"  {'Market Value':{w}s} {fmt(est.market_value):>18s}")
    print()

    print(f"  --- Assessment (Colorado split-rate system) ---")
    print(f"  {'Local govt assessed (6.25%)':{w}s} {fmt(est.local_assessed):>18s}")
    print(f"  {'School district assessed (7.05%)':{w}s} {fmt(est.school_assessed):>18s}")
    print()

    print(f"  --- Mill Levies ---")
    print(f"  {'Local government mills':{w}s} {est.local_mills:>17.3f}")
    print(f"  {'School district mills':{w}s} {est.school_mills:>17.3f}")
    print(f"  {'Total mills':{w}s} {est.local_mills + est.school_mills:>17.3f}")
    print()

    if verbose:
        print(f"  --- Mill Levy Breakdown ---")
        print(f"  {'  County':{w}s} {profile.county_mills:>17.3f}")
        if profile.city_mills:
            print(f"  {'  City/Town':{w}s} {profile.city_mills:>17.3f}")
        if profile.fire_mills:
            print(f"  {'  Fire protection':{w}s} {profile.fire_mills:>17.3f}")
        if profile.water_sewer_mills:
            print(f"  {'  Water/sewer':{w}s} {profile.water_sewer_mills:>17.3f}")
        if profile.other_mills:
            print(f"  {'  Other (drainage, library, etc.)':{w}s} {profile.other_mills:>17.3f}")
        print(f"  {'  School district':{w}s} {profile.school_mills:>17.3f}")
        print()

    print(f"  --- Tax Estimate ---")
    print(f"  {'Local government tax':{w}s} {fmt(est.local_tax):>18s}")
    print(f"  {'School district tax':{w}s} {fmt(est.school_tax):>18s}")
    print(f"  {'TOTAL ANNUAL TAX':{w}s} {fmt(est.total_tax):>18s}")
    print(f"  {'Monthly (escrow estimate)':{w}s} {fmt(est.monthly_estimate):>18s}")
    print(f"  {'Effective rate':{w}s} {est.effective_rate:>17.3%}")
    print()

    if verbose and profile.notes:
        print(f"  Notes:")
        for note in profile.notes:
            print(f"    - {note}")

    print(f"\n  Look up your exact tax:")
    print(f"    Assessor:  {profile.assessor_search_url}")
    print(f"    Treasurer: {profile.treasurer_search_url}")
    print(f"{'=' * 62}")


def compare_counties(market_value: float, counties: list[str] | None = None):
    """Print a side-by-side comparison of all requested counties."""
    if counties is None:
        counties = list(COUNTIES.keys())

    estimates = []
    for key in counties:
        profile = COUNTIES[key]
        est = estimate_tax(market_value, profile)
        estimates.append((key, profile, est))

    # Individual detailed estimates
    for key, profile, est in estimates:
        print_estimate(est, profile)

    # Summary comparison table
    print(f"\n{'=' * 78}")
    print(f"  COMPARISON — All Counties at {fmt(market_value)} Market Value")
    print(f"{'=' * 78}\n")

    headers = ["County", "Total Mills", "Annual Tax", "Monthly", "Eff. Rate"]
    widths = [22, 13, 14, 12, 10]
    header_line = "  " + "  ".join(h.rjust(w) for h, w in zip(headers, widths))
    print(header_line)
    print("  " + "  ".join("-" * w for w in widths))

    sorted_estimates = sorted(estimates, key=lambda x: x[2].total_tax)
    for key, profile, est in sorted_estimates:
        row = [
            profile.name[:22],
            f"{est.local_mills + est.school_mills:.3f}",
            fmt(est.total_tax),
            fmt(est.monthly_estimate),
            f"{est.effective_rate:.3%}",
        ]
        print("  " + "  ".join(str(c).rjust(w) for c, w in zip(row, widths)))

    cheapest = sorted_estimates[0]
    most_expensive = sorted_estimates[-1]
    diff = most_expensive[2].total_tax - cheapest[2].total_tax
    print(f"\n  Cheapest:        {cheapest[1].name} ({fmt(cheapest[2].total_tax)}/yr)")
    print(f"  Most expensive:  {most_expensive[1].name} ({fmt(most_expensive[2].total_tax)}/yr)")
    print(f"  Spread:          {fmt(diff)}/yr ({fmt(diff/12)}/mo)")
    print(f"{'=' * 78}")


def run_single(county_key: str, market_value: float,
               school_mills: float | None = None,
               local_mills: float | None = None):
    """Run estimate for a single county."""
    profile = COUNTIES[county_key]
    est = estimate_tax(market_value, profile, school_mills, local_mills)
    print_estimate(est, profile)
    return est


def print_vendors(category: str | None = None):
    """Print vendor directory, optionally filtered to one category."""
    cats = {category: VENDORS[category]} if category else VENDORS
    print(f"\n{'=' * 78}")
    print(f"  DENVER METRO REAL ESTATE VENDOR DIRECTORY")
    print(f"{'=' * 78}")

    for key, cat in cats.items():
        print(f"\n  --- {cat['label']} ---")
        print(f"  Typical cost: {cat['cost_range']}\n")
        for v in cat["entries"]:
            print(f"    {v['name']}")
            print(f"      {v['url']}")
            print(f"      {v['notes']}")
        print()

    print(f"{'=' * 78}")


def print_reports(county_key: str | None = None):
    """Print assessment reports, market data, and appeal info."""
    print(f"\n{'=' * 78}")
    print(f"  PROPERTY TAX REPORTS & PUBLIC DATA")
    print(f"{'=' * 78}")

    # Statewide
    print(f"\n  --- Colorado Statewide Resources ---\n")
    for label, url in STATEWIDE_REPORTS.items():
        print(f"    {label}")
        print(f"      {url}")
    print()

    # Appeal deadlines
    print(f"  --- CO Property Tax Appeal Deadlines ---\n")
    for label, detail in APPEAL_DEADLINES.items():
        print(f"    {label.replace('_', ' ').title():40s} {detail}")
    print()

    # Per-county
    counties = {county_key: COUNTY_REPORTS[county_key]} if county_key else COUNTY_REPORTS
    for key, reports in counties.items():
        profile = COUNTIES[key]
        print(f"  --- {profile.name} ---\n")
        for label, url in reports.items():
            print(f"    {label.replace('_', ' ').title():40s} {url}")
        print()

    print(f"{'=' * 78}")


def main():
    county_choices = list(COUNTIES.keys())
    vendor_choices = list(VENDORS.keys())
    parser = argparse.ArgumentParser(
        description="Estimate property tax for Denver metro area counties (CO)"
    )
    parser.add_argument("--county", "-c", choices=county_choices,
                        help="County to estimate (omit for all)")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Show all counties with comparison")
    parser.add_argument("--value", "-v", type=float, default=None,
                        help="Property market value in dollars")
    parser.add_argument("--school-mills", type=float, default=None,
                        help="Override school district mill levy")
    parser.add_argument("--local-mills", type=float, default=None,
                        help="Override total local government mill levy")
    parser.add_argument("--vendors", nargs="?", const="all", default=None,
                        metavar="CATEGORY",
                        help=f"Show vendor directory. Optional category: {', '.join(vendor_choices)}")
    parser.add_argument("--reports", action="store_true",
                        help="Show assessment reports, market data, and appeal info")

    args = parser.parse_args()

    ran_something = False

    if args.vendors:
        cat = None if args.vendors == "all" else args.vendors
        if cat and cat not in VENDORS:
            parser.error(f"Unknown vendor category '{cat}'. Choose from: {', '.join(vendor_choices)}")
        print_vendors(cat)
        ran_something = True

    if args.reports:
        print_reports(args.county)
        ran_something = True

    if args.value is not None:
        if args.all or args.county is None:
            compare_counties(args.value)
        else:
            run_single(args.county, args.value, args.school_mills, args.local_mills)
        ran_something = True

    if not ran_something:
        parser.print_help()


if __name__ == "__main__":
    main()
