from django.db import models


class Proyecto(models.Model):
    # =========================
    # IDENTIFICACIÓN DEL PROYECTO
    # =========================
    nombre = models.CharField(max_length=255)
    fecha = models.DateField(null=True, blank=True)

    # =========================
    # DATOS DEL INMUEBLE
    # =========================
    precio_propiedad = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    precio_compra_inmueble = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    precio_venta_estimado = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    ref_catastral = models.CharField(
        max_length=50, blank=True, null=True
    )
    valor_referencia = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    # =========================
    # GASTOS DE ADQUISICIÓN
    # =========================
    itp = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    notaria = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    registro = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    otros_gastos_compra = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    # =========================
    # INVERSIÓN INICIAL
    # =========================
    reforma = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    limpieza_inicial = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    mobiliario = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    otros_puesta_marcha = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    # =========================
    # GASTOS RECURRENTES
    # =========================
    comunidad = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    ibi = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    seguros = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    suministros = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    limpieza_periodica = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    ocupas = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    # =========================
    # GASTOS DE VENTA
    # =========================
    gastos_comercializacion = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    gastos_administracion = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    plusvalia = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    inmobiliaria = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    # =========================
    # VALORACIONES
    # =========================
    val_idealista = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    val_fotocasa = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    val_registradores = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    val_casafari = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    val_tasacion = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    media_valoraciones = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    # =========================
    # RESULTADOS / MÉTRICAS
    # =========================
    beneficio_bruto = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    beneficio_neto = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    roi = models.DecimalField(
        max_digits=6, decimal_places=2, default=0
    )

    # =========================
    # ESTADO DEL PROYECTO
    # =========================
    ESTADO_CHOICES = (
        ("estudio", "En estudio"),
        ("viable", "Viable"),
        ("descartado", "Descartado"),
        ("operacion", "En operación"),
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="estudio"
    )
    # =========================
    # CONTROL
    # =========================
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nombre} ({self.fecha})"


# =========================
# MODELO CLIENTE
# =========================
class Cliente(models.Model):
    TIPO_PERSONA_CHOICES = (
        ("F", "Persona física"),
        ("J", "Persona jurídica"),
    )

    # =========================
    # IDENTIFICACIÓN
    # =========================
    tipo_persona = models.CharField(
        max_length=1,
        choices=TIPO_PERSONA_CHOICES,
        default="F"
    )

    nombre = models.CharField(
        max_length=255,
        help_text="Nombre completo o razón social"
    )

    dni_cif = models.CharField(
        max_length=20,
        unique=True
    )

    # =========================
    # CONTACTO
    # =========================
    email = models.EmailField(
        blank=True,
        null=True
    )

    telefono = models.CharField(
        max_length=30,
        blank=True,
        null=True
    )

    # =========================
    # DATOS BANCARIOS
    # =========================
    iban = models.CharField(
        max_length=34,
        blank=True,
        null=True,
        help_text="IBAN del cliente (opcional)"
    )

    # =========================
    # CONTROL / NOTAS
    # =========================
    observaciones = models.TextField(
        blank=True,
        null=True
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nombre} ({self.dni_cif})"