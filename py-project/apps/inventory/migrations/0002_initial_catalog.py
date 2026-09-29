from django.db import migrations


def add_initial_catalog(apps, schema_editor):
    Section = apps.get_model("inventory", "Section")
    AssetStatus = apps.get_model("inventory", "AssetStatus")
    IdentifierKind = apps.get_model("inventory", "IdentifierKind")

    Section.objects.bulk_create(
        [
            Section(code="computer_server", title="Компьютерная и серверная техника", inventory_prefix="pc"),
            Section(code="peripheral", title="Периферия", inventory_prefix="prf"),
            Section(code="component", title="Комплектующие", inventory_prefix="adv"),
            Section(code="network", title="Сетевое оборудование", inventory_prefix="ntw"),
        ],
        ignore_conflicts=True,
    )
    AssetStatus.objects.bulk_create(
        [
            AssetStatus(code="in_stock", title="На складе"),
            AssetStatus(code="in_use", title="В эксплуатации"),
            AssetStatus(code="in_repair", title="В ремонте"),
            AssetStatus(code="retired", title="Списано", is_terminal=True),
        ],
        ignore_conflicts=True,
    )
    IdentifierKind.objects.bulk_create(
        [
            IdentifierKind(code="inventory", title="Инвентарный номер"),
            IdentifierKind(code="manufacturer_serial", title="Серийный номер производителя"),
            IdentifierKind(code="mac_address", title="MAC-адрес"),
        ],
        ignore_conflicts=True,
    )


def remove_initial_catalog(apps, schema_editor):
    # Initial reference data is preserved intentionally: equipment could refer to it.
    pass


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]

    operations = [migrations.RunPython(add_initial_catalog, remove_initial_catalog)]
