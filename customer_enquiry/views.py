from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from datetime import datetime
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .models import Customer, CustomerSource, ChannelPartner, Referral, InternalSalesAssessment, BookingApplication, BookingApplicant, BookingChannelPartner, Project, UserProfile, AdditionalChannelPartner, CustomerAssignment, CustomerRevisit, AuditLog, ChannelPartnerMaster
from django.shortcuts import get_object_or_404
import json
import logging
import random
import requests as http_client
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse, HttpResponseRedirect
import time     
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
import io
from django.db import models
from django.db.models import Q
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.contrib.auth.views import PasswordResetView
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Role helpers ────────────────────────────────────────────────────────────

def get_user_role(user):
    """Return role string for a user, defaults to 'admin' if no profile."""
    try:
        return user.profile.role
    except Exception:
        return 'admin'


def role_redirect(user):
    """Return the correct dashboard URL name based on user role."""
    role = get_user_role(user)
    mapping = {
        'super_admin':      'customer_enquiry:super_admin_dashboard',
        'admin':            'customer_enquiry:admin_dashboard',
        'gre':              'customer_enquiry:gre_dashboard',
        'sourcing_manager': 'customer_enquiry:sourcing_manager_dashboard',
        'closing_manager':  'customer_enquiry:closing_manager_dashboard',
    }
    return mapping.get(role, 'customer_enquiry:dashboard')


def require_role(*roles):
    """Decorator: allow only users with given roles. Others → 403."""
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            role = get_user_role(request.user)
            if role not in roles:
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def log_action(user, action, model_name='', object_id=None, object_repr='', changes='', request=None):
    """Helper to create an AuditLog entry."""
    ip = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')
    try:
        AuditLog.objects.create(
            user=user,
            action=action,
            model_name=model_name,
            object_id=object_id,
            object_repr=object_repr,
            changes=changes,
            ip_address=ip,
        )
    except Exception as e:
        logger.error(f"AuditLog creation failed: {e}")

# Helper function to get project data from database
def get_project_by_code(code):
    """Get project data from database by form number or URL code"""
    try:
        # First try to get by exact form number
        project = Project.objects.get(form_number=code, is_active=True)
    except Project.DoesNotExist:
        try:
            # If not found, try to match by prefix (for URL codes like 'Alt', 'Med', etc.)
            # Map URL codes to prefixes
            url_code_mapping = {
                'Alt': 'ALT',
                'Med': 'MED',
                'Orn': 'ORN',
                'Star': 'STAR',
                'Ant': 'ANT'
            }

            if code in url_code_mapping:
                prefix = url_code_mapping[code]
                # Get the first active project with matching prefix
                project = Project.objects.filter(
                    project_prefix__icontains=prefix,
                    is_active=True
                ).first()

                if not project:
                    return None
            else:
                return None
        except Project.DoesNotExist:
            return None

    if project:
        return {
            'code': project.form_number,
            'name': project.project_name,
            'location': project.site_name,
            'address': project.address,
            'company_name': project.company_name,
            'maharera_no': project.maharera_no,
            'logo': str(project.project_logo) if project.project_logo else None,
            'prefix': project.project_prefix
        }

    return None

def index(request, property_code=None):
    """
    Display the customer form - Updated to use dynamic project data from database
    """
    # Get property from URL parameter if provided
    if property_code:
        selected_property = get_project_by_code(property_code)
    else:
        selected_property = None

    # Get property from GET parameter (from verification page)
    get_property = request.GET.get('property')
    if get_property and not selected_property:
        selected_property = get_project_by_code(get_property)

    # If still no property found, check session for stored property code
    if not selected_property:
        session_property = request.session.get('selected_property_code')
        if session_property:
            selected_property = get_project_by_code(session_property)

    # Get verified phone number from session
    verified_phone = request.session.get('user_phone')

    # Get all active projects for any dropdowns
    active_projects = Project.objects.active_projects()

    # Channel partner master list for auto-fill
    import json as _json
    cp_master = list(ChannelPartnerMaster.objects.filter(is_active=True).values(
        'id', 'company_name', 'partner_name', 'mobile_number', 'rera_number'
    ))
    cp_master_json = _json.dumps(cp_master)

    context = {
        'selected_property': selected_property,
        'property_code': property_code or get_property or request.session.get('selected_property_code'),
        'verified_phone': verified_phone,
        'active_projects': active_projects,
        'cp_master_json': cp_master_json,
    }

    # Use the new template name that matches your current working form
    return render(request, 'customer_enquiry.html', context)

def thank_you(request):
    """Display thank you page - NO AUTH CHECK"""
    # Get customer data from session if available
    customer_data = request.session.get('customer_data', None)
    
    context = {
        'customer_data': customer_data,
        'form_number': customer_data.get('form_number', 'N/A') if customer_data else 'N/A',
        'customer_name': customer_data.get('customer_name', 'Customer') if customer_data else 'Customer',
        'property_name': customer_data.get('property_name', 'Property') if customer_data else 'Property'
    }
    
    # Clear session data after use
    if 'customer_data' in request.session:
        del request.session['customer_data']
    
    return render(request, 'thank-you.html', context)



@require_http_methods(["POST"])
@require_http_methods(["POST"])
def save_step_view(request):
    """
    AJAX endpoint: save partial customer form data for a given step.
    Creates or updates a Customer record. Returns form_number + customer_id.
    """
    try:
        data = request.POST
        step = int(data.get('step', 1))
        customer_id = data.get('customer_id', '').strip()
        property_code = data.get('property_code', '').strip()

        # Resolve project prefix for form_number generation
        project_prefix = property_code
        try:
            project = Project.objects.get(form_number=property_code, is_active=True)
            project_prefix = project.project_prefix
        except Project.DoesNotExist:
            if '-' in property_code:
                parts = property_code.split('-')
                project_prefix = parts[0] if parts[1].isdigit() else f"{parts[0]}-{parts[1]}"

        if customer_id:
            try:
                customer = Customer.objects.get(id=customer_id)
            except Customer.DoesNotExist:
                customer = None
        else:
            customer = None

        # Build update dict based on step
        update_fields = {}

        if step >= 1:
            update_fields.update({
                'first_name': data.get('first_name', ''),
                'middle_name': data.get('middle_name', ''),
                'last_name': data.get('last_name', ''),
                'email': data.get('email', ''),
                'phone_number': data.get('phone_number') or None,
                'sex': data.get('sex', ''),
                'marital_status': data.get('marital_status', ''),
                'date_of_birth': data.get('date_of_birth') or None,
                'residential_address': data.get('residential_address', ''),
                'city': data.get('city', ''),
                'locality': data.get('locality', ''),
                'pincode': data.get('pincode', ''),
                'nationality': data.get('nationality', ''),
            })

        if step >= 2:
            update_fields.update({
                'employment_type': data.get('employment_type', ''),
                'company_name': data.get('company_name', ''),
                'designation': data.get('designation', ''),
                'industry': data.get('industry', ''),
            })

        if step >= 3:
            update_fields.update({
                'configuration': data.get('configuration', ''),
                'budget': data.get('budget', ''),
                'construction_status': data.get('construction_status', ''),
                'purpose_of_buying': data.get('purpose_of_buying', ''),
            })

        if step >= 4:
            update_fields.update({
                'source_details': data.get('source_details', ''),
            })

        if customer:
            for k, v in update_fields.items():
                setattr(customer, k, v)
            customer.save()
        else:
            # Generate form number
            while True:
                form_number = f"{project_prefix}-{random.randint(10000, 99999)}"
                if not Customer.objects.filter(form_number=form_number).exists():
                    break
            update_fields['form_number'] = form_number
            update_fields.setdefault('form_date', timezone.now().date())
            customer = Customer.objects.create(**update_fields)

        return JsonResponse({
            'success': True,
            'customer_id': customer.id,
            'form_number': customer.form_number,
            'step': step,
        })

    except Exception as e:
        logger.error(f"save_step error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def customer_submit_view(request):
    """Handle customer form submission with property support, phone number, sex, and marital status"""
    try:
        with transaction.atomic():
            # Extract and validate data
            data = request.POST
            
            # Get property code from form
            property_code = data.get('property_code')
            user_phone = data.get('user_phone') or data.get('phone_number')
            
            if not property_code:
                error_msg = 'Property selection is required'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                else:
                    messages.error(request, error_msg)
                    return HttpResponse('Property required', status=400)
            
            # Updated property mapping - removed Default Property
            # Get property name using database lookup
            property_name = get_project_name_from_form_number(property_code)
            if not property_name:
                property_name = property_code
            
            # Check required fields - UPDATED: Added sex, marital_status, and source
            required_fields = [
                'first_name', 'last_name', 'email',
                'city', 'locality', 'pincode',
                'nationality', 'employment_type', 'configuration',
                'budget', 'construction_status', 'purpose_of_buying',
                'sex', 'marital_status', 'source'
            ]
            
            missing_fields = [field for field in required_fields if not data.get(field)]
            if missing_fields:
                error_msg = f'Required fields missing: {", ".join(missing_fields)}'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                else:
                    return HttpResponse(f'Missing fields: {error_msg}', status=400)
            
            # Validate pincode
            pincode = data.get('pincode', '')
            if len(pincode) != 6 or not pincode.isdigit():
                error_msg = 'Please enter a valid 6-digit pincode'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                else:
                    return HttpResponse('Invalid pincode', status=400)
            
            # Validate phone number (optional but if provided, must be valid)
            phone_number = data.get('phone_number', '').strip()
            if phone_number and (len(phone_number) != 10 or not phone_number.isdigit()):
                error_msg = 'Please enter a valid 10-digit phone number'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                else:
                    return HttpResponse('Invalid phone number', status=400)
            
            # Validate sex and marital_status choices
            valid_sex_choices = ['male', 'female', 'other']
            valid_marital_choices = ['single', 'married', 'divorced', 'widowed', 'other']
            
            sex = data.get('sex', '')
            marital_status = data.get('marital_status', '')
            
            if sex not in valid_sex_choices:
                error_msg = 'Please select a valid sex option'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                else:
                    return HttpResponse('Invalid sex selection', status=400)
            
            if marital_status not in valid_marital_choices:
                error_msg = 'Please select a valid marital status option'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                else:
                    return HttpResponse('Invalid marital status selection', status=400)
            
            # Generate unique customer form number with project prefix
            import random

            # Get the project to use its full prefix
            try:
                project = Project.objects.get(form_number=property_code, is_active=True)
                project_prefix = project.project_prefix
            except Project.DoesNotExist:
                # Fallback: extract prefix from property_code
                if '-' in property_code:
                    # For compound form numbers like "ALT-PHASE1-12345", extract "ALT-PHASE1"
                    parts = property_code.split('-')
                    if len(parts) >= 3 and not parts[1].isdigit():
                        project_prefix = f"{parts[0]}-{parts[1]}"
                    else:
                        project_prefix = parts[0]
                else:
                    project_prefix = property_code

            # Generate unique customer form number using full project prefix
            while True:
                random_number = random.randint(10000, 99999)
                form_number = f"{project_prefix}-{random_number}"

                # Check if this form number already exists
                if not Customer.objects.filter(form_number=form_number).exists():
                    break
            
            # Handle optional date_of_birth field
            date_of_birth = data.get('date_of_birth', '').strip()
            if not date_of_birth:
                date_of_birth = None  # Allow null values as per model definition
                
            # Create customer - UPDATED: Added sex and marital_status fields, made date_of_birth and residential_address optional
            customer = Customer.objects.create(
                form_number=form_number,
                form_date=data.get('form_date', datetime.now().date()),
                first_name=data.get('first_name'),
                middle_name=data.get('middle_name', ''),
                last_name=data.get('last_name'),
                email=data.get('email'),
                phone_number=phone_number if phone_number else None,
                sex=sex,
                marital_status=marital_status,
                date_of_birth=date_of_birth,  # Can be None
                residential_address=data.get('residential_address', ''),
                city=data.get('city'),
                locality=data.get('locality'),
                pincode=pincode,
                nationality=data.get('nationality'),
                employment_type=data.get('employment_type'),
                company_name=data.get('company_name', ''),
                designation=data.get('designation', ''),
                industry=data.get('industry', ''),
                configuration=data.get('configuration'),
                budget=data.get('budget'),
                construction_status=data.get('construction_status'),
                purpose_of_buying=data.get('purpose_of_buying'),
                source_details=data.get('source_details', '')
            )
            
            # Add single source (changed from multiple sources to single source)
            source = request.POST.get('source')
            if source:
                CustomerSource.objects.create(
                    customer=customer,
                    source_type=source
                )
            
            # Add channel partner if selected
            if source == 'channel_partner':
                partner_data = {
                    'company_name': data.get('partner_company_name'),
                    'partner_name': data.get('partner_name'),
                    'mobile_number': data.get('partner_mobile'),
                    'rera_number': data.get('partner_rera')
                }
                
                if all(partner_data.values()):
                    ChannelPartner.objects.create(customer=customer, **partner_data)
            
            # Add referral if selected
            if source == 'referral':
                referral_data = {
                    'referral_name': data.get('referral_name'),
                    'project_name': data.get('referral_project')
                }
                if all(referral_data.values()):
                    Referral.objects.create(customer=customer, **referral_data)

            # Handle additional channel partners (cp_company_name_2, cp_company_name_3, ...)
            if source == 'channel_partner':
                extra_cp_count = int(data.get('additional_cp_count', 0))
                for i in range(2, extra_cp_count + 2):
                    extra_company = data.get(f'cp_company_name_{i}', '').strip()
                    extra_name = data.get(f'cp_partner_name_{i}', '').strip()
                    extra_mobile = data.get(f'cp_mobile_{i}', '').strip()
                    extra_rera = data.get(f'cp_rera_{i}', '').strip()
                    if extra_company and extra_name and extra_mobile:
                        AdditionalChannelPartner.objects.create(
                            customer=customer,
                            company_name=extra_company,
                            partner_name=extra_name,
                            mobile_number=extra_mobile,
                            rera_number=extra_rera,
                        )

            # Mark form as complete
            customer.is_complete = True
            customer.current_step = 4
            customer.save()

            log_action(None, 'submit', 'Customer', customer.id, str(customer), request=request)

            # Store customer data in session for thank you page
            request.session['customer_data'] = {
                'form_number': customer.form_number,
                'customer_name': customer.get_full_name(),
                'email': customer.email,
                'customer_id': customer.id,
                'property_name': property_name,
                'property_code': property_code,
                'phone_number': customer.phone_number or user_phone
            }
            
            # ALWAYS return JSON response for AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Customer enquiry submitted successfully!',
                    'form_number': customer.form_number,
                    'customer_id': customer.id,
                    'property_name': property_name,
                    'redirect_url': '/thank-you/'
                })
            else:
                # For non-AJAX, direct redirect
                from django.http import HttpResponseRedirect
                return HttpResponseRedirect('/thank-you/')
            
    except Exception as e:
        error_msg = f'An error occurred: {str(e)}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': error_msg})
        else:
            return HttpResponse(f'Error: {error_msg}', status=500)


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        
        # Try authentication with username
        user = authenticate(request, username=username, password=password)
        
        # If username fails, try with email
        if user is None:
            try:
                # Check if the username is actually an email
                user_obj = User.objects.get(email=username)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None
        
        if user is not None:
            login(request, user)
            log_action(user, 'login', request=request)
            return redirect(role_redirect(user))
        else:
            messages.error(request, "Invalid username or password")
    return render(request, 'login.html')

def logout_view(request):
    if request.user.is_authenticated:
        log_action(request.user, 'logout', request=request)
    logout(request)
    return redirect('customer_enquiry:login')

@login_required
def dashboard(request):
    """Enhanced dashboard with filtering capabilities"""
    # Get all customers with related data
    customers = Customer.objects.select_related('sales_assessment').prefetch_related(
        'sources', 'booking_applications', 'additional_channel_partners'
    ).order_by('-created_at')

    # Apply filters if provided (for AJAX requests)
    search = request.GET.get('search', '')
    property_filter = request.GET.get('property', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    assessment_filter = request.GET.get('assessment', '')
    booking_filter = request.GET.get('booking', '')
    
    if search:
        customers = customers.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(form_number__icontains=search) |
            Q(city__icontains=search) |
            Q(phone_number__icontains=search)  # ADDED: Phone number search
        )
    
    if property_filter:
        customers = customers.filter(form_number__startswith=property_filter)
    
    if date_from:
        customers = customers.filter(created_at__date__gte=date_from)
    
    if date_to:
        customers = customers.filter(created_at__date__lte=date_to)
    
    if assessment_filter == 'completed':
        customers = customers.filter(sales_assessment__isnull=False)
    elif assessment_filter == 'pending':
        customers = customers.filter(sales_assessment__isnull=True)
    
    if booking_filter == 'completed':
        customers = customers.filter(booking_applications__isnull=False)
    elif booking_filter == 'pending':
        customers = customers.filter(booking_applications__isnull=True)
    
    # Get all active projects for JavaScript property mapping
    projects = Project.objects.active_projects()

    # Create a dictionary for JavaScript consumption
    projects_data = {}
    for project in projects:
        projects_data[project.project_prefix.upper()] = {
            'code': project.project_prefix,
            'name': project.project_name
        }

    import json
    projects_data_json = json.dumps(projects_data)

    return render(request, 'dashboard.html', {
        'customers': customers,
        'projects_data_json': projects_data_json,
        'active_projects': projects
    })

@login_required
@csrf_exempt
def export_leads(request):
    """Export filtered leads to Excel - Updated with phone number, removed budget/config"""
    if request.method == 'POST':
        # Get filter parameters
        search = request.POST.get('search', '')
        property_filter = request.POST.get('property', '')
        date_from = request.POST.get('date_from', '')
        date_to = request.POST.get('date_to', '')
        assessment_filter = request.POST.get('assessment', '')
        booking_filter = request.POST.get('booking', '')
        form_numbers_str = request.POST.get('form_numbers', '')

        # Get filtered customers
        customers = Customer.objects.select_related('sales_assessment').prefetch_related(
            'sources', 'booking_applications'
        ).order_by('-created_at')

        # If specific form numbers are provided (e.g. from closing manager), restrict to those
        if form_numbers_str:
            form_numbers_list = [fn.strip() for fn in form_numbers_str.split(',') if fn.strip()]
            if form_numbers_list:
                customers = customers.filter(form_number__in=form_numbers_list)

        # Apply filters
        if search:
            customers = customers.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(form_number__icontains=search) |
                Q(city__icontains=search) |
                Q(phone_number__icontains=search)  # ADDED: Phone search
            )
        
        if property_filter:
            customers = customers.filter(form_number__startswith=property_filter)
        
        if date_from:
            customers = customers.filter(created_at__date__gte=date_from)
        
        if date_to:
            customers = customers.filter(created_at__date__lte=date_to)
        
        if assessment_filter == 'completed':
            customers = customers.filter(sales_assessment__isnull=False)
        elif assessment_filter == 'pending':
            customers = customers.filter(sales_assessment__isnull=True)
        
        if booking_filter == 'completed':
            customers = customers.filter(booking_applications__isnull=False)
        elif booking_filter == 'pending':
            customers = customers.filter(booking_applications__isnull=True)
        
        # Prepare data for Excel
        data = []
        for customer in customers:
            # Get property name using database lookup
            property_name = get_project_name_from_form_number(customer.form_number)
            if not property_name:
                property_name = 'Unknown Property'
            
            # Get sources
            sources = ', '.join([source.get_source_type_display() for source in customer.sources.all()])
            
            # Get channel partner information
            channel_partner_name = ''
            try:
                if hasattr(customer, 'channel_partner') and customer.channel_partner:
                    channel_partner_name = customer.channel_partner.partner_name
            except (ChannelPartner.DoesNotExist, AttributeError):
                channel_partner_name = ''
            
            # Assessment status
            assessment_status = 'Completed' if hasattr(customer, 'sales_assessment') and customer.sales_assessment else 'Pending'
            
            # Booking status
            booking_status = 'Completed' if customer.booking_applications.exists() else 'Pending'
            
            data.append({
                'Form Number': customer.form_number,
                'Property': property_name,
                'First Name': customer.first_name,
                'Middle Name': customer.middle_name or '',
                'Last Name': customer.last_name,
                'Email': customer.email,
                'Phone Number': customer.phone_number or 'Not Provided',  # ADDED
                'Date of Birth': customer.date_of_birth.strftime('%Y-%m-%d') if customer.date_of_birth else '',
                'City': customer.city,
                'Locality': customer.locality,
                'Pincode': customer.pincode,
                'Residential Address': customer.residential_address,
                'Nationality': customer.get_nationality_display(),
                'Employment Type': customer.get_employment_type_display(),
                'Company Name': customer.company_name or '',
                'Designation': customer.designation or '',
                'Industry': customer.industry or '',
                'Configuration': customer.configuration,
                'Budget': customer.budget,
                'Construction Status': customer.get_construction_status_display(),
                'Purpose of Buying': customer.get_purpose_of_buying_display(),
                'Lead Sources': sources,
                'Channel Partner Name': channel_partner_name or 'Not Applicable',
                'Source Details': customer.source_details or '',
                'Assessment Status': assessment_status,
                'Booking Status': booking_status,
                'Created Date': customer.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Leads Export', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Leads Export']
            
            # Auto-adjust column widths
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        # Create response
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        property_suffix = f'_{property_filter}' if property_filter else '_All'
        filename = f'leads_export{property_suffix}_{timestamp}.xlsx'
        
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        log_action(request.user, 'export', 'Customer', None,
                   f'Exported {len(data)} leads — {filename}', request=request)
        return response

    return HttpResponse('Method not allowed', status=405)


def edit_customer(request, pk):
    """Edit or view customer information based on user role"""
    customer = get_object_or_404(Customer, pk=pk)
    user_role = get_user_role(request.user)
    can_edit = user_role in ('admin', 'super_admin', 'closing_manager')

    if request.method == 'POST' and can_edit:
        try:
            with transaction.atomic():
                customer.first_name = request.POST.get('first_name', customer.first_name)
                customer.middle_name = request.POST.get('middle_name', '')
                customer.last_name = request.POST.get('last_name', customer.last_name)
                customer.email = request.POST.get('email', customer.email)

                phone_number = request.POST.get('phone_number', '').strip()
                if phone_number and (len(phone_number) != 10 or not phone_number.isdigit()):
                    messages.error(request, 'Please enter a valid 10-digit phone number')
                    return redirect('customer_enquiry:edit_customer', pk=pk)
                customer.phone_number = phone_number if phone_number else customer.phone_number

                sex = request.POST.get('sex', '')
                if sex in ('male', 'female', 'other'):
                    customer.sex = sex

                marital_status = request.POST.get('marital_status', '')
                if marital_status in ('single', 'married', 'divorced', 'widowed', 'other'):
                    customer.marital_status = marital_status

                dob = request.POST.get('date_of_birth', '').strip()
                if dob:
                    customer.date_of_birth = dob

                customer.residential_address = request.POST.get('residential_address', customer.residential_address)
                customer.city = request.POST.get('city', customer.city)
                customer.locality = request.POST.get('locality', customer.locality)

                pincode = request.POST.get('pincode', '').strip()
                if pincode:
                    if len(pincode) != 6 or not pincode.isdigit():
                        messages.error(request, 'Please enter a valid 6-digit pincode')
                        return redirect('customer_enquiry:edit_customer', pk=pk)
                    customer.pincode = pincode

                customer.nationality = request.POST.get('nationality', customer.nationality)
                customer.employment_type = request.POST.get('employment_type', customer.employment_type)
                customer.company_name = request.POST.get('company_name', customer.company_name)
                customer.designation = request.POST.get('designation', customer.designation)
                customer.industry = request.POST.get('industry', customer.industry)
                customer.configuration = request.POST.get('configuration', customer.configuration)
                customer.budget = request.POST.get('budget', customer.budget)
                customer.construction_status = request.POST.get('construction_status', customer.construction_status)
                customer.purpose_of_buying = request.POST.get('purpose_of_buying', customer.purpose_of_buying)
                customer.source_details = request.POST.get('source_details', customer.source_details)
                customer.save()

                # Update sources
                customer.sources.all().delete()
                for source in request.POST.getlist('sources'):
                    CustomerSource.objects.create(customer=customer, source_type=source)

                # Update channel partner
                try:
                    customer.channel_partner.delete()
                except ChannelPartner.DoesNotExist:
                    pass
                if 'channel_partner' in request.POST.getlist('sources'):
                    cp_company = request.POST.get('partner_company_name', '')
                    cp_name = request.POST.get('partner_name', '')
                    cp_mobile = request.POST.get('partner_mobile', '')
                    cp_rera = request.POST.get('partner_rera', '')
                    if cp_name or cp_company:
                        ChannelPartner.objects.create(
                            customer=customer,
                            company_name=cp_company,
                            partner_name=cp_name,
                            mobile_number=cp_mobile,
                            rera_number=cp_rera
                        )

                # Update referral
                try:
                    customer.referral.delete()
                except Referral.DoesNotExist:
                    pass
                if 'referral' in request.POST.getlist('sources'):
                    ref_name = request.POST.get('referral_name', '')
                    ref_project = request.POST.get('referral_project', '')
                    if ref_name:
                        Referral.objects.create(
                            customer=customer,
                            referral_name=ref_name,
                            project_name=ref_project
                        )

                log_action(request.user, 'edit', 'Customer', customer.id, str(customer), request=request)
                messages.success(request, 'Customer information updated successfully!')
                return redirect('customer_enquiry:dashboard')

        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
            return redirect('customer_enquiry:edit_customer', pk=pk)

    # GET — prepare context
    current_sources = list(customer.sources.values_list('source_type', flat=True))

    try:
        channel_partner = customer.channel_partner
    except ChannelPartner.DoesNotExist:
        channel_partner = None

    additional_channel_partners = customer.additional_channel_partners.all()

    try:
        referral = customer.referral
    except Referral.DoesNotExist:
        referral = None

    project_data = None
    if customer.form_number:
        try:
            form_parts = customer.form_number.split('-')
            found_project = None
            if len(form_parts) >= 3:
                compound_prefix = f"{form_parts[0]}-{form_parts[1]}"
                found_project = Project.objects.filter(project_prefix__iexact=compound_prefix, is_active=True).first()
                if not found_project:
                    found_project = Project.objects.filter(project_prefix__iexact=form_parts[0], is_active=True).first()
            else:
                prefix = form_parts[0] if len(form_parts) > 1 else customer.form_number[:3]
                found_project = Project.objects.filter(project_prefix__iexact=prefix, is_active=True).first()
            if found_project:
                project_data = {
                    'code': found_project.form_number,
                    'name': found_project.project_name,
                    'logo': str(found_project.project_logo) if found_project.project_logo else None,
                }
        except Exception:
            project_data = None

    cp_master = ChannelPartnerMaster.objects.filter(is_active=True).values(
        'id', 'company_name', 'partner_name', 'mobile_number', 'rera_number'
    )
    cp_master_json = json.dumps(list(cp_master))

    context = {
        'customer': customer,
        'current_sources': current_sources,
        'channel_partner': channel_partner,
        'additional_channel_partners': additional_channel_partners,
        'referral': referral,
        'view_only': not can_edit,
        'selected_property': project_data,
        'cp_master_json': cp_master_json,
    }
    return render(request, 'edit_customer.html', context)


@login_required
def remove_additional_cp(request, cp_id):
    """Remove an additional channel partner (admin/super_admin/closing_manager only)."""
    from django.http import JsonResponse
    role = get_user_role(request.user)
    if role not in ('admin', 'super_admin', 'closing_manager'):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required.'}, status=405)

    cp = get_object_or_404(AdditionalChannelPartner, pk=cp_id)
    customer_pk = cp.customer_id
    cp_repr = f"{cp.company_name} — {cp.partner_name}" if cp.company_name else f"CP #{cp_id}"
    cp.delete()
    log_action(request.user, 'cp_remove', 'AdditionalChannelPartner', cp_id,
               f'Additional CP removed for customer #{customer_pk}: {cp_repr}', request=request)
    return JsonResponse({'success': True, 'customer_pk': customer_pk})


@login_required
def add_additional_cp(request, customer_id):
    """Add a new additional channel partner to a customer (admin/super_admin/closing_manager only)."""
    from django.http import JsonResponse
    role = get_user_role(request.user)
    if role not in ('admin', 'super_admin', 'closing_manager'):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required.'}, status=405)

    customer = get_object_or_404(Customer, pk=customer_id)
    company_name = request.POST.get('company_name', '').strip()
    partner_name = request.POST.get('partner_name', '').strip()
    mobile_number = request.POST.get('mobile_number', '').strip()
    rera_number = request.POST.get('rera_number', '').strip()

    if not company_name or not partner_name or not mobile_number:
        return JsonResponse({'success': False, 'error': 'Company name, partner name, and mobile are required.'})
    if len(mobile_number) != 10 or not mobile_number.isdigit():
        return JsonResponse({'success': False, 'error': 'Mobile number must be exactly 10 digits.'})

    acp = AdditionalChannelPartner.objects.create(
        customer=customer,
        company_name=company_name,
        partner_name=partner_name,
        mobile_number=mobile_number,
        rera_number=rera_number,
    )
    log_action(request.user, 'cp_add', 'AdditionalChannelPartner', acp.id,
               f'{company_name} — {partner_name} added to {customer.form_number}', request=request)
    return JsonResponse({
        'success': True,
        'acp_id': acp.pk,
        'company_name': company_name,
        'partner_name': partner_name,
        'mobile_number': mobile_number,
        'rera_number': rera_number,
    })


# def edit_customer(request, pk):
#     """Edit customer with phone number, sex, and marital status support"""
#     customer = get_object_or_404(Customer, pk=pk)

#     if request.method == 'POST':
#         try:
#             with transaction.atomic():
#                 # Update main customer fields
#                 customer.first_name = request.POST.get('first_name')
#                 customer.middle_name = request.POST.get('middle_name', '')
#                 customer.last_name = request.POST.get('last_name')
#                 customer.email = request.POST.get('email')
                
#                 # ADDED: Phone number handling
#                 phone_number = request.POST.get('phone_number', '').strip()
#                 if phone_number and (len(phone_number) != 10 or not phone_number.isdigit()):
#                     messages.error(request, 'Please enter a valid 10-digit phone number')
#                     return redirect('customer_enquiry:edit_customer', pk=pk)
#                 customer.phone_number = phone_number if phone_number else None
                
#                 # ADDED: Sex and Marital Status handling
#                 sex = request.POST.get('sex')
#                 marital_status = request.POST.get('marital_status')
                
#                 if sex:
#                     valid_sex_choices = ['male', 'female', 'other']
#                     if sex in valid_sex_choices:
#                         customer.sex = sex
#                     else:
#                         messages.error(request, 'Please select a valid sex option')
#                         return redirect('customer_enquiry:edit_customer', pk=pk)
                
#                 if marital_status:
#                     valid_marital_choices = ['single', 'married', 'divorced', 'widowed', 'other']
#                     if marital_status in valid_marital_choices:
#                         customer.marital_status = marital_status
#                     else:
#                         messages.error(request, 'Please select a valid marital status option')
#                         return redirect('customer_enquiry:edit_customer', pk=pk)
                
#                 # Handle optional date_of_birth field in edit
#                 date_of_birth = request.POST.get('date_of_birth', '').strip()
#                 if not date_of_birth:
#                     # If no date provided, keep existing value or use placeholder
#                     if customer.date_of_birth:
#                         date_of_birth = customer.date_of_birth  # Keep existing value
#                     else:
#                         date_of_birth = '1900-01-01'  # Placeholder date
                
#                 customer.date_of_birth = date_of_birth  # Handle empty dates
#                 customer.residential_address = request.POST.get('residential_address', '')  # OPTIONAL - empty string if not provided
#                 customer.city = request.POST.get('city')
#                 customer.locality = request.POST.get('locality')
#                 customer.pincode = request.POST.get('pincode')
#                 customer.nationality = request.POST.get('nationality')
#                 customer.employment_type = request.POST.get('employment_type')
#                 customer.company_name = request.POST.get('company_name', '')
#                 customer.designation = request.POST.get('designation', '')
#                 customer.industry = request.POST.get('industry', '')
#                 customer.configuration = request.POST.get('configuration')
#                 customer.budget = request.POST.get('budget')
#                 customer.construction_status = request.POST.get('construction_status')
#                 customer.purpose_of_buying = request.POST.get('purpose_of_buying')
#                 customer.source_details = request.POST.get('source_details', '')

#                 # Validate pincode
#                 pincode = request.POST.get('pincode', '')
#                 if len(pincode) != 6 or not pincode.isdigit():
#                     messages.error(request, 'Please enter a valid 6-digit pincode')
#                     return redirect('customer_enquiry:edit_customer', pk=pk)

#                 customer.save()

#                 # Update Sources (existing code)
#                 customer.sources.all().delete()
#                 sources = request.POST.getlist('sources')
#                 for source in sources:
#                     CustomerSource.objects.create(
#                         customer=customer,
#                         source_type=source
#                     )

#                 # Update Channel Partner (existing code)
#                 if hasattr(customer, 'channel_partner'):
#                     customer.channel_partner.delete()
                
#                 if 'channel_partner' in sources:
#                     partner_data = {
#                         'company_name': request.POST.get('partner_company_name', ''),
#                         'partner_name': request.POST.get('partner_name', ''),
#                         'mobile_number': request.POST.get('partner_mobile', ''),
#                         'rera_number': request.POST.get('partner_rera', '')
#                     }
                    
#                     if all(partner_data.values()):
#                         ChannelPartner.objects.create(customer=customer, **partner_data)

#                 # Update Referral (existing code)
#                 if hasattr(customer, 'referral'):
#                     customer.referral.delete()
                
#                 if 'referral' in sources:
#                     referral_data = {
#                         'referral_name': request.POST.get('referral_name', ''),
#                         'project_name': request.POST.get('referral_project', '')
#                     }
                    
#                     if all(referral_data.values()):
#                         Referral.objects.create(customer=customer, **referral_data)

#                 messages.success(request, 'Customer information updated successfully!')
#                 return redirect('customer_enquiry:dashboard')

#         except Exception as e:
#             messages.error(request, f'An error occurred: {str(e)}')
#             return redirect('customer_enquiry:edit_customer', pk=pk)

#     # GET request - prepare context for template
#     else:
#         # Get current sources
#         current_sources = list(customer.sources.values_list('source_type', flat=True))
        
#         # Get channel partner if exists
#         try:
#             channel_partner = customer.channel_partner
#         except ChannelPartner.DoesNotExist:
#             channel_partner = None
        
#         # Get referral if exists
#         try:
#             referral = customer.referral
#         except Referral.DoesNotExist:
#             referral = None

#         context = {
#             'customer': customer,
#             'current_sources': current_sources,
#             'channel_partner': channel_partner,
#             'referral': referral,
#         }
        
#         return render(request, 'edit_customer.html', context)

@login_required
def internal_sales_assessment(request, customer_id):
    """Create or edit internal sales assessment for a customer"""
    customer = get_object_or_404(Customer, pk=customer_id)
    
    # Try to get existing assessment or create new one
    try:
        assessment = customer.sales_assessment
    except InternalSalesAssessment.DoesNotExist:
        assessment = None
        
    # If creating new assessment, auto-populate from customer data
    if not assessment:
        # Create a new assessment instance with auto-populated data
        assessment = InternalSalesAssessment()
        assessment.customer = customer
        
        # Auto-populate fields from customer enquiry data
        print(f"Auto-populating assessment for customer: {customer.get_full_name()}")
        
        # 1. Map customer gender to assessment format
        if customer.sex:
            if customer.sex == 'male':
                assessment.customer_gender = 'male'
            elif customer.sex == 'female':
                assessment.customer_gender = 'female'
            else:
                assessment.customer_gender = 'family'  # Default for other cases
            print(f"Mapped gender: {customer.sex} -> {assessment.customer_gender}")
            
        # 2. Map current residence configuration (if they mentioned current living situation)
        # For now, we'll use their desired configuration as a starting point
        if customer.configuration:
            assessment.current_residence_config = customer.configuration
            print(f"Mapped configuration: {customer.configuration}")
            
        # 3. Auto-populate area looking based on customer's requirements
        area_description = []
        if customer.configuration:
            area_description.append(f"Looking for {customer.get_configuration_display()}")
        if customer.budget:
            area_description.append(f"Budget: {customer.get_budget_display()}")
        if customer.construction_status:
            area_description.append(f"Status: {customer.get_construction_status_display()}")
        
        assessment.area_looking = ". ".join(area_description) if area_description else "Customer requirements to be discussed"
        print(f"Generated area_looking: {assessment.area_looking}")
            
        # 4. Set default ethnicity based on nationality
        if customer.nationality == 'indian':
            assessment.ethnicity = 'hindu'  # Default assumption, can be changed by user
        else:
            assessment.ethnicity = 'other'
        print(f"Mapped ethnicity based on nationality {customer.nationality}: {assessment.ethnicity}")
        
        # 5. Set default family size (can be inferred from marital status)
        if customer.marital_status == 'married':
            assessment.family_size = '2'  # Default for married couples
        elif customer.marital_status == 'single':
            assessment.family_size = '1'  # Default for single
        else:
            assessment.family_size = '2'  # Default assumption
        print(f"Mapped family size based on marital status {customer.marital_status}: {assessment.family_size}")
        
        print("Auto-population completed")

    user_role = get_user_role(request.user)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Get or create assessment
                if assessment:
                    assessment_obj = assessment
                else:
                    assessment_obj = InternalSalesAssessment(customer=customer)

                # Step 1 fields — GRE can fill these
                assessment_obj.sourcing_manager = request.POST.get('sourcing_manager', '')
                assessment_obj.sales_manager = request.POST.get('sales_manager', '')
                assessment_obj.customer_gender = request.POST.get('customer_gender', '')
                assessment_obj.facilitated_by_pre_sales = request.POST.get('facilitated_by_pre_sales', 'false') == 'true'
                assessment_obj.executive_name = request.POST.get('executive_name', '')

                # Auto-assign to managers based on dropdown selection
                sourcing_id = request.POST.get('sourcing_manager_id')
                closing_id = request.POST.get('sales_manager_id')
                sourcing_user = User.objects.filter(id=sourcing_id).first() if sourcing_id else None
                closing_user = User.objects.filter(id=closing_id).first() if closing_id else None

                if sourcing_user or closing_user:
                    assignment_obj, _ = CustomerAssignment.objects.get_or_create(
                        customer=customer,
                        defaults={'assigned_by': request.user}
                    )
                    if sourcing_user:
                        assignment_obj.sourcing_manager = sourcing_user
                    if closing_user:
                        assignment_obj.closing_manager = closing_user
                    assignment_obj.assigned_by = request.user
                    assignment_obj.save()

                    log_action(
                        request.user, 'assign', 'Customer', customer.id,
                        str(customer),
                        changes=json.dumps({
                            'sourcing_manager': sourcing_user.get_full_name() if sourcing_user else None,
                            'closing_manager': closing_user.get_full_name() if closing_user else None,
                        }),
                        request=request
                    )

                # Steps 2-5 — only non-GRE roles can update these
                if user_role != 'gre':
                    assessment_obj.lead_classification = request.POST.get('lead_classification', '')
                    assessment_obj.reason_for_lost = request.POST.get('reason_for_lost', '')
                    assessment_obj.customer_classification = request.POST.get('customer_classification', '')
                    assessment_obj.reason_for_closed = request.POST.get('reason_for_closed', '')
                    assessment_obj.current_residence_config = request.POST.get('current_residence_config', '')
                    assessment_obj.current_residence_ownership = request.POST.get('current_residence_ownership', '')
                    assessment_obj.plot = request.POST.get('plot', '')
                    assessment_obj.family_size = request.POST.get('family_size', '')
                    assessment_obj.area_looking = request.POST.get('area_looking', '')
                    assessment_obj.desired_flat_area = request.POST.get('desired_flat_area', '')
                    assessment_obj.source_of_funding = request.POST.get('source_of_funding', '')
                    assessment_obj.ethnicity = request.POST.get('ethnicity', '')
                    assessment_obj.other_projects_considered = request.POST.get('other_projects_considered', '')
                    assessment_obj.sales_manager_remarks = request.POST.get('sales_manager_remarks', '')

                assessment_obj.save()
                log_action(request.user, 'assessment', 'InternalSalesAssessment', assessment_obj.id,
                           f"Assessment for {customer.get_full_name()} ({customer.form_number})",
                           changes=json.dumps({'action': 'updated' if assessment else 'created',
                                               'lead_classification': assessment_obj.lead_classification}),
                           request=request)

                if assessment:
                    messages.success(request, 'Internal sales assessment updated successfully!')
                else:
                    messages.success(request, 'Internal sales assessment created successfully!')
                
                return redirect('customer_enquiry:dashboard')

        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
            return redirect('customer_enquiry:internal_sales_assessment', customer_id=customer_id)

    # GET request
    # Get project data from customer's form number prefix for logo display
    project_data = None
    if customer.form_number:
        try:
            # Extract prefix from form number with better matching logic
            form_parts = customer.form_number.split('-')

            # Try different prefix matching strategies
            if len(form_parts) >= 3:
                # For form numbers like "ALT-phase4-35509", try "ALT-phase4" first
                compound_prefix = f"{form_parts[0]}-{form_parts[1]}"
                project = Project.objects.filter(
                    project_prefix__iexact=compound_prefix,
                    is_active=True
                ).first()

                if project:
                    project_data = project
                else:
                    # Fall back to just the first part "ALT"
                    simple_prefix = form_parts[0]
                    project = Project.objects.filter(
                        project_prefix__iexact=simple_prefix,
                        is_active=True
                    ).first()
                    if project:
                        project_data = project
            else:
                # For simple form numbers like "MED-49988"
                prefix = form_parts[0] if len(form_parts) > 1 else customer.form_number[:3]
                project = Project.objects.filter(
                    project_prefix__iexact=prefix,
                    is_active=True
                ).first()
                if project:
                    project_data = project

        except Exception as e:
            # If all else fails, try the old logic
            prefix = customer.form_number.split('-')[0] if '-' in customer.form_number else customer.form_number[:3]
            try:
                project = Project.objects.filter(
                    project_prefix__icontains=prefix,
                    is_active=True
                ).first()
                if project:
                    project_data = project
            except Exception:
                project_data = None

    # Get managers for dropdown
    sourcing_managers = User.objects.filter(profile__role='sourcing_manager').order_by('first_name')
    closing_managers = User.objects.filter(profile__role='closing_manager').order_by('first_name')

    # Get existing assignment if any
    try:
        assignment = customer.assignment
    except CustomerAssignment.DoesNotExist:
        assignment = None

    context = {
        'customer': customer,
        'assessment': assessment,
        'selected_property': project_data,
        'user_role': user_role,
        'gre_only': user_role == 'gre',
        'sourcing_managers': sourcing_managers,
        'closing_managers': closing_managers,
        'assignment': assignment,
    }

    return render(request, 'internal_sales_assessment.html', context)

# BOOKING FORM VIEWS
@login_required
def booking_form_view(request, customer_id):
    """
    Booking form view with pre-filled customer data and persistence support
    """
    customer = get_object_or_404(Customer, pk=customer_id)
    
    if request.method == 'GET':
        # Check if customer already has a booking application (for editing)
        existing_booking = BookingApplication.objects.filter(customer=customer).first()
        
        if existing_booking:
            # Pre-fill with existing booking data
            prefilled_data = prepare_prefilled_data_from_booking(customer, existing_booking)
        else:
            # Pre-fill with customer data only
            prefilled_data = prepare_prefilled_data(customer)
        
        # Get channel partner if exists
        try:
            channel_partner = customer.channel_partner
        except (ChannelPartner.DoesNotExist, AttributeError):
            channel_partner = None
        
        # Get referral if exists
        try:
            referral = customer.referral
        except (Referral.DoesNotExist, AttributeError):
            referral = None

        # Get project data for terms and conditions
        project_data = None
        try:
            # Extract prefix from customer's form number
            if '-' in customer.form_number:
                parts = customer.form_number.split('-')
                if len(parts) >= 3 and not parts[1].isdigit():
                    prefix = f"{parts[0]}-{parts[1]}".upper()
                else:
                    prefix = parts[0].upper()
            else:
                prefix = customer.form_number[:3].upper()

            # Get project from database
            project = Project.objects.filter(
                project_prefix__iexact=prefix,
                is_active=True
            ).first()

            if project:
                project_data = {
                    'name': project.project_name,
                    'site_name': project.site_name,
                    'company_name': project.company_name,
                    'maharera_no': project.maharera_no,
                    'address': project.address,
                    'qr_code': project.project_qr_code.url if project.project_qr_code else None
                }

        except Exception as e:
            logger.error(f"Error getting project data for customer {customer.id}: {e}")

        context = {
            'customer': customer,
            'prefilled_data': prefilled_data,
            'existing_booking': existing_booking,
            'existing_applicants': prefilled_data.get('existing_applicants', []),
            'channel_partner': channel_partner,
            'referral': referral,
            'project_data': project_data,
        }
        
        return render(request, 'booking_form.html', context)
    
    elif request.method == 'POST':
        # Handle form submission
        return handle_booking_submission(request, customer)

def get_project_name_from_form_number(form_number):
    """
    Get project name from form number using database lookup with exact prefix matching
    """
    if not form_number:
        return ''

    try:
        # Extract full prefix from customer form number
        if '-' in form_number:
            # For form numbers like "ALT-PHASE1-98141", we need to extract "ALT-PHASE1"
            # For form numbers like "ALT-12345", we need to extract "ALT"
            parts = form_number.split('-')

            # If there are 3 parts (like ALT-PHASE1-98141), take first two as prefix
            if len(parts) >= 3 and not parts[1].isdigit():
                prefix = f"{parts[0]}-{parts[1]}".upper()
            else:
                # Otherwise, take first part as prefix (like ALT-12345)
                prefix = parts[0].upper()
        else:
            # Handle old format or extract first 3 characters
            prefix = form_number[:3].upper()

        # First try exact prefix match
        project = Project.objects.filter(
            project_prefix__iexact=prefix,
            is_active=True
        ).first()

        if project:
            return project.project_name

        # If no exact match and we have a compound prefix, try just the first part
        if '-' in prefix:
            simple_prefix = prefix.split('-')[0]
            project = Project.objects.filter(
                project_prefix__iexact=simple_prefix,
                is_active=True
            ).first()

            if project:
                return project.project_name

    except Exception as e:
        logger.error(f"Error getting project name from form number {form_number}: {e}")

    return ''


def prepare_prefilled_data(customer):
    """
    Customer ke existing data se form pre-fill karo
    """
    # Try to get project name from customer's form number (primary source)
    project_name = get_project_name_from_form_number(customer.form_number)
    
    # If form number doesn't give us a project name, try other sources
    if not project_name:
        # Try to get from customer referral (OneToOneField)
        try:
            if hasattr(customer, 'referral') and customer.referral:
                project_name = customer.referral.project_name
        except Exception:
            pass
        
        # Try to get from existing bookings
        if not project_name:
            try:
                existing_booking = customer.booking_applications.first() if hasattr(customer, 'booking_applications') else None
                if existing_booking and existing_booking.project_name and existing_booking.project_name != 'Default Project':
                    project_name = existing_booking.project_name
            except Exception:
                pass
    
    prefilled_data = {
        # Project details
        'project_name': project_name,
        
        # 1st Applicant - Customer ki details se auto-fill
        'applicant_1_title': get_title_from_customer(customer),
        'applicant_1_first_name': customer.first_name,
        'applicant_1_middle_name': customer.middle_name or '',
        'applicant_1_last_name': customer.last_name,
        'applicant_1_email': customer.email,
        'applicant_1_mobile': customer.phone_number or '',
        'applicant_1_residential_address': customer.residential_address,
        'applicant_1_city': customer.city,
        'applicant_1_pin': customer.pincode,
        'applicant_1_state': get_state_from_city(customer.city),  # Helper function
        'applicant_1_country': 'India',
        
        # Residential status mapping
        'applicant_1_residential_status': map_nationality_to_residential_status(customer.nationality),
        
        # Employment details from customer
        'applicant_1_employment_type': map_employment_type(customer.employment_type),
        'applicant_1_company_name': customer.company_name or '',
        'applicant_1_profession': customer.designation or '',
    }
    
    return prefilled_data

def prepare_prefilled_data_from_booking(customer, booking):
    """
    Existing booking application se form pre-fill karo
    """
    prefilled_data = prepare_prefilled_data(customer)  # Start with customer data
    
    # Override with booking application data
    prefilled_data.update({
        'project_name': booking.project_name,
        'flat_number': booking.flat_number,
        'floor': booking.floor,
        'rera_carpet_area': booking.rera_carpet_area,
        'exclusive_deck_balcony': booking.exclusive_deck_balcony,
        'car_parking_count': booking.car_parking_count,
        'total_purchase_price': booking.total_purchase_price,
        'total_purchase_price_words': booking.total_purchase_price_words,
        'application_money_amount': booking.application_money_amount,
        'application_money_words': booking.application_money_words,
        'gst_amount': booking.gst_amount,
        'gst_words': booking.gst_words,
        'cheque_dd_no': booking.cheque_dd_no,
        'instrument_date': booking.instrument_date,
        'drawn_on': booking.drawn_on,
        'gst_cheque_dd_no': booking.gst_cheque_dd_no,
        'gst_instrument_date': booking.gst_instrument_date,
        'gst_drawn_on': booking.gst_drawn_on,
        'referral_customer_name': booking.referral_customer_name,
        'referral_project': booking.referral_project,
        'referral_flat_no': booking.referral_flat_no,
        'sales_manager_name': booking.sales_manager_name,
        'sourcing_manager_name': booking.sourcing_manager_name,
        'source_direct': booking.source_direct,
        'source_direct_specify': booking.source_direct_specify,
    })
    
    # Add applicant data from booking
    applicants = booking.applicants.all().order_by('applicant_order')
    
    # Track which applicants exist for JavaScript to show them
    existing_applicants = []
    
    for applicant in applicants:
        prefix = f'applicant_{applicant.applicant_order}_'
        existing_applicants.append(applicant.applicant_order)
        
        prefilled_data.update({
            f'{prefix}title': applicant.title or '',
            f'{prefix}first_name': applicant.first_name or '',
            f'{prefix}middle_name': applicant.middle_name or '',
            f'{prefix}last_name': applicant.last_name or '',
            f'{prefix}mobile': applicant.mobile or '',
            f'{prefix}email': applicant.email or '',
            f'{prefix}residential_address': applicant.residential_address or '',
            f'{prefix}correspondence_address': applicant.correspondence_address or '',
            f'{prefix}city': applicant.city or '',
            f'{prefix}pin': applicant.pin or '',
            f'{prefix}state': applicant.state or '',
            f'{prefix}country': applicant.country or 'India',
            f'{prefix}residential_status': applicant.residential_status or '',
            f'{prefix}employment_type': applicant.employment_type or '',
            f'{prefix}company_name': applicant.company_name or '',
            f'{prefix}profession': applicant.profession or '',
            f'{prefix}contact_residence': applicant.contact_residence or '',
            f'{prefix}contact_office': applicant.contact_office or '',
            f'{prefix}marital_status': applicant.marital_status or '',
            f'{prefix}sex': applicant.sex or '',
        })
        
        # Handle date fields safely
        if applicant.date_of_birth:
            dob_str = applicant.date_of_birth.strftime('%d%m%Y')
            for i, char in enumerate(dob_str, 1):
                if i <= 2:
                    prefilled_data[f'{prefix}dob_d{i}'] = char
                elif i <= 4:
                    prefilled_data[f'{prefix}dob_m{i-2}'] = char
                else:
                    prefilled_data[f'{prefix}dob_y{i-4}'] = char
        
        if applicant.anniversary_date:
            ann_str = applicant.anniversary_date.strftime('%d%m%Y')
            for i, char in enumerate(ann_str, 1):
                if i <= 2:
                    prefilled_data[f'{prefix}anniversary_d{i}'] = char
                elif i <= 4:
                    prefilled_data[f'{prefix}anniversary_m{i-2}'] = char
                else:
                    prefilled_data[f'{prefix}anniversary_y{i-4}'] = char
        
        # Handle PAN and Aadhaar numbers
        if applicant.pan_no:
            for i, char in enumerate(applicant.pan_no, 1):
                if i <= 10:
                    prefilled_data[f'{prefix}pan_{i}'] = char
        
        if applicant.aadhar_no:
            for i, char in enumerate(applicant.aadhar_no, 1):
                if i <= 12:
                    prefilled_data[f'{prefix}aadhar_{i}'] = char
                    
        # Handle checkboxes for marital status, sex, etc.
        prefilled_data[f'{prefix}marital_status'] = applicant.marital_status
        prefilled_data[f'{prefix}sex'] = applicant.sex
    
    # Add count of existing applicants to show them in the form
    prefilled_data['existing_applicant_count'] = len(existing_applicants)
    prefilled_data['existing_applicants'] = existing_applicants
    
    # Add channel partner data if exists
    if hasattr(booking, 'channel_partner') and booking.channel_partner:
        cp = booking.channel_partner
        prefilled_data.update({
            'channel_partner_name': cp.name,
            'channel_partner_rera': cp.maharera_registration,
            'channel_partner_mobile': cp.mobile,
            'channel_partner_email': cp.email,
        })
    
    return prefilled_data

def get_title_from_customer(customer):
    """
    Customer name se title guess karo (basic logic)
    """
    first_name = customer.first_name.lower()
    # Basic logic - aap improve kar sakte ho
    if first_name.endswith('a') or first_name in ['priya', 'rani', 'devi']:
        return 'Ms'
    return 'Mr'

def map_nationality_to_residential_status(nationality):
    """
    Customer nationality ko booking form residential status mein convert karo
    """
    mapping = {
        'indian': 'indian',
        'nri': 'nri', 
        'pio': 'pio',
        'oci': 'oci'
    }
    return mapping.get(nationality, 'indian')

def map_employment_type(employment_type):
    """
    Customer employment type ko booking form employment type mein convert karo
    """
    mapping = {
        'salaried': 'salaried',
        'business': 'self_employed',
        'professional': 'self_employed',
        'retired': 'self_employed',
        'homemaker': 'salaried'  # Default
    }
    return mapping.get(employment_type, 'salaried')

def get_state_from_city(city):
    """
    City se state guess karo - basic mapping
    """
    city_state_mapping = {
        'mumbai': 'Maharashtra',
        'delhi': 'Delhi', 
        'bangalore': 'Karnataka',
        'chennai': 'Tamil Nadu',
        'hyderabad': 'Telangana',
        'pune': 'Maharashtra',
        'thane': 'Maharashtra',
        'kolkata': 'West Bengal',
        # Add more cities as needed
    }
    
    return city_state_mapping.get(city.lower(), 'Maharashtra')  # Default

def handle_booking_submission(request, customer):
    """
    Form submission handle karo aur database mein save karo (create or update)
    """
    try:
        logger.debug(f"Form data received: {request.POST}")
        
        with transaction.atomic():
            # Check if customer already has a booking application
            existing_booking = BookingApplication.objects.filter(customer=customer).first()
            
            booking_data = {
                'customer': customer,
                'project_name': request.POST.get('project_name', 'Default Project'),
                'application_date': request.POST.get('application_date'),
                
                # Flat details
                'flat_number': request.POST.get('flat_number', ''),
                'floor': request.POST.get('floor', ''),
                'rera_carpet_area': request.POST.get('rera_carpet_area') or None,
                'exclusive_deck_balcony': request.POST.get('exclusive_deck_balcony') or None,
                'car_parking_count': request.POST.get('car_parking_count') or 0,
                'total_purchase_price': request.POST.get('total_purchase_price') or None,
                'total_purchase_price_words': request.POST.get('total_purchase_price_words', ''),
                
                # Source of funds
                'self_financed': 'self_financed' in request.POST.getlist('source_of_funds'),
                'housing_loan': 'housing_loan' in request.POST.getlist('source_of_funds'),
                
                # Source of booking
                'source_direct': request.POST.get('source_direct') == 'on',
                'source_direct_specify': request.POST.get('source_direct_specify', ''),
                
                # Referral details
                'referral_customer_name': request.POST.get('referral_customer_name', ''),
                'referral_project': request.POST.get('referral_project', ''),
                'referral_flat_no': request.POST.get('referral_flat_no', ''),
                
                # Payment details
                'application_money_amount': request.POST.get('application_money_amount') or None,
                'application_money_words': request.POST.get('application_money_words', ''),
                'gst_amount': request.POST.get('gst_amount') or None,
                'gst_words': request.POST.get('gst_words', ''),
                'cheque_dd_no': request.POST.get('cheque_dd_no', ''),
                'instrument_date': request.POST.get('instrument_date') or None,
                'drawn_on': request.POST.get('drawn_on', ''),
                'gst_cheque_dd_no': request.POST.get('gst_cheque_dd_no', ''),
                'gst_instrument_date': request.POST.get('gst_instrument_date') or None,
                'gst_drawn_on': request.POST.get('gst_drawn_on', ''),
                
                # Manager details
                'sales_manager_name': request.POST.get('sales_manager_name', ''),
                'sourcing_manager_name': request.POST.get('sourcing_manager_name', ''),
            }
            
            if existing_booking:
                # Update existing booking
                for field, value in booking_data.items():
                    if field != 'customer':  # Don't update customer field
                        setattr(existing_booking, field, value)
                existing_booking.save()
                booking_app = existing_booking
                log_action(request.user, 'booking', 'BookingApplication', existing_booking.id,
                           f"Booking updated for {customer.get_full_name()} ({customer.form_number})",
                           request=request)

                # Clear existing applicants and channel partner
                booking_app.applicants.all().delete()
                if hasattr(booking_app, 'channel_partner'):
                    booking_app.channel_partner.delete()
                
                action_message = 'updated'
                logger.debug(f"Booking updated successfully: {booking_app.id}")
            else:
                # Create new booking
                booking_app = BookingApplication.objects.create(**booking_data)
                log_action(request.user, 'booking', 'BookingApplication', booking_app.id,
                           f"Booking created for {customer.get_full_name()} ({customer.form_number})",
                           request=request)
                action_message = 'created'
                logger.debug(f"Booking created successfully: {booking_app.id}")
            
            # Create applicants (fresh data)
            create_applicants(request, booking_app)
            
            # Create channel partner (if exists)
            create_channel_partner(request, booking_app)
            
            # Success response for AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'Booking application {action_message} successfully!',
                    'booking_id': booking_app.id,
                    'redirect_url': reverse('customer_enquiry:dashboard')
                })
            else:
                messages.success(request, f'Booking application {action_message} successfully!')
                return redirect('customer_enquiry:dashboard')
            
    except Exception as e:
        logger.error(f"Error in booking submission: {str(e)}", exc_info=True)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': f'Error processing booking: {str(e)}'
            })
        else:
            messages.error(request, f'Error processing booking: {str(e)}')
            return redirect('customer_enquiry:booking_form', customer_id=customer.id)

def generate_booking_pdf(request, customer):
    """
    PDF generation removed as requested
    """
    from django.http import HttpResponse
    from django.contrib import messages
    from django.shortcuts import redirect
    
    # PDF functionality removed - redirect back to form
    messages.info(request, 'PDF download functionality has been disabled.')
    return redirect('customer_enquiry:booking_form', customer_id=customer.id)

def create_applicants(request, booking_app):
    """
    Multiple applicants create karo
    """
    # Check kitne applicants fill kiye hain
    for i in range(1, 5):  # 1 to 4 applicants
        prefix = f'applicant_{i}_'
        
        # Check agar is applicant ka data hai - check for any meaningful field
        first_name = request.POST.get(f'{prefix}first_name', '').strip()
        last_name = request.POST.get(f'{prefix}last_name', '').strip()
        title = request.POST.get(f'{prefix}title', '').strip()
        mobile = request.POST.get(f'{prefix}mobile', '').strip()
        email = request.POST.get(f'{prefix}email', '').strip()
        city = request.POST.get(f'{prefix}city', '').strip()
        
        # Check for PAN number
        pan_chars = []
        for j in range(1, 11):
            pan_char = request.POST.get(f'{prefix}pan_{j}', '').strip()
            pan_chars.append(pan_char)
        pan_filled = any(pan_chars)
        
        # Check for Aadhar number
        aadhar_chars = []
        for j in range(1, 13):
            aadhar_char = request.POST.get(f'{prefix}aadhar_{j}', '').strip()
            aadhar_chars.append(aadhar_char)
        aadhar_filled = any(aadhar_chars)
        
        # Check for DOB
        dob_fields = [
            request.POST.get(f'{prefix}dob_d1', '').strip(),
            request.POST.get(f'{prefix}dob_d2', '').strip(),
            request.POST.get(f'{prefix}dob_m1', '').strip(),
            request.POST.get(f'{prefix}dob_m2', '').strip(),
        ]
        dob_filled = any(dob_fields)
        
        # Create applicant if ANY meaningful data is provided
        has_applicant_data = any([
            first_name, last_name, title, mobile, email, city,
            pan_filled, aadhar_filled, dob_filled,
            request.POST.get(f'{prefix}residential_address', '').strip(),
            request.POST.get(f'{prefix}correspondence_address', '').strip()
        ])
        
        if has_applicant_data:  # Agar koi bhi meaningful data hai toh applicant create karo
            try:
                # Build PAN number (reuse the chars we already collected)
                pan_no = ''.join([request.POST.get(f'{prefix}pan_{j}', '').strip() for j in range(1, 11)]).strip().upper()
                
                # Build Aadhaar number (reuse logic but with digit validation)
                aadhar_chars_clean = []
                for j in range(1, 13):
                    aadhar_char = request.POST.get(f'{prefix}aadhar_{j}', '').strip()
                    if aadhar_char.isdigit():  # Only accept digits for Aadhaar
                        aadhar_chars_clean.append(aadhar_char)
                aadhar_no = ''.join(aadhar_chars_clean).strip()
                
                # Build date of birth from individual fields
                dob_d1 = request.POST.get(f'{prefix}dob_d1', '')
                dob_d2 = request.POST.get(f'{prefix}dob_d2', '')
                dob_m1 = request.POST.get(f'{prefix}dob_m1', '')
                dob_m2 = request.POST.get(f'{prefix}dob_m2', '')
                dob_y1 = request.POST.get(f'{prefix}dob_y1', '')
                dob_y2 = request.POST.get(f'{prefix}dob_y2', '')
                dob_y3 = request.POST.get(f'{prefix}dob_y3', '')
                dob_y4 = request.POST.get(f'{prefix}dob_y4', '')
                
                date_of_birth = None
                if all([dob_d1, dob_d2, dob_m1, dob_m2, dob_y1, dob_y2, dob_y3, dob_y4]):
                    try:
                        from datetime import datetime
                        dob_str = f"{dob_d1}{dob_d2}/{dob_m1}{dob_m2}/{dob_y1}{dob_y2}{dob_y3}{dob_y4}"
                        date_of_birth = datetime.strptime(dob_str, '%d/%m/%Y').date()
                    except ValueError:
                        date_of_birth = None
                
                # Build anniversary date from individual fields
                ann_d1 = request.POST.get(f'{prefix}anniversary_d1', '')
                ann_d2 = request.POST.get(f'{prefix}anniversary_d2', '')
                ann_m1 = request.POST.get(f'{prefix}anniversary_m1', '')
                ann_m2 = request.POST.get(f'{prefix}anniversary_m2', '')
                ann_y1 = request.POST.get(f'{prefix}anniversary_y1', '')
                ann_y2 = request.POST.get(f'{prefix}anniversary_y2', '')
                ann_y3 = request.POST.get(f'{prefix}anniversary_y3', '')
                ann_y4 = request.POST.get(f'{prefix}anniversary_y4', '')
                
                anniversary_date = None
                if all([ann_d1, ann_d2, ann_m1, ann_m2, ann_y1, ann_y2, ann_y3, ann_y4]):
                    try:
                        from datetime import datetime
                        ann_str = f"{ann_d1}{ann_d2}/{ann_m1}{ann_m2}/{ann_y1}{ann_y2}{ann_y3}{ann_y4}"
                        anniversary_date = datetime.strptime(ann_str, '%d/%m/%Y').date()
                    except ValueError:
                        anniversary_date = None
                
                # Validate data before saving
                mobile_no = request.POST.get(f'{prefix}mobile', '').strip()
                email_addr = request.POST.get(f'{prefix}email', '').strip()
                
                # Create applicant with proper validation
                applicant_data = {
                    'booking_application': booking_app,
                    'applicant_order': i,
                    
                    # Personal details
                    'title': request.POST.get(f'{prefix}title', ''),
                    'first_name': first_name,
                    'middle_name': request.POST.get(f'{prefix}middle_name', ''),
                    'last_name': last_name,
                    'date_of_birth': date_of_birth,
                    'marital_status': request.POST.get(f'{prefix}marital_status', ''),
                    'anniversary_date': anniversary_date,
                    'sex': request.POST.get(f'{prefix}sex', ''),
                    
                    # Documents
                    'pan_no': pan_no[:10] if pan_no else '',  # Limit to 10 chars
                    'aadhar_no': aadhar_no[:12] if aadhar_no else '',  # Limit to 12 chars
                    'residential_status': request.POST.get(f'{prefix}residential_status', ''),
                    
                    # Address
                    'residential_address': request.POST.get(f'{prefix}residential_address', ''),
                    'city': request.POST.get(f'{prefix}city', ''),
                    'pin': request.POST.get(f'{prefix}pin', ''),
                    'state': request.POST.get(f'{prefix}state', ''),
                    'country': request.POST.get(f'{prefix}country', 'India'),
                    'correspondence_address': request.POST.get(f'{prefix}correspondence_address', ''),
                    
                    # Contact
                    'contact_residence': request.POST.get(f'{prefix}contact_residence', ''),
                    'contact_office': request.POST.get(f'{prefix}contact_office', ''),
                    'mobile': mobile_no[:10] if mobile_no else '',  # Limit to 10 chars
                    'email': email_addr[:254] if email_addr else '',  # Standard email length limit
                    
                    # Employment
                    'employment_type': request.POST.get(f'{prefix}employment_type', ''),
                    'profession': request.POST.get(f'{prefix}profession', ''),
                    'company_name': request.POST.get(f'{prefix}company_name', ''),
                }
                
                BookingApplicant.objects.create(**applicant_data)
                logger.debug(f"Applicant {i} created successfully with full data")
                
            except Exception as e:
                logger.error(f"Error creating applicant {i}: {str(e)}")
                # Log the specific data that caused the error
                logger.error(f"Applicant {i} data: first_name='{first_name}', last_name='{last_name}'")
                continue

def create_channel_partner(request, booking_app):
    """
    Channel partner create karo (if details provided)
    """
    partner_name = request.POST.get('channel_partner_name', '').strip()
    
    if partner_name:  # Agar channel partner details diye hain
        try:
            BookingChannelPartner.objects.create(
                booking_application=booking_app,
                name=partner_name,
                maharera_registration=request.POST.get('channel_partner_rera', ''),
                mobile=request.POST.get('channel_partner_mobile', ''),
                email=request.POST.get('channel_partner_email', ''),
            )
            logger.debug("Channel partner created successfully")
        except Exception as e:
            logger.error(f"Error creating channel partner: {str(e)}")


def user_login_view(request):
    """
    User login page with OTP verification and property selection - Updated with new properties
    """
    if request.method == 'GET':
        return render(request, 'customer-verification.html')
    
    elif request.method == 'POST':
        # Handle form submission
        phone_number = request.POST.get('phone_number')
        entered_otp = request.POST.get('otp')
        property_code = request.POST.get('property_code')
        
        # Get stored OTP from session
        stored_otp = request.session.get('otp')
        stored_phone = request.session.get('otp_phone')
        
        # Validate inputs
        if not all([phone_number, entered_otp, property_code]):
            messages.error(request, 'All fields are required.')
            return render(request, 'customer-verification.html')
        
        # Validate phone number format
        if len(phone_number) != 10 or not phone_number.isdigit():
            messages.error(request, 'Please enter a valid 10-digit phone number.')
            return render(request, 'customer-verification.html')
        
        # Validate OTP
        if not stored_otp or stored_phone != phone_number:
            messages.error(request, 'Please send OTP first.')
            return render(request, 'customer-verification.html')
        
        if entered_otp != stored_otp:
            messages.error(request, 'Invalid OTP. Please try again.')
            return render(request, 'customer-verification.html')
        
        # Validate property code - Updated with new properties
        valid_properties = ['Alt', 'Orn', 'Med', 'Star', 'Ant']
        if property_code not in valid_properties:
            messages.error(request, 'Please select a valid property.')
            return render(request, 'customer-verification.html')
        
        # Clear OTP from session
        request.session.pop('otp', None)
        request.session.pop('otp_phone', None)
        
        # Store user data in session
        request.session['user_authenticated'] = True
        request.session['user_phone'] = phone_number
        request.session['selected_property'] = property_code
        
        # Success - redirect to property-specific form
        messages.success(request, 'Login successful!')
        return redirect('customer_enquiry:property_form', property_code=property_code)

def get_client_ip(request):
    """Get real IP address of the client"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@csrf_exempt
@require_http_methods(["POST"])
def send_otp_view(request):
    """
    Generate OTP on backend and send via Interakt WhatsApp API with rate limiting
    """
    try:
        data = json.loads(request.body)
        phone_number = data.get('phone_number')

        if not phone_number or len(phone_number) != 10 or not phone_number.isdigit():
            return JsonResponse({'success': False, 'message': 'Invalid phone number format'})

        client_ip = get_client_ip(request)

        # --- Rate limit by phone number ---
        phone_cache_key = f'otp_count_phone_{phone_number}'
        phone_count = cache.get(phone_cache_key, 0)

        if phone_count >= settings.OTP_MAX_PER_PHONE:
            logger.warning(f"OTP rate limit hit for phone {phone_number}")
            return JsonResponse({
                'success': False,
                'message': f'Too many OTP requests for this number. Please try again after 1 hour.'
            })

        # --- Rate limit by IP address ---
        ip_cache_key = f'otp_count_ip_{client_ip}'
        ip_count = cache.get(ip_cache_key, 0)

        if ip_count >= settings.OTP_MAX_PER_IP:
            logger.warning(f"OTP rate limit hit for IP {client_ip}")
            return JsonResponse({
                'success': False,
                'message': 'Too many requests from your network. Please try again after 1 hour.'
            })

        # Generate OTP on backend (secure)
        otp = str(random.randint(100000, 999999))

        # Send via Interakt WhatsApp API
        response = http_client.post(
            'https://api.interakt.ai/v1/public/message/',
            headers={
                'Authorization': f'Basic {settings.INTERAKT_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'countryCode': '+91',
                'phoneNumber': phone_number,
                'callbackData': 'otp_verification',
                'type': 'Template',
                'template': {
                    'name': 'otp_verification',
                    'languageCode': 'en',
                    'bodyValues': [otp],
                    'buttonValues': {'0': [otp]}
                }
            },
            timeout=10
        )

        if response.status_code in (200, 201):
            # Increment counters only on successful send
            cache.set(phone_cache_key, phone_count + 1, settings.OTP_BLOCK_DURATION)
            cache.set(ip_cache_key, ip_count + 1, settings.OTP_BLOCK_DURATION)

            request.session['otp'] = otp
            request.session['otp_phone'] = phone_number
            request.session['otp_timestamp'] = int(timezone.now().timestamp())
            logger.info(f"OTP sent via WhatsApp for phone {phone_number} (attempt {phone_count + 1})")
            return JsonResponse({'success': True, 'message': 'OTP sent to your WhatsApp number'})
        else:
            logger.error(f"Interakt API error: {response.status_code} - {response.text}")
            return JsonResponse({'success': False, 'message': 'Failed to send OTP. Please try again.'})

    except Exception as e:
        logger.error(f"Error sending OTP: {str(e)}")
        return JsonResponse({'success': False, 'message': 'Failed to send OTP. Please try again.'})


@csrf_exempt
@require_http_methods(["POST"])
def verify_otp_view(request):
    """
    Verify OTP entered by user against session-stored OTP
    """
    try:
        data = json.loads(request.body)
        phone_number = data.get('phone_number')
        entered_otp = data.get('otp')
        property_code = data.get('property_code')

        if not all([phone_number, entered_otp, property_code]):
            return JsonResponse({'success': False, 'message': 'All fields are required.'})

        stored_otp = request.session.get('otp')
        stored_phone = request.session.get('otp_phone')
        otp_timestamp = request.session.get('otp_timestamp')

        if not stored_otp or stored_phone != phone_number:
            return JsonResponse({'success': False, 'message': 'Please send OTP first.'})

        # Check OTP expiry (10 minutes)
        if otp_timestamp:
            elapsed = int(timezone.now().timestamp()) - otp_timestamp
            if elapsed > 600:
                return JsonResponse({'success': False, 'message': 'OTP has expired. Please request a new one.'})

        if entered_otp != stored_otp:
            return JsonResponse({'success': False, 'message': 'Invalid OTP. Please try again.'})

        # Clear OTP from session
        request.session.pop('otp', None)
        request.session.pop('otp_phone', None)
        request.session.pop('otp_timestamp', None)

        # Mark user as authenticated
        request.session['user_authenticated'] = True
        request.session['user_phone'] = phone_number

        # Determine redirect URL based on property_code
        property_url_map = {
            'Alt': '/altavista/customer-form/',
            'Orn': '/ornata/customer-form/',
            'Med': '/medius/customer-form/',
            'Star': '/spenta-stardeous/customer-form/',
            'Ant': '/spenta-anthea/customer-form/',
        }
        redirect_url = property_url_map.get(property_code, '/customer-form/')

        return JsonResponse({'success': True, 'redirect_url': redirect_url})

    except Exception as e:
        logger.error(f"Error verifying OTP: {str(e)}")
        return JsonResponse({'success': False, 'message': 'Verification failed. Please try again.'})

def property_verification_view(request, property_code):
    """
    Property-specific verification page with auto-selected property - Updated to use database
    """
    # Get project from database
    selected_property = get_project_by_code(property_code)
    if not selected_property:
        # Invalid property code, redirect to main verification
        return redirect('customer_enquiry:verification')
    
    context = {
        'selected_property': selected_property,
        'property_code': property_code,
        'auto_selected': True  # Flag to indicate auto-selection
    }
    
    return render(request, 'customer-verification.html', context)

def property_customer_form(request, property_code):
    """
    Property-specific customer form with auto-selected property - Updated to use database
    """
    # Get project data from database using the property code
    selected_property = get_project_by_code(property_code)

    if not selected_property:
        # Invalid property code, redirect to main form
        return redirect('customer_enquiry:customer_form')

    # Get verified phone number from session
    verified_phone = request.session.get('user_phone')

    # Get all active projects for any dropdowns
    active_projects = Project.objects.active_projects()

    import json as _json
    cp_master = list(ChannelPartnerMaster.objects.filter(is_active=True).values(
        'id', 'company_name', 'partner_name', 'mobile_number', 'rera_number'
    ))
    cp_master_json = _json.dumps(cp_master)

    context = {
        'selected_property': selected_property,
        'property_code': property_code,
        'auto_selected': True,
        'verified_phone': verified_phone,
        'active_projects': active_projects,
        'cp_master_json': cp_master_json,
    }

    return render(request, 'customer_enquiry.html', context)

def customer_verification_view(request):
    """
    Customer verification page with dynamic project list
    """
    # Get all active projects for dropdown
    active_projects = Project.objects.active_projects()

    context = {
        'active_projects': active_projects,
    }

    return render(request, 'customer-verification.html', context)

@require_http_methods(["GET"])
def get_project_data(request):
    """
    AJAX endpoint to get project data by property code
    """
    property_code = request.GET.get('property_code')
    if not property_code:
        return JsonResponse({'error': 'Property code is required'}, status=400)

    project_data = get_project_by_code(property_code)
    if project_data:
        # Convert logo to URL if it exists
        if project_data.get('logo'):
            project_data['logo_url'] = f"/media/{project_data['logo']}"
        return JsonResponse({'success': True, 'project': project_data})
    else:
        return JsonResponse({'error': 'Project not found'}, status=404)

# Decorator to check user authentication
def login_required_custom(view_func):
    """
    Custom decorator to check if user is authenticated via OTP
    """
    def wrapper(request, *args, **kwargs):
        if not request.session.get('user_authenticated'):
            messages.warning(request, 'Please login first.')
            return redirect('customer_enquiry:user_login')
        return view_func(request, *args, **kwargs)
    return wrapper


# PASSWORD RESET VIA WHATSAPP OTP

def password_reset_request(request):
    """
    Step 1: User enters username — OTP is sent to their registered WhatsApp number
    """
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()

        if not username:
            messages.error(request, 'Please enter your username.')
            return render(request, 'password_reset_form.html')

        # --- Rate limit by username ---
        username_cache_key = f'pwd_reset_count_user_{username}'
        username_count = cache.get(username_cache_key, 0)
        if username_count >= settings.OTP_MAX_PER_PHONE:
            messages.error(request, 'Too many password reset attempts for this account. Please try again after 1 hour.')
            return render(request, 'password_reset_form.html')

        # --- Rate limit by IP ---
        client_ip = get_client_ip(request)
        ip_cache_key = f'pwd_reset_count_ip_{client_ip}'
        ip_count = cache.get(ip_cache_key, 0)
        if ip_count >= settings.OTP_MAX_PER_IP:
            messages.error(request, 'Too many password reset attempts from your network. Please try again after 1 hour.')
            return render(request, 'password_reset_form.html')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # Still increment counters to prevent username enumeration
            cache.set(username_cache_key, username_count + 1, settings.OTP_BLOCK_DURATION)
            cache.set(ip_cache_key, ip_count + 1, settings.OTP_BLOCK_DURATION)
            messages.error(request, 'No account found with this username.')
            return render(request, 'password_reset_form.html')

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            messages.error(request, 'No WhatsApp number registered for this account. Please contact your administrator.')
            return render(request, 'password_reset_form.html')

        # Generate OTP
        otp = str(random.randint(100000, 999999))

        # Send via Interakt WhatsApp API
        try:
            response = http_client.post(
                'https://api.interakt.ai/v1/public/message/',
                headers={
                    'Authorization': f'Basic {settings.INTERAKT_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={
                    'countryCode': '+91',
                    'phoneNumber': profile.whatsapp_number,
                    'callbackData': 'password_reset_otp',
                    'type': 'Template',
                    'template': {
                        'name': 'otp_verification',
                        'languageCode': 'en',
                        'bodyValues': [otp],
                        'buttonValues': {'0': [otp]}
                    }
                },
                timeout=10
            )

            if response.status_code in (200, 201):
                # Increment rate limit counters on successful send
                cache.set(username_cache_key, username_count + 1, settings.OTP_BLOCK_DURATION)
                cache.set(ip_cache_key, ip_count + 1, settings.OTP_BLOCK_DURATION)
                request.session['reset_otp'] = otp
                request.session['reset_username'] = username
                request.session['reset_otp_timestamp'] = int(timezone.now().timestamp())
                messages.success(request, f'OTP sent to your registered WhatsApp number.')
                log_action(user, 'password_reset', 'User', user.id,
                           f'Password reset OTP sent for {username}', request=request)
                return redirect('customer_enquiry:password_reset_verify')
            else:
                logger.error(f"Interakt error: {response.status_code} - {response.text}")
                messages.error(request, 'Failed to send OTP. Please try again.')

        except Exception as e:
            logger.error(f"OTP send error: {str(e)}")
            messages.error(request, 'Failed to send OTP. Please try again.')

    return render(request, 'password_reset_form.html')


def password_reset_verify(request):
    """
    Step 2: User enters the OTP received on WhatsApp
    """
    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()
        stored_otp = request.session.get('reset_otp')
        otp_timestamp = request.session.get('reset_otp_timestamp')

        if not stored_otp:
            messages.error(request, 'Session expired. Please start again.')
            return redirect('customer_enquiry:password_reset')

        # Check expiry (10 minutes)
        if otp_timestamp and (int(timezone.now().timestamp()) - otp_timestamp) > 600:
            messages.error(request, 'OTP has expired. Please request a new one.')
            return redirect('customer_enquiry:password_reset')

        if entered_otp != stored_otp:
            messages.error(request, 'Invalid OTP. Please try again.')
            return render(request, 'password_reset_verify.html')

        # OTP correct — mark as verified
        request.session['reset_otp_verified'] = True
        request.session.pop('reset_otp', None)
        return redirect('customer_enquiry:password_reset_new')

    return render(request, 'password_reset_verify.html')


def password_reset_new(request):
    """
    Step 3: User sets a new password after OTP verification
    """
    if not request.session.get('reset_otp_verified'):
        messages.error(request, 'Please complete OTP verification first.')
        return redirect('customer_enquiry:password_reset')

    username = request.session.get('reset_username')
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        messages.error(request, 'Session expired. Please start again.')
        return redirect('customer_enquiry:password_reset')

    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            # Clear all reset session data
            request.session.pop('reset_otp_verified', None)
            request.session.pop('reset_username', None)
            request.session.pop('reset_otp_timestamp', None)
            messages.success(request, 'Your password has been reset successfully!')
            return redirect('customer_enquiry:password_reset_done')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = SetPasswordForm(user)

    return render(request, 'password_reset_confirm.html', {'form': form, 'validlink': True})


def password_reset_done(request):
    return render(request, 'password_reset_done.html')


def password_reset_complete(request):
    return render(request, 'password_reset_complete.html')


# ─── Sourcing Manager Dashboard ───────────────────────────────────────────────

@login_required
def sourcing_manager_dashboard(request):
    """Dashboard for Sourcing Manager — view only, shows assigned leads."""
    role = get_user_role(request.user)
    if role not in ('sourcing_manager', 'admin', 'super_admin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    if role == 'sourcing_manager':
        customers = Customer.objects.filter(
            assignment__sourcing_manager=request.user
        ).select_related('sales_assessment').prefetch_related(
            'sources', 'booking_applications', 'additional_channel_partners'
        ).order_by('-created_at')
    else:
        customers = Customer.objects.select_related('sales_assessment').prefetch_related(
            'sources', 'booking_applications', 'additional_channel_partners'
        ).order_by('-created_at')

    # Get all active projects for JavaScript property mapping
    projects = Project.objects.active_projects()
    projects_data = {}
    for project in projects:
        projects_data[project.project_prefix.upper()] = {
            'code': project.project_prefix,
            'name': project.project_name
        }

    import json
    projects_data_json = json.dumps(projects_data)

    return render(request, 'sourcing_manager_dashboard.html', {
        'customers': customers,
        'user_role': role,
        'projects_data_json': projects_data_json,
        'active_projects': projects,
    })


# ─── Closing Manager Dashboard ────────────────────────────────────────────────

@login_required
def closing_manager_dashboard(request):
    """Dashboard for Closing Manager — view + edit, shows assigned leads."""
    role = get_user_role(request.user)
    if role not in ('closing_manager', 'admin', 'super_admin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    if role == 'closing_manager':
        customers = Customer.objects.filter(
            assignment__closing_manager=request.user
        ).select_related('sales_assessment').prefetch_related(
            'sources', 'booking_applications', 'revisits', 'additional_channel_partners'
        ).order_by('-created_at')
    else:
        customers = Customer.objects.select_related('sales_assessment').prefetch_related(
            'sources', 'booking_applications', 'revisits', 'additional_channel_partners'
        ).order_by('-created_at')

    # Get all active projects for JavaScript property mapping
    projects = Project.objects.active_projects()
    projects_data = {}
    for project in projects:
        projects_data[project.project_prefix.upper()] = {
            'code': project.project_prefix,
            'name': project.project_name
        }

    import json
    projects_data_json = json.dumps(projects_data)

    return render(request, 'closing_manager_dashboard.html', {
        'customers': customers,
        'user_role': role,
        'projects_data_json': projects_data_json,
        'active_projects': projects,
    })


# ─── Admin: Manage Users (Managers) ──────────────────────────────────────────

@login_required
def manage_users(request):
    """Admin page: list all managers, create new ones."""
    role = get_user_role(request.user)
    if role not in ('admin', 'super_admin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_user':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            whatsapp = request.POST.get('whatsapp_number', '').strip()
            new_role = request.POST.get('role', 'gre')
            password = request.POST.get('password', '').strip()

            if not first_name or not email or not password:
                messages.error(request, "First name, email, and password are required.")
            elif User.objects.filter(email=email).exists():
                messages.error(request, "A user with this email already exists.")
            else:
                username = email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1

                new_user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                )
                UserProfile.objects.create(
                    user=new_user,
                    whatsapp_number=whatsapp,
                    role=new_role,
                )
                log_action(
                    request.user, 'create', 'User',
                    new_user.id, f"{first_name} {last_name} ({new_role})",
                    request=request
                )
                messages.success(request, f"User '{username}' created successfully with role '{new_role}'.")
                return redirect('customer_enquiry:manage_users')

        elif action == 'delete_user':
            user_id = request.POST.get('user_id')
            try:
                target_user = User.objects.get(id=user_id)
                if target_user == request.user:
                    messages.error(request, "You cannot delete your own account.")
                else:
                    log_action(request.user, 'delete', 'User', target_user.id, str(target_user), request=request)
                    target_user.delete()
                    messages.success(request, "User deleted successfully.")
            except User.DoesNotExist:
                messages.error(request, "User not found.")
            return redirect('customer_enquiry:manage_users')

    # List all staff users with profiles
    profiles = UserProfile.objects.select_related('user').order_by('role', 'user__first_name')
    return render(request, 'manage_users.html', {
        'profiles': profiles,
        'role_choices': UserProfile.ROLE_CHOICES,
        'user_role': role,
    })


# ─── Admin: Assign Customer to Managers ──────────────────────────────────────

@login_required
def assign_customer(request, customer_id):
    """Assign a customer to sourcing/closing manager."""
    role = get_user_role(request.user)
    if role not in ('admin', 'super_admin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    customer = get_object_or_404(Customer, id=customer_id)

    sourcing_managers = User.objects.filter(profile__role='sourcing_manager')
    closing_managers = User.objects.filter(profile__role='closing_manager')

    try:
        assignment = customer.assignment
    except CustomerAssignment.DoesNotExist:
        assignment = None

    if request.method == 'POST':
        sourcing_id = request.POST.get('sourcing_manager') or None
        closing_id = request.POST.get('closing_manager') or None

        sourcing_user = User.objects.get(id=sourcing_id) if sourcing_id else None
        closing_user = User.objects.get(id=closing_id) if closing_id else None

        if assignment:
            assignment.sourcing_manager = sourcing_user
            assignment.closing_manager = closing_user
            assignment.assigned_by = request.user
            assignment.save()
        else:
            assignment = CustomerAssignment.objects.create(
                customer=customer,
                sourcing_manager=sourcing_user,
                closing_manager=closing_user,
                assigned_by=request.user,
            )

        log_action(
            request.user, 'assign', 'Customer', customer.id,
            str(customer),
            changes=json.dumps({
                'sourcing_manager': sourcing_user.get_full_name() if sourcing_user else None,
                'closing_manager': closing_user.get_full_name() if closing_user else None,
            }),
            request=request
        )
        messages.success(request, f"Assignment updated for {customer.get_full_name()}.")
        return redirect('customer_enquiry:dashboard')

    return render(request, 'assign_customer.html', {
        'customer': customer,
        'assignment': assignment,
        'sourcing_managers': sourcing_managers,
        'closing_managers': closing_managers,
        'user_role': role,
    })


# ─── Manage Channel Partners (Master Directory) ───────────────────────────────

@login_required
def manage_channel_partners(request):
    """Admin page: manage master list of Channel Partners."""
    role = get_user_role(request.user)
    if role not in ('admin', 'super_admin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    message = None
    error = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            company_name = request.POST.get('company_name', '').strip()
            partner_name = request.POST.get('partner_name', '').strip()
            mobile_number = request.POST.get('mobile_number', '').strip()
            rera_number = request.POST.get('rera_number', '').strip()
            if not company_name or not partner_name or not mobile_number:
                error = 'Company Name, Partner Name, and Mobile Number are required.'
            elif len(mobile_number) != 10 or not mobile_number.isdigit():
                error = 'Mobile number must be exactly 10 digits.'
            else:
                new_cp = ChannelPartnerMaster.objects.create(
                    company_name=company_name,
                    partner_name=partner_name,
                    mobile_number=mobile_number,
                    rera_number=rera_number,
                )
                message = f'Channel Partner "{company_name} — {partner_name}" added successfully.'
                log_action(request.user, 'cp_add', 'ChannelPartnerMaster', new_cp.id,
                           f'{company_name} — {partner_name}', request=request)

        elif action == 'delete':
            cp_id = request.POST.get('cp_id')
            cp = get_object_or_404(ChannelPartnerMaster, pk=cp_id)
            name = str(cp)
            cp.delete()
            message = f'"{name}" has been removed.'
            log_action(request.user, 'delete', 'ChannelPartnerMaster', cp_id, name, request=request)

        elif action == 'toggle_active':
            cp_id = request.POST.get('cp_id')
            cp = get_object_or_404(ChannelPartnerMaster, pk=cp_id)
            cp.is_active = not cp.is_active
            cp.save()
            status = 'activated' if cp.is_active else 'deactivated'
            message = f'"{cp.company_name}" has been {status}.'
            log_action(request.user, 'cp_toggle', 'ChannelPartnerMaster', cp.id,
                       f'{cp.company_name} — {status}', request=request)

    search = request.GET.get('search', '')
    partners = ChannelPartnerMaster.objects.all()
    if search:
        partners = partners.filter(
            Q(company_name__icontains=search) |
            Q(partner_name__icontains=search) |
            Q(mobile_number__icontains=search)
        )

    return render(request, 'manage_channel_partners.html', {
        'partners': partners,
        'search': search,
        'message': message,
        'error': error,
    })


@login_required
def channel_partners_api(request):
    """Return active channel partners as JSON for auto-fill in forms."""
    from django.http import JsonResponse
    partners = ChannelPartnerMaster.objects.filter(is_active=True).values(
        'id', 'company_name', 'partner_name', 'mobile_number', 'rera_number'
    )
    return JsonResponse({'partners': list(partners)})


# ─── Audit Trail ─────────────────────────────────────────────────────────────

@login_required
def audit_trail(request):
    """View audit logs. Only admin and super admin can access."""
    role = get_user_role(request.user)
    if role not in ('admin', 'super_admin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")

    logs = AuditLog.objects.select_related('user', 'user__profile').order_by('-timestamp')

    # Filters
    filter_user = request.GET.get('user', '')
    filter_action = request.GET.get('action', '')
    filter_date_from = request.GET.get('date_from', '')
    filter_date_to = request.GET.get('date_to', '')
    filter_model = request.GET.get('model', '')

    if filter_user:
        logs = logs.filter(user__username__icontains=filter_user)
    if filter_action:
        logs = logs.filter(action=filter_action)
    if filter_date_from:
        logs = logs.filter(timestamp__date__gte=filter_date_from)
    if filter_date_to:
        logs = logs.filter(timestamp__date__lte=filter_date_to)
    if filter_model:
        logs = logs.filter(model_name__icontains=filter_model)

    model_choices = AuditLog.objects.values_list('model_name', flat=True).distinct().exclude(model_name='').order_by('model_name')

    from django.core.paginator import Paginator
    logs_limited = logs[:5000]
    paginator = Paginator(logs_limited, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'audit_trail.html', {
        'page_obj': page_obj,
        'total_count': paginator.count,
        'action_choices': AuditLog.ACTION_CHOICES,
        'model_choices': model_choices,
        'filter_user': filter_user,
        'filter_action': filter_action,
        'filter_date_from': filter_date_from,
        'filter_date_to': filter_date_to,
        'filter_model': filter_model,
        'user_role': role,
    })


# ─── Revisit ─────────────────────────────────────────────────────────────────

@login_required
def add_revisit(request, customer_id):
    """Record a revisit for a customer."""
    customer = get_object_or_404(Customer, id=customer_id)

    if request.method == 'POST':
        visit_date = request.POST.get('visit_date', str(timezone.now().date()))
        remark = request.POST.get('remark', '').strip()

        revisit = CustomerRevisit.objects.create(
            customer=customer,
            visit_date=visit_date,
            remark=remark,
            created_by=request.user,
        )
        log_action(
            request.user, 'create', 'CustomerRevisit', revisit.id,
            f"Revisit for {customer.get_full_name()} on {visit_date}",
            request=request
        )
        return JsonResponse({'success': True, 'visit_date': str(revisit.visit_date), 'remark': revisit.remark})

    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)


@login_required
def revisit_history(request, customer_id):
    """Return revisit history for a customer as JSON."""
    customer = get_object_or_404(Customer, id=customer_id)
    revisits = customer.revisits.select_related('created_by').order_by('-visit_date')
    data = [
        {
            'visit_date': str(r.visit_date),
            'remark': r.remark,
            'recorded_by': r.created_by.get_full_name() or r.created_by.username if r.created_by else 'Unknown',
        }
        for r in revisits
    ]
    return JsonResponse({'revisits': data, 'count': len(data)})