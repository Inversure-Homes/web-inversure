from __future__ import annotations

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import reverse
from django.db import transaction
from django.db.models import Sum, Count, Max, Prefetch
from django.utils import timezone
from django.conf import settings

from copy import deepcopy

import json
import os
import boto3
from decimal import Decimal
from datetime import date, datetime


from .models import Estudio, Proyecto
from .models import EstudioSnapshot, ProyectoSnapshot
from .models import GastoProyecto, IngresoProyecto, ChecklistItem
from .models import Cliente, Participacion, InversorPerfil, SolicitudParticipacion, ComunicacionInversor, DocumentoProyecto, DocumentoInversor

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


def _s3_presigned_url(key: str, expires_seconds: int = 300) -> str:
    if not key:
        return ""
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
    access_key = getattr(settings, "AWS_ACCESS_KEY_ID", None)
    secret_key = getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
    region = getattr(settings, "AWS_S3_REGION_NAME", None)
    if not bucket or not access_key or not secret_key:
        return ""
    try:
        client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
    except Exception:
        return ""



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


def _parse_decimal(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        s = value.strip().replace("€", "").replace("%", "").strip()
        if not s:
            return None
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        return Decimal(s)
    raise ValueError("decimal_invalido")


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        return date.fromisoformat(s)
    raise ValueError("fecha_invalida")


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


def _resultado_desde_metricas(metricas: dict) -> dict:
    if not isinstance(metricas, dict):
        metricas = {}
    beneficio_neto = _safe_float(
        metricas.get("beneficio_neto") or metricas.get("beneficio") or 0.0,
        0.0,
    )
    roi = _safe_float(metricas.get("roi") or metricas.get("roi_neto") or 0.0, 0.0)
    valor_adq = _safe_float(
        metricas.get("valor_adquisicion_total")
        or metricas.get("valor_adquisicion")
        or metricas.get("inversion_total")
        or 0.0,
        0.0,
    )
    ratio_euro = _safe_float(
        metricas.get("ratio_euro") or (beneficio_neto / valor_adq if valor_adq else 0.0),
        0.0,
    )
    precio_min_venta = _safe_float(
        metricas.get("precio_minimo_venta")
        or metricas.get("precio_breakeven")
        or metricas.get("breakeven")
        or metricas.get("break_even")
        or 0.0,
        0.0,
    )
    colchon = _safe_float(
        metricas.get("colchon_seguridad")
        or metricas.get("colchon")
        or 0.0,
        0.0,
    )
    margen = _safe_float(
        metricas.get("margen_neto")
        or metricas.get("margen")
        or 0.0,
        0.0,
    )
    ajuste_precio_venta = _safe_float(metricas.get("ajuste_precio_venta") or 0.0, 0.0)
    ajuste_gastos = _safe_float(metricas.get("ajuste_gastos") or 0.0, 0.0)

    viable = roi >= 15 and beneficio_neto >= 30000
    ajustada = roi >= 15 and 0 < beneficio_neto < 30000

    return {
        "beneficio_neto": beneficio_neto,
        "roi": roi,
        "valor_adquisicion": valor_adq,
        "ratio_euro": ratio_euro,
        "precio_minimo_venta": precio_min_venta,
        "colchon_seguridad": colchon,
        "margen_neto": margen,
        "ajuste_precio_venta": ajuste_precio_venta,
        "ajuste_gastos": ajuste_gastos,
        "viable": viable,
        "ajustada": ajustada,
    }


def _checklist_defaults():
    return [
        ("compra", "Pagar notaría"),
        ("compra", "Pagar registro"),
        ("compra", "Liquidar ITP"),
        ("post_compra", "Pagar deudas retenidas (IBI, comunidad)"),
        ("post_compra", "Cambiar contratos de suministros"),
        ("post_compra", "Cambiar cerradura"),
        ("post_compra", "Instalar alarma"),
        ("venta", "Tramitar plusvalía"),
        ("post_venta", "Baja o cambio de suministros"),
    ]


def _resultado_desde_memoria(proyecto: Proyecto, snapshot: dict) -> dict:
    gastos = list(GastoProyecto.objects.filter(proyecto=proyecto))
    ingresos = list(IngresoProyecto.objects.filter(proyecto=proyecto))

    def _sum_importes(items):
        total = Decimal("0")
        for item in items:
            if item is None:
                continue
            total += item
        return total

    ingresos_est = _sum_importes([i.importe for i in ingresos if i.estado == "estimado"])
    ingresos_real = _sum_importes([i.importe for i in ingresos if i.estado == "confirmado"])
    venta_est = _sum_importes(
        [i.importe for i in ingresos if i.estado == "estimado" and i.tipo == "venta"]
    )
    venta_real = _sum_importes(
        [i.importe for i in ingresos if i.estado == "confirmado" and i.tipo == "venta"]
    )
    gastos_est = _sum_importes([g.importe for g in gastos if g.estado == "estimado"])
    gastos_real = _sum_importes([g.importe for g in gastos if g.estado == "confirmado"])

    has_real = ingresos_real > 0 or gastos_real > 0
    ingresos_base = ingresos_real if ingresos_real > 0 else ingresos_est
    venta_base = venta_real if venta_real > 0 else venta_est
    gastos_venta_est = _sum_importes([g.importe for g in gastos if g.estado == "estimado" and g.categoria == "venta"])
    gastos_venta_real = _sum_importes([g.importe for g in gastos if g.estado == "confirmado" and g.categoria == "venta"])
    gastos_venta_base = gastos_venta_real if gastos_venta_real > 0 else gastos_venta_est
    gastos_base = gastos_real if gastos_real > 0 else gastos_est
    beneficio = ingresos_base - gastos_base

    cats_adq = {"adquisicion", "reforma", "seguridad", "operativos", "financieros", "legales", "otros"}
    gastos_adq_est = _sum_importes([g.importe for g in gastos if g.estado == "estimado" and g.categoria in cats_adq])
    gastos_adq_real = _sum_importes([g.importe for g in gastos if g.estado == "confirmado" and g.categoria in cats_adq])
    gastos_adq_base = gastos_adq_real if gastos_adq_real > 0 else gastos_adq_est

    snap_econ = snapshot.get("economico") if isinstance(snapshot.get("economico"), dict) else {}
    snap_kpis = snapshot.get("kpis") if isinstance(snapshot.get("kpis"), dict) else {}
    snap_met = snap_kpis.get("metricas") if isinstance(snap_kpis.get("metricas"), dict) else {}

    base_precio = (
        proyecto.precio_compra_inmueble
        or proyecto.precio_propiedad
        or _parse_decimal(snap_econ.get("precio_propiedad") or snap_econ.get("precio_escritura") or "")
        or _parse_decimal(snap_met.get("precio_propiedad") or snap_met.get("precio_escritura") or "")
        or Decimal("0")
    )

    valor_adquisicion = base_precio + gastos_adq_base
    venta_snapshot = _parse_decimal(
        snap_econ.get("venta_estimada")
        or snap_econ.get("valor_transmision")
        or snap_met.get("venta_estimada")
        or snap_met.get("valor_transmision")
        or ""
    ) or Decimal("0")
    if venta_base > 0:
        valor_transmision = venta_base - gastos_venta_base
    else:
        valor_transmision = venta_snapshot

    roi = float(beneficio / valor_adquisicion * 100) if valor_adquisicion > 0 else 0.0
    ratio_euro = float(beneficio / valor_adquisicion) if valor_adquisicion > 0 else 0.0
    margen_pct = float(beneficio / valor_transmision * 100) if valor_transmision > 0 else 0.0

    beneficio_objetivo = Decimal("30000")
    objetivo_roi = valor_adquisicion * Decimal("0.15")
    objetivo_beneficio = beneficio_objetivo if beneficio_objetivo > objetivo_roi else objetivo_roi
    min_valor_transmision = valor_adquisicion + objetivo_beneficio
    min_venta = min_valor_transmision + gastos_venta_base

    ajuste_precio_venta = float(max(min_valor_transmision - valor_transmision, Decimal("0"))) if valor_transmision > 0 else float(min_valor_transmision)

    costo_requerido_roi = valor_transmision / Decimal("1.15") if valor_transmision > 0 else Decimal("0")
    costo_requerido_benef = valor_transmision - beneficio_objetivo
    costo_requerido = min(costo_requerido_roi, costo_requerido_benef)
    if costo_requerido < 0:
        costo_requerido = Decimal("0")
    ajuste_gastos = float(max(valor_adquisicion - costo_requerido, Decimal("0"))) if valor_transmision > 0 else float(valor_adquisicion)

    colchon_seguridad = float(valor_transmision - valor_adquisicion - objetivo_beneficio) if valor_transmision > 0 else 0.0

    return {
        "beneficio_neto": float(beneficio),
        "roi": roi,
        "valor_adquisicion": float(valor_adquisicion),
        "ratio_euro": ratio_euro,
        "precio_minimo_venta": float(min_venta),
        "colchon_seguridad": colchon_seguridad,
        "margen_neto": margen_pct,
        "ajuste_precio_venta": ajuste_precio_venta,
        "ajuste_gastos": ajuste_gastos,
        "origen_memoria": True,
        "base_memoria_real": bool(has_real),
    }


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
    proyectos_ids = list(proyectos.values_list("id", flat=True))

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

    gastos_reales_map = {}
    if proyectos_ids:
        for row in (
            GastoProyecto.objects.filter(proyecto_id__in=proyectos_ids, estado="confirmado")
            .values("proyecto_id")
            .annotate(total=Sum("importe"))
        ):
            gastos_reales_map[row["proyecto_id"]] = _as_float(row.get("total"), 0.0)

    # Enriquecer cada proyecto con métricas heredadas (sin exigir cambios en el template)
    for p in proyectos:
        snap = _get_snapshot(p)
        economico = snap.get("economico") if isinstance(snap.get("economico"), dict) else {}
        inversor = snap.get("inversor") if isinstance(snap.get("inversor"), dict) else {}
        kpis = snap.get("kpis") if isinstance(snap.get("kpis"), dict) else {}
        metricas = kpis.get("metricas") if isinstance(kpis.get("metricas"), dict) else {}

        # Capital objetivo (lo que realmente se invierte)
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
        gastos_reales = gastos_reales_map.get(p.id, 0.0)
        if gastos_reales > 0:
            capital_objetivo = gastos_reales

        # Capital captado: suma de participaciones reales del proyecto
        capital_captado = Participacion.objects.filter(
            proyecto=p, estado="confirmada"
        ).aggregate(total=Sum("importe_invertido")).get("total") or 0
        capital_captado = _as_float(capital_captado, 0.0)

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


def clientes(request):
    clientes_qs = Cliente.objects.all().order_by("nombre")
    return render(request, "core/clientes.html", {"clientes": clientes_qs})


def clientes_form(request):
    if request.method == "POST":
        data = request.POST
        try:
            kwargs = {
                "tipo_persona": data.get("tipo_persona") or "F",
                "nombre": (data.get("nombre") or "").strip(),
                "dni_cif": (data.get("dni_cif") or "").strip(),
                "email": (data.get("email") or "").strip() or None,
                "telefono": (data.get("telefono") or "").strip() or None,
                "iban": (data.get("iban") or "").strip() or None,
                "observaciones": (data.get("observaciones") or "").strip() or None,
                "direccion_postal": (data.get("direccion") or "").strip() or None,
                "cuota_abonada": bool(data.get("cuota_pagada")),
                "presente_en_comunidad": bool(data.get("en_comunidad")),
            }
            fecha = _parse_date(data.get("fecha_alta"))
            if fecha:
                kwargs["fecha_introduccion"] = fecha
            Cliente.objects.create(**kwargs)
            messages.success(request, "Cliente creado correctamente.")
            return redirect("core:clientes")
        except Exception as e:
            messages.error(request, f"No se pudo crear el cliente: {e}")

    return render(request, "core/clientes_form.html", {"titulo": "Nuevo cliente"})


def cliente_edit(request, cliente_id: int):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.method == "POST":
        data = request.POST
        try:
            cliente.tipo_persona = data.get("tipo_persona") or cliente.tipo_persona
            cliente.nombre = (data.get("nombre") or "").strip()
            cliente.dni_cif = (data.get("dni_cif") or "").strip()
            cliente.email = (data.get("email") or "").strip() or None
            cliente.telefono = (data.get("telefono") or "").strip() or None
            cliente.iban = (data.get("iban") or "").strip() or None
            cliente.observaciones = (data.get("observaciones") or "").strip() or None
            if data.get("fecha_alta"):
                cliente.fecha_introduccion = _parse_date(data.get("fecha_alta")) or cliente.fecha_introduccion
            cliente.direccion_postal = (data.get("direccion") or "").strip() or None
            cliente.cuota_abonada = bool(data.get("cuota_pagada"))
            cliente.presente_en_comunidad = bool(data.get("en_comunidad"))
            cliente.save()
            messages.success(request, "Cliente actualizado correctamente.")
            return redirect("core:clientes")
        except Exception as e:
            messages.error(request, f"No se pudo actualizar el cliente: {e}")

    return render(request, "core/clientes_form.html", {"titulo": "Editar cliente", "cliente": cliente})


def inversores_list(request):
    participaciones_qs = Participacion.objects.select_related("proyecto").filter(
        estado="confirmada"
    ).order_by("-creado")
    clientes_base = Cliente.objects.all().order_by("nombre").prefetch_related(
        Prefetch("participaciones", queryset=participaciones_qs, to_attr="participaciones_confirmadas")
    )
    perfiles_map = {}
    for cliente in clientes_base:
        perfil, _ = InversorPerfil.objects.get_or_create(cliente=cliente)
        perfiles_map[cliente.id] = perfil

    perfiles_ids = [p.id for p in perfiles_map.values()]
    cliente_ids = list(clientes_base.values_list("id", flat=True))

    totales = {
        row["cliente_id"]: row
        for row in (
            Participacion.objects.filter(cliente_id__in=cliente_ids, estado="confirmada")
            .values("cliente_id")
            .annotate(total=Sum("importe_invertido"), num=Count("id"))
        )
    }

    estados_cerrados = {"cerrado", "cerrado_positivo", "cerrado_negativo", "finalizado", "descartado", "vendido"}
    activos = {
        row["cliente_id"]: row["num"]
        for row in (
            Participacion.objects.filter(cliente_id__in=cliente_ids, estado="confirmada")
            .exclude(proyecto__estado__in=estados_cerrados)
            .values("cliente_id")
            .annotate(num=Count("proyecto", distinct=True))
        )
    }

    solicitudes_pend = {
        row["inversor_id"]: row["total"]
        for row in (
            SolicitudParticipacion.objects.filter(inversor_id__in=perfiles_ids, estado="pendiente")
            .values("inversor_id")
            .annotate(total=Count("id"))
        )
    }

    comunicaciones = {
        row["inversor_id"]: row
        for row in (
            ComunicacionInversor.objects.filter(inversor_id__in=perfiles_ids)
            .values("inversor_id")
            .annotate(total=Count("id"), ultima=Max("creado"))
        )
    }

    docs_por_inversor = {}
    if perfiles_ids:
        for d in DocumentoInversor.objects.filter(inversor_id__in=perfiles_ids).order_by("-creado"):
            signed = _s3_presigned_url(d.archivo.name)
            setattr(d, "signed_url", signed or "")
            docs_por_inversor.setdefault(d.inversor_id, []).append(d)

    inversores = []
    total_invertido = 0
    total_participaciones = 0
    total_pendientes = 0

    for cliente in clientes_base:
        perfil = perfiles_map.get(cliente.id)
        if not perfil:
            continue
        total_row = totales.get(cliente.id, {})
        total_cli = float(total_row.get("total") or 0)
        num_part = int(total_row.get("num") or 0)
        total_invertido += total_cli
        total_participaciones += num_part

        pend = int(solicitudes_pend.get(perfil.id, 0))
        total_pendientes += pend

        comm = comunicaciones.get(perfil.id, {})
        ultima_com = comm.get("ultima")
        total_com = int(comm.get("total") or 0)

        participaciones = getattr(cliente, "participaciones_confirmadas", []) or []
        preview = participaciones[:3]

        inversores.append(
            {
                "perfil": perfil,
                "cliente": cliente,
                "total_invertido": total_cli,
                "num_participaciones": num_part,
                "proyectos_activos": int(activos.get(cliente.id, 0)),
                "solicitudes_pendientes": pend,
                "ultima_comunicacion": ultima_com,
                "total_comunicaciones": total_com,
                "participaciones_preview": preview,
                "documentos": docs_por_inversor.get(perfil.id, []),
            }
        )

    ctx = {
        "inversores": inversores,
        "total_inversores": len(inversores),
        "total_invertido": total_invertido,
        "total_participaciones": total_participaciones,
        "total_pendientes": total_pendientes,
        "proyectos": Proyecto.objects.order_by("-id"),
    }
    return render(request, "core/inversores.html", ctx)


def clientes_import(request):
    if request.method == "POST" and request.FILES.get("archivo"):
        archivo = request.FILES["archivo"]
        try:
            import pandas as pd
        except Exception:
            messages.error(request, "Falta la dependencia pandas para importar el Excel.")
            return redirect("core:clientes_import")

        try:
            df = pd.read_excel(archivo, sheet_name="Datos Participes", header=6)
        except Exception as e:
            messages.error(request, f"No se pudo leer la hoja 'Datos Participes': {e}")
            return redirect("core:clientes_import")

        # Limpiar columnas (eliminar 'Unnamed' y espacios)
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, ~df.columns.str.contains("^Unnamed", case=False, na=False)]

        def _to_str(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            return str(val).strip()

        def _to_bool(val):
            s = _to_str(val).lower()
            return s in {"ok", "si", "sí", "true", "1", "x"}

        creados = 0
        omitidos = 0

        for _, row in df.iterrows():
            nombre = _to_str(row.get("Nombre"))
            dni_cif = _to_str(row.get("DNI"))
            if not nombre or not dni_cif:
                omitidos += 1
                continue

            if Cliente.objects.filter(dni_cif=dni_cif).exists():
                omitidos += 1
                continue

            fecha = None
            raw_fecha = row.get("Fecha incorporación")
            if raw_fecha is not None and not (isinstance(raw_fecha, float) and pd.isna(raw_fecha)):
                try:
                    fecha = pd.to_datetime(raw_fecha).date()
                except Exception:
                    fecha = None

            Cliente.objects.create(
                tipo_persona="F",
                nombre=nombre,
                dni_cif=dni_cif,
                email=_to_str(row.get("Correo")) or None,
                telefono=_to_str(row.get("Contacto")) or None,
                iban=_to_str(row.get("Cuenta")) or None,
                direccion_postal=_to_str(row.get("Dirección")) or None,
                presente_en_comunidad=_to_bool(row.get("Comunidad Whatsapp")),
                fecha_introduccion=fecha or timezone.now().date(),
            )
            creados += 1

        messages.success(
            request,
            f"Importación finalizada: {creados} clientes creados, {omitidos} filas omitidas."
        )
        return redirect("core:clientes")

    return render(request, "core/clientes_import.html")


def cliente_inversor_link(request, cliente_id: int):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    perfil, _ = InversorPerfil.objects.get_or_create(cliente=cliente)
    return render(request, "core/inversor_link.html", {"cliente": cliente, "perfil": perfil})


def _build_inversor_portal_context(perfil: InversorPerfil, internal_view: bool) -> dict:
    participaciones = Participacion.objects.filter(cliente=perfil.cliente).select_related("proyecto").order_by("-creado")
    comunicaciones = ComunicacionInversor.objects.filter(inversor=perfil)
    proyectos_abiertos = Proyecto.objects.filter(estado__in=["activo", "captacion"]).order_by("-id")
    solicitudes = SolicitudParticipacion.objects.filter(inversor=perfil).select_related("proyecto")

    total_invertido = participaciones.filter(estado="confirmada").aggregate(total=Sum("importe_invertido")).get("total") or 0
    total_invertido = float(total_invertido or 0)

    participaciones_conf = participaciones.filter(estado="confirmada")
    proyectos_ids = list(participaciones_conf.values_list("proyecto_id", flat=True))

    def _get_snapshot(p: Proyecto) -> dict:
        snap = getattr(p, "snapshot_datos", None)
        if not isinstance(snap, dict):
            snap = {}
        if snap:
            base = dict(snap)
        else:
            base = {}

        extra = getattr(p, "extra", None)
        overlay = {}
        if isinstance(extra, dict):
            ultimo = extra.get("ultimo_guardado")
            if isinstance(ultimo, dict) and isinstance(ultimo.get("payload"), dict):
                overlay = ultimo.get("payload") or {}
            elif isinstance(extra.get("payload"), dict):
                overlay = extra.get("payload") or {}

        if overlay:
            base = _deep_merge_dict(base, overlay)
        if base:
            return base
        osnap = getattr(p, "origen_snapshot", None)
        if osnap is not None:
            datos = getattr(osnap, "datos", None)
            if isinstance(datos, dict) and datos:
                return _deep_merge_dict(dict(datos), overlay)
        oest = getattr(p, "origen_estudio", None)
        if oest is not None:
            datos = getattr(oest, "datos", None)
            if isinstance(datos, dict) and datos:
                return _deep_merge_dict(dict(datos), overlay)
        return overlay or {}

    totales_proyecto = {}
    if proyectos_ids:
        for row in (
            Participacion.objects.filter(proyecto_id__in=proyectos_ids, estado="confirmada")
            .values("proyecto_id")
            .annotate(total=Sum("importe_invertido"))
        ):
            totales_proyecto[row["proyecto_id"]] = float(row.get("total") or 0)

    beneficios_por_proyecto = []
    total_beneficio = 0.0
    total_retencion = 0.0
    beneficio_chart = []
    for p in participaciones_conf:
        proyecto = p.proyecto
        if not proyecto:
            continue
        total_proj = totales_proyecto.get(proyecto.id, 0.0)
        if total_proj <= 0:
            continue
        snap = _get_snapshot(proyecto)
        resultado = _resultado_desde_memoria(proyecto, snap)
        beneficio_bruto = float(resultado.get("beneficio_neto") or 0.0)

        inv_sec = snap.get("inversor") if isinstance(snap.get("inversor"), dict) else {}
        comision_pct = _safe_float(
            inv_sec.get("comision_inversure_pct")
            or inv_sec.get("inversure_comision_pct")
            or inv_sec.get("comision_pct")
            or snap.get("comision_inversure_pct")
            or snap.get("inversure_comision_pct")
            or snap.get("comision_pct")
            or 0.0,
            0.0,
        )
        if comision_pct < 0:
            comision_pct = 0.0
        if comision_pct > 100:
            comision_pct = 100.0

        comision_eur = beneficio_bruto * (comision_pct / 100.0) if beneficio_bruto else 0.0
        beneficio_neto_inversor_total = beneficio_bruto - comision_eur

        proj_extra = proyecto.extra if isinstance(proyecto.extra, dict) else {}
        proj_override = proj_extra.get("beneficio_operacion_override")
        if isinstance(proj_override, dict):
            override_bruto = proj_override.get("beneficio_bruto")
            override_comision = proj_override.get("comision_eur")
            override_neto = proj_override.get("beneficio_neto_total")
            if override_bruto not in (None, ""):
                beneficio_bruto = _safe_float(override_bruto, beneficio_bruto)
            if override_comision not in (None, ""):
                comision_eur = _safe_float(override_comision, comision_eur)
            if override_neto not in (None, ""):
                beneficio_neto_inversor_total = _safe_float(override_neto, beneficio_neto_inversor_total)
            elif override_bruto not in (None, "") or override_comision not in (None, ""):
                beneficio_neto_inversor_total = beneficio_bruto - comision_eur

        ratio_part = float(p.importe_invertido or 0) / total_proj if total_proj > 0 else 0.0
        beneficio_inversor = beneficio_neto_inversor_total * ratio_part
        override_val = float(p.beneficio_neto_override) if p.beneficio_neto_override is not None else None
        override_data = p.beneficio_override_data if isinstance(p.beneficio_override_data, dict) else {}
        if override_data.get("beneficio_inversor") not in (None, ""):
            beneficio_inversor = _safe_float(override_data.get("beneficio_inversor"), beneficio_inversor)
        elif override_val is not None:
            beneficio_inversor = override_val
        retencion = beneficio_inversor * 0.19
        if override_data.get("retencion") not in (None, ""):
            retencion = _safe_float(override_data.get("retencion"), retencion)
        neto_cobrar = beneficio_inversor - retencion
        if override_data.get("neto_cobrar") not in (None, ""):
            neto_cobrar = _safe_float(override_data.get("neto_cobrar"), neto_cobrar)
        total_beneficio += beneficio_inversor
        total_retencion += retencion

        beneficios_por_proyecto.append(
            {
                "proyecto": proyecto,
                "beneficio_bruto": beneficio_bruto,
                "comision_eur": comision_eur,
                "beneficio_neto_total": beneficio_neto_inversor_total,
                "beneficio_inversor": beneficio_inversor,
                "beneficio_override": override_data.get("beneficio_inversor") if override_data.get("beneficio_inversor") not in (None, "") else override_val,
                "retencion": retencion,
                "neto_cobrar": neto_cobrar,
                "participacion_pct": ratio_part * 100.0,
                "participacion_id": p.id,
            }
        )

        fecha_ref = getattr(proyecto, "fecha", None) or getattr(p, "creado", None)
        if isinstance(fecha_ref, datetime):
            fecha_ref = fecha_ref.date().isoformat()
        elif isinstance(fecha_ref, date):
            fecha_ref = fecha_ref.isoformat()
        elif fecha_ref is not None:
            fecha_ref = str(fecha_ref)
        beneficio_chart.append(
            {
                "label": proyecto.nombre,
                "fecha": fecha_ref or "",
                "beneficio": beneficio_inversor,
                "inversion": float(p.importe_invertido or 0),
                "pct": (beneficio_inversor / float(p.importe_invertido or 0) * 100.0) if float(p.importe_invertido or 0) > 0 else 0.0,
            }
        )

    documentos_por_proyecto = []
    if proyectos_ids:
        docs = DocumentoProyecto.objects.filter(proyecto_id__in=proyectos_ids).exclude(categoria="fotografias")
        docs = docs.select_related("proyecto").order_by("-creado")
        docs_map = {}
        for d in docs:
            signed = _s3_presigned_url(d.archivo.name)
            setattr(d, "signed_url", signed or "")
            docs_map.setdefault(d.proyecto_id, {"proyecto": d.proyecto, "docs": []})["docs"].append(d)
        documentos_por_proyecto = list(docs_map.values())

    documentos_personales = []
    for d in DocumentoInversor.objects.filter(inversor=perfil).order_by("-creado"):
        signed = _s3_presigned_url(d.archivo.name)
        setattr(d, "signed_url", signed or "")
        documentos_personales.append(d)

    return {
        "perfil": perfil,
        "participaciones": participaciones,
        "comunicaciones": comunicaciones,
        "proyectos_abiertos": proyectos_abiertos,
        "solicitudes": solicitudes,
        "total_invertido": total_invertido,
        "beneficios_por_proyecto": beneficios_por_proyecto,
        "total_beneficio": total_beneficio,
        "total_retencion": total_retencion,
        "total_neto_cobrar": total_beneficio - total_retencion,
        "beneficio_chart": beneficio_chart,
        "documentos_por_proyecto": documentos_por_proyecto,
        "documentos_personales": documentos_personales,
        "logo_url": reverse("core:inversores_list"),
        "internal_view": internal_view,
    }


def inversor_portal(request, token: str):
    perfil = get_object_or_404(InversorPerfil, token=token, activo=True)
    ctx = _build_inversor_portal_context(perfil, internal_view=False)
    return render(request, "core/inversor_portal.html", ctx)


def inversor_portal_admin(request, perfil_id: int):
    perfil = get_object_or_404(InversorPerfil, id=perfil_id)
    ctx = _build_inversor_portal_context(perfil, internal_view=True)
    return render(request, "core/inversor_portal.html", ctx)


def inversor_documento_upload(request, perfil_id: int):
    if request.method != "POST":
        return redirect("core:inversores_list")
    perfil = get_object_or_404(InversorPerfil, id=perfil_id)
    titulo = (request.POST.get("doc_titulo") or "").strip()
    categoria = (request.POST.get("doc_categoria") or "otros").strip()
    archivo = request.FILES.get("doc_archivo")
    if not titulo or not archivo:
        messages.error(request, "Faltan datos para subir el documento.")
        return redirect("core:inversores_list")
    DocumentoInversor.objects.create(
        inversor=perfil,
        titulo=titulo,
        categoria=categoria,
        archivo=archivo,
    )
    messages.success(request, "Documento del inversor subido correctamente.")
    return redirect("core:inversores_list")


def inversor_documento_borrar(request, perfil_id: int, doc_id: int):
    if request.method != "POST":
        return redirect("core:inversores_list")
    perfil = get_object_or_404(InversorPerfil, id=perfil_id)
    documento = get_object_or_404(DocumentoInversor, id=doc_id, inversor=perfil)
    documento.delete()
    messages.success(request, "Documento del inversor eliminado correctamente.")
    return redirect("core:inversores_list")


def inversor_beneficio_update(request, token: str, participacion_id: int):
    perfil = get_object_or_404(InversorPerfil, token=token, activo=True)
    if request.method != "POST":
        return redirect("core:inversor_portal", token=token)

    participacion = get_object_or_404(Participacion, id=participacion_id, cliente=perfil.cliente)
    proyecto = participacion.proyecto

    def _get_decimal(name: str):
        if name not in request.POST:
            return None, False
        raw = (request.POST.get(name) or "").strip()
        if raw == "":
            return None, True
        try:
            return _parse_decimal(raw), True
        except Exception:
            return None, True

    # Compatibilidad: formulario antiguo
    legacy_val, legacy_present = _get_decimal("beneficio_neto")
    if legacy_present and set(request.POST.keys()).issubset({"csrfmiddlewaretoken", "beneficio_neto"}):
        if legacy_val is None and (request.POST.get("beneficio_neto") or "").strip() == "":
            participacion.beneficio_neto_override = None
            participacion.save(update_fields=["beneficio_neto_override"])
            messages.success(request, "Beneficio actualizado correctamente.")
            return redirect("core:inversor_portal", token=token)
        if legacy_val is None:
            messages.error(request, "El beneficio indicado no es válido.")
            return redirect("core:inversor_portal", token=token)
        participacion.beneficio_neto_override = legacy_val
        participacion.save(update_fields=["beneficio_neto_override"])
        messages.success(request, "Beneficio actualizado correctamente.")
        return redirect("core:inversor_portal", token=token)

    proj_keys = ("beneficio_bruto", "comision_eur", "beneficio_neto_total")
    inv_keys = ("beneficio_inversor", "retencion", "neto_cobrar")

    extra = proyecto.extra if isinstance(proyecto.extra, dict) else {}
    proj_override = extra.get("beneficio_operacion_override")
    if not isinstance(proj_override, dict):
        proj_override = {}

    updated_proj = False
    for key in proj_keys:
        value, present = _get_decimal(key)
        if not present:
            continue
        if value is None:
            proj_override.pop(key, None)
        else:
            proj_override[key] = float(value)
        updated_proj = True

    if updated_proj:
        if proj_override:
            extra["beneficio_operacion_override"] = proj_override
        else:
            extra.pop("beneficio_operacion_override", None)
        proyecto.extra = extra
        proyecto.save(update_fields=["extra"])

    override_data = participacion.beneficio_override_data if isinstance(participacion.beneficio_override_data, dict) else {}
    updated_inv = False
    for key in inv_keys:
        value, present = _get_decimal(key)
        if not present:
            continue
        if value is None:
            override_data.pop(key, None)
        else:
            override_data[key] = float(value)
        updated_inv = True

    if updated_inv:
        participacion.beneficio_override_data = override_data
        beneficio_override_val = override_data.get("beneficio_inversor")
        if beneficio_override_val is None and "beneficio_inversor" not in override_data:
            participacion.beneficio_neto_override = None
        elif beneficio_override_val is not None:
            participacion.beneficio_neto_override = beneficio_override_val
        participacion.save(update_fields=["beneficio_override_data", "beneficio_neto_override"])

    messages.success(request, "Beneficio actualizado correctamente.")
    return redirect("core:inversor_portal", token=token)


def inversor_solicitar(request, token: str, proyecto_id: int):
    perfil = get_object_or_404(InversorPerfil, token=token, activo=True)
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)
    if request.method != "POST":
        return redirect("core:inversor_portal", token=token)

    importe = _parse_decimal(request.POST.get("importe"))
    comentario = (request.POST.get("comentario") or "").strip()
    if importe is None:
        messages.error(request, "Indica un importe válido.")
        return redirect("core:inversor_portal", token=token)

    SolicitudParticipacion.objects.create(
        proyecto=proyecto,
        inversor=perfil,
        importe_solicitado=importe,
        comentario=comentario or None,
    )
    messages.success(request, "Solicitud enviada correctamente.")
    return redirect("core:inversor_portal", token=token)


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
        "meses",
        "financiacion_pct",
        "responsable",
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
        try:
            if not getattr(proyecto_obj, "responsable", "") and overlay.get("responsable"):
                setattr(proyecto_obj, "responsable", overlay.get("responsable"))
        except Exception:
            pass
        try:
            if overlay.get("proyecto", {}).get("estado") and not getattr(proyecto_obj, "estado", ""):
                proyecto_obj.estado = overlay["proyecto"]["estado"]
            if overlay.get("proyecto", {}).get("fecha") and not getattr(proyecto_obj, "fecha", None):
                proyecto_obj.fecha = _parse_date(overlay["proyecto"]["fecha"])
            if overlay.get("proyecto", {}).get("responsable") and not getattr(proyecto_obj, "responsable", ""):
                setattr(proyecto_obj, "responsable", overlay["proyecto"]["responsable"])
        except Exception:
            pass
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

    # --- Resultado de inversión para dashboard / vista proyecto ---
    resultado = {}
    try:
        snap_result = snapshot.get("resultado") if isinstance(snapshot.get("resultado"), dict) else {}
        calc = _metricas_desde_estudio(Estudio(datos=snapshot))
        metricas_calc = calc.get("metricas", {}) if isinstance(calc.get("metricas"), dict) else {}
        resultado_calc = _resultado_desde_metricas(metricas_calc)
        resultado = dict(resultado_calc)
        try:
            resultado_memoria = _resultado_desde_memoria(proyecto_obj, snapshot)
            for k, v in resultado_memoria.items():
                if v not in (None, ""):
                    resultado[k] = v
        except Exception:
            pass
        if isinstance(snap_result, dict):
            for k, v in snap_result.items():
                if v not in (None, "", []):
                    resultado[k] = v
    except Exception:
        resultado = snapshot.get("resultado") if isinstance(snapshot.get("resultado"), dict) else {}

    inv_calc = {}
    try:
        inv_calc = calc.get("inversor") if isinstance(calc.get("inversor"), dict) else {}
    except Exception:
        inv_calc = {}
    try:
        inv_snap = snapshot.get("inversor") if isinstance(snapshot.get("inversor"), dict) else {}
    except Exception:
        inv_snap = {}
    if isinstance(inv_snap, dict) and isinstance(inv_calc, dict):
        for k, v in inv_snap.items():
            if k not in inv_calc or inv_calc.get(k) in (None, ""):
                inv_calc[k] = v

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

        # Capital captado: suma de participaciones confirmadas (si existe el módulo)
        capital_captado_db = Participacion.objects.filter(
            proyecto=proyecto_obj, estado="confirmada"
        ).aggregate(total=Sum("importe_invertido")).get("total") or 0
        capital_captado_db = _safe_float(capital_captado_db, 0.0)

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
        if capital_captado_db > 0:
            capital_captado = capital_captado_db

        # Fallback si no hay objetivo en snapshot: usar resultado o valores del proyecto
        if capital_objetivo <= 0:
            capital_objetivo = _safe_float(
                resultado.get("valor_adquisicion")
                or getattr(proyecto_obj, "precio_compra_inmueble", None)
                or getattr(proyecto_obj, "precio_propiedad", None)
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
        pct_restante = max(0.0, 100.0 - pct_captado)

        captacion_ctx = SafeAccessDict({
            "capital_objetivo": capital_objetivo,
            "capital_captado": capital_captado,
            "pct_captado": pct_captado,
            "restante": restante,
            "pct_restante": pct_restante,
            "capital_objetivo_fmt": _fmt_eur(capital_objetivo),
            "capital_captado_fmt": _fmt_eur(capital_captado),
            "restante_fmt": _fmt_eur(restante),
            "pct_captado_fmt": _fmt_pct(pct_captado),
            "pct_restante_fmt": _fmt_pct(pct_restante),
        })
    except Exception:
        captacion_ctx = SafeAccessDict({
            "capital_objetivo": 0.0,
            "capital_captado": 0.0,
            "pct_captado": 0.0,
            "restante": 0.0,
            "pct_restante": 0.0,
            "capital_objetivo_fmt": _fmt_eur(0.0),
            "capital_captado_fmt": _fmt_eur(0.0),
            "restante_fmt": _fmt_eur(0.0),
            "pct_captado_fmt": _fmt_pct(0.0),
            "pct_restante_fmt": _fmt_pct(0.0),
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
        "inversor": _safe_template_obj(inv_calc) if isinstance(inv_calc, dict) else SafeAccessDict(),
        "inv": _safe_template_obj(inv_calc) if isinstance(inv_calc, dict) else SafeAccessDict(),
        "comite": _safe_template_obj(snapshot.get("comite", {})) if isinstance(snapshot.get("comite"), dict) else SafeAccessDict(),
        "kpis": _safe_template_obj(snapshot.get("kpis", {})) if isinstance(snapshot.get("kpis"), dict) else SafeAccessDict(),
        "metricas": _safe_template_obj(metricas_raw) if isinstance(metricas_raw, dict) else SafeAccessDict(),
        "resultado": _safe_template_obj(resultado) if isinstance(resultado, dict) else SafeAccessDict(),
        "captacion": captacion_ctx,
        "capital_objetivo": captacion_ctx.get("capital_objetivo"),
        "capital_captado": captacion_ctx.get("capital_captado"),
        "pct_captado": captacion_ctx.get("pct_captado"),
    }

    try:
        if not ChecklistItem.objects.filter(proyecto=proyecto_obj).exists():
            for fase, titulo in _checklist_defaults():
                ChecklistItem.objects.create(
                    proyecto=proyecto_obj,
                    fase=fase,
                    titulo=titulo,
                    estado="pendiente",
                )
        ctx["checklist_items"] = ChecklistItem.objects.filter(proyecto=proyecto_obj).order_by("fase", "fecha_objetivo", "id")
    except Exception:
        ctx["checklist_items"] = []
    try:
        ctx["clientes"] = Cliente.objects.all().order_by("nombre")
    except Exception:
        ctx["clientes"] = []
    try:
        ctx["participaciones"] = Participacion.objects.filter(proyecto=proyecto_obj).select_related("cliente").order_by("-id")
    except Exception:
        ctx["participaciones"] = []
    try:
        documentos = list(DocumentoProyecto.objects.filter(proyecto=proyecto_obj).order_by("-creado", "-id"))
        use_signed = False
        try:
            use_signed = bool(getattr(settings, "AWS_STORAGE_BUCKET_NAME", None))
        except Exception:
            use_signed = False
        if use_signed:
            for doc in documentos:
                try:
                    key = getattr(doc.archivo, "name", "") or ""
                    signed = _s3_presigned_url(key)
                    if signed:
                        doc.signed_url = signed
                except Exception:
                    pass
        categorias_map = {}
        for doc in documentos:
            cat = getattr(doc, "categoria", "otros") or "otros"
            categorias_map.setdefault(cat, []).append(doc)
        ctx["documentos_por_categoria"] = categorias_map
        ctx["documentos"] = documentos
        principal = next((d for d in documentos if d.categoria == "fotografias" and d.es_principal), None)
        if principal is None:
            principal = next((d for d in documentos if d.categoria == "fotografias"), None)
        if principal:
            try:
                ctx["foto_principal_url"] = principal.signed_url if hasattr(principal, "signed_url") and principal.signed_url else principal.archivo.url
                ctx["foto_principal_titulo"] = principal.titulo
            except Exception:
                pass
    except Exception:
        ctx["documentos"] = []

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

        # Normalizar decisiones de comité si llegan con claves alternativas
        if isinstance(datos.get("comite"), dict):
            comite_sec = datos["comite"]
            if comite_sec.get("decision") in (None, "") and comite_sec.get("decision_estado") not in (None, ""):
                comite_sec["decision"] = comite_sec.get("decision_estado")
            if comite_sec.get("observaciones") in (None, ""):
                if comite_sec.get("comentario") not in (None, ""):
                    comite_sec["observaciones"] = comite_sec.get("comentario")
                elif comite_sec.get("resumen_ejecutivo") not in (None, ""):
                    comite_sec["observaciones"] = comite_sec.get("resumen_ejecutivo")
            if comite_sec.get("resumen_ejecutivo") in (None, "") and comite_sec.get("resumen_ejecutivo_comite") not in (None, ""):
                comite_sec["resumen_ejecutivo"] = comite_sec.get("resumen_ejecutivo_comite")

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
    if isinstance(payload.get("payload"), dict):
        payload = payload.get("payload") or {}

    update_fields = []

    payload_proyecto = payload.get("proyecto") if isinstance(payload.get("proyecto"), dict) else {}

    # Permitir que el payload incluya un nombre editable (si se quiere persistir)
    nombre = (
        payload.get("nombre")
        or payload.get("nombre_proyecto")
        or payload_proyecto.get("nombre")
        or payload_proyecto.get("nombre_proyecto")
        or ""
    ).strip()
    if nombre:
        try:
            proyecto_obj.nombre = nombre
            update_fields.append("nombre")
        except Exception:
            # si el campo no existe en el modelo, ignoramos
            pass

    # Estado, fecha y responsable (cabecera de proyecto)
    estado = (payload.get("estado") or payload_proyecto.get("estado") or "").strip()
    if estado:
        try:
            proyecto_obj.estado = estado
            update_fields.append("estado")
        except Exception:
            pass

    fecha_raw = payload.get("fecha") or payload_proyecto.get("fecha")
    if fecha_raw not in (None, ""):
        try:
            proyecto_obj.fecha = _parse_date(fecha_raw)
            update_fields.append("fecha")
        except Exception:
            pass

    responsable = (payload.get("responsable") or payload_proyecto.get("responsable") or "").strip()
    if responsable:
        try:
            setattr(proyecto_obj, "responsable", responsable)
            update_fields.append("responsable")
        except Exception:
            # si el campo no existe en el modelo, lo guardamos en extra
            pass

    codigo_raw = payload.get("codigo_proyecto") or payload_proyecto.get("codigo_proyecto")
    if codigo_raw not in (None, ""):
        try:
            if isinstance(codigo_raw, str):
                codigo_raw = codigo_raw.strip()
            codigo_val = int(float(codigo_raw))
            if codigo_val >= 0:
                proyecto_obj.codigo_proyecto = codigo_val
                update_fields.append("codigo_proyecto")
        except Exception:
            pass

    if update_fields:
        try:
            proyecto_obj.save(update_fields=list(set(update_fields)))
        except Exception:
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
        if responsable:
            extra["responsable"] = responsable
        if estado:
            extra["estado"] = estado
        if fecha_raw not in (None, ""):
            extra["fecha"] = fecha_raw
        if codigo_raw not in (None, ""):
            extra["codigo_proyecto"] = codigo_raw

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
        datos_raw = estudio.datos or {}
        if not isinstance(datos_raw, dict):
            datos_raw = {}
        inmueble_raw = datos_raw.get("inmueble") if isinstance(datos_raw.get("inmueble"), dict) else {}
        proyecto_raw = datos_raw.get("proyecto") if isinstance(datos_raw.get("proyecto"), dict) else {}

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
        nombre_estudio = (
            estudio.nombre
            or datos_raw.get("nombre_proyecto")
            or datos_raw.get("nombre")
            or proyecto_raw.get("nombre")
            or proyecto_raw.get("nombre_proyecto")
            or ""
        )
        direccion_estudio = (
            estudio.direccion
            or datos_raw.get("direccion")
            or inmueble_raw.get("direccion")
            or inmueble_raw.get("direccion_inmueble")
            or ""
        )
        ref_catastral_estudio = (
            estudio.ref_catastral
            or datos_raw.get("ref_catastral")
            or inmueble_raw.get("ref_catastral")
            or ""
        )
        valor_referencia_estudio = (
            estudio.valor_referencia
            if estudio.valor_referencia is not None
            else inmueble_raw.get("valor_referencia")
            or datos_raw.get("valor_referencia")
        )

        if _has_field(Proyecto, "nombre"):
            proyecto_kwargs["nombre"] = nombre_estudio
        if _has_field(Proyecto, "direccion"):
            proyecto_kwargs["direccion"] = direccion_estudio
        if _has_field(Proyecto, "ref_catastral"):
            proyecto_kwargs["ref_catastral"] = ref_catastral_estudio
        if _has_field(Proyecto, "valor_referencia"):
            proyecto_kwargs["valor_referencia"] = valor_referencia_estudio
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


def pdf_memoria_economica(request, proyecto_id: int):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)
    gastos = list(GastoProyecto.objects.filter(proyecto=proyecto).order_by("fecha", "id"))
    ingresos = list(IngresoProyecto.objects.filter(proyecto=proyecto).order_by("fecha", "id"))

    for i in ingresos:
        if not i.estado:
            i.estado = "confirmado"

    def _sum_importes(items):
        total = Decimal("0")
        for item in items:
            if item is None:
                continue
            total += item
        return total

    ingresos_estimados = _sum_importes([i.importe for i in ingresos if i.estado == "estimado"])
    ingresos_reales = _sum_importes([i.importe for i in ingresos if i.estado == "confirmado"])
    gastos_estimados = _sum_importes([g.importe for g in gastos if g.estado == "estimado"])
    gastos_reales = _sum_importes([g.importe for g in gastos if g.estado == "confirmado"])

    beneficio_estimado = ingresos_estimados - gastos_estimados
    beneficio_real = ingresos_reales - gastos_reales

    base_precio = proyecto.precio_compra_inmueble or proyecto.precio_propiedad or Decimal("0")
    cats_adq = {"adquisicion", "reforma", "seguridad", "operativos", "financieros", "legales", "otros"}
    gastos_adq_estimado = _sum_importes(
        [g.importe for g in gastos if g.estado == "estimado" and g.categoria in cats_adq]
    )
    gastos_adq_real = _sum_importes(
        [g.importe for g in gastos if g.estado == "confirmado" and g.categoria in cats_adq]
    )

    base_est = base_precio + gastos_adq_estimado
    base_real = base_precio + gastos_adq_real
    roi_estimado = (beneficio_estimado / base_est * Decimal("100")) if base_est > 0 else None
    roi_real = (beneficio_real / base_real * Decimal("100")) if base_real > 0 else None

    categorias = []
    for key, label in GastoProyecto.CATEGORIAS:
        est = _sum_importes([g.importe for g in gastos if g.categoria == key and g.estado == "estimado"])
        real = _sum_importes([g.importe for g in gastos if g.categoria == key and g.estado == "confirmado"])
        categorias.append({"nombre": label, "estimado": est, "real": real})

    resumen = {
        "ingresos_estimados": ingresos_estimados,
        "ingresos_reales": ingresos_reales,
        "gastos_estimados": gastos_estimados,
        "gastos_reales": gastos_reales,
        "beneficio_estimado": beneficio_estimado,
        "beneficio_real": beneficio_real,
        "roi_estimado": roi_estimado,
        "roi_real": roi_real,
        "categorias": categorias,
    }

    ctx = {
        "proyecto": proyecto,
        "gastos": gastos,
        "ingresos": ingresos,
        "resumen": resumen,
        "fecha_informe": timezone.now(),
    }
    return render(request, "core/pdf_memoria_economica.html", ctx)


@csrf_exempt
def proyecto_gastos(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        gastos = []
        for g in GastoProyecto.objects.filter(proyecto=proyecto).order_by("fecha", "id"):
            gastos.append({
                "id": g.id,
                "fecha": g.fecha.isoformat(),
                "categoria": g.categoria,
                "concepto": g.concepto,
                "proveedor": g.proveedor,
                "importe": float(g.importe),
                "imputable_inversores": g.imputable_inversores,
                "estado": g.estado,
                "observaciones": g.observaciones,
            })
        return JsonResponse({"ok": True, "gastos": gastos})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        fecha = _parse_date(data.get("fecha"))
        categoria = (data.get("categoria") or "").strip()
        concepto = (data.get("concepto") or "").strip()
        importe = _parse_decimal(data.get("importe"))

        if not fecha or not categoria or not concepto or importe is None:
            return JsonResponse({"ok": False, "error": "Faltan campos obligatorios"}, status=400)

        gasto = GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=fecha,
            categoria=categoria,
            concepto=concepto,
            proveedor=(data.get("proveedor") or "").strip() or None,
            importe=importe,
            imputable_inversores=bool(data.get("imputable_inversores", True)),
            estado=(data.get("estado") or "estimado"),
            observaciones=(data.get("observaciones") or "").strip() or None,
        )
        return JsonResponse({"ok": True, "id": gasto.id})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_gasto_detalle(request, proyecto_id: int, gasto_id: int):
    try:
        gasto = GastoProyecto.objects.select_related("proyecto").get(id=gasto_id, proyecto_id=proyecto_id)
    except GastoProyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Gasto no encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "ok": True,
            "gasto": {
                "id": gasto.id,
                "fecha": gasto.fecha.isoformat(),
                "categoria": gasto.categoria,
                "concepto": gasto.concepto,
                "proveedor": gasto.proveedor,
                "importe": float(gasto.importe),
                "imputable_inversores": gasto.imputable_inversores,
                "estado": gasto.estado,
                "observaciones": gasto.observaciones,
            },
        })

    if request.method == "DELETE":
        gasto.delete()
        return JsonResponse({"ok": True})

    if request.method not in ("PUT", "PATCH"):
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        if "fecha" in data:
            gasto.fecha = _parse_date(data.get("fecha")) or gasto.fecha
        if "categoria" in data:
            gasto.categoria = (data.get("categoria") or gasto.categoria).strip()
        if "concepto" in data:
            gasto.concepto = (data.get("concepto") or gasto.concepto).strip()
        if "proveedor" in data:
            gasto.proveedor = (data.get("proveedor") or "").strip() or None
        if "importe" in data:
            gasto.importe = _parse_decimal(data.get("importe")) or gasto.importe
        if "imputable_inversores" in data:
            gasto.imputable_inversores = bool(data.get("imputable_inversores"))
        if "estado" in data:
            gasto.estado = (data.get("estado") or gasto.estado)
        if "observaciones" in data:
            gasto.observaciones = (data.get("observaciones") or "").strip() or None

        gasto.save()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_ingresos(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        ingresos = []
        for i in IngresoProyecto.objects.filter(proyecto=proyecto).order_by("fecha", "id"):
            ingresos.append({
                "id": i.id,
                "fecha": i.fecha.isoformat(),
                "tipo": i.tipo,
                "concepto": i.concepto,
                "importe": float(i.importe),
                "estado": i.estado,
                "imputable_inversores": i.imputable_inversores,
                "observaciones": i.observaciones,
            })
        return JsonResponse({"ok": True, "ingresos": ingresos})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        fecha = _parse_date(data.get("fecha"))
        tipo = (data.get("tipo") or "").strip()
        concepto = (data.get("concepto") or "").strip()
        importe = _parse_decimal(data.get("importe"))

        if not fecha or not tipo or not concepto or importe is None:
            return JsonResponse({"ok": False, "error": "Faltan campos obligatorios"}, status=400)

        ingreso = IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=fecha,
            tipo=tipo,
            concepto=concepto,
            importe=importe,
            estado=(data.get("estado") or "estimado"),
            imputable_inversores=bool(data.get("imputable_inversores", True)),
            observaciones=(data.get("observaciones") or "").strip() or None,
        )
        return JsonResponse({"ok": True, "id": ingreso.id})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_ingreso_detalle(request, proyecto_id: int, ingreso_id: int):
    try:
        ingreso = IngresoProyecto.objects.select_related("proyecto").get(id=ingreso_id, proyecto_id=proyecto_id)
    except IngresoProyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Ingreso no encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "ok": True,
            "ingreso": {
                "id": ingreso.id,
                "fecha": ingreso.fecha.isoformat(),
                "tipo": ingreso.tipo,
                "concepto": ingreso.concepto,
                "importe": float(ingreso.importe),
                "estado": ingreso.estado,
                "imputable_inversores": ingreso.imputable_inversores,
                "observaciones": ingreso.observaciones,
            },
        })

    if request.method == "DELETE":
        ingreso.delete()
        return JsonResponse({"ok": True})

    if request.method not in ("PUT", "PATCH"):
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        if "fecha" in data:
            ingreso.fecha = _parse_date(data.get("fecha")) or ingreso.fecha
        if "tipo" in data:
            ingreso.tipo = (data.get("tipo") or ingreso.tipo).strip()
        if "concepto" in data:
            ingreso.concepto = (data.get("concepto") or ingreso.concepto).strip()
        if "importe" in data:
            ingreso.importe = _parse_decimal(data.get("importe")) or ingreso.importe
        if "estado" in data:
            ingreso.estado = (data.get("estado") or ingreso.estado)
        if "imputable_inversores" in data:
            ingreso.imputable_inversores = bool(data.get("imputable_inversores"))
        if "observaciones" in data:
            ingreso.observaciones = (data.get("observaciones") or "").strip() or None

        ingreso.save()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


def proyecto_documentos(request, proyecto_id: int):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    archivos = request.FILES.getlist("archivo")
    if not archivos:
        return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-documentacion")

    titulo = (request.POST.get("titulo") or "").strip()

    categoria = (request.POST.get("categoria") or "otros").strip()
    categorias_validas = {c[0] for c in DocumentoProyecto.CATEGORIAS}
    if categoria not in categorias_validas:
        categoria = "otros"

    for idx, archivo in enumerate(archivos, start=1):
        nombre_base = os.path.splitext(archivo.name or "")[0] or "Documento"
        if titulo:
            doc_titulo = f"{titulo} ({idx})" if len(archivos) > 1 else titulo
        else:
            doc_titulo = nombre_base
        DocumentoProyecto.objects.create(
            proyecto=proyecto,
            tipo=categoria,
            categoria=categoria,
            titulo=doc_titulo,
            archivo=archivo,
        )

    return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-documentacion")


def proyecto_documento_borrar(request, proyecto_id: int, documento_id: int):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    documento = get_object_or_404(
        DocumentoProyecto,
        id=documento_id,
        proyecto_id=proyecto_id,
    )
    documento.delete()
    return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-documentacion")


def proyecto_documento_principal(request, proyecto_id: int, documento_id: int):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)
    documento = get_object_or_404(
        DocumentoProyecto,
        id=documento_id,
        proyecto_id=proyecto_id,
    )
    if documento.categoria != "fotografias":
        return JsonResponse({"ok": False, "error": "Solo válido para fotografías"}, status=400)
    DocumentoProyecto.objects.filter(
        proyecto_id=proyecto_id,
        categoria="fotografias",
    ).update(es_principal=False)
    documento.es_principal = True
    documento.save(update_fields=["es_principal"])
    return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-documentacion")


@csrf_exempt
def proyecto_checklist(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    def _seed_defaults():
        for fase, titulo in _checklist_defaults():
            ChecklistItem.objects.create(
                proyecto=proyecto,
                fase=fase,
                titulo=titulo,
                estado="pendiente",
            )

    if request.method == "GET":
        if not ChecklistItem.objects.filter(proyecto=proyecto).exists():
            _seed_defaults()
        items = []
        for it in ChecklistItem.objects.filter(proyecto=proyecto).order_by("fase", "fecha_objetivo", "id"):
            items.append({
                "id": it.id,
                "fase": it.fase,
                "titulo": it.titulo,
                "descripcion": it.descripcion,
                "responsable": it.responsable,
                "fecha_objetivo": it.fecha_objetivo.isoformat() if it.fecha_objetivo else "",
                "estado": it.estado,
                "gasto_id": it.gasto_id,
            })
        return JsonResponse({"ok": True, "items": items})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        return JsonResponse({"ok": False, "error": "Las tareas son predefinidas"}, status=405)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_checklist_detalle(request, proyecto_id: int, item_id: int):
    try:
        item = ChecklistItem.objects.select_related("proyecto").get(id=item_id, proyecto_id=proyecto_id)
    except ChecklistItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Item no encontrado"}, status=404)

    if request.method == "DELETE":
        return JsonResponse({"ok": False, "error": "No se permite borrar tareas"}, status=405)

    if request.method not in ("PUT", "PATCH"):
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        if "descripcion" in data:
            item.descripcion = (data.get("descripcion") or "").strip() or None
        if "responsable" in data:
            item.responsable = (data.get("responsable") or "").strip() or None
        if "fecha_objetivo" in data:
            item.fecha_objetivo = _parse_date(data.get("fecha_objetivo")) or item.fecha_objetivo
        if "estado" in data:
            item.estado = (data.get("estado") or item.estado)
            if item.estado == "hecho" and not item.fecha_objetivo:
                item.fecha_objetivo = timezone.now().date()

        item.save()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_participaciones(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        capital_objetivo = Decimal("0")
        try:
            snap = getattr(proyecto, "snapshot_datos", {}) or {}
            economico = snap.get("economico") if isinstance(snap.get("economico"), dict) else {}
            kpis = snap.get("kpis") if isinstance(snap.get("kpis"), dict) else {}
            metricas = kpis.get("metricas") if isinstance(kpis.get("metricas"), dict) else {}
            capital_objetivo = (
                metricas.get("valor_adquisicion_total")
                or metricas.get("valor_adquisicion")
                or economico.get("valor_adquisicion")
                or 0
            )
            capital_objetivo = _parse_decimal(capital_objetivo) or Decimal("0")
        except Exception:
            capital_objetivo = Decimal("0")

        participaciones = []
        qs = Participacion.objects.filter(proyecto=proyecto).select_related("cliente").order_by("-id")
        total_confirmadas = qs.filter(estado="confirmada").aggregate(total=Sum("importe_invertido")).get("total") or Decimal("0")
        total_confirmadas = _parse_decimal(total_confirmadas) or Decimal("0")
        for p in qs:
            pct = p.porcentaje_participacion
            if pct is None:
                if capital_objetivo > 0:
                    pct = (p.importe_invertido / capital_objetivo) * Decimal("100")
                elif total_confirmadas > 0:
                    pct = (p.importe_invertido / total_confirmadas) * Decimal("100")
            participaciones.append({
                "id": p.id,
                "cliente_id": p.cliente_id,
                "cliente_nombre": p.cliente.nombre,
                "importe_invertido": float(p.importe_invertido),
                "porcentaje_participacion": float(pct) if pct is not None else None,
                "fecha": p.creado.isoformat(),
                "estado": p.estado,
            })
        total = sum([p["importe_invertido"] for p in participaciones]) if participaciones else 0
        return JsonResponse({"ok": True, "participaciones": participaciones, "total": total})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        cliente_id = data.get("cliente_id")
        importe = _parse_decimal(data.get("importe_invertido"))
        if not cliente_id or importe is None:
            return JsonResponse({"ok": False, "error": "Faltan campos obligatorios"}, status=400)

        try:
            cliente = Cliente.objects.get(id=cliente_id)
        except Cliente.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Cliente no encontrado"}, status=404)

        porcentaje = None
        try:
            snap = getattr(proyecto, "snapshot_datos", {}) or {}
            economico = snap.get("economico") if isinstance(snap.get("economico"), dict) else {}
            kpis = snap.get("kpis") if isinstance(snap.get("kpis"), dict) else {}
            metricas = kpis.get("metricas") if isinstance(kpis.get("metricas"), dict) else {}
            capital_objetivo = (
                metricas.get("valor_adquisicion_total")
                or metricas.get("valor_adquisicion")
                or economico.get("valor_adquisicion")
                or 0
            )
            capital_objetivo = _parse_decimal(capital_objetivo) or Decimal("0")
            if capital_objetivo > 0:
                porcentaje = (importe / capital_objetivo) * Decimal("100")
        except Exception:
            porcentaje = None

        Participacion.objects.create(
            proyecto=proyecto,
            cliente=cliente,
            importe_invertido=importe,
            porcentaje_participacion=porcentaje,
            estado="confirmada",
        )
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_participacion_detalle(request, proyecto_id: int, participacion_id: int):
    try:
        part = Participacion.objects.select_related("proyecto").get(id=participacion_id, proyecto_id=proyecto_id)
    except Participacion.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Participación no encontrada"}, status=404)

    if request.method == "PATCH":
        try:
            data = json.loads(request.body or "{}")
            if "estado" in data:
                nuevo_estado = (data.get("estado") or part.estado)
                if nuevo_estado != part.estado:
                    part.estado = nuevo_estado
                    # Comunicación automática al inversor
                    try:
                        perfil = getattr(part.cliente, "perfil_inversor", None)
                        if perfil:
                            titulo = "Actualización de tu inversión"
                            mensaje = f"Tu participación en {part.proyecto.nombre} ha cambiado a estado: {nuevo_estado}."
                            ComunicacionInversor.objects.create(
                                inversor=perfil,
                                proyecto=part.proyecto,
                                titulo=titulo,
                                mensaje=mensaje,
                            )
                    except Exception:
                        pass
            part.save()
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

    if request.method == "DELETE":
        part.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)


@csrf_exempt
def proyecto_solicitudes(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        solicitudes = []
        for s in SolicitudParticipacion.objects.filter(proyecto=proyecto).select_related("inversor", "inversor__cliente"):
            solicitudes.append({
                "id": s.id,
                "cliente_nombre": s.inversor.cliente.nombre,
                "importe_solicitado": float(s.importe_solicitado),
                "estado": s.estado,
                "fecha": s.creado.isoformat(),
            })
        return JsonResponse({"ok": True, "solicitudes": solicitudes})

    return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)


@csrf_exempt
def proyecto_solicitud_detalle(request, proyecto_id: int, solicitud_id: int):
    try:
        solicitud = SolicitudParticipacion.objects.select_related("proyecto", "inversor", "inversor__cliente").get(
            id=solicitud_id, proyecto_id=proyecto_id
        )
    except SolicitudParticipacion.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Solicitud no encontrada"}, status=404)

    if request.method != "PATCH":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        estado = (data.get("estado") or "").strip()
        if estado not in ("aprobada", "rechazada", "pendiente"):
            return JsonResponse({"ok": False, "error": "Estado inválido"}, status=400)
        solicitud.estado = estado
        solicitud.save()

        if estado == "aprobada":
            # Crear participación confirmada si no existe una igual
            Participacion.objects.create(
                proyecto=solicitud.proyecto,
                cliente=solicitud.inversor.cliente,
                importe_invertido=solicitud.importe_solicitado,
                estado="confirmada",
            )
        # Comunicación automática
        try:
            titulo = "Estado de tu solicitud"
            mensaje = f"Tu solicitud en {solicitud.proyecto.nombre} ha sido {estado}."
            ComunicacionInversor.objects.create(
                inversor=solicitud.inversor,
                proyecto=solicitud.proyecto,
                titulo=titulo,
                mensaje=mensaje,
            )
        except Exception:
            pass
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_comunicaciones(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        comunicaciones = []
        for c in ComunicacionInversor.objects.filter(proyecto=proyecto).select_related("inversor", "inversor__cliente"):
            comunicaciones.append({
                "id": c.id,
                "cliente_nombre": c.inversor.cliente.nombre,
                "titulo": c.titulo,
                "mensaje": c.mensaje,
                "fecha": c.creado.isoformat(),
            })
        return JsonResponse({"ok": True, "comunicaciones": comunicaciones})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        titulo = (data.get("titulo") or "").strip()
        mensaje = (data.get("mensaje") or "").strip()
        if not titulo or not mensaje:
            return JsonResponse({"ok": False, "error": "Título y mensaje son obligatorios"}, status=400)

        clientes = Cliente.objects.filter(participaciones__proyecto=proyecto).distinct()
        count = 0
        for cliente in clientes:
            perfil, _ = InversorPerfil.objects.get_or_create(cliente=cliente)
            ComunicacionInversor.objects.create(
                inversor=perfil,
                proyecto=proyecto,
                titulo=titulo,
                mensaje=mensaje,
            )
            count += 1
        return JsonResponse({"ok": True, "enviadas": count})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
