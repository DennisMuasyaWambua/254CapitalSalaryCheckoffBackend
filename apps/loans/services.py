"""
Loan calculation and schedule generation services.

CRITICAL: These calculations must match exactly with the frontend calculations
in frontend/src/lib/utils/calculations.ts
"""

import random
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List
from django.conf import settings
from apps.loans.models import LoanApplication, RepaymentSchedule
import logging

logger = logging.getLogger(__name__)


def calculate_flat_interest(
    principal: Decimal,
    rate: Decimal = Decimal('0.05'),
    months: int = 6
) -> Dict[str, Decimal]:
    """
    Calculate loan repayment using flat interest rate per month.

    The interest is calculated as a fixed percentage of the principal for each month.

    Formula:
        interest_per_month = principal * rate
        total_interest = interest_per_month * months
        total_repayment = principal + total_interest
        monthly_deduction = total_repayment / months

    Examples:
        - 1 month at 5%: total = 100,000 + (5,000 * 1) = 105,000
        - 3 months at 5%: total = 100,000 + (5,000 * 3) = 115,000
        - 6 months at 5%: total = 100,000 + (5,000 * 6) = 130,000
        - 12 months at 5%: total = 100,000 + (5,000 * 12) = 160,000

    Args:
        principal: Loan principal amount
        rate: Monthly interest rate (default: 0.05 = 5% per month)
        months: Repayment period in months

    Returns:
        Dict with:
            - total_repayment: Total amount to be repaid
            - monthly_deduction: Monthly deduction amount
            - interest_amount: Total interest amount
            - interest_rate: Monthly interest rate used

    Example:
        >>> calculate_flat_interest(Decimal('100000'), Decimal('0.05'), 6)
        {
            'total_repayment': Decimal('130000.00'),
            'monthly_deduction': Decimal('21666.67'),
            'interest_amount': Decimal('30000.00'),
            'interest_rate': Decimal('0.05')
        }
    """
    # Ensure Decimal precision
    principal = Decimal(str(principal))
    rate = Decimal(str(rate))

    # Calculate interest per month
    interest_per_month = principal * rate

    # Calculate total interest: interest_per_month * number of months
    total_interest = interest_per_month * Decimal(str(months))
    total_interest = total_interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Calculate total repayment: principal + total_interest
    total_repayment = principal + total_interest
    total_repayment = total_repayment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Calculate monthly deduction: total / months
    monthly_deduction = total_repayment / Decimal(str(months))
    monthly_deduction = monthly_deduction.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Calculate interest amount
    interest_amount = total_repayment - principal

    return {
        'total_repayment': total_repayment,
        'monthly_deduction': monthly_deduction,
        'interest_amount': interest_amount,
        'interest_rate': rate,
    }


def calculate_amortized(
    principal: Decimal,
    annual_rate: Decimal,
    months: int
) -> Dict[str, any]:
    """
    Calculate loan repayment using amortized (reducing balance) method.

    Formula (annuity):
        monthly_rate = annual_rate / 12
        payment = principal * (r * (1 + r)^n) / ((1 + r)^n - 1)
        where r = monthly_rate, n = months

    Args:
        principal: Loan principal amount
        annual_rate: Annual interest rate (e.g., 0.12 for 12% per annum)
        months: Repayment period in months

    Returns:
        Dict with:
            - monthly_payment: Monthly payment amount
            - total_repayment: Total amount to be repaid
            - interest_amount: Total interest amount
            - schedule: List of dicts with installment details
    """
    principal = Decimal(str(principal))
    annual_rate = Decimal(str(annual_rate))

    # Calculate monthly interest rate
    monthly_rate = annual_rate / Decimal('12')

    # Calculate monthly payment using annuity formula
    if monthly_rate > 0:
        numerator = monthly_rate * ((Decimal('1') + monthly_rate) ** months)
        denominator = ((Decimal('1') + monthly_rate) ** months) - Decimal('1')
        monthly_payment = principal * (numerator / denominator)
    else:
        # If rate is 0, simple division
        monthly_payment = principal / Decimal(str(months))

    monthly_payment = monthly_payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Generate amortization schedule
    schedule = []
    balance = principal

    for i in range(1, months + 1):
        # Calculate interest for this period
        interest_payment = balance * monthly_rate
        interest_payment = interest_payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Calculate principal payment
        principal_payment = monthly_payment - interest_payment

        # Update balance
        balance = balance - principal_payment

        # Adjust last payment to account for rounding
        if i == months:
            # Ensure balance is exactly zero
            principal_payment = principal_payment + balance
            balance = Decimal('0.00')

        schedule.append({
            'installment': i,
            'payment': monthly_payment,
            'principal': principal_payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'interest': interest_payment,
            'balance': balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        })

    total_repayment = monthly_payment * Decimal(str(months))
    interest_amount = total_repayment - principal

    return {
        'monthly_payment': monthly_payment,
        'total_repayment': total_repayment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'interest_amount': interest_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'schedule': schedule,
    }


def calculate_first_deduction_date(disbursement_date: date) -> date:
    """
    Calculate the first deduction date based on disbursement date.

    Rule:
        - If disbursed on or before 15th: first deduction = 25th of same month
        - If disbursed after 15th: first deduction = 25th of next month

    Args:
        disbursement_date: Date when loan was disbursed

    Returns:
        Date of first salary deduction

    Examples:
        >>> calculate_first_deduction_date(date(2024, 1, 10))
        date(2024, 1, 25)

        >>> calculate_first_deduction_date(date(2024, 1, 20))
        date(2024, 2, 25)
    """
    deduction_day = settings.PAYROLL_DEDUCTION_DAY  # Default: 25

    if disbursement_date.day <= 15:
        # Same month, 25th
        first_deduction = date(disbursement_date.year, disbursement_date.month, deduction_day)
    else:
        # Next month, 25th
        next_month = disbursement_date + relativedelta(months=1)
        first_deduction = date(next_month.year, next_month.month, deduction_day)

    return first_deduction


def generate_repayment_schedule(loan: LoanApplication) -> List[RepaymentSchedule]:
    """
    Generate repayment schedule entries for a loan.

    Creates RepaymentSchedule model instances for each installment.
    All deductions occur on the 25th of each month starting from first_deduction_date.

    Args:
        loan: LoanApplication instance (must have first_deduction_date set)

    Returns:
        List of created RepaymentSchedule instances

    Raises:
        ValueError: If loan doesn't have required fields set
    """
    if not loan.first_deduction_date:
        raise ValueError('Loan must have first_deduction_date set')

    if not loan.monthly_deduction:
        raise ValueError('Loan must have monthly_deduction calculated')

    if not loan.total_repayment:
        raise ValueError('Loan must have total_repayment calculated')

    # Delete any existing schedule (in case of regeneration)
    loan.repayment_schedule.all().delete()

    schedules = []
    running_balance = loan.total_repayment
    deduction_date = loan.first_deduction_date

    for installment_num in range(1, loan.repayment_months + 1):
        # Calculate amount for this installment
        if installment_num == loan.repayment_months:
            # Last installment: pay remaining balance to handle rounding
            amount = running_balance
        else:
            amount = loan.monthly_deduction

        # Update running balance
        running_balance -= amount

        # Create schedule entry
        schedule = RepaymentSchedule.objects.create(
            loan=loan,
            installment_number=installment_num,
            due_date=deduction_date,
            amount=amount,
            running_balance=running_balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            is_first_deduction=(installment_num == 1),
            is_paid=False,
        )
        schedules.append(schedule)

        # Calculate next deduction date (25th of next month)
        deduction_date = deduction_date + relativedelta(months=1)

    logger.info(
        f'Generated {len(schedules)} repayment schedule entries for loan {loan.application_number}'
    )

    return schedules


def generate_application_number() -> str:
    """
    Generate a unique loan application number.

    Format: "254L" + 8 random digits

    Returns:
        Unique application number

    Example:
        "254L12345678"
    """
    max_attempts = 10
    for _ in range(max_attempts):
        # Generate 8 random digits
        digits = ''.join([str(random.randint(0, 9)) for _ in range(8)])
        number = f'254L{digits}'

        # Check uniqueness
        if not LoanApplication.objects.filter(application_number=number).exists():
            return number

    # Fallback: use timestamp if random generation fails
    import time
    timestamp_digits = str(int(time.time()))[-8:]
    return f'254L{timestamp_digits}'


def calculate_loan_affordability(
    monthly_salary: Decimal,
    requested_amount: Decimal,
    monthly_deduction: Decimal,
    max_deduction_percentage: Decimal = Decimal('0.33')
) -> Dict[str, any]:
    """
    Check if employee can afford the requested loan based on salary.

    Rule: Monthly deduction should not exceed 33% of gross monthly salary.

    Args:
        monthly_salary: Employee's monthly gross salary
        requested_amount: Requested loan amount
        monthly_deduction: Calculated monthly deduction
        max_deduction_percentage: Maximum allowed deduction as % of salary

    Returns:
        Dict with:
            - is_affordable: Boolean
            - max_allowed_deduction: Maximum deduction based on salary
            - deduction_percentage: Actual deduction as % of salary
            - message: Human-readable message
    """
    max_allowed = monthly_salary * max_deduction_percentage
    max_allowed = max_allowed.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    deduction_percentage = (monthly_deduction / monthly_salary) * Decimal('100')
    deduction_percentage = deduction_percentage.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    is_affordable = monthly_deduction <= max_allowed

    if is_affordable:
        message = f'Loan is affordable. Deduction is {deduction_percentage}% of salary.'
    else:
        message = (
            f'Loan may not be affordable. Deduction is {deduction_percentage}% of salary '
            f'(maximum recommended: {max_deduction_percentage * 100}%). '
            f'Maximum affordable monthly deduction: KES {max_allowed:,.2f}'
        )

    return {
        'is_affordable': is_affordable,
        'max_allowed_deduction': max_allowed,
        'deduction_percentage': deduction_percentage,
        'monthly_deduction': monthly_deduction,
        'message': message,
    }
