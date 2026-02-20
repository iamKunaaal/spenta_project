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
from .models import Customer, CustomerSource, ChannelPartner, Referral, InternalSalesAssessment, BookingApplication, BookingApplicant, BookingChannelPartner, Project
from django.shortcuts import get_object_or_404
import json
import logging
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

    context = {
        'selected_property': selected_property,
        'property_code': property_code or get_property or request.session.get('selected_property_code'),
        'verified_phone': verified_phone,
        'active_projects': active_projects,
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
            return redirect('customer_enquiry:dashboard')  # Redirect to GRE dashboard
        else:
            messages.error(request, "Invalid username or password")
            # Debug: print what was tried
            print(f"Login attempt with username: {username}")
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('customer_enquiry:login')

@login_required
def dashboard(request):
    """Enhanced dashboard with filtering capabilities"""
    # Get all customers with related data
    customers = Customer.objects.select_related('sales_assessment').prefetch_related(
        'sources', 'booking_applications'
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
        
        # Get filtered customers
        customers = Customer.objects.select_related('sales_assessment').prefetch_related(
            'sources', 'booking_applications'
        ).order_by('-created_at')
        
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
        
        return response
    
    return HttpResponse('Method not allowed', status=405)


def edit_customer(request, pk):
    """View customer information - display only, no editing allowed"""
    customer = get_object_or_404(Customer, pk=pk)

    # Only allow GET requests - no form submission/editing
    if request.method == 'POST':
        # Redirect back to view mode if someone tries to submit
        messages.info(request, 'This form is view-only. Customer information cannot be edited.')
        return redirect('customer_enquiry:edit_customer', pk=pk)

    # GET request - prepare context for template (view-only)
    # Get current sources
    current_sources = list(customer.sources.values_list('source_type', flat=True))
    
    # Get channel partner if exists
    try:
        channel_partner = customer.channel_partner
    except ChannelPartner.DoesNotExist:
        channel_partner = None
    
    # Get referral if exists
    try:
        referral = customer.referral
    except Referral.DoesNotExist:
        referral = None

    # Get project data from customer's form number prefix
    project_data = None
    if customer.form_number:
        try:
            # Extract prefix from form number with better matching logic
            form_parts = customer.form_number.split('-')
            found_project = None

            # Try different prefix matching strategies
            if len(form_parts) >= 3:
                # For form numbers like "ALT-phase4-35509", try "ALT-phase4" first
                compound_prefix = f"{form_parts[0]}-{form_parts[1]}"
                found_project = Project.objects.filter(
                    project_prefix__iexact=compound_prefix,
                    is_active=True
                ).first()

                if not found_project:
                    # Fall back to just the first part "ALT"
                    simple_prefix = form_parts[0]
                    found_project = Project.objects.filter(
                        project_prefix__iexact=simple_prefix,
                        is_active=True
                    ).first()
            else:
                # For simple form numbers like "MED-49988"
                prefix = form_parts[0] if len(form_parts) > 1 else customer.form_number[:3]
                found_project = Project.objects.filter(
                    project_prefix__iexact=prefix,
                    is_active=True
                ).first()

            if found_project:
                project_data = {
                    'code': found_project.form_number,
                    'name': found_project.project_name,
                    'location': found_project.site_name,
                    'address': found_project.address,
                    'company_name': found_project.company_name,
                    'maharera_no': found_project.maharera_no,
                    'logo': str(found_project.project_logo) if found_project.project_logo else None,
                    'prefix': found_project.project_prefix
                }
        except Exception:
            project_data = None

    context = {
        'customer': customer,
        'current_sources': current_sources,
        'channel_partner': channel_partner,
        'referral': referral,
        'view_only': True,  # Flag to indicate this is view-only mode
        'selected_property': project_data,
    }
    
    return render(request, 'edit_customer.html', context)

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
        
        # 6. Set default lead classification as 'warm' for new assessments
        assessment.lead_classification = 'warm'
        print(f"Set default lead classification: {assessment.lead_classification}")
        
        print("Auto-population completed")

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Get or create assessment
                if assessment:
                    # Update existing
                    assessment_obj = assessment
                else:
                    # Create new
                    assessment_obj = InternalSalesAssessment(customer=customer)

                # Update fields - GRE Section
                assessment_obj.sourcing_manager = request.POST.get('sourcing_manager', '')
                assessment_obj.sales_manager = request.POST.get('sales_manager', '')
                assessment_obj.customer_gender = request.POST.get('customer_gender', '')
                assessment_obj.facilitated_by_pre_sales = request.POST.get('facilitated_by_pre_sales', 'false') == 'true'
                assessment_obj.executive_name = request.POST.get('executive_name', '')
                
                # Sales Manager Section - Updated fields
                assessment_obj.lead_classification = request.POST.get('lead_classification', '')
                assessment_obj.reason_for_lost = request.POST.get('reason_for_lost', '')
                
                # Legacy fields (for backward compatibility)
                assessment_obj.customer_classification = request.POST.get('customer_classification', '')
                assessment_obj.reason_for_closed = request.POST.get('reason_for_closed', '')
                
                # Current Residence Section
                assessment_obj.current_residence_config = request.POST.get('current_residence_config', '')
                assessment_obj.current_residence_ownership = request.POST.get('current_residence_ownership', '')
                assessment_obj.plot = request.POST.get('plot', '')
                assessment_obj.family_size = request.POST.get('family_size', '')
                
                # Customer's Desired Requirement Section
                assessment_obj.area_looking = request.POST.get('area_looking', '')
                assessment_obj.desired_flat_area = request.POST.get('desired_flat_area', '')  # Legacy
                assessment_obj.source_of_funding = request.POST.get('source_of_funding', '')
                assessment_obj.ethnicity = request.POST.get('ethnicity', '')
                
                # Additional Information Section
                assessment_obj.other_projects_considered = request.POST.get('other_projects_considered', '')
                assessment_obj.sales_manager_remarks = request.POST.get('sales_manager_remarks', '')

                assessment_obj.save()

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

    context = {
        'customer': customer,
        'assessment': assessment,
        'selected_property': project_data,  # Add project data for logo display
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
                
                # Clear existing applicants and channel partner
                booking_app.applicants.all().delete()
                if hasattr(booking_app, 'channel_partner'):
                    booking_app.channel_partner.delete()
                
                action_message = 'updated'
                logger.debug(f"Booking updated successfully: {booking_app.id}")
            else:
                # Create new booking
                booking_app = BookingApplication.objects.create(**booking_data)
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

@csrf_exempt
@require_http_methods(["POST"])
def send_otp_view(request):
    """
    Send OTP to user's phone number
    """
    try:
        data = json.loads(request.body)
        phone_number = data.get('phone_number')
        otp = data.get('otp')
        
        # Validate phone number
        if not phone_number or len(phone_number) != 10 or not phone_number.isdigit():
            return JsonResponse({
                'success': False,
                'message': 'Invalid phone number format'
            })
        
        # Store OTP in session (in production, send via SMS API)
        request.session['otp'] = otp
        request.session['otp_phone'] = phone_number
        request.session['otp_timestamp'] = int(timezone.now().timestamp())
        
        # In production, integrate with SMS API like Twilio, MSG91, etc.
        # For now, we're just storing in session for demo
        
        logger.info(f"OTP {otp} generated for phone {phone_number}")
        
        return JsonResponse({
            'success': True,
            'message': 'OTP sent successfully'
        })
        
    except Exception as e:
        logger.error(f"Error sending OTP: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'Failed to send OTP'
        })

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

    context = {
        'selected_property': selected_property,
        'property_code': property_code,
        'auto_selected': True,  # Flag to indicate auto-selection
        'verified_phone': verified_phone,
        'active_projects': active_projects,
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


# PASSWORD RESET FUNCTIONALITY
def password_reset_request(request):
    """
    Handle password reset request
    """
    print(f"DEBUG: password_reset_request called with method: {request.method}")
    
    if request.method == 'POST':
        print(f"DEBUG: Processing POST request")
        form = PasswordResetForm(request.POST)
        print(f"DEBUG: Form created: {form}")
        
        if form.is_valid():
            print(f"DEBUG: Form is valid")
            email = form.cleaned_data.get('email')
            print(f"DEBUG: Email from form: {email}")
            
            try:
                user = User.objects.get(email=email)
                print(f"DEBUG: User found: {user.username}")
                
                # Generate token and UID
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                # Create reset link
                reset_link = request.build_absolute_uri(
                    f"/password-reset-confirm/{uid}/{token}/"
                )
                
                # Send password reset email
                try:
                    send_mail(
                        subject='Password Reset Request - Spenta CRM',
                        message=f'Click the following link to reset your password:\n\n{reset_link}\n\nThis link will expire in 1 hour.\n\nIf you did not request a password reset, please ignore this email.',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[email],
                        fail_silently=False,
                    )
                    messages.success(request, 'Password reset email has been sent to your email address.')
                    return redirect('customer_enquiry:password_reset_done')
                except Exception as e:
                    logger.error(f"Email sending failed: {str(e)}")
                    messages.error(request, 'Failed to send reset email. Please try again or contact your administrator.')
                    return render(request, 'password_reset_form.html', {'form': form})
                
            except User.DoesNotExist:
                messages.error(request, 'No user found with this email address.')
                
    else:
        form = PasswordResetForm()
    
    return render(request, 'password_reset_form.html', {'form': form})

def password_reset_done(request):
    """
    Display success message after password reset email is sent
    """
    return render(request, 'password_reset_done.html')

def password_reset_confirm(request, uidb64, token):
    """
    Handle password reset confirmation with token
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Your password has been reset successfully!')
                return redirect('customer_enquiry:login')
            else:
                # Debug: Print form errors
                logger.error(f"Form errors: {form.errors}")
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
        else:
            form = SetPasswordForm(user)
        
        return render(request, 'password_reset_confirm.html', {'form': form, 'validlink': True})
    else:
        messages.error(request, 'The password reset link is invalid or has expired.')
        return redirect('customer_enquiry:password_reset')

def password_reset_complete(request):
    """
    Display success message after password has been reset
    """
    return render(request, 'password_reset_complete.html')