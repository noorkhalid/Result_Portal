from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0010_delete_semester"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ProgramCourse",
        ),
    ]
