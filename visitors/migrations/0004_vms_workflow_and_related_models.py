# Generated manually — VMS workflow fields and related models
# Idempotent: skips columns/tables that already exist (partial manual schema apply).

from django.db import migrations, models
import django.db.models.deletion


def _visitor_field(name, field):
    return migrations.AddField(model_name="visitor", name=name, field=field)


VISITOR_FIELD_STATE_OPS = [
    _visitor_field("registration_source", models.CharField(blank=True, default="", max_length=30)),
    _visitor_field("registration_status", models.CharField(blank=True, default="approved", max_length=20)),
    _visitor_field("approval_status", models.CharField(blank=True, default="pending", max_length=20)),
    _visitor_field("approved_by", models.CharField(blank=True, default="", max_length=150)),
    _visitor_field("denied_by", models.CharField(blank=True, default="", max_length=150)),
    _visitor_field("rejection_reason", models.TextField(blank=True, default="")),
    _visitor_field("location", models.CharField(blank=True, default="", max_length=30)),
    _visitor_field("registered_by_user_id", models.IntegerField(blank=True, null=True)),
    _visitor_field("registered_by_username", models.CharField(blank=True, default="", max_length=150)),
    _visitor_field("profile_image", models.TextField(blank=True, default="")),
    _visitor_field("guard_entry_time", models.CharField(blank=True, default="", max_length=50)),
    _visitor_field("guard_name", models.CharField(blank=True, default="", max_length=150)),
    _visitor_field("host_notified_at", models.DateTimeField(blank=True, null=True)),
    _visitor_field("extra_data", models.JSONField(blank=True, default=dict)),
]

# Fresh field instances for database apply (must not share with state ops).
VISITOR_FIELD_DB_SPECS = [
    ("registration_source", models.CharField(blank=True, default="", max_length=30)),
    ("registration_status", models.CharField(blank=True, default="approved", max_length=20)),
    ("approval_status", models.CharField(blank=True, default="pending", max_length=20)),
    ("approved_by", models.CharField(blank=True, default="", max_length=150)),
    ("denied_by", models.CharField(blank=True, default="", max_length=150)),
    ("rejection_reason", models.TextField(blank=True, default="")),
    ("location", models.CharField(blank=True, default="", max_length=30)),
    ("registered_by_user_id", models.IntegerField(blank=True, null=True)),
    ("registered_by_username", models.CharField(blank=True, default="", max_length=150)),
    ("profile_image", models.TextField(blank=True, default="")),
    ("guard_entry_time", models.CharField(blank=True, default="", max_length=50)),
    ("guard_name", models.CharField(blank=True, default="", max_length=150)),
    ("host_notified_at", models.DateTimeField(blank=True, null=True)),
    ("extra_data", models.JSONField(blank=True, default=dict)),
]

CREATE_MODEL_STATE_OPS = [
    migrations.CreateModel(
        name="Vehicle",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("plate_number", models.CharField(max_length=50)),
            ("vehicle_type", models.CharField(blank=True, default="", max_length=50)),
            ("contractor_company", models.CharField(blank=True, default="", max_length=200)),
            ("driver_name", models.CharField(blank=True, default="", max_length=150)),
            ("remarks", models.TextField(blank=True, default="")),
            ("extra_data", models.JSONField(blank=True, default=dict)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            (
                "visitor",
                models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="vehicles",
                    to="visitors.visitor",
                ),
            ),
        ],
        options={"ordering": ["-created_at"]},
    ),
    migrations.CreateModel(
        name="VisitorNotification",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("notification_type", models.CharField(default="host_notify", max_length=50)),
            ("recipient", models.CharField(max_length=254)),
            ("message", models.TextField(blank=True, default="")),
            ("success", models.BooleanField(default=True)),
            ("sent_at", models.DateTimeField(auto_now_add=True)),
            (
                "visitor",
                models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="notifications",
                    to="visitors.visitor",
                ),
            ),
        ],
        options={"ordering": ["-sent_at"]},
    ),
    migrations.CreateModel(
        name="VmsListRecord",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("module", models.CharField(db_index=True, max_length=80)),
            ("record_id", models.CharField(max_length=80)),
            ("data", models.JSONField(default=dict)),
            ("location", models.CharField(blank=True, default="", max_length=30)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
        ],
        options={
            "ordering": ["-updated_at"],
            "unique_together": {("module", "record_id")},
        },
    ),
]


def _existing_columns(schema_editor, table_name):
    with schema_editor.connection.cursor() as cursor:
        description = schema_editor.connection.introspection.get_table_description(
            cursor, table_name
        )
    return {col.name for col in description}


def _add_visitor_fields_if_missing(apps, schema_editor):
    Visitor = apps.get_model("visitors", "Visitor")
    table = Visitor._meta.db_table
    existing = _existing_columns(schema_editor, table)

    for name, field in VISITOR_FIELD_DB_SPECS:
        if name in existing:
            continue
        field.set_attributes_from_name(name)
        field.model = Visitor
        schema_editor.add_field(Visitor, field)


def _create_vms_tables_if_missing(apps, schema_editor):
    tables = set(schema_editor.connection.introspection.table_names())
    if schema_editor.connection.vendor != "postgresql":
        if "visitors_vehicle" not in tables:
            schema_editor.create_model(apps.get_model("visitors", "Vehicle"))
        if "visitors_visitornotification" not in tables:
            schema_editor.create_model(apps.get_model("visitors", "VisitorNotification"))
        if "visitors_vmslistrecord" not in tables:
            schema_editor.create_model(apps.get_model("visitors", "VmsListRecord"))
        return

    statements = [
        (
            "visitors_vehicle",
            """
            CREATE TABLE IF NOT EXISTS visitors_vehicle (
                id BIGSERIAL PRIMARY KEY,
                plate_number VARCHAR(50) NOT NULL,
                vehicle_type VARCHAR(50) NOT NULL DEFAULT '',
                contractor_company VARCHAR(200) NOT NULL DEFAULT '',
                driver_name VARCHAR(150) NOT NULL DEFAULT '',
                remarks TEXT NOT NULL DEFAULT '',
                extra_data JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                visitor_id BIGINT NOT NULL REFERENCES visitors_visitor(id)
                    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            );
            """,
        ),
        (
            "visitors_visitornotification",
            """
            CREATE TABLE IF NOT EXISTS visitors_visitornotification (
                id BIGSERIAL PRIMARY KEY,
                notification_type VARCHAR(50) NOT NULL DEFAULT 'host_notify',
                recipient VARCHAR(254) NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                success BOOLEAN NOT NULL DEFAULT TRUE,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                visitor_id BIGINT NOT NULL REFERENCES visitors_visitor(id)
                    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            );
            """,
        ),
        (
            "visitors_vmslistrecord",
            """
            CREATE TABLE IF NOT EXISTS visitors_vmslistrecord (
                id BIGSERIAL PRIMARY KEY,
                module VARCHAR(80) NOT NULL,
                record_id VARCHAR(80) NOT NULL,
                data JSONB NOT NULL DEFAULT '{}',
                location VARCHAR(30) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (module, record_id)
            );
            CREATE INDEX IF NOT EXISTS visitors_vmslistrecord_module_idx
                ON visitors_vmslistrecord (module);
            """,
        ),
    ]

    with schema_editor.connection.cursor() as cursor:
        for table_name, sql in statements:
            if table_name in tables:
                continue
            cursor.execute(sql)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("visitors", "0003_alter_visitor_expiry_status_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=VISITOR_FIELD_STATE_OPS,
            database_operations=[
                migrations.RunPython(_add_visitor_fields_if_missing, _noop_reverse),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=CREATE_MODEL_STATE_OPS,
            database_operations=[
                migrations.RunPython(_create_vms_tables_if_missing, _noop_reverse),
            ],
        ),
    ]
