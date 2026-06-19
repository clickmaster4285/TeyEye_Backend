# Site / NVR / Camera hierarchy — supports fresh DBs and DBs that already had tables.

import django.db.models.deletion
from django.db import migrations, models


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = %s
        """,
        [table_name],
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s AND column_name = %s
        """,
        [table_name, column_name],
    )
    return cursor.fetchone() is not None


def forwards_database(apps, schema_editor):
    """Apply DB changes. Handles fresh DBs, partial runs, and existing production DBs."""
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        has_site = _table_exists(cursor, "cameras_site")
        has_nvr_column = _column_exists(cursor, "cameras_camera", "nvr_id")

        if has_site and has_nvr_column:
            cursor.execute(
                "ALTER TABLE cameras_site ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';"
            )
            cursor.execute("DROP TABLE IF EXISTS cameras_camerartspsettings CASCADE;")
            return

        if not has_site:
            cursor.execute(
                """
                CREATE TABLE cameras_site (
                  id BIGSERIAL PRIMARY KEY,
                  code VARCHAR(64) NOT NULL UNIQUE,
                  name VARCHAR(150) NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  is_active BOOLEAN NOT NULL DEFAULT TRUE,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

        if not _table_exists(cursor, "cameras_nvrdevice"):
            cursor.execute(
                """
                CREATE TABLE cameras_nvrdevice (
                  id BIGSERIAL PRIMARY KEY,
                  site_id BIGINT NOT NULL REFERENCES cameras_site(id) ON DELETE CASCADE,
                  name VARCHAR(150) NOT NULL,
                  ip_address VARCHAR(45) NOT NULL,
                  port INTEGER NOT NULL DEFAULT 554 CHECK (port >= 0),
                  username VARCHAR(64) NOT NULL DEFAULT 'admin',
                  password VARCHAR(128) NOT NULL DEFAULT '',
                  brand VARCHAR(32) NOT NULL DEFAULT 'hikvision',
                  stream_path_template VARCHAR(255) NOT NULL DEFAULT '',
                  is_active BOOLEAN NOT NULL DEFAULT TRUE,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

        cursor.execute("SELECT id FROM cameras_nvrdevice ORDER BY id LIMIT 1;")
        row = cursor.fetchone()
        if row:
            nvr_id = row[0]
        else:
            cursor.execute("SELECT id FROM cameras_site WHERE code = 'DEFAULT' LIMIT 1;")
            site_row = cursor.fetchone()
            if site_row:
                site_id = site_row[0]
            else:
                cursor.execute(
                    """
                    INSERT INTO cameras_site (code, name, description, is_active)
                    VALUES ('DEFAULT', 'Default Site', '', TRUE)
                    RETURNING id;
                    """
                )
                site_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO cameras_nvrdevice (site_id, name, ip_address, port, username, password, brand)
                VALUES (%s, 'Default NVR', '127.0.0.1', 554, 'admin', '', 'hikvision')
                RETURNING id;
                """,
                [site_id],
            )
            nvr_id = cursor.fetchone()[0]

        if not has_nvr_column:
            cursor.execute(
                """
                ALTER TABLE cameras_camera
                  ADD COLUMN nvr_id BIGINT REFERENCES cameras_nvrdevice(id) ON DELETE CASCADE,
                  ADD COLUMN rtsp_channel SMALLINT CHECK (rtsp_channel >= 0);
                """
            )
            cursor.execute(
                """
                UPDATE cameras_camera AS c
                SET nvr_id = %s,
                    rtsp_channel = ranked.ch
                FROM (
                  SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS ch
                  FROM cameras_camera
                ) AS ranked
                WHERE c.id = ranked.id AND c.nvr_id IS NULL;
                """,
                [nvr_id],
            )
            cursor.execute(
                """
                ALTER TABLE cameras_camera
                  ALTER COLUMN nvr_id SET NOT NULL,
                  ALTER COLUMN rtsp_channel SET NOT NULL;
                """
            )

        if _column_exists(cursor, "cameras_camera", "ip_address"):
            cursor.execute("ALTER TABLE cameras_camera DROP COLUMN ip_address;")
        if _column_exists(cursor, "cameras_camera", "stream_url"):
            cursor.execute("ALTER TABLE cameras_camera DROP COLUMN stream_url;")
        if _column_exists(cursor, "cameras_camera", "site_label"):
            cursor.execute("ALTER TABLE cameras_camera DROP COLUMN site_label;")

        cursor.execute("DROP TABLE IF EXISTS cameras_camerartspsettings CASCADE;")

        cursor.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'cameras_camera_nvr_id_rtsp_channel_uniq'
              ) THEN
                ALTER TABLE cameras_camera
                  ADD CONSTRAINT cameras_camera_nvr_id_rtsp_channel_uniq UNIQUE (nvr_id, rtsp_channel);
              END IF;
            END $$;
            """
        )


def backwards_database(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0004_alter_camera_frame_rate"),
    ]

    state_operations = [
        migrations.CreateModel(
            name="Site",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(help_text="Short code e.g. PESHAWAR", max_length=64, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "cameras_site",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Nvr",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("ip_address", models.CharField(max_length=45)),
                ("port", models.PositiveIntegerField(default=554)),
                ("username", models.CharField(default="admin", max_length=64)),
                ("password", models.CharField(blank=True, default="", max_length=128)),
                (
                    "brand",
                    models.CharField(
                        choices=[
                            ("hikvision", "Hikvision"),
                            ("dahua", "Dahua"),
                            ("uniview", "Uniview"),
                            ("generic", "Generic RTSP"),
                        ],
                        default="hikvision",
                        max_length=32,
                    ),
                ),
                (
                    "stream_path_template",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional path template with {channel}",
                        max_length=255,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nvrs",
                        to="cameras.site",
                    ),
                ),
            ],
            options={
                "db_table": "cameras_nvrdevice",
                "verbose_name": "NVR",
                "verbose_name_plural": "NVRs",
                "ordering": ["site__name", "name"],
            },
        ),
        migrations.RemoveField(model_name="camera", name="ip_address"),
        migrations.RemoveField(model_name="camera", name="stream_url"),
        migrations.RemoveField(model_name="camera", name="site_label"),
        migrations.AddField(
            model_name="camera",
            name="nvr",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cameras",
                to="cameras.nvr",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="camera",
            name="channel",
            field=models.PositiveSmallIntegerField(
                db_column="rtsp_channel",
                help_text="NVR channel number (1–32+, or Hikvision stream ID e.g. 101)",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="camera",
            name="location",
            field=models.CharField(help_text="Denormalized site code", max_length=64),
        ),
        migrations.AlterField(
            model_name="camera",
            name="name",
            field=models.CharField(help_text="User-defined label e.g. Main Gate", max_length=150),
        ),
        migrations.AlterUniqueTogether(
            name="camera",
            unique_together={("nvr", "channel")},
        ),
        migrations.AlterModelOptions(
            name="camera",
            options={"ordering": ["nvr__site__name", "nvr__name", "channel"]},
        ),
        migrations.DeleteModel(name="CameraRtspSettings"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards_database, backwards_database),
            ],
            state_operations=state_operations,
        ),
    ]
