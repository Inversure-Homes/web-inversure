from __future__ import annotations

import os
from dataclasses import dataclass


def _clamp(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _as_float(x, default: float | None = None) -> float | None:
    if x is None or x == "":
        return default
    try:
        return float(x)
    except Exception:
        return default


def _env_float(name: str, default: float | None = None) -> float | None:
    return _as_float(os.environ.get(name), default)


def retencion_pct_for_tipo_persona(tipo_persona: str) -> float:
    """
    Retención por defecto (en %).

    Importante: esto NO pretende ser asesoramiento fiscal.
    Se usa como configuración del sistema y puede ajustarse vía variables de entorno.
    """
    tipo = (tipo_persona or "F").strip().upper()
    if tipo == "J":
        return _env_float("INVERSOR_RETENCION_PCT_J", 19.0) or 19.0
    return _env_float("INVERSOR_RETENCION_PCT_F", 19.0) or 19.0


def limit_loss_to_capital_enabled() -> bool:
    return (os.environ.get("CUENTAS_PARTICIPACION_LIMIT_LOSS_TO_CAPITAL", "1") or "1").strip() == "1"


@dataclass(frozen=True)
class OperacionEconomica:
    beneficio_bruto: float
    comision_eur: float
    beneficio_neto_total: float


def calc_operacion_economica(
    *,
    beneficio_bruto: float,
    comision_pct: float = 0.0,
    comision_eur: float | None = None,
    override_bruto: float | None = None,
    override_comision_eur: float | None = None,
    override_beneficio_neto_total: float | None = None,
) -> OperacionEconomica:
    """
    Calcula la operación (a nivel proyecto):
    - beneficio_bruto (beneficio de la operación antes de comisión)
    - comision_eur (solo sobre beneficio positivo)
    - beneficio_neto_total (beneficio tras comisión, a repartir)
    """
    bruto = float(beneficio_bruto or 0.0)
    pct = _clamp(float(comision_pct or 0.0), 0.0, 100.0)

    if override_bruto is not None:
        bruto = float(override_bruto)

    comision_override = override_comision_eur if override_comision_eur is not None else comision_eur

    # Comisión: solo se descuenta sobre beneficio positivo
    if bruto <= 0:
        com_eur = 0.0
    else:
        if comision_override is not None and comision_override != "":
            com_eur = float(comision_override)
        elif pct > 0:
            com_eur = bruto * (pct / 100.0)
        else:
            com_eur = 0.0
        com_eur = _clamp(com_eur, 0.0, bruto)

    if override_beneficio_neto_total is not None:
        neto_total = float(override_beneficio_neto_total)
    else:
        neto_total = bruto - com_eur

    return OperacionEconomica(beneficio_bruto=bruto, comision_eur=com_eur, beneficio_neto_total=neto_total)


def calc_inversor_settlement(
    *,
    capital_invertido: float,
    total_proyecto_invertido: float,
    beneficio_bruto_operacion: float,
    comision_pct: float = 0.0,
    comision_eur: float | None = None,
    tipo_persona: str = "F",
    retencion_pct: float | None = None,
    operacion_override: dict | None = None,
    inversor_override: dict | None = None,
    limit_loss_to_capital: bool | None = None,
) -> dict:
    """
    Devuelve métricas coherentes para:
    - comisión sobre beneficio (antes de repartir)
    - reparto por ratio (importe / total proyecto)
    - retención solo sobre beneficio positivo
    - total a percibir = capital + neto_beneficio (con clamp opcional a 0)
    """
    capital = float(capital_invertido or 0.0)
    total_proj = float(total_proyecto_invertido or 0.0)
    ratio = (capital / total_proj) if total_proj > 0 else 0.0

    op_ov = operacion_override or {}
    inv_ov = inversor_override or {}

    op = calc_operacion_economica(
        beneficio_bruto=float(beneficio_bruto_operacion or 0.0),
        comision_pct=float(comision_pct or 0.0),
        comision_eur=comision_eur,
        override_bruto=_as_float(op_ov.get("beneficio_bruto"), None),
        override_comision_eur=_as_float(op_ov.get("comision_eur"), None),
        override_beneficio_neto_total=_as_float(op_ov.get("beneficio_neto_total"), None),
    )

    beneficio_inversor = op.beneficio_neto_total * ratio
    if inv_ov.get("beneficio_inversor") not in (None, ""):
        beneficio_inversor = float(inv_ov.get("beneficio_inversor"))

    ret_pct = (
        _as_float(inv_ov.get("retencion_pct"), None)
        if inv_ov.get("retencion_pct") not in (None, "")
        else (float(retencion_pct) if retencion_pct is not None else retencion_pct_for_tipo_persona(tipo_persona))
    )
    ret_pct = _clamp(float(ret_pct or 0.0), 0.0, 100.0)

    # Retención: solo sobre beneficio positivo
    retencion = (beneficio_inversor * (ret_pct / 100.0)) if beneficio_inversor > 0 else 0.0
    if inv_ov.get("retencion") not in (None, ""):
        retencion = float(inv_ov.get("retencion"))
    retencion = max(0.0, retencion)

    neto_beneficio = beneficio_inversor - retencion
    if inv_ov.get("neto_cobrar") not in (None, ""):
        neto_beneficio = float(inv_ov.get("neto_cobrar"))

    total_a_percibir = capital + neto_beneficio

    if limit_loss_to_capital is None:
        limit_loss_to_capital = limit_loss_to_capital_enabled()
    if limit_loss_to_capital and total_a_percibir < 0:
        total_a_percibir = 0.0
        neto_beneficio = -capital

    roi_bruto_pct = (beneficio_inversor / capital * 100.0) if capital > 0 else 0.0
    roi_neto_pct = (neto_beneficio / capital * 100.0) if capital > 0 else 0.0

    return {
        # Operación / proyecto
        "beneficio_bruto": op.beneficio_bruto,
        "comision_eur": op.comision_eur,
        "beneficio_neto_total": op.beneficio_neto_total,
        # Inversor
        "participacion_pct": ratio * 100.0,
        "capital_invertido": capital,
        "beneficio_inversor": beneficio_inversor,
        "retencion_pct": ret_pct,
        "retencion": retencion,
        "neto_cobrar": neto_beneficio,
        "total_a_percibir": total_a_percibir,
        "roi_bruto_pct": roi_bruto_pct,
        "roi_neto_pct": roi_neto_pct,
    }
