"""Staff-only views for the inventory MVP."""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import (
    EquipmentCharacteristicForm,
    EquipmentCreateForm,
    EquipmentEditForm,
    EquipmentIdentifierForm,
    LocationChangeForm,
    StatusChangeForm,
)
from .models import (
    AssetStatus,
    Equipment,
    EquipmentCharacteristic,
    EquipmentIdentifier,
    EquipmentLocation,
    EquipmentStatus,
    Location,
    Section,
)
from .services import change_equipment_status, move_equipment


def _staff_view(view):
    return staff_member_required(view, login_url="login")


def _equipment_queryset():
    return Equipment.objects.select_related(
        "model__manufacturer", "model__equipment_type__section"
    ).prefetch_related(
        Prefetch(
            "identifiers",
            queryset=EquipmentIdentifier.objects.filter(kind__code="inventory").select_related("kind"),
            to_attr="inventory_identifiers",
        ),
        Prefetch(
            "status_history",
            queryset=EquipmentStatus.objects.filter(valid_to__isnull=True).select_related("status"),
            to_attr="current_status_entries",
        ),
        Prefetch(
            "location_history",
            queryset=EquipmentLocation.objects.filter(valid_to__isnull=True).select_related("location"),
            to_attr="current_location_entries",
        ),
    )


@_staff_view
@require_http_methods(["GET"])
def equipment_list(request):
    equipment = _equipment_queryset().order_by("-created_at")
    query = request.GET.get("q", "").strip()
    selected_section = request.GET.get("section", "")
    selected_status = request.GET.get("status", "")
    selected_location = request.GET.get("location", "")

    if query:
        equipment = equipment.filter(
            Q(identifiers__value__icontains=query)
            | Q(model__name__icontains=query)
            | Q(model__manufacturer__name__icontains=query)
        ).distinct()
    if selected_section:
        equipment = equipment.filter(model__equipment_type__section_id=selected_section)
    if selected_status:
        equipment = equipment.filter(
            status_history__status_id=selected_status, status_history__valid_to__isnull=True
        )
    if selected_location:
        equipment = equipment.filter(
            location_history__location_id=selected_location, location_history__valid_to__isnull=True
        )

    page = Paginator(equipment, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "inventory/equipment_list.html",
        {
            "page": page,
            "sections": Section.objects.order_by("title"),
            "statuses": AssetStatus.objects.order_by("title"),
            "locations": Location.objects.order_by("title"),
            "filters": {
                "q": query,
                "section": selected_section,
                "status": selected_status,
                "location": selected_location,
            },
        },
    )


@_staff_view
@require_http_methods(["GET", "POST"])
def equipment_create(request):
    form = EquipmentCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        equipment = form.create_equipment()
        messages.success(request, "Оборудование добавлено, инвентарный номер сформирован автоматически.")
        return redirect("equipment_detail", pk=equipment.pk)
    return render(request, "inventory/equipment_form.html", {"form": form})


@_staff_view
@require_http_methods(["GET"])
def equipment_detail(request, pk):
    equipment = get_object_or_404(
        Equipment.objects.select_related("model__manufacturer", "model__equipment_type__section").prefetch_related(
            Prefetch("identifiers", queryset=EquipmentIdentifier.objects.select_related("kind").order_by("kind__title")),
            Prefetch(
                "characteristic_values",
                queryset=EquipmentCharacteristic.objects.select_related("characteristic").order_by("characteristic__title"),
            ),
            Prefetch("status_history", queryset=EquipmentStatus.objects.select_related("status").order_by("-valid_from")),
            Prefetch("location_history", queryset=EquipmentLocation.objects.select_related("location").order_by("-valid_from")),
        ),
        pk=pk,
    )
    current_status = next((item for item in equipment.status_history.all() if item.valid_to is None), None)
    current_location = next((item for item in equipment.location_history.all() if item.valid_to is None), None)
    return render(
        request,
        "inventory/equipment_detail.html",
        {
            "equipment": equipment,
            "current_status": current_status,
            "current_location": current_location,
            "is_retired": bool(current_status and current_status.status.code == "retired"),
        },
    )


@_staff_view
@require_http_methods(["GET", "POST"])
def equipment_edit(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    form = EquipmentEditForm(request.POST or None, instance=equipment)
    if request.method == "POST" and form.is_valid():
        try:
            equipment = form.update_equipment()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Карточка оборудования изменена.")
            return redirect("equipment_detail", pk=equipment.pk)
    return render(request, "inventory/equipment_edit_form.html", {"form": form, "equipment": equipment})


@_staff_view
@require_http_methods(["GET", "POST"])
def status_change(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    form = StatusChangeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            change_equipment_status(equipment=equipment, status=form.cleaned_data["status"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Статус оборудования изменён.")
            return redirect("equipment_detail", pk=equipment.pk)
    return render(request, "inventory/status_change_form.html", {"form": form, "equipment": equipment})


@_staff_view
@require_http_methods(["GET", "POST"])
def location_change(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    form = LocationChangeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            move_equipment(equipment=equipment, location=form.cleaned_data["location"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Местоположение оборудования изменено.")
            return redirect("equipment_detail", pk=equipment.pk)
    return render(request, "inventory/location_change_form.html", {"form": form, "equipment": equipment})


@_staff_view
@require_http_methods(["GET", "POST"])
def identifier_add(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    form = EquipmentIdentifierForm(request.POST or None, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            kind = form.cleaned_data["kind"]
            value = form.cleaned_data["value"]
            form.add_error("value", f"{kind.title} «{value}» уже используется другим оборудованием.")
        else:
            messages.success(request, "Идентификатор добавлен.")
            return redirect("equipment_detail", pk=equipment.pk)
    return render(request, "inventory/related_form.html", {"form": form, "equipment": equipment, "title": "Добавить идентификатор"})


@_staff_view
@require_http_methods(["GET", "POST"])
def identifier_edit(request, pk, identifier_pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    identifier = get_object_or_404(EquipmentIdentifier, pk=identifier_pk, equipment=equipment)
    form = EquipmentIdentifierForm(request.POST or None, instance=identifier, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            kind = form.cleaned_data["kind"]
            value = form.cleaned_data["value"]
            form.add_error("value", f"{kind.title} «{value}» уже используется другим оборудованием.")
        else:
            messages.success(request, "Идентификатор изменён.")
            return redirect("equipment_detail", pk=equipment.pk)
    return render(request, "inventory/related_form.html", {"form": form, "equipment": equipment, "title": "Изменить идентификатор"})


@_staff_view
@require_http_methods(["GET", "POST"])
def characteristic_add(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    form = EquipmentCharacteristicForm(request.POST or None, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error("characteristic", "Эта характеристика уже задана для оборудования.")
        else:
            messages.success(request, "Характеристика добавлена.")
            return redirect("equipment_detail", pk=equipment.pk)
    return render(request, "inventory/related_form.html", {"form": form, "equipment": equipment, "title": "Добавить характеристику"})
