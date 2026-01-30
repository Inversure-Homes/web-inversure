from django.db import migrations, models

import core.fields


def _encrypt_cliente_data(apps, schema_editor):
    Cliente = apps.get_model("core", "Cliente")
    from core.security import (
        encrypt_value,
        hash_value,
        normalize_dni_cif,
        normalize_email,
        normalize_iban,
        normalize_phone,
    )

    qs = Cliente.objects.all().only(
        "id",
        "dni_cif",
        "email",
        "telefono",
        "iban",
        "direccion_postal",
    )
    for cliente in qs.iterator():
        dni = cliente.dni_cif or ""
        email = cliente.email or ""
        tel = cliente.telefono or ""
        iban = cliente.iban or ""
        direccion = cliente.direccion_postal or ""

        update = {}
        if dni:
            update["dni_cif"] = encrypt_value(dni)
            update["dni_cif_hash"] = hash_value(normalize_dni_cif(dni), "dni_cif")
        if email:
            update["email"] = encrypt_value(email)
            update["email_hash"] = hash_value(normalize_email(email), "email")
        else:
            update["email_hash"] = None
        if tel:
            update["telefono"] = encrypt_value(tel)
            update["telefono_hash"] = hash_value(normalize_phone(tel), "telefono")
        else:
            update["telefono_hash"] = None
        if iban:
            update["iban"] = encrypt_value(iban)
            update["iban_hash"] = hash_value(normalize_iban(iban), "iban")
        else:
            update["iban_hash"] = None
        if direccion:
            update["direccion_postal"] = encrypt_value(direccion)

        if update:
            Cliente.objects.filter(pk=cliente.pk).update(**update)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0040_inversor_portal_pin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cliente",
            name="dni_cif",
            field=core.fields.EncryptedCharField(),
        ),
        migrations.AlterField(
            model_name="cliente",
            name="email",
            field=core.fields.EncryptedTextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="cliente",
            name="telefono",
            field=core.fields.EncryptedCharField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="cliente",
            name="iban",
            field=core.fields.EncryptedCharField(
                blank=True, null=True, help_text="IBAN del cliente (opcional)"
            ),
        ),
        migrations.AlterField(
            model_name="cliente",
            name="direccion_postal",
            field=core.fields.EncryptedTextField(
                blank=True,
                null=True,
                help_text="Dirección postal completa del cliente",
            ),
        ),
        migrations.AddField(
            model_name="cliente",
            name="dni_cif_hash",
            field=models.CharField(
                blank=True, max_length=64, null=True, unique=True, db_index=True
            ),
        ),
        migrations.AddField(
            model_name="cliente",
            name="email_hash",
            field=models.CharField(
                blank=True, max_length=64, null=True, db_index=True
            ),
        ),
        migrations.AddField(
            model_name="cliente",
            name="telefono_hash",
            field=models.CharField(
                blank=True, max_length=64, null=True, db_index=True
            ),
        ),
        migrations.AddField(
            model_name="cliente",
            name="iban_hash",
            field=models.CharField(
                blank=True, max_length=64, null=True, db_index=True
            ),
        ),
        migrations.RunPython(_encrypt_cliente_data, migrations.RunPython.noop),
    ]
