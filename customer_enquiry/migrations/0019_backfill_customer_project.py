from django.db import migrations


def backfill_customer_project(apps, schema_editor):
    """
    Populate Customer.project from the form_number prefix.

    Each customer's project is currently inferred from its form_number prefix
    (e.g. 'ALT-49988' -> Altavista). We match against Project.project_prefix,
    choosing the project whose 'PREFIX-' is the LONGEST matching prefix of the
    form_number so compound prefixes (e.g. 'STAR-PHASE1') win over their leading
    token ('STAR').
    """
    Customer = apps.get_model('customer_enquiry', 'Customer')
    Project = apps.get_model('customer_enquiry', 'Project')

    projects = list(Project.objects.exclude(project_prefix='').exclude(project_prefix=None))
    if not projects:
        return

    # (uppercased "PREFIX-", project) sorted by descending prefix length -> longest match first
    prefix_map = sorted(
        ((f"{p.project_prefix.upper()}-", p) for p in projects),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )

    for customer in Customer.objects.filter(project__isnull=True).iterator():
        fn = (customer.form_number or '').upper()
        matched = None
        for prefix, project in prefix_map:
            if fn.startswith(prefix):
                matched = project
                break
        if matched is not None:
            customer.project = matched
            customer.save(update_fields=['project'])


def noop_reverse(apps, schema_editor):
    # Reversing simply clears the FK; the column removal is handled by the schema migration.
    Customer = apps.get_model('customer_enquiry', 'Customer')
    Customer.objects.update(project=None)


class Migration(migrations.Migration):

    dependencies = [
        ('customer_enquiry', '0018_customer_project_userprofile_projects_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_customer_project, noop_reverse),
    ]
