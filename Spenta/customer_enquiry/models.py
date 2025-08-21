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
    
    # Employment Type Choices
    EMPLOYMENT_CHOICES = [
        ('salaried', 'Salaried'),
        ('business', 'Business'),
        ('professional', 'Professional'),
        ('retired', 'Retired'),
        ('homemaker', 'Homemaker'),
    ]
    
    # Configuration Choices
    CONFIGURATION_CHOICES = [
        ('2bhk', '2 BHK'),
        ('3bhk', '3 BHK'),
        ('4bhk', '4 BHK'),
    ]
    
    # Budget Choices
    BUDGET_CHOICES = [
        ('3.5-4.00cr', '3.5 - 4.00 Cr.'),
        ('4.5-5.00cr', '4.5 - 5.00 Cr.'),
        ('6.00-7.00cr', '6.00 - 7.00 Cr.'),
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
    date_of_birth = models.DateField()
    residential_address = models.TextField()
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
        max_length=10,
        choices=CONFIGURATION_CHOICES
    )
    budget = models.CharField(
        max_length=15,
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