from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0006_programoffering"),
    ]

    operations = [
        # Programs are now GLOBAL/master (no department FK).
        migrations.RemoveField(
            model_name="program",
            name="department",
        ),
        # ProgramCourse is now GLOBAL curriculum mapping (no department FK).
        migrations.RemoveField(
            model_name="programcourse",
            name="department",
        ),
    ]
