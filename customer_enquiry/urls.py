from django.urls import path
from customer_enquiry import views

app_name = 'customer_enquiry'

urlpatterns = [
    # Main verification page (home page)
    path('', views.customer_verification_view, name='verification'),
    
    # Property-specific verification URLs - UPDATED WITH ALL 5 PROPERTIES
    path('altavista/', views.property_verification_view, {'property_code': 'Alt'}, name='altavista_verification'),
    path('ornata/', views.property_verification_view, {'property_code': 'Orn'}, name='ornata_verification'),  # NEW
    path('medius/', views.property_verification_view, {'property_code': 'Med'}, name='medius_verification'),  # UPDATED
    path('spenta-stardeous/', views.property_verification_view, {'property_code': 'Star'}, name='stardeous_verification'),  # UPDATED
    path('spenta-anthea/', views.property_verification_view, {'property_code': 'Ant'}, name='anthea_verification'),  # NEW
    
    # Customer form page (requires verification)
    path('customer-form/', views.index, name='customer_form'),
    
    # Property-specific customer form URLs - UPDATED WITH ALL 5 PROPERTIES
    path('altavista/customer-form/', views.property_customer_form, {'property_code': 'Alt'}, name='altavista_form'),
    path('ornata/customer-form/', views.property_customer_form, {'property_code': 'Orn'}, name='ornata_form'),  # NEW
    path('medius/customer-form/', views.property_customer_form, {'property_code': 'Med'}, name='medius_form'),  # UPDATED
    path('spenta-stardeous/customer-form/', views.property_customer_form, {'property_code': 'Star'}, name='stardeous_form'),  # UPDATED
    path('spenta-anthea/customer-form/', views.property_customer_form, {'property_code': 'Ant'}, name='anthea_form'),  # NEW
    
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
    path('get-project-data/', views.get_project_data, name='get_project_data'),
    
    # Password Reset URLs
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset-done/', views.password_reset_done, name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('password-reset-complete/', views.password_reset_complete, name='password_reset_complete'),
]