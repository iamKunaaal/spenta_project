from django.db import models
from django.core.validators import RegexValidator, EmailValidator
from django.utils import timezone


class Customer(models.Model):
    """
    Main customer information model that stores all form data
    """
    
    # Nationality Choices
    NATIONALITY_CHOICES = [
        ('indian', 'Indian'),
        ('nri', 'NRI'),
        ('pio', 'PIO'),
        ('oci', 'OCI'),
    ]
    
    # Employment Type Choices - UPDATED: Added "Other" option
    EMPLOYMENT_CHOICES = [
        ('salaried', 'Salaried'),
        ('business', 'Business'),
        ('professional', 'Professional'),
        ('retired', 'Retired'),
        ('homemaker', 'Homemaker'),
        ('other', 'Other'),  # NEW OPTION ADDED
    ]
    
    # NEW: Sex/Gender Choices
    SEX_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]
    
    # NEW: Marital Status Choices
    MARITAL_STATUS_CHOICES = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
        ('other', 'Other'),
    ]
    
    # Configuration Choices - UPDATED: Added more BHK options, Duplex, and Other
    CONFIGURATION_CHOICES = [
        ('1bhk', '1 BHK'),
        ('1.5bhk', '1.5 BHK'),
        ('2bhk', '2 BHK'),
        ('2.5bhk', '2.5 BHK'),
        ('3bhk', '3 BHK'),
        ('3.5bhk', '3.5 BHK'),
        ('4bhk', '4 BHK'),
        ('duplex', 'Duplex'),
        ('other_config', 'Other'),
    ]
    
    # Budget Choices - COMPLETELY UPDATED with new ranges
    BUDGET_CHOICES = [
        ('less_than_1cr', 'Less than 1 Cr.'),
        ('1cr_to_2cr', '1 Cr. to 2 Cr.'),
        ('2cr_to_4cr', '2 Cr. to 4 Cr.'),
        ('4cr_to_6cr', '4 Cr. to 6 Cr.'),
        ('more_than_6cr', 'More than 6 Cr.'),
    ]
    
    # Construction Status Choices
    CONSTRUCTION_STATUS_CHOICES = [
        ('under_construction', 'Under Construction (>1 yr)'),
        ('near_completion', 'Near Completion (<1 yr)'),
        ('ready_possession', 'Ready Possession'),
    ]
    
    # Purpose of Buying Choices
    PURPOSE_CHOICES = [
        ('personal_use', 'Personal Use'),
        ('investment', 'Investment'),
        ('second_home', 'Second Home'),
        ('gift', 'Gift'),
    ]
    
    # Form Meta Information
    form_number = models.CharField(
        max_length=20, 
        unique=True,
        help_text="Auto-generated form number"
    )
    form_date = models.DateField(default=timezone.now)
    
    # Personal Details
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(validators=[EmailValidator()])
    
    # ADDED: Phone number field with validation
    phone_number = models.CharField(
        max_length=10,
        validators=[RegexValidator(
            regex=r'^\d{10}$',
            message='Phone number must be 10 digits'
        )],
        blank=True,
        null=True,
        help_text="10-digit phone number"
    )
    
    # NEW: Sex/Gender field
    sex = models.CharField(
        max_length=10,
        choices=SEX_CHOICES,
        blank=True,
        help_text="Gender/Sex of the customer"
    )
    
    # NEW: Marital Status field
    marital_status = models.CharField(
        max_length=15,
        choices=MARITAL_STATUS_CHOICES,
        blank=True,
        help_text="Marital status of the customer"
    )
    
    date_of_birth = models.DateField(blank=True, null=True)
    residential_address = models.TextField(blank=True)
    city = models.CharField(max_length=100)
    locality = models.CharField(max_length=100)
    
    # Pincode with validation
    pincode = models.CharField(
        max_length=6,
        validators=[RegexValidator(
            regex=r'^\d{6}$',
            message='Pincode must be 6 digits'
        )]
    )
    
    nationality = models.CharField(
        max_length=10,
        choices=NATIONALITY_CHOICES
    )
    
    # Employment Details
    employment_type = models.CharField(
        max_length=15,
        choices=EMPLOYMENT_CHOICES
    )
    company_name = models.CharField(max_length=200, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    
    # Customer Requirements
    configuration = models.CharField(
        max_length=15,  # Increased length to accommodate new options
        choices=CONFIGURATION_CHOICES
    )
    budget = models.CharField(
        max_length=20,  # Increased length for new budget ranges
        choices=BUDGET_CHOICES
    )
    construction_status = models.CharField(
        max_length=20,
        choices=CONSTRUCTION_STATUS_CHOICES
    )
    purpose_of_buying = models.CharField(
        max_length=15,
        choices=PURPOSE_CHOICES
    )
    
    # Source Details
    source_details = models.TextField(
        blank=True,
        help_text="Additional details for Newspaper Ad, Social Media, Exhibition, or Property Portal"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'customers'
        ordering = ['-created_at']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.form_number}"
    
    def get_full_name(self):
        """Return the customer's full name"""
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
    def get_complete_address(self):
        """Return complete formatted address"""
        return f"{self.residential_address}, {self.locality}, {self.city} - {self.pincode}"
    
    def get_display_phone(self):
        """Return formatted phone number for display"""
        if self.phone_number:
            # Format as: XXX-XXX-XXXX
            phone = str(self.phone_number)
            if len(phone) == 10:
                return f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
        return self.phone_number or "Not Provided"


class CustomerSource(models.Model):
    """
    Model to handle multiple sources of visit for each customer
    """
    
    SOURCE_CHOICES = [
        ('channel_partner', 'Channel Partner'),
        ('referral', 'Referral'),
        ('whatsapp', 'WhatsApp'),
        ('social_media', 'Social Media (Facebook, Google, etc.)'),
        ('website', 'Website'),
        ('passing_by', 'Passing by'),
        ('property_portal', 'Property Search Portal'),
        ('hoarding', 'Hoarding'),
        ('newspaper_ad', 'Newspaper Ad'),
        ('exhibition', 'Exhibition'),
    ]
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='sources'
    )
    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES
    )
    
    class Meta:
        db_table = 'customer_sources'
        unique_together = ('customer', 'source_type')
        verbose_name = 'Customer Source'
        verbose_name_plural = 'Customer Sources'
    
    def __str__(self):
        return f"{self.customer.get_full_name()} - {self.get_source_type_display()}"


class ChannelPartner(models.Model):
    """
    Model for Channel Partner details (appears when Channel Partner is selected as source)
    """
    
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name='channel_partner'
    )
    company_name = models.CharField(max_length=200)
    partner_name = models.CharField(max_length=100)
    
    # Mobile number with validation
    mobile_number = models.CharField(
        max_length=10,
        validators=[RegexValidator(
            regex=r'^\d{10}$',
            message='Mobile number must be 10 digits'
        )]
    )
    
    rera_number = models.CharField(
        max_length=50,
        help_text="Real Estate Regulatory Authority Number"
    )
    
    class Meta:
        db_table = 'channel_partners'
        verbose_name = 'Channel Partner'
        verbose_name_plural = 'Channel Partners'
    
    def __str__(self):
        return f"{self.partner_name} - {self.company_name}"


class Referral(models.Model):
    """
    Model for Referral details (appears when Referral is selected as source)
    """
    
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name='referral'
    )
    referral_name = models.CharField(max_length=100)
    project_name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'referrals'
        verbose_name = 'Referral'
        verbose_name_plural = 'Referrals'
    
    def __str__(self):
        return f"{self.referral_name} - {self.project_name}"


# Custom Manager for Customer model with useful querysets
class CustomerManager(models.Manager):
    """
    Custom manager for Customer model with helpful methods
    """
    
    def get_by_form_number(self, form_number):
        """Get customer by form number"""
        return self.get(form_number=form_number)
    
    def by_nationality(self, nationality):
        """Filter customers by nationality"""
        return self.filter(nationality=nationality)
    
    def by_employment_type(self, employment_type):
        """Filter customers by employment type"""
        return self.filter(employment_type=employment_type)
    
    def by_budget_range(self, budget):
        """Filter customers by budget range"""
        return self.filter(budget=budget)
    
    def by_configuration(self, configuration):
        """Filter customers by property configuration"""
        return self.filter(configuration=configuration)
    
    def recent_inquiries(self, days=30):
        """Get customers who inquired in the last N days"""
        from django.utils import timezone
        from datetime import timedelta
        
        since_date = timezone.now() - timedelta(days=days)
        return self.filter(created_at__gte=since_date)
    
    def with_channel_partners(self):
        """Get customers who came through channel partners"""
        return self.filter(sources__source_type='channel_partner')
    
    def with_referrals(self):
        """Get customers who came through referrals"""
        return self.filter(sources__source_type='referral')


# Add the custom manager to Customer model
Customer.add_to_class('objects', CustomerManager())


class InternalSalesAssessment(models.Model):
    """
    Internal sales team assessment form for existing customers
    """
    
    # Link to customer
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name='sales_assessment'
    )
    
    # TO BE FILLED BY GRE Section
    sourcing_manager = models.CharField(max_length=100, blank=True)
    sales_manager = models.CharField(max_length=100, blank=True)
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('family', 'Family'),
    ]
    customer_gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    
    facilitated_by_pre_sales = models.BooleanField(default=False)
    executive_name = models.CharField(max_length=100, blank=True)
    
    # TO BE FILLED BY SALES MANAGER Section
    LEAD_CLASSIFICATION_CHOICES = [
        ('hot', 'Hot'),
        ('warm', 'Warm'),
        ('cold', 'Cold'),
        ('lost', 'Lost'),
    ]
    lead_classification = models.CharField(max_length=10, choices=LEAD_CLASSIFICATION_CHOICES, blank=True)
    
    # Reason for Lost (shows only if Lost is selected)
    REASON_FOR_LOST_CHOICES = [
        ('construction_issue', 'Construction Issue'),
        ('project_issue', 'Project Issue'),
        ('developer_history', 'Developer History'),
        ('budget_issue', 'Budget Issue'),
        ('google_reviews', 'Google Reviews'),
        ('not_responding', 'Not Responding'),
        ('booked_with_competition', 'Booked with competition'),
        ('pricing_issue', 'Pricing issue'),
        ('rtmi', 'RTMI'),
        ('csop', 'CSOP'),
        ('possession_timeline', 'Possession Timeline'),
        ('no_reason_given', 'No Reason Given'),
        ('casual_buyer', 'Casual Buyer'),
        ('postponed_decision', 'Postponed The Decision'),
        ('needs_time', 'Needs Time'),
        ('wrong_number', 'Wrong number'),
        ('inventory_issue', 'Inventory issue'),
        ('serial_vdnb', 'Serial VDNB'),
        ('view_issue', 'View issue'),
        ('plan_dropped', 'Plan Dropped'),
        ('configuration_issue', 'Configuration Issue'),
        ('not_interested', 'Not Interested'),
        ('location_issue', 'Location issue'),
        ('vastu_issue', 'Vastu Issue'),
        ('looking_for_commercial', 'Looking For Commercial'),
        ('channel_partner', 'Channel Partner'),
        ('competition', 'Competition'),
    ]
    reason_for_lost = models.CharField(max_length=30, choices=REASON_FOR_LOST_CHOICES, blank=True)
    
    # Keep old fields for backward compatibility (can be removed in future migration)
    customer_classification = models.CharField(max_length=10, blank=True)  # Legacy field
    reason_for_closed = models.CharField(max_length=20, blank=True)  # Legacy field
    
    # Customer's Current Residence
    CURRENT_RESIDENCE_CONFIG_CHOICES = [
        ('1bhk', '1 BHK'),
        ('1.5bhk', '1.5 BHK'),
        ('2bhk', '2 BHK'),
        ('2.5bhk', '2.5 BHK'),
        ('3bhk', '3 BHK'),
        ('3.5bhk', '3.5 BHK'),
        ('4bhk', '4 BHK'),
        ('duplex', 'Duplex'),
        ('other', 'Other'),
    ]
    current_residence_config = models.CharField(max_length=10, choices=CURRENT_RESIDENCE_CONFIG_CHOICES, blank=True)
    
    OWNERSHIP_CHOICES = [
        ('family_owned', 'Family Owned'),
        ('self_owned', 'Self-Owned'),
        ('rented', 'Rented'),
        ('pagdi', 'Pagdi'),
    ]
    current_residence_ownership = models.CharField(max_length=15, choices=OWNERSHIP_CHOICES, blank=True)
    
    # NEW: Plot field
    plot = models.CharField(max_length=200, blank=True, help_text="Plot details")
    
    FAMILY_SIZE_CHOICES = [
        ('1', '1'),
        ('2', '2'),
        ('3', '3'),
        ('4', '4'),
        ('5', '5'),
        ('6', '6'),
        ('6+', '>6'),
    ]
    family_size = models.CharField(max_length=5, choices=FAMILY_SIZE_CHOICES, blank=True)
    
    # Customer's Desired Requirement
    # NEW: Updated field name to match template
    area_looking = models.TextField(blank=True, help_text="Type/Area of flat customer is looking for")
    
    # Keep old field for backward compatibility
    desired_flat_area = models.CharField(max_length=100, blank=True, help_text="Area of flat customer is looking for (Legacy)")
    
    FUNDING_SOURCE_CHOICES = [
        ('self-funding', 'Self-Funding'),
        ('current-property-sale', 'Current Property Sale'),
        ('loan', 'Loan'),
    ]
    source_of_funding = models.CharField(max_length=25, choices=FUNDING_SOURCE_CHOICES, blank=True)
    
    ETHNICITY_CHOICES = [
        ('hindu', 'Hindu'),
        ('maharashtrian', 'Maharashtrian'),
        ('other', 'Other'),
    ]
    ethnicity = models.CharField(max_length=15, choices=ETHNICITY_CHOICES, blank=True)
    
    # Text areas
    other_projects_considered = models.TextField(blank=True, help_text="Other Projects Considered By The Customer")
    sales_manager_remarks = models.TextField(blank=True, help_text="Sales Manager Remarks About Customer")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'internal_sales_assessments'
        verbose_name = 'Internal Sales Assessment'
        verbose_name_plural = 'Internal Sales Assessments'
    
    def __str__(self):
        return f"Sales Assessment - {self.customer.get_full_name()}"


class BookingApplication(models.Model):
    """
    Main booking application model
    """
    # Link to customer
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.CASCADE, 
        related_name='booking_applications'
    )
    
    # Project and basic details
    project_name = models.CharField(max_length=200, default="Project Name")
    application_date = models.DateField(default=timezone.now)
    
    # Flat details section
    flat_number = models.CharField(max_length=50, blank=True)
    floor = models.CharField(max_length=50, blank=True)
    rera_carpet_area = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    exclusive_deck_balcony = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    car_parking_count = models.IntegerField(default=0)
    total_purchase_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_purchase_price_words = models.TextField(blank=True)
    
    # Source of funds
    self_financed = models.BooleanField(default=False)
    housing_loan = models.BooleanField(default=False)
    
    # Source of booking
    source_direct = models.BooleanField(default=False)
    source_direct_specify = models.CharField(max_length=200, blank=True)
    
    # Referral details
    referral_customer_name = models.CharField(max_length=100, blank=True)
    referral_project = models.CharField(max_length=100, blank=True)
    referral_flat_no = models.CharField(max_length=50, blank=True)
    
    # Payment details
    application_money_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    application_money_words = models.CharField(max_length=500, blank=True)
    gst_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    gst_words = models.CharField(max_length=500, blank=True)
    cheque_dd_no = models.CharField(max_length=100, blank=True)
    instrument_date = models.DateField(null=True, blank=True)
    drawn_on = models.CharField(max_length=200, blank=True)
    gst_cheque_dd_no = models.CharField(max_length=100, blank=True)
    gst_instrument_date = models.DateField(null=True, blank=True)
    gst_drawn_on = models.CharField(max_length=200, blank=True)
    
    # Manager details
    sales_manager_name = models.CharField(max_length=100, blank=True)
    sourcing_manager_name = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_applications'
        ordering = ['-created_at']
        verbose_name = 'Booking Application'
        verbose_name_plural = 'Booking Applications'
    
    def __str__(self):
        return f"Booking - {self.customer.get_full_name()} - {self.project_name}"


class BookingApplicant(models.Model):
    """
    Model for multiple applicants in booking form
    """
    # Choices
    TITLE_CHOICES = [
        ('Mr', 'Mr.'),
        ('Ms', 'Ms.'),
        ('Mrs', 'Mrs.'),
    ]
    
    MARITAL_STATUS_CHOICES = [
        ('married', 'Married'),
        ('unmarried', 'Unmarried'),
        ('other', 'Other'),
    ]
    
    SEX_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('others', 'Others'),
    ]
    
    RESIDENTIAL_STATUS_CHOICES = [
        ('indian', 'Indian'),
        ('nri', 'NRI'),
        ('pio', 'PIO'),
        ('oci', 'OCI'),
    ]
    
    EMPLOYMENT_TYPE_CHOICES = [
        ('salaried', 'Salaried'),
        ('self_employed', 'Self Employed'),
    ]
    
    # Relations
    booking_application = models.ForeignKey(
        BookingApplication, 
        on_delete=models.CASCADE, 
        related_name='applicants'
    )
    applicant_order = models.IntegerField()  # 1, 2, 3, 4
    
    # Personal details
    title = models.CharField(max_length=5, choices=TITLE_CHOICES, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True)  # Allow blank for flexibility
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True)  # Allow blank for flexibility
    date_of_birth = models.DateField(null=True, blank=True)  # Optional - this is correct
    marital_status = models.CharField(max_length=15, choices=MARITAL_STATUS_CHOICES, blank=True)  # Allow blank
    anniversary_date = models.DateField(null=True, blank=True)  # Optional - this is correct
    sex = models.CharField(max_length=10, choices=SEX_CHOICES, blank=True)  # Allow blank
    
    # Documents
    pan_no = models.CharField(max_length=10, blank=True)
    aadhar_no = models.CharField(max_length=12, blank=True)
    residential_status = models.CharField(max_length=15, choices=RESIDENTIAL_STATUS_CHOICES, blank=True)
    
    # Address details
    residential_address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    pin = models.CharField(max_length=6, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='India')
    correspondence_address = models.TextField(blank=True)
    
    # Contact details
    contact_residence = models.CharField(max_length=15, blank=True)
    contact_office = models.CharField(max_length=15, blank=True)
    mobile = models.CharField(max_length=10, blank=True)
    email = models.EmailField(blank=True)
    
    # Employment details
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, blank=True)
    profession = models.CharField(max_length=100, blank=True)
    company_name = models.CharField(max_length=200, blank=True)
    
    class Meta:
        db_table = 'booking_applicants'
        unique_together = ('booking_application', 'applicant_order')
        ordering = ['applicant_order']
        verbose_name = 'Booking Applicant'
        verbose_name_plural = 'Booking Applicants'
    
    def __str__(self):
        return f"{self.get_full_name()} - Applicant {self.applicant_order}"
    
    def get_full_name(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"


class BookingChannelPartner(models.Model):
    """
    Channel partner details for booking
    """
    booking_application = models.OneToOneField(
        BookingApplication,
        on_delete=models.CASCADE,
        related_name='channel_partner'
    )
    
    name = models.CharField(max_length=200, blank=True)
    maharera_registration = models.CharField(max_length=100, blank=True)
    mobile = models.CharField(max_length=10, blank=True)
    email = models.EmailField(blank=True)
    
    class Meta:
        db_table = 'booking_channel_partners'
        verbose_name = 'Booking Channel Partner'
        verbose_name_plural = 'Booking Channel Partners'
    
    def __str__(self):
        return f"Channel Partner - {self.name}"


# Custom Manager for BookingApplication
class BookingApplicationManager(models.Manager):
    """
    Custom manager for booking applications
    """
    
    def for_customer(self, customer):
        """Get all bookings for a specific customer"""
        return self.filter(customer=customer)
    
    def by_project(self, project_name):
        """Filter bookings by project"""
        return self.filter(project_name__icontains=project_name)
    
    def recent_bookings(self, days=30):
        """Get recent bookings"""
        from django.utils import timezone
        from datetime import timedelta
        
        since_date = timezone.now() - timedelta(days=days)
        return self.filter(created_at__gte=since_date)
    
    def with_applicants(self):
        """Get bookings with applicants prefetched"""
        return self.prefetch_related('applicants')

 
# Add custom manager to BookingApplication
BookingApplication.add_to_class('objects', BookingApplicationManager())