from django.db import models
from django.utils.text import slugify
from django.utils.timezone import now


class Hero(models.Model):
    titulo = models.CharField(max_length=200)
    subtitulo = models.CharField(max_length=300, blank=True)
    cta_texto = models.CharField(max_length=80, default="Acceder a la plataforma")
    cta_url = models.CharField(max_length=200, default="/app/")
    imagen = models.ImageField(upload_to="landing/hero/", blank=True, null=True)
    activo = models.BooleanField(default=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizado", "-id"]

    def __str__(self):
        return self.titulo


class Seccion(models.Model):
    titulo = models.CharField(max_length=200)
    texto = models.TextField(blank=True)
    icono = models.CharField(
        max_length=60,
        blank=True,
        help_text="Nombre de icono Bootstrap (ej. bi-shield-lock).",
    )
    imagen = models.ImageField(upload_to="landing/secciones/", blank=True, null=True)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return self.titulo


class Noticia(models.Model):
    ESTADOS = [
        ("borrador", "Borrador"),
        ("publicado", "Publicado"),
        ("archivado", "Archivado"),
    ]

    titulo = models.CharField(max_length=220)
    slug = models.SlugField(max_length=240, unique=True, blank=True)
    extracto = models.TextField(blank=True)
    cuerpo = models.TextField()
    imagen = models.ImageField(upload_to="landing/noticias/", blank=True, null=True)
    autor = models.CharField(max_length=120, blank=True)
    fecha_publicacion = models.DateField(default=now)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="borrador")
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_publicacion", "-id"]

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.titulo)[:200] or "noticia"
            candidate = base
            i = 1
            while Noticia.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                i += 1
                candidate = f"{base}-{i}"
            self.slug = candidate
        super().save(*args, **kwargs)


class MediaAsset(models.Model):
    CATEGORIAS = [
        ("general", "General"),
        ("landing", "Landing"),
        ("noticias", "Noticias"),
    ]

    titulo = models.CharField(max_length=200, blank=True)
    archivo = models.ImageField(upload_to="landing/media/")
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="general")
    alt_texto = models.CharField(max_length=200, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado", "-id"]

    def __str__(self):
        return self.titulo or self.archivo.name
