"""
Reconciliation and payment matching services.
"""

from decimal import Decimal
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


def match_payments_to_loans(
    total_amount: Decimal,
    expected_records: List[Dict]
) -> Dict:
    """
    Match remitted amount against expected deductions.

    Args:
        total_amount: Total remitted amount
        expected_records: List of expected deduction records with loan_id and amount

    Returns:
        Dict with match results
    """
    try:
        # Calculate total expected
        total_expected = sum(record['amount'] for record in expected_records)

        # Calculate variance
        variance = total_amount - total_expected

        # Tolerance for rounding (1 KES)
        tolerance = Decimal('1.00')

        # Exact match or within tolerance
        if abs(variance) <= tolerance:
            match_type = 'exact' if variance == 0 else 'within_tolerance'

            # Mark all as matched
            results = []
            for record in expected_records:
                results.append({
                    'loan_id': record['loan_id'],
                    'expected': record['amount'],
                    'received': record['amount'],
                    'is_matched': True,
                    'variance': Decimal('0.00')
                })

            return {
                'match_type': match_type,
                'total_expected': total_expected,
                'total_received': total_amount,
                'variance': variance,
                'is_fully_matched': True,
                'records': results
            }

        # Overpayment
        elif variance > 0:
            # Distribute overpayment proportionally (or could be manual)
            results = []
            for record in expected_records:
                results.append({
                    'loan_id': record['loan_id'],
                    'expected': record['amount'],
                    'received': record['amount'],  # Keep expected, mark excess separately
                    'is_matched': True,
                    'variance': Decimal('0.00')
                })

            return {
                'match_type': 'overpayment',
                'total_expected': total_expected,
                'total_received': total_amount,
                'variance': variance,
                'is_fully_matched': False,
                'excess_amount': variance,
                'records': results,
                'note': f'Excess amount of KES {variance:,.2f} to be credited or carried forward'
            }

        # Underpayment - need manual reconciliation
        else:
            results = []
            for record in expected_records:
                results.append({
                    'loan_id': record['loan_id'],
                    'expected': record['amount'],
                    'received': Decimal('0.00'),  # Mark as unmatched, manual intervention needed
                    'is_matched': False,
                    'variance': record['amount']
                })

            return {
                'match_type': 'underpayment',
                'total_expected': total_expected,
                'total_received': total_amount,
                'variance': variance,
                'is_fully_matched': False,
                'shortfall': abs(variance),
                'records': results,
                'note': f'Shortfall of KES {abs(variance):,.2f} requires manual reconciliation'
            }

    except Exception as e:
        logger.error(f'Payment matching failed: {str(e)}')
        return {
            'match_type': 'error',
            'error': str(e)
        }
