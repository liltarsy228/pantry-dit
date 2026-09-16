"""Normalised domain model for physical IT assets.

No table stores a calculated current location or status: those facts are read
from the corresponding history relations.
"""
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Section(models.Model):
    """Top-level catalogue section and its inventory-code prefix."""

    code = models.CharField("код", max_length=32, unique=True)
    title = models.CharField("наименование", max_length=100, unique=True)
    inventory_prefix = models.CharField("префикс инвентарного номера", max_length=8, unique=True)

    class Meta:
        verbose_name = "раздел"
        verbose_name_plural = "разделы"

    def __str__(self) -> str:
        return self.title


class EquipmentType(models.Model):
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="equipment_types")
    code = models.CharField("код типа", max_length=40, unique=True)
    title = models.CharField("наименование", max_length=100)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["section", "title"], name="uq_type_section_title")]

    def __str__(self) -> str:
        return self.title


class Manufacturer(models.Model):
    name = models.CharField("производитель", max_length=150, unique=True)

    def __str__(self) -> str:
        return self.name


class EquipmentModel(models.Model):
    """A manufacturer model belongs to exactly one equipment type."""

    equipment_type = models.ForeignKey(EquipmentType, on_delete=models.PROTECT, related_name="models")
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.PROTECT, related_name="models")
    name = models.CharField("модель", max_length=150)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["equipment_type", "manufacturer", "name"], name="uq_equipment_model"
            )
        ]

    def __str__(self) -> str:
        return f"{self.manufacturer} {self.name}"


class Equipment(models.Model):
    """The physical unit. Its type and section are derived through model."""

    model = models.ForeignKey(EquipmentModel, on_delete=models.PROTECT, related_name="equipment")
    received_on = models.DateField("дата поступления", null=True, blank=True)
    purchase_price = models.DecimalField(
        "стоимость", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    note = models.TextField("примечание", blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    def __str__(self) -> str:
        return str(self.pk)


class IdentifierKind(models.Model):
    code = models.CharField("код", max_length=32, unique=True)
    title = models.CharField("наименование", max_length=100, unique=True)

    def __str__(self) -> str:
        return self.title


class EquipmentIdentifier(models.Model):
    """One identifier value of a unit: inventory, factory serial number, MAC."""

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="identifiers")
    kind = models.ForeignKey(IdentifierKind, on_delete=models.PROTECT, related_name="identifiers")
    value = models.CharField("значение", max_length=128)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "value"], name="uq_identifier_kind_value"),
            models.UniqueConstraint(fields=["equipment", "kind"], name="uq_equipment_identifier_kind"),
        ]


class Location(models.Model):
    code = models.CharField("код", max_length=32, unique=True)
    title = models.CharField("местоположение", max_length=150, unique=True)

    def __str__(self) -> str:
        return self.title


class EquipmentLocation(models.Model):
    """Time interval during which equipment was located at one location."""

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="location_history")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="equipment_history")
    valid_from = models.DateTimeField("с", auto_now_add=True)
    valid_to = models.DateTimeField("по", null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="ck_location_interval",
            ),
            models.UniqueConstraint(
                fields=["equipment"], condition=Q(valid_to__isnull=True), name="uq_active_equipment_location",
            ),
        ]


class AssetStatus(models.Model):
    code = models.CharField("код", max_length=32, unique=True)
    title = models.CharField("статус", max_length=100, unique=True)
    is_terminal = models.BooleanField("завершающий статус", default=False)

    def __str__(self) -> str:
        return self.title


class EquipmentStatus(models.Model):
    """Time interval of a status; current status is its open interval."""

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="status_history")
    status = models.ForeignKey(AssetStatus, on_delete=models.PROTECT, related_name="equipment_history")
    valid_from = models.DateTimeField("с", auto_now_add=True)
    valid_to = models.DateTimeField("по", null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="ck_status_interval",
            ),
            models.UniqueConstraint(
                fields=["equipment"], condition=Q(valid_to__isnull=True), name="uq_active_equipment_status",
            ),
        ]


class Characteristic(models.Model):
    """A scalar characteristic allowed for a particular equipment type."""

    equipment_type = models.ForeignKey(EquipmentType, on_delete=models.PROTECT, related_name="characteristics")
    code = models.CharField("код", max_length=40)
    title = models.CharField("наименование", max_length=100)
    unit = models.CharField("единица измерения", max_length=20, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["equipment_type", "code"], name="uq_characteristic_type_code")
        ]


class EquipmentCharacteristic(models.Model):
    """One atomic, canonical value of a characteristic of a unit."""

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="characteristic_values")
    characteristic = models.ForeignKey(Characteristic, on_delete=models.PROTECT, related_name="values")
    value = models.CharField("значение", max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "characteristic"], name="uq_equipment_characteristic"
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.equipment_id and self.characteristic_id:
            actual_type_id = self.equipment.model.equipment_type_id
            if actual_type_id != self.characteristic.equipment_type_id:
                raise ValidationError({"characteristic": "Характеристика не разрешена для типа этой техники."})


class InventorySequence(models.Model):
    """Per-section sequence used only for safe generation of inventory numbers."""

    section = models.OneToOneField(Section, on_delete=models.PROTECT, related_name="inventory_sequence")
    next_number = models.PositiveBigIntegerField(default=1, validators=[MinValueValidator(1)])
