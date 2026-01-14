from django.db import models
from django.utils.text import slugify
from django.utils.timezone import now


class Hero(models.Model):
    etiqueta = models.CharField(max_length=120, blank=True)
    titulo = models.CharField(max_length=200)
    subtitulo = models.CharField(max_length=300, blank=True)
    cta_texto = models.CharField(max_length=80, default="Acceder a la plataforma")
    cta_url = models.CharField(max_length=200, default="/app/")
    fondo_color = models.CharField(
        max_length=20,
        blank=True,
        help_text="Color de fondo en formato HEX. Ej: #0b1324",
    )
    fondo_imagen = models.ImageField(upload_to="landing/hero/fondos/", blank=True, null=True)
    imagen = models.ImageField(upload_to="landing/hero/", blank=True, null=True)
    panel_titulo = models.CharField(max_length=120, blank=True)
    panel_texto = models.CharField(max_length=200, blank=True)
    panel_footer = models.CharField(max_length=120, blank=True)
    meta_1_valor = models.CharField(max_length=40, blank=True)
    meta_1_texto = models.CharField(max_length=80, blank=True)
    meta_2_valor = models.CharField(max_length=40, blank=True)
    meta_2_texto = models.CharField(max_length=80, blank=True)
    meta_3_valor = models.CharField(max_length=40, blank=True)
    meta_3_texto = models.CharField(max_length=80, blank=True)
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
