from django.db import models
from django.utils.timezone import now


class Proyecto(models.Model):
    # =========================
    # IDENTIFICACIÓN DEL PROYECTO
    # =========================
    nombre = models.CharField(max_length=255)
    fecha = models.DateField(null=True, blank=True)

    # =========================
    # DATOS DEL INMUEBLE
    # =========================
    direccion = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Dirección del inmueble del proyecto"
    )
    lat = models.FloatField(
        null=True,
        blank=True,
        help_text="Latitud del inmueble (geolocalización)"
    )
    lon = models.FloatField(
        null=True,
        blank=True,
        help_text="Longitud del inmueble (geolocalización)"
    )
    precio_propiedad = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    precio_compra_inmueble = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )

    fecha_compra = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha real de adquisición del inmueble"
    )

    TIPO_ADQUISICION_CHOICES = (
        ("directa", "Compra directa"),
        ("deuda", "Compra de deuda"),
        ("subasta", "Subasta"),
        ("dacion", "Dación en pago"),
    )

    tipo_adquisicion = models.CharField(
        max_length=20,
        choices=TIPO_ADQUISICION_CHOICES,
        null=True,
        blank=True,
        help_text="Tipo de adquisición del inmueble"
    )
    precio_venta_estimado = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    ref_catastral = models.CharField(
        max_length=50, blank=True, null=True
    )
    valor_referencia = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )

    # =========================
    # GASTOS DE ADQUISICIÓN
    # =========================
    itp = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    impuesto_tipo = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text="Tipo de impuesto aplicado (ITP / IVA)"
    )
    impuesto_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Porcentaje de impuesto aplicado"
    )
    notaria = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    registro = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    otros_gastos_compra = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )

    # =========================
    # INVERSIÓN INICIAL
    # =========================
    reforma = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    limpieza_inicial = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    mobiliario = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    otros_puesta_marcha = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )

    # =========================
    # OBRA (DETALLE POR PARTIDAS)
    # =========================
    obra_demoliciones = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_albanileria = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_fontaneria = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_electricidad = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_carpinteria_interior = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_carpinteria_exterior = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_cocina = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_banos = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_pintura = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    obra_otros = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )

    # =========================
    # SEGURIDAD
    # =========================
    cerrajero = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    alarma = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )

    # =========================
    # GASTOS RECURRENTES
    # =========================
    comunidad = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    ibi = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    seguros = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    suministros = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    limpieza_periodica = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    ocupas = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )

    # =========================
    # GASTOS DE VENTA
    # =========================
    gestion_comercial = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    gestion_administracion = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    plusvalia = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    inmobiliaria = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )

    # =========================
    # VALORACIONES
    # =========================
    val_idealista = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    val_fotocasa = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    val_registradores = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    val_casafari = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    val_tasacion = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    media_valoraciones = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    # =========================
    # DURACIÓN DE LA OPERACIÓN
    # =========================
    meses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duración estimada de la operación en meses"
    )
    # =========================
    # NOTA:
    # Los campos de resultados (beneficio, ROI, etc.)
    # NO son fuente de verdad.
    # Se recalculan dinámicamente en views.py
    # y se almacenan solo a efectos informativos / históricos.
    # =========================
    # RESULTADOS / MÉTRICAS
    # =========================
    beneficio_bruto = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    beneficio_neto = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    roi = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, default=None
    )

    # =========================
    # INVERSIÓN / CAPTACIÓN
    # =========================
    capital_objetivo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Capital total que se desea captar para el proyecto"
    )

    inversion_completa = models.BooleanField(
        default=False,
        help_text="Indica si la inversión del proyecto está completamente cubierta"
    )

    # =========================
    # ESTADO DEL PROYECTO
    # =========================
    ESTADO_CHOICES = (
        ("estudio", "En estudio"),
        ("reservado", "Reservado"),
        ("comprado", "Comprado"),
        ("operacion", "En operación"),
        ("vendido", "Vendido"),
        ("descartado", "Descartado"),
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="estudio"
    )

    # =========================
    # CONTROL DE APROBACIÓN (PDF OFICIAL)
    # =========================
    aprobado = models.BooleanField(
        default=False,
        help_text="Indica si el proyecto ha sido aprobado por el comité"
    )

    pdf_aprobado = models.FileField(
        upload_to="proyectos_aprobados/",
        null=True,
        blank=True,
        help_text="PDF oficial aprobado del proyecto"
    )

    fecha_aprobacion = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora de aprobación del proyecto"
    )
    # =========================
    # ORIGEN DE LA SIMULACIÓN
    # =========================
    simulacion_origen = models.ForeignKey(
        "Simulacion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="proyectos_generados",
        help_text="Simulación de la que procede este proyecto (si aplica)"
    )
    # =========================
    # CONTROL
    # =========================
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    # =========================
    # NOTA FUNCIONAL
    # =========================
    # El modelo Proyecto actúa únicamente como
    # contenedor de datos persistentes.
    #
    # NO se aplica ninguna lógica de cálculo,
    # estimación ni formateo en el modelo.
    #
    # Toda la lógica económica y de rentabilidad
    # se resuelve exclusivamente en views.py
    # y/o en el frontend (simulador).

    def es_estudio(self):
        return self.estado == "estudio"

    def es_operacion(self):
        return self.estado == "operacion"

    def __str__(self):
        return f"{self.nombre} ({self.fecha})"


# =========================
# MODELO GASTO DE PROYECTO
# =========================
class GastoProyecto(models.Model):

    CATEGORIAS = [
        ("adquisicion", "Adquisición"),
        ("reforma", "Reforma"),
        ("seguridad", "Seguridad"),
        ("operativos", "Gastos operativos"),
        ("financieros", "Financieros"),
        ("legales", "Legales"),
        ("venta", "Venta"),
        ("otros", "Otros"),
    ]

    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("pagado", "Pagado"),
        ("provisionado", "Provisionado"),
        ("anulado", "Anulado"),
    ]

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.PROTECT,
        related_name="gastos"
    )

    fecha = models.DateField()

    categoria = models.CharField(
        max_length=20,
        choices=CATEGORIAS
    )

    concepto = models.CharField(
        max_length=255
    )

    proveedor = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    importe = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    imputable_inversores = models.BooleanField(
        default=True,
        help_text="Indica si el gasto se imputa a los inversores"
    )

    estado = models.CharField(
        max_length=15,
        choices=ESTADOS,
        default="pendiente"
    )

    observaciones = models.TextField(
        blank=True,
        null=True
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha", "id"]

    def __str__(self):
        return f"{self.proyecto} · {self.concepto} · {self.importe} €"


# =========================
# MODELO FACTURA DE GASTO
# =========================
class FacturaGasto(models.Model):

    gasto = models.OneToOneField(
        GastoProyecto,
        on_delete=models.CASCADE,
        related_name="factura"
    )

    archivo = models.FileField(
        upload_to="facturas_proyectos/%Y/%m/"
    )

    nombre_original = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    fecha_subida = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Factura · {self.gasto.concepto}"


# =========================
# MODELO INGRESO DE PROYECTO (C2.3)
# =========================
class IngresoProyecto(models.Model):

    TIPOS_INGRESO = [
        ("senal", "Señal / Arras"),
        ("venta", "Venta"),
        ("anticipo", "Anticipo"),
        ("devolucion", "Devolución"),
        ("otro", "Otro ingreso"),
    ]

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="ingresos"
    )

    fecha = models.DateField()

    tipo = models.CharField(
        max_length=20,
        choices=TIPOS_INGRESO
    )

    concepto = models.CharField(
        max_length=255
    )

    importe = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Importe del ingreso (positivo o negativo)"
    )

    imputable_inversores = models.BooleanField(
        default=True,
        help_text="Indica si el ingreso computa para inversores"
    )

    observaciones = models.TextField(
        blank=True,
        null=True
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha", "id"]

    def __str__(self):
        return f"{self.proyecto} · {self.tipo} · {self.importe} €"


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

    # =========================
    # DATOS ADMINISTRATIVOS
    # =========================
    fecha_introduccion = models.DateField(
        default=now,
        help_text="Fecha de alta del cliente en el sistema"
    )

    direccion_postal = models.TextField(
        blank=True,
        null=True,
        help_text="Dirección postal completa del cliente"
    )

    cuota_abonada = models.BooleanField(
        default=False,
        help_text="Indica si el cliente ha abonado la cuota"
    )

    presente_en_comunidad = models.BooleanField(
        default=False,
        help_text="Indica si el cliente está presente en la comunidad"
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nombre} ({self.dni_cif})"

# =========================
# MODELO PARTICIPACIÓN (INVERSORES EN PROYECTOS)
# =========================
class Participacion(models.Model):
    # =========================
    # RELACIONES
    # =========================
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="participaciones"
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="participaciones"
    )

    # =========================
    # DATOS DE INVERSIÓN
    # =========================
    importe_invertido = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Cantidad aportada por el cliente al proyecto"
    )

    porcentaje_participacion = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Porcentaje de participación sobre el total invertido"
    )

    # =========================
    # CONTROL
    # =========================
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.cliente} → {self.proyecto} ({self.importe_invertido} €)"


# =========================
# MODELO SIMULACIÓN
# =========================
class Simulacion(models.Model):
    # =========================
    # IDENTIFICACIÓN
    # =========================
    nombre = models.CharField(
        max_length=255,
        help_text="Nombre identificativo de la simulación"
    )

    fecha = models.DateField(
        default=now,
        help_text="Fecha de creación de la simulación"
    )

    # =========================
    # DATOS DEL INMUEBLE (BÁSICOS)
    # =========================
    direccion = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )
    lat = models.FloatField(
        null=True,
        blank=True,
        help_text="Latitud del inmueble (geolocalización)"
    )
    lon = models.FloatField(
        null=True,
        blank=True,
        help_text="Longitud del inmueble (geolocalización)"
    )

    ref_catastral = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    # =========================
    # VALORES BÁSICOS
    # =========================
    precio_compra = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Precio estimado de compra del inmueble"
    )

    precio_venta_estimado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Precio estimado de venta del inmueble"
    )

    gastos_estimados = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Gastos estimados globales (simplificados)"
    )

    # =========================
    # RESULTADOS
    # =========================
    beneficio_estimado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Beneficio estimado de la simulación"
    )

    roi_estimado = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="ROI estimado (%)"
    )

    # =========================
    # RESULTADOS CALCULADOS (DETALLE)
    # =========================
    inversion_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    beneficio = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    roi = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    viable = models.BooleanField(
        default=False,
        help_text="Indica si la simulación supera los criterios de viabilidad"
    )

    convertida = models.BooleanField(
        default=False,
        help_text="Indica si la simulación ya ha sido convertida en proyecto"
    )
    # =========================
    # CONTROL
    # =========================
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Simulación: {self.nombre}"