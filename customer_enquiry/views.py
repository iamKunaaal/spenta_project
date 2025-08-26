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
from .models import Customer, CustomerSource, ChannelPartner, Referral, InternalSalesAssessment, BookingApplication, BookingApplicant, BookingChannelPartner
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
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.contrib.auth.views import PasswordResetView
from django.utils import timezone

logger = logging.getLogger(__name__)

# Updated property mapping - removed 'CIF' and added new properties
PROPERTY_MAPPING = {
    'Alt': {'name': 'Altavista', 'location': 'Mumbai'},
    'Orn': {'name': 'Ornata', 'location': 'Mumbai'},
    'Med': {'name': 'Medius', 'location': 'Mumbai'},
    'Star': {'name': 'Spenta Stardeous', 'location': 'Mumbai'},
    'Ant': {'name': 'Spenta Anthea', 'location': 'Mumbai'},
}

def index(request, property_code=None):
    """
    Display the customer form - Updated to use the new property mapping
    """
    # Get property from URL parameter if provided
    if property_code:
        # Handle property-specific form - Updated with new properties
        if property_code in PROPERTY_MAPPING:
            selected_property = {
                'code': property_code,
                'name': PROPERTY_MAPPING[property_code]['name'],
                'location': PROPERTY_MAPPING[property_code]['location']
            }
        else:
            selected_property = None
    else:
        selected_property = None
    
    # Get property from GET parameter (from verification page)
    get_property = request.GET.get('property')
    if get_property and not selected_property:
        if get_property in PROPERTY_MAPPING:
            selected_property = {
                'code': get_property,
                'name': PROPERTY_MAPPING[get_property]['name'],
                'location': PROPERTY_MAPPING[get_property]['location']
            }
    
    context = {
        'selected_property': selected_property,
        'property_code': property_code or get_property,
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
            property_mapping = {
                'Alt': 'Altavista',
                'Orn': 'Ornata',
                'Med': 'Medius', 
                'Star': 'Spenta Stardeous',
                'Ant': 'Spenta Anthea'
            }
            
            property_name = property_mapping.get(property_code, property_code)
            
            # Check required fields - UPDATED: Added sex and marital_status, removed date_of_birth and residential_address
            required_fields = [
                'first_name', 'last_name', 'email',
                'city', 'locality', 'pincode',
                'nationality', 'employment_type', 'configuration',
                'budget', 'construction_status', 'purpose_of_buying',
                'sex', 'marital_status'  # ADDED: New required fields
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
            
            # Generate form number based on property
            import time
            timestamp = str(int(time.time()))[-5:]  # Last 5 digits of timestamp
            form_number = f"{property_code}-{timestamp}"
            
            # Handle optional date_of_birth field
            date_of_birth = data.get('date_of_birth', '').strip()
            if not date_of_birth:
                # If no date provided, use a default date or handle appropriately
                # Option 1: Use today's date (not recommended)
                # date_of_birth = datetime.now().date()
                
                # Option 2: Use a placeholder date (better for now)
                date_of_birth = '1900-01-01'  # Placeholder date
                
            # Create customer - UPDATED: Added sex and marital_status fields, made date_of_birth and residential_address optional
            customer = Customer.objects.create(
                form_number=form_number,
                form_date=data.get('form_date', datetime.now().date()),
                first_name=data.get('first_name'),
                middle_name=data.get('middle_name', ''),
                last_name=data.get('last_name'),
                email=data.get('email'),
                phone_number=phone_number if phone_number else None,
                sex=sex,  # ADDED: Sex field
                marital_status=marital_status,  # ADDED: Marital status field
                date_of_birth=date_of_birth,  # Handle empty dates
                residential_address=data.get('residential_address', ''),  # OPTIONAL - empty string if not provided
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
            
            # Add sources
            sources = request.POST.getlist('sources')
            for source in sources:
                CustomerSource.objects.create(
                    customer=customer,
                    source_type=source
                )
            
            # Add channel partner if selected
            if 'channel_partner' in sources:
                partner_data = {
                    'company_name': data.get('partner_company_name'),
                    'partner_name': data.get('partner_name'),
                    'mobile_number': data.get('partner_mobile'),
                    'rera_number': data.get('partner_rera')
                }
                
                if all(partner_data.values()):
                    ChannelPartner.objects.create(customer=customer, **partner_data)
            
            # Add referral if selected
            if 'referral' in sources:
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
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('customer_enquiry:dashboard')  # Redirect to GRE dashboard
        else:
            messages.error(request, "Invalid username or password")
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
    
    return render(request, 'dashboard.html', {'customers': customers})

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
            # Get property name - Updated with new properties
            property_code = customer.form_number[:3] if customer.form_number else ''
            # Handle different property code lengths
            if customer.form_number:
                if customer.form_number.startswith('Star'):
                    property_code = 'Star'
                elif customer.form_number.startswith('Ant'):
                    property_code = 'Ant'
                elif customer.form_number.startswith('Orn'):
                    property_code = 'Orn'
                elif customer.form_number.startswith('Med'):
                    property_code = 'Med'
                elif customer.form_number.startswith('Alt'):
                    property_code = 'Alt'
            
            property_names = {
                'Alt': 'Altavista',
                'Orn': 'Ornata',
                'Med': 'Medius',
                'Star': 'Spenta Stardeous',
                'Ant': 'Spenta Anthea'
            }
            property_name = property_names.get(property_code, property_code)
            
            # Get sources
            sources = ', '.join([source.get_source_type_display() for source in customer.sources.all()])
            
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
    """Edit customer with phone number, sex, and marital status support"""
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Update main customer fields
                customer.first_name = request.POST.get('first_name')
                customer.middle_name = request.POST.get('middle_name', '')
                customer.last_name = request.POST.get('last_name')
                customer.email = request.POST.get('email')
                
                # ADDED: Phone number handling
                phone_number = request.POST.get('phone_number', '').strip()
                if phone_number and (len(phone_number) != 10 or not phone_number.isdigit()):
                    messages.error(request, 'Please enter a valid 10-digit phone number')
                    return redirect('customer_enquiry:edit_customer', pk=pk)
                customer.phone_number = phone_number if phone_number else None
                
                # ADDED: Sex and Marital Status handling
                sex = request.POST.get('sex')
                marital_status = request.POST.get('marital_status')
                
                if sex:
                    valid_sex_choices = ['male', 'female', 'other']
                    if sex in valid_sex_choices:
                        customer.sex = sex
                    else:
                        messages.error(request, 'Please select a valid sex option')
                        return redirect('customer_enquiry:edit_customer', pk=pk)
                
                if marital_status:
                    valid_marital_choices = ['single', 'married', 'divorced', 'widowed', 'other']
                    if marital_status in valid_marital_choices:
                        customer.marital_status = marital_status
                    else:
                        messages.error(request, 'Please select a valid marital status option')
                        return redirect('customer_enquiry:edit_customer', pk=pk)
                
                # Handle optional date_of_birth field in edit
                date_of_birth = request.POST.get('date_of_birth', '').strip()
                if not date_of_birth:
                    # If no date provided, keep existing value or use placeholder
                    if customer.date_of_birth:
                        date_of_birth = customer.date_of_birth  # Keep existing value
                    else:
                        date_of_birth = '1900-01-01'  # Placeholder date
                
                customer.date_of_birth = date_of_birth  # Handle empty dates
                customer.residential_address = request.POST.get('residential_address', '')  # OPTIONAL - empty string if not provided
                customer.city = request.POST.get('city')
                customer.locality = request.POST.get('locality')
                customer.pincode = request.POST.get('pincode')
                customer.nationality = request.POST.get('nationality')
                customer.employment_type = request.POST.get('employment_type')
                customer.company_name = request.POST.get('company_name', '')
                customer.designation = request.POST.get('designation', '')
                customer.industry = request.POST.get('industry', '')
                customer.configuration = request.POST.get('configuration')
                customer.budget = request.POST.get('budget')
                customer.construction_status = request.POST.get('construction_status')
                customer.purpose_of_buying = request.POST.get('purpose_of_buying')
                customer.source_details = request.POST.get('source_details', '')

                # Validate pincode
                pincode = request.POST.get('pincode', '')
                if len(pincode) != 6 or not pincode.isdigit():
                    messages.error(request, 'Please enter a valid 6-digit pincode')
                    return redirect('customer_enquiry:edit_customer', pk=pk)

                customer.save()

                # Update Sources (existing code)
                customer.sources.all().delete()
                sources = request.POST.getlist('sources')
                for source in sources:
                    CustomerSource.objects.create(
                        customer=customer,
                        source_type=source
                    )

                # Update Channel Partner (existing code)
                if hasattr(customer, 'channel_partner'):
                    customer.channel_partner.delete()
                
                if 'channel_partner' in sources:
                    partner_data = {
                        'company_name': request.POST.get('partner_company_name', ''),
                        'partner_name': request.POST.get('partner_name', ''),
                        'mobile_number': request.POST.get('partner_mobile', ''),
                        'rera_number': request.POST.get('partner_rera', '')
                    }
                    
                    if all(partner_data.values()):
                        ChannelPartner.objects.create(customer=customer, **partner_data)

                # Update Referral (existing code)
                if hasattr(customer, 'referral'):
                    customer.referral.delete()
                
                if 'referral' in sources:
                    referral_data = {
                        'referral_name': request.POST.get('referral_name', ''),
                        'project_name': request.POST.get('referral_project', '')
                    }
                    
                    if all(referral_data.values()):
                        Referral.objects.create(customer=customer, **referral_data)

                messages.success(request, 'Customer information updated successfully!')
                return redirect('customer_enquiry:dashboard')

        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
            return redirect('customer_enquiry:edit_customer', pk=pk)

    # GET request - prepare context for template
    else:
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

        context = {
            'customer': customer,
            'current_sources': current_sources,
            'channel_partner': channel_partner,
            'referral': referral,
        }
        
        return render(request, 'edit_customer.html', context)

@login_required
def internal_sales_assessment(request, customer_id):
    """Create or edit internal sales assessment for a customer"""
    customer = get_object_or_404(Customer, pk=customer_id)
    
    # Try to get existing assessment or create new one
    try:
        assessment = customer.sales_assessment
    except InternalSalesAssessment.DoesNotExist:
        assessment = None

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

                # Update fields
                assessment_obj.sourcing_manager = request.POST.get('sourcing_manager', '')
                assessment_obj.sales_manager = request.POST.get('sales_manager', '')
                assessment_obj.customer_gender = request.POST.get('customer_gender', '')
                assessment_obj.facilitated_by_pre_sales = request.POST.get('facilitated_by_pre_sales', 'false') == 'true'
                assessment_obj.executive_name = request.POST.get('executive_name', '')
                assessment_obj.lead_classification = request.POST.get('lead_classification', '')
                assessment_obj.customer_classification = request.POST.get('customer_classification', '')
                assessment_obj.reason_for_closed = request.POST.get('reason_for_closed', '')
                assessment_obj.current_residence_config = request.POST.get('current_residence_config', '')
                assessment_obj.current_residence_ownership = request.POST.get('current_residence_ownership', '')
                assessment_obj.family_size = request.POST.get('family_size', '')
                assessment_obj.desired_flat_area = request.POST.get('desired_flat_area', '')
                assessment_obj.source_of_funding = request.POST.get('source_of_funding', '')
                assessment_obj.ethnicity = request.POST.get('ethnicity', '')
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
    context = {
        'customer': customer,
        'assessment': assessment,
    }
    
    return render(request, 'internal_sales_assessment.html', context)

# BOOKING FORM VIEWS
@login_required
def booking_form_view(request, customer_id):
    """
    Booking form view with pre-filled customer data
    """
    customer = get_object_or_404(Customer, pk=customer_id)
    
    if request.method == 'GET':
        # Pre-filled data prepare karo
        prefilled_data = prepare_prefilled_data(customer)
        
        context = {
            'customer': customer,
            'prefilled_data': prefilled_data,
        }
        
        return render(request, 'booking_form.html', context)
    
    elif request.method == 'POST':
        # Form submission handle karo
        return handle_booking_submission(request, customer)

def prepare_prefilled_data(customer):
    """
    Customer ke existing data se form pre-fill karo
    """
    prefilled_data = {
        # Project details - yeh aap customize kar sakte ho
        'project_name': 'Default Project Name',  # Ya customer.project se if available
        
        # 1st Applicant - Customer ki details se auto-fill
        'applicant_1_title': get_title_from_customer(customer),
        'applicant_1_first_name': customer.first_name,
        'applicant_1_middle_name': customer.middle_name or '',
        'applicant_1_last_name': customer.last_name,
        'applicant_1_email': customer.email,
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
    Form submission handle karo aur database mein save karo
    """
    try:
        logger.debug(f"Form data received: {request.POST}")
        
        with transaction.atomic():
            # Main booking application create karo
            booking_app = BookingApplication.objects.create(
                customer=customer,
                project_name=request.POST.get('project_name', 'Default Project'),
                application_date=request.POST.get('application_date'),
                
                # Flat details
                flat_number=request.POST.get('flat_number', ''),
                floor=request.POST.get('floor', ''),
                rera_carpet_area=request.POST.get('rera_carpet_area') or None,
                exclusive_deck_balcony=request.POST.get('exclusive_deck_balcony') or None,
                car_parking_count=request.POST.get('car_parking_count') or 0,
                total_purchase_price=request.POST.get('total_purchase_price') or None,
                total_purchase_price_words=request.POST.get('total_purchase_price_words', ''),
                
                # Source of funds
                self_financed='self_financed' in request.POST.getlist('source_of_funds'),
                housing_loan='housing_loan' in request.POST.getlist('source_of_funds'),
                
                # Source of booking
                source_direct=request.POST.get('source_direct') == 'on',
                source_direct_specify=request.POST.get('source_direct_specify', ''),
                
                # Referral details
                referral_customer_name=request.POST.get('referral_customer_name', ''),
                referral_project=request.POST.get('referral_project', ''),
                referral_flat_no=request.POST.get('referral_flat_no', ''),
                
                # Payment details
                application_money_amount=request.POST.get('application_money_amount') or None,
                application_money_words=request.POST.get('application_money_words', ''),
                gst_amount=request.POST.get('gst_amount') or None,
                gst_words=request.POST.get('gst_words', ''),
                cheque_dd_no=request.POST.get('cheque_dd_no', ''),
                instrument_date=request.POST.get('instrument_date') or None,
                drawn_on=request.POST.get('drawn_on', ''),
                gst_cheque_dd_no=request.POST.get('gst_cheque_dd_no', ''),
                gst_instrument_date=request.POST.get('gst_instrument_date') or None,
                gst_drawn_on=request.POST.get('gst_drawn_on', ''),
                
                # Manager details
                sales_manager_name=request.POST.get('sales_manager_name', ''),
                sourcing_manager_name=request.POST.get('sourcing_manager_name', ''),
            )
            
            # Applicants create karo
            create_applicants(request, booking_app)
            
            # Channel partner create karo (if exists)
            create_channel_partner(request, booking_app)
            
            logger.debug(f"Booking created successfully: {booking_app.id}")
            
            # Success response for AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Booking application created successfully!',
                    'booking_id': booking_app.id,
                    'redirect_url': reverse('customer_enquiry:dashboard')
                })
            else:
                messages.success(request, 'Booking application created successfully!')
                return redirect('customer_enquiry:dashboard')
            
    except Exception as e:
        logger.error(f"Error in booking submission: {str(e)}", exc_info=True)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': f'Error creating booking: {str(e)}'
            })
        else:
            messages.error(request, f'Error creating booking: {str(e)}')
            return redirect('customer_enquiry:booking_form', customer_id=customer.id)

def create_applicants(request, booking_app):
    """
    Multiple applicants create karo
    """
    # Check kitne applicants fill kiye hain
    for i in range(1, 5):  # 1 to 4 applicants
        prefix = f'applicant_{i}_'
        
        # Check agar is applicant ka data hai
        first_name = request.POST.get(f'{prefix}first_name', '').strip()
        last_name = request.POST.get(f'{prefix}last_name', '').strip()
        
        if first_name or last_name:  # Agar kuch data hai toh applicant create karo
            try:
                BookingApplicant.objects.create(
                    booking_application=booking_app,
                    applicant_order=i,
                    
                    # Personal details
                    title=request.POST.get(f'{prefix}title', ''),
                    first_name=first_name,
                    middle_name=request.POST.get(f'{prefix}middle_name', ''),
                    last_name=last_name,
                    date_of_birth=request.POST.get(f'{prefix}date_of_birth') or None,
                    marital_status=request.POST.get(f'{prefix}marital_status', ''),
                    anniversary_date=request.POST.get(f'{prefix}anniversary') or None,
                    sex=request.POST.get(f'{prefix}sex', ''),
                    
                    # Documents
                    pan_no=request.POST.get(f'{prefix}pan_no', ''),
                    aadhar_no=request.POST.get(f'{prefix}aadhar_no', ''),
                    residential_status=request.POST.get(f'{prefix}residential_status', ''),
                    
                    # Address
                    residential_address=request.POST.get(f'{prefix}residential_address', ''),
                    city=request.POST.get(f'{prefix}city', ''),
                    pin=request.POST.get(f'{prefix}pin', ''),
                    state=request.POST.get(f'{prefix}state', ''),
                    country=request.POST.get(f'{prefix}country', 'India'),
                    correspondence_address=request.POST.get(f'{prefix}correspondence_address', ''),
                    
                    # Contact
                    contact_residence=request.POST.get(f'{prefix}contact_residence', ''),
                    contact_office=request.POST.get(f'{prefix}contact_office', ''),
                    mobile=request.POST.get(f'{prefix}mobile', ''),
                    email=request.POST.get(f'{prefix}email', ''),
                    
                    # Employment
                    employment_type=request.POST.get(f'{prefix}employment_type', ''),
                    profession=request.POST.get(f'{prefix}profession', ''),
                    company_name=request.POST.get(f'{prefix}company_name', ''),
                )
                logger.debug(f"Applicant {i} created successfully")
            except Exception as e:
                logger.error(f"Error creating applicant {i}: {str(e)}")
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

def generate_booking_pdf(request, booking_app):
    """
    PDF generate karo aur download karo - Basic implementation
    """
    # Abhi basic response return kar rahe hain
    # Baad mein WeasyPrint use karenge PDF generation ke liye
    
    return JsonResponse({
        'success': True,
        'message': 'Booking created successfully!',
        'booking_id': booking_app.id,
        'redirect_url': reverse('customer_enquiry:dashboard')
    })

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
    Property-specific verification page with auto-selected property - Updated with new properties
    """
    # Updated property mapping
    if property_code not in PROPERTY_MAPPING:
        # Invalid property code, redirect to main verification
        return redirect('customer_enquiry:verification')
    
    selected_property = {
        'code': property_code,
        'name': PROPERTY_MAPPING[property_code]['name'],
        'location': PROPERTY_MAPPING[property_code]['location']
    }
    
    context = {
        'selected_property': selected_property,
        'property_code': property_code,
        'auto_selected': True  # Flag to indicate auto-selection
    }
    
    return render(request, 'customer-verification.html', context)

def property_customer_form(request, property_code):
    """
    Property-specific customer form with auto-selected property - Updated with new properties
    """
    # Updated property mapping
    if property_code not in PROPERTY_MAPPING:
        # Invalid property code, redirect to main form
        return redirect('customer_enquiry:customer_form')
    
    selected_property = {
        'code': property_code,
        'name': PROPERTY_MAPPING[property_code]['name'],
        'location': PROPERTY_MAPPING[property_code]['location']
    }
    
    context = {
        'selected_property': selected_property,
        'property_code': property_code,
        'auto_selected': True  # Flag to indicate auto-selection
    }
    
    return render(request, 'customer_enquiry.html', context)

def customer_verification_view(request):
    """
    Customer verification page (temporary implementation)
    """
    return render(request, 'customer-verification.html')

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