"""Forms for the inventory MVP interface."""
from django import forms

from .models import (
    AssetStatus,
    Characteristic,
    Equipment,
    EquipmentCharacteristic,
    EquipmentIdentifier,
    EquipmentModel,
    IdentifierKind,
    Location,
)
from .services import create_equipment_with_inventory_number, update_equipment


class EquipmentCreateForm(forms.ModelForm):
    status = forms.ModelChoiceField(label="Начальный статус", queryset=AssetStatus.objects.none())
    location = forms.ModelChoiceField(label="Начальное местоположение", queryset=Location.objects.none())

    class Meta:
        model = Equipment
        fields = ("model", "received_on", "purchase_price", "note")
        labels = {
            "model": "Модель оборудования",
            "received_on": "Дата поступления",
            "purchase_price": "Стоимость",
            "note": "Примечание",
        }
        widgets = {
            "received_on": forms.DateInput(attrs={"type": "date"}),
            "purchase_price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["model"].queryset = EquipmentModel.objects.select_related(
            "manufacturer", "equipment_type"
        ).order_by("manufacturer__name", "name")
        self.fields["status"].queryset = AssetStatus.objects.filter(is_terminal=False).order_by("title")
        self.fields["location"].queryset = Location.objects.order_by("title")

    def create_equipment(self) -> Equipment:
        if not self.is_valid():
            raise ValueError("Нельзя создать оборудование из невалидной формы.")
        return create_equipment_with_inventory_number(
            model=self.cleaned_data["model"],
            status=self.cleaned_data["status"],
            location=self.cleaned_data["location"],
            received_on=self.cleaned_data["received_on"],
            purchase_price=self.cleaned_data["purchase_price"],
            note=self.cleaned_data["note"],
        )


class EquipmentEditForm(forms.ModelForm):
    """Edit only ordinary Equipment fields; lifecycle facts have separate forms."""

    class Meta:
        model = Equipment
        fields = ("model", "received_on", "purchase_price", "note")
        labels = {
            "model": "Модель оборудования",
            "received_on": "Дата поступления",
            "purchase_price": "Стоимость",
            "note": "Примечание",
        }
        widgets = {
            "received_on": forms.DateInput(attrs={"type": "date"}),
            "purchase_price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["model"].queryset = EquipmentModel.objects.select_related(
            "manufacturer", "equipment_type"
        ).order_by("manufacturer__name", "name")

    def update_equipment(self) -> Equipment:
        if not self.is_valid():
            raise ValueError("Нельзя обновить оборудование из невалидной формы.")
        return update_equipment(
            equipment=self.instance,
            model=self.cleaned_data["model"],
            received_on=self.cleaned_data["received_on"],
            purchase_price=self.cleaned_data["purchase_price"],
            note=self.cleaned_data["note"],
        )


class StatusChangeForm(forms.Form):
    status = forms.ModelChoiceField(label="Новый статус", queryset=AssetStatus.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].queryset = AssetStatus.objects.order_by("title")


class LocationChangeForm(forms.Form):
    location = forms.ModelChoiceField(label="Новое местоположение", queryset=Location.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.order_by("title")


class EquipmentIdentifierForm(forms.ModelForm):
    """Add or edit one identifier while preserving global uniqueness by kind."""

    class Meta:
        model = EquipmentIdentifier
        fields = ("kind", "value")
        labels = {"kind": "Вид идентификатора", "value": "Значение"}

    def __init__(self, *args, equipment: Equipment, **kwargs):
        self.equipment = equipment
        super().__init__(*args, **kwargs)
        self.instance.equipment = equipment
        self.fields["kind"].queryset = IdentifierKind.objects.order_by("title")

    def clean_value(self):
        return self.cleaned_data["value"].strip()

    def clean(self):
        cleaned_data = super().clean()
        kind = cleaned_data.get("kind")
        value = cleaned_data.get("value")
        if not kind or not value:
            return cleaned_data

        duplicate = EquipmentIdentifier.objects.filter(kind=kind, value=value).exclude(pk=self.instance.pk).first()
        if duplicate:
            self.add_error(
                "value",
                f"{kind.title} «{value}» уже используется другим оборудованием.",
            )
        return cleaned_data


class EquipmentCharacteristicForm(forms.ModelForm):
    """Allow only characteristics configured for this equipment's type."""

    class Meta:
        model = EquipmentCharacteristic
        fields = ("characteristic", "value")
        labels = {"characteristic": "Характеристика", "value": "Значение"}

    def __init__(self, *args, equipment: Equipment, **kwargs):
        self.equipment = equipment
        super().__init__(*args, **kwargs)
        self.instance.equipment = equipment
        self.allowed_characteristics = Characteristic.objects.filter(
            equipment_type=equipment.model.equipment_type
        ).order_by("title")
        self.fields["characteristic"].queryset = self.allowed_characteristics

    def clean(self):
        cleaned_data = super().clean()
        characteristic = cleaned_data.get("characteristic")
        if characteristic and characteristic.equipment_type_id != self.equipment.model.equipment_type_id:
            self.add_error("characteristic", "Характеристика не разрешена для типа этой техники.")
            return cleaned_data

        # A tampered POST contains an id outside the restricted queryset and
        # therefore has no cleaned characteristic. Replace the generic choice
        # error with the domain-specific explanation when appropriate.
        raw_characteristic_id = self.data.get(self.add_prefix("characteristic"))
        if raw_characteristic_id and not characteristic and Characteristic.objects.filter(
            pk=raw_characteristic_id
        ).exists():
            self.errors.pop("characteristic", None)
            self.add_error("characteristic", "Характеристика не разрешена для типа этой техники.")

        if characteristic and EquipmentCharacteristic.objects.filter(
            equipment=self.equipment, characteristic=characteristic
        ).exclude(pk=self.instance.pk).exists():
            self.add_error("characteristic", "Эта характеристика уже задана для оборудования.")
        return cleaned_data
