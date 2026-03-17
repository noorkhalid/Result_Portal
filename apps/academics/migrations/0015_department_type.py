from django.db import migrations, models


def assign_department_types(apps, schema_editor):
    Department = apps.get_model('academics', 'Department')

    private_names = {
        'Al Habib Degree College, Shangla',
        'Falcon Educational Complex, Tank',
        'Hi Tech Polytechnic Institute, Karak',
        'Jamil Post Graduate College of Science, Peer Jaggi More',
        'School of Medical & Management Sciences, Buner',
        'Sir Syed College, Noor Pur Thal',
        'Superior College, Lahore',
        'Superior College, Rawalpindi',
    }
    public_names = set()
    main_campus_names = {
        'Institute Of Biological Sciences',
    }
    quaid_e_azam_names = set()
    tank_campus_names = set()

    for dept in Department.objects.all():
        if dept.name in public_names:
            dept.type = 'public_affiliated'
        elif dept.name in main_campus_names:
            dept.type = 'university_main'
        elif dept.name in quaid_e_azam_names:
            dept.type = 'university_quaid_e_azam'
        elif dept.name in tank_campus_names:
            dept.type = 'university_tank'
        else:
            dept.type = 'private_affiliated'
        dept.save(update_fields=['type'])


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0014_program_and_curriculum_semester_start'),
    ]

    operations = [
        migrations.AddField(
            model_name='department',
            name='type',
            field=models.CharField(
                choices=[
                    ('private_affiliated', 'Private Affiliated College'),
                    ('public_affiliated', 'Public Affiliated College'),
                    ('university_main', 'University Department, Main Campus'),
                    ('university_quaid_e_azam', 'University Department, Quid E Azam Campus'),
                    ('university_tank', 'University Department, Tank Campus'),
                ],
                default='private_affiliated',
                max_length=40,
            ),
        ),
        migrations.RunPython(assign_department_types, migrations.RunPython.noop),
    ]
