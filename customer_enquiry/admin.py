from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponse
import csv
from datetime import datetime

from .models import Customer, CustomerSource, ChannelPartner, Referral, InternalSalesAssessment
from .models import BookingApplication, BookingApplicant, BookingChannelPartner, Project

# Inline Admin Classes
class CustomerSourceInline(admin.TabularInline):
    """Inline admin for customer sources"""
    model = CustomerSource
    extra = 1
    verbose_name = "Source of Visit"
    verbose_name_plural = "Sources of Visit"


class ChannelPartnerInline(admin.StackedInline):
    """Inline admin for channel partner details"""
    model = ChannelPartner
    extra = 0
    verbose_name = "Channel Partner Details"


class ReferralInline(admin.StackedInline):
    """Inline admin for referral details"""
    model = Referral
    extra = 0
    verbose_name = "Referral Details"


# Main Admin Classes
class CustomerAdmin(admin.ModelAdmin):
    """Admin configuration for Customer model"""
    
    list_display = [
        'form_number',
        'get_full_name',
        'email',
        'get_location',
        'nationality',
        'employment_type',
        'configuration',
        'budget',
        'created_at_formatted',
    ]
    
    list_filter = [
        'nationality',
        'employment_type',
        'configuration',
        'budget',
        'construction_status',
        'purpose_of_buying',
        'created_at',
    ]
    
    search_fields = [
        'form_number',
        'first_name',
        'last_name',
        'email',
        'city',
        'locality',
        'company_name',
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Form Information', {
            'fields': ('form_number', 'form_date')
        }),
        ('Personal Details', {
            'fields': (
                ('first_name', 'middle_name', 'last_name'),
                ('email', 'date_of_birth'),
                'residential_address',
                ('city', 'locality'),
                ('pincode', 'nationality')
            )
        }),
        ('Employment Details', {
            'fields': (
                'employment_type',
                ('company_name', 'designation'),
                'industry'
            )
        }),
        ('Requirements', {
            'fields': (
                ('configuration', 'budget'),
                ('construction_status', 'purpose_of_buying')
            )
        }),
        ('Source Information', {
            'fields': ('source_details',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [CustomerSourceInline, ChannelPartnerInline, ReferralInline]
    
    list_per_page = 25
    date_hierarchy = 'created_at'
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = "Full Name"
    
    def get_location(self, obj):
        return f"{obj.city}, {obj.locality}"
    get_location.short_description = "Location"
    
    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%d %b, %Y")
    created_at_formatted.short_description = "Inquiry Date"
    created_at_formatted.admin_order_field = 'created_at'


class CustomerSourceAdmin(admin.ModelAdmin):
    """Admin for CustomerSource model"""
    
    list_display = ['customer_name', 'source_type', 'customer_email']
    list_filter = ['source_type']
    search_fields = ['customer__first_name', 'customer__last_name', 'customer__email']
    
    def customer_name(self, obj):
        return obj.customer.get_full_name()
    customer_name.short_description = "Customer Name"
    
    def customer_email(self, obj):
        return obj.customer.email
    customer_email.short_description = "Email"


class ChannelPartnerAdmin(admin.ModelAdmin):
    """Admin for ChannelPartner model"""
    
    list_display = ['partner_name', 'company_name', 'mobile_number', 'customer_name']
    search_fields = ['partner_name', 'company_name', 'mobile_number']
    
    def customer_name(self, obj):
        return obj.customer.get_full_name()
    customer_name.short_description = "Customer"


class ReferralAdmin(admin.ModelAdmin):
    """Admin for Referral model"""
    
    list_display = ['referral_name', 'project_name', 'customer_name']
    search_fields = ['referral_name', 'project_name']
    
    def customer_name(self, obj):
        return obj.customer.get_full_name()
    customer_name.short_description = "Customer"


# Register all models
admin.site.register(Customer, CustomerAdmin)
admin.site.register(CustomerSource, CustomerSourceAdmin)
admin.site.register(ChannelPartner, ChannelPartnerAdmin)
admin.site.register(Referral, ReferralAdmin)

# Customize admin site
admin.site.site_header = "Customer Enquiry Management"
admin.site.site_title = "Customer Admin"
admin.site.index_title = "Welcome to Customer Management"


@admin.register(InternalSalesAssessment)
class InternalSalesAssessmentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'lead_classification', 'customer_classification', 'sales_manager', 'created_at')
    list_filter = ('lead_classification', 'customer_classification', 'customer_gender', 'created_at')
    search_fields = ('customer__first_name', 'customer__last_name', 'sales_manager', 'sourcing_manager')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Customer Information', {
            'fields': ('customer',)
        }),
        ('GRE Information', {
            'fields': ('sourcing_manager', 'sales_manager', 'customer_gender', 'facilitated_by_pre_sales', 'executive_name')
        }),
        ('Sales Manager Assessment', {
            'fields': ('lead_classification', 'customer_classification', 'reason_for_closed')
        }),
        ('Current Residence', {
            'fields': ('current_residence_config', 'current_residence_ownership', 'family_size')
        }),
        ('Requirements', {
            'fields': ('desired_flat_area', 'source_of_funding', 'ethnicity')
        }),
        ('Additional Information', {
            'fields': ('other_projects_considered', 'sales_manager_remarks')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )





# Register for the booking modal    



class BookingApplicantInline(admin.TabularInline):
    model = BookingApplicant
    extra = 1  # Number of empty forms displayed
    show_change_link = True


class BookingChannelPartnerInline(admin.StackedInline):
    model = BookingChannelPartner
    extra = 0
    max_num = 1
    show_change_link = True


@admin.register(BookingApplication)
class BookingApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'customer',
        'project_name',
        'application_date',
        'total_purchase_price',
        'sales_manager_name',
        'created_at',
    )
    list_filter = ('project_name', 'application_date')
    search_fields = ('customer__first_name', 'customer__last_name', 'project_name')
    inlines = [BookingApplicantInline, BookingChannelPartnerInline]
    date_hierarchy = 'application_date'
    ordering = ('-created_at',)


@admin.register(BookingApplicant)
class BookingApplicantAdmin(admin.ModelAdmin):
    list_display = ('get_full_name', 'applicant_order', 'booking_application')
    list_filter = ('employment_type', 'marital_status', 'residential_status')
    search_fields = ('first_name', 'last_name', 'mobile')


@admin.register(BookingChannelPartner)
class BookingChannelPartnerAdmin(admin.ModelAdmin):
    list_display = ('name', 'mobile', 'booking_application')
    search_fields = ('name', 'mobile')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """Admin configuration for Project model"""

    list_display = [
        'project_name',
        'site_name',
        'project_prefix',
        'form_number',
        'company_name',
        'maharera_no',
        'is_active',
        'created_at'
    ]

    list_filter = [
        'is_active',
        'company_name',
        'created_at'
    ]

    search_fields = [
        'project_name',
        'site_name',
        'project_prefix',
        'form_number',
        'company_name',
        'maharera_no'
    ]

    readonly_fields = ['created_at', 'updated_at', 'form_number']

    fieldsets = (
        ('Project Information', {
            'fields': (
                'project_name',
                'site_name',
                'address',
                'project_prefix',
                'form_number',
                'project_logo'
            )
        }),
        ('Company Details', {
            'fields': (
                'company_name',
                'maharera_no'
            )
        }),
        ('System Settings', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    list_per_page = 25
    date_hierarchy = 'created_at'

    def get_readonly_fields(self, request, obj=None):
        """Form number is always readonly since it's auto-generated"""
        return self.readonly_fields