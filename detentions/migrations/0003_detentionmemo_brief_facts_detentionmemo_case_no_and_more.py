import uuid

import detentions.models
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("detentions", "0002_alter_detentionmemo_options_depositaccountentry_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="detentionmemo",
            name="brief_facts",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="case_no",
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="created_by",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="date_time_detention",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="date_time_occurrence",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="detention_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="detention_type",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="directorate",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="driver_cnic",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="driver_contact",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="driver_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="driver_photo_upload",
            field=models.FileField(blank=True, null=True, upload_to=detentions.models.detention_driver_photo_path),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="driver_picture",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="examining_officer_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="fir_number",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="forwarding_officer_remarks",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="gd_number",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="gd_number_2",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="location_of_detention",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="memo_qr_code_number",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="memo_qr_code_payload",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="owner_cnic",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="owner_contact",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="owner_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="owner_photo_upload",
            field=models.FileField(blank=True, null=True, upload_to=detentions.models.detention_owner_photo_path),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="owner_picture",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="place_of_detention",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="place_of_occurrence",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="purpose_of_detention",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="reason_for_detention",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="receipt_officer",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="reference_number",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="search_chassis_number",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="seizing_officer_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="settlement_status",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="verification_status",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="detentionmemo",
            name="where_deposited",
            field=models.CharField(blank=True, max_length=400),
        ),
        migrations.AlterField(
            model_name="detentionmemo",
            name="disposition_status",
            field=models.CharField(
                blank=True,
                default="",
                help_text="e.g. In Warehouse, Destructed, Released",
                max_length=80,
            ),
        ),
        migrations.AlterField(
            model_name="detentionmemo",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
        ),
    ]
