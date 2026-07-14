from django.db import migrations, models


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS detentions_detentionmemo (
    id uuid NOT NULL PRIMARY KEY,
    case_no varchar(120) NOT NULL DEFAULT '',
    reference_number varchar(200) NOT NULL DEFAULT '',
    fir_number varchar(120) NOT NULL DEFAULT '',
    date_time_occurrence varchar(80) NOT NULL DEFAULT '',
    place_of_occurrence varchar(300) NOT NULL DEFAULT '',
    date_time_detention varchar(80) NOT NULL DEFAULT '',
    place_of_detention varchar(300) NOT NULL DEFAULT '',
    detention_type varchar(80) NOT NULL DEFAULT '',
    directorate varchar(200) NOT NULL DEFAULT '',
    reason_for_detention varchar(200) NOT NULL DEFAULT '',
    location_of_detention varchar(300) NOT NULL DEFAULT '',
    gd_number varchar(120) NOT NULL DEFAULT '',
    gd_number_2 varchar(120) NOT NULL DEFAULT '',
    where_deposited varchar(400) NOT NULL DEFAULT '',
    search_chassis_number varchar(120) NOT NULL DEFAULT '',
    receipt_officer varchar(200) NOT NULL DEFAULT '',
    settlement_status varchar(80) NOT NULL DEFAULT '',
    verification_status varchar(80) NOT NULL DEFAULT '',
    disposition_status varchar(80) NOT NULL DEFAULT '',
    brief_facts text NOT NULL DEFAULT '',
    forwarding_officer_remarks text NOT NULL DEFAULT '',
    purpose_of_detention text NOT NULL DEFAULT '',
    owner_name varchar(200) NOT NULL DEFAULT '',
    owner_cnic varchar(30) NOT NULL DEFAULT '',
    owner_contact varchar(50) NOT NULL DEFAULT '',
    owner_picture text NOT NULL DEFAULT '',
    owner_photo_upload varchar(100) NULL,
    driver_name varchar(200) NOT NULL DEFAULT '',
    driver_cnic varchar(30) NOT NULL DEFAULT '',
    driver_contact varchar(50) NOT NULL DEFAULT '',
    driver_picture text NOT NULL DEFAULT '',
    driver_photo_upload varchar(100) NULL,
    seizing_officer_notes text NOT NULL DEFAULT '',
    examining_officer_notes text NOT NULL DEFAULT '',
    detention_notes text NOT NULL DEFAULT '',
    memo_qr_code_number varchar(160) NOT NULL DEFAULT '',
    memo_qr_code_payload text NOT NULL DEFAULT '',
    created_by varchar(150) NOT NULL DEFAULT '',
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
"""


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="DetentionMemo",
                    fields=[
                        ("id", models.UUIDField(primary_key=True, serialize=False)),
                        ("disposition_status", models.CharField(blank=True, default="", max_length=80)),
                    ],
                    options={"managed": False},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=_CREATE_TABLE_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE detentions_detentionmemo "
                        "ADD COLUMN IF NOT EXISTS disposition_status varchar(80) NOT NULL DEFAULT ''"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
