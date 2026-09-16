"""Administration interface for inventory reference data."""
from django.contrib import admin

from .models import (
    AssetStatus,
    Characteristic,
    EquipmentModel,
    EquipmentType,
    IdentifierKind,
    Location,
    Manufacturer,
    Section,
)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "inventory_prefix")
    search_fields = ("code", "title", "inventory_prefix")
    ordering = ("title",)


@admin.register(EquipmentType)
class EquipmentTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "section")
    list_filter = ("section",)
    search_fields = ("code", "title")
    list_select_related = ("section",)
    ordering = ("section__title", "title")


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(EquipmentModel)
class EquipmentModelAdmin(admin.ModelAdmin):
    list_display = ("name", "manufacturer", "equipment_type")
    list_filter = ("equipment_type", "manufacturer")
    search_fields = ("name", "manufacturer__name")
    list_select_related = ("manufacturer", "equipment_type")
    ordering = ("manufacturer__name", "name")


@admin.register(AssetStatus)
class AssetStatusAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "is_terminal")
    list_filter = ("is_terminal",)
    search_fields = ("code", "title")
    ordering = ("title",)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("code", "title")
    search_fields = ("code", "title")
    ordering = ("title",)


@admin.register(Characteristic)
class CharacteristicAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "equipment_type", "unit")
    list_filter = ("equipment_type",)
    search_fields = ("code", "title")
    list_select_related = ("equipment_type",)
    ordering = ("equipment_type__title", "title")


@admin.register(IdentifierKind)
class IdentifierKindAdmin(admin.ModelAdmin):
    list_display = ("code", "title")
    search_fields = ("code", "title")
    ordering = ("title",)
