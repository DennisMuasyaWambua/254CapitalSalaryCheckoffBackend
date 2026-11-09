"""
Bulk export of employee loan applications as Excel, CSV or PDF.

One row per LoanApplication, filtered by employer, status and submitted date.
The three formats are rendered from the same rows (iter_rows), so for the same
filters they always carry the same applications and the same values.

Who sees what:
- Admins export every employer, or one employer via ``employer_id``.
- HR managers are always scoped to their own employer; any ``employer_id``
  they send is ignored.

Date filter: ``from_date``/``to_date`` apply to the date the application was
submitted (LoanApplication.created_at), inclusive, in Africa/Nairobi time.
"""

import csv
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Iterable, Iterator, Optional
from zoneinfo import ZoneInfo

from django.db.models import Count, DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.employers.models import Employer
from apps.loans.models import LoanApplication, LoanStatusHistory, RepaymentSchedule
from apps.loans.serializers import LoanApplicationListSerializer

EXPORT_TZ = ZoneInfo('Africa/Nairobi')
BRAND = '3F2A56'

# WeasyPrint lays out the whole report in memory: about 17s for 500 rows and
# 70s for 2,000 on a developer laptop, and nginx gives up after 60s. Larger
# exports must use Excel or CSV, which take about a second for 2,000 rows.
PDF_MAX_ROWS = 500

STATUS_LABELS = dict(LoanApplication.Status.choices)


# Filters

@dataclass(frozen=True)
class ExportFilters:
    employer: Optional[Employer]
    status: Optional[str]
    from_date: Optional[date]
    to_date: Optional[date]
    # True when the user cannot choose the employer (HR managers)
    employer_locked: bool

    def as_metadata(self):
        """Filters as plain values, for the audit log and API responses."""
        return {
            'employer_id': str(self.employer.id) if self.employer else None,
            'employer_name': self.employer.name if self.employer else None,
            'status': self.status,
            'from_date': self.from_date.isoformat() if self.from_date else None,
            'to_date': self.to_date.isoformat() if self.to_date else None,
        }

    def describe(self):
        """Human-readable filter lines for file headers."""
        if self.from_date and self.to_date:
            period = f'{_fmt_date(self.from_date)} to {_fmt_date(self.to_date)}'
        elif self.from_date:
            period = f'From {_fmt_date(self.from_date)}'
        elif self.to_date:
            period = f'Up to {_fmt_date(self.to_date)}'
        else:
            period = 'Any date'
        return [
            ('Employer', self.employer.name if self.employer else 'All employers'),
            ('Status', STATUS_LABELS[self.status] if self.status else 'All statuses'),
            ('Submitted', f'{period} (Africa/Nairobi)'),
        ]


def _parse_date(params, name, errors):
    raw = (params.get(name) or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        errors[name] = ['Enter the date as YYYY-MM-DD.']
        return None


def parse_export_filters(request):
    """
    Read and validate the export filters, applying the user's data scope.

    Raises ValidationError (400) with field-keyed messages for bad input, and
    PermissionDenied (403) for a role that cannot export.
    """
    params = request.query_params
    errors = {}
    user = request.user

    if user.role == 'hr_manager':
        hr_profile = getattr(user, 'hr_profile', None)
        if not hr_profile or not hr_profile.employer_id:
            raise PermissionDenied('Your HR account is not linked to an employer.')
        employer, employer_locked = hr_profile.employer, True
    elif user.role == 'admin':
        employer, employer_locked = None, False
        raw = (params.get('employer_id') or '').strip()
        if raw:
            try:
                employer = Employer.objects.get(id=uuid.UUID(raw))
            except (ValueError, Employer.DoesNotExist):
                errors['employer_id'] = ['Employer not found.']
    else:
        raise PermissionDenied('You do not have permission to export loan applications.')

    status = (params.get('status') or '').strip() or None
    if status and status not in STATUS_LABELS:
        errors['status'] = [
            f'Unknown status "{status}". Use one of: {", ".join(STATUS_LABELS)}.'
        ]

    from_date = _parse_date(params, 'from_date', errors)
    to_date = _parse_date(params, 'to_date', errors)
    if from_date and to_date and from_date > to_date:
        errors['to_date'] = ['The "to" date must be on or after the "from" date.']

    if errors:
        raise ValidationError(errors)
    return ExportFilters(employer, status, from_date, to_date, employer_locked)


def _start_of_day(day):
    return datetime.combine(day, time.min, tzinfo=EXPORT_TZ)


def filtered_applications(filters):
    """
    Applications matching the filters, without per-row annotations.

    Only plain filters on LoanApplication and forward foreign keys, so every
    application appears exactly once.
    """
    qs = LoanApplication.objects.all()
    if filters.employer is not None:
        qs = qs.filter(employer=filters.employer)
    if filters.status:
        qs = qs.filter(status=filters.status)
    # Compare against Nairobi day boundaries, so "to 31 Jan" includes
    # applications submitted late on 31 Jan and nothing from 1 Feb.
    if filters.from_date:
        qs = qs.filter(created_at__gte=_start_of_day(filters.from_date))
    if filters.to_date:
        qs = qs.filter(created_at__lt=_start_of_day(filters.to_date + timedelta(days=1)))
    return qs


def summarize(filters):
    """Count and principal per status for the filtered applications."""
    by_status = {
        row['status']: row
        for row in filtered_applications(filters)
        .order_by()
        .values('status')
        .annotate(count=Count('id'), principal=Sum('principal_amount'))
    }
    statuses = [
        {
            'status': value,
            'label': label,
            'count': by_status[value]['count'],
            'principal': by_status[value]['principal'] or Decimal('0.00'),
        }
        for value, label in LoanApplication.Status.choices
        if value in by_status
    ]
    return {
        'count': sum(s['count'] for s in statuses),
        'total_principal': sum((s['principal'] for s in statuses), Decimal('0.00')),
        'by_status': statuses,
    }


def export_queryset(filters):
    """
    Applications to export, with repayment and decision figures, in export order.

    Repaid amount and decision date come from correlated subqueries rather than
    joins, so a loan with several paid installments or status changes is still
    one row.
    """
    money = DecimalField(max_digits=12, decimal_places=2)
    # Same definition as LoanApplication.total_paid: the paid installments.
    paid = (
        RepaymentSchedule.objects.filter(loan=OuterRef('pk'), is_paid=True)
        .order_by()
        .values('loan')
        .annotate(total=Sum('amount'))
        .values('total')
    )
    # When 254 Capital last approved or declined the application
    decision = (
        LoanStatusHistory.objects.filter(
            application=OuterRef('pk'),
            status__in=[LoanApplication.Status.APPROVED, LoanApplication.Status.DECLINED],
        )
        .order_by('-created_at')
        .values('created_at')[:1]
    )
    return (
        filtered_applications(filters)
        .select_related('employee', 'employee__employee_profile', 'employer')
        .annotate(
            amount_repaid=Coalesce(
                Subquery(paid, output_field=money), Value(Decimal('0.00')), output_field=money
            ),
            decision_at=Subquery(decision),
        )
        .order_by('employer__name', 'employer_id', '-created_at', 'application_number')
    )


# Rows

@dataclass(frozen=True)
class Column:
    key: str
    header: str
    kind: str  # text | money | int | number | date | datetime
    width: int = 16


COLUMNS = (
    Column('application_number', 'Application Number', 'text', 18),
    Column('status', 'Status', 'text', 22),
    Column('employer', 'Employer', 'text', 28),
    Column('employee_name', 'Employee Name', 'text', 26),
    Column('national_id', 'National ID', 'text', 14),
    Column('phone_number', 'Phone Number', 'text', 16),
    Column('staff_number', 'Employee ID', 'text', 14),
    Column('department', 'Department', 'text', 18),
    Column('submitted_at', 'Submitted On', 'datetime', 18),
    Column('decision_at', 'Decision Date', 'datetime', 18),
    Column('updated_at', 'Last Updated', 'datetime', 18),
    Column('principal_amount', 'Principal Amount (KES)', 'money', 18),
    Column('repayment_months', 'Tenure (Months)', 'int', 10),
    Column('interest_method', 'Interest Method', 'text', 18),
    Column('interest_rate', 'Interest Rate (% per Month)', 'number', 12),
    Column('monthly_deduction', 'Monthly Deduction (KES)', 'money', 18),
    Column('total_interest', 'Total Interest (KES)', 'money', 16),
    Column('total_repayment', 'Total Repayment (KES)', 'money', 18),
    Column('amount_repaid', 'Amount Repaid (KES)', 'money', 16),
    Column('outstanding_balance', 'Outstanding Balance (KES)', 'money', 18),
    Column('disbursement_method', 'Disbursement Method', 'text', 16),
    Column('bank_name', 'Bank Name', 'text', 18),
    Column('bank_branch', 'Bank Branch', 'text', 16),
    Column('bank_account_number', 'Bank Account Number', 'text', 18),
    Column('mpesa_number', 'M-Pesa Number', 'text', 16),
    Column('disbursement_date', 'Disbursement Date', 'date', 14),
    Column('disbursement_reference', 'Disbursement Reference', 'text', 20),
    Column('first_deduction_date', 'First Deduction Date', 'date', 14),
    Column('purpose', 'Purpose', 'text', 40),
)
HEADERS = [c.header for c in COLUMNS]
MONEY_KEYS = [c.key for c in COLUMNS if c.kind == 'money']

# The admin application tables already resolve bank and M-Pesa details with a
# fallback to the employee profile; reuse that logic so the export matches.
_list_serializer = LoanApplicationListSerializer()


def _local(value):
    """Aware datetime -> naive Africa/Nairobi datetime (None stays None)."""
    return timezone.localtime(value, EXPORT_TZ).replace(tzinfo=None) if value else None


def build_row(loan):
    """One export row for a loan from export_queryset()."""
    employee = loan.employee
    profile = getattr(employee, 'employee_profile', None)
    disbursed = loan.status == LoanApplication.Status.DISBURSED

    total_interest = (
        loan.total_repayment - loan.principal_amount if loan.total_repayment is not None else None
    )
    # Repaid/outstanding only mean something once money has gone out.
    repaid = loan.amount_repaid if disbursed else None
    outstanding = (
        loan.total_repayment - loan.amount_repaid
        if disbursed and loan.total_repayment is not None else None
    )

    return {
        'application_number': loan.application_number,
        'status': loan.get_status_display(),
        'employer': loan.employer.name,
        'employee_name': employee.get_full_name(),
        'national_id': employee.national_id or '',
        'phone_number': employee.phone_number or '',
        'staff_number': profile.employee_id if profile else '',
        'department': (profile.department if profile else '') or '',
        'submitted_at': _local(loan.created_at),
        'decision_at': _local(loan.decision_at),
        'updated_at': _local(loan.updated_at),
        'principal_amount': loan.principal_amount,
        'repayment_months': loan.repayment_months,
        'interest_method': loan.get_interest_method_display(),
        'interest_rate': (loan.interest_rate * 100).quantize(Decimal('0.01'))
        if loan.interest_rate is not None else None,
        'monthly_deduction': loan.monthly_deduction,
        'total_interest': total_interest,
        'total_repayment': loan.total_repayment,
        'amount_repaid': repaid,
        'outstanding_balance': outstanding,
        'disbursement_method': loan.get_disbursement_method_display() if loan.disbursement_method else '',
        'bank_name': _list_serializer.get_bank_name(loan),
        'bank_branch': _list_serializer.get_bank_branch(loan),
        'bank_account_number': _list_serializer.get_bank_account_number(loan),
        'mpesa_number': _list_serializer.get_mpesa_number(loan) or '',
        'disbursement_date': loan.disbursement_date,
        'disbursement_reference': loan.disbursement_reference or '',
        'first_deduction_date': loan.first_deduction_date,
        'purpose': loan.purpose or '',
    }


def iter_rows(filters) -> Iterator[dict]:
    """Export rows in order, fetched in chunks so large exports stay small in memory."""
    for loan in export_queryset(filters).iterator(chunk_size=500):
        yield build_row(loan)


@dataclass(frozen=True)
class ExportContext:
    """Everything a renderer needs besides the rows."""
    filters: ExportFilters
    summary: dict
    export_id: uuid.UUID
    generated_at: datetime
    generated_by: str


def new_export_context(filters, user):
    return ExportContext(
        filters=filters,
        summary=summarize(filters),
        export_id=uuid.uuid4(),
        generated_at=timezone.now(),
        generated_by=user.get_full_name() or user.username,
    )


def export_filename(filters, extension):
    """loan-applications-{employer|all}-{status|all}-{from|any}-{to|any}.{ext}"""
    employer = 'all'
    if filters.employer is not None:
        employer = slugify(filters.employer.name)[:60].strip('-') or 'employer'
    parts = [
        'loan-applications',
        employer,
        (filters.status or 'all').replace('_', '-'),
        filters.from_date.isoformat() if filters.from_date else 'any',
        filters.to_date.isoformat() if filters.to_date else 'any',
    ]
    return f'{"-".join(parts)}.{extension}'


# Formatting helpers

def _fmt_date(value):
    return value.strftime('%d %b %Y') if value else ''


def _fmt_datetime(value):
    return value.strftime('%d %b %Y %H:%M') if value else ''


def _fmt_money(value):
    return f'{value:,.2f}' if value is not None else ''


def _generated_line(ctx):
    local = timezone.localtime(ctx.generated_at, EXPORT_TZ)
    return f'Generated {local.strftime("%d %b %Y, %H:%M")} EAT by {ctx.generated_by}'


# Text that a spreadsheet would run as a formula. A bare phone number such as
# +254712345678 is data, not a formula, so it is left alone.
_FORMULA_START = ('=', '+', '-', '@', '\t', '\r')
_PLAIN_NUMBER = re.compile(r'^\+?\d[\d ]*$')


def _neutralize(text):
    """Stop spreadsheet formula injection from user-entered text (CSV)."""
    if text and text.startswith(_FORMULA_START) and not _PLAIN_NUMBER.match(text):
        return "'" + text
    return text


# CSV

class _Echo:
    """File-like object whose write() just returns the line, for streaming."""

    def write(self, value):
        return value


def _csv_value(value, kind):
    if value is None:
        return ''
    if kind in ('money', 'number'):
        return f'{value:.2f}'  # no thousands separator, so spreadsheets read a number
    if kind == 'date':
        return value.isoformat()
    if kind == 'datetime':
        return value.strftime('%Y-%m-%d %H:%M')
    if kind == 'int':
        return str(value)
    return _neutralize(value)


def iter_csv(rows: Iterable[dict]) -> Iterator[str]:
    """
    Stream the CSV: a header line, then one line per application.

    Starts with a UTF-8 byte order mark so Excel reads accented names
    correctly. Values are plain (no thousands separators, ISO dates) so they
    stay numeric when opened in a spreadsheet.
    """
    writer = csv.writer(_Echo())
    yield '﻿'
    yield writer.writerow(HEADERS)
    for row in rows:
        yield writer.writerow([_csv_value(row[c.key], c.kind) for c in COLUMNS])


# Excel

_TITLE_FONT = Font(bold=True, size=14, color=BRAND)
_META_FONT = Font(color='555555')
_HEADER_FONT = Font(bold=True, color='FFFFFF')
_HEADER_FILL = PatternFill(start_color=BRAND, end_color=BRAND, fill_type='solid')
_TOTAL_FONT = Font(bold=True)
_NUMBER_FORMATS = {
    'money': '#,##0.00',
    'number': '0.00',
    'int': '0',
    'date': 'DD MMM YYYY',
    'datetime': 'DD MMM YYYY HH:MM',
}


def _xlsx_cell(ws, value, kind, font=None):
    cell = WriteOnlyCell(ws, value=value)
    if kind == 'text' and isinstance(value, str):
        # Always store text as text: openpyxl would otherwise write any value
        # starting with "=" (e.g. an employee's purpose) as a live formula.
        cell.data_type = 's'
    elif kind in _NUMBER_FORMATS and value is not None:
        cell.number_format = _NUMBER_FORMATS[kind]
    if font is not None:
        cell.font = font
    return cell


def render_xlsx(rows: Iterable[dict], ctx: ExportContext) -> bytes:
    """
    One sheet: title, filters, generated-at, then a header row and one row per
    application. Amounts and dates are real numeric/date cells so they sum and
    sort in Excel; a totals row follows the data.
    """
    wb = Workbook(write_only=True)
    ws = wb.create_sheet('Loan Applications')
    for index, column in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(index)].width = column.width

    def text_row(text, font=_META_FONT):
        return [_xlsx_cell(ws, text, 'text', font)]

    ws.append(text_row('254 Capital - Loan Applications Export', _TITLE_FONT))
    ws.append(text_row(' · '.join(f'{label}: {value}' for label, value in ctx.filters.describe())))
    ws.append(text_row(
        f'{_generated_line(ctx)} · {ctx.summary["count"]} application'
        f'{"" if ctx.summary["count"] == 1 else "s"} · Export ref {ctx.export_id}'
    ))
    ws.append([])

    header_row = 5
    ws.freeze_panes = f'B{header_row + 1}'
    header = []
    for column in COLUMNS:
        cell = _xlsx_cell(ws, column.header, 'text', _HEADER_FONT)
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        header.append(cell)
    ws.append(header)

    totals = dict.fromkeys(MONEY_KEYS, Decimal('0.00'))
    count = 0
    for row in rows:
        count += 1
        for key in MONEY_KEYS:
            if row[key] is not None:
                totals[key] += row[key]
        ws.append([_xlsx_cell(ws, row[c.key], c.kind) for c in COLUMNS])

    last_column = get_column_letter(len(COLUMNS))
    if count:
        ws.auto_filter.ref = f'A{header_row}:{last_column}{header_row + count}'
        ws.append([])
        total_cells = []
        for column in COLUMNS:
            if column.key == 'application_number':
                total_cells.append(_xlsx_cell(ws, f'Total ({count})', 'text', _TOTAL_FONT))
            elif column.kind == 'money':
                total_cells.append(_xlsx_cell(ws, totals[column.key], 'money', _TOTAL_FONT))
            else:
                total_cells.append(None)
        ws.append(total_cells)
    else:
        ws.append(text_row('No applications match these filters.'))

    output = BytesIO()
    wb.save(output)
    return output.getvalue()


# PDF

def render_pdf(rows: Iterable[dict], ctx: ExportContext) -> bytes:
    """A landscape tabular report: summary first, then the applications."""
    from weasyprint import HTML

    display_rows = []
    for row in rows:
        display_rows.append({
            **row,
            'submitted_at': _fmt_datetime(row['submitted_at']),
            'decision_at': _fmt_datetime(row['decision_at']),
            'updated_at': _fmt_datetime(row['updated_at']),
            'principal_amount': _fmt_money(row['principal_amount']),
            'monthly_deduction': _fmt_money(row['monthly_deduction']),
            'total_interest': _fmt_money(row['total_interest']),
            'total_repayment': _fmt_money(row['total_repayment']),
            'amount_repaid': _fmt_money(row['amount_repaid']),
            'outstanding_balance': _fmt_money(row['outstanding_balance']),
            'disbursement_date': _fmt_date(row['disbursement_date']),
            'first_deduction_date': _fmt_date(row['first_deduction_date']),
        })

    summary = ctx.summary
    html = render_to_string('exports/loan_applications_report.html', {
        'rows': display_rows,
        'filters': ctx.filters.describe(),
        'count': summary['count'],
        'total_principal': _fmt_money(summary['total_principal']),
        'by_status': [
            {**s, 'principal': _fmt_money(s['principal'])} for s in summary['by_status']
        ],
        'generated_line': _generated_line(ctx),
        'export_id': ctx.export_id,
    })
    return HTML(string=html).write_pdf()
