import threading
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .forms import EquipmentCharacteristicForm, EquipmentIdentifierForm
from .models import (
    AssetStatus,
    Characteristic,
    EquipmentCharacteristic,
    EquipmentIdentifier,
    EquipmentModel,
    EquipmentType,
    IdentifierKind,
    InventorySequence,
    Location,
    Manufacturer,
    Section,
)
from .services import change_equipment_status, create_equipment_with_inventory_number, move_equipment


class InventoryMvpTests(TestCase):
    def setUp(self):
        self.section = Section.objects.get(code="computer_server")
        equipment_type = EquipmentType.objects.create(
            section=self.section, code="laptop", title="Ноутбук"
        )
        manufacturer = Manufacturer.objects.create(name="Example")
        self.model = EquipmentModel.objects.create(
            equipment_type=equipment_type, manufacturer=manufacturer, name="MVP-1"
        )
        other_type = EquipmentType.objects.create(
            section=self.section, code="server", title="Сервер"
        )
        other_manufacturer = Manufacturer.objects.create(name="Other Example")
        self.other_model = EquipmentModel.objects.create(
            equipment_type=other_type, manufacturer=other_manufacturer, name="MVP-2"
        )
        self.stock = AssetStatus.objects.get(code="in_stock")
        self.in_use = AssetStatus.objects.get(code="in_use")
        self.warehouse = Location.objects.create(code="warehouse", title="Склад")
        self.office = Location.objects.create(code="office-101", title="Кабинет 101")
        self.serial_kind = IdentifierKind.objects.get(code="manufacturer_serial")
        self.mac_kind = IdentifierKind.objects.get(code="mac_address")
        self.ram = Characteristic.objects.create(
            equipment_type=equipment_type, code="ram", title="Оперативная память", unit="ГБ"
        )
        self.cores = Characteristic.objects.create(
            equipment_type=other_type, code="cores", title="Ядра процессора", unit="шт."
        )

    def create_equipment(self):
        return create_equipment_with_inventory_number(
            model=self.model, status=self.stock, location=self.warehouse, note="Проверка MVP"
        )

    def test_creation_generates_inventory_number_and_initial_intervals(self):
        equipment = self.create_equipment()

        self.assertEqual(
            EquipmentIdentifier.objects.get(equipment=equipment, kind__code="inventory").value, "pc-000001"
        )
        self.assertEqual(equipment.status_history.get(valid_to__isnull=True).status, self.stock)
        self.assertEqual(equipment.location_history.get(valid_to__isnull=True).location, self.warehouse)

    def test_status_and_location_changes_preserve_history(self):
        equipment = self.create_equipment()
        previous_status = equipment.status_history.get(valid_to__isnull=True)
        previous_location = equipment.location_history.get(valid_to__isnull=True)

        change_equipment_status(equipment=equipment, status=self.in_use)
        move_equipment(equipment=equipment, location=self.office)

        self.assertEqual(equipment.status_history.filter(valid_to__isnull=True).get().status, self.in_use)
        self.assertEqual(equipment.location_history.filter(valid_to__isnull=True).get().location, self.office)
        self.assertEqual(equipment.status_history.count(), 2)
        self.assertEqual(equipment.location_history.count(), 2)
        self.assertEqual(equipment.status_history.filter(valid_to__isnull=True).count(), 1)
        self.assertEqual(equipment.location_history.filter(valid_to__isnull=True).count(), 1)
        previous_status.refresh_from_db()
        previous_location.refresh_from_db()
        self.assertIsNotNone(previous_status.valid_to)
        self.assertIsNotNone(previous_location.valid_to)

    def test_retirement_preserves_history_and_blocks_regular_card_editing(self):
        equipment = self.create_equipment()
        retired = AssetStatus.objects.get(code="retired")
        change_equipment_status(equipment=equipment, status=self.in_use)
        change_equipment_status(equipment=equipment, status=retired)

        active = equipment.status_history.get(valid_to__isnull=True)
        previous = equipment.status_history.order_by("valid_from")[1]
        self.assertEqual(active.status, retired)
        self.assertEqual(equipment.status_history.filter(valid_to__isnull=True).count(), 1)
        self.assertEqual(equipment.status_history.count(), 3)
        self.assertIsNotNone(previous.valid_to)
        self.assertLessEqual(previous.valid_to, active.valid_from)
        self.assertTrue(type(equipment).objects.filter(pk=equipment.pk).exists())

        staff = get_user_model().objects.create_user("operator", password="test-password", is_staff=True)
        self.client.force_login(staff)
        response = self.client.post(
            reverse("equipment_edit", kwargs={"pk": equipment.pk}),
            {"model": self.other_model.pk, "received_on": "2026-01-10", "purchase_price": "10.00", "note": "Изменение"},
        )
        equipment.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Списанное оборудование нельзя редактировать.")
        self.assertEqual(equipment.model, self.model)

    def test_staff_can_edit_equipment_fields(self):
        equipment = self.create_equipment()
        staff = get_user_model().objects.create_user("operator", password="test-password", is_staff=True)
        self.client.force_login(staff)

        response = self.client.post(
            reverse("equipment_edit", kwargs={"pk": equipment.pk}),
            {
                "model": self.other_model.pk,
                "received_on": "2026-01-10",
                "purchase_price": "12345.67",
                "note": "Перенесённая карточка",
            },
        )
        self.assertRedirects(response, reverse("equipment_detail", kwargs={"pk": equipment.pk}))
        equipment.refresh_from_db()
        self.assertEqual(equipment.model, self.other_model)
        self.assertEqual(equipment.received_on, date(2026, 1, 10))
        self.assertEqual(equipment.purchase_price, Decimal("12345.67"))
        self.assertEqual(equipment.note, "Перенесённая карточка")

    def test_editing_cannot_change_type_when_characteristics_exist(self):
        equipment = self.create_equipment()
        EquipmentCharacteristic.objects.create(equipment=equipment, characteristic=self.ram, value="16")
        staff = get_user_model().objects.create_user("operator", password="test-password", is_staff=True)
        self.client.force_login(staff)

        response = self.client.post(
            reverse("equipment_edit", kwargs={"pk": equipment.pk}),
            {"model": self.other_model.pk, "received_on": "", "purchase_price": "", "note": ""},
        )

        equipment.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нельзя изменить тип оборудования, пока для него заданы характеристики.")
        self.assertEqual(equipment.model, self.model)

    def test_non_staff_cannot_edit_equipment_or_change_status(self):
        equipment = self.create_equipment()
        user = get_user_model().objects.create_user("viewer", password="test-password")
        self.client.force_login(user)

        edit_response = self.client.post(
            reverse("equipment_edit", kwargs={"pk": equipment.pk}),
            {"model": self.other_model.pk, "received_on": "2026-01-10", "purchase_price": "10.00", "note": "Изменение"},
        )
        status_response = self.client.post(
            reverse("status_change", kwargs={"pk": equipment.pk}), {"status": self.in_use.pk}
        )
        location_response = self.client.post(
            reverse("location_change", kwargs={"pk": equipment.pk}), {"location": self.office.pk}
        )
        equipment.refresh_from_db()
        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(status_response.status_code, 302)
        self.assertEqual(location_response.status_code, 302)
        self.assertEqual(equipment.model, self.model)
        self.assertEqual(equipment.status_history.get(valid_to__isnull=True).status, self.stock)
        self.assertEqual(equipment.location_history.get(valid_to__isnull=True).location, self.warehouse)

    def test_equipment_list_is_staff_only(self):
        response = self.client.get(reverse("equipment_list"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('equipment_list')}")

        user = get_user_model().objects.create_user("operator", password="test-password", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("equipment_list"))
        self.assertEqual(response.status_code, 200)

    def test_staff_can_create_and_open_equipment_card(self):
        user = get_user_model().objects.create_user("operator", password="test-password", is_staff=True)
        self.client.force_login(user)

        response = self.client.post(
            reverse("equipment_create"),
            {"model": self.model.pk, "status": self.stock.pk, "location": self.warehouse.pk, "note": ""},
        )

        equipment = EquipmentIdentifier.objects.get(kind__code="inventory", value="pc-000001").equipment
        self.assertRedirects(response, reverse("equipment_detail", kwargs={"pk": equipment.pk}))
        self.assertContains(self.client.get(response.url), "pc-000001")

    def test_identifier_form_shows_clear_error_for_duplicate_and_allows_own_edit(self):
        first = self.create_equipment()
        second = create_equipment_with_inventory_number(
            model=self.model, status=self.stock, location=self.warehouse
        )
        first_form = EquipmentIdentifierForm(
            {"kind": self.serial_kind.pk, "value": "ABC123"}, equipment=first
        )
        self.assertTrue(first_form.is_valid(), first_form.errors)
        identifier = first_form.save()

        duplicate_form = EquipmentIdentifierForm(
            {"kind": self.serial_kind.pk, "value": "ABC123"}, equipment=second
        )
        self.assertFalse(duplicate_form.is_valid())
        self.assertIn("Серийный номер производителя «ABC123» уже используется другим оборудованием.", duplicate_form.errors["value"])

        edit_own_form = EquipmentIdentifierForm(
            {"kind": self.serial_kind.pk, "value": "ABC123"}, instance=identifier, equipment=first
        )
        self.assertTrue(edit_own_form.is_valid(), edit_own_form.errors)

    def test_identifier_allows_same_value_for_different_kinds_and_database_enforces_unique_kind_value(self):
        first = self.create_equipment()
        second = create_equipment_with_inventory_number(
            model=self.model, status=self.stock, location=self.warehouse
        )
        serial_form = EquipmentIdentifierForm(
            {"kind": self.serial_kind.pk, "value": "SAME-VALUE"}, equipment=first
        )
        mac_form = EquipmentIdentifierForm(
            {"kind": self.mac_kind.pk, "value": "SAME-VALUE"}, equipment=second
        )
        self.assertTrue(serial_form.is_valid(), serial_form.errors)
        serial_form.save()
        self.assertTrue(mac_form.is_valid(), mac_form.errors)
        mac_form.save()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EquipmentIdentifier.objects.create(
                    equipment=second, kind=self.serial_kind, value="SAME-VALUE"
                )

    def test_characteristic_form_accepts_only_equipment_type_characteristics(self):
        equipment = self.create_equipment()
        valid_form = EquipmentCharacteristicForm(
            {"characteristic": self.ram.pk, "value": "16"}, equipment=equipment
        )
        self.assertTrue(valid_form.is_valid(), valid_form.errors)
        valid_form.save()
        self.assertTrue(
            EquipmentCharacteristic.objects.filter(equipment=equipment, characteristic=self.ram, value="16").exists()
        )

        invalid_form = EquipmentCharacteristicForm(
            {"characteristic": self.cores.pk, "value": "8"}, equipment=equipment
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("Характеристика не разрешена для типа этой техники.", invalid_form.errors["characteristic"])
        self.assertFalse(EquipmentCharacteristic.objects.filter(equipment=equipment, characteristic=self.cores).exists())

        invalid_model = EquipmentCharacteristic(equipment=equipment, characteristic=self.cores, value="8")
        with self.assertRaises(ValidationError):
            invalid_model.full_clean()
        self.assertFalse(EquipmentCharacteristic.objects.filter(equipment=equipment, characteristic=self.cores).exists())


class InventoryConcurrencyTests(TransactionTestCase):
    """Database-level lock test for the PostgreSQL production backend."""

    reset_sequences = True

    def setUp(self):
        self.section = Section.objects.get(code="computer_server")
        equipment_type = EquipmentType.objects.create(
            section=self.section, code="concurrent-laptop", title="Параллельный ноутбук"
        )
        manufacturer = Manufacturer.objects.create(name="Parallel Example")
        self.model = EquipmentModel.objects.create(
            equipment_type=equipment_type, manufacturer=manufacturer, name="Parallel-1"
        )
        self.status = AssetStatus.objects.get(code="in_stock")
        self.location = Location.objects.create(code="parallel-warehouse", title="Склад тестов")

    def test_parallel_creation_allocates_unique_inventory_numbers(self):
        if connection.vendor != "postgresql":
            self.skipTest("Параллельная блокировка строк проверяется на PostgreSQL; SQLite её не поддерживает.")

        workers = 6
        barrier = threading.Barrier(workers)
        inventory_numbers = []
        errors = []

        def create_in_thread():
            close_old_connections()
            try:
                model = EquipmentModel.objects.get(pk=self.model.pk)
                status = AssetStatus.objects.get(pk=self.status.pk)
                location = Location.objects.get(pk=self.location.pk)
                barrier.wait(timeout=10)
                equipment = create_equipment_with_inventory_number(
                    model=model, status=status, location=location
                )
                inventory_numbers.append(
                    EquipmentIdentifier.objects.get(equipment=equipment, kind__code="inventory").value
                )
            except BaseException as error:  # recorded and asserted in the main thread
                errors.append(error)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=create_in_thread) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(any(thread.is_alive() for thread in threads), "Потоки не завершили работу вовремя.")
        self.assertEqual(errors, [])
        self.assertEqual(len(inventory_numbers), workers)
        self.assertEqual(len(set(inventory_numbers)), workers)
        self.assertEqual(sorted(inventory_numbers), [f"pc-{number:06d}" for number in range(1, workers + 1)])
        self.assertEqual(InventorySequence.objects.get(section=self.section).next_number, workers + 1)
