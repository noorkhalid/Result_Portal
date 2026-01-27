from django.contrib import admin
from django.urls import path, include

from dashboards.views.core import home

urlpatterns = [
    path("", home, name="home"),

    # Django auth (login, logout, password reset, etc.)
    path("accounts/", include("django.contrib.auth.urls")),

    path("", include("dashboards.urls")),

    # PDF / prints
    path("results/", include("results.urls")),
    path("admin/", admin.site.urls),
]
