from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('customer_enquiry', '0016_fix_gre_assessment_lead_classification'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChannelPartnerMaster',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_name', models.CharField(max_length=200)),
                ('partner_name', models.CharField(max_length=100)),
                ('mobile_number', models.CharField(
                    max_length=10,
                    validators=[django.core.validators.RegexValidator(
                        regex=r'^\d{10}$',
                        message='Mobile number must be 10 digits'
                    )]
                )),
                ('rera_number', models.CharField(blank=True, max_length=50)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Channel Partner (Master)',
                'verbose_name_plural': 'Channel Partners (Master)',
                'db_table': 'channel_partner_master',
                'ordering': ['company_name'],
            },
        ),
    ]
