from django.urls import path
from . import views

urlpatterns = [
    path(
        "result-notification/<int:batch_id>/pdf/",
        views.result_notification_pdf,
        name="result_notification_pdf",
    ),
]
