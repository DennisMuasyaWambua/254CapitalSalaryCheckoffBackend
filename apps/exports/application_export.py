"""
Admin export of a single loan application, with the Terms & Conditions the
employee accepted, as PDF or Excel.

build_application_record() gathers everything once; the PDF and Excel
renderers only lay it out, so the two formats always carry the same facts.
"""

import math
from decimal import Decimal
from io import BytesIO

from django.template.loader import render_to_string
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.audit.models import AuditLog
from apps.loans.terms import resolve_terms_for_loan

NOT_RECORDED = 'Not recorded'
BRAND = '3F2A56'


def _money(value):
    return f'KES {value:,.2f}' if value is not None else NOT_RECORDED


def _date(value):
    return value.strftime('%d %b %Y') if value else NOT_RECORDED


def _datetime(value):
    return timezone.localtime(value).strftime('%d %b %Y, %H:%M:%S %Z') if value else NOT_RECORDED


def _person(user):
    if not user:
        return 'System'
    return user.get_full_name() or user.username or user.phone_number


def _submission_ip(loan):
    """IP the application (and so the T&C acceptance) was submitted from."""
    entry = AuditLog.objects.filter(
        target_type='LoanApplication',
        target_id=loan.id,
        action__startswith='Loan application submitted',
    ).order_by('created_at').first()
    return entry.ip_address if entry and entry.ip_address else NOT_RECORDED


def build_application_record(loan, generated_by):
    """Collect every fact the export shows, as display-ready values."""
    employee = loan.employee
    profile = getattr(employee, 'employee_profile', None)

    interest = (
        loan.total_repayment - loan.principal_amount
        if loan.total_repayment is not None else None
    )
    method_label = 'Reducing Balance' if loan.interest_method == 'reducing_balance' else 'Flat Rate'
    rate_pct = (loan.interest_rate or Decimal('0')) * 100

    disbursement = [
        ('Method', loan.get_disbursement_method_display() or NOT_RECORDED),
    ]
    if loan.disbursement_method == 'bank':
        disbursement += [
            ('Bank', loan.bank_name or (profile.bank_name if profile else '') or NOT_RECORDED),
            ('Branch', loan.bank_branch or (profile.bank_branch if profile else '') or NOT_RECORDED),
            ('Account Number',
             loan.account_number or (profile.bank_account_number if profile else '') or NOT_RECORDED),
        ]
    elif loan.disbursement_method == 'mpesa':
        disbursement.append(
            ('M-Pesa Number', (profile.mpesa_number if profile else '') or employee.phone_number)
        )
    disbursement += [
        ('Disbursement Date', _date(loan.disbursement_date)),
        ('Disbursement Reference', loan.disbursement_reference or NOT_RECORDED),
        ('First Deduction Date', _date(loan.first_deduction_date)),
    ]

    terms, terms_inferred = resolve_terms_for_loan(loan)
    if terms:
        version = terms['version']
        if terms_inferred:
            version += ' (inferred from acceptance date; not recorded at submission)'
    else:
        version = 'N/A'
    acceptance = [
        ('Terms Accepted', 'Yes' if loan.terms_accepted else 'No'),
        ('Accepted At', _datetime(loan.terms_accepted_at)),
        ('Terms Version', version),
        ('Submitted From IP', _submission_ip(loan)),
    ]
    if terms:
        acceptance.append(('Acceptance Statement', terms['acceptance_statement']))

    sections = [
        ('Applicant', [
            ('Full Name', employee.get_full_name() or NOT_RECORDED),
            ('National ID', employee.national_id or NOT_RECORDED),
            ('Phone Number', employee.phone_number),
            ('Email', employee.email or NOT_RECORDED),
        ]),
        ('Employment', [
            ('Employer', loan.employer.name),
            ('Employee ID', profile.employee_id if profile else NOT_RECORDED),
            ('Department', (profile.department if profile else '') or NOT_RECORDED),
            ('Employment Type', profile.get_employment_type_display() if profile else NOT_RECORDED),
            ('Monthly Gross Salary', _money(profile.monthly_gross_salary) if profile else NOT_RECORDED),
        ]),
        ('Loan Details', [
            ('Application Number', loan.application_number),
            ('Status', loan.get_status_display()),
            ('Application Date', _datetime(loan.created_at)),
            ('Principal Amount', _money(loan.principal_amount)),
            ('Interest Rate', f'{rate_pct:.2f}% per month ({method_label})'),
            ('Repayment Period', f'{loan.repayment_months} month{"s" if loan.repayment_months != 1 else ""}'),
            ('Monthly Deduction', _money(loan.monthly_deduction)),
            ('Total Interest', _money(interest)),
            ('Total Repayment', _money(loan.total_repayment)),
            ('Purpose', loan.purpose or NOT_RECORDED),
        ]),
        ('Disbursement', disbursement),
        ('Terms & Conditions Acceptance', acceptance),
    ]

    status_history = [
        {
            'date': _datetime(entry.created_at),
            'status': entry.get_status_display(),
            'actor': _person(entry.actor),
            'comment': entry.comment,
        }
        for entry in loan.status_history.select_related('actor').order_by('created_at')
    ]
    schedule = [
        {
            'number': item.installment_number,
            'due_date': item.due_date,
            'amount': item.amount,
            'running_balance': item.running_balance,
            'is_paid': item.is_paid,
            'paid_date': item.paid_date,
        }
        for item in loan.repayment_schedule.order_by('installment_number')
    ]
    documents = [
        {
            'type': doc.get_document_type_display(),
            'filename': doc.original_filename,
            'uploaded_at': _datetime(doc.created_at),
        }
        for doc in loan.documents.order_by('created_at')
    ]

    return {
        'application_number': loan.application_number,
        'employee_name': employee.get_full_name() or employee.phone_number,
        'status': loan.get_status_display(),
        'generated_at': _datetime(timezone.now()),
        'generated_by': _person(generated_by),
        'sections': sections,
        'terms': terms,
        'terms_inferred': terms_inferred,
        'status_history': status_history,
        'schedule': schedule,
        'documents': documents,
    }


# PDF

def generate_application_pdf(record) -> bytes:
    from weasyprint import HTML

    context = dict(record)
    context['schedule'] = [
        {**row,
         'due_date': _date(row['due_date']),
         'amount': _money(row['amount']),
         'running_balance': _money(row['running_balance']),
         'paid': f'Paid {_date(row["paid_date"])}' if row['is_paid'] else 'Pending'}
        for row in record['schedule']
    ]
    html = render_to_string('exports/loan_application.html', context)
    return HTML(string=html).write_pdf()


# Excel

_TITLE = Font(bold=True, size=14, color=BRAND)
_HEADER = Font(bold=True, color='FFFFFF')
_HEADER_FILL = PatternFill(start_color=BRAND, end_color=BRAND, fill_type='solid')
_SECTION = Font(bold=True, size=12, color=BRAND)
_LABEL = Font(bold=True)
_THIN = Side(style='thin', color='BBBBBB')
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_WRAP = Alignment(wrap_text=True, vertical='top')


def _fit_height(ws, row, text, width):
    """openpyxl can't auto-fit wrapped rows; estimate the lines needed."""
    lines = sum(max(1, math.ceil(len(part) / (width * 1.1))) for part in str(text).split('\n'))
    if lines > 1:
        ws.row_dimensions[row].height = 15 * lines


def _table(ws, headers, rows, widths, money_cols=(), date_cols=()):
    ws.append(headers)
    for cell in ws[ws.max_row]:
        cell.font, cell.fill, cell.border = _HEADER, _HEADER_FILL, _BORDER
    for row in rows:
        ws.append(row)
        for col, cell in enumerate(ws[ws.max_row], start=1):
            cell.border, cell.alignment = _BORDER, _WRAP
            if col in money_cols:
                cell.number_format = '#,##0.00'
            elif col in date_cols:
                cell.number_format = 'DD MMM YYYY'
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def generate_application_excel(record) -> bytes:
    wb = Workbook()

    # Application details
    ws = wb.active
    ws.title = 'Application'
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 70
    ws['A1'] = '254 Capital — Loan Application Record'
    ws['A1'].font = _TITLE
    ws['A2'] = (f'{record["application_number"]} · {record["employee_name"]} · '
                f'Generated {record["generated_at"]} by {record["generated_by"]}')
    for heading, rows in record['sections']:
        ws.append([])
        ws.append([heading])
        ws.cell(row=ws.max_row, column=1).font = _SECTION
        for label, value in rows:
            ws.append([label, value])
            ws.cell(row=ws.max_row, column=1).font = _LABEL
            for cell in ws[ws.max_row]:
                cell.border, cell.alignment = _BORDER, _WRAP
            _fit_height(ws, ws.max_row, value, 70)

    # Terms & Conditions, verbatim as accepted
    ws = wb.create_sheet('Terms & Conditions')
    ws.column_dimensions['A'].width = 110
    terms = record['terms']
    acceptance = dict(record['sections'])['Terms & Conditions Acceptance']
    if not terms:
        ws['A1'] = 'The applicant did not accept the Terms & Conditions.'
        ws['A1'].font = _SECTION
    else:
        ws['A1'] = terms['title']
        ws['A1'].font = _TITLE
        for label, value in acceptance:
            ws.append([f'{label}: {value}'])
            ws.cell(row=ws.max_row, column=1).alignment = _WRAP
            _fit_height(ws, ws.max_row, f'{label}: {value}', 110)
        ws.append([])
        ws.append([terms['intro']])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True)
        for section in terms['sections']:
            ws.append([])
            ws.append([section['heading']])
            ws.cell(row=ws.max_row, column=1).font = _SECTION
            blocks = (section['paragraphs']
                      + [f'• {b}' for b in section.get('bullets', [])]
                      + section.get('closing', []))
            for text in blocks:
                ws.append([text])
                ws.cell(row=ws.max_row, column=1).alignment = _WRAP
                _fit_height(ws, ws.max_row, text, 110)
        ws.append([])
        ws.append([terms['footer']])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, color='666666')

    # Status history
    ws = wb.create_sheet('Status History')
    _table(ws, ['Date', 'Status', 'By', 'Comment'],
           [[h['date'], h['status'], h['actor'], h['comment']] for h in record['status_history']],
           widths=[26, 24, 26, 70])

    # Repayment schedule (only exists once the loan is disbursed)
    if record['schedule']:
        ws = wb.create_sheet('Repayment Schedule')
        _table(ws, ['Installment', 'Due Date', 'Amount (KES)', 'Running Balance (KES)', 'Status', 'Paid On'],
               [[r['number'], r['due_date'], r['amount'], r['running_balance'],
                 'Paid' if r['is_paid'] else 'Pending', r['paid_date']] for r in record['schedule']],
               widths=[12, 16, 18, 22, 12, 16], money_cols=(3, 4), date_cols=(2, 6))

    # Supporting documents
    ws = wb.create_sheet('Documents')
    _table(ws, ['Document', 'File Name', 'Uploaded'],
           [[d['type'], d['filename'], d['uploaded_at']] for d in record['documents']],
           widths=[28, 50, 26])

    output = BytesIO()
    wb.save(output)
    return output.getvalue()
