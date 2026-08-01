from django.db import migrations, models


def classify_existing_notifications(apps, schema_editor):
    ResultBatch = apps.get_model("results", "ResultBatch")
    ResultNotification = apps.get_model("results", "ResultNotification")
    ResultNotificationItem = apps.get_model("results", "ResultNotificationItem")

    hold_labels = {
        "dues": "RL Dues",
        "documents": "RL Documents",
    }

    for batch in ResultBatch.objects.all().iterator():
        notifications = list(
            ResultNotification.objects.filter(batch_id=batch.id).order_by(
                "created_at", "id"
            )
        )
        for index, notification in enumerate(notifications):
            notification.notification_type = "full" if index == 0 else "clearance"
            notification.save(update_fields=["notification_type"])

        first = notifications[0] if notifications else None
        official_date = None
        if first:
            official_date = first.declaration_date or first.notification_date
        if not official_date:
            official_date = batch.notification_date
        if official_date:
            ResultBatch.objects.filter(pk=batch.pk).update(
                official_result_declaration_date=official_date
            )

    for item in ResultNotificationItem.objects.all().iterator():
        label = hold_labels.get(item.hold_status_snapshot, "")
        if label:
            ResultNotificationItem.objects.filter(pk=item.pk).update(
                hold_label_snapshot=label
            )


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0013_align_course_result_max_marks_20"),
    ]

    operations = [
        migrations.AddField(
            model_name="resultbatch",
            name="official_result_declaration_date",
            field=models.DateField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="resultnotification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("full", "Full Notification"),
                    ("clearance", "Clearance Notification"),
                ],
                default="full",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="resultnotificationitem",
            name="hold_label_snapshot",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(
            classify_existing_notifications,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="resultnotification",
            name="notification_no",
            field=models.CharField(max_length=100, unique=True),
        ),
        migrations.AlterModelOptions(
            name="resultnotification",
            options={"ordering": ["notification_date", "created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="resultnotification",
            index=models.Index(
                fields=["batch", "notification_type"],
                name="result_notif_batch_type_idx",
            ),
        ),
    ]
