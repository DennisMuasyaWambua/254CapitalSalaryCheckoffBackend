"""
Versioned loan Terms & Conditions.

Employees read and accept the T&C in the frontend (TermsModal.tsx); the
backend records *which* version they accepted so an admin export can
reproduce the exact wording later.

When the T&C wording changes:
  1. Add a new entry to TERMS_VERSIONS (never edit a published one; existing
     loans were accepted against it).
  2. Point CURRENT_TERMS_VERSION at it.
  3. Update TermsModal.tsx in the frontend to the same wording.
"""

from datetime import date

from django.utils import timezone


TERMS_VERSIONS = {
    # Wording shipped in the frontend on 2026-02-26, the same evening the
    # backend began recording terms acceptance. Unchanged since.
    '2026-01': {
        'version': '2026-01',
        'effective_from': date(2026, 2, 26),
        'title': 'Terms & Conditions — Salary Check-Off Loan',
        'intro': 'Please read these terms carefully before applying for a loan.',
        'sections': [
            {
                'heading': '1. Eligibility Requirements',
                'paragraphs': [
                    'This salary check-off loan facility is available only to confirmed '
                    'staff members. Employees on probation or temporary contracts are not '
                    'eligible to apply for this loan product.',
                    'You must have completed your probation period and received written '
                    'confirmation of permanent employment from your employer to qualify '
                    'for this facility.',
                ],
            },
            {
                'heading': '2. Interest Rate Disclosure',
                'paragraphs': [
                    '254 Capital charges a flat interest rate of 5% on the principal loan '
                    'amount for the entire loan duration. This rate is applied once to the '
                    'principal and does not compound. The total repayment amount is '
                    'calculated as: Total = Principal + (Principal × 5%).',
                    'Example: A loan of KES 100,000 over 12 months will attract KES 5,000 '
                    'in interest, making the total repayment KES 105,000, with a monthly '
                    'deduction of KES 8,750.',
                ],
            },
            {
                'heading': '3. Payroll Deduction Authorization',
                'paragraphs': [
                    'By accepting these terms, you irrevocably authorize your employer to '
                    'deduct the agreed monthly loan repayment amount directly from your '
                    'salary. This deduction will be remitted to 254 Capital on your behalf.',
                    'You acknowledge that this authorization remains in effect until the '
                    'loan is fully repaid and cannot be withdrawn without prior written '
                    'consent from 254 Capital.',
                ],
            },
            {
                'heading': '4. Deduction Date Rules',
                'paragraphs': [
                    'Monthly deductions are processed on the 25th of each calendar month. '
                    'The first deduction date is determined as follows:',
                ],
                'bullets': [
                    'If the loan is disbursed on or before the 15th of the month, the '
                    'first deduction will be on the 25th of that same month.',
                    'If the loan is disbursed after the 15th, the first deduction will be '
                    'on the 25th of the following month.',
                ],
                'closing': [
                    'Subsequent deductions will occur on the 25th of each consecutive '
                    'month until the loan is fully repaid.',
                ],
            },
            {
                'heading': '5. Early Exit / Employment Termination',
                'paragraphs': [
                    'This facility is eligible to confirmed staff only. In the event that '
                    'your employment is terminated for any reason before the loan is fully '
                    'repaid, the outstanding loan balance becomes immediately due and '
                    'payable. Your employer is authorized to deduct the full outstanding '
                    'balance from your terminal dues.',
                    'If terminal dues are insufficient to cover the outstanding balance, '
                    'you remain personally liable for the remaining amount and must arrange '
                    'alternative repayment with 254 Capital within 30 days of termination.',
                ],
            },
            {
                'heading': '6. Document Handling & Privacy Policy',
                'paragraphs': [
                    'All documents submitted (National ID, payslips, etc.) will be stored '
                    'securely and used solely for the purpose of loan assessment and '
                    'verification. 254 Capital will not share your personal documents with '
                    'third parties except as required by law or for credit reference '
                    'purposes.',
                    'Documents are retained for a minimum of 7 years in compliance with '
                    'Kenyan financial regulations. You have the right to request access to '
                    'your personal data at any time.',
                    'Data Protection Compliance: 254 Capital is fully compliant with the '
                    'Data Protection Act, 2019 (Act No. 24 of 2019) of the Republic of '
                    'Kenya. Your personal data is processed lawfully, fairly, and '
                    'transparently in accordance with the Act. You have rights to access, '
                    'rectify, and request deletion of your personal data as provided under '
                    'the Act.',
                ],
            },
            {
                'heading': '7. Employment Verification Consent',
                'paragraphs': [
                    "You hereby consent to 254 Capital contacting your employer's HR "
                    'department to verify your employment status, salary details, and any '
                    'existing financial obligations. This verification is a mandatory '
                    'requirement for loan processing.',
                ],
            },
            {
                'heading': '8. Default & Late Payment',
                'paragraphs': [
                    'Failure to maintain employment without notifying 254 Capital, or any '
                    'action that prevents the scheduled deduction, will be considered a '
                    'default. 254 Capital reserves the right to report defaults to the '
                    'Credit Reference Bureau (CRB) and pursue legal recovery.',
                ],
            },
            {
                'heading': '9. Governing Law',
                'paragraphs': [
                    'These terms are governed by the laws of the Republic of Kenya. Any '
                    'disputes shall be resolved through the courts of Kenya or through '
                    'mutually agreed arbitration.',
                ],
            },
        ],
        # The checkbox the employee ticks before "Accept & Continue"
        'acceptance_statement': (
            'I have read and agree to the Terms and Conditions, including the payroll '
            'deduction authorization and privacy policy.'
        ),
        'footer': 'Last updated: January 2026 · 254 Capital Limited · Nairobi, Kenya',
    },
}

CURRENT_TERMS_VERSION = '2026-01'


def resolve_terms_for_loan(loan):
    """
    Return (terms, inferred) for the T&C a loan's applicant accepted.

    Loans submitted after version tracking began carry ``terms_version``.
    Older loans don't, so their version is inferred from the acceptance date:
    the newest version already in effect on that day. ``inferred`` is True in
    that case so exports can say the version wasn't recorded at the time.
    Returns (None, False) when the terms were never accepted.
    """
    if not loan.terms_accepted:
        return None, False

    if loan.terms_version in TERMS_VERSIONS:
        return TERMS_VERSIONS[loan.terms_version], False

    accepted_on = (
        timezone.localtime(loan.terms_accepted_at).date()
        if loan.terms_accepted_at else timezone.localdate(loan.created_at)
    )
    by_date = sorted(TERMS_VERSIONS.values(), key=lambda t: t['effective_from'])
    in_effect = [t for t in by_date if t['effective_from'] <= accepted_on]
    return (in_effect[-1] if in_effect else by_date[0]), True
