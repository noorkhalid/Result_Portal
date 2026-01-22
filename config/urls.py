"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import include, path

from dashboards import views as dashboard_views

urlpatterns = [
    # Home / dashboards
    path("", dashboard_views.home, name="home"),
    path("", include("dashboards.urls")),

    # Authentication
    path("accounts/", include("django.contrib.auth.urls")),

    # Results (✅ REQUIRED for Result Notification PDF)
    path("results/", include("results.urls")),

    # Admin
    path("admin/", admin.site.urls),
]
