import io
import re
from functools import wraps

import pandas as pd
from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse

MOBILE_RE = re.compile(r'^\d{10}$')
REQUIRED_COLS = ('company_name', 'partner_name', 'mobile_number')
OPTIONAL_COLS = ('rera_number', 'is_active')
ALLOWED_EXT = ('.xlsx', '.xls', '.csv')


def _get_role(user):
    try:
        return user.profile.role
    except Exception:
        return 'admin'


def require_role(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if _get_role(request.user) not in roles:
                return HttpResponseForbidden("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def _log(user, action, request, changes=''):
    """Best-effort audit log. Silently no-ops if AuditLog model missing."""
    try:
        AuditLog = apps.get_model('customer_enquiry', 'AuditLog')
        ip = None
        if request is not None:
            xf = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = xf.split(',')[0] if xf else request.META.get('REMOTE_ADDR')
        AuditLog.objects.create(
            user=user, action=action, model_name='ChannelPartnerMaster',
            object_repr='bulk_upload', changes=changes, ip_address=ip,
        )
    except Exception:
        pass


def _parse_bool(v, default=True):
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ('', 'nan', 'none'):
        return default
    return s in ('1', 'true', 'yes', 'y', 'active', 't')


def _clean(v):
    if v is None:
        return ''
    s = str(v).strip()
    if s.lower() in ('nan', 'none'):
        return ''
    return s


@require_role('admin', 'super_admin')
def cp_bulk_upload(request):
    CPM = apps.get_model('customer_enquiry', 'ChannelPartnerMaster')

    if request.method == 'GET':
        return render(request, 'bulk_upload/bulk_upload.html', {
            'errors': request.session.get('bulk_cp_errors', []),
            'skipped': request.session.get('bulk_cp_skipped', []),
            'summary': request.session.pop('bulk_cp_summary', None),
        })

    f = request.FILES.get('file')
    if not f:
        messages.error(request, 'No file selected.')
        return redirect(reverse('bulk_upload:cp_bulk_upload'))

    name = f.name.lower()
    if not name.endswith(ALLOWED_EXT):
        messages.error(request, 'Only .xlsx, .xls or .csv files are allowed.')
        return redirect(reverse('bulk_upload:cp_bulk_upload'))

    try:
        if name.endswith('.csv'):
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(f, dtype=str, engine='openpyxl' if name.endswith('.xlsx') else None)
    except Exception as e:
        messages.error(request, f'File parse error: {e}')
        return redirect(reverse('bulk_upload:cp_bulk_upload'))  # noqa

    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        messages.error(request, f'Required columns missing: {", ".join(missing)}')
        return redirect(reverse('bulk_upload:cp_bulk_upload'))

    existing_keys = {
        (m, (c or '').strip().lower(), (p or '').strip().lower())
        for m, c, p in CPM.objects.values_list('mobile_number', 'company_name', 'partner_name')
    }
    seen_in_file = set()
    valid_objs = []
    errors = []
    skipped = []

    for idx, row in df.iterrows():
        row_no = int(idx) + 2  # +1 for header, +1 for 1-indexed
        company = _clean(row.get('company_name'))
        partner = _clean(row.get('partner_name'))
        mobile = _clean(row.get('mobile_number'))
        rera = _clean(row.get('rera_number')) if 'rera_number' in df.columns else ''
        is_active = _parse_bool(row.get('is_active'), default=True) if 'is_active' in df.columns else True

        reasons = []
        if not company:
            reasons.append('company_name is empty')
        elif len(company) > 200:
            reasons.append('company_name exceeds 200 characters')
        if not partner:
            reasons.append('partner_name is empty')
        elif len(partner) > 100:
            reasons.append('partner_name exceeds 100 characters')
        if not mobile:
            reasons.append('mobile_number is empty')
        elif not MOBILE_RE.match(mobile):
            reasons.append('mobile_number must be exactly 10 digits')
        if rera and len(rera) > 50:
            reasons.append('rera_number exceeds 50 characters')

        if reasons:
            errors.append({'row': row_no, 'mobile': mobile, 'reason': '; '.join(reasons)})
            continue

        key = (mobile, company.lower(), partner.lower())
        if key in existing_keys:
            skipped.append({'row': row_no, 'mobile': mobile, 'reason': 'Already exists in database (same mobile + company + partner)'})
            continue
        if key in seen_in_file:
            skipped.append({'row': row_no, 'mobile': mobile, 'reason': 'Duplicate within uploaded file (same mobile + company + partner)'})
            continue

        seen_in_file.add(key)
        valid_objs.append(CPM(
            company_name=company,
            partner_name=partner,
            mobile_number=mobile,
            rera_number=rera,
            is_active=is_active,
        ))

    created = 0
    if valid_objs:
        with transaction.atomic():
            CPM.objects.bulk_create(valid_objs, batch_size=500)
            created = len(valid_objs)

    _log(request.user, 'BULK_UPLOAD', request,
         changes=f'created={created}, skipped={len(skipped)}, errors={len(errors)}')

    if created:
        messages.success(request, f'{created} channel partner(s) successfully added.')
    if skipped:
        messages.warning(request, f'{len(skipped)} row(s) skipped (duplicates).')
    if errors:
        messages.error(request, f'{len(errors)} row(s) failed validation.')
    if not (created or skipped or errors):
        messages.info(request, 'File was empty or no processable rows found.')

    request.session['bulk_cp_errors'] = errors
    request.session['bulk_cp_skipped'] = skipped
    request.session['bulk_cp_summary'] = {
        'created': created, 'skipped': len(skipped), 'errors': len(errors),
        'total': len(df),
    }
    return redirect(reverse('bulk_upload:cp_bulk_upload'))


@require_role('admin', 'super_admin')
def clear_results(request):
    for k in ('bulk_cp_errors', 'bulk_cp_skipped', 'bulk_cp_summary'):
        request.session.pop(k, None)
    messages.info(request, 'Previous results cleared.')
    return redirect(reverse('bulk_upload:cp_bulk_upload'))


@require_role('admin', 'super_admin')
def download_template(request):
    df = pd.DataFrame([{
        'company_name': 'ABC Realty Pvt Ltd',
        'partner_name': 'Rahul Sharma',
        'mobile_number': '9876543210',
        'rera_number': 'A12345678',
        'is_active': 'true',
    }])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='ChannelPartners')
    buf.seek(0)
    resp = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    resp['Content-Disposition'] = 'attachment; filename="channel_partners_template.xlsx"'
    return resp


@require_role('admin', 'super_admin')
def download_error_report(request):
    errors = request.session.get('bulk_cp_errors', [])
    skipped = request.session.get('bulk_cp_skipped', [])
    rows = (
        [{'Row': e['row'], 'Mobile': e['mobile'], 'Type': 'Error', 'Reason': e['reason']} for e in errors]
        + [{'Row': s['row'], 'Mobile': s['mobile'], 'Type': 'Skipped', 'Reason': s['reason']} for s in skipped]
    )
    if not rows:
        messages.info(request, 'No error/skip report available.')
        return redirect(reverse('bulk_upload:cp_bulk_upload'))

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Report')
    buf.seek(0)
    resp = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    resp['Content-Disposition'] = 'attachment; filename="bulk_upload_error_report.xlsx"'
    return resp
