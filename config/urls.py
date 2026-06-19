"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("users.urls")),
    path("api/", include("visitors.urls")),
    path("api/", include("logs.urls")),
    path("api/", include("detentions.urls")),
    path("api/", include("cameras.urls")),
    path("api/", include("warehouse.urls")),
    path("api/", include("ml.urls")),
]

# Serve uploaded media files in development (e.g. /media/staff_docs/CRM.docx)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
