"""Kenya statutory payroll helpers for salary registration estimates.

Rates follow common 2025/2026 employer practice:
- NSSF Year 4 graduated contributions (LEL 9,000 / UEL 108,000 at 6% each side)
- SHIF 2.75% of gross (minimum KES 300)
- Affordable Housing Levy 1.5% employee / 1.5% employer of gross
- PAYE monthly bands with KES 2,400 personal relief
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

NSSF_LEL = Decimal("9000")
NSSF_UEL = Decimal("108000")
NSSF_RATE = Decimal("0.06")

SHIF_RATE = Decimal("0.0275")
SHIF_MINIMUM = Decimal("300")

AHL_RATE = Decimal("0.015")

PERSONAL_RELIEF = Decimal("2400")

# Monthly PAYE bands: (upper bound inclusive, rate). Last upper bound is None.
PAYE_BANDS: tuple[tuple[Decimal | None, Decimal], ...] = (
    (Decimal("24000"), Decimal("0.10")),
    (Decimal("32333"), Decimal("0.25")),
    (Decimal("500000"), Decimal("0.30")),
    (Decimal("800000"), Decimal("0.325")),
    (None, Decimal("0.35")),
)


def money(value: Decimal | int | float | str | None) -> Decimal:
    if value is None or value == "":
        return ZERO
    amount = Decimal(str(value))
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def gross_pay(
    basic_salary: Decimal | int | float | str | None,
    house_allowance: Decimal | int | float | str | None = ZERO,
    transport_allowance: Decimal | int | float | str | None = ZERO,
    other_allowances: Decimal | int | float | str | None = ZERO,
) -> Decimal:
    return money(
        money(basic_salary)
        + money(house_allowance)
        + money(transport_allowance)
        + money(other_allowances)
    )


def nssf_employee(pensionable_pay: Decimal) -> Decimal:
    """Employee NSSF on pensionable earnings (basic + cash allowances)."""
    pay = min(max(money(pensionable_pay), ZERO), NSSF_UEL)
    tier_i = money(min(pay, NSSF_LEL) * NSSF_RATE)
    tier_ii = money(max(pay - NSSF_LEL, ZERO) * NSSF_RATE)
    return money(tier_i + tier_ii)


def shif_employee(gross: Decimal) -> Decimal:
    return money(max(money(gross) * SHIF_RATE, SHIF_MINIMUM if money(gross) > ZERO else ZERO))


def ahl_employee(gross: Decimal) -> Decimal:
    return money(money(gross) * AHL_RATE)


def paye_before_relief(taxable_pay: Decimal) -> Decimal:
    remaining = max(money(taxable_pay), ZERO)
    tax = ZERO
    lower = ZERO
    for upper, rate in PAYE_BANDS:
        if remaining <= ZERO:
            break
        if upper is None:
            band_width = remaining
        else:
            band_width = max(min(remaining, upper - lower), ZERO)
        tax += band_width * rate
        remaining -= band_width
        if upper is not None:
            lower = upper
    return money(tax)


def estimate_statutory(
    *,
    basic_salary: Decimal | int | float | str | None,
    house_allowance: Decimal | int | float | str | None = ZERO,
    transport_allowance: Decimal | int | float | str | None = ZERO,
    other_allowances: Decimal | int | float | str | None = ZERO,
    is_resident: bool = True,
    is_person_with_disability: bool = False,
) -> dict[str, Any]:
    gross = gross_pay(basic_salary, house_allowance, transport_allowance, other_allowances)
    nssf = nssf_employee(gross)
    shif = shif_employee(gross)
    ahl = ahl_employee(gross)
    employer_nssf = nssf
    employer_ahl = ahl

    if is_person_with_disability:
        paye = ZERO
        taxable = ZERO
    else:
        taxable = money(max(gross - nssf - shif - ahl, ZERO))
        paye = paye_before_relief(taxable)
        if is_resident:
            paye = money(max(paye - PERSONAL_RELIEF, ZERO))

    employee_deductions = money(nssf + shif + ahl + paye)
    net = money(gross - employee_deductions)

    return {
        "gross": gross,
        "nssf_employee": nssf,
        "nssf_employer": employer_nssf,
        "shif": shif,
        "ahl_employee": ahl,
        "ahl_employer": employer_ahl,
        "taxable_pay": taxable,
        "paye": paye,
        "employee_deductions": employee_deductions,
        "net_pay": net,
        "employer_cost": money(gross + employer_nssf + employer_ahl),
    }
