from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from datetime import datetime
from django.contrib import messages

from .models import Customer, CustomerSource, ChannelPartner, Referral

def index(request):
    """Display the customer form"""
    return render(request, 'customer_enquiry.html')

def thank_you(request):
    """Display thank you page"""
    # Get customer data from session if available
    customer_data = request.session.get('customer_data', None)
    context = {'customer_data': customer_data}
    
    # Clear session data after use
    if 'customer_data' in request.session:
        del request.session['customer_data']
    
    return render(request, 'thank-you.html', context)

@require_http_methods(["POST"])
def customer_submit_view(request):
    """Handle customer form submission"""
    try:
        with transaction.atomic():
            # Extract and validate data
            data = request.POST
            
            # Check required fields
            required_fields = [
                'first_name', 'last_name', 'email', 'date_of_birth',
                'residential_address', 'city', 'locality', 'pincode',
                'nationality', 'employment_type', 'configuration',
                'budget', 'construction_status', 'purpose_of_buying'
            ]
            
            missing_fields = [field for field in required_fields if not data.get(field)]
            if missing_fields:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': f'Required fields missing: {", ".join(missing_fields)}'
                    })
                else:
                    messages.error(request, f'Required fields missing: {", ".join(missing_fields)}')
                    return redirect('index')  # Fixed redirect
            
            # Validate pincode
            pincode = data.get('pincode', '')
            if len(pincode) != 6 or not pincode.isdigit():
                error_msg = 'Please enter a valid 6-digit pincode'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                else:
                    messages.error(request, error_msg)
                    return redirect('index')  # Fixed redirect
            
            # Create customer
            customer = Customer.objects.create(
                form_number=data.get('form_number', f'CIF-{datetime.now().strftime("%Y%m%d%H%M%S")}'),
                form_date=data.get('form_date', datetime.now().date()),
                first_name=data.get('first_name'),
                middle_name=data.get('middle_name', ''),
                last_name=data.get('last_name'),
                email=data.get('email'),
                date_of_birth=data.get('date_of_birth'),
                residential_address=data.get('residential_address'),
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
                'customer_id': customer.id
            }
            
            # Check if AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Customer enquiry submitted successfully!',
                    'form_number': customer.form_number,
                    'customer_id': customer.id,
                    'redirect_url': '/thank-you/'
                })
            else:
                # Traditional form submission - redirect to thank you page
                return redirect('thank_you')  # Fixed redirect - matches your URL name
            
    except Exception as e:
        error_msg = f'An error occurred: {str(e)}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': error_msg})
        else:
            messages.error(request, error_msg)
            return redirect('index')