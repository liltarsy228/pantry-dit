"""Domain operations that must be performed atomically."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AssetStatus,
    Equipment,
    EquipmentIdentifier,
    EquipmentLocation,
    EquipmentStatus,
    IdentifierKind,
    InventorySequence,
    Location,
    Section,
)


@transaction.atomic
def create_equipment_with_inventory_number(*, model, status: AssetStatus, location: Location, **equipment_fields) -> Equipment:
    """Create a unit with its inventory number, initial status and location.

    A row lock prevents duplicate numbers when several operators add equipment
    at the same time.
    """
    # Lock the parent section before creating or incrementing its sequence.
    # This also serialises the very first allocation, when no sequence row
    # exists yet and get_or_create alone would race.
    section: Section = Section.objects.select_for_update().get(pk=model.equipment_type.section_id)
    sequence, _ = InventorySequence.objects.select_for_update().get_or_create(section=section)
    number = sequence.next_number
    sequence.next_number = number + 1
    sequence.save(update_fields=["next_number"])

    equipment = Equipment.objects.create(model=model, **equipment_fields)
    inventory_kind, _ = IdentifierKind.objects.get_or_create(code="inventory", defaults={"title": "Инвентарный номер"})
    EquipmentIdentifier.objects.create(
        equipment=equipment,
        kind=inventory_kind,
        value=f"{section.inventory_prefix}-{number:06d}",
    )
    EquipmentStatus.objects.create(equipment=equipment, status=status)
    EquipmentLocation.objects.create(equipment=equipment, location=location)
    return equipment


@transaction.atomic
def change_equipment_status(*, equipment: Equipment, status: AssetStatus) -> EquipmentStatus:
    """Close the current status interval and start a new one."""
    equipment = Equipment.objects.select_for_update().get(pk=equipment.pk)
    current = EquipmentStatus.objects.select_for_update().filter(
        equipment=equipment, valid_to__isnull=True
    ).first()
    if current and current.status_id == status.pk:
        raise ValidationError("Оборудование уже имеет выбранный статус.")

    if current:
        current.valid_to = timezone.now()
        current.save(update_fields=["valid_to"])
    return EquipmentStatus.objects.create(equipment=equipment, status=status)


@transaction.atomic
def move_equipment(*, equipment: Equipment, location: Location) -> EquipmentLocation:
    """Close the current location interval and start a new one."""
    equipment = Equipment.objects.select_for_update().get(pk=equipment.pk)
    current = EquipmentLocation.objects.select_for_update().filter(
        equipment=equipment, valid_to__isnull=True
    ).first()
    if current and current.location_id == location.pk:
        raise ValidationError("Оборудование уже находится в выбранном местоположении.")

    if current:
        current.valid_to = timezone.now()
        current.save(update_fields=["valid_to"])
    return EquipmentLocation.objects.create(equipment=equipment, location=location)


@transaction.atomic
def update_equipment(*, equipment: Equipment, model, received_on, purchase_price, note: str) -> Equipment:
    """Update ordinary equipment fields without bypassing its lifecycle state."""
    equipment = Equipment.objects.select_for_update().get(pk=equipment.pk)
    is_retired = EquipmentStatus.objects.filter(
        equipment=equipment, valid_to__isnull=True, status__code="retired"
    ).exists()
    if is_retired:
        raise ValidationError("Списанное оборудование нельзя редактировать.")

    type_changes = equipment.model.equipment_type_id != model.equipment_type_id
    has_characteristics = equipment.characteristic_values.exists()
    if type_changes and has_characteristics:
        raise ValidationError(
            "Нельзя изменить тип оборудования, пока для него заданы характеристики."
        )

    equipment.model = model
    equipment.received_on = received_on
    equipment.purchase_price = purchase_price
    equipment.note = note
    equipment.full_clean()
    equipment.save(update_fields=["model", "received_on", "purchase_price", "note"])
    return equipment
