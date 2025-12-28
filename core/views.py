
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
from .models import Proyecto, Cliente, Participacion, Simulacion

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

    proyecto = get_object_or_404(Proyecto, id=proyecto_id) if proyecto_id else None
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
                proyecto.estado = "operacion"
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
    estado = request.GET.get("estado")

    # Proyectos (filtrados por estado si se indica)
    proyectos = Proyecto.objects.all().order_by("-id")
    if estado:
        proyectos = proyectos.filter(estado__iexact=estado)

    # Simulaciones que NO están convertidas en proyecto
    simulaciones_pendientes = Simulacion.objects.filter(
        convertida=False
    ).order_by("-id")

    return render(
        request,
        "core/lista_proyectos.html",
        {
            "proyectos": proyectos,
            "simulaciones_pendientes": simulaciones_pendientes,
            "estado_actual": estado,
        },
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

    return redirect("core:lista_proyectos")


@require_POST
def convertir_simulacion_a_proyecto(request, simulacion_id):
    """
    Convierte una simulación básica en un proyecto real.
    Mapeo correcto de campos:
    - Inmueble (simulación.nombre / direccion) -> Proyecto.direccion
    - Compra (simulación.precio_compra) -> Proyecto.precio_propiedad (precio escritura)
    - Venta (simulación.precio_venta_estimado) -> Proyecto.val_tasacion
    """
    simulacion = Simulacion.objects.filter(
        id=simulacion_id,
        convertida=False
    ).first()

    if not simulacion:
        # No existe o ya convertida: volvemos a proyectos
        return redirect("core:lista_proyectos")

    # 1) Determinar dirección del inmueble
    direccion = (
        simulacion.direccion
        or simulacion.nombre
        or f"Inmueble simulación #{simulacion.id}"
    )

    # 2) Crear proyecto con los campos correctamente mapeados (bloque exacto con Decimal)
    proyecto = Proyecto.objects.create(
        nombre=f"Proyecto - {direccion}",
        direccion=direccion,
        # Precio de escritura
        precio_propiedad=simulacion.precio_compra,
        # Valor de adquisición (Decimal seguro)
        precio_compra_inmueble=simulacion.precio_compra * Decimal("1.10"),
        # Tasación / valor venta
        val_tasacion=simulacion.precio_venta_estimado,
        roi=simulacion.roi,
        beneficio_neto=simulacion.beneficio,
        estado="estudio",
        simulacion_origen=simulacion,
    )

    # 3) Marcar simulación como convertida (deja de aparecer en pendientes)
    simulacion.convertida = True
    simulacion.save(update_fields=["convertida"])

    # 4) Redirigir al formulario de proyecto (simulador completo)
    return redirect("core:simulador", proyecto_id=proyecto.id)




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

        def parse_euro(valor):
            try:
                return float(
                    str(valor)
                    .replace(".", "")
                    .replace(",", ".")
                    .replace("€", "")
                    .strip()
                )
            except Exception:
                return 0.0

        precio_compra = parse_euro(precio_compra_raw)
        precio_venta = parse_euro(precio_venta_raw)

        beneficio = precio_venta - precio_compra
        roi = (beneficio / precio_compra * 100) if precio_compra > 0 else 0

        resultado = {
            "inversion_total": round(precio_compra, 2),
            "beneficio": round(beneficio, 2),
            "roi": round(roi, 2),
            # REGLA EXACTA QUE PEDISTE
            "viable": beneficio >= 30000 or roi >= 15,
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
                # NO se pasa simulacion aquí
            },
        )

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

@require_POST
def borrar_simulacion(request, simulacion_id):
    """
    Borrado estándar:
    - Elimina la simulación
    - Redirige a la lista de proyectos
    """
    Simulacion.objects.filter(id=simulacion_id).delete()
    return redirect("core:lista_proyectos")


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
from weasyprint import HTML
from datetime import date
from django.conf import settings
import os
import base64
from pathlib import Path
import io

# --- matplotlib: inicialización única y correcta ---

# ============================
# PALETA CORPORATIVA INVERSURE
# ============================
COLOR_AZUL = "#122135"      # Inversure
COLOR_DORADO = "#d7b04c"    # Objetivos / énfasis
COLOR_VERDE = "#2e7d32"     # Beneficio neto
COLOR_GRIS = "#9e9e9e"      # Referencias / neutro
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
    fig1, ax1 = plt.subplots(figsize=(7, 4))

    valores_beneficio = [
        metricas["beneficio_bruto"],
        metricas["comision_eur"],
        metricas["beneficio_neto"],
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
            fmt_eur(Decimal(str(altura))),
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold"
        )

    buffer1 = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buffer1, format="png", dpi=160)
    plt.close(fig1)

    grafico_beneficio_base64 = base64.b64encode(buffer1.getvalue()).decode("utf-8")

    # =================================================
    # GRÁFICO 2: ADQUISICIÓN VS TRANSMISIÓN (secundario pero claro)
    # =================================================
    fig2, ax2 = plt.subplots(figsize=(6, 3.5))

    valores_precios = [
        metricas["inversion_total"],
        metricas["precio_transmision"],
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
            fmt_eur(Decimal(str(altura))),
            ha="center",
            va="bottom",
            fontsize=9
        )

    buffer2 = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buffer2, format="png", dpi=150)
    plt.close(fig2)

    grafico_precios_base64 = base64.b64encode(buffer2.getvalue()).decode("utf-8")

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
    fig3, ax3 = plt.subplots(figsize=(7, 3.8))

    precios_sens = [
        metricas["precio_adquisicion"],
        metricas["precio_objetivo_15"],
        metricas["precio_objetivo_30000"],
        metricas["precio_transmision"],
    ]

    labels_sens = [
        "Compra",
        "Objetivo 15 %",
        "Objetivo +30.000 €",
        "Venta estimada",
    ]

    ax3.plot(
        labels_sens,
        precios_sens,
        marker="o",
        linewidth=2.5,
        color=COLOR_AZUL
    )

    for x, y in zip(labels_sens, precios_sens):
        ax3.text(
            x,
            float(y) * 1.01,
            fmt_eur(y),
            ha="center",
            fontsize=9,
            fontweight="bold"
        )

    ax3.set_title("Sensibilidad del precio de venta", fontsize=13, fontweight="bold")
    ax3.set_ylabel("Precio (€)")
    ax3.grid(True, linestyle="--", alpha=0.3)

    buffer3 = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buffer3, format="png", dpi=160)
    plt.close(fig3)

    grafico_sensibilidad_base64 = base64.b64encode(buffer3.getvalue()).decode("utf-8")

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