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
    path('save-step/', views.save_step_view, name='save_step'),
    path('thank-you/', views.thank_you, name='thank_you'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('panel/admin/dashboard/', views.dashboard, name='admin_dashboard'),
    path('panel/super-admin/dashboard/', views.dashboard, name='super_admin_dashboard'),
    path('panel/gre/dashboard/', views.dashboard, name='gre_dashboard'),
    path('customer/<int:pk>/edit/', views.edit_customer, name='edit_customer'),
    path('customer/<int:customer_id>/assessment/', views.internal_sales_assessment, name='internal_sales_assessment'),
    path('customer/<int:customer_id>/booking/', views.booking_form_view, name='booking_form'),
    path('export-leads/', views.export_leads, name='export_leads'),
    path('get-project-data/', views.get_project_data, name='get_project_data'),
    path('send-otp/', views.send_otp_view, name='send_otp'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    
    # Password Reset via WhatsApp OTP
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset-verify/', views.password_reset_verify, name='password_reset_verify'),
    path('password-reset-new/', views.password_reset_new, name='password_reset_new'),
    path('password-reset-done/', views.password_reset_done, name='password_reset_done'),
    path('password-reset-complete/', views.password_reset_complete, name='password_reset_complete'),

    # Role-based dashboards
    path('sourcing-dashboard/', views.sourcing_manager_dashboard, name='sourcing_manager_dashboard'),
    path('closing-dashboard/', views.closing_manager_dashboard, name='closing_manager_dashboard'),

    # Admin: User management
    path('manage-users/', views.manage_users, name='manage_users'),

    # Admin: Assign customer to managers
    path('customer/<int:customer_id>/assign/', views.assign_customer, name='assign_customer'),

    # Audit trail
    path('audit-trail/', views.audit_trail, name='audit_trail'),

    # Revisit
    path('customer/<int:customer_id>/revisit/', views.add_revisit, name='add_revisit'),
    path('customer/<int:customer_id>/revisit-history/', views.revisit_history, name='revisit_history'),

    # Additional Channel Partner removal / add
    path('additional-cp/<int:cp_id>/remove/', views.remove_additional_cp, name='remove_additional_cp'),
    path('customer/<int:customer_id>/add-cp/', views.add_additional_cp, name='add_additional_cp'),

    # Master Channel Partners directory
    path('manage-channel-partners/', views.manage_channel_partners, name='manage_channel_partners'),
    path('api/channel-partners/', views.channel_partners_api, name='channel_partners_api'),
]