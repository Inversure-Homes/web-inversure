from django.db import migrations
from django.utils.text import slugify


def fill_slugs(apps, schema_editor):
    Noticia = apps.get_model("landing", "Noticia")
    for noticia in Noticia.objects.all():
        if noticia.slug:
            continue
        base = slugify(noticia.titulo)[:200] or "noticia"
        candidate = base
        i = 1
        while Noticia.objects.filter(slug=candidate).exclude(pk=noticia.pk).exists():
            i += 1
            candidate = f"{base}-{i}"
        noticia.slug = candidate
        noticia.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("landing", "0003_mediaasset"),
    ]

    operations = [
        migrations.RunPython(fill_slugs, reverse_code=migrations.RunPython.noop),
    ]
