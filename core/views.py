from __future__ import annotations

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
import json


from .models import Estudio, Proyecto

# --- SafeAccessDict helper and _safe_template_obj ---
class SafeAccessDict(dict):
    """Dict seguro para plantillas Django: nunca lanza KeyError y permite acceso por atributo."""

    def __getitem__(self, key):
        return dict.get(self, key, "")

    def __getattr__(self, item):
        # permite `proyecto.campo` en plantillas
        return dict.get(self, item, "")

    def get(self, key, default=""):
        return dict.get(self, key, default)


def _safe_template_obj(obj):
    """Convierte dicts anidados en SafeAccessDict para evitar VariableDoesNotExist en plantillas."""
    if isinstance(obj, SafeAccessDict):
        return obj
    if isinstance(obj, dict):
        return SafeAccessDict({k: _safe_template_obj(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return [_safe_template_obj(v) for v in obj]
    return obj


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        # strings like "1.234,56" or "1,234.56" → normalize
        if isinstance(v, str):
            s = v.strip()
            # remove currency/percent symbols
            s = s.replace("€", "").replace("%", "").strip()
            # spanish thousands/decimal
            if "." in s and "," in s:
                # assume dot thousands, comma decimal
                s = s.replace(".", "").replace(",", ".")
            else:
                # otherwise, treat comma as decimal
                s = s.replace(",", ".")
            v = s
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt_es_number(x: float, decimals: int = 2) -> str:
    # 12,345.67 -> 12.345,67
    s = f"{x:,.{decimals}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _fmt_eur(x: float) -> str:
    return f"{_fmt_es_number(x, 2)} €"


def _fmt_pct(x: float) -> str:
    return f"{_fmt_es_number(x, 2)} %"


def _metricas_desde_estudio(estudio: Estudio) -> dict:
    d = estudio.datos or {}

    valor_adquisicion = _safe_float(d.get("valor_adquisicion"), 0.0)

    # intentar localizar precio de venta/valor de transmisión
    precio_transmision = _safe_float(
        d.get("precio_transmision")
        or d.get("precio_venta_estimado")
        or d.get("valor_transmision")
        or d.get("valor_transmision_estimado"),
        0.0,
    )

    beneficio = _safe_float(d.get("beneficio"), precio_transmision - valor_adquisicion)

    roi = _safe_float(d.get("roi"), (beneficio / valor_adquisicion * 100.0) if valor_adquisicion else 0.0)

    media_valoraciones = _safe_float(d.get("media_valoraciones"), 0.0)

    metricas = {
        "valor_adquisicion": valor_adquisicion,
        "valor_adquisicion_total": valor_adquisicion,
        # aliases usados por plantillas antiguas
        "precio_adquisicion": valor_adquisicion,
        "precio_compra": valor_adquisicion,
        "precio_transmision": precio_transmision,
        "valor_transmision": precio_transmision,
        "beneficio": beneficio,
        "roi": roi,
        "media_valoraciones": media_valoraciones,
        # alias típicos por si la plantilla usa otros nombres
        "inversion_total": valor_adquisicion,
        "beneficio_neto": beneficio,
        "roi_neto": roi,
    }

    metricas_fmt = {
        "valor_adquisicion": _fmt_eur(valor_adquisicion),
        "valor_adquisicion_total": _fmt_eur(valor_adquisicion),
        # aliases
        "precio_adquisicion": _fmt_eur(valor_adquisicion),
        "precio_compra": _fmt_eur(valor_adquisicion),
        "precio_transmision": _fmt_eur(precio_transmision),
        "valor_transmision": _fmt_eur(precio_transmision),
        "beneficio": _fmt_eur(beneficio),
        "roi": _fmt_pct(roi),
        "media_valoraciones": _fmt_eur(media_valoraciones),
        # alias
        "inversion_total": _fmt_eur(valor_adquisicion),
        "beneficio_neto": _fmt_eur(beneficio),
        "roi_neto": _fmt_pct(roi),
    }

    # decisión simple (placeholder) para que la plantilla no quede vacía
    resultado = {
        "viable": True if (beneficio >= 0 and roi >= 0) else False,
        "mensaje": "Operación viable" if (beneficio >= 0 and roi >= 0) else "Operación no viable",
    }

    # --- Enriquecimiento automático con métricas de Comité/Inversor guardadas en `datos` ---
    # El simulador guarda muchos KPIs adicionales (breakeven, colchón, riesgo, etc.) dentro de `estudio.datos`.
    # Para que el PDF los pueda mostrar sin depender de campos del modelo, los añadimos aquí de forma defensiva.
    texto = {}

    def _is_percent_key(key: str) -> bool:
        k = (key or "").lower()
        return any(t in k for t in ["roi", "%", "pct", "porc", "porcentaje", "tasa"]) and not any(t in k for t in ["euros", "eur", "euro"])

    def _is_ratio_key(key: str) -> bool:
        k = (key or "").lower()
        return "ratio" in k or "multiplic" in k

    def _is_currency_key(key: str) -> bool:
        k = (key or "").lower()
        # Heurística: casi todo en el simulador es dinero salvo ratios/%.
        # Aun así, si el nombre sugiere % o ratio, no lo tratamos como €.
        if _is_percent_key(k) or _is_ratio_key(k):
            return False
        return True

    for k, v in d.items():
        # Guardar textos (para estado/situación, decisión, comentarios, etc.)
        if isinstance(v, str):
            sv = v.strip()
            if sv and k not in texto:
                texto[k] = sv

        # Añadir numéricos que no estén ya normalizados
        if k in metricas:
            continue
        fv = _safe_float(v, None)
        if fv is None:
            continue
        metricas[k] = fv

        # Formateo por heurística
        if _is_percent_key(k):
            metricas_fmt[k] = _fmt_pct(fv)
        elif _is_ratio_key(k):
            metricas_fmt[k] = _fmt_es_number(fv, 2)
        elif _is_currency_key(k):
            metricas_fmt[k] = _fmt_eur(fv)
        else:
            metricas_fmt[k] = _fmt_es_number(fv, 2)

    # Algunos alias habituales (por si la plantilla usa nombres alternativos)
    if "margen" in metricas and "margen_seguridad" not in metricas:
        metricas["margen_seguridad"] = metricas.get("margen")
        metricas_fmt["margen_seguridad"] = metricas_fmt.get("margen")
    if "colchon" in metricas and "colchon_seguridad" not in metricas:
        metricas["colchon_seguridad"] = metricas.get("colchon")
        metricas_fmt["colchon_seguridad"] = metricas_fmt.get("colchon")

    return {
        "metricas": metricas,
        "metricas_fmt": metricas_fmt,
        "resultado": resultado,
        "texto": texto,
    }


# --- Datos de identificación inmueble desde estudio ---
def _datos_inmueble_desde_estudio(estudio: Estudio) -> dict:
    """Extrae y normaliza datos de identificación del inmueble desde `estudio` y su JSON `datos`."""
    d = estudio.datos or {}

    def _s(v) -> str:
        if v is None:
            return ""
        return str(v).strip()

    tipologia = _s(d.get("tipologia") or d.get("tipo_inmueble") or d.get("tipo"))
    estado = _s(d.get("estado") or d.get("estado_conservacion") or d.get("conservacion"))
    situacion = _s(d.get("situacion") or d.get("ocupacion") or d.get("situacion_ocupacional"))

    superficie_m2 = _safe_float(
        d.get("superficie")
        or d.get("superficie_m2")
        or d.get("m2")
        or d.get("metros_cuadrados"),
        0.0,
    )

    # Valor de referencia: preferimos el campo del modelo si existe
    valor_referencia_num = _safe_float(getattr(estudio, "valor_referencia", None), None)
    if valor_referencia_num is None:
        valor_referencia_num = _safe_float(d.get("valor_referencia"), 0.0)

    # Formatos
    superficie_m2_fmt = f"{_fmt_es_number(superficie_m2, 0)} m²" if superficie_m2 else ""
    valor_referencia_fmt = _fmt_eur(valor_referencia_num) if valor_referencia_num else ""

    # Fecha de creación (para el PDF)
    creado = getattr(estudio, "creado", None)
    creado_fmt = creado.strftime("%d/%m/%Y") if creado else ""

    return {
        "tipologia": tipologia,
        "estado": estado,
        "situacion": situacion,
        "superficie_m2": superficie_m2,
        "superficie_m2_fmt": superficie_m2_fmt,
        "valor_referencia": valor_referencia_num,
        "valor_referencia_fmt": valor_referencia_fmt,
        "fecha": creado,
        "fecha_fmt": creado_fmt,
    }


def home(request):
    return render(request, "core/home.html")


def simulador(request):
    estudio = None
    estudio_id = request.session.get("estudio_id")

    if estudio_id:
        try:
            estudio_obj = Estudio.objects.get(id=estudio_id)
        except Estudio.DoesNotExist:
            estudio_obj = None
    else:
        estudio_obj = None

    # No creamos el Estudio en GET para evitar duplicados/estudios vacíos.
    # El Estudio se crea/actualiza al pulsar "Guardar".
    if estudio_obj is None:
        estudio = {
            "id": None,
            "nombre": "",
            "direccion": "",
            "ref_catastral": "",
            "valor_referencia": "",
            "datos": {},
        }
    else:
        estudio = {
            "id": estudio_obj.id,
            "nombre": estudio_obj.nombre,
            "direccion": estudio_obj.direccion,
            "ref_catastral": estudio_obj.ref_catastral,
            "valor_referencia": estudio_obj.valor_referencia,
            "datos": estudio_obj.datos or {},
        }

    return render(
        request,
        "core/simulador.html",
        {
            "estudio": estudio
        }
    )


def lista_estudio(request):
    estudios_qs = Estudio.objects.all().order_by("-datos__roi", "-id")
    estudios = []

    for e in estudios_qs:
        d = e.datos or {}
        estudios.append({
            "id": e.id,
            "nombre": e.nombre,
            "direccion": e.direccion,
            "ref_catastral": e.ref_catastral,
            "valor_referencia": e.valor_referencia,
            "valor_adquisicion": d.get("valor_adquisicion", 0),
            "beneficio": d.get("beneficio", 0),
            "roi": d.get("roi", 0),
           "fecha": e.creado,
        })

    return render(
        request,
        "core/lista_estudio.html",
        {"estudios": estudios},
    )


def lista_proyectos(request):
    proyectos = Proyecto.objects.all().order_by("-id")
    return render(
        request,
        "core/lista_proyectos.html",
        {"proyectos": proyectos},
    )


@csrf_exempt
def guardar_estudio(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body)

        estudio_id = data.get("id")

        # Aceptar tanto las keys antiguas como las del formulario actual (simulador.html)
        nombre = (
            data.get("nombre")
            or data.get("nombre_proyecto")
            or data.get("proyecto_nombre")
            or ""
        ).strip()

        direccion = (
            data.get("direccion")
            or data.get("direccion_completa")
            or data.get("proyecto_direccion")
            or ""
        ).strip()

        ref_catastral = (
            data.get("ref_catastral")
            or data.get("referencia_catastral")
            or data.get("ref_catastral_inmueble")
            or ""
        ).strip()

        # `datos` siempre debe ser dict
        datos = data.get("datos", {}) or {}
        if not isinstance(datos, dict):
            datos = {}

        # `valor_referencia` puede venir a nivel raíz o dentro de `datos`
        valor_referencia_raw = data.get("valor_referencia")
        if valor_referencia_raw is None:
            valor_referencia_raw = datos.get("valor_referencia")

        valor_referencia = None
        if valor_referencia_raw is not None:
            if isinstance(valor_referencia_raw, str) and not valor_referencia_raw.strip():
                valor_referencia = None
            else:
                valor_referencia = _safe_float(valor_referencia_raw, 0.0)

        # Normalizar KPIs clave para cards (defensivo)
        valor_adq = _safe_float(datos.get("valor_adquisicion"), 0.0)
        beneficio = _safe_float(datos.get("beneficio"), 0.0)
        roi = _safe_float(datos.get("roi"), 0.0)

        datos["valor_adquisicion"] = valor_adq
        datos["beneficio"] = beneficio
        datos["roi"] = roi

        # Persistir campos clave del simulador (vista técnica / valoraciones / transmisión)
        # para que el PDF pueda leerlos siempre desde `estudio.datos`.
        def _copy_if_present(src_key: str, dst_key: str | None = None):
            k_dst = dst_key or src_key
            if src_key in data and data.get(src_key) not in (None, ""):
                datos[k_dst] = data.get(src_key)

        # Campos de identificación (por si llegan arriba además de en `datos`)
        for k in ["tipologia", "superficie_m2", "estado", "situacion", "valor_referencia"]:
            _copy_if_present(k)

        # Valores calculados/estimados
        for k in ["valor_transmision", "precio_transmision", "precio_venta_estimado", "media_valoraciones"]:
            _copy_if_present(k)

        # Valoraciones de mercado individuales
        for k in [
            "valoracion_tasacion",
            "valoracion_idealista",
            "valoracion_fotocasa",
            "valoracion_registradores",
            "valoracion_casafari",
        ]:
            _copy_if_present(k)

        # Normalizaciones numéricas útiles para PDF/ordenación (defensivo)
        for num_k in [
            "valor_referencia",
            "superficie_m2",
            "media_valoraciones",
            "valor_transmision",
            "precio_transmision",
            "precio_venta_estimado",
        ]:
            if num_k in datos:
                datos[num_k] = _safe_float(datos.get(num_k), 0.0)

        # Evitar crear estudios vacíos
        if (not estudio_id) and (not nombre) and (not direccion) and (not ref_catastral) and (not datos):
            return JsonResponse({"ok": False, "error": "Estudio vacío"}, status=400)

        campos = {
            "nombre": nombre,
            "direccion": direccion,
            "ref_catastral": ref_catastral,
            "valor_referencia": valor_referencia,
            "datos": datos,
        }

        if estudio_id:
            # Actualiza el estudio actual por ID
            estudio, _ = Estudio.objects.update_or_create(
                id=estudio_id,
                defaults=campos,
            )
        else:
            # De-duplicación: si ya existe un estudio con mismo nombre+dirección+ref_catastral, lo reutilizamos.
            # (Regla: coincidencia por campos no vacíos; al menos uno debe existir)
            qs = Estudio.objects.all()
            if nombre:
                qs = qs.filter(nombre=nombre)
            if direccion:
                qs = qs.filter(direccion=direccion)
            if ref_catastral:
                qs = qs.filter(ref_catastral=ref_catastral)

            existente = qs.first() if (nombre or direccion or ref_catastral) else None
            if existente:
                for k, v in campos.items():
                    setattr(existente, k, v)
                existente.save(update_fields=list(campos.keys()))
                estudio = existente
            else:
                estudio = Estudio.objects.create(**campos)

        # Mantener el estudio actual en sesión
        request.session["estudio_id"] = estudio.id

        return JsonResponse(
            {
                "ok": True,
                "id": estudio.id,
            }
        )

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@csrf_exempt
def convertir_a_proyecto(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body)
        estudio_id = data.get("id")

        estudio = Estudio.objects.get(id=estudio_id)

        proyecto = Proyecto.objects.create(
            nombre=estudio.nombre,
            direccion=estudio.direccion,
            ref_catastral=estudio.ref_catastral,
            media_valoraciones=estudio.datos.get("media_valoraciones"),
            precio_venta_estimado=estudio.datos.get("precio_venta_estimado"),
        )

        estudio.delete()

        if request.session.get("estudio_id") == estudio_id:
            try:
                del request.session["estudio_id"]
            except KeyError:
                pass

        return JsonResponse({
            "ok": True,
            "redirect": reverse("core:lista_proyectos"),
            "proyecto_id": proyecto.id
        })

    except Estudio.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Estudio no encontrado"}, status=404)

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def pdf_estudio_preview(request, estudio_id):
    estudio = get_object_or_404(Estudio, id=estudio_id)

    # --- SNAPSHOT DEL ESTUDIO (creado al generar el PDF) ---
    from core.services.estudio_snapshot import build_estudio_snapshot
    from core.models import EstudioSnapshot

    snapshot_data = build_estudio_snapshot(estudio)

    snapshot = EstudioSnapshot.objects.create(
        estudio=estudio,
        datos=snapshot_data,
    )

    # Métricas calculadas a partir del JSON `datos`
    ctx = _metricas_desde_estudio(estudio)
    # Exponemos el JSON completo del simulador para que el PDF pueda leer cualquier campo de Comité/Inversor
    datos_safe = _safe_template_obj(estudio.datos or {})

    # La plantilla histórica del “pdf” espera un objeto/dict llamado `proyecto`
    # con campos tipo `inversion_total`, `beneficio_neto`, etc.
    # Creamos un dict compatible (Django permite acceso con punto sobre dict).
    metricas = ctx.get("metricas", {}) or {}
    metricas_fmt = ctx.get("metricas_fmt", {}) or {}
    inmueble = _datos_inmueble_desde_estudio(estudio)

    proyecto = {
        "id": estudio.id,
        "nombre": estudio.nombre,
        "direccion": estudio.direccion,
        "ref_catastral": estudio.ref_catastral,
        "valor_referencia": inmueble.get("valor_referencia"),
        "valor_referencia_fmt": inmueble.get("valor_referencia_fmt"),
        "tipologia": inmueble.get("tipologia"),
        "superficie_m2": inmueble.get("superficie_m2"),
        "superficie_m2_fmt": inmueble.get("superficie_m2_fmt"),
        "estado": inmueble.get("estado"),
        "situacion": inmueble.get("situacion"),
        "fecha": inmueble.get("fecha"),
        "fecha_fmt": inmueble.get("fecha_fmt"),
        "valor_adquisicion": metricas.get("valor_adquisicion", 0.0),
        "valor_adquisicion_total": metricas.get("valor_adquisicion_total", metricas.get("valor_adquisicion", 0.0)),
        "precio_adquisicion": metricas.get("precio_adquisicion", metricas.get("valor_adquisicion", 0.0)),
        "precio_compra": metricas.get("precio_compra", metricas.get("valor_adquisicion", 0.0)),
        "precio_transmision": metricas.get("precio_transmision", 0.0),
        "valor_transmision": metricas.get("valor_transmision", metricas.get("precio_transmision", 0.0)),
        "beneficio": metricas.get("beneficio", 0.0),
        "roi": metricas.get("roi", 0.0),
        "media_valoraciones": metricas.get("media_valoraciones", 0.0),
        # aliases usados en plantillas antiguas
        "inversion_total": metricas.get("inversion_total", metricas.get("valor_adquisicion", 0.0)),
        "beneficio_neto": metricas.get("beneficio_neto", metricas.get("beneficio", 0.0)),
        "roi_neto": metricas.get("roi_neto", metricas.get("roi", 0.0)),
        "valor_adquisicion_fmt": metricas_fmt.get("valor_adquisicion"),
        "valor_adquisicion_total_fmt": metricas_fmt.get("valor_adquisicion_total", metricas_fmt.get("valor_adquisicion")),
        "precio_adquisicion_fmt": metricas_fmt.get("precio_adquisicion", metricas_fmt.get("valor_adquisicion")),
        "precio_compra_fmt": metricas_fmt.get("precio_compra", metricas_fmt.get("valor_adquisicion")),
        "precio_transmision_fmt": metricas_fmt.get("precio_transmision"),
        "valor_transmision_fmt": metricas_fmt.get("valor_transmision", metricas_fmt.get("precio_transmision")),
        "beneficio_fmt": metricas_fmt.get("beneficio"),
        "roi_fmt": metricas_fmt.get("roi"),
        "media_valoraciones_fmt": metricas_fmt.get("media_valoraciones"),
        "inversion_total_fmt": metricas_fmt.get("inversion_total"),
        "beneficio_neto_fmt": metricas_fmt.get("beneficio_neto"),
        "roi_neto_fmt": metricas_fmt.get("roi_neto"),
    }
    # Adjuntar datos completos y aplanar claves que no estén en el dict principal
    proyecto["datos"] = datos_safe
    for k, v in (estudio.datos or {}).items():
        if k not in proyecto:
            proyecto[k] = v
        # si existe un formateo preparado en metricas_fmt, exponer también `<clave>_fmt`
        if (f"{k}_fmt" not in proyecto) and (k in (metricas_fmt or {})):
            proyecto[f"{k}_fmt"] = metricas_fmt.get(k)
    proyecto = _safe_template_obj(proyecto)

    # Exponer aliases también en el objeto `estudio` (la plantilla usa `estudio.xxx` en algunos sitios)
    estudio.valor_adquisicion_total = proyecto.get("valor_adquisicion_total")
    estudio.precio_adquisicion = proyecto.get("precio_adquisicion")
    estudio.precio_compra = proyecto.get("precio_compra")
    estudio.valor_transmision = proyecto.get("valor_transmision")
    estudio.inversion_total = proyecto.get("inversion_total")
    estudio.beneficio_neto = proyecto.get("beneficio_neto")
    estudio.roi_neto = proyecto.get("roi_neto")

    # formatos
    estudio.valor_adquisicion_total_fmt = proyecto.get("valor_adquisicion_total_fmt")
    estudio.precio_adquisicion_fmt = proyecto.get("precio_adquisicion_fmt")
    estudio.precio_compra_fmt = proyecto.get("precio_compra_fmt")
    estudio.valor_transmision_fmt = proyecto.get("valor_transmision_fmt")
    estudio.inversion_total_fmt = proyecto.get("inversion_total_fmt")
    estudio.beneficio_neto_fmt = proyecto.get("beneficio_neto_fmt")
    estudio.roi_neto_fmt = proyecto.get("roi_neto_fmt")

    # Identificación inmueble (para plantillas que usan `estudio.xxx`)
    estudio.tipologia = proyecto.get("tipologia")
    estudio.superficie_m2 = proyecto.get("superficie_m2")
    estudio.superficie_m2_fmt = proyecto.get("superficie_m2_fmt")
    estudio.estado = proyecto.get("estado")
    estudio.situacion = proyecto.get("situacion")
    estudio.fecha = proyecto.get("fecha")
    estudio.fecha_fmt = proyecto.get("fecha_fmt")
    estudio.valor_referencia_fmt = proyecto.get("valor_referencia_fmt")

    # --- Snapshot para el PDF (estructura que espera el HTML) ---
    raw_snapshot = (estudio.datos or {}).get("snapshot", {}) or {}
    raw_comite = raw_snapshot.get("comite", {}) if isinstance(raw_snapshot, dict) else {}

    snapshot_ctx = {
        "datos": {
            "tecnico": {
                "nombre_proyecto": estudio.nombre,
                "direccion": estudio.direccion,
                "ref_catastral": estudio.ref_catastral,
                "valor_referencia": raw_snapshot.get("valor_referencia"),
                "tipologia": raw_snapshot.get("tipologia"),
                "superficie_m2": raw_snapshot.get("superficie_m2"),
                "estado": raw_snapshot.get("estado_inmueble"),
                "situacion": raw_snapshot.get("situacion"),
            },
            "economico": {
                "valor_adquisicion": raw_snapshot.get("valor_adquisicion"),
                "valor_transmision": raw_snapshot.get("valor_transmision"),
                "beneficio_estimado": (estudio.datos or {}).get("beneficio"),
                "roi_estimado": (estudio.datos or {}).get("roi"),
            },
            "kpis": {
                "ratio_euro_beneficio": raw_comite.get("ratio_euro_beneficio"),
                "colchon_seguridad": raw_comite.get("colchon_seguridad"),
                "precio_breakeven": raw_comite.get("breakeven"),
            },
            "comite": {
                "recomendacion": raw_comite.get("decision_texto"),
                "observaciones": raw_comite.get("conclusion"),
                "nivel_riesgo": raw_comite.get("nivel_riesgo"),
                "roi": raw_comite.get("roi"),
            },
        }
    }

    snapshot_ctx = _safe_template_obj(snapshot_ctx)

    # Exponer snapshot exactamente como lo espera el HTML
    ctx["snapshot"] = snapshot_ctx

    # Mantener compatibilidad con accesos antiguos
    proyecto["snapshot"] = snapshot_ctx
    proyecto["comite"] = snapshot_ctx["datos"]["comite"]

    ctx.update({
        "estudio": estudio,
        "proyecto": proyecto,
        "datos": datos_safe,
        "texto": _safe_template_obj(ctx.get("texto", {})),
    })

    return render(request, "core/pdf_estudio_rentabilidad.html", ctx)

@csrf_exempt
def pdf_estudio_rentabilidad(request, estudio_id):
    estudio = get_object_or_404(Estudio, id=estudio_id)

    # Métricas calculadas a partir del JSON `datos`
    ctx = _metricas_desde_estudio(estudio)
    # Exponemos el JSON completo del simulador para que el PDF pueda leer cualquier campo de Comité/Inversor
    datos_safe = _safe_template_obj(estudio.datos or {})

    metricas = ctx.get("metricas", {}) or {}
    metricas_fmt = ctx.get("metricas_fmt", {}) or {}
    inmueble = _datos_inmueble_desde_estudio(estudio)

    proyecto = {
        "id": estudio.id,
        "nombre": estudio.nombre,
        "direccion": estudio.direccion,
        "ref_catastral": estudio.ref_catastral,
        "valor_referencia": inmueble.get("valor_referencia"),
        "valor_referencia_fmt": inmueble.get("valor_referencia_fmt"),
        "tipologia": inmueble.get("tipologia"),
        "superficie_m2": inmueble.get("superficie_m2"),
        "superficie_m2_fmt": inmueble.get("superficie_m2_fmt"),
        "estado": inmueble.get("estado"),
        "situacion": inmueble.get("situacion"),
        "fecha": inmueble.get("fecha"),
        "fecha_fmt": inmueble.get("fecha_fmt"),
        "valor_adquisicion": metricas.get("valor_adquisicion", 0.0),
        "valor_adquisicion_total": metricas.get("valor_adquisicion_total", metricas.get("valor_adquisicion", 0.0)),
        "precio_adquisicion": metricas.get("precio_adquisicion", metricas.get("valor_adquisicion", 0.0)),
        "precio_compra": metricas.get("precio_compra", metricas.get("valor_adquisicion", 0.0)),
        "precio_transmision": metricas.get("precio_transmision", 0.0),
        "valor_transmision": metricas.get("valor_transmision", metricas.get("precio_transmision", 0.0)),
        "beneficio": metricas.get("beneficio", 0.0),
        "roi": metricas.get("roi", 0.0),
        "media_valoraciones": metricas.get("media_valoraciones", 0.0),
        "inversion_total": metricas.get("inversion_total", metricas.get("valor_adquisicion", 0.0)),
        "beneficio_neto": metricas.get("beneficio_neto", metricas.get("beneficio", 0.0)),
        "roi_neto": metricas.get("roi_neto", metricas.get("roi", 0.0)),
        "valor_adquisicion_fmt": metricas_fmt.get("valor_adquisicion"),
        "valor_adquisicion_total_fmt": metricas_fmt.get("valor_adquisicion_total", metricas_fmt.get("valor_adquisicion")),
        "precio_adquisicion_fmt": metricas_fmt.get("precio_adquisicion", metricas_fmt.get("valor_adquisicion")),
        "precio_compra_fmt": metricas_fmt.get("precio_compra", metricas_fmt.get("valor_adquisicion")),
        "precio_transmision_fmt": metricas_fmt.get("precio_transmision"),
        "valor_transmision_fmt": metricas_fmt.get("valor_transmision", metricas_fmt.get("precio_transmision")),
        "beneficio_fmt": metricas_fmt.get("beneficio"),
        "roi_fmt": metricas_fmt.get("roi"),
        "media_valoraciones_fmt": metricas_fmt.get("media_valoraciones"),
        "inversion_total_fmt": metricas_fmt.get("inversion_total"),
        "beneficio_neto_fmt": metricas_fmt.get("beneficio_neto"),
        "roi_neto_fmt": metricas_fmt.get("roi_neto"),
    }
    # Adjuntar datos completos y aplanar claves que no estén en el dict principal
    proyecto["datos"] = datos_safe
    for k, v in (estudio.datos or {}).items():
        if k not in proyecto:
            proyecto[k] = v
        # si existe un formateo preparado en metricas_fmt, exponer también `<clave>_fmt`
        if (f"{k}_fmt" not in proyecto) and (k in (metricas_fmt or {})):
            proyecto[f"{k}_fmt"] = metricas_fmt.get(k)
    proyecto = _safe_template_obj(proyecto)

    # Exponer aliases también en el objeto `estudio` (la plantilla usa `estudio.xxx` en algunos sitios)
    estudio.valor_adquisicion_total = proyecto.get("valor_adquisicion_total")
    estudio.precio_adquisicion = proyecto.get("precio_adquisicion")
    estudio.precio_compra = proyecto.get("precio_compra")
    estudio.valor_transmision = proyecto.get("valor_transmision")
    estudio.inversion_total = proyecto.get("inversion_total")
    estudio.beneficio_neto = proyecto.get("beneficio_neto")
    estudio.roi_neto = proyecto.get("roi_neto")

    # formatos
    estudio.valor_adquisicion_total_fmt = proyecto.get("valor_adquisicion_total_fmt")
    estudio.precio_adquisicion_fmt = proyecto.get("precio_adquisicion_fmt")
    estudio.precio_compra_fmt = proyecto.get("precio_compra_fmt")
    estudio.valor_transmision_fmt = proyecto.get("valor_transmision_fmt")
    estudio.inversion_total_fmt = proyecto.get("inversion_total_fmt")
    estudio.beneficio_neto_fmt = proyecto.get("beneficio_neto_fmt")
    estudio.roi_neto_fmt = proyecto.get("roi_neto_fmt")

    # Identificación inmueble (para plantillas que usan `estudio.xxx`)
    estudio.tipologia = proyecto.get("tipologia")
    estudio.superficie_m2 = proyecto.get("superficie_m2")
    estudio.superficie_m2_fmt = proyecto.get("superficie_m2_fmt")
    estudio.estado = proyecto.get("estado")
    estudio.situacion = proyecto.get("situacion")
    estudio.fecha = proyecto.get("fecha")
    estudio.fecha_fmt = proyecto.get("fecha_fmt")
    estudio.valor_referencia_fmt = proyecto.get("valor_referencia_fmt")

    ctx.update({
        "estudio": estudio,
        "proyecto": proyecto,
        "datos": datos_safe,
        "texto": _safe_template_obj(ctx.get("texto", {})),
    })

    return render(request, "core/pdf_estudio_rentabilidad.html", ctx)

def borrar_estudio(request, estudio_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)
    try:
        estudio = Estudio.objects.get(id=estudio_id)
        estudio.delete()
        return JsonResponse({"ok": True})
    except Estudio.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Estudio no encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)