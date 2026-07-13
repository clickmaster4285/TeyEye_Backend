from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("person_journey", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="cameratrack",
            new_name="person_jour_camera__0a26b1_idx",
            old_name="person_jour_camera__4b2f11_idx",
        ),
        migrations.RenameIndex(
            model_name="journeyevent",
            new_name="person_jour_journey_a4a1b6_idx",
            old_name="person_jour_journey_91c4e2_idx",
        ),
        migrations.RenameIndex(
            model_name="journeyevent",
            new_name="person_jour_event_t_9c3c51_idx",
            old_name="person_jour_event_t_6d31a8_idx",
        ),
        migrations.RenameIndex(
            model_name="journeyperson",
            new_name="person_jour_person__3efaff_idx",
            old_name="person_jour_person__a8f2c0_idx",
        ),
    ]
