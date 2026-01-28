from django.conf import settings
from django.db import models
from django.utils.timezone import now


class Estudio(models.Model):
    codigo_estudio = models.PositiveIntegerField(
        unique=True,
        null=True,
        blank=True,
        help_text="Código interno visible del estudio (contador propio)"
    )
    nombre = models.CharField(max_length=255)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    ref_catastral = models.CharField(max_length=50, blank=True, null=True)
    valor_referencia = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    datos = models.JSONField(
        default=dict,
        blank=True,
        help_text="Payload JSON del estudio (estado del simulador). Se inicializa vacío para evitar errores en creación."
    )
    guardado = models.BooleanField(
        default=False,
        help_text="Marca si el estudio está finalizado/guardado (True) o es borrador (False)"
    )

    bloqueado = models.BooleanField(
        default=False,
        help_text="Si True, el estudio está congelado (no editable) porque ha sido convertido a proyecto"
    )

    bloqueado_en = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha/hora en que el estudio se bloqueó (conversión a proyecto)"
    )
    conversion_solicitada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="estudios_conversion_solicitada",
        help_text="Usuario que solicitó la conversión a proyecto"
    )
    conversion_solicitada_en = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha/hora en que se solicitó la conversión a proyecto"
    )
    conversion_aprobada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="estudios_conversion_aprobada",
        help_text="Administrador que aprobó la conversión a proyecto"
    )
    conversion_aprobada_en = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha/hora de aprobación de la conversión a proyecto"
    )
    valor_adquisicion = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    beneficio = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    roi = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if self.codigo_estudio is None:
            ultimo = Estudio.objects.aggregate(models.Max("codigo_estudio"))["codigo_estudio__max"]
            self.codigo_estudio = 0 if ultimo is None else ultimo + 1
        super().save(*args, **kwargs)


# =========================
# MODELO SNAPSHOT DE ESTUDIO (CIERRE DEFINITIVO)
# =========================
class EstudioSnapshot(models.Model):
    estudio = models.ForeignKey(
        Estudio,
        on_delete=models.CASCADE,
        related_name="snapshots"
    )

    # --- CONTROL ---
    creado_en = models.DateTimeField(auto_now_add=True)
    version_simulador = models.CharField(
        max_length=20,
        default="v1",
        help_text="Versión del simulador con la que se generó el snapshot"
    )

    # --- ESTADO DEL ESTUDIO ---
    ESTADO_CHOICES = (
        ("borrador", "Borrador"),
        ("aprobado", "Aprobado"),
        ("en_estudio", "En estudio"),
        ("denegado", "Denegado"),
    )

    estado_estudio = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="borrador",
        help_text="Estado del estudio en el momento de generar el snapshot"
    )

    fecha_decision_comite = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha de la decisión del comité (si aplica)"
    )

    # --- METADATA ---
    codigo_version = models.CharField(
        max_length=30,
        help_text="Código legible de versión del estudio (ej: EST-2026-001-v1)"
    )

    es_convertible = models.BooleanField(
        default=False,
        help_text="Indica si este snapshot puede convertirse en proyecto"
    )

    # --- DATOS CONGELADOS ---
    datos = models.JSONField(
        help_text="Datos completos congelados del estudio (comité, inversor, económico)"
    )

    def __str__(self):
        return (
            f"Snapshot {self.codigo_version} · "
            f"{self.get_estado_estudio_display()} · "
            f"{self.creado_en.strftime('%d/%m/%Y %H:%M')}"
        )

class Proyecto(models.Model):
    # =========================
    # ORIGEN (FASE 2: CONVERSIÓN DESDE ESTUDIO)
    # =========================
    origen_estudio = models.ForeignKey(
        Estudio,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="proyectos",
        help_text="Estudio del que procede este proyecto (fase de análisis previa)"
    )

    origen_snapshot = models.ForeignKey(
        EstudioSnapshot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="proyectos",
        help_text="Snapshot final del estudio usado para convertir a proyecto (estado congelado)"
    )

    snapshot_datos = models.JSONField(
        null=True,
        blank=True,
        help_text="Copia inmutable de los datos del snapshot en el momento de conversión"
    )
    extra = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        help_text="Datos extensibles del proyecto (checklists, notas, hitos, comité final, etc.)"
    )

    convertido_desde_estudio = models.BooleanField(
        default=False,
        help_text="Marca si el proyecto fue generado desde un estudio (True) o creado manualmente"
    )
    # =========================
    # IDENTIFICACIÓN DEL PROYECTO
    # =========================
    nombre = models.CharField(max_length=255)
    fecha = models.DateField(null=True, blank=True)
    codigo_proyecto = models.PositiveIntegerField(
        unique=True,
        null=True,
        blank=True,
        help_text="Código interno visible del proyecto (contador propio)"
    )
    responsable_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="proyectos_responsable",
        help_text="Usuario responsable del proyecto",
    )
    responsable = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Nombre visible del responsable (compatibilidad)",
    )
    acceso_comercial = models.BooleanField(
        default=False,
        help_text="Permite acceso del equipo comercial a este proyecto",
    )
    mostrar_en_landing = models.BooleanField(
        default=False,
        help_text="Permite mostrar este proyecto en la landing pública",
    )
    difusion_clientes = models.ManyToManyField(
        "Cliente",
        blank=True,
        related_name="proyectos_difusion",
        help_text="Clientes seleccionados para la difusión de este proyecto",
    )

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
    # =========================
    # GASTOS DE PROYECTO (DEPRECATED)
    # -------------------------
    # Los siguientes campos (itp, notaria, registro, etc.) están DEPRECATED.
    # NO deben usarse como fuente de verdad económica.
    # El único origen válido de los gastos es GastoProyecto.
    # Se mantienen temporalmente por compatibilidad y para no romper vistas ni cálculos existentes.
    # =========================
    # DEPRECATED: No usar para cálculos ni lógica económica.
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
    # DEPRECATED: No usar para cálculos ni lógica económica.
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
    # DEPRECATED: No usar para cálculos ni lógica económica.
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
    # DEPRECATED: No usar para cálculos ni lógica económica.
    cerrajero = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    alarma = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )

    # =========================
    # DEPRECATED: No usar para cálculos ni lógica económica.
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
    # DEPRECATED: No usar para cálculos ni lógica económica.
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
        ("captacion", "Captación"),
        ("comprado", "Comprado"),
        ("comercializacion", "Comercialización"),
        ("reservado", "Reservado"),
        ("vendido", "Vendido"),
        ("cerrado", "Cerrado"),
        ("descartado", "Descartado"),
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="captacion"
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

    def save(self, *args, **kwargs):
        if self.codigo_proyecto is None:
            ultimo = Proyecto.objects.aggregate(models.Max("codigo_proyecto"))["codigo_proyecto__max"]
            self.codigo_proyecto = 0 if ultimo is None else int(ultimo) + 1
        super().save(*args, **kwargs)

    def es_estudio(self):
        return self.estado in {"captacion", "estudio"}

    def es_operacion(self):
        return self.estado in {"comprado", "comercializacion", "reservado", "vendido", "cerrado"}

    def __str__(self):
        return f"{self.nombre} ({self.fecha})"


#
# =========================
# MODELO SNAPSHOT DE PROYECTO (TRAZABILIDAD / VERSIONADO)
# =========================
class ProyectoSnapshot(models.Model):
    FUENTE_CHOICES = (
        ("conversion", "Conversión desde estudio"),
        ("guardado", "Guardado de proyecto"),
        ("cierre", "Cierre / venta"),
    )

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="snapshots",
        help_text="Proyecto al que pertenece este snapshot"
    )

    creado_en = models.DateTimeField(auto_now_add=True)

    fuente = models.CharField(
        max_length=20,
        choices=FUENTE_CHOICES,
        default="guardado",
        help_text="Motivo/origen del snapshot"
    )

    version_num = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Número de versión incremental por proyecto (v1, v2, ...)"
    )

    codigo_version = models.CharField(
        max_length=40,
        blank=True,
        help_text="Código legible (ej: PRJ-2026-000001-v3)"
    )

    nota = models.CharField(
        max_length=255,
        blank=True,
        help_text="Nota corta de la versión (opcional)"
    )

    datos = models.JSONField(
        help_text="Datos completos congelados del proyecto en este momento (overlay: base_snapshot + reales + kpis)"
    )

    class Meta:
        ordering = ["-creado_en", "-id"]

    def __str__(self):
        cod = self.codigo_version or f"Proyecto {self.proyecto_id}"
        return f"{cod} · {self.creado_en.strftime('%d/%m/%Y %H:%M')}"

    def save(self, *args, **kwargs):
        # Autonumeración por proyecto
        if self.version_num is None:
            ultimo = (
                ProyectoSnapshot.objects.filter(proyecto=self.proyecto)
                .aggregate(models.Max("version_num"))
                .get("version_num__max")
            )
            self.version_num = 1 if ultimo is None else int(ultimo) + 1

        # Código legible
        if not self.codigo_version:
            year = now().year
            pid = self.proyecto_id or 0
            self.codigo_version = f"PRJ-{year}-{pid:06d}-v{self.version_num}"

        super().save(*args, **kwargs)

# =========================
# MODELO PRESUPUESTO DE PROYECTO (ESCENARIO EDITABLE)
# =========================
class PresupuestoProyecto(models.Model):
    proyecto = models.OneToOneField(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="presupuesto"
    )

    concepto = models.CharField(
        max_length=255,
        help_text="Concepto del gasto o ingreso presupuestado"
    )

    categoria = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    importe_previsto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Importe estimado del concepto"
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.proyecto} · Presupuesto · {self.concepto}"


# =========================
# MODELO GASTO DE PROYECTO
# =========================
# GastoProyecto es la única fuente de verdad económica del proyecto.
# Todo gasto comienza como ESTIMADO y pasa a CONFIRMADO cuando existe justificante real.
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
        ("estimado", "Estimado"),
        ("confirmado", "Confirmado"),
    ]

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.PROTECT,
        related_name="gastos_proyecto"
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
    importe_estimado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Importe estimado original"
    )
    importe_real = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Importe real confirmado"
    )

    imputable_inversores = models.BooleanField(
        default=True,
        help_text="Indica si el gasto se imputa a los inversores"
    )

    estado = models.CharField(
        max_length=15,
        choices=ESTADOS,
        default="estimado"
    )

    observaciones = models.TextField(
        blank=True,
        null=True
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    @property
    def es_estimado(self):
        return self.estado == "estimado"

    @property
    def es_real(self):
        return self.estado == "confirmado"

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
        ("indemnizacion", "Indemnización"),
        ("otro", "Otro ingreso"),
    ]
    ESTADOS = [
        ("estimado", "Estimado"),
        ("confirmado", "Confirmado"),
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
    importe_estimado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Importe estimado original"
    )
    importe_real = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Importe real confirmado"
    )
    estado = models.CharField(
        max_length=15,
        choices=ESTADOS,
        default="estimado"
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
# CHECKLIST OPERATIVO
# =========================
class ChecklistItem(models.Model):
    FASES = [
        ("compra", "Compra"),
        ("post_compra", "Post-compra"),
        ("operacion", "Operación"),
        ("venta", "Venta"),
        ("post_venta", "Post-venta"),
    ]
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("en_curso", "En curso"),
        ("hecho", "Hecho"),
    ]

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="checklist_items"
    )
    fase = models.CharField(max_length=20, choices=FASES, default="compra")
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    responsable = models.CharField(max_length=255, blank=True, null=True)
    responsable_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checklist_items_asignados",
    )
    fecha_objetivo = models.DateField(blank=True, null=True)
    estado = models.CharField(max_length=15, choices=ESTADOS, default="pendiente")
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checklist_items_cerrados",
    )
    cerrado_en = models.DateTimeField(null=True, blank=True)
    coste_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    coste_real = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    gasto = models.ForeignKey(
        GastoProyecto,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="checklist_items"
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fase", "fecha_objetivo", "id"]

    def __str__(self):
        return f"{self.proyecto} · {self.titulo}"


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

    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("confirmada", "Confirmada"),
        ("cancelada", "Cancelada"),
    ]
    estado = models.CharField(
        max_length=12,
        choices=ESTADOS,
        default="pendiente"
    )

    # =========================
    # CONTROL
    # =========================
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    beneficio_neto_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Beneficio neto del inversor para operaciones históricas (override manual)"
    )
    beneficio_override_data = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        help_text="Overrides detallados del beneficio (bruto, comisión, neto, retención, etc.)"
    )

    def __str__(self):
        return f"{self.cliente} → {self.proyecto} ({self.importe_invertido} €)"


# =========================
# PERFIL INVERSOR (PORTAL)
# =========================
class InversorPerfil(models.Model):
    cliente = models.OneToOneField(
        Cliente,
        on_delete=models.CASCADE,
        related_name="perfil_inversor"
    )
    token = models.CharField(max_length=64, unique=True)
    activo = models.BooleanField(default=True)
    proyectos_visibles = models.JSONField(
        null=True,
        blank=True,
        default=list,
        help_text="IDs de proyectos visibles en el portal del inversor",
    )
    aportacion_inicial_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Ajuste manual de la aportación inicial para operaciones históricas",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.token:
            import secrets
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Inversor · {self.cliente.nombre}"


# =========================
# PUSH SUSCRIPTIONS (INVERSOR)
# =========================
class InversorPushSubscription(models.Model):
    inversor = models.ForeignKey(
        InversorPerfil,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizado", "-creado", "-id"]

    def __str__(self):
        return f"Push inversor · {self.inversor.cliente.nombre}"


# =========================
# SOLICITUDES DE PARTICIPACIÓN
# =========================
class SolicitudParticipacion(models.Model):
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("aprobada", "Aprobada"),
        ("rechazada", "Rechazada"),
    ]

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="solicitudes_participacion"
    )
    inversor = models.ForeignKey(
        InversorPerfil,
        on_delete=models.CASCADE,
        related_name="solicitudes"
    )
    importe_solicitado = models.DecimalField(max_digits=12, decimal_places=2)
    comentario = models.TextField(blank=True, null=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default="pendiente")
    decision_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_decididas",
    )
    decision_at = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado", "-id"]

    def __str__(self):
        return f"{self.inversor.cliente.nombre} → {self.proyecto} ({self.importe_solicitado} €)"


# =========================
# COMUNICACIONES AL INVERSOR
# =========================
class ComunicacionInversor(models.Model):
    inversor = models.ForeignKey(
        InversorPerfil,
        on_delete=models.CASCADE,
        related_name="comunicaciones"
    )
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comunicaciones_inversores"
    )
    titulo = models.CharField(max_length=255)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado", "-id"]

    def __str__(self):
        return f"{self.titulo} ({self.inversor.cliente.nombre})"


# =========================
# DOCUMENTOS DE PROYECTO
# =========================
class DocumentoProyecto(models.Model):
    CATEGORIAS = [
        ("inmueble", "Documentación inmueble"),
        ("facturas", "Facturas"),
        ("fotografias", "Fotografías"),
        ("presentacion", "Presentación"),
        ("otros", "Otros"),
    ]
    TIPO_CHOICES = CATEGORIAS

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="documentos"
    )
    tipo = models.CharField(
        max_length=30,
        choices=TIPO_CHOICES,
        default="otros"
    )
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="otros")
    titulo = models.CharField(max_length=255)
    archivo = models.FileField(upload_to="proyectos/documentos/%Y/%m/")
    fecha_factura = models.DateField(
        blank=True,
        null=True,
        help_text="Fecha de la factura (solo para categoria facturas)",
    )
    importe_factura = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Importe de la factura (solo para categoria facturas)",
    )
    es_principal = models.BooleanField(default=False)
    usar_pdf = models.BooleanField(default=False)
    usar_story = models.BooleanField(default=False)
    usar_instagram = models.BooleanField(default=False)
    usar_dossier = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado", "-id"]

    def __str__(self):
        return f"{self.proyecto} · {self.titulo}"


# =========================
# DOCUMENTOS PERSONALES INVERSOR
# =========================
class DocumentoInversor(models.Model):
    CATEGORIAS = [
        ("contrato", "Contrato"),
        ("retenciones", "Certificado retenciones"),
        ("comunicaciones", "Comunicaciones"),
        ("otros", "Otros"),
    ]

    inversor = models.ForeignKey(
        InversorPerfil,
        on_delete=models.CASCADE,
        related_name="documentos"
    )
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="otros")
    titulo = models.CharField(max_length=255)
    archivo = models.FileField(upload_to="inversores/documentos/%Y/%m/")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado", "-id"]

    def __str__(self):
        return f"{self.inversor} · {self.titulo}"


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
#
# =========================
# MODELO GASTOS ESTIMADOS DEL PROYECTO (FASE ESTUDIO)
# =========================
class GastosProyectoEstimacion(models.Model):

    proyecto = models.OneToOneField(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="gastos_estimacion"
    )

    # --- GASTOS DE ADQUISICIÓN ---
    precio_escritura = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_precio_escritura = models.CharField(max_length=10, default="estimado")

    impuestos = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_impuestos = models.CharField(max_length=10, default="estimado")

    notaria = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_notaria = models.CharField(max_length=10, default="estimado")

    registro = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_registro = models.CharField(max_length=10, default="estimado")

    gestoria = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_gestoria = models.CharField(max_length=10, default="estimado")

    # --- GASTOS DE MANTENIMIENTO ---
    ibi = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_ibi = models.CharField(max_length=10, default="estimado")

    comunidad = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_comunidad = models.CharField(max_length=10, default="estimado")

    luz = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_luz = models.CharField(max_length=10, default="estimado")

    agua = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_agua = models.CharField(max_length=10, default="estimado")

    alarma = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_alarma = models.CharField(max_length=10, default="estimado")

    cerrajero = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_cerrajero = models.CharField(max_length=10, default="estimado")

    limpieza_vaciado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_limpieza_vaciado = models.CharField(max_length=10, default="estimado")

    # --- GASTOS DE OBRA ---
    obra_reforma = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_obra_reforma = models.CharField(max_length=10, default="estimado")

    obra_materiales = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_obra_materiales = models.CharField(max_length=10, default="estimado")

    obra_mano_obra = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_obra_mano_obra = models.CharField(max_length=10, default="estimado")

    obra_tecnico = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_obra_tecnico = models.CharField(max_length=10, default="estimado")

    obra_licencias = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_obra_licencias = models.CharField(max_length=10, default="estimado")

    obra_contingencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_obra_contingencia = models.CharField(max_length=10, default="estimado")

    # --- COMERCIALIZACIÓN Y GESTIÓN ---
    comercializacion = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_comercializacion = models.CharField(max_length=10, default="estimado")

    administracion = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_administracion = models.CharField(max_length=10, default="estimado")

    comision_inversure = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado_comision_inversure = models.CharField(max_length=10, default="estimado")

    # --- VENTA ESTIMADA ---
    valor_transmision_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Estimación de gastos · {self.proyecto}"

# =========================
# MODELO DATOS ECONÓMICOS REALES DEL PROYECTO (G3.1)
# =========================
class DatosEconomicosProyecto(models.Model):

    ESTADO_OPERATIVO_CHOICES = [
        ("captacion", "Captación"),
        ("comercializacion", "Comercialización"),
        ("cierre", "Cierre"),
        ("vendido", "Vendido"),
        ("cancelado", "Cancelado"),
    ]

    proyecto = models.OneToOneField(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="datos_economicos"
    )

    # Estado operativo
    estado_operativo = models.CharField(
        max_length=20,
        choices=ESTADO_OPERATIVO_CHOICES,
        default="captacion"
    )
    fecha_estado = models.DateField(
        null=True,
        blank=True
    )
    observaciones_estado = models.TextField(
        blank=True,
        null=True
    )

    # --- PORCENTAJES DE GESTIÓN SOBRE BENEFICIO BRUTO ---
    porcentaje_comercializacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5,
        help_text="Porcentaje de comercialización sobre el beneficio bruto"
    )

    porcentaje_administracion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5,
        help_text="Porcentaje de administración sobre el beneficio bruto"
    )

    # --- ADQUISICIÓN REAL ---
    precio_compra_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    fecha_compra_real = models.DateField(
        null=True, blank=True
    )
    tipo_adquisicion = models.CharField(
        max_length=20,
        null=True, blank=True
    )
    impuesto_tipo = models.CharField(
        max_length=10, null=True, blank=True
    )
    impuesto_porcentaje_real = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    impuesto_importe_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    notaria_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    registro_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    gestoria_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    otros_gastos_adquisicion_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # --- VENTA REAL ---
    precio_venta_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    fecha_venta_real = models.DateField(
        null=True, blank=True
    )
    gastos_venta_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    plusvalia_municipal_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    honorarios_agencia_real = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # --- GESTIÓN INVERSURE ---
    TIPO_COMISION_CHOICES = [
        ("porcentaje_beneficio", "Porcentaje sobre beneficio"),
        ("porcentaje_ingresos", "Porcentaje sobre ingresos"),
        ("importe_fijo", "Importe fijo"),
    ]

    tipo_comision_gestion = models.CharField(
        max_length=30,
        choices=TIPO_COMISION_CHOICES,
        default="porcentaje_beneficio"
    )
    valor_comision_gestion = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Datos económicos · {self.proyecto}"

# =========================
# MODELO MOVIMIENTO ECONÓMICO DE PROYECTO (G3.1)
# =========================
class MovimientoEconomicoProyecto(models.Model):

    TIPO_CHOICES = [
        ("operacion", "Operación"),
        ("ingreso", "Ingreso"),
        ("comercializacion", "Comercialización"),
    ]

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="movimientos_economicos"
    )

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES
    )
    subtipo = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )
    concepto = models.CharField(
        max_length=255
    )
    fecha = models.DateField()
    importe = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    documento = models.ForeignKey(
        'DocumentoProyecto',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "id"]

    def __str__(self):
        return f"{self.proyecto} · {self.concepto} · {self.importe} €"

# =========================
# MODELO MOVIMIENTO REAL DE PROYECTO (TRAZABILIDAD)
# =========================
class MovimientoProyecto(models.Model):

    TIPO_CHOICES = [
        ("gasto", "Gasto"),
        ("ingreso", "Ingreso"),
    ]

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="movimientos"
    )

    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES
    )

    concepto = models.CharField(
        max_length=255
    )

    fecha = models.DateField()

    importe = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    documento = models.FileField(
        upload_to="movimientos_proyecto/%Y/%m/",
        blank=True,
        null=True
    )

    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "id"]

    def __str__(self):
        return f"{self.proyecto} · {self.tipo} · {self.importe} €"
