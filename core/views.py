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

    estudios_qs = estudios_qs.order_by("-datos__roi", "-id")
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
    }

    return render(request, "core/proyecto.html", ctx)


@csrf_exempt
def guardar_estudio(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body)

        estudio_id = data.get("id")

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

        # --- NUEVO: compatibilidad con payloads que envían secciones en la raíz (no dentro de `datos`) ---
        for _root_sec in ("inmueble", "economico", "comite", "inversor", "kpis", "tecnico"):
            sec_val = data.get(_root_sec)
            if isinstance(sec_val, dict):
                if _root_sec not in datos or not isinstance(datos.get(_root_sec), dict):
                    datos[_root_sec] = {}
                for kk, vv in sec_val.items():
                    if kk not in datos[_root_sec] or datos[_root_sec].get(kk) in (None, ""):
                        datos[_root_sec][kk] = vv

        # Aplanar secciones por compatibilidad
        def _flatten_section(section_key: str):
            sec = datos.get(section_key)
            if isinstance(sec, dict):
                for kk, vv in sec.items():
                    if kk not in datos or datos.get(kk) in (None, ""):
                        datos[kk] = vv

        for _sec in ("tecnico", "economico", "comite", "inversor", "kpis", "inmueble"):
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

                for kk in ("decision", "decision_texto", "recomendacion", "nivel_riesgo", "comentario", "observaciones"):
                    if kk in datos["comite"] and (kk not in datos or datos.get(kk) in (None, "")):
                        datos[kk] = datos["comite"].get(kk)

        # `valor_referencia` puede venir a nivel raíz, dentro de `datos` o dentro de secciones
        valor_referencia_raw = data.get("valor_referencia")
        if valor_referencia_raw is None:
            valor_referencia_raw = datos.get("valor_referencia")
        if valor_referencia_raw is None and isinstance(datos.get("inmueble"), dict):
            valor_referencia_raw = datos["inmueble"].get("valor_referencia")
        if valor_referencia_raw is None and isinstance(data.get("inmueble"), dict):
            valor_referencia_raw = data["inmueble"].get("valor_referencia")

        valor_referencia = None
        if valor_referencia_raw is not None:
            if isinstance(valor_referencia_raw, str) and not valor_referencia_raw.strip():
                valor_referencia = None
            else:
                valor_referencia = _safe_float(valor_referencia_raw, None)

        # Normalizar KPIs clave
        valor_adq = _safe_float(
            datos.get("valor_adquisicion")
            or datos.get("precio_adquisicion")
            or datos.get("precio_compra"),
            0.0,
        )

        valor_transm = _safe_float(
            datos.get("valor_transmision")
            or datos.get("precio_transmision")
            or datos.get("precio_venta_estimado"),
            0.0,
        )

        beneficio = _safe_float(
            datos.get("beneficio")
            or datos.get("beneficio_estimado"),
            (valor_transm - valor_adq) if (valor_transm and valor_adq) else 0.0,
        )

        roi = _safe_float(
            datos.get("roi")
            or datos.get("roi_estimado"),
            (beneficio / valor_adq * 100.0) if valor_adq else 0.0,
        )

        datos["valor_adquisicion"] = valor_adq
        datos["valor_transmision"] = valor_transm
        datos["beneficio"] = beneficio
        datos["roi"] = roi

        # Comisión Inversure y métricas netas
        com_pct = _safe_float(
            datos.get("comision_inversure_pct")
            or datos.get("inversure_comision_pct")
            or datos.get("porcentaje_comision")
            or datos.get("comision_pct")
            or datos.get("comision_inversure_porcentaje"),
            0.0,
        )
        if com_pct < 0:
            com_pct = 0.0
        if com_pct > 100:
            com_pct = 100.0

        beneficio_bruto = _safe_float(datos.get("beneficio_bruto"), beneficio)
        com_eur = beneficio_bruto * (com_pct / 100.0)
        beneficio_neto = beneficio_bruto - com_eur
        roi_neto = (beneficio_neto / valor_adq * 100.0) if valor_adq else 0.0

        datos["comision_inversure_pct"] = com_pct
        datos["comision_inversure_eur"] = com_eur
        datos["inversure_comision_pct"] = com_pct
        datos["inversure_comision_eur"] = com_eur
        datos["beneficio_bruto"] = beneficio_bruto
        datos["beneficio_neto"] = beneficio_neto
        datos["roi_neto"] = roi_neto
        datos["inversion_total"] = valor_adq

        # Evitar crear estudios vacíos
        if (not estudio_id) and (not nombre) and (not direccion) and (not ref_catastral) and (not datos):
            return JsonResponse({"ok": False, "error": "Estudio vacío"}, status=400)

        campos = {
            "nombre": nombre,
            "direccion": direccion,
            "ref_catastral": ref_catastral,
            "valor_referencia": valor_referencia,
            "datos": datos,
            "guardado": True,
        }

        if estudio_id:
            estudio, _ = Estudio.objects.update_or_create(
                id=estudio_id,
                defaults=campos,
            )
        else:
            estudio = Estudio.objects.create(**campos)

        # Al guardar, cerramos el estudio activo
        request.session.pop("estudio_id", None)

        if request.GET.get("debug") == "1":
            return JsonResponse({
                "ok": True,
                "id": estudio.id,
                "received_keys": sorted(list(data.keys())),
            })

        return JsonResponse({"ok": True, "id": estudio.id})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# --- NUEVO: Guardar cambios en Proyecto y snapshot versionado ---
@csrf_exempt
def guardar_proyecto(request, proyecto_id: int):
    """Guarda cambios del proyecto (fase operativa) y crea snapshot versionado.

    No modifica el snapshot base heredado (Proyecto.snapshot_datos). En su lugar:
    - Guarda el último estado recibido en Proyecto.extra
    - Crea un ProyectoSnapshot con los datos completos (base_snapshot + overlay)
    """

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    try:
        raw_payload = json.loads(request.body or "{}")
        if not isinstance(raw_payload, dict):
            raw_payload = {}

        # Aceptamos ambos formatos:
        # 1) {"payload": { ... }}  (nuevo, usado por proyecto.js)
        # 2) { ... }               (legacy)
        incoming = raw_payload.get("payload") if isinstance(raw_payload.get("payload"), dict) else raw_payload

        # Normalizar: si viene `datos` lo usamos como overlay; si no, el payload completo
        overlay = incoming.get("datos") if isinstance(incoming.get("datos"), dict) else incoming
        if not isinstance(overlay, dict):
            overlay = {}

        overlay = _sanitize_for_json(overlay)

        # ------------------------------------------------------------
        # Persistencia en BDD (campos principales del Proyecto)
        # - nombre (cabecera / listado)
        # - direccion, ref_catastral, valor_referencia (si existen en el modelo)
        # ------------------------------------------------------------
        def _has_field(model, fname: str) -> bool:
            try:
                model._meta.get_field(fname)
                return True
            except Exception:
                return False

        def _get_str(*candidates) -> str:
            for v in candidates:
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

        proyecto_sec = overlay.get("proyecto") if isinstance(overlay.get("proyecto"), dict) else {}
        inmueble_sec = overlay.get("inmueble") if isinstance(overlay.get("inmueble"), dict) else {}

        nuevo_nombre = _get_str(
            proyecto_sec.get("nombre"),
            proyecto_sec.get("nombre_proyecto"),
            overlay.get("nombre"),
            overlay.get("nombre_proyecto"),
            inmueble_sec.get("nombre_proyecto"),
        )
        nueva_direccion = _get_str(
            inmueble_sec.get("direccion"),
            overlay.get("direccion"),
            overlay.get("direccion_completa"),
        )
        nueva_ref = _get_str(
            inmueble_sec.get("ref_catastral"),
            overlay.get("ref_catastral"),
            overlay.get("referencia_catastral"),
        )

        # valor_referencia puede venir en varias ubicaciones
        vr_raw = None
        if isinstance(inmueble_sec, dict):
            vr_raw = inmueble_sec.get("valor_referencia")
        if vr_raw in (None, ""):
            vr_raw = overlay.get("valor_referencia")
        nuevo_vr = _safe_float(vr_raw, None) if vr_raw not in (None, "") else None
        # ------------------------------------------------------------
        # Asegurar coherencia de NOMBRE en el overlay para que la UI no
        # "vuelva" al nombre heredado del estudio al recargar.
        # Muchas plantillas leen `snapshot.inmueble.nombre_proyecto` y/o
        # `snapshot.proyecto.nombre_proyecto`, no solo `proyecto.nombre`.
        # ------------------------------------------------------------
        if nuevo_nombre:
            # claves planas (fallbacks)
            overlay["nombre"] = nuevo_nombre
            overlay["nombre_proyecto"] = nuevo_nombre

            # sección proyecto
            if not isinstance(overlay.get("proyecto"), dict):
                overlay["proyecto"] = {}
            overlay["proyecto"]["nombre"] = nuevo_nombre
            overlay["proyecto"]["nombre_proyecto"] = nuevo_nombre

            # sección inmueble
            if not isinstance(overlay.get("inmueble"), dict):
                overlay["inmueble"] = {}
            overlay["inmueble"]["nombre_proyecto"] = nuevo_nombre
        update_fields: list[str] = []
        if nuevo_nombre and _has_field(Proyecto, "nombre") and getattr(proyecto, "nombre", "") != nuevo_nombre:
            proyecto.nombre = nuevo_nombre
            update_fields.append("nombre")
        if nueva_direccion and _has_field(Proyecto, "direccion") and getattr(proyecto, "direccion", "") != nueva_direccion:
            proyecto.direccion = nueva_direccion
            update_fields.append("direccion")
        if nueva_ref and _has_field(Proyecto, "ref_catastral") and getattr(proyecto, "ref_catastral", "") != nueva_ref:
            proyecto.ref_catastral = nueva_ref
            update_fields.append("ref_catastral")
        if _has_field(Proyecto, "valor_referencia"):
            cur_vr = getattr(proyecto, "valor_referencia", None)
            # Solo actualizamos si llega un valor explícito (evitamos pisar con None)
            if nuevo_vr is not None and cur_vr != nuevo_vr:
                proyecto.valor_referencia = nuevo_vr
                update_fields.append("valor_referencia")

        # Base snapshot (inmutable) + overlay (reales / ajustes / kpis)
        base_snapshot = getattr(proyecto, "snapshot_datos", None)
        if not isinstance(base_snapshot, dict):
            base_snapshot = {}

        merged = deepcopy(base_snapshot)
        merged = _deep_merge_dict(merged, overlay)

        # Guardar último estado recibido de forma robusta:
        # - Preferimos `Proyecto.extra` si existe
        # - Si el modelo no tiene `extra`, persistimos el overlay dentro de `snapshot_datos["_overlay"]`
        saved_overlay = False
        try:
            Proyecto._meta.get_field("extra")
        except Exception:
            saved_overlay = False
        else:
            extra = getattr(proyecto, "extra", None)
            if not isinstance(extra, dict):
                extra = {}
            extra["ultimo_guardado"] = {
                "fecha": timezone.now().isoformat(),
                "payload": overlay,
            }
            proyecto.extra = extra
            update_fields.append("extra")
            saved_overlay = True

        if not saved_overlay:
            sd = getattr(proyecto, "snapshot_datos", None)
            if not isinstance(sd, dict):
                sd = {}
            sd["_overlay"] = overlay
            proyecto.snapshot_datos = sd
            update_fields.append("snapshot_datos")

        # Guardar en una sola operación (incluye overlay y campos principales)
        if update_fields:
            proyecto.save(update_fields=sorted(set(update_fields)))

        # Snapshot versionado
        try:
            snap = ProyectoSnapshot.objects.create(
                proyecto=proyecto,
                fuente="guardado",
                datos=merged,
            )
            snap_id = snap.id
            version_num = snap.version_num
            codigo_version = snap.codigo_version
        except Exception:
            snap_id = None
            version_num = None
            codigo_version = ""

        return JsonResponse({
            "ok": True,
            "proyecto_id": proyecto.id,
            "snapshot_id": snap_id,
            "version": version_num,
            "codigo_version": codigo_version,
        })

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def convertir_a_proyecto(request, estudio_id: int):
    """FASE 2: Convierte un estudio guardado en un proyecto.

    Reglas:
    - El estudio debe estar guardado.
    - Se crea un snapshot final (inmutable).
    - Se crea un proyecto enlazado al estudio y al snapshot.
    - Se bloquea el estudio.

    Devuelve JSON si la petición es AJAX/JSON, o redirige a lista de proyectos.
    """

    estudio = get_object_or_404(Estudio, id=estudio_id)

    # Para este endpoint, si viene por POST desde fetch, respondemos SIEMPRE JSON
    wants_json = (
        request.method == "POST"
        or "application/json" in (request.headers.get("Accept", "") or "").lower()
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.content_type == "application/json"
    )

    # No permitir convertir borradores
    if not getattr(estudio, "guardado", False):
        msg = "El estudio debe estar guardado antes de convertirlo a proyecto."
        if wants_json:
            return JsonResponse({"ok": False, "error": msg}, status=400)
        return redirect("core:simulador")

    # Si ya está bloqueado, intentamos reutilizar el proyecto existente (idempotencia)
    if getattr(estudio, "bloqueado", False):
        existente = Proyecto.objects.filter(origen_estudio=estudio).order_by("-id").first()
        url_destino = reverse("core:lista_proyectos")
        if wants_json:
            return JsonResponse({"ok": True, "already": True, "proyecto_id": getattr(existente, "id", None), "redirect": url_destino})
        return redirect(url_destino)

    # Helper: comprobar si el modelo Proyecto tiene un campo
    def _proyecto_has_field(fname: str) -> bool:
        try:
            Proyecto._meta.get_field(fname)
            return True
        except Exception:
            return False

    from core.services.estudio_snapshot import build_estudio_snapshot

    with transaction.atomic():
        # 1) Snapshot final
        snapshot_data = build_estudio_snapshot(estudio)
        snapshot_data = _sanitize_for_json(snapshot_data)

        snapshot = EstudioSnapshot.objects.create(
            estudio=estudio,
            datos=snapshot_data,
        )

        # 2) Crear Proyecto (copiamos campos comunes si existen)
        proyecto_kwargs = {
            "origen_estudio": estudio,
            "origen_snapshot": snapshot,
            "snapshot_datos": snapshot_data,
            "convertido_desde_estudio": True,
        }

        # Campos típicos si existen en el modelo
        if _proyecto_has_field("nombre"):
            proyecto_kwargs["nombre"] = (getattr(estudio, "nombre", "") or "").strip() or f"Proyecto {estudio.id}"
        if _proyecto_has_field("direccion"):
            proyecto_kwargs["direccion"] = (getattr(estudio, "direccion", "") or "").strip()
        if _proyecto_has_field("ref_catastral"):
            proyecto_kwargs["ref_catastral"] = (getattr(estudio, "ref_catastral", "") or "").strip()
        if _proyecto_has_field("valor_referencia"):
            proyecto_kwargs["valor_referencia"] = getattr(estudio, "valor_referencia", None)

        proyecto = Proyecto.objects.create(**proyecto_kwargs)

        # 2.1) Snapshot del PROYECTO (v1) para trazabilidad
        try:
            ProyectoSnapshot.objects.create(
                proyecto=proyecto,
                fuente="conversion",
                nota="Snapshot inicial desde estudio",
                datos=snapshot_data,
            )
        except Exception:
            # No debe romper la conversión si falla el snapshot
            pass

        # 3) Bloquear el estudio
        estudio.bloqueado = True
        estudio.bloqueado_en = timezone.now()
        estudio.save(update_fields=["bloqueado", "bloqueado_en"])

        # 4) Limpiar sesión del estudio activo (evita reusar el estudio bloqueado)
        try:
            if request.session.get("estudio_id") == estudio.id:
                request.session.pop("estudio_id", None)
        except Exception:
            pass

    url_destino = reverse("core:lista_proyectos")

    # Respuesta JSON para llamadas desde JS (POST/fetch) o redirección si se accede por navegador
    if wants_json:
        return JsonResponse({"ok": True, "proyecto_id": proyecto.id, "redirect": url_destino})

    return redirect(url_destino)



def pdf_estudio_preview(request, estudio_id):
    estudio = get_object_or_404(Estudio, id=estudio_id)

    from core.services.estudio_snapshot import build_estudio_snapshot
    from core.models import EstudioSnapshot

    # --- Construir snapshot FINAL y persistir ---
    snapshot_data = build_estudio_snapshot(estudio)

    metricas_ctx = {}
    metricas_fmt_ctx = {}
    resultado_ctx = {}
    texto_ctx = {}

    # Enriquecimiento defensivo: si el builder no recibe ciertas claves (por cómo llegó el JSON),
    # añadimos aquí métricas derivables desde `estudio.datos` para que el PDF nunca quede vacío.
    try:
        m = _metricas_desde_estudio(estudio)
        metricas = m.get("metricas", {})
        metricas_ctx = metricas
        metricas_fmt_ctx = m.get("metricas_fmt", {})
        resultado_ctx = m.get("resultado", {})
        texto_ctx = m.get("texto", {})

        # Exponer también en snapshot para que la plantilla pueda acceder vía snapshot.kpis.*
        snapshot_data.setdefault("kpis", {})
        if isinstance(snapshot_data.get("kpis"), dict):
            snapshot_data["kpis"].setdefault("metricas", metricas_ctx)
            snapshot_data["kpis"].setdefault("metricas_fmt", metricas_fmt_ctx)
            snapshot_data["kpis"].setdefault("resultado", resultado_ctx)
            snapshot_data["kpis"].setdefault("texto", texto_ctx)

        # asegurar sub-dicts
        if not isinstance(snapshot_data, dict):
            snapshot_data = {}
        snapshot_data.setdefault("economico", {})
        snapshot_data.setdefault("inversor", {})

        # económicos
        if snapshot_data["economico"].get("valor_adquisicion") in (None, ""):
            snapshot_data["economico"]["valor_adquisicion"] = metricas.get("valor_adquisicion")
        if snapshot_data["economico"].get("valor_transmision") in (None, ""):
            snapshot_data["economico"]["valor_transmision"] = metricas.get("valor_transmision")
        if snapshot_data["economico"].get("beneficio_estimado") in (None, ""):
            snapshot_data["economico"]["beneficio_estimado"] = metricas.get("beneficio")
        if snapshot_data["economico"].get("roi_estimado") in (None, ""):
            snapshot_data["economico"]["roi_estimado"] = metricas.get("roi")

        # inversor (si vienen en estudio.datos)
        d0 = estudio.datos or {}
        snapshot_data["inversor"].setdefault("comision_inversure_pct", d0.get("comision_inversure_pct"))
        snapshot_data["inversor"].setdefault("comision_inversure_eur", d0.get("comision_inversure_eur"))
        snapshot_data["inversor"].setdefault("beneficio_neto", d0.get("beneficio_neto"))
        snapshot_data["inversor"].setdefault("roi_neto", d0.get("roi_neto"))
        snapshot_data["inversor"].setdefault("inversion_total", d0.get("inversion_total") or metricas.get("valor_adquisicion"))
        # Compatibilidad con nombres que usa la plantilla PDF (comision_pct/comision_eur)
        if snapshot_data["inversor"].get("comision_pct") in (None, ""):
            snapshot_data["inversor"]["comision_pct"] = snapshot_data["inversor"].get("comision_inversure_pct")
        if snapshot_data["inversor"].get("comision_eur") in (None, ""):
            snapshot_data["inversor"]["comision_eur"] = snapshot_data["inversor"].get("comision_inversure_eur")

        # Asegurar comisión Inversure (aliases)
        snapshot_data["inversor"].setdefault("comision_inversure_pct", d0.get("comision_inversure_pct") or d0.get("inversure_comision_pct"))
        snapshot_data["inversor"].setdefault("comision_inversure_eur", d0.get("comision_inversure_eur") or d0.get("inversure_comision_eur"))
    except Exception:
        pass

    # --- Enriquecimiento defensivo: decisión del comité ---
    try:
        if not isinstance(snapshot_data, dict):
            snapshot_data = {}
        snapshot_data.setdefault("comite", {})
        if not isinstance(snapshot_data.get("comite"), dict):
            snapshot_data["comite"] = {}

        d0 = estudio.datos or {}
        c0 = d0.get("comite") if isinstance(d0.get("comite"), dict) else {}

        for kk in ("recomendacion", "decision", "decision_texto", "nivel_riesgo", "comentario", "observaciones"):
            if snapshot_data["comite"].get(kk) in (None, ""):
                snapshot_data["comite"][kk] = c0.get(kk) or d0.get(kk)

        # Fallback de texto de decisión
        if not snapshot_data["comite"].get("decision_texto") and snapshot_data["comite"].get("decision"):
            snapshot_data["comite"]["decision_texto"] = str(snapshot_data["comite"].get("decision")).strip().capitalize()
    except Exception:
        pass

    # --- Enriquecimiento defensivo: identificación del inmueble ---
    # Si el builder devuelve None en los campos de identificación, los reconstruimos desde el Estudio.
    try:
        if not isinstance(snapshot_data, dict):
            snapshot_data = {}
        snapshot_data.setdefault("inmueble", {})
        inm = snapshot_data.get("inmueble")
        if not isinstance(inm, dict):
            inm = {}
            snapshot_data["inmueble"] = inm

        # asegurar básicos
        if inm.get("nombre_proyecto") in (None, ""):
            inm["nombre_proyecto"] = getattr(estudio, "nombre", "")
        if inm.get("direccion") in (None, ""):
            inm["direccion"] = getattr(estudio, "direccion", "")
        if inm.get("ref_catastral") in (None, ""):
            inm["ref_catastral"] = getattr(estudio, "ref_catastral", "")

        di = _datos_inmueble_desde_estudio(estudio)

        # Normalizar claves alternativas que puedan venir del builder
        alt_map = {
            "tipologia_inmueble": "tipologia",
            "tipo_inmueble": "tipologia",
            "tipo": "tipologia",
            "superficie": "superficie_m2",
            "m2": "superficie_m2",
            "metros_cuadrados": "superficie_m2",
            "estado_inmueble": "estado",
            "ocupacion": "situacion",
        }
        for src_k, dst_k in alt_map.items():
            if inm.get(dst_k) in (None, "") and inm.get(src_k) not in (None, ""):
                inm[dst_k] = inm.get(src_k)

        # Completar campos si vienen como None (caso actual)
        if inm.get("valor_referencia") in (None, ""):
            inm["valor_referencia"] = di.get("valor_referencia")
        if inm.get("tipologia") in (None, ""):
            inm["tipologia"] = di.get("tipologia")
        if inm.get("superficie_m2") in (None, ""):
            inm["superficie_m2"] = di.get("superficie_m2")
        if inm.get("estado") in (None, ""):
            inm["estado"] = di.get("estado")
        if inm.get("situacion") in (None, ""):
            inm["situacion"] = di.get("situacion")

        # Añadir formatos listos para plantilla (no rompe nada si la plantilla no los usa)
        inm.setdefault("valor_referencia_fmt", di.get("valor_referencia_fmt"))
        inm.setdefault("superficie_m2_fmt", di.get("superficie_m2_fmt"))
        inm.setdefault("fecha_fmt", di.get("fecha_fmt"))
    except Exception:
        pass

    # --- Normalización final de KPIs y Comité para la plantilla PDF (sin tocar HTML) ---
    try:
        if not isinstance(snapshot_data, dict):
            snapshot_data = {}

        # KPIs top-level esperados por la plantilla: ratio_euro_beneficio / colchon_seguridad / precio_breakeven
        kpis = snapshot_data.get("kpis")
        if not isinstance(kpis, dict):
            kpis = {}

        metricas = kpis.get("metricas")
        if not isinstance(metricas, dict):
            metricas = {}

        def _to_float_or_none(v):
            try:
                if v in (None, ""):
                    return None
                return float(v)
            except Exception:
                return None

        inv_total = _to_float_or_none(
            metricas.get("valor_adquisicion_total")
            or metricas.get("inversion_total")
            or metricas.get("valor_adquisicion")
            or snapshot_data.get("economico", {}).get("valor_adquisicion")
        )
        v_trans = _to_float_or_none(
            metricas.get("valor_transmision")
            or metricas.get("precio_transmision")
            or snapshot_data.get("economico", {}).get("valor_transmision")
        )
        ben = _to_float_or_none(
            metricas.get("beneficio")
            or metricas.get("beneficio_bruto")
            or snapshot_data.get("economico", {}).get("beneficio_estimado")
        )

        breakeven = _to_float_or_none(kpis.get("precio_breakeven") or metricas.get("precio_breakeven"))
        if breakeven is None and inv_total is not None:
            breakeven = inv_total

        colchon = _to_float_or_none(kpis.get("colchon_seguridad") or metricas.get("colchon_seguridad"))
        if colchon is None and v_trans is not None and breakeven is not None:
            colchon = v_trans - breakeven

        ratio = _to_float_or_none(kpis.get("ratio_euro_beneficio") or metricas.get("ratio_euro_beneficio"))
        if ratio is None and ben not in (None, 0) and inv_total is not None:
            ratio = inv_total / ben

        if kpis.get("precio_breakeven") in (None, "") and breakeven is not None:
            kpis["precio_breakeven"] = float(breakeven)
        if kpis.get("colchon_seguridad") in (None, "") and colchon is not None:
            kpis["colchon_seguridad"] = float(colchon)
        if kpis.get("ratio_euro_beneficio") in (None, "") and ratio is not None:
            kpis["ratio_euro_beneficio"] = float(ratio)

        snapshot_data["kpis"] = kpis

        # Comité: la plantilla espera recomendación y observaciones
        comite = snapshot_data.get("comite")
        if not isinstance(comite, dict):
            comite = {}

        if comite.get("recomendacion") in (None, ""):
            comite["recomendacion"] = comite.get("decision_texto") or comite.get("decision")
        if comite.get("observaciones") in (None, ""):
            comite["observaciones"] = comite.get("comentario") or ""

        snapshot_data["comite"] = comite
    except Exception:
        pass
    # Asegurar que el JSON es serializable (Decimal -> float, fechas -> string)
    snapshot_data = _sanitize_for_json(snapshot_data)
    snapshot = EstudioSnapshot.objects.create(
        estudio=estudio,
        datos=snapshot_data,
    )

    snapshot_safe = _safe_template_obj(snapshot_data)

    # Si pedimos debug, devolvemos el snapshot como JSON para inspeccionar sin usar shell
    if request.GET.get("debug") == "1":
        return JsonResponse(snapshot_data, json_dumps_params={"ensure_ascii": False, "indent": 2})

    # --- Contexto ROBUSTO para el PDF ---
    # (compatibilidad: además de snapshot.*, exponemos variables planas por si la plantilla antigua las usa)
    inm_ctx = snapshot_safe.get("inmueble", {}) if isinstance(snapshot_safe, dict) else {}
    eco_ctx = snapshot_safe.get("economico", {}) if isinstance(snapshot_safe, dict) else {}
    inv_ctx = snapshot_safe.get("inversor", {}) if isinstance(snapshot_safe, dict) else {}

    # --- Visual charts (robusto): porcentajes ya calculados para no depender de widthratio/formatos ---
    kpis_ctx = snapshot_safe.get("kpis", {}) if isinstance(snapshot_safe, dict) else {}

    def _clamp_pct(x: float) -> float:
        if x < 0:
            return 0.0
        if x > 100:
            return 100.0
        return x

    # 1) Break-even vs venta estimada (break-even + colchón = 100% de venta)
    vt = _safe_float(eco_ctx.get("valor_transmision"), 0.0)
    be = _safe_float(kpis_ctx.get("precio_breakeven"), 0.0)
    col = _safe_float(kpis_ctx.get("colchon_seguridad"), 0.0)

    if vt > 0:
        pct_be = _clamp_pct((be / vt) * 100.0)
        pct_col = _clamp_pct((col / vt) * 100.0)
        # Normalizar si por redondeos/sumas > 100
        total = pct_be + pct_col
        if total > 100.0 and total > 0:
            scale = 100.0 / total
            pct_be *= scale
            pct_col *= scale
    else:
        pct_be = 0.0
        pct_col = 0.0

    # 2) Reparto beneficio (comisión + neto = 100% del beneficio)
    ben = _safe_float(eco_ctx.get("beneficio_estimado"), 0.0)
    com = _safe_float(inv_ctx.get("comision_inversure_eur") or inv_ctx.get("comision_eur"), 0.0)
    net = _safe_float(inv_ctx.get("beneficio_neto"), 0.0)

    if ben > 0:
        pct_com = _clamp_pct((com / ben) * 100.0)
        pct_net = _clamp_pct((net / ben) * 100.0)
        total2 = pct_com + pct_net
        if total2 > 100.0 and total2 > 0:
            scale2 = 100.0 / total2
            pct_com *= scale2
            pct_net *= scale2
    else:
        pct_com = 0.0
        pct_net = 0.0

    visual_ctx = {
        # break-even chart
        "pct_be": round(pct_be, 2),
        "pct_col": round(pct_col, 2),
        # reparto beneficio chart
        "pct_com": round(pct_com, 2),
        "pct_net": round(pct_net, 2),
    }

    ctx = {
        "snapshot": snapshot_safe,
        "estudio": estudio,
        "inmueble": inm_ctx,
        "economico": eco_ctx,
        "inversor": inv_ctx,
        "visual": visual_ctx,

        # Variables planas (fallbacks) — evitan que el PDF quede vacío si la plantilla no usa snapshot.inmueble.*
        "nombre_proyecto": inm_ctx.get("nombre_proyecto") or getattr(estudio, "nombre", ""),
        "direccion": inm_ctx.get("direccion") or getattr(estudio, "direccion", ""),
        "ref_catastral": inm_ctx.get("ref_catastral") or getattr(estudio, "ref_catastral", ""),

        "valor_referencia": inm_ctx.get("valor_referencia"),
        "valor_referencia_fmt": inm_ctx.get("valor_referencia_fmt"),
        "tipologia": inm_ctx.get("tipologia"),
        "estado": inm_ctx.get("estado"),
        "situacion": inm_ctx.get("situacion"),
        "superficie_m2": inm_ctx.get("superficie_m2"),
        "superficie_m2_fmt": inm_ctx.get("superficie_m2_fmt"),
        "fecha_fmt": inm_ctx.get("fecha_fmt"),

        # Gráfico/resumen económico
        "grafico": {
            "valor_adquisicion_fmt": eco_ctx.get("valor_adquisicion"),
            "valor_transmision_fmt": eco_ctx.get("valor_transmision"),
        },

        # Aliases por si la plantilla usa estos nombres
        "inversion_total": inv_ctx.get("inversion_total") or eco_ctx.get("valor_adquisicion") or eco_ctx.get("valor_adquisicion_total"),
        "beneficio_neto": inv_ctx.get("beneficio_neto") or eco_ctx.get("beneficio_estimado"),
        "roi_neto": inv_ctx.get("roi_neto") or eco_ctx.get("roi_estimado"),

        "metricas": metricas_ctx,
        "metricas_fmt": metricas_fmt_ctx,
        "resultado": resultado_ctx,
        "texto": texto_ctx,
        "comite": snapshot_safe.get("comite", {}) if isinstance(snapshot_safe, dict) else {},
    }

    return render(
        request,
        "core/pdf_estudio_rentabilidad.html",
        ctx
    )


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