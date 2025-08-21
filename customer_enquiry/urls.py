from django.urls import path
from customer_enquiry import views

app_name = 'customer_enquiry'

urlpatterns = [
    # Main verification page (home page)
    path('', views.customer_verification_view, name='verification'),
    
    # Property-specific verification URLs - NEW ADDITION
    path('altavista/', views.property_verification_view, {'property_code': 'Alt'}, name='altavista_verification'),
    path('spenta-medius/', views.property_verification_view, {'property_code': 'Med'}, name='medius_verification'),
    path('stardeous/', views.property_verification_view, {'property_code': 'Star'}, name='stardeous_verification'),
    
    # Customer form page (requires verification)
    path('customer-form/', views.index, name='customer_form'),
    
    # Property-specific customer form URLs - NEW ADDITION
    path('altavista/customer-form/', views.property_customer_form, {'property_code': 'Alt'}, name='altavista_form'),
    path('spenta-medius/customer-form/', views.property_customer_form, {'property_code': 'Med'}, name='medius_form'),
    path('stardeous/customer-form/', views.property_customer_form, {'property_code': 'Star'}, name='stardeous_form'),
    
    # Keep your existing URLs exactly as they were working
    path('verification/', views.customer_verification_view, name='customer_verification'),
    path('user-login/', views.customer_verification_view, name='user_login'),
    path('submit/', views.customer_submit_view, name='submit'),
    path('thank-you/', views.thank_you, name='thank_you'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('customer/<int:pk>/edit/', views.edit_customer, name='edit_customer'),
    path('customer/<int:customer_id>/assessment/', views.internal_sales_assessment, name='internal_sales_assessment'),
    path('customer/<int:customer_id>/booking/', views.booking_form_view, name='booking_form'),
    path('export-leads/', views.export_leads, name='export_leads'),
]