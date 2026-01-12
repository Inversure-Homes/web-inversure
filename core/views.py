from __future__ import annotations

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import reverse
from django.db import transaction
from django.utils import timezone

from copy import deepcopy

import json
from decimal import Decimal
from datetime import date, datetime


from .models import Estudio, Proyecto
from .models import EstudioSnapshot, ProyectoSnapshot

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


# --- Helper para sanear datos para JSONField (Decimal, fechas, etc.) ---
def _sanitize_for_json(value):
    """Convierte objetos no serializables (Decimal, fechas) a tipos JSON-safe."""
    if isinstance(value, Decimal):
        # JSONField no acepta Decimal; convertimos a float
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    return value


def _deep_merge_dict(base: dict, overlay: dict) -> dict:
    """Merge recursivo: overlay pisa base; diccionarios se fusionan."""
    if not isinstance(base, dict):
        base = {}
    if not isinstance(overlay, dict):
        return base
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_merge_dict(base.get(k, {}), v)
        else:
            base[k] = v
    return base


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

    def _deep_get(*keys, default=None):
        containers = [
            d,
            d.get("inversor") if isinstance(d.get("inversor"), dict) else {},
            (d.get("snapshot") or {}).get("inversor") if isinstance(d.get("snapshot"), dict) else {},
            (d.get("kpis") or {}).get("metricas") if isinstance(d.get("kpis"), dict) else {},
            d.get("kpis") if isinstance(d.get("kpis"), dict) else {},
            d.get("economico") if isinstance(d.get("economico"), dict) else {},
            d.get("comite") if isinstance(d.get("comite"), dict) else {},
        ]
        for k in keys:
            for c in containers:
                if not isinstance(c, dict):
                    continue
                if k in c and c.get(k) not in (None, ""):
                    return c.get(k)
        return default

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

    # Enriquecer con métricas anidadas (comite/inversor/economico/kpis) si no estaban en raíz
    nested_sections = [
        d.get("comite"),
        d.get("inversor"),
        d.get("economico"),
        d.get("kpis"),
        (d.get("kpis") or {}).get("metricas") if isinstance(d.get("kpis"), dict) else None,
        (d.get("snapshot") or {}).get("kpis") if isinstance(d.get("snapshot"), dict) else None,
        ((d.get("snapshot") or {}).get("kpis") or {}).get("metricas") if isinstance(d.get("snapshot"), dict) else None,
    ]
    for sec in nested_sections:
        if not isinstance(sec, dict):
            continue
        for k, v in sec.items():
            if k in metricas:
                continue
            fv = _safe_float(v, None)
            if fv is None:
                continue
            metricas[k] = fv
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
    if "breakeven" in metricas and "precio_breakeven" not in metricas:
        metricas["precio_breakeven"] = metricas.get("breakeven")
        metricas_fmt["precio_breakeven"] = metricas_fmt.get("breakeven")
    if "break_even" in metricas and "precio_breakeven" not in metricas:
        metricas["precio_breakeven"] = metricas.get("break_even")
        metricas_fmt["precio_breakeven"] = metricas_fmt.get("break_even")

    # --- Vista inversor + reparto (para PDF/plantillas) ---
    inversion_total = _safe_float(
        metricas.get("inversion_total")
        or metricas.get("valor_adquisicion_total")
        or metricas.get("valor_adquisicion")
        or 0.0,
        0.0,
    )

    beneficio_bruto = _safe_float(
        metricas.get("beneficio_bruto")
        or metricas.get("beneficio")
        or 0.0,
        0.0,
    )

    comision_pct = _safe_float(
        _deep_get(
            "comision_inversure_pct",
            "inversure_comision_pct",
            "comision_pct",
        ),
        0.0,
    )
    if comision_pct < 0:
        comision_pct = 0.0
    if comision_pct > 100:
        comision_pct = 100.0

    comision_eur = _safe_float(
        _deep_get(
            "comision_inversure_eur",
            "inversure_comision_eur",
            "comision_eur",
        ),
        0.0,
    )

    # Si no viene calculada, la calculamos sobre el beneficio bruto
    if comision_eur == 0.0 and comision_pct and beneficio_bruto:
        comision_eur = beneficio_bruto * (comision_pct / 100.0)

    beneficio_neto_inversor = _safe_float(
        metricas.get("beneficio_neto")
        or (beneficio_bruto - comision_eur),
        0.0,
    )

    roi_neto_inversor = _safe_float(
        metricas.get("roi_neto")
        or ((beneficio_neto_inversor / inversion_total) * 100.0 if inversion_total else 0.0),
        0.0,
    )

    # Asegurar aliases útiles para plantillas
    metricas["comision_inversure_pct"] = comision_pct
    metricas["comision_inversure_eur"] = comision_eur
    metricas["beneficio_bruto"] = beneficio_bruto
    metricas["beneficio_neto"] = beneficio_neto_inversor
    metricas["roi_neto"] = roi_neto_inversor
    metricas["inversion_total"] = inversion_total
    # Aliases esperados por el PDF
    metricas["beneficio_estimado"] = metricas.get("beneficio_estimado", beneficio_bruto)
    metricas["roi_estimado"] = metricas.get("roi_estimado", roi)

    metricas_fmt["comision_inversure_pct"] = _fmt_pct(comision_pct)
    metricas_fmt["comision_inversure_eur"] = _fmt_eur(comision_eur)
    metricas_fmt["beneficio_bruto"] = _fmt_eur(beneficio_bruto)
    metricas_fmt["beneficio_neto"] = _fmt_eur(beneficio_neto_inversor)
    metricas_fmt["roi_neto"] = _fmt_pct(roi_neto_inversor)
    metricas_fmt["inversion_total"] = _fmt_eur(inversion_total)
    metricas_fmt["beneficio_estimado"] = _fmt_eur(metricas["beneficio_estimado"])
    metricas_fmt["roi_estimado"] = _fmt_pct(metricas["roi_estimado"])

    inversor = SafeAccessDict(
        {
            "inversion_total": inversion_total,
            "comision_inversure_pct": comision_pct,
            "comision_inversure_eur": comision_eur,
            "beneficio_neto_inversor": beneficio_neto_inversor,
            "roi_neto_inversor": roi_neto_inversor,
            # aliases por si el template usa otros nombres
            "comision_pct": comision_pct,
            "comision_eur": comision_eur,
            "beneficio_neto": beneficio_neto_inversor,
            "roi_neto": roi_neto_inversor,
        }
    )

    inversor_fmt = SafeAccessDict(
        {
            "inversion_total": _fmt_eur(inversion_total),
            "comision_inversure_pct": _fmt_pct(comision_pct),
            "comision_inversure_eur": _fmt_eur(comision_eur),
            "beneficio_neto_inversor": _fmt_eur(beneficio_neto_inversor),
            "roi_neto_inversor": _fmt_pct(roi_neto_inversor),
            # aliases
            "comision_pct": _fmt_pct(comision_pct),
            "comision_eur": _fmt_eur(comision_eur),
            "beneficio_neto": _fmt_eur(beneficio_neto_inversor),
            "roi_neto": _fmt_pct(roi_neto_inversor),
        }
    )

    # Reparto del beneficio (para barras/indicadores en PDF)
    reparto_total = beneficio_bruto
    reparto_inversure = comision_eur
    reparto_inversor = max(reparto_total - reparto_inversure, 0.0)

    if reparto_total > 0:
        pct_inversure = (reparto_inversure / reparto_total) * 100.0
        pct_inversor = (reparto_inversor / reparto_total) * 100.0
    else:
        pct_inversure = 0.0
        pct_inversor = 0.0

    # clamp para uso en CSS width
    pct_inversure = max(0.0, min(100.0, pct_inversure))
    pct_inversor = max(0.0, min(100.0, pct_inversor))

    reparto = SafeAccessDict(
        {
            "total": reparto_total,
            "inversure": reparto_inversure,
            "inversor": reparto_inversor,
            "pct_inversure": pct_inversure,
            "pct_inversor": pct_inversor,
        }
    )

    reparto_fmt = SafeAccessDict(
        {
            "total": _fmt_eur(reparto_total),
            "inversure": _fmt_eur(reparto_inversure),
            "inversor": _fmt_eur(reparto_inversor),
            "pct_inversure": _fmt_pct(pct_inversure),
            "pct_inversor": _fmt_pct(pct_inversor),
        }
    )

    return {
        "metricas": metricas,
        "metricas_fmt": metricas_fmt,
        "resultado": resultado,
        "texto": texto,
        "inversor": inversor,
        "inversor_fmt": inversor_fmt,
        "reparto": reparto,
        "reparto_fmt": reparto_fmt,
    }


# --- Datos de identificación inmueble desde estudio ---
def _datos_inmueble_desde_estudio(estudio: Estudio) -> dict:
    """Extrae y normaliza datos de identificación del inmueble desde `estudio` y su JSON `datos`.

    El simulador/JS puede guardar estos campos con nombres distintos o dentro de secciones
    (`datos['inmueble']`, `datos['tecnico']`, etc.). Aquí buscamos de forma defensiva.
    """
    d = estudio.datos or {}

    def _s(v) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def _deep_get(*keys, default=None):
        containers = [
            d,
            d.get("inmueble") if isinstance(d.get("inmueble"), dict) else {},
            d.get("tecnico") if isinstance(d.get("tecnico"), dict) else {},
            d.get("kpis") if isinstance(d.get("kpis"), dict) else {},
        ]
        for k in keys:
            for c in containers:
                if not isinstance(c, dict):
                    continue
                if k in c and c.get(k) not in (None, ""):
                    return c.get(k)
        return default

    tipologia = _s(
        _deep_get(
            "tipologia",
            "tipo_inmueble",
            "tipologia_inmueble",
            "tipo",
            "tipoActivo",
            "tipo_activo",
        )
    )

    estado = _s(
        _deep_get(
            "estado",
            "estado_conservacion",
            "estadoConservacion",
            "conservacion",
            "estado_inmueble",
        )
    )

    situacion = _s(
        _deep_get(
            "situacion",
            "situacion_ocupacional",
            "situacionOcupacional",
            "ocupacion",
            "situacion_inmueble",
        )
    )

    superficie_raw = _deep_get(
        "superficie_m2",
        "superficie",
        "m2",
        "metros_cuadrados",
        "m2_construidos",
        "m2Construidos",
        "superficie_construida",
        "superficieConstruida",
    )
    superficie_m2 = _safe_float(superficie_raw, 0.0)

    nombre_proyecto = _s(
        _deep_get(
            "nombre_proyecto",
            "nombre",
            "proyecto",
            "proyecto_nombre",
        )
    )
    if not nombre_proyecto:
        nombre_proyecto = _s(getattr(estudio, "nombre", "") or "")

    direccion = _s(
        _deep_get(
            "direccion",
            "direccion_completa",
            "proyecto_direccion",
        )
    )
    if not direccion:
        direccion = _s(getattr(estudio, "direccion", "") or "")

    ref_catastral = _s(
        _deep_get(
            "ref_catastral",
            "referencia_catastral",
            "ref_catastral_inmueble",
        )
    )
    if not ref_catastral:
        ref_catastral = _s(getattr(estudio, "ref_catastral", "") or "")

    # Valor de referencia: preferimos el campo del modelo si existe
    valor_referencia_num = _safe_float(getattr(estudio, "valor_referencia", None), None)
    if valor_referencia_num is None:
        valor_referencia_num = _safe_float(
            _deep_get(
                "valor_referencia",
                "valor_referencia_catastral",
                "valorRefCatastral",
                "valorReferencia",
                "valor_referencia_catastro",
            ),
            0.0,
        )

    # Formatos
    superficie_m2_fmt = f"{_fmt_es_number(superficie_m2, 0)} m²" if superficie_m2 else ""
    valor_referencia_fmt = _fmt_eur(valor_referencia_num) if valor_referencia_num else ""

    creado = getattr(estudio, "creado", None)
    creado_fmt = creado.strftime("%d/%m/%Y") if creado else ""

    return {
        "nombre_proyecto": nombre_proyecto,
        "direccion": direccion,
        "ref_catastral": ref_catastral,
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


def nuevo_estudio(request):
    """Crea un estudio nuevo, limpia la sesión del estudio anterior y redirige al simulador."""
    # Crear un estudio vacío como BORRADOR (no debe aparecer en lista hasta que se guarde)
    estudio = Estudio.objects.create(
        nombre="",
        direccion="",
        ref_catastral="",
        valor_referencia=None,
        datos={},
        guardado=False,
    )

    # Marcarlo como estudio activo en la sesión
    request.session["estudio_id"] = estudio.id

    # Redirigir al simulador (la vista simulador leerá el estudio desde sesión)
    return redirect("core:simulador")


def simulador(request):
    """Renderiza el simulador.

    - Si llega un estudio explícito por GET (estudio_id / id / codigo), lo carga y lo fija en sesión.
    - Si no, usa el estudio activo en sesión.
    - Si no hay ninguno, muestra el formulario vacío.

    Nota: `codigo` se acepta por compatibilidad con enlaces antiguos.
    Si `codigo` es numérico, se interpreta como `id`.
    Si no es numérico y el modelo Estudio tiene campo `codigo`, se busca por ese campo.
    """

    # 1) Selección explícita desde lista (prioridad sobre sesión)
    estudio_id_param = (request.GET.get("estudio_id") or request.GET.get("id") or "").strip()
    codigo_param = (request.GET.get("codigo") or "").strip()

    selected_id = None

    if estudio_id_param.isdigit():
        selected_id = int(estudio_id_param)
    elif codigo_param:
        if codigo_param.isdigit():
            selected_id = int(codigo_param)
        else:
            # Intentar buscar por campo `codigo` si existe en el modelo
            try:
                Estudio._meta.get_field("codigo")
            except Exception:
                selected_id = None
            else:
                try:
                    selected_id = Estudio.objects.only("id").get(codigo=codigo_param).id
                except Estudio.DoesNotExist:
                    selected_id = None

    # Si se seleccionó uno válido por GET, fijarlo en sesión
    if selected_id:
        request.session["estudio_id"] = selected_id

    # 2) Resolver estudio desde sesión
    estudio_obj = None
    estudio_id = request.session.get("estudio_id")
    if estudio_id:
        try:
            estudio_obj = Estudio.objects.get(id=estudio_id)
        except Estudio.DoesNotExist:
            estudio_obj = None

    # 3) Construir contexto
    if estudio_obj is None:
        estudio = {
            "id": None,
            "nombre": "",
            "direccion": "",
            "ref_catastral": "",
            "valor_referencia": "",
            "datos": {},
            "guardado": False,
            "bloqueado": False,
        }
    else:
        estudio = {
            "id": estudio_obj.id,
            "nombre": estudio_obj.nombre,
            "direccion": estudio_obj.direccion,
            "ref_catastral": estudio_obj.ref_catastral,
            "valor_referencia": estudio_obj.valor_referencia,
            "datos": estudio_obj.datos or {},
            "guardado": bool(getattr(estudio_obj, "guardado", False)),
            "bloqueado": bool(getattr(estudio_obj, "bloqueado", False)),
        }

    # --- Estado inicial para hidratar el simulador al abrir un estudio guardado ---
    estado_inicial = {}
    try:
        if estudio_obj is not None:
            datos0 = getattr(estudio_obj, "datos", None) or {}
            if isinstance(datos0, dict):
                # Preferimos snapshot si existe; si no, el JSON completo
                estado_inicial = datos0.get("snapshot") or datos0
    except Exception:
        estado_inicial = {}

    ctx = {
        "estudio": estudio,
        "ESTUDIO_ID": str(estudio_obj.id) if estudio_obj is not None else "",
        "ESTADO_INICIAL_JSON": json.dumps(estado_inicial, ensure_ascii=False),
    }

    return render(request, "core/simulador.html", ctx)


def lista_estudio(request):
    # Por defecto, ocultamos estudios ya convertidos a proyecto (bloqueados), para no saturar el listado.
    # Si se desea ver también los convertidos, usar ?mostrar_convertidos=1
    estudios_qs = Estudio.objects.filter(guardado=True)

    mostrar_convertidos = (request.GET.get("mostrar_convertidos") == "1")
    try:
        Estudio._meta.get_field("bloqueado")
        if not mostrar_convertidos:
            estudios_qs = estudios_qs.filter(bloqueado=False)
    except Exception:
        # Si el modelo no tiene el campo (o hay inconsistencias), mantenemos el listado clásico
        pass

    estudios_qs_base = estudios_qs
    try:
        estudios_qs = estudios_qs.order_by("-datos__roi", "-id")
        # Force evaluation to catch JSON lookup errors on backends without JSON1 support.
        list(estudios_qs[:1])
    except Exception:
        estudios_qs = estudios_qs_base.order_by("-id")
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
            "guardado": bool(getattr(e, "guardado", False)),
            "bloqueado": bool(getattr(e, "bloqueado", False)),
        })

    return render(
        request,
        "core/lista_estudio.html",
        {"estudios": estudios},
    )


def lista_proyectos(request):
    proyectos = Proyecto.objects.all().order_by("-id")

    def _as_float(val, default=0.0):
        try:
            if val is None or val == "":
                return float(default)
            return float(val)
        except Exception:
            return float(default)

    def _get_snapshot(p: Proyecto) -> dict:
        # Prioridad: snapshot_datos (copia inmutable) > origen_snapshot.datos > origen_estudio.datos
        snap = getattr(p, "snapshot_datos", None)
        if isinstance(snap, dict) and snap:
            return snap
        osnap = getattr(p, "origen_snapshot", None)
        if osnap is not None:
            datos = getattr(osnap, "datos", None)
            if isinstance(datos, dict) and datos:
                return datos
        oest = getattr(p, "origen_estudio", None)
        if oest is not None:
            datos = getattr(oest, "datos", None)
            if isinstance(datos, dict) and datos:
                return datos
        return {}

    # Enriquecer cada proyecto con métricas heredadas (sin exigir cambios en el template)
    for p in proyectos:
        snap = _get_snapshot(p)
        economico = snap.get("economico") if isinstance(snap.get("economico"), dict) else {}
        inversor = snap.get("inversor") if isinstance(snap.get("inversor"), dict) else {}
        kpis = snap.get("kpis") if isinstance(snap.get("kpis"), dict) else {}
        metricas = kpis.get("metricas") if isinstance(kpis.get("metricas"), dict) else {}

        # Capital objetivo (lo que realmente se invierte) – heredado del estudio
        capital_objetivo = (
            inversor.get("inversion_total")
            or metricas.get("inversion_total")
            or metricas.get("valor_adquisicion_total")
            or metricas.get("valor_adquisicion")
            or economico.get("valor_adquisicion")
            or metricas.get("precio_adquisicion")
            or metricas.get("precio_compra")
            or 0
        )
        capital_objetivo = _as_float(capital_objetivo, 0.0)

        # Mientras no exista módulo de inversores/captación, mostramos captado = objetivo
        capital_captado = capital_objetivo

        # ROI heredado del estudio (preferimos neto si existe)
        roi = (
            inversor.get("roi_neto")
            or metricas.get("roi_neto")
            or metricas.get("roi")
            or economico.get("roi_estimado")
            or economico.get("roi")
            or 0
        )
        roi = _as_float(roi, 0.0)

        # Adjuntar atributos para plantilla
        p.capital_objetivo = capital_objetivo
        p.capital_captado = capital_captado
        p.roi = roi
        p._snapshot = snap

    return render(
        request,
        "core/lista_proyectos.html",
        {"proyectos": proyectos},
    )


@ensure_csrf_cookie
def proyecto(request, proyecto_id: int):
    """Vista única del Proyecto (pestañas), heredando el snapshot del estudio convertido."""
    proyecto_obj = get_object_or_404(Proyecto, id=proyecto_id)

    # --- Compatibilidad de plantilla: algunos campos pueden no existir en el modelo Proyecto ---
    # Django templates fallan con VariableDoesNotExist si se accede a un atributo inexistente.
    # Definimos atributos "dummy" para que la plantilla no rompa (los valores reales vendrán del snapshot).
    _tpl_expected_fields = [
        "venta_estimada",
        "precio_propiedad",
        "precio_compra_inmueble",
        "precio_venta_estimado",
        "notaria",
        "registro",
        "itp",
        "direccion",
        "ref_catastral",
        "valor_referencia",
    ]
    for _f in _tpl_expected_fields:
        if not hasattr(proyecto_obj, _f):
            setattr(proyecto_obj, _f, "")

    # Snapshot efectivo del proyecto (prioridad):
    # 1) Último ProyectoSnapshot (guardados/versionado)
    # 2) snapshot_datos (copia inmutable heredada)
    # 3) origen_snapshot.datos
    # 4) origen_estudio.datos
    snapshot: dict = {}
    try:
        last_ps = ProyectoSnapshot.objects.filter(proyecto=proyecto_obj).order_by("-version_num", "-id").first()
        if last_ps is not None:
            ps_d = getattr(last_ps, "datos", None)
            if isinstance(ps_d, dict) and ps_d:
                snapshot = ps_d

        if not snapshot:
            sd = getattr(proyecto_obj, "snapshot_datos", None)
            if isinstance(sd, dict) and sd:
                snapshot = sd

        if not snapshot:
            osnap = getattr(proyecto_obj, "origen_snapshot", None)
            if osnap is not None:
                od = getattr(osnap, "datos", None)
                if isinstance(od, dict) and od:
                    snapshot = od

        if not snapshot:
            oest = getattr(proyecto_obj, "origen_estudio", None)
            if oest is not None:
                ed = getattr(oest, "datos", None)
                if isinstance(ed, dict) and ed:
                    snapshot = ed
    except Exception:
        snapshot = {}

    # --- Normalización defensiva del snapshot y KPIs ---
    if not isinstance(snapshot, dict):
        snapshot = {}

    # --- Overlay persistente (ediciones del proyecto) ---
    # Si el usuario guardó cambios operativos del proyecto, los almacenamos en `Proyecto.extra`
    # y deben re-hidratar la vista al recargar la página.
    overlay = {}
    try:
        # 1) Preferimos `Proyecto.extra` si existe
        extra = getattr(proyecto_obj, "extra", None)
        if isinstance(extra, dict):
            ultimo = extra.get("ultimo_guardado")
            if isinstance(ultimo, dict) and isinstance(ultimo.get("payload"), dict):
                overlay = ultimo.get("payload") or {}

        # 2) Fallback: si no hay `extra`, buscamos overlay persistido dentro de `snapshot_datos`
        if not overlay:
            sd = getattr(proyecto_obj, "snapshot_datos", None)
            if isinstance(sd, dict) and isinstance(sd.get("_overlay"), dict):
                overlay = sd.get("_overlay") or {}
    except Exception:
        overlay = {}

    if overlay:
        merged_snapshot = deepcopy(snapshot) if isinstance(snapshot, dict) else {}
        merged_snapshot = _deep_merge_dict(merged_snapshot, overlay)
        snapshot = merged_snapshot
    # --- Forzar nombre persistido del PROYECTO en el snapshot renderizado ---
    # Evita que al recargar se muestre el nombre heredado del estudio.
    try:
        nombre_p = (getattr(proyecto_obj, "nombre", "") or "").strip()
    except Exception:
        nombre_p = ""

    if nombre_p:
        if not isinstance(snapshot, dict):
            snapshot = {}

        if not isinstance(snapshot.get("proyecto"), dict):
            snapshot["proyecto"] = {}
        snapshot["proyecto"]["nombre"] = nombre_p
        snapshot["proyecto"]["nombre_proyecto"] = nombre_p

        if not isinstance(snapshot.get("inmueble"), dict):
            snapshot["inmueble"] = {}
        snapshot["inmueble"]["nombre_proyecto"] = nombre_p
    kpis_raw = snapshot.get("kpis")
    if not isinstance(kpis_raw, dict):
        kpis_raw = {}
        snapshot["kpis"] = kpis_raw

    if not isinstance(kpis_raw.get("metricas"), dict):
        kpis_raw["metricas"] = {}

    # Exponer `metricas` como atajo seguro para la plantilla proyecto.html
    metricas_raw = kpis_raw.get("metricas") if isinstance(kpis_raw.get("metricas"), dict) else {}

    # --- Estado inicial para hidratar el simulador en modo proyecto ---
    estado_inicial = {}
    try:
        if isinstance(snapshot, dict) and snapshot:
            # Si el snapshot ya incluye un bloque snapshot (overlay completo), lo preferimos
            estado_inicial = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else snapshot
    except Exception:
        estado_inicial = {}

    # --- Editabilidad del proyecto ---
    # En proyecto (fase operativa) el formulario debe ser editable por defecto.
    # Solo lo bloqueamos si existe un campo de estado/cierre que indique finalización.
    editable = True
    try:
        estado = (getattr(proyecto_obj, "estado", "") or "").strip().lower()
        # Estados típicos de cierre (ajústalos si tu modelo usa otros nombres)
        if estado in {"cerrado", "cerrado_positivo", "cerrado_negativo", "finalizado", "descartado"}:
            editable = False
    except Exception:
        editable = True

    # --- Captación / Progreso de inversión (robusto) ---
    # Objetivo: lo que se pretende captar (normalmente la inversión total)
    try:
        inv_sec = snapshot.get("inversor") if isinstance(snapshot.get("inversor"), dict) else {}
        eco_sec = snapshot.get("economico") if isinstance(snapshot.get("economico"), dict) else {}
        kpis_sec = snapshot.get("kpis") if isinstance(snapshot.get("kpis"), dict) else {}
        met_sec = kpis_sec.get("metricas") if isinstance(kpis_sec.get("metricas"), dict) else {}

        # Capital objetivo (prioridad)
        capital_objetivo = _safe_float(
            inv_sec.get("inversion_total")
            or inv_sec.get("capital_objetivo")
            or inv_sec.get("objetivo")
            or met_sec.get("inversion_total")
            or met_sec.get("valor_adquisicion_total")
            or met_sec.get("valor_adquisicion")
            or eco_sec.get("valor_adquisicion")
            or eco_sec.get("valor_adquisicion_total"),
            0.0,
        )

        # Capital captado: si aún no hay módulo de inversores, por defecto 0
        cap_sec = snapshot.get("captacion") if isinstance(snapshot.get("captacion"), dict) else {}
        capital_captado = _safe_float(
            cap_sec.get("capital_captado")
            or cap_sec.get("captado")
            or inv_sec.get("capital_captado")
            or inv_sec.get("captado")
            or met_sec.get("capital_captado")
            or 0.0,
            0.0,
        )

        # Normalizar
        if capital_objetivo < 0:
            capital_objetivo = 0.0
        if capital_captado < 0:
            capital_captado = 0.0

        # % captado
        if capital_objetivo > 0:
            pct_captado = (capital_captado / capital_objetivo) * 100.0
        else:
            pct_captado = 0.0

        # clamp 0..100
        if pct_captado < 0:
            pct_captado = 0.0
        if pct_captado > 100:
            pct_captado = 100.0

        restante = max(capital_objetivo - capital_captado, 0.0)

        captacion_ctx = SafeAccessDict({
            "capital_objetivo": capital_objetivo,
            "capital_captado": capital_captado,
            "pct_captado": pct_captado,
            "restante": restante,
            "capital_objetivo_fmt": _fmt_eur(capital_objetivo),
            "capital_captado_fmt": _fmt_eur(capital_captado),
            "restante_fmt": _fmt_eur(restante),
            "pct_captado_fmt": _fmt_pct(pct_captado),
        })
    except Exception:
        captacion_ctx = SafeAccessDict({
            "capital_objetivo": 0.0,
            "capital_captado": 0.0,
            "pct_captado": 0.0,
            "restante": 0.0,
            "capital_objetivo_fmt": _fmt_eur(0.0),
            "capital_captado_fmt": _fmt_eur(0.0),
            "restante_fmt": _fmt_eur(0.0),
            "pct_captado_fmt": _fmt_pct(0.0),
        })

    ctx = {
        "PROYECTO_ID": str(proyecto_obj.id),
        "ESTADO_INICIAL_JSON": json.dumps(estado_inicial, ensure_ascii=False),
        "editable": editable,
        "proyecto": proyecto_obj,
        "snapshot": _safe_template_obj(snapshot),
        # Atajos por si `proyecto.html` los usa como en el PDF/estudio
        "inmueble": _safe_template_obj(snapshot.get("inmueble", {})) if isinstance(snapshot.get("inmueble"), dict) else SafeAccessDict(),
        "economico": _safe_template_obj(snapshot.get("economico", {})) if isinstance(snapshot.get("economico"), dict) else SafeAccessDict(),
        "inversor": _safe_template_obj(snapshot.get("inversor", {})) if isinstance(snapshot.get("inversor"), dict) else SafeAccessDict(),
        "comite": _safe_template_obj(snapshot.get("comite", {})) if isinstance(snapshot.get("comite"), dict) else SafeAccessDict(),
        "kpis": _safe_template_obj(snapshot.get("kpis", {})) if isinstance(snapshot.get("kpis"), dict) else SafeAccessDict(),
        "metricas": _safe_template_obj(metricas_raw) if isinstance(metricas_raw, dict) else SafeAccessDict(),
        "captacion": captacion_ctx,
        "capital_objetivo": captacion_ctx.get("capital_objetivo"),
        "capital_captado": captacion_ctx.get("capital_captado"),
        "pct_captado": captacion_ctx.get("pct_captado"),
    }

    return render(request, "core/proyecto.html", ctx)


@csrf_exempt
def guardar_estudio(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")

        # Puede venir como `id` o puede no venir (si el frontend perdió el ID).
        # Para evitar duplicados, si no llega ID usamos el estudio activo en sesión.
        estudio_id = data.get("id") or data.get("estudio_id") or data.get("ESTUDIO_ID")
        if not estudio_id:
            estudio_id = request.session.get("estudio_id")

        # Si el estudio está bloqueado (ya convertido a proyecto), no permitimos cambios.
        if estudio_id:
            try:
                _e0 = Estudio.objects.only("id", "bloqueado").get(id=estudio_id)
                if getattr(_e0, "bloqueado", False):
                    return JsonResponse(
                        {"ok": False, "error": "Este estudio está bloqueado porque ya se convirtió en proyecto."},
                        status=409,
                    )
            except Estudio.DoesNotExist:
                pass

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

        # --- HIDRATAR SNAPSHOT CANÓNICO PARA PDF / PROYECTO ---
        # Garantiza que inversor, kpis y economico NUNCA sean strings vacíos
        try:
            fake_estudio = Estudio(
                datos=datos,
                valor_referencia=None,
            )

            kpis = _metricas_desde_estudio(fake_estudio)
            inmueble = _datos_inmueble_desde_estudio(fake_estudio)

            snapshot = {
                "inmueble": inmueble,
                "economico": kpis.get("metricas", {}),
                "kpis": {
                    "metricas": kpis.get("metricas", {}),
                    "metricas_fmt": kpis.get("metricas_fmt", {}),
                },
                "inversor": kpis.get("inversor", {}),
                "comite": datos.get("comite", {}) if isinstance(datos.get("comite"), dict) else {},
                "resultado": kpis.get("resultado", {}),
                "texto": kpis.get("texto", {}),
                "reparto": kpis.get("reparto", {}),
            }

            # Preservar campos operativos no calculados (p.ej. meses/financiación)
            meses_raw = datos.get("meses") or datos.get("meses_operacion") or datos.get("meses_operación")
            financiacion_raw = datos.get("financiacion_pct") or datos.get("porcentaje_financiacion")
            if meses_raw not in (None, ""):
                snapshot["economico"]["meses"] = meses_raw
            if financiacion_raw not in (None, ""):
                snapshot["economico"]["financiacion_pct"] = financiacion_raw

            # Forzar snapshot y secciones críticas
            datos["snapshot"] = snapshot
            datos["inversor"] = snapshot.get("inversor", {})
            if not isinstance(datos.get("economico"), dict):
                datos["economico"] = {}
            datos["economico"] = _deep_merge_dict(datos["economico"], snapshot.get("economico", {}))
            datos["kpis"] = snapshot.get("kpis", {})

        except Exception:
            # En caso extremo, evitar que inversor sea string
            if not isinstance(datos.get("inversor"), dict):
                datos["inversor"] = {}
            if not isinstance(datos.get("economico"), dict):
                datos["economico"] = {}
            if not isinstance(datos.get("kpis"), dict):
                datos["kpis"] = {}

        # --- Compatibilidad: payloads que envían secciones en la raíz (no dentro de `datos`) ---
        # Hay campos editables (p.ej. comisión) que deben sobrescribir valores existentes.
        ALWAYS_OVERWRITE_KEYS = {
            # comisión Inversure (porcentaje / euros)
            "comision_inversure_pct",
            "inversure_comision_pct",
            "comision_pct",
            "comision_inversure_eur",
            "inversure_comision_eur",
            "comision_eur",
            # variantes usadas en diferentes pantallas
            "comision_inversure",
            "comision_inversure_sobre_beneficio",
            "comision_inversure_sobre_beneficio_pct",
            "comision_inversure_sobre_beneficio_eur",
        }

        for _root_sec in ("inmueble", "economico", "comite", "inversor", "kpis", "tecnico", "proyecto"):
            sec_val = data.get(_root_sec)
            if isinstance(sec_val, dict):
                if _root_sec not in datos or not isinstance(datos.get(_root_sec), dict):
                    datos[_root_sec] = {}
                for kk, vv in sec_val.items():
                    if kk in ALWAYS_OVERWRITE_KEYS:
                        datos[_root_sec][kk] = vv
                    else:
                        if kk not in datos[_root_sec] or datos[_root_sec].get(kk) in (None, ""):
                            datos[_root_sec][kk] = vv

        # Aplanar secciones por compatibilidad (algunos templates esperan keys en raíz)
        def _flatten_section(section_key: str) -> None:
            sec = datos.get(section_key)
            if isinstance(sec, dict):
                for kk, vv in sec.items():
                    if kk in ALWAYS_OVERWRITE_KEYS:
                        datos[kk] = vv
                    else:
                        if kk not in datos or datos.get(kk) in (None, ""):
                            datos[kk] = vv

        for _sec in ("tecnico", "economico", "comite", "inversor", "kpis", "inmueble", "proyecto"):
            _flatten_section(_sec)

        # Absorber `datos.snapshot` si existe
        snap = datos.get("snapshot") if isinstance(datos.get("snapshot"), dict) else {}
        if snap:
            for kk, vv in snap.items():
                if kk == "comite":
                    continue
                if kk not in datos or datos.get(kk) in (None, ""):
                    datos[kk] = vv

            if isinstance(snap.get("comite"), dict):
                if "comite" not in datos or not isinstance(datos.get("comite"), dict):
                    datos["comite"] = {}
                for kk, vv in snap["comite"].items():
                    if kk not in datos["comite"] or datos["comite"].get(kk) in (None, ""):
                        datos["comite"][kk] = vv

                for kk in (
                    "decision",
                    "decision_texto",
                    "recomendacion",
                    "nivel_riesgo",
                    "comentario",
                    "observaciones",
                ):
                    if kk in datos["comite"] and (kk not in datos or datos.get(kk) in (None, "")):
                        datos[kk] = datos["comite"].get(kk)

        # Fallback de campos principales desde `datos` (para que lista_estudio tenga nombre/dirección)
        def _get_str_from(*vals) -> str:
            for v in vals:
                if v is None:
                    continue
                if isinstance(v, str):
                    s = v.strip()
                    if s:
                        return s
                else:
                    s = str(v).strip()
                    if s:
                        return s
            return ""

        inmueble_sec = datos.get("inmueble") if isinstance(datos.get("inmueble"), dict) else {}
        proyecto_sec = datos.get("proyecto") if isinstance(datos.get("proyecto"), dict) else {}

        if not nombre:
            nombre = _get_str_from(
                datos.get("nombre"),
                datos.get("nombre_proyecto"),
                proyecto_sec.get("nombre"),
                proyecto_sec.get("nombre_proyecto"),
                inmueble_sec.get("nombre"),
                inmueble_sec.get("nombre_proyecto"),
                datos.get("proyecto_nombre"),
                datos.get("proyecto"),
            )

        if not direccion:
            direccion = _get_str_from(
                datos.get("direccion"),
                datos.get("direccion_completa"),
                proyecto_sec.get("direccion"),
                proyecto_sec.get("direccion_completa"),
                inmueble_sec.get("direccion"),
                inmueble_sec.get("direccion_completa"),
                datos.get("proyecto_direccion"),
            )

        if not ref_catastral:
            ref_catastral = _get_str_from(
                datos.get("ref_catastral"),
                datos.get("referencia_catastral"),
                proyecto_sec.get("ref_catastral"),
                proyecto_sec.get("referencia_catastral"),
                inmueble_sec.get("ref_catastral"),
                inmueble_sec.get("referencia_catastral"),
            )

        # Valor de referencia (opcional)
        valor_referencia_raw = (
            data.get("valor_referencia")
            or datos.get("valor_referencia")
            or proyecto_sec.get("valor_referencia")
            or inmueble_sec.get("valor_referencia")
            or data.get("valor_referencia_catastral")
            or datos.get("valor_referencia_catastral")
        )
        valor_referencia = None
        if valor_referencia_raw not in (None, ""):
            try:
                # admitir formatos es-ES "231.369,24"
                if isinstance(valor_referencia_raw, str):
                    s = valor_referencia_raw.strip().replace("€", "").strip()
                    if "." in s and "," in s:
                        s = s.replace(".", "").replace(",", ".")
                    else:
                        s = s.replace(",", ".")
                    valor_referencia = Decimal(s)
                else:
                    valor_referencia = Decimal(str(valor_referencia_raw))
            except Exception:
                valor_referencia = None

        # Sanear datos para JSONField
        datos = _sanitize_for_json(datos)

        # Guardar (actualizando el borrador existente para NO duplicar)
        if estudio_id:
            try:
                estudio_obj = Estudio.objects.get(id=int(estudio_id))
            except Exception:
                estudio_obj = None
        else:
            estudio_obj = None

        if estudio_obj is None:
            # Si por algún motivo no existe borrador, creamos uno nuevo
            estudio_obj = Estudio.objects.create(
                nombre=nombre,
                direccion=direccion,
                ref_catastral=ref_catastral,
                valor_referencia=valor_referencia,
                datos=datos,
                guardado=True,
            )
        else:
            estudio_obj.nombre = nombre
            estudio_obj.direccion = direccion
            estudio_obj.ref_catastral = ref_catastral
            if valor_referencia is not None:
                estudio_obj.valor_referencia = valor_referencia
            estudio_obj.datos = datos
            estudio_obj.guardado = True
            estudio_obj.save()

        # Asegurar sesión apuntando al estudio guardado
        request.session["estudio_id"] = estudio_obj.id

        return JsonResponse({"ok": True, "id": estudio_obj.id})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def guardar_proyecto(request, proyecto_id: int):
    """Guarda cambios del Proyecto de forma automática.

    Este endpoint existe porque `core/urls.py` lo referencia.
    Persistimos el payload dentro de `Proyecto.extra['ultimo_guardado']` para re-hidratar la vista.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    proyecto_obj = get_object_or_404(Proyecto, id=proyecto_id)

    try:
        payload = json.loads(request.body or "{}")
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    # Permitir que el payload incluya un nombre editable (si se quiere persistir)
    nombre = (payload.get("nombre") or payload.get("nombre_proyecto") or "").strip()
    if nombre:
        try:
            proyecto_obj.nombre = nombre
            proyecto_obj.save(update_fields=["nombre"])
        except Exception:
            # si el campo no existe en el modelo, ignoramos
            pass

    # Guardar overlay en `extra`
    try:
        extra = getattr(proyecto_obj, "extra", None)
        if not isinstance(extra, dict):
            extra = {}

        extra["ultimo_guardado"] = {
            "ts": timezone.now().isoformat(),
            "payload": _sanitize_for_json(payload),
        }

        # Guardar también dentro de snapshot_datos como fallback si existe
        try:
            proyecto_obj.extra = extra
            proyecto_obj.save(update_fields=["extra"])
        except Exception:
            # si el campo extra no existe, intentamos snapshot_datos
            sd = getattr(proyecto_obj, "snapshot_datos", None)
            if isinstance(sd, dict):
                sd["_overlay"] = _sanitize_for_json(payload)
                proyecto_obj.snapshot_datos = sd
                proyecto_obj.save(update_fields=["snapshot_datos"])

        return JsonResponse({"ok": True})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
              
            

        if not direccion:
            direccion = _get_str_from(
                datos.get("direccion"),
                datos.get("direccion_completa"),
                proyecto_sec.get("direccion"),
                proyecto_sec.get("direccion_completa"),
                inmueble_sec.get("direccion"),
                inmueble_sec.get("direccion_completa"),
            )

        if not ref_catastral:
            ref_catastral = _get_str_from(
                datos.get("ref_catastral"),
                datos.get("referencia_catastral"),
                proyecto_sec.get("ref_catastral"),
                proyecto_sec.get("referencia_catastral"),
                inmueble_sec.get("ref_catastral"),
                inmueble_sec.get("referencia_catastral"),
            )

        # Persistir valor de referencia si llega
        valor_referencia = data.get("valor_referencia")
        if valor_referencia in (None, ""):
            valor_referencia = (
                datos.get("valor_referencia")
                or inmueble_sec.get("valor_referencia")
                or inmueble_sec.get("valor_referencia_catastral")
            )
        try:
            if valor_referencia in (None, ""):
                valor_referencia = None
            else:
                valor_referencia = Decimal(str(valor_referencia).replace("€", "").strip().replace(".", "").replace(",", "."))
        except Exception:
            valor_referencia = None

        # Sanear JSON (Decimal/fechas)
        datos = _sanitize_for_json(datos)

        # Guardar/actualizar
        if estudio_id:
            try:
                estudio = Estudio.objects.get(id=estudio_id)
            except Estudio.DoesNotExist:
                estudio = Estudio.objects.create(
                    nombre=nombre,
                    direccion=direccion,
                    ref_catastral=ref_catastral,
                    valor_referencia=valor_referencia,
                    datos=datos,
                    guardado=True,
                )
        else:
            estudio = Estudio.objects.create(
                nombre=nombre,
                direccion=direccion,
                ref_catastral=ref_catastral,
                valor_referencia=valor_referencia,
                datos=datos,
                guardado=True,
            )

        # Actualizar campos en cualquier caso
        estudio.nombre = nombre
        estudio.direccion = direccion
        estudio.ref_catastral = ref_catastral
        try:
            # si el campo existe
            Estudio._meta.get_field("valor_referencia")
            estudio.valor_referencia = valor_referencia
        except Exception:
            pass

        # Marcar como guardado
        try:
            Estudio._meta.get_field("guardado")
            estudio.guardado = True
        except Exception:
            pass

        estudio.datos = datos
        estudio.save()

        # Mantenerlo como estudio activo
        request.session["estudio_id"] = estudio.id

        return JsonResponse({"ok": True, "id": estudio.id})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


def borrar_estudio(request, estudio_id: int):
    estudio = get_object_or_404(Estudio, id=estudio_id)
    estudio.delete()
    # si se borró el activo en sesión, limpiar
    if request.session.get("estudio_id") == estudio_id:
        try:
            del request.session["estudio_id"]
        except KeyError:
            pass
    return redirect("core:lista_estudio")


@csrf_exempt
def convertir_a_proyecto(request, estudio_id: int):
    """Convierte un Estudio guardado en Proyecto.

    - Crea un EstudioSnapshot inmutable.
    - Crea un Proyecto heredando nombre/dirección/ref y snapshot.
    - Bloquea el estudio (si existe el campo).

    Devuelve JSON con redirect a lista_proyectos.
    """

    if request.method not in ("POST", "GET"):
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    estudio = get_object_or_404(Estudio, id=estudio_id)

    # Si ya está bloqueado, intentamos redirigir al proyecto existente si lo hubiera
    try:
        if getattr(estudio, "bloqueado", False):
            return JsonResponse({"ok": True, "redirect": reverse("core:lista_proyectos")})
    except Exception:
        pass

    def _has_field(model_cls, field_name: str) -> bool:
        try:
            model_cls._meta.get_field(field_name)
            return True
        except Exception:
            return False

    with transaction.atomic():
        # 1) Snapshot del estudio
        datos_snapshot = _sanitize_for_json(estudio.datos or {})

        # versionado si existe
        snap_kwargs = {"estudio": estudio, "datos": datos_snapshot}
        if _has_field(EstudioSnapshot, "version_num"):
            last_v = (
                EstudioSnapshot.objects.filter(estudio=estudio)
                .order_by("-version_num", "-id")
                .values_list("version_num", flat=True)
                .first()
            )
            snap_kwargs["version_num"] = int(last_v or 0) + 1

        estudio_snapshot = EstudioSnapshot.objects.create(**snap_kwargs)

        # 2) Crear proyecto heredando
        proyecto_kwargs = {}
        if _has_field(Proyecto, "nombre"):
            proyecto_kwargs["nombre"] = estudio.nombre or ""
        if _has_field(Proyecto, "origen_estudio"):
            proyecto_kwargs["origen_estudio"] = estudio
        if _has_field(Proyecto, "origen_snapshot"):
            proyecto_kwargs["origen_snapshot"] = estudio_snapshot
        if _has_field(Proyecto, "snapshot_datos"):
            proyecto_kwargs["snapshot_datos"] = datos_snapshot
        if _has_field(Proyecto, "estado"):
            # estado inicial del proyecto
            proyecto_kwargs["estado"] = "Estudio"

        proyecto = Proyecto.objects.create(**proyecto_kwargs)

        # 3) Bloquear el estudio
        if _has_field(Estudio, "bloqueado"):
            estudio.bloqueado = True
        if _has_field(Estudio, "bloqueado_en"):
            estudio.bloqueado_en = timezone.now()
        estudio.save()

    return JsonResponse({"ok": True, "proyecto_id": proyecto.id, "redirect": reverse("core:lista_proyectos")})

def pdf_estudio_preview(request, estudio_id: int):
    estudio = get_object_or_404(Estudio, id=estudio_id)

    # Recalcular SIEMPRE desde backend
    kpis = _metricas_desde_estudio(estudio)
    inmueble = _datos_inmueble_desde_estudio(estudio)
    datos_raw = estudio.datos or {}
    if not isinstance(datos_raw, dict):
        datos_raw = {}

    comite_raw = datos_raw.get("comite") if isinstance(datos_raw.get("comite"), dict) else {}
    comite = dict(comite_raw) if isinstance(comite_raw, dict) else {}
    # Completar con campos sueltos (compatibilidad con payloads antiguos)
    for src_key, dst_key in (
        ("recomendacion", "recomendacion"),
        ("decision", "recomendacion"),
        ("decision_texto", "recomendacion"),
        ("observaciones", "observaciones"),
        ("comentario", "observaciones"),
        ("comentario_comite", "observaciones"),
        ("resumen_ejecutivo_comite", "observaciones"),
        ("resumen_ejecutivo", "resumen_ejecutivo"),
        ("resumen_ejecutivo_comite", "resumen_ejecutivo"),
    ):
        if comite.get(dst_key) in (None, "") and datos_raw.get(src_key) not in (None, ""):
            comite[dst_key] = datos_raw.get(src_key)

    # Snapshot canónico (el PDF SOLO usa esto)
    kpis_metricas = kpis.get("metricas", {}) if isinstance(kpis.get("metricas", {}), dict) else {}
    meses = _safe_float(
        datos_raw.get("meses")
        or datos_raw.get("meses_operacion")
        or datos_raw.get("meses_operación")
        or (datos_raw.get("economico") or {}).get("meses") if isinstance(datos_raw.get("economico"), dict) else None,
        None,
    )
    financiacion_pct = _safe_float(
        datos_raw.get("financiacion_pct")
        or datos_raw.get("porcentaje_financiacion")
        or (datos_raw.get("economico") or {}).get("financiacion_pct") if isinstance(datos_raw.get("economico"), dict) else None,
        None,
    )
    if meses is not None and "meses" not in kpis_metricas:
        kpis_metricas["meses"] = meses
    if financiacion_pct is not None and "financiacion_pct" not in kpis_metricas:
        kpis_metricas["financiacion_pct"] = financiacion_pct
    snapshot = {
        "inmueble": inmueble,
        "economico": {**kpis_metricas},
        # Compatibilidad: exponer KPIs tanto en raíz de "kpis" como dentro de "metricas".
        "kpis": {
            **kpis_metricas,
            "metricas": kpis_metricas,
            "metricas_fmt": kpis.get("metricas_fmt", {}),
        },
        "inversor": kpis.get("inversor", {}),
        "inversor_fmt": kpis.get("inversor_fmt", {}),
        "comite": comite,
        "resultado": kpis.get("resultado", {}),
        "texto": kpis.get("texto", {}),
        "reparto": kpis.get("reparto", {}),
        "reparto_fmt": kpis.get("reparto_fmt", {}),
    }

    ctx = {
        "estudio": estudio,
        "datos": _safe_template_obj(estudio.datos or {}),
        "inmueble": _safe_template_obj(inmueble),
        "metricas": _safe_template_obj(kpis.get("metricas", {})),
        "metricas_fmt": _safe_template_obj(kpis.get("metricas_fmt", {})),
        "inversor": _safe_template_obj(kpis.get("inversor", {})),
        "inversor_fmt": _safe_template_obj(kpis.get("inversor_fmt", {})),
        "reparto": _safe_template_obj(kpis.get("reparto", {})),
        "reparto_fmt": _safe_template_obj(kpis.get("reparto_fmt", {})),
        "resultado": _safe_template_obj(kpis.get("resultado", {})),
        "texto": _safe_template_obj(kpis.get("texto", {})),
        "comite": _safe_template_obj(comite),
        "snapshot": _safe_template_obj(snapshot),
    }

    return render(request, "core/pdf_estudio_rentabilidad.html", ctx)
@csrf_exempt
def guardar_proyecto(request, proyecto_id):
    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "error": "Método no permitido"},
            status=405
        )

    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse(
            {"ok": False, "error": "Proyecto no encontrado"},
            status=404
        )

    try:
        data = json.loads(request.body or "{}")
        if not isinstance(data, dict):
            data = {}

        payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
        payload = _sanitize_for_json(payload)

        with transaction.atomic():
            extra = getattr(proyecto, "extra", None)
            if not isinstance(extra, dict):
                extra = {}

            extra["ultimo_guardado"] = {
                "ts": timezone.now().isoformat(),
                "payload": payload,
            }

            proyecto.extra = extra
            proyecto.save()

        return JsonResponse({"ok": True})

    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": str(e)},
            status=500
        )
