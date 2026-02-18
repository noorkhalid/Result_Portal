from django.urls import path
from . import views

urlpatterns = [
    path(
        "result-notification/<int:batch_id>/pdf/",
        views.result_notification_pdf,
        name="result_notification_pdf",
    ),

    path(
        "result-notification/by-id/<int:notification_id>/pdf/",
        views.result_notification_by_id_pdf,
        name="result_notification_by_id_pdf",
    ),

    # DMCs (one per student per semester)
    path(
        "dmc/<int:batch_id>/pdf/",
        views.dmc_batch_pdf,
        name="dmc_batch_pdf",
    ),
    path(
        "dmc/<int:batch_id>/<int:enrollment_id>/pdf/",
        views.dmc_single_pdf,
        name="dmc_single_pdf",
    ),

    # Transcript (single student, full program+session)
    path(
        "transcript/<int:enrollment_id>/pdf/",
        views.transcript_pdf,
        name="transcript_pdf",
    ),

    # Transcript (batch) - one combined PDF for all students in a final-semester batch
    path(
        "transcript/batch/<int:batch_id>/pdf/",
        views.transcript_batch_pdf,
        name="transcript_batch_pdf",
    ),
]
