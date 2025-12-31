def f(x):
    """Cast to float, handling Decimal and None."""
    if x is None:
        return 0.0
    try:
        return float(x)
    except Exception:
        return 0.0

from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import csrf_protect
from decimal import Decimal
from .models import Proyecto, Cliente, Participacion, Simulacion
from .models import GastoProyecto
from .models import IngresoProyecto

try:
    import pandas as pd
except ImportError:
    pd = None
from django.contrib import messages
import requests
import xml.etree.ElementTree as ET
from django.http import JsonResponse


# Nueva vista home
def home(request):
    return render(request, "core/home.html")


from decimal import Decimal, InvalidOperation

def parse_euro(value):
    if value in (None, ""):
        return Decimal("0")
    try:
        cleaned = (
            str(value)
            .replace("€", "")
            .replace("\xa0", "")
            .replace(".", "")
            .replace(",", ".")
            .strip()
        )
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def consultar_catastro_por_rc(ref_catastral):
    """
    Consulta SOAP REAL al Catastro a partir de una referencia catastral.
    Devuelve un dict con direccion, lat, lon si existen.
    Nunca lanza excepción: devuelve None si no hay datos útiles.
    """
    if not ref_catastral:
        return None

    url = "https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCSWLocalizacionRC.asmx"

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://www.catastro.meh.es/Consulta_RCCOOR",
        "User-Agent": "Inversure/1.0",
    }

    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <Consulta_RCCOOR xmlns="http://www.catastro.meh.es/">
      <RC>{ref_catastral}</RC>
    </Consulta_RCCOOR>
  </soap:Body>
</soap:Envelope>
"""

    try:
        response = requests.post(
            url,
            data=soap_body.encode("utf-8"),
            headers=headers,
            timeout=15,
        )

        if response.status_code != 200:
            print("❌ Catastro HTTP error:", response.status_code)
            return None

        xml = response.content.decode("utf-8", errors="ignore")
        print("📦 XML Catastro recibido:\n", xml)

        root = ET.fromstring(xml)

        # Buscar campos SIN depender de namespaces estrictos
        def find_text(tag):
            el = root.find(f".//{tag}")
            return el.text.strip() if el is not None and el.text else None

        direccion = find_text("ldt")
        municipio = find_text("nmp")
        provincia = find_text("npp")

        direccion_completa = None
        if direccion and municipio and provincia:
            direccion_completa = f"{direccion}, {municipio}, {provincia}"
        elif direccion:
            direccion_completa = direccion

        lat = find_text("xcen")
        lon = find_text("ycen")

        lat_val = float(lat) if lat else None
        lon_val = float(lon) if lon else None

        if not direccion_completa and lat_val is None and lon_val is None:
            print("⚠️ Catastro respondió sin datos útiles")
            return None

        return {
            "direccion": direccion_completa,
            "lat": lat_val,
            "lon": lon_val,
        }

    except Exception as e:
        print("❌ Error procesando SOAP Catastro:", e)
        return None

from django.shortcuts import get_object_or_404

@csrf_exempt
def simulador(request, proyecto_id=None):
    """
    Vista saneada del simulador:
    - Nunca borra datos existentes
    - Calcular ≠ Guardar
    - No formatea euros
    - No toca mapa ni JS
    """

    proyecto = None
    if proyecto_id:
        try:
            proyecto = Proyecto.objects.get(id=proyecto_id)
        except Proyecto.DoesNotExist:
            return redirect("core:estudio_detalle", proyecto_id)
    resultado = None
    editable = True

    def safe_post(name):
        """
        Devuelve:
        - "__MISSING__" si el campo NO viene en el POST (no tocar en BD)
        - None si viene vacío (permitir borrar explícito)
        - valor si viene informado
        """
        if name not in request.POST:
            return "__MISSING__"
        val = request.POST.get(name)
        return None if val == "" else val

    if request.method == "POST":
        accion = request.POST.get("accion")

        # =========================
        # GUARDAR DATOS (SIN CALCULAR)
        # =========================
        if accion in ("guardar", "convertir") and proyecto:
            campos = [
                # Identificación
                "nombre", "direccion", "ref_catastral", "estado",

                # Datos principales
                "precio_propiedad", "venta_estimada", "meses",

                # Gastos de adquisición
                "notaria", "registro", "itp", "otros_gastos_compra",

                # Inversión inicial
                "limpieza_inicial", "mobiliario", "otros_puesta_marcha",

                # OBRA 4A
                "obra_demoliciones",
                "obra_albanileria",
                "obra_fontaneria",
                "obra_electricidad",
                "obra_carpinteria_interior",
                "obra_carpinteria_exterior",
                "obra_cocina",
                "obra_banos",
                "obra_pintura",
                "obra_otros",

                # SEGURIDAD 4B
                "seguridad_cerrajero",
                "seguridad_alarma",

                # REFORMA (resultado)
                "reforma",

                # Gastos recurrentes
                "comunidad", "ibi", "seguros", "suministros",
                "limpieza_periodica", "ocupas",

                # Gastos de venta
                "plusvalia", "inmobiliaria",

                # Valoraciones
                "val_idealista", "val_fotocasa", "val_registradores",
                "val_casafari", "val_tasacion",
            ]

            CAMPOS_NUMERICOS = {
                # Datos principales
                "precio_propiedad",
                "venta_estimada",
                "meses",

                # Gastos de adquisición
                "notaria",
                "registro",
                "itp",
                "otros_gastos_compra",

                # Inversión inicial
                "limpieza_inicial",
                "mobiliario",
                "otros_puesta_marcha",

                # OBRA 4A
                "obra_demoliciones",
                "obra_albanileria",
                "obra_fontaneria",
                "obra_electricidad",
                "obra_carpinteria_interior",
                "obra_carpinteria_exterior",
                "obra_cocina",
                "obra_banos",
                "obra_pintura",
                "obra_otros",

                # SEGURIDAD 4B
                "seguridad_cerrajero",
                "seguridad_alarma",

                # REFORMA (resultado)
                "reforma",

                # Gastos recurrentes
                "comunidad",
                "ibi",
                "seguros",
                "suministros",
                "limpieza_periodica",
                "ocupas",

                # Gastos de venta
                "plusvalia",
                "inmobiliaria",

                # Valoraciones
                "val_idealista",
                "val_fotocasa",
                "val_registradores",
                "val_casafari",
                "val_tasacion",
            }

            for campo in campos:
                valor = safe_post(campo)

                # Campo no enviado → NO tocar
                if valor == "__MISSING__":
                    continue

                # Campo enviado vacío → permitir borrar
                if valor is None:
                    setattr(proyecto, campo, None)
                    continue

                # Campo con valor
                if campo in CAMPOS_NUMERICOS:
                    setattr(proyecto, campo, parse_euro(valor))
                else:
                    setattr(proyecto, campo, valor)

            proyecto.save()

            if accion == "guardar":
                return redirect("core:simulador", proyecto_id=proyecto.id)

            if accion == "convertir":
                proyecto.estado = "estudio"
                proyecto.save(update_fields=["estado"])
                return redirect("core:lista_proyectos")

        # =========================
        # CALCULAR / ANALIZAR VIABILIDAD (SIN GUARDAR)
        # =========================
        if accion in ("calcular", "analizar") and proyecto:
            precio_escritura = parse_euro(request.POST.get("precio_propiedad"))
            valores = [
                parse_euro(request.POST.get("val_idealista")),
                parse_euro(request.POST.get("val_fotocasa")),
                parse_euro(request.POST.get("val_registradores")),
                parse_euro(request.POST.get("val_casafari")),
                parse_euro(request.POST.get("val_tasacion")),
            ]
            valores = [v for v in valores if v > 0]
            media_valoraciones = sum(valores) / len(valores) if valores else 0

            notaria = max(precio_escritura * Decimal("0.002"), Decimal("500"))
            registro = max(precio_escritura * Decimal("0.002"), Decimal("500"))
            itp = precio_escritura * Decimal("0.02")

            gastos_adquisicion = notaria + registro + itp
            valor_adquisicion = precio_escritura + gastos_adquisicion
            precio_venta = media_valoraciones
            beneficio = precio_venta - valor_adquisicion
            roi = (beneficio / valor_adquisicion * Decimal("100")) if valor_adquisicion else Decimal("0")

            # NUEVAS MÉTRICAS CLAVE
            ratio_euro = (beneficio / valor_adquisicion) if valor_adquisicion else Decimal("0")
            margen_neto = (beneficio / precio_venta * Decimal("100")) if precio_venta else Decimal("0")

            # Precio mínimo de venta exigido por Inversure
            precio_min_15 = valor_adquisicion * Decimal("1.15")
            precio_min_30000 = valor_adquisicion + Decimal("30000")
            precio_minimo_venta = max(precio_min_15, precio_min_30000)

            # Colchón de seguridad (%)
            colchon_seguridad = (
                (precio_venta - precio_minimo_venta) / precio_venta * Decimal("100")
            ) if precio_venta else Decimal("0")

            # =========================
            # LÓGICA ANALISTA INVERSURE
            # =========================

            # Umbral dominante
            if precio_min_15 >= precio_min_30000:
                umbral_dominante = "Rentabilidad mínima 15 %"
            else:
                umbral_dominante = "Beneficio mínimo 30.000 €"

            # Diferencia vs mínimo exigido
            diferencia_vs_minimo = precio_venta - precio_minimo_venta

            # Dictamen automático
            if diferencia_vs_minimo >= 0:
                dictamen = "La operación cumple los criterios mínimos de Inversure."
            else:
                dictamen = (
                    "La operación NO cumple los criterios mínimos de Inversure. "
                    "El precio estimado de venta debería incrementarse para alcanzar el umbral exigido."
                )

            resultado = {
                "valor_adquisicion": float(round(valor_adquisicion, 2)),
                "precio_venta": float(round(precio_venta, 2)),
                "beneficio_neto": float(round(beneficio, 2)),
                "roi": round(roi, 2),

                # 🔹 MÉTRICAS QUE FALTABAN
                "ratio_euro": round(ratio_euro, 2),
                "margen_neto": round(margen_neto, 2),
                "colchon_seguridad": round(colchon_seguridad, 2),
                "precio_minimo_venta": float(round(precio_minimo_venta, 2)),

                "umbral_dominante": umbral_dominante,
                "diferencia_vs_minimo": float(round(diferencia_vs_minimo, 2)),
                "dictamen": dictamen,

                "viable": beneficio >= Decimal("30000") or roi >= Decimal("15"),
            }

    if proyecto and proyecto.estado and proyecto.estado.lower() in ["cerrado", "cerrado_positivo"]:
        editable = False

    return render(
        request,
        "core/simulador.html",
        {
            "proyecto": proyecto,
            "resultado": resultado,
            "editable": editable,
        },
    )


from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET

@require_POST
def cambiar_estado_proyecto(request, proyecto_id):
    estado_nuevo = request.POST.get("estado")

    ESTADOS_VALIDOS = [
        "estudio",
        "operacion",
        "cerrado",
        "descartado",
    ]

    proyecto = Proyecto.objects.filter(id=proyecto_id).first()
    if not proyecto:
        return redirect("lista_proyectos")

    if estado_nuevo not in ESTADOS_VALIDOS:
        return redirect("lista_proyectos")

    proyecto.estado = estado_nuevo
    proyecto.save(update_fields=["estado"])

    return redirect("core:lista_proyectos")




 
# =========================
# AÑADIR INVERSOR A PROYECTO
# =========================
def participacion_create(request, proyecto_id):
    proyecto = Proyecto.objects.filter(id=proyecto_id).first()
    if not proyecto:
        return redirect("lista_proyectos")

    clientes = Cliente.objects.all().order_by("nombre")

    if request.method == "POST":
        cliente_id = request.POST.get("cliente")
        importe = request.POST.get("importe_invertido")

        if cliente_id and importe:
            try:
                importe_val = float(
                    str(importe)
                    .replace(".", "")
                    .replace(",", ".")
                    .replace("€", "")
                    .strip()
                )
            except Exception:
                importe_val = 0

            porcentaje = 0
            if proyecto.precio_compra_inmueble and proyecto.precio_compra_inmueble > 0:
                porcentaje = (importe_val / proyecto.precio_compra_inmueble) * 100

            Participacion.objects.create(
                proyecto=proyecto,
                cliente_id=cliente_id,
                importe_invertido=importe_val,
                porcentaje_participacion=porcentaje,
            )

        return redirect("participacion_create", proyecto_id=proyecto.id)

    participaciones = Participacion.objects.filter(proyecto=proyecto)

    return render(
        request,
        "core/participacion_form.html",
        {
            "proyecto": proyecto,
            "clientes": clientes,
            "participaciones": participaciones,
        },
    )


# =========================
# LISTA DE ESTUDIOS (estado = "estudio")
# =========================
def lista_estudios(request):
    """
    Muestra únicamente los proyectos en fase de ESTUDIO.
    No incluye proyectos operativos ni simulaciones.
    """
    estudios = Proyecto.objects.filter(estado__iexact="estudio").order_by("-id")

    return render(
        request,
        "core/lista_estudio.html",
        {
            "estudios": estudios,
        },
    )
def lista_proyectos(request):
    """
    Lista de proyectos REAL.
    Se pasa al template información ENRIQUECIDA para cada card:
    - capital objetivo
    - capital captado
    - porcentaje completado
    - ROI dinámico (estimado o real según estado)
    """
    estado = request.GET.get("estado")

    proyectos_qs = Proyecto.objects.all().order_by("-id")

    # Filtrado opcional por estado
    if estado and estado != "todos":
        proyectos_qs = proyectos_qs.filter(estado__iexact=estado)

    proyectos_enriquecidos = []

    for proyecto in proyectos_qs:
        # Capital objetivo → precio de adquisición + gastos previstos (actualizado)
        capital_objetivo = (
            (proyecto.precio_compra_inmueble or 0)
            + (proyecto.itp or 0)
            + (proyecto.notaria or 0)
            + (proyecto.registro or 0)
        )

        # Capital captado (participaciones reales)
        participaciones = Participacion.objects.filter(proyecto=proyecto)
        capital_captado = participaciones.aggregate(
            total=Sum("importe_invertido")
        )["total"] or 0

        porcentaje_completado = (
            (capital_captado / capital_objetivo * 100)
            if capital_objetivo > 0 else 0
        )

        # ROI dinámico
        if proyecto.estado in ["cerrado", "cerrado_positivo"]:
            roi_mostrar = proyecto.roi or 0
            roi_tipo = "real"
        else:
            roi_mostrar = proyecto.roi or 0
            roi_tipo = "estimado"

        proyectos_enriquecidos.append({
            "proyecto": proyecto,
            "capital_objetivo": capital_objetivo,
            "capital_captado": capital_captado,
            "porcentaje_completado": round(porcentaje_completado, 2),
            "roi": roi_mostrar,
            "roi_tipo": roi_tipo,
        })

    return render(
        request,
        "core/lista_proyectos.html",
        {
            "proyectos": proyectos_enriquecidos,
            "estado_actual": estado,
        },
    )

# =========================
# BORRAR PROYECTO DE FORMA SEGURA
# =========================
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect

@require_POST
def borrar_proyecto(request, proyecto_id):
    """
    Borra un proyecto SOLO si está en fase de estudio.
    No se permite borrar proyectos en operación o cerrados.
    """
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    # Regla de negocio Inversure
    if proyecto.estado in ["operacion", "cerrado"]:
        return redirect("core:lista_proyectos")

    proyecto.delete()
    return redirect("core:lista_proyectos")


# === Proyecto Detalle View ===
from django.db.models import Sum

def proyecto_detalle(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    # KPIs consolidados (solo lectura, C2.2)
    participaciones = Participacion.objects.filter(proyecto=proyecto)
    total_invertido = participaciones.aggregate(
        total=Sum("importe_invertido")
    )["total"] or Decimal("0")

    num_inversores = participaciones.count()

    gastos = GastoProyecto.objects.filter(proyecto=proyecto)
    total_gastos = gastos.aggregate(
        total=Sum("importe")
    )["total"] or Decimal("0")

    inversion_total = (
        (proyecto.precio_compra_inmueble or Decimal("0"))
        + (proyecto.itp or Decimal("0"))
        + (proyecto.notaria or Decimal("0"))
        + (proyecto.registro or Decimal("0"))
        + total_gastos
    )

    beneficio = proyecto.beneficio_neto or Decimal("0")
    roi = proyecto.roi or Decimal("0")

    contexto = {
        "proyecto": proyecto,
        "kpis": {
            "inversion_total": inversion_total,
            "beneficio": beneficio,
            "roi": roi,
            "total_invertido": total_invertido,
            "num_inversores": num_inversores,
            "total_gastos": total_gastos,
        },
    }

    return render(
        request,
        "core/proyecto_detalle.html",
        contexto
    )

# === Proyecto Gastos View ===

def proyecto_gastos(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    if request.method == "POST":
        # Detectar tipo de formulario enviado
        tipo_form = request.POST.get("form_tipo")

        # GUARDAR ESTADO DEL PROYECTO (C1.3.2)
        if tipo_form == "estado":
            estado_nuevo = request.POST.get("estado")

            ESTADOS_VALIDOS = [
                "estudio",
                "reservado",
                "comprado",
                "operacion",
                "vendido",
                "descartado",
            ]

            if estado_nuevo in ESTADOS_VALIDOS:
                proyecto.estado = estado_nuevo
                proyecto.save(update_fields=["estado"])

            return redirect("core:proyecto_gastos", proyecto_id=proyecto.id)

        # GUARDAR DATOS DE ADQUISICIÓN (C1.2)
        if tipo_form == "adquisicion":
            proyecto.precio_compra_inmueble = request.POST.get("precio_compra_inmueble") or None
            proyecto.fecha_compra = request.POST.get("fecha_compra") or None
            proyecto.tipo_adquisicion = request.POST.get("tipo_adquisicion") or None
            proyecto.impuesto_tipo = request.POST.get("impuesto_tipo") or None

            # Campos numéricos (Decimal seguro)
            def parse_decimal(val):
                try:
                    return Decimal(str(val).replace(",", "."))
                except Exception:
                    return None

            proyecto.impuesto_porcentaje = parse_decimal(request.POST.get("impuesto_porcentaje"))
            proyecto.itp = parse_decimal(request.POST.get("itp"))
            proyecto.notaria = parse_decimal(request.POST.get("notaria"))
            proyecto.registro = parse_decimal(request.POST.get("registro"))
            proyecto.gestoria = parse_decimal(request.POST.get("gestoria"))

            proyecto.save()
            return redirect("core:proyecto_gastos", proyecto_id=proyecto.id)

        # GUARDAR INGRESOS DEL PROYECTO (C2.3.2 – normalizado)
        if tipo_form == "ingresos":
            tipo_ingreso = request.POST.get("tipo_ingreso")
            fecha_ingreso = request.POST.get("fecha_ingreso")
            concepto = request.POST.get("concepto") or tipo_ingreso
            importe_ingreso_raw = request.POST.get("importe_ingreso")

            try:
                importe_ingreso = Decimal(str(importe_ingreso_raw).replace(",", "."))
            except Exception:
                importe_ingreso = Decimal("0")

            IngresoProyecto.objects.create(
                proyecto=proyecto,
                fecha=fecha_ingreso,
                tipo=tipo_ingreso,
                concepto=concepto,
                importe=importe_ingreso,
                imputable_inversores=True,
            )

            return redirect("core:proyecto_gastos", proyecto_id=proyecto.id)

    # =========================
    # LECTURA DE GASTOS
    # =========================
    gastos = GastoProyecto.objects.filter(proyecto=proyecto).order_by("-fecha")
    total_gastos = gastos.aggregate(total=Sum("importe"))["total"] or 0

    # =========================
    # LECTURA DE INGRESOS (C2.3)
    # =========================
    ingresos = IngresoProyecto.objects.filter(proyecto=proyecto)
    total_ingresos = ingresos.aggregate(
        total=Sum("importe")
    )["total"] or Decimal("0")

    # =========================
    # C2.1 – CONSOLIDACIÓN ECONÓMICA AUTOMÁTICA
    # =========================

    # 1. Gastos clasificados por tipo
    def suma_gastos(tipo):
        return (
            gastos.filter(tipo=tipo)
            .aggregate(total=Sum("importe"))["total"]
            or Decimal("0")
        )

    gastos_adquisicion = suma_gastos("adquisicion")
    gastos_reforma = suma_gastos("reforma")
    gastos_operativos = suma_gastos("operativos")
    gastos_financieros = suma_gastos("financieros")
    gastos_legales = suma_gastos("legales")
    gastos_venta = suma_gastos("venta")
    gastos_otros = suma_gastos("otros")

    # 2. Inversión total del proyecto
    precio_compra = proyecto.precio_compra_inmueble or Decimal("0")

    inversion_total = (
        precio_compra
        + gastos_adquisicion
        + gastos_reforma
        + gastos_operativos
        + gastos_financieros
        + gastos_legales
        + gastos_otros
    )

    # =========================
    # C2.3.3 – RESULTADO REAL USANDO INGRESOS NORMALIZADOS
    # =========================

    # Ingresos imputables a inversores
    ingresos_imputables = ingresos.filter(imputable_inversores=True)
    total_ingresos_imputables = ingresos_imputables.aggregate(
        total=Sum("importe")
    )["total"] or Decimal("0")

    # Beneficio real devengado
    beneficio_neto = total_ingresos_imputables - inversion_total

    # ROI real
    roi_real = (
        (beneficio_neto / inversion_total * Decimal("100"))
        if inversion_total > 0 else Decimal("0")
    )

    # Persistir siempre que haya ingresos
    if ingresos.exists():
        proyecto.beneficio_neto = beneficio_neto
        proyecto.roi = roi_real
        proyecto.save(update_fields=["beneficio_neto", "roi"])

    contexto = {
        "proyecto": proyecto,
        "gastos": gastos,
        "total_gastos": total_gastos,
    }

    return render(
        request,
        "core/proyecto_gastos.html",
        contexto
    )

# === Nueva vista para crear gasto de proyecto ===
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect
from decimal import Decimal, InvalidOperation

@require_POST
def proyecto_gasto_nuevo(request, proyecto_id):
    """
    Crea un nuevo gasto asociado a un proyecto y redirige siempre a la vista de gastos del proyecto.
    """
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)
    concepto = request.POST.get("concepto")
    tipo = request.POST.get("tipo")
    importe_raw = request.POST.get("importe")
    fecha = request.POST.get("fecha")
    observaciones = request.POST.get("observaciones")
    try:
        importe = Decimal(str(importe_raw).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        importe = Decimal("0")
    GastoProyecto.objects.create(
        proyecto=proyecto,
        concepto=concepto,
        tipo=tipo,
        importe=importe,
        fecha=fecha,
        observaciones=observaciones,
    )
    return redirect("core:proyecto_gastos", proyecto_id=proyecto.id)


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


# Editar cliente existente
def cliente_edit(request, cliente_id):
    cliente = Cliente.objects.filter(id=cliente_id).first()
    if not cliente:
        return redirect("clientes")

    if request.method == "POST":
        data = request.POST

        cliente.tipo_persona = data.get("tipo_persona")
        cliente.nombre = data.get("nombre")
        cliente.dni_cif = data.get("dni_cif")
        cliente.email = data.get("email") or None
        cliente.telefono = data.get("telefono") or None
        cliente.iban = data.get("iban") or None
        cliente.direccion_postal = data.get("direccion_postal") or None
        cliente.cuota_abonada = True if data.get("cuota_abonada") == "on" else False
        cliente.presente_en_comunidad = True if data.get("presente_en_comunidad") == "on" else False
        cliente.observaciones = data.get("observaciones") or None

        cliente.save()
        return redirect("clientes")

    return render(
        request,
        "core/clientes_form.html",
        {
            "cliente": cliente,
        },
    )


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
from django.views.decorators.http import require_POST



# === CONVERTIR SIMULACIÓN EN PROYECTO (NUEVA VERSIÓN CORRECTA) ===
from django.views.decorators.http import require_POST


# === GUARDAR SIMULACIÓN DESDE SIMULADOR BÁSICO (NO proyecto) ===
@require_POST
def guardar_simulacion(request):
    """
    Guarda una simulación básica desde el simulador básico
    SIN convertirla en proyecto.
    """
    Simulacion.objects.create(
        nombre=request.POST.get("direccion") or None,
        direccion=request.POST.get("direccion"),
        ref_catastral=request.POST.get("ref_catastral"),
        precio_compra=parse_euro(request.POST.get("precio_compra")),
        precio_venta_estimado=parse_euro(request.POST.get("precio_venta")),
        beneficio=parse_euro(request.POST.get("beneficio")),
        roi=parse_euro(request.POST.get("roi")),
        viable=True,
        convertida=False,
    )

    return redirect("core:lista_estudio")



from django.views.decorators.http import require_POST
from django.shortcuts import redirect, get_object_or_404
from decimal import Decimal


@require_POST
def convertir_simulacion_a_proyecto(request, simulacion_id=None):
    """
    Convierte una simulación en un proyecto de estudio.
    Si simulacion_id está presente, marca la simulación como convertida y usa sus datos.
    Si no, usa los datos del POST.
    """
    if simulacion_id:
        simulacion = get_object_or_404(Simulacion, id=simulacion_id, convertida=False)
        direccion = simulacion.direccion
        ref_catastral = simulacion.ref_catastral
        precio = simulacion.precio_compra or Decimal("0")
        beneficio = simulacion.beneficio or Decimal("0")
        roi = simulacion.roi or Decimal("0")
        simulacion.convertida = True
        simulacion.save(update_fields=["convertida"])
    else:
        direccion = request.POST.get("direccion")
        ref_catastral = request.POST.get("ref_catastral")
        precio = parse_euro(request.POST.get("precio_compra"))
        beneficio = parse_euro(request.POST.get("beneficio"))
        roi = parse_euro(request.POST.get("roi"))
    # Formato correcto de decimales para beneficio y roi
    try:
        beneficio = Decimal(str(beneficio).replace(",", "."))
    except Exception:
        beneficio = Decimal("0")
    try:
        roi = Decimal(str(roi).replace(",", "."))
    except Exception:
        roi = Decimal("0")
    Proyecto.objects.create(
        nombre=f"Estudio - {direccion}",
        direccion=direccion,
        ref_catastral=ref_catastral,
        precio_propiedad=precio,
        beneficio_neto=beneficio,
        roi=roi,
        estado="estudio",
    )
    return redirect("core:lista_estudio")




@csrf_protect
def simulador_basico(request):
    # Valores por defecto (para que NUNCA se borren)
    direccion = ""
    ref_catastral = ""
    precio_compra_raw = ""
    precio_venta_raw = ""
    resultado = None

    if request.method == "POST":
        direccion = request.POST.get("direccion", "")
        ref_catastral = request.POST.get("ref_catastral", "")
        precio_compra_raw = request.POST.get("precio_compra", "")
        precio_venta_raw = request.POST.get("precio_venta", "")

        precio_compra = parse_euro(precio_compra_raw)
        precio_venta = parse_euro(precio_venta_raw)

        beneficio = precio_venta - precio_compra
        roi = (beneficio / precio_compra * Decimal("100")) if precio_compra > 0 else Decimal("0")

        resultado = {
            "inversion_total": float(precio_compra),
            "beneficio": float(beneficio),
            "roi": float(roi),
            "viable": beneficio >= Decimal("30000") or roi >= Decimal("15"),
        }

    return render(
        request,
        "core/simulador_basico.html",
        {
            "direccion": direccion,
            "ref_catastral": ref_catastral,
            "precio_compra": precio_compra_raw,
            "precio_venta": precio_venta_raw,
            "resultado": resultado,
        },
    )



from django.http import HttpResponse
from django.views.decorators.http import require_POST



# Nueva función para borrar análisis previo (NO borra nada en BD)
@require_POST
def borrar_analisis_previo(request):
    """
    Borrado del análisis previo:
    - No guarda nada
    - No borra simulaciones existentes
    - Vuelve al simulador básico limpio
    """
    return redirect("core:simulador_basico")


@require_GET
def catastro_obtener(request):
    ref = request.GET.get("ref")

    if not ref:
        return JsonResponse({"ok": False, "error": "Referencia catastral vacía"}, status=400)

    datos = consultar_catastro_por_rc(ref)

    if not datos or not datos.get("direccion"):
        return JsonResponse({"ok": False, "error": "No se pudo consultar el Catastro"}, status=404)

    return JsonResponse({
        "ok": True,
        "direccion": datos.get("direccion"),
        "lat": datos.get("lat"),
        "lon": datos.get("lon"),
        "ref": ref,
    })

from django.template.loader import render_to_string
from django.http import HttpResponse
from datetime import date
from django.conf import settings
import os
import base64
from pathlib import Path
import io

# ============================
# PALETA CORPORATIVA INVERSURE
# ============================
COLOR_AZUL = "#122135"      # Inversure
COLOR_DORADO = "#d7b04c"    # Objetivos / énfasis
COLOR_VERDE = "#2e7d32"     # Beneficio neto
COLOR_GRIS = "#9e9e9e"      # Referencias / neutro
from decimal import Decimal

def fmt_eur(valor):
    if valor is None:
        return "—"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + "€"

def fmt_pct(valor):
    if valor is None:
        return "—"
    return f"{valor:.2f}".replace(".", ",") + "%"

def generar_pdf_estudio(request, proyecto_id):
    """
    Genera el PDF del informe de rentabilidad
    usando los datos del Estudio de inversión (xhtml2pdf).
    """
    try:
        from weasyprint import HTML
    except Exception as e:
        return HttpResponse(
            f"WeasyPrint no disponible en este entorno: {e}",
            status=503
        )
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import hashlib
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    precio_escritura = proyecto.precio_propiedad or Decimal("0")

    valores = [
        proyecto.val_idealista,
        proyecto.val_fotocasa,
        proyecto.val_registradores,
        proyecto.val_casafari,
        proyecto.val_tasacion,
    ]
    valores = [v for v in valores if v and v > 0]
    media_valoraciones = sum(valores) / len(valores) if valores else Decimal("0")

    notaria = max(precio_escritura * Decimal("0.002"), Decimal("500"))
    registro = max(precio_escritura * Decimal("0.002"), Decimal("500"))
    itp = precio_escritura * Decimal("0.02")

    gastos_adquisicion = notaria + registro + itp
    inversion_total = precio_escritura + gastos_adquisicion

    precio_venta = media_valoraciones
    beneficio = precio_venta - inversion_total
    roi = (beneficio / inversion_total * Decimal("100")) if inversion_total else Decimal("0")

    resultado = {
        "inversion_total": round(inversion_total, 2),
        "beneficio": round(beneficio, 2),
        "roi": round(roi, 2),
        "viable": beneficio >= 30000 or roi >= 15,
    }

    # =========================
    # MÉTRICAS PASO 1 (BASE)
    # =========================
    comision_pct = Decimal("0.30")  # valor por defecto; configurable 0.30 / 0.35 / 0.40
    comision_eur = beneficio * comision_pct if beneficio else Decimal("0")
    beneficio_neto = beneficio - comision_eur
    roi_neto = (beneficio_neto / inversion_total * Decimal("100")) if inversion_total else Decimal("0")

    break_even = inversion_total
    margen_seguridad = ((precio_venta - inversion_total) / precio_venta * Decimal("100")) if precio_venta else Decimal("0")

    # Sensibilidades
    pt_menos_5 = precio_venta * Decimal("0.95")
    pt_menos_10 = precio_venta * Decimal("0.90")

    beneficio_menos_5 = pt_menos_5 - inversion_total
    beneficio_menos_10 = pt_menos_10 - inversion_total

    roi_menos_5 = (beneficio_menos_5 / inversion_total * Decimal("100")) if inversion_total else Decimal("0")
    roi_menos_10 = (beneficio_menos_10 / inversion_total * Decimal("100")) if inversion_total else Decimal("0")

    # =========================
    # FINGERPRINT Y CACHE DE GRÁFICOS
    # =========================
    fingerprint_data = f"{precio_escritura}|{precio_venta}|{beneficio}|{roi}|{comision_pct}"
    hash_estudio = hashlib.md5(fingerprint_data.encode()).hexdigest()

    cache_dir = Path(settings.BASE_DIR) / "tmp" / "pdf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    grafico1_path = cache_dir / f"estudio_{proyecto.id}_{hash_estudio}_g1.png"
    grafico2_path = cache_dir / f"estudio_{proyecto.id}_{hash_estudio}_g2.png"
    grafico3_path = cache_dir / f"estudio_{proyecto.id}_{hash_estudio}_g3.png"

    metricas = {
        "precio_adquisicion": precio_escritura,
        "precio_transmision": precio_venta,
        "inversion_total": inversion_total,
        "beneficio_bruto": beneficio,
        "roi_bruto": roi,
        "comision_pct": comision_pct * Decimal("100"),
        "comision_eur": comision_eur,
        "beneficio_neto": beneficio_neto,
        "roi_neto": roi_neto,
        "break_even": break_even,
        "margen_seguridad": margen_seguridad,
        "sensibilidad": {
            "-5%": {"precio": pt_menos_5, "beneficio": beneficio_menos_5, "roi": roi_menos_5},
            "-10%": {"precio": pt_menos_10, "beneficio": beneficio_menos_10, "roi": roi_menos_10},
        },
    }

    # =================================================
    # MÉTRICAS FORMATEADAS PARA EL RESUMEN EJECUTIVO
    # =================================================
    metricas_fmt = {
        "inversion_total": fmt_eur(metricas["inversion_total"]),
        "precio_transmision": fmt_eur(metricas["precio_transmision"]),
        "beneficio_bruto": fmt_eur(metricas["beneficio_bruto"]),
        "beneficio_neto": fmt_eur(metricas["beneficio_neto"]),
        "precio_objetivo_15": fmt_eur(metricas.get("precio_objetivo_15")),
        "roi_bruto": fmt_pct(metricas["roi_bruto"]),
        "roi_neto": fmt_pct(metricas["roi_neto"]),
    }

    # =================================================
    # GRÁFICO 1: DESGLOSE DEL BENEFICIO (BRUTO / COMISIÓN / NETO) (PROTAGONISTA)
    # =================================================
    if grafico1_path.exists():
        grafico_beneficio_base64 = base64.b64encode(grafico1_path.read_bytes()).decode("utf-8")
    else:
        fig1, ax1 = plt.subplots(figsize=(7, 4))

        valores_beneficio = [
            float(metricas["beneficio_bruto"]),
            float(metricas["comision_eur"]),
            float(metricas["beneficio_neto"]),
        ]

        etiquetas_beneficio = [
            "Beneficio bruto",
            "Comisión Inversure",
            "Beneficio neto inversor",
        ]

        colores = [COLOR_AZUL, COLOR_DORADO, COLOR_GRIS]

        barras1 = ax1.bar(
            etiquetas_beneficio,
            valores_beneficio,
            color=colores,
            width=0.55
        )

        ax1.set_title("Resultado económico de la operación", fontsize=13, fontweight="bold")
        ax1.set_ylabel("Euros (€)")
        ax1.tick_params(axis="x", labelsize=10)
        ax1.tick_params(axis="y", labelsize=9)

        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)

        for barra in barras1:
            altura = barra.get_height()
            ax1.text(
                barra.get_x() + barra.get_width() / 2,
                altura * 1.02,
                fmt_eur(Decimal(str(float(altura)))),
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold"
            )

        try:
            plt.tight_layout()
        except Exception:
            pass
        plt.savefig(grafico1_path, format="png", dpi=160)
        plt.close(fig1)
        grafico_beneficio_base64 = base64.b64encode(grafico1_path.read_bytes()).decode("utf-8")

    # =================================================
    # GRÁFICO 2: ADQUISICIÓN VS TRANSMISIÓN (secundario pero claro)
    # =================================================
    if grafico2_path.exists():
        grafico_precios_base64 = base64.b64encode(grafico2_path.read_bytes()).decode("utf-8")
    else:
        fig2, ax2 = plt.subplots(figsize=(6, 3.5))

        valores_precios = [
            float(metricas["inversion_total"]),
            float(metricas["precio_transmision"]),
        ]

        etiquetas_precios = [
            "Inversión total",
            "Precio de venta",
        ]

        barras2 = ax2.bar(
            etiquetas_precios,
            valores_precios,
            color=[COLOR_AZUL, COLOR_DORADO],
            width=0.5
        )

        ax2.set_title("Comparativa adquisición / venta", fontsize=12, fontweight="bold")
        ax2.set_ylabel("Euros (€)")
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)

        for barra in barras2:
            altura = barra.get_height()
            ax2.text(
                barra.get_x() + barra.get_width() / 2,
                altura * 1.01,
                fmt_eur(Decimal(str(float(altura)))),
                ha="center",
                va="bottom",
                fontsize=9
            )

        try:
            plt.tight_layout()
        except Exception:
            pass
        plt.savefig(grafico2_path, format="png", dpi=150)
        plt.close(fig2)
        grafico_precios_base64 = base64.b64encode(grafico2_path.read_bytes()).decode("utf-8")

    # ============================
    # OBJETIVOS DE RENTABILIDAD (INVERSOR)
    # ============================

    # Objetivo 1: 15 % de rentabilidad sobre la inversión total
    precio_objetivo_15 = inversion_total * Decimal("1.15")

    # Objetivo 2: beneficio absoluto mínimo de 30.000 €
    precio_objetivo_30000 = inversion_total + Decimal("30000")

    # ¿Resultado neto negativo tras comisión?
    resultado_negativo = beneficio_neto <= 0

    # Precio mínimo de venta necesario para alcanzar el objetivo esperado
    if resultado_negativo:
        precio_equilibrio_beneficio = max(precio_objetivo_15, precio_objetivo_30000)
    else:
        precio_equilibrio_beneficio = None

    # Añadir métricas al diccionario principal
    metricas["precio_objetivo_15"] = precio_objetivo_15
    metricas["precio_objetivo_30000"] = precio_objetivo_30000
    metricas["resultado_negativo"] = resultado_negativo
    metricas["precio_equilibrio_beneficio"] = precio_equilibrio_beneficio

    # =================================================
    # GRÁFICO 3: SENSIBILIDAD DEL PRECIO DE VENTA (DECISIÓN)
    # =================================================
    if grafico3_path.exists():
        grafico_sensibilidad_base64 = base64.b64encode(grafico3_path.read_bytes()).decode("utf-8")
    else:
        fig3, ax3 = plt.subplots(figsize=(7, 3.8))

        precios_sens = [
            float(metricas["precio_adquisicion"]),
            float(metricas["precio_objetivo_15"]),
            float(metricas["precio_objetivo_30000"]),
            float(metricas["precio_transmision"]),
        ]

        labels_sens = [
            "Compra",
            "Objetivo 15 %",
            "Objetivo +30.000 €",
            "Venta estimada",
        ]

        x_pos = list(range(len(labels_sens)))

        ax3.plot(
            x_pos,
            precios_sens,
            marker="o",
            linewidth=2.5,
            color=COLOR_AZUL
        )
        ax3.set_xticks(x_pos)
        ax3.set_xticklabels(labels_sens)

        for i, y in enumerate(precios_sens):
            ax3.text(
                i,
                y * 1.01,
                fmt_eur(Decimal(str(float(y)))),
                ha="center",
                fontsize=9,
                fontweight="bold"
            )

        ax3.set_title("Sensibilidad del precio de venta", fontsize=13, fontweight="bold")
        ax3.set_ylabel("Precio (€)")
        ax3.grid(True, linestyle="--", alpha=0.3)

        try:
            plt.tight_layout()
        except Exception:
            pass
        plt.savefig(grafico3_path, format="png", dpi=160)
        plt.close(fig3)
        grafico_sensibilidad_base64 = base64.b64encode(grafico3_path.read_bytes()).decode("utf-8")

    # ============================
    # LOGO CORPORATIVO (WeasyPrint)
    # ============================
    logo_path = (
        Path(settings.BASE_DIR)
        / "core"
        / "static"
        / "core"
        / "logo_inversure.jpg"
    )
    logo_url = logo_path.resolve().as_uri()

    mapa_base64 = None
    if proyecto.lat and proyecto.lon:
        mapa_url = (
            "https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={proyecto.lat},{proyecto.lon}"
            "&zoom=16"
            "&size=600x300"
            f"&markers={proyecto.lat},{proyecto.lon},red-pushpin"
        )
        try:
            resp = requests.get(mapa_url, timeout=10)
            if resp.status_code == 200:
                mapa_base64 = base64.b64encode(resp.content).decode("utf-8")
        except Exception:
            mapa_base64 = None

    html = render_to_string(
        "core/pdf_estudio_rentabilidad.html",
        {
            "proyecto": proyecto,
            "resultado": resultado,
            "fecha": date.today().strftime("%d/%m/%Y"),
            "logo_url": logo_url,
            "mapa_base64": mapa_base64,
            "metricas": metricas,
            "metricas_fmt": metricas_fmt,
            "grafico_beneficio_base64": grafico_beneficio_base64,
            "grafico_precios_base64": grafico_precios_base64,
            "grafico_sensibilidad_base64": grafico_sensibilidad_base64,
        }
    )

    pdf = HTML(
        string=html,
        base_url=settings.BASE_DIR
    ).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="Informe_Estudio_{proyecto.id}.pdf"'
    )

    return response


# ============================
# APROBAR PROYECTO (NUEVA VISTA)
# ============================
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.conf import settings
import os

@require_POST
def aprobar_proyecto(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    if proyecto.aprobado:
        return redirect("core:lista_estudios")

    # Generar PDF usando la función existente
    response = generar_pdf_estudio(request, proyecto_id)

    nombre_pdf = f"proyecto_{proyecto.id}_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
    ruta_relativa = os.path.join("proyectos_aprobados", nombre_pdf)
    ruta_absoluta = os.path.join(settings.MEDIA_ROOT, ruta_relativa)

    os.makedirs(os.path.dirname(ruta_absoluta), exist_ok=True)

    with open(ruta_absoluta, "wb") as f:
        f.write(response.content)

    proyecto.pdf_aprobado = ruta_relativa
    proyecto.aprobado = True
    proyecto.fecha_aprobacion = timezone.now()
    proyecto.save(update_fields=["pdf_aprobado", "aprobado", "fecha_aprobacion"])

    return redirect("core:lista_estudios")


# === NUEVAS VISTAS DE GASTOS Y DETALLE DE PROYECTO ===

from django.db.models import Sum
from django.views.decorators.http import require_GET

@require_GET
def proyecto_detalle(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    gastos = GastoProyecto.objects.filter(
        proyecto=proyecto
    ).order_by("-fecha")

    total_gastos = gastos.aggregate(
        total=Sum("importe")
    )["total"] or 0

    return render(
        request,
        "core/proyecto_detalle.html",
        {
            "proyecto": proyecto,
            "gastos": gastos,
            "total_gastos": total_gastos,
        },
    )


@require_GET
def proyecto_gastos(request, proyecto_id):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    gastos = GastoProyecto.objects.filter(
        proyecto=proyecto
    ).order_by("-fecha")

    total_gastos = gastos.aggregate(
        total=Sum("importe")
    )["total"] or 0

    return render(
        request,
        "core/proyecto_gastos.html",
        {
            "proyecto": proyecto,
            "gastos": gastos,
            "total_gastos": total_gastos,
        },
    )
from django.shortcuts import get_object_or_404

def estudio_detalle(request, proyecto_id):
    estudio = Proyecto.objects.filter(
        id=proyecto_id,
        estado__iexact="estudio"
    ).first()

    if not estudio:
        return redirect("core:lista_estudio")

    return render(
        request,
        "core/simulador.html",
        {
            "estudio": estudio,
        },
    )