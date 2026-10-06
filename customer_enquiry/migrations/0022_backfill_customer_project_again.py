from django.db import migrations


def backfill_customer_project(apps, schema_editor):
    """
    Re-run of the 0019 backfill for customers saved WITHOUT a project since then
    (the form's partial "Save" used to create customers without Customer.project).
    Longest matching 'PREFIX-' of the form_number wins, so 'STAR-PHASE1' beats 'STAR'.
    """
    Customer = apps.get_model('customer_enquiry', 'Customer')
    Project = apps.get_model('customer_enquiry', 'Project')

    projects = list(Project.objects.exclude(project_prefix='').exclude(project_prefix=None))
    if not projects:
        return
    prefix_map = sorted(
        ((f"{p.project_prefix.upper()}-", p) for p in projects),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for customer in Customer.objects.filter(project__isnull=True).iterator():
        fn = (customer.form_number or '').upper()
        for prefix, project in prefix_map:
            if fn.startswith(prefix):
                customer.project = project
                customer.save(update_fields=['project'])
                break


class Migration(migrations.Migration):

    dependencies = [
        ('customer_enquiry', '0021_additionalchannelpartner_rera_status_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_customer_project, migrations.RunPython.noop),
    ]
