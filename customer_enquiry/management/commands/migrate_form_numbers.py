from django.core.management.base import BaseCommand
from django.db import transaction
from customer_enquiry.models import Customer, Project
import random
import re


class Command(BaseCommand):
    help = 'Migrate old customer form numbers to new format (PREFIX-12345)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )

        # Get all customers with old format form numbers
        customers = Customer.objects.all()
        updated_count = 0
        skipped_count = 0

        # Get all active projects for prefix mapping
        projects = {p.project_prefix.upper(): p for p in Project.objects.active_projects()}

        with transaction.atomic():
            for customer in customers:
                old_form_number = customer.form_number

                # Check if already in new format (contains single dash with 5 digits after)
                if re.match(r'^[A-Z]{2,5}-\d{5}$', old_form_number):
                    self.stdout.write(f'Skipping {old_form_number} - already in new format')
                    skipped_count += 1
                    continue

                # Extract prefix from old form number
                prefix = self.extract_prefix(old_form_number)

                # Validate prefix exists in projects
                if prefix not in projects:
                    self.stdout.write(
                        self.style.WARNING(f'No project found for prefix "{prefix}" in form number {old_form_number}')
                    )
                    skipped_count += 1
                    continue

                # Generate new form number
                new_form_number = self.generate_new_form_number(prefix)

                if not dry_run:
                    customer.form_number = new_form_number
                    customer.save()

                self.stdout.write(f'Updated: {old_form_number} -> {new_form_number}')
                updated_count += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'DRY RUN COMPLETE: Would update {updated_count} customers, skip {skipped_count}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully updated {updated_count} customers, skipped {skipped_count}')
            )

    def extract_prefix(self, form_number):
        """Extract prefix from various form number formats"""
        if not form_number:
            return 'UNK'

        form_upper = form_number.upper()

        # Try to find known prefixes
        prefixes = ['STAR', 'ANT', 'ORN', 'MED', 'ALT']
        for prefix in prefixes:
            if form_upper.startswith(prefix):
                return prefix

        # Extract first 2-4 characters as prefix
        if '-' in form_number:
            return form_number.split('-')[0].upper()
        else:
            # Take first 3 characters
            return form_number[:3].upper()

    def generate_new_form_number(self, prefix):
        """Generate unique new format form number"""
        while True:
            random_number = random.randint(10000, 99999)
            new_form_number = f"{prefix}-{random_number}"

            # Check if this form number already exists
            if not Customer.objects.filter(form_number=new_form_number).exists():
                return new_form_number