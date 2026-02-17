---
name: refinance-analyzer
description: Analyze mortgage refinancing tradeoffs for rental properties. Use when the user asks about refinancing, comparing mortgage rates, break-even analysis, or whether to refinance an investment property.
---

# Refinance Analyzer — Mortgage Refinancing Tradeoff Analysis

Evaluates whether refinancing a rental property mortgage makes financial sense by comparing current vs proposed loan terms across monthly cash flow, total interest, break-even timeline, NPV, and tax-adjusted returns.

## Gather from user

Before running, collect these parameters (defaults shown):

| Parameter | Flag | Default | Description |
|---|---|---|---|
| Loan balance | `--balance` | 620000 | Current remaining mortgage balance |
| Current rate | `--current-rate` | 6.49 | Current annual interest rate (%) |
| New rate | `--new-rate` | 5.90 | Proposed new interest rate (%) |
| Term | `--term` | 30 | Loan term in years |
| Closing costs | `--closing-costs` | 8500 | Estimated refinance closing costs |
| Tax rate | `--tax-rate` | 0.24 | Marginal income tax rate (for deduction calc) |
| Discount rate | `--discount-rate` | 5.0 | Discount rate for NPV calculation (%) |

## Run the analysis

```bash
uv run refinance-analyzer --balance <BALANCE> --current-rate <RATE> --new-rate <RATE> --closing-costs <COSTS>
```

Example:
```bash
uv run refinance-analyzer --balance 620000 --current-rate 6.49 --new-rate 5.9 --closing-costs 8500
```

## What it reports

The analyzer outputs:
1. **Loan comparison** — side-by-side monthly payment, total interest, closing costs
2. **Monthly cash flow impact** — payment reduction per month and per year
3. **Break-even analysis** — months until cumulative savings exceed closing costs
4. **Lifetime interest comparison** — gross and net interest saved over the full term
5. **Tax-adjusted analysis** — after-tax cost comparison (rental mortgage interest is deductible)
6. **NPV analysis** — net present value of the refinancing decision at the discount rate
7. **Holding period sensitivity** — how the deal looks at 2, 3, 5, 7, 10, 15, 20, 30 year horizons
8. **Rate sensitivity** — results at different proposed rates (5.50% to 6.25%)

## Key rental property considerations

- Mortgage interest is deductible against rental income, which reduces the effective benefit of a lower rate compared to owner-occupied
- Closing costs may be amortized over the loan life for tax purposes
- If selling or doing a 1031 exchange within the break-even window, refinancing may not pay off
- Rental lenders typically charge 0.25-0.75% higher rates than owner-occupied
- Verify the proposed rate accounts for the investment property premium

## Programmatic use

```python
from refinance_analyzer import LoanParams, run_analysis, break_even_month, npv_of_refinancing

result = run_analysis(balance=620000, current_rate=6.49, new_rate=5.9, closing_costs=8500)
print(f"Monthly savings: ${result['monthly_savings']:,.2f}")
print(f"Break-even: {result['break_even_months']} months")
print(f"NPV: ${result['npv']:,.2f}")
```
