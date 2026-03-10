from django.db import migrations


def fix_gre_assessments(apps, schema_editor):
    """
    Reset lead_classification for assessments that were auto-populated
    with 'warm' but never had Steps 2-5 actually filled by a closing manager/admin.
    An assessment is considered GRE-only if lead_classification is 'warm'
    AND none of the Step 3-5 fields have real content.
    """
    InternalSalesAssessment = apps.get_model('customer_enquiry', 'InternalSalesAssessment')

    for obj in InternalSalesAssessment.objects.filter(lead_classification='warm'):
        # If Steps 3-5 key fields are all empty, this was auto-populated by GRE submit
        step3_empty = not obj.current_residence_ownership  # Step 3 field GRE can't fill
        step4_empty = not obj.source_of_funding            # Step 4 field GRE can't fill
        if step3_empty and step4_empty:
            obj.lead_classification = ''
            obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ('customer_enquiry', '0015_alter_customer_budget_alter_customer_city_and_more'),
    ]

    operations = [
        migrations.RunPython(fix_gre_assessments, migrations.RunPython.noop),
    ]
