from django.shortcuts import render, redirect
from .models import Proyecto, Cliente

try:
    import pandas as pd
except ImportError:
    pd = None
from django.contrib import messages


# Nueva vista home
def home(request):
    return render(request, "core/home.html")


def parse_euro(value):
    if value in (None, ""):
        return 0.0
    try:
        return float(
            str(value)
            .replace(".", "")
            .replace(",", ".")
            .replace("€", "")
            .replace("\xa0", "")
            .strip()
        )
    except Exception:
        return 0.0


def simulador(request):
    proyectos = Proyecto.objects.all().order_by("-creado", "-id")
    resultado = None
    proyecto = None

    # === CARGA DE PROYECTO POR NOMBRE (GET) ===
    nombre_get = request.GET.get("proyecto")
    if nombre_get:
        proyecto = Proyecto.objects.filter(nombre=nombre_get).first()

    if request.method == "POST":
        data = request.POST

        nombre_proyecto = data.get("nombre")
        proyecto = None

        if nombre_proyecto:
            proyecto = Proyecto.objects.filter(nombre=nombre_proyecto).first()

            # BLOQUEO POR ESTADO: si el proyecto está cerrado positivamente, no se permite recalcular ni sobrescribir
            if proyecto and proyecto.estado == "cerrado_positivo":
                resultado = {
                    "valor_adquisicion": round(proyecto.precio_compra_inmueble or 0, 2),
                    "precio_venta": round(proyecto.precio_venta_estimado or 0, 2),
                    "beneficio_neto": round(proyecto.beneficio_neto or 0, 2),
                    "roi": round(proyecto.roi or 0, 2),
                    "viable": (proyecto.roi or 0) >= 15,
                    "margen_neto": 0,
                    "colchon_seguridad": 0,
                    "ratio_euro": 0,
                    "precio_minimo_venta": 0,
                }
                return render(
                    request,
                    "core/simulador.html",
                    {
                        "proyectos": proyectos,
                        "resultado": resultado,
                        "proyecto": proyecto,
                    },
                )

        """
        ============================================================
        MOTOR DE CÁLCULO – SIMULADOR INVERSURE (CIERRE DEFINITIVO)
        ============================================================

        Este bloque define las reglas económicas base del simulador.
        Estas reglas se consideran ESTABLES y NO deben modificarse
        sin decisión estratégica expresa.

        --- DEFINICIONES CLAVE ---

        1) Precio de escritura
           Valor introducido por el usuario en escritura pública.

        2) Gastos automáticos de adquisición (sobre precio escritura):
           - Notaría: 0,20 % (mínimo 500 €)
           - Registro: 0,20 % (mínimo 500 €)
           - ITP: 2 %

        3) Valor de adquisición:
           Precio de escritura
           + gastos de adquisición
           + inversión inicial
           + gastos recurrentes

           (Los gastos de venta NO forman parte del valor de adquisición)

        4) Precio de venta:
           Por defecto: media de valoraciones.
           Puede ser sobrescrito manualmente para simulación de escenarios.

        5) Beneficio base:
           (Precio de venta – gastos de venta) – valor de adquisición

        6) Gastos de gestión:
           - Gestión comercial: 5 % del beneficio base
           - Gestión administrativa: 5 % del beneficio base

           (Solo se aplican sobre beneficio, nunca sobre costes)

        7) Beneficio neto:
           Beneficio base – gastos de gestión

           El sistema asume beneficio >= 0 en fase de estudio.

        8) ROI (Return on Investment):
           ROI = beneficio neto / valor de adquisición

        9) Viabilidad:
           Una operación se considera VIABLE si:
           ROI >= 15 %

        --- NOTAS IMPORTANTES ---

        - El botón "Calcular" siempre aplica estas reglas.
        - El formulario no redefine la lógica, solo aporta datos.
        - UX, escenarios y visualizaciones NO alteran este motor.
        - Este motor es la base para futuras operaciones reales.

        ============================================================
        """

        # === DATOS BASE ===
        # SIEMPRE leer todos los datos relevantes directamente del formulario (POST)
        precio_escritura = parse_euro(data.get("precio_propiedad"))
        precio_venta = parse_euro(data.get("precio_venta_estimado"))

        # === VALORACIONES ===
        val_idealista = parse_euro(data.get("val_idealista"))
        val_fotocasa = parse_euro(data.get("val_fotocasa"))
        val_registradores = parse_euro(data.get("val_registradores"))
        val_casafari = parse_euro(data.get("val_casafari"))
        val_tasacion = parse_euro(data.get("val_tasacion"))

        valores = [
            v for v in [
                val_idealista,
                val_fotocasa,
                val_registradores,
                val_casafari,
                val_tasacion,
            ] if v > 0
        ]
        media_valoraciones = sum(valores) / len(valores) if valores else 0

        # === GASTOS AUTOMÁTICOS DE ADQUISICIÓN (solo sobre precio_escritura) ===
        notaria = max(float(precio_escritura) * 0.002, 500)
        registro = max(float(precio_escritura) * 0.002, 500)
        itp = float(precio_escritura) * 0.02

        # === GASTOS MANUALES ===
        otros_gastos_compra = parse_euro(data.get("otros_gastos_compra"))

        # Inversión inicial y gastos recurrentes
        reforma = parse_euro(data.get("reforma"))
        limpieza_inicial = parse_euro(data.get("limpieza_inicial"))
        mobiliario = parse_euro(data.get("mobiliario"))
        otros_puesta_marcha = parse_euro(data.get("otros_puesta_marcha"))

        comunidad = parse_euro(data.get("comunidad"))
        ibi = parse_euro(data.get("ibi"))
        seguros = parse_euro(data.get("seguros"))
        suministros = parse_euro(data.get("suministros"))
        limpieza_periodica = parse_euro(data.get("limpieza_periodica"))
        ocupas = parse_euro(data.get("ocupas"))

        inversion_inicial = (
            float(reforma or 0)
            + float(limpieza_inicial or 0)
            + float(mobiliario or 0)
            + float(otros_puesta_marcha or 0)
        )

        gastos_recurrentes = (
            float(comunidad or 0)
            + float(ibi or 0)
            + float(seguros or 0)
            + float(suministros or 0)
            + float(limpieza_periodica or 0)
            + float(ocupas or 0)
        )

        # === VALOR DE ADQUISICIÓN ===
        valor_adquisicion = float(precio_escritura or 0) + float(notaria or 0) + float(registro or 0) + float(itp or 0) + float(otros_gastos_compra or 0) + float(inversion_inicial or 0) + float(gastos_recurrentes or 0)

        # === GASTOS DE VENTA ===
        plusvalia = parse_euro(data.get("plusvalia"))
        inmobiliaria = parse_euro(data.get("inmobiliaria"))
        gastos_venta = float(plusvalia or 0) + float(inmobiliaria or 0)

        # === BENEFICIO BASE ===
        beneficio_base = (precio_venta - gastos_venta) - valor_adquisicion

        # === GESTIÓN COMERCIAL Y ADMINISTRACIÓN ===
        gestion_comercial = beneficio_base * 0.05 if beneficio_base > 0 else 0
        gestion_administracion = beneficio_base * 0.05 if beneficio_base > 0 else 0

        # === BENEFICIO NETO ===
        beneficio_neto = beneficio_base - gestion_comercial - gestion_administracion

        # === ROI ===
        roi = (beneficio_neto / valor_adquisicion) * 100 if valor_adquisicion > 0 else 0

        # === VIABILIDAD ===
        viable = roi >= 15

        # === MÉTRICAS PRO (ANÁLISIS INVERSOR) ===

        # Margen neto sobre precio de venta
        margen_neto = (beneficio_neto / precio_venta) * 100 if precio_venta > 0 else 0

        # === MÉTRICAS INVERSOR AVANZADAS ===
        # Colchón de seguridad (%)
        # ¿Cuánto puede bajar el precio de venta antes de perder dinero?
        colchon_seguridad = (beneficio_neto / precio_venta) * 100 if precio_venta > 0 else 0

        # Ratio € ganado por € invertido
        # Ej: 0,15 € por cada € invertido
        ratio_euro = (beneficio_neto / valor_adquisicion) if valor_adquisicion > 0 else 0

        # Precio mínimo de venta para cumplir ROI mínimo del 15 %
        # Beneficio mínimo exigido = 15 % del valor de adquisición
        beneficio_minimo = valor_adquisicion * 0.15

        # Precio mínimo de venta = adquisición + gastos de venta + beneficio mínimo
        precio_minimo_venta = valor_adquisicion + gastos_venta + beneficio_minimo

        resultado = {
            "valor_adquisicion": round(valor_adquisicion, 2),
            "precio_venta": round(precio_venta, 2),
            "beneficio_neto": round(beneficio_neto, 2),
            "roi": round(roi, 2),
            "viable": viable,

            # Métricas inversor
            "margen_neto": round(margen_neto, 2),
            "colchon_seguridad": round(colchon_seguridad, 2),
            "ratio_euro": round(ratio_euro, 3),
            "precio_minimo_venta": round(precio_minimo_venta, 2),
        }

        # === GUARDAR / ACTUALIZAR PROYECTO (CLAVE = NOMBRE) ===
        if nombre_proyecto:
            estado_post = data.get("estado", "ESTUDIO")
            meses_val = int(data.get("meses")) if data.get("meses") else None
            if proyecto:
                # === ACTUALIZAR PROYECTO EXISTENTE (SIN PÉRDIDA DE DATOS) ===
                # Asignar todos los campos manuales directamente desde el formulario
                proyecto.meses = meses_val
                proyecto.otros_gastos_compra = otros_gastos_compra
                proyecto.reforma = reforma
                proyecto.limpieza_inicial = limpieza_inicial
                proyecto.mobiliario = mobiliario
                proyecto.otros_puesta_marcha = otros_puesta_marcha
                proyecto.comunidad = comunidad
                proyecto.ibi = ibi
                proyecto.seguros = seguros
                proyecto.suministros = suministros
                proyecto.limpieza_periodica = limpieza_periodica
                proyecto.ocupas = ocupas
                proyecto.plusvalia = plusvalia
                proyecto.inmobiliaria = inmobiliaria
                proyecto.val_idealista = val_idealista
                proyecto.val_fotocasa = val_fotocasa
                proyecto.val_registradores = val_registradores
                proyecto.val_casafari = val_casafari
                proyecto.val_tasacion = val_tasacion

                proyecto.precio_propiedad = precio_escritura
                proyecto.precio_compra_inmueble = valor_adquisicion
                proyecto.precio_venta_estimado = precio_venta
                proyecto.notaria = notaria
                proyecto.registro = registro
                proyecto.itp = itp

                proyecto.media_valoraciones = media_valoraciones
                proyecto.gestion_comercial = gestion_comercial
                proyecto.gestion_administracion = gestion_administracion
                proyecto.beneficio_neto = beneficio_neto
                proyecto.roi = roi
                proyecto.estado = estado_post

                proyecto.save()
            else:
                # Crear nuevo proyecto
                proyecto = Proyecto.objects.create(
                    nombre=nombre_proyecto,
                    precio_propiedad=precio_escritura,
                    precio_compra_inmueble=valor_adquisicion,
                    precio_venta_estimado=precio_venta,
                    notaria=notaria,
                    registro=registro,
                    itp=itp,
                    beneficio_neto=beneficio_neto,
                    roi=roi,
                    val_idealista=val_idealista,
                    val_fotocasa=val_fotocasa,
                    val_registradores=val_registradores,
                    val_casafari=val_casafari,
                    val_tasacion=val_tasacion,
                    otros_gastos_compra=otros_gastos_compra,
                    reforma=reforma,
                    limpieza_inicial=limpieza_inicial,
                    mobiliario=mobiliario,
                    otros_puesta_marcha=otros_puesta_marcha,
                    comunidad=comunidad,
                    ibi=ibi,
                    seguros=seguros,
                    suministros=suministros,
                    limpieza_periodica=limpieza_periodica,
                    ocupas=ocupas,
                    plusvalia=plusvalia,
                    inmobiliaria=inmobiliaria,
                    estado=estado_post,
                    media_valoraciones=media_valoraciones,
                    gestion_comercial=gestion_comercial,
                    gestion_administracion=gestion_administracion,
                    meses=meses_val,
                )

    # No refrescar desde BD tras POST

    return render(
        request,
        "core/simulador.html",
        {
            "proyectos": proyectos,
            "resultado": resultado,
            "proyecto": proyecto,
        }
    )


# === BORRAR PROYECTO DEFINITIVAMENTE ===
def borrar_proyecto(request, nombre):
    proyecto = Proyecto.objects.filter(nombre=nombre).first()
    if proyecto:
        proyecto.delete()
    return redirect("simulador")


def lista_proyectos(request):
    proyectos = Proyecto.objects.all().order_by("-fecha", "-id")
    return render(
        request,
        "core/lista_proyectos.html",
        {"proyectos": proyectos},
    )


# Vista clientes
def clientes(request):
    clientes = Cliente.objects.all().order_by("nombre")
    return render(
        request,
        "core/clientes.html",
        {
            "clientes": clientes,
        },
    )


# Nueva vista para crear cliente
def cliente_create(request):
    if request.method == "POST":
        data = request.POST

        Cliente.objects.create(
            tipo_persona=data.get("tipo_persona"),
            nombre=data.get("nombre"),
            dni_cif=data.get("dni_cif"),
            email=data.get("email") or None,
            telefono=data.get("telefono") or None,
            iban=data.get("iban") or None,
            observaciones=data.get("observaciones") or None,
        )

        return redirect("clientes")

    return render(request, "core/clientes_form.html")


# Vista para importar clientes desde Excel
def clientes_import(request):
    if pd is None:
        messages.error(request, "El módulo pandas no está disponible. No se puede importar el Excel.")
        return redirect("clientes")
    """
    Importa clientes desde un archivo Excel.
    El Excel debe contener como mínimo las columnas:
    nombre, dni_cif

    Columnas opcionales:
    tipo_persona, email, telefono, iban, observaciones
    """

    if request.method == "POST" and request.FILES.get("archivo"):
        archivo = request.FILES["archivo"]

        try:
            df = pd.read_excel(archivo)

            creados = 0
            omitidos = 0

            for _, row in df.iterrows():
                dni_cif = str(row.get("dni_cif", "")).strip()
                nombre = str(row.get("nombre", "")).strip()

                if not dni_cif or not nombre:
                    omitidos += 1
                    continue

                if Cliente.objects.filter(dni_cif=dni_cif).exists():
                    omitidos += 1
                    continue

                Cliente.objects.create(
                    tipo_persona=str(row.get("tipo_persona", "F")).upper()[:1],
                    nombre=nombre,
                    dni_cif=dni_cif,
                    email=row.get("email") or None,
                    telefono=row.get("telefono") or None,
                    iban=row.get("iban") or None,
                    observaciones=row.get("observaciones") or None,
                )
                creados += 1

            messages.success(
                request,
                f"Importación finalizada: {creados} clientes creados, {omitidos} omitidos."
            )

        except Exception as e:
            messages.error(request, f"Error al importar el archivo: {e}")

        return redirect("clientes")

    return render(request, "core/clientes_import.html")