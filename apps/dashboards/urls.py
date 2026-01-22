from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    path("controller/dashboard/", views.controller_dashboard, name="dash_controller"),

    path("data-entry/dashboard/", views.data_entry_dashboard, name="dash_data_entry"),
    path("data-entry/import/", views.data_entry_import_marks, name="data_entry_import_marks"),

    path("documents/dashboard/", views.document_generator_dashboard, name="dash_document_generator"),
    path("results/dashboard/", views.result_checker_dashboard, name="dash_result_checker"),
    path("admin-dashboard/", views.system_admin_dashboard, name="dash_system_admin"),
]
