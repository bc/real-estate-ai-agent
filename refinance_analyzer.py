"""
Mortgage refinancing tradeoff analyzer for rental properties.

Evaluates whether refinancing makes financial sense by comparing
current vs proposed loan across multiple dimensions: monthly cash flow,
total interest, break-even timeline, NPV, and tax-adjusted returns.

Usage:
    python refinance_analyzer.py
    python refinance_analyzer.py --balance 620000 --current-rate 6.49 --new-rate 5.9
    python refinance_analyzer.py --help
"""

import argparse
from dataclasses import dataclass


@dataclass
class LoanParams:
    balance: float
    annual_rate: float  # percent, e.g. 6.49
    term_years: int
    closing_costs: float = 0.0

    @property
    def monthly_rate(self):
        return self.annual_rate / 100 / 12

    @property
    def num_payments(self):
        return self.term_years * 12

    @property
    def monthly_payment(self):
        r = self.monthly_rate
        n = self.num_payments
        if r == 0:
            return self.balance / n
        return self.balance * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def amortization_schedule(loan: LoanParams) -> list[dict]:
    """Generate month-by-month amortization schedule."""
    schedule = []
    remaining = loan.balance
    r = loan.monthly_rate
    payment = loan.monthly_payment

    for month in range(1, loan.num_payments + 1):
        interest = remaining * r
        principal = payment - interest
        remaining -= principal
        schedule.append({
            "month": month,
            "payment": payment,
            "principal": principal,
            "interest": interest,
            "remaining_balance": max(remaining, 0),
        })
    return schedule


def total_interest(loan: LoanParams) -> float:
    return sum(row["interest"] for row in amortization_schedule(loan))


def cumulative_interest_at(schedule: list[dict], month: int) -> float:
    return sum(row["interest"] for row in schedule[:month])


def break_even_month(current: LoanParams, proposed: LoanParams) -> int | None:
    """Month at which cumulative savings exceed closing costs.

    Compares raw monthly payment difference against closing costs.
    Returns None if refinancing never breaks even within the proposed term.
    """
    monthly_savings = current.monthly_payment - proposed.monthly_payment
    if monthly_savings <= 0:
        return None

    cumulative = 0.0
    for month in range(1, proposed.num_payments + 1):
        cumulative += monthly_savings
        if cumulative >= proposed.closing_costs:
            return month
    return None


def npv_of_refinancing(current: LoanParams, proposed: LoanParams,
                       discount_rate_annual: float = 5.0,
                       horizon_months: int | None = None) -> float:
    """Net present value of the refinancing decision.

    Discounts the monthly payment difference stream and subtracts
    upfront closing costs. Positive NPV means refinancing is favorable.
    """
    if horizon_months is None:
        horizon_months = proposed.num_payments
    monthly_savings = current.monthly_payment - proposed.monthly_payment
    r = discount_rate_annual / 100 / 12

    pv_savings = 0.0
    for m in range(1, horizon_months + 1):
        pv_savings += monthly_savings / (1 + r) ** m

    return pv_savings - proposed.closing_costs


def tax_adjusted_analysis(current: LoanParams, proposed: LoanParams,
                          marginal_tax_rate: float = 0.24,
                          horizon_years: int | None = None):
    """Compare after-tax cost of interest for a rental property.

    Rental property mortgage interest is deductible against rental income,
    so the effective interest cost is reduced by the marginal tax rate.
    """
    if horizon_years is None:
        horizon_years = proposed.term_years

    horizon_months = horizon_years * 12
    cur_sched = amortization_schedule(current)
    new_sched = amortization_schedule(proposed)

    cur_interest = cumulative_interest_at(cur_sched, horizon_months)
    new_interest = cumulative_interest_at(new_sched, horizon_months)

    cur_after_tax = cur_interest * (1 - marginal_tax_rate)
    new_after_tax = new_interest * (1 - marginal_tax_rate) + proposed.closing_costs

    return {
        "current_gross_interest": cur_interest,
        "proposed_gross_interest": new_interest,
        "current_after_tax_cost": cur_after_tax,
        "proposed_after_tax_cost": new_after_tax,
        "after_tax_savings": cur_after_tax - new_after_tax,
        "horizon_years": horizon_years,
        "marginal_tax_rate": marginal_tax_rate,
    }


def sensitivity_table(balance: float, current_rate: float,
                      new_rates: list[float], term_years: int,
                      closing_costs: float) -> list[dict]:
    """Show how key metrics change across a range of proposed rates."""
    current = LoanParams(balance, current_rate, term_years)
    rows = []
    for rate in new_rates:
        proposed = LoanParams(balance, rate, term_years, closing_costs)
        savings_mo = current.monthly_payment - proposed.monthly_payment
        be = break_even_month(current, proposed)
        npv = npv_of_refinancing(current, proposed)
        interest_saved = total_interest(current) - total_interest(proposed)
        rows.append({
            "new_rate": rate,
            "monthly_savings": savings_mo,
            "break_even_months": be,
            "lifetime_interest_saved": interest_saved,
            "net_interest_saved": interest_saved - closing_costs,
            "npv": npv,
        })
    return rows


def holding_period_table(current: LoanParams, proposed: LoanParams,
                         periods_years: list[int]) -> list[dict]:
    """Show how the deal looks if you sell/refi again at various horizons."""
    rows = []
    for yrs in periods_years:
        months = yrs * 12
        cur_sched = amortization_schedule(current)
        new_sched = amortization_schedule(proposed)

        cur_interest = cumulative_interest_at(cur_sched, months)
        new_interest = cumulative_interest_at(new_sched, months)
        gross_interest_saved = cur_interest - new_interest
        net_saved = gross_interest_saved - proposed.closing_costs
        npv = npv_of_refinancing(current, proposed, horizon_months=months)

        rows.append({
            "hold_years": yrs,
            "gross_interest_saved": gross_interest_saved,
            "net_savings_after_costs": net_saved,
            "npv": npv,
        })
    return rows


def format_currency(val: float) -> str:
    return f"${val:,.2f}"


def format_table(headers: list[str], rows: list[list[str]], col_widths: list[int]) -> str:
    lines = []
    header_line = "  ".join(h.rjust(w) for h, w in zip(headers, col_widths))
    lines.append(header_line)
    lines.append("  ".join("-" * w for w in col_widths))
    for row in rows:
        lines.append("  ".join(str(c).rjust(w) for c, w in zip(row, col_widths)))
    return "\n".join(lines)


def run_analysis(balance: float = 620_000,
                 current_rate: float = 6.49,
                 new_rate: float = 5.90,
                 term_years: int = 30,
                 closing_costs: float = 8_500,
                 marginal_tax_rate: float = 0.24,
                 discount_rate: float = 5.0):
    """Run the full refinancing analysis and print results."""

    current = LoanParams(balance, current_rate, term_years)
    proposed = LoanParams(balance, new_rate, term_years, closing_costs)

    print("=" * 68)
    print("  RENTAL PROPERTY MORTGAGE REFINANCE ANALYSIS")
    print("=" * 68)

    # --- Loan comparison ---
    print("\n--- Loan Comparison ---\n")
    print(f"  {'':30s} {'Current':>16s}  {'Proposed':>16s}")
    print(f"  {'':30s} {'--------':>16s}  {'--------':>16s}")
    print(f"  {'Balance':30s} {format_currency(balance):>16s}  {format_currency(balance):>16s}")
    print(f"  {'Interest Rate':30s} {current_rate:>15.2f}%  {new_rate:>15.2f}%")
    print(f"  {'Term':30s} {term_years:>14d} yr  {term_years:>14d} yr")
    print(f"  {'Monthly Payment':30s} {format_currency(current.monthly_payment):>16s}  {format_currency(proposed.monthly_payment):>16s}")
    print(f"  {'Total Interest (life of loan)':30s} {format_currency(total_interest(current)):>16s}  {format_currency(total_interest(proposed)):>16s}")
    print(f"  {'Closing Costs':30s} {'N/A':>16s}  {format_currency(closing_costs):>16s}")

    # --- Monthly savings ---
    monthly_savings = current.monthly_payment - proposed.monthly_payment
    annual_savings = monthly_savings * 12
    print("\n--- Monthly Cash Flow Impact ---\n")
    print(f"  Monthly payment reduction:     {format_currency(monthly_savings)}")
    print(f"  Annual cash flow improvement:  {format_currency(annual_savings)}")

    # --- Break-even ---
    be = break_even_month(current, proposed)
    print("\n--- Break-Even Analysis ---\n")
    print(f"  Closing costs:                 {format_currency(closing_costs)}")
    if be is not None:
        be_years = be / 12
        print(f"  Break-even point:              {be} months ({be_years:.1f} years)")
    else:
        print(f"  Break-even point:              Never (savings don't cover costs)")

    # --- Lifetime interest ---
    cur_total = total_interest(current)
    new_total = total_interest(proposed)
    gross_saved = cur_total - new_total
    net_saved = gross_saved - closing_costs
    print("\n--- Lifetime Interest Comparison ---\n")
    print(f"  Current loan total interest:   {format_currency(cur_total)}")
    print(f"  New loan total interest:       {format_currency(new_total)}")
    print(f"  Gross interest saved:          {format_currency(gross_saved)}")
    print(f"  Net savings (after costs):     {format_currency(net_saved)}")

    # --- Tax-adjusted (rental property) ---
    tax = tax_adjusted_analysis(current, proposed, marginal_tax_rate)
    print(f"\n--- Tax-Adjusted Analysis (Rental Property) ---")
    print(f"   Marginal tax rate: {marginal_tax_rate:.0%} | Horizon: {tax['horizon_years']} years\n")
    print(f"  Current after-tax interest:    {format_currency(tax['current_after_tax_cost'])}")
    print(f"  Proposed after-tax cost:       {format_currency(tax['proposed_after_tax_cost'])}")
    print(f"  After-tax savings:             {format_currency(tax['after_tax_savings'])}")
    if tax["after_tax_savings"] < 0:
        print(f"  ** Refinancing costs MORE on an after-tax basis **")

    # --- NPV ---
    npv = npv_of_refinancing(current, proposed, discount_rate)
    print(f"\n--- Net Present Value (discount rate {discount_rate:.1f}%) ---\n")
    print(f"  NPV of refinancing:            {format_currency(npv)}")
    verdict = "FAVORABLE" if npv > 0 else "UNFAVORABLE"
    print(f"  Verdict:                       {verdict}")

    # --- Holding period sensitivity ---
    print("\n--- Holding Period Sensitivity ---\n")
    hold_rows = holding_period_table(current, proposed, [2, 3, 5, 7, 10, 15, 20, 30])
    headers = ["Hold (yr)", "Interest Saved", "Net Savings", "NPV"]
    widths = [10, 16, 16, 16]
    table_rows = []
    for r in hold_rows:
        table_rows.append([
            str(r["hold_years"]),
            format_currency(r["gross_interest_saved"]),
            format_currency(r["net_savings_after_costs"]),
            format_currency(r["npv"]),
        ])
    print(format_table(headers, table_rows, widths))

    # --- Rate sensitivity ---
    print("\n--- Rate Sensitivity (what if you got a different rate?) ---\n")
    test_rates = [5.50, 5.75, 5.90, 6.00, 6.10, 6.25]
    sens = sensitivity_table(balance, current_rate, test_rates, term_years, closing_costs)
    headers = ["New Rate", "Mo. Savings", "Break-Even", "Net Interest Saved", "NPV"]
    widths = [10, 14, 12, 18, 14]
    table_rows = []
    for r in sens:
        be_str = f"{r['break_even_months']} mo" if r["break_even_months"] else "Never"
        table_rows.append([
            f"{r['new_rate']:.2f}%",
            format_currency(r["monthly_savings"]),
            be_str,
            format_currency(r["net_interest_saved"]),
            format_currency(r["npv"]),
        ])
    print(format_table(headers, table_rows, widths))

    # --- Summary ---
    print("\n" + "=" * 68)
    print("  SUMMARY")
    print("=" * 68)
    print(f"""
  Refinancing from {current_rate:.2f}% to {new_rate:.2f}% on a {format_currency(balance)} balance:

  - Saves {format_currency(monthly_savings)}/mo ({format_currency(annual_savings)}/yr) in payments
  - Breaks even in {be} months ({be/12:.1f} years) after {format_currency(closing_costs)} closing costs
  - Saves {format_currency(net_saved)} in net interest over the life of the loan
  - After-tax savings (at {marginal_tax_rate:.0%} rate): {format_currency(tax['after_tax_savings'])}
  - NPV at {discount_rate:.0f}% discount rate: {format_currency(npv)} ({verdict})
""")

    # Key considerations for rental properties
    print("  KEY RENTAL PROPERTY CONSIDERATIONS:")
    print("  - Mortgage interest is deductible against rental income, reducing")
    print("    the effective benefit of a lower rate vs. an owner-occupied home")
    print("  - Closing costs may be amortized over the loan life for tax purposes")
    print("  - If you plan to sell or 1031-exchange within the break-even window,")
    print("    refinancing may not pay off")
    print("  - Rental lenders may charge 0.25-0.75% higher rates than shown here")
    print("  - Verify the new rate accounts for the investment property premium")
    print("=" * 68)

    return {
        "monthly_savings": monthly_savings,
        "annual_savings": annual_savings,
        "break_even_months": be,
        "net_interest_saved": net_saved,
        "after_tax_savings": tax["after_tax_savings"],
        "npv": npv,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze mortgage refinancing tradeoffs for a rental property"
    )
    parser.add_argument("--balance", type=float, default=620_000,
                        help="Current loan balance (default: 620000)")
    parser.add_argument("--current-rate", type=float, default=6.49,
                        help="Current interest rate in %% (default: 6.49)")
    parser.add_argument("--new-rate", type=float, default=5.90,
                        help="Proposed new interest rate in %% (default: 5.90)")
    parser.add_argument("--term", type=int, default=30,
                        help="Loan term in years (default: 30)")
    parser.add_argument("--closing-costs", type=float, default=8_500,
                        help="Estimated closing costs (default: 8500)")
    parser.add_argument("--tax-rate", type=float, default=0.24,
                        help="Marginal income tax rate for deduction calc (default: 0.24)")
    parser.add_argument("--discount-rate", type=float, default=5.0,
                        help="Discount rate for NPV in %% (default: 5.0)")

    args = parser.parse_args()
    run_analysis(
        balance=args.balance,
        current_rate=args.current_rate,
        new_rate=args.new_rate,
        term_years=args.term,
        closing_costs=args.closing_costs,
        marginal_tax_rate=args.tax_rate,
        discount_rate=args.discount_rate,
    )


if __name__ == "__main__":
    main()
