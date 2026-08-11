"""
Sorteos de inmuebles (rifas ocasionales, Ley 13/2011).

Esta app se ocupa SOLO de vender participaciones: papeletas, pedidos, pagos y
acta notarial. La cara económica —adquisición del inmueble, ingresos, gastos y
rentabilidad— vive en `core.Proyecto`, al que cada sorteo está enlazado.

Ojo con el vocabulario: `core.Participacion` es la participación de un INVERSOR
en un proyecto. La de una rifa se llama `Papeleta` a propósito, para que nadie
sume dos cosas que no se parecen en nada.
"""

import calendar
import datetime
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .impuestos import COMUNIDADES, Operacion  # noqa: F401


def _sumar_meses(fecha, meses):
    total = fecha.month - 1 + meses
    anio = fecha.year + total // 12
    mes = total % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return datetime.date(anio, mes, dia)


class Organizador(models.Model):
    """
    Entidad que solicita la autorización y figura como organizadora.

    Es un modelo aparte, y no unos ajustes globales, porque cada sorteo puede
    organizarlo una sociedad distinta. Estos datos son obligatorios en las
    bases y en el justificante de participación.
    """

    nombre = models.CharField(max_length=200)
    nif = models.CharField("NIF", max_length=20, blank=True)
    domicilio = models.CharField(max_length=255, blank=True)
    email = models.EmailField()
    datos_registrales = models.CharField(
        max_length=255,
        blank=True,
        help_text="Registro Mercantil, tomo, folio y hoja. Figura en las bases.",
    )
    autorizacion_dgoj = models.CharField(
        "Nº de autorización DGOJ",
        max_length=120,
        blank=True,
        help_text="Resolución de la Dirección General de Ordenación del Juego. Sin ella no se puede abrir la venta.",
    )

    class Meta:
        verbose_name = "organizador"
        verbose_name_plural = "organizadores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Sorteo(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        EN_VENTA = "en_venta", "En venta"
        CERRADO = "cerrado", "Venta cerrada"
        SORTEADO = "sorteado", "Sorteado"

    proyecto = models.OneToOneField(
        "core.Proyecto",
        on_delete=models.PROTECT,
        related_name="sorteo",
        help_text="Proyecto del ERP que soporta la economía de este sorteo.",
    )
    organizador = models.ForeignKey(Organizador, on_delete=models.PROTECT, related_name="sorteos")

    slug = models.SlugField(unique=True)
    titulo = models.CharField(max_length=200)
    premio_descripcion = models.CharField(max_length=255)

    precio_participacion = models.DecimalField(max_digits=8, decimal_places=2)
    total_participaciones = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Nº total de participaciones emitidas. La tasa del 20 % se "
        "anticipa sobre este número, no sobre las vendidas.",
    )
    max_por_pedido = models.PositiveIntegerField(default=50)
    reserva_minutos = models.PositiveIntegerField(default=10)

    fecha_inicio_venta = models.DateField()
    fecha_fin_venta = models.DateField(null=True, blank=True, help_text="Último día de venta de participaciones.")
    fecha_sorteo = models.DateField(help_text="No puede distar más de un año del inicio de la venta.")
    hora_sorteo = models.TimeField(null=True, blank=True)

    # Condición de celebración: sin un mínimo, el organizador queda obligado a
    # entregar el inmueble aunque solo se venda una fracción de las
    # participaciones. Ver apartado 9 de las bases.
    minimo_participaciones = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Mínimo de participaciones vendidas para celebrar el sorteo. "
        "Si se deja vacío, el sorteo se celebra incondicionalmente.",
    )
    dias_reintegro = models.PositiveIntegerField(default=30, help_text="Plazo de reintegro si el sorteo se cancela.")

    # Tipo de la tasa sobre actividades de juego. El 7 % aplica a rifas
    # declaradas de beneficencia o de utilidad pública; en otro caso, el 20 %.
    # Es la palanca que más mueve el resultado de toda la operación.
    tasa_juego_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        verbose_name="Tasa sobre actividades de juego (%)",
    )
    comision_pago_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.30"),
        verbose_name="Comisión media de la pasarela (%)",
        help_text="Depende del tamaño medio del pedido. Con Stripe y pedidos de 3 participaciones ronda el 2,3 %.",
    )

    # El ingreso a cuenta del IRPF sobre un premio en especie: quién lo asume
    # debe constar en las bases y saberse antes de comprar.
    organizador_asume_ingreso_cuenta = models.BooleanField(
        default=True,
        verbose_name="El organizador asume el ingreso a cuenta del IRPF",
    )
    importe_ingreso_cuenta = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Solo si se repercute a la persona premiada.",
    )
    caducidad_premio_meses = models.PositiveIntegerField(
        default=12,
        validators=[MinValueValidator(12)],
        help_text="Plazo para reclamar el premio. La normativa exige un mínimo de doce meses.",
    )

    territorio = models.CharField(max_length=200, default="Todo el territorio español")
    version_bases = models.CharField(max_length=20, default="1.0")

    # El sorteo se celebra siempre ante notario: la normativa no admite que el
    # resultado lo genere el organizador.
    notaria_nombre = models.CharField(max_length=200, blank=True)
    notaria_poblacion = models.CharField(max_length=120, blank=True)

    # Datos del inmueble, obligatorios en las bases cuando el premio es un bien
    # inmueble.
    inmueble_direccion = models.CharField(max_length=255, blank=True)
    inmueble_superficie = models.CharField(max_length=80, blank=True)
    inmueble_referencia_catastral = models.CharField(max_length=40, blank=True)
    inmueble_datos_registrales = models.CharField(max_length=255, blank=True)
    inmueble_valor = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Impuesto de la compra. El ITP lo fija cada comunidad y la operación decide
    # si es ITP o IVA; con esto se calcula solo si el proyecto no lo trae.
    comunidad = models.CharField(
        max_length=30,
        blank=True,
        choices=COMUNIDADES,
        verbose_name="Comunidad autónoma del inmueble",
    )
    operacion_compra = models.CharField(
        max_length=10,
        blank=True,
        default=Operacion.ITP,
        choices=Operacion.OPCIONES,
        verbose_name="Impuesto de la compra",
    )
    # Ningún tipo reducido se aplica solo: hay que elegirlo a sabiendas, porque
    # aplicarlo sin cumplir los requisitos se paga después con intereses.
    supuesto_reducido = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="Tipo reducido aplicado",
        help_text="Déjalo vacío para calcular al tipo general. Los supuestos "
        "que podrían aplicar se listan en el panel del sorteo.",
    )
    compra_para_reventa = models.BooleanField(
        default=True,
        verbose_name="Se adquiere para revender, dentro de la actividad inmobiliaria",
        help_text="Condición de los tipos reducidos por reventa profesional.",
    )

    inmueble_cargas = models.TextField(default="Libre de cargas y gravámenes.")
    inmueble_gastos = models.TextField(
        default="Los gastos de notaría, registro e impuestos derivados de la transmisión corren por cuenta del ganador."
    )

    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.BORRADOR)

    # Sello del listado que se entrega al notario. Se calcula al cerrar la
    # venta y se publica antes del sorteo: cualquiera puede recalcularlo sobre
    # el listado recibido y comprobar que no se ha tocado después.
    cerrado_en = models.DateTimeField(null=True, blank=True)
    hash_listado = models.CharField(max_length=64, blank=True)
    participaciones_vendidas_cierre = models.PositiveIntegerField(null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "sorteo"
        verbose_name_plural = "sorteos"
        ordering = ["-fecha_sorteo"]

    def __str__(self):
        return self.titulo

    # -- Cifras -------------------------------------------------------------

    @property
    def vendidas(self):
        return self.papeletas.filter(estado=Papeleta.Estado.PAGADA).count()

    @property
    def reservadas(self):
        return self.papeletas.filter(estado=Papeleta.Estado.RESERVADA).count()

    @property
    def disponibles(self):
        return self.papeletas.filter(estado=Papeleta.Estado.LIBRE).count()

    @property
    def recaudado(self):
        return self.vendidas * self.precio_participacion

    @property
    def objetivo(self):
        return self.total_participaciones * self.precio_participacion

    @property
    def porcentaje_vendido(self):
        if not self.total_participaciones:
            return 0
        return round(self.vendidas * 100 / self.total_participaciones)

    @property
    def fecha_caducidad_premio(self):
        return _sumar_meses(self.fecha_sorteo, self.caducidad_premio_meses)

    @property
    def abierto(self):
        return self.estado == self.Estado.EN_VENTA

    def generar_papeletas(self):
        """Crea las papeletas que falten. Idempotente."""
        existentes = set(self.papeletas.values_list("numero", flat=True))
        nuevas = [
            Papeleta(sorteo=self, numero=n) for n in range(1, self.total_participaciones + 1) if n not in existentes
        ]
        if nuevas:
            Papeleta.objects.bulk_create(nuevas, batch_size=1000)
        return len(nuevas)


class Pedido(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de pago"
        PAGADO = "pagado", "Pagado"
        CADUCADO = "caducado", "Caducado"

    class Origen(models.TextChoices):
        WEB = "web", "Web"
        MANUAL = "manual", "Registro manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sorteo = models.ForeignKey(Sorteo, on_delete=models.PROTECT, related_name="pedidos")

    nombre = models.CharField(max_length=120)
    email = models.EmailField()
    telefono = models.CharField(max_length=30, blank=True)

    importe = models.DecimalField(max_digits=10, decimal_places=2)
    codigo = models.CharField("localizador", max_length=12, db_index=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)

    # Prueba de que se aceptaron las bases y se declaró la mayoría de edad. La
    # normativa prohíbe la participación de menores, así que hay que poder
    # acreditar cuándo, desde dónde y sobre qué versión de las bases.
    version_bases = models.CharField(max_length=20)
    acepta_bases_en = models.DateTimeField()
    ip = models.GenericIPAddressField(null=True, blank=True)

    # Las ventas presenciales (efectivo, transferencia) se registran a mano
    # desde el ERP: entran en el sorteo igual que las de la web y deben poder
    # distinguirse a efectos de conciliación.
    origen = models.CharField(max_length=20, choices=Origen.choices, default=Origen.WEB)
    medio_pago = models.CharField(max_length=60, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Solo en registros manuales.",
    )

    stripe_session_id = models.CharField(max_length=255, blank=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    pagado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["sorteo", "estado"])]

    def __str__(self):
        return "{} · {} · {} €".format(self.codigo, self.nombre, self.importe)

    @property
    def numeros(self):
        return list(self.papeletas.order_by("numero").values_list("numero", flat=True))

    @property
    def numeros_texto(self):
        return ", ".join(str(n) for n in self.numeros)


class Papeleta(models.Model):
    class Estado(models.TextChoices):
        LIBRE = "libre", "Libre"
        RESERVADA = "reservada", "Reservada"
        PAGADA = "pagada", "Pagada"

    sorteo = models.ForeignKey(Sorteo, on_delete=models.CASCADE, related_name="papeletas")
    numero = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.LIBRE)
    reserva_expira = models.DateTimeField(null=True, blank=True)
    pedido = models.ForeignKey(
        Pedido,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="papeletas",
    )

    class Meta:
        verbose_name = "papeleta"
        verbose_name_plural = "papeletas"
        ordering = ["numero"]
        constraints = [models.UniqueConstraint(fields=["sorteo", "numero"], name="papeleta_unica_por_sorteo")]
        indexes = [
            models.Index(fields=["sorteo", "estado"]),
            models.Index(fields=["estado", "reserva_expira"]),
        ]

    def __str__(self):
        return "#{} ({})".format(self.numero, self.get_estado_display())


class Interesado(models.Model):
    """
    Lista de espera previa a la autorización.

    Mientras la DGOJ no autorice el sorteo no se puede vender nada, así que
    esto NO es una compra ni una reserva: es una anotación de interés. De ahí
    tres consecuencias de diseño:

    - No se pide DNI ni dirección. No hacen falta para avisar por email, y
      pedirlos sería exceso de datos además de fricción inútil.
    - La base jurídica es el **consentimiento**, no la ejecución de un
      contrato. Debe poder revocarse: de ahí `token_baja`.
    - Se piden dos datos que no sirven para avisar pero sí para decidir:
      cuántas participaciones compraría y hasta qué precio. Sin ellos la lista
      cuenta personas; con ellos estima demanda, que es lo que hace falta para
      saber si merece la pena comprar el inmueble.
    """

    class Precio(models.TextChoices):
        HASTA_10 = "10", "Hasta 10 €"
        HASTA_20 = "20", "Hasta 20 €"
        HASTA_25 = "25", "Hasta 25 €"
        HASTA_50 = "50", "Hasta 50 €"
        MAS_50 = "51", "Más de 50 €"

    sorteo = models.ForeignKey(
        Sorteo,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="interesados",
        help_text="Puede no existir todavía cuando alguien se apunta.",
    )

    nombre = models.CharField(max_length=120)
    email = models.EmailField()
    telefono = models.CharField(max_length=30, blank=True)
    provincia = models.CharField(
        max_length=60,
        blank=True,
        help_text="Una plaza de garaje interesa sobre todo cerca. Saber de "
        "dónde viene la demanda cambia dónde se hace la campaña.",
    )

    participaciones_estimadas = models.PositiveIntegerField(default=1)
    precio_maximo = models.CharField(max_length=4, choices=Precio.choices, default=Precio.HASTA_10)

    mayor_edad = models.BooleanField(default=False)
    acepta_aviso = models.BooleanField(default=False, verbose_name="Consiente recibir el aviso de apertura")

    token_baja = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    baja_en = models.DateTimeField(null=True, blank=True)

    ip = models.GenericIPAddressField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "interesado"
        verbose_name_plural = "interesados"
        ordering = ["-creado_en"]
        constraints = [models.UniqueConstraint(fields=["sorteo", "email"], name="interesado_unico_por_sorteo")]

    def __str__(self):
        return "{} <{}>".format(self.nombre, self.email)

    @property
    def activo(self):
        return self.baja_en is None


class ActaSorteo(models.Model):
    """
    Resultado del sorteo celebrado ante notario.

    Esta aplicación no sortea: transcribe el acta. El notario extrae entre las
    papeletas efectivamente vendidas, así que `numero_premiado` tiene que ser
    una de ellas — se valida en el servicio antes de guardar.
    """

    sorteo = models.OneToOneField(Sorteo, on_delete=models.PROTECT, related_name="acta")
    numero_premiado = models.PositiveIntegerField()
    pedido = models.ForeignKey(Pedido, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    protocolo = models.CharField("nº de protocolo", max_length=120)
    notario = models.CharField(max_length=200, blank=True)
    fecha = models.DateField()

    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "acta de sorteo"
        verbose_name_plural = "actas de sorteo"

    def __str__(self):
        return "Acta {} · nº {}".format(self.protocolo, self.numero_premiado)


class EstudioRifa(models.Model):
    """
    Escenario de rifa guardado, previo a comprometer nada.

    Es el equivalente del `Estudio` del ERP para el resto de operaciones: aquí
    se prueban combinaciones de precio, número de participaciones y comunidad
    sobre un inmueble que a lo mejor ni se ha comprado, se comparan entre sí y
    solo el que convence se convierte en `Sorteo`.

    No guarda resultados calculados a propósito: se recalculan al abrirlo, para
    que un cambio en los tipos impositivos o en la tasa se refleje en los
    estudios viejos en vez de dejarlos mintiendo.
    """

    nombre = models.CharField(max_length=160)
    notas = models.TextField(blank=True)

    proyecto = models.ForeignKey(
        "core.Proyecto",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="estudios_rifa",
        help_text="Opcional: precarga los datos de un proyecto existente.",
    )

    # Inmueble
    precio_compra = models.DecimalField(max_digits=12, decimal_places=2)
    valor_referencia = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor de referencia de Catastro. Si es mayor que el precio, es la base del impuesto.",
    )
    comunidad = models.CharField(max_length=30, blank=True, choices=COMUNIDADES)
    operacion_compra = models.CharField(max_length=10, blank=True, default=Operacion.ITP, choices=Operacion.OPCIONES)
    supuesto_reducido = models.CharField(max_length=40, blank=True)
    # Gastos de compra. Cada uno se calcula solo si se deja vacío; poner un
    # importe manda sobre el cálculo, que es lo que hará falta cuando lleguen
    # las facturas de verdad.
    gastos_notaria = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Notaría de la compra (€)",
        help_text="Vacío: se calcula por el arancel del RD 1426/1989.",
    )
    gastos_registro = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Registro de la propiedad (€)",
        help_text="Vacío: se calcula por el arancel del RD 1427/1989.",
    )
    gastos_gestoria = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Gestoría de la compra (€)",
        help_text="Vacío: se estiman 400 €.",
    )

    # Gastos propios del sorteo, más allá de los impuestos.
    tasa_dgoj = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Tasa de autorización DGOJ (€)",
        help_text="Vacío: 100 €, que es la tasa vigente.",
    )
    gastos_notaria_sorteo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Notaría del sorteo (€)",
        help_text="Vacío: se estiman 400 €.",
    )
    gastos_asesoria = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Asesoría jurídica y fiscal (€)",
        help_text="Vacío: se estiman 800 €.",
    )

    # La campaña no es un extra: en una rifa es lo que decide si se coloca.
    presupuesto_marketing = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Presupuesto de marketing (€)",
        help_text="Campaña, creatividades, anuncios. Es lo que separa vender 300 papeletas de vender 3.000.",
    )
    otros_gastos = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Otros gastos (€)",
        help_text="Lo que no encaje en los anteriores.",
    )

    # Rifa
    precio_participacion = models.DecimalField(max_digits=8, decimal_places=2, default=10)
    participaciones = models.PositiveIntegerField(default=5000)
    tasa_juego_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    comision_pago_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("2.30"))
    minimo_participaciones = models.PositiveIntegerField(null=True, blank=True)

    # Venta ordinaria, para poder comparar las dos rutas
    precio_venta_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    meses_venta = models.PositiveIntegerField(default=6)
    meses_rifa = models.PositiveIntegerField(default=6)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    sorteo = models.OneToOneField(
        "Sorteo",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="estudio_origen",
        help_text="Sorteo en el que se convirtió, si llegó a hacerse.",
    )
    archivado = models.BooleanField(
        default=False,
        help_text="Descarta el estudio conservándolo. Para deshacerse de él del todo está el borrado.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "estudio de rifa"
        verbose_name_plural = "estudios de rifa"
        ordering = ["-actualizado_en"]

    def __str__(self):
        return self.nombre

    def desglose_gastos(self):
        """
        Cada gasto con su importe y de dónde sale: calculado o puesto a mano.

        Se devuelve la procedencia además del número porque no es lo mismo un
        arancel estimado que una factura real, y quien lea el estudio tiene
        que poder distinguirlo.
        """
        from . import aranceles

        def fila(concepto, valor, calculado, nota=""):
            return {
                "concepto": concepto,
                "importe": valor if valor is not None else calculado,
                "calculado": valor is None,
                "nota": nota,
            }

        base = self.precio_compra or Decimal("0")
        return [
            fila(
                "Notaría de la compra",
                self.gastos_notaria,
                aranceles.notaria(base),
                "Arancel RD 1426/1989 aproximado a factura.",
            ),
            fila(
                "Registro de la propiedad",
                self.gastos_registro,
                aranceles.registro(base),
                "Arancel RD 1427/1989 aproximado a factura.",
            ),
            fila("Gestoría de la compra", self.gastos_gestoria, Decimal("400")),
            fila("Tasa de autorización DGOJ", self.tasa_dgoj, Decimal("100"), "Tasa vigente para rifas ocasionales."),
            fila("Notaría del sorteo", self.gastos_notaria_sorteo, Decimal("400")),
            fila("Asesoría jurídica y fiscal", self.gastos_asesoria, Decimal("800")),
            fila("Marketing y campaña", self.presupuesto_marketing, Decimal("0")),
            fila("Otros gastos", self.otros_gastos, Decimal("0")),
        ]

    @property
    def gastos_totales(self):
        return sum(f["importe"] for f in self.desglose_gastos())

    def como_datos(self):
        """Diccionario que entiende el comparador."""
        return {
            "precio_compra": self.precio_compra,
            "valor_referencia": self.valor_referencia,
            "comunidad": self.comunidad,
            "operacion": self.operacion_compra,
            "supuesto_reducido": self.supuesto_reducido,
            "otros_gastos": self.gastos_totales,
            "desglose": self.desglose_gastos(),
            "precio_participacion": self.precio_participacion,
            "participaciones": self.participaciones,
            "tasa_pct": self.tasa_juego_porcentaje,
            "comision_pago_pct": self.comision_pago_porcentaje,
            "precio_venta": self.precio_venta_estimado or 0,
            "meses_venta": self.meses_venta,
            "meses_rifa": self.meses_rifa,
        }
