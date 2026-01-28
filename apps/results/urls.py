from django.urls import path
from . import views

urlpatterns = [
    path(
        "result-notification/<int:batch_id>/pdf/",
        views.result_notification_pdf,
        name="result_notification_pdf",
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
]
