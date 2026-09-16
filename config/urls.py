from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from apps.inventory import views as inventory_views

admin.site.site_header = "Учёт IT-оборудования"
admin.site.site_title = "Учёт IT-оборудования"
admin.site.index_title = "Управление справочниками"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="equipment_list", permanent=False)),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("equipment/", inventory_views.equipment_list, name="equipment_list"),
    path("equipment/add/", inventory_views.equipment_create, name="equipment_create"),
    path("equipment/<int:pk>/", inventory_views.equipment_detail, name="equipment_detail"),
    path("equipment/<int:pk>/edit/", inventory_views.equipment_edit, name="equipment_edit"),
    path("equipment/<int:pk>/status/", inventory_views.status_change, name="status_change"),
    path("equipment/<int:pk>/location/", inventory_views.location_change, name="location_change"),
    path("equipment/<int:pk>/identifiers/add/", inventory_views.identifier_add, name="identifier_add"),
    path(
        "equipment/<int:pk>/identifiers/<int:identifier_pk>/edit/",
        inventory_views.identifier_edit,
        name="identifier_edit",
    ),
    path("equipment/<int:pk>/characteristics/add/", inventory_views.characteristic_add, name="characteristic_add"),
]
