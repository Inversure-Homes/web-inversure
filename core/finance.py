from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from core.decimal_utils import HUNDRED, ZERO, percentage_to_ratio, to_decimal


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
    env_names = ("INVERSOR_RETENCION_PCT_J", "INVERSOR_RETENCION_PCT") if tipo == "J" else (
        "INVERSOR_RETENCION_PCT_F",
        "INVERSOR_RETENCION_PCT",
    )
    for env_name in env_names:
        raw = os.environ.get(env_name)
        if raw in (None, ""):
            continue
        value = _as_float(raw, None)
        if value is not None:
            return value
    return 19.0


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

    def _to_decimal(value: object, *, blank_zero: bool = False) -> Decimal:
        if value is None or (blank_zero and value == ""):
            return ZERO
        if isinstance(value, bool):
            return Decimal(int(value))
        return to_decimal(value)

    bruto = _to_decimal(beneficio_bruto, blank_zero=True)
    pct = _to_decimal(comision_pct, blank_zero=True)
    if pct < ZERO:
        pct = ZERO
    elif pct > HUNDRED:
        pct = HUNDRED

    if override_bruto is not None:
        bruto = _to_decimal(override_bruto)

    comision_override = override_comision_eur if override_comision_eur is not None else comision_eur

    # Comisión: solo se descuenta sobre beneficio positivo
    if bruto <= ZERO:
        com_eur = ZERO
    else:
        if comision_override is not None and comision_override != "":
            com_eur = _to_decimal(comision_override)
        elif pct > ZERO:
            com_eur = bruto * (pct / HUNDRED)
        else:
            com_eur = ZERO
        if com_eur < ZERO:
            com_eur = ZERO
        elif com_eur > bruto:
            com_eur = bruto

    if override_beneficio_neto_total is not None:
        neto_total = _to_decimal(override_beneficio_neto_total)
    else:
        neto_total = bruto - com_eur

    return OperacionEconomica(
        beneficio_bruto=float(bruto),
        comision_eur=float(com_eur),
        beneficio_neto_total=float(neto_total),
    )


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
    def _legacy_decimal(value: object) -> Decimal:
        if value is None or value == "":
            return ZERO
        if isinstance(value, bool):
            return Decimal(int(value))
        return to_decimal(value)

    def _optional_decimal(value: object) -> Decimal | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return Decimal(int(value))
        return to_decimal(value)

    capital = _legacy_decimal(capital_invertido)
    total_proj = _legacy_decimal(total_proyecto_invertido)
    ratio = (capital / total_proj) if total_proj > ZERO else ZERO

    op_ov = operacion_override or {}
    inv_ov = inversor_override or {}

    op = calc_operacion_economica(
        beneficio_bruto=beneficio_bruto_operacion,
        comision_pct=comision_pct,
        comision_eur=comision_eur,
        override_bruto=_optional_decimal(op_ov.get("beneficio_bruto")),
        override_comision_eur=_optional_decimal(op_ov.get("comision_eur")),
        override_beneficio_neto_total=_optional_decimal(op_ov.get("beneficio_neto_total")),
    )

    beneficio_bruto_total = to_decimal(op.beneficio_bruto)
    comision_eur_total = to_decimal(op.comision_eur)
    beneficio_neto_total = to_decimal(op.beneficio_neto_total)

    beneficio_inversor = beneficio_neto_total * ratio
    beneficio_inversor_override = _optional_decimal(inv_ov.get("beneficio_inversor"))
    if beneficio_inversor_override is not None:
        beneficio_inversor = beneficio_inversor_override

    if inv_ov.get("retencion_pct") not in (None, ""):
        ret_pct = _legacy_decimal(inv_ov.get("retencion_pct"))
    elif retencion_pct is not None:
        ret_pct = Decimal(int(retencion_pct)) if isinstance(retencion_pct, bool) else to_decimal(retencion_pct)
    else:
        ret_pct = to_decimal(retencion_pct_for_tipo_persona(tipo_persona))
    if ret_pct < ZERO:
        ret_pct = ZERO
    elif ret_pct > HUNDRED:
        ret_pct = HUNDRED

    # Retención: solo sobre beneficio positivo
    retencion = beneficio_inversor * percentage_to_ratio(ret_pct) if beneficio_inversor > ZERO else ZERO
    retencion_override = _optional_decimal(inv_ov.get("retencion"))
    if retencion_override is not None:
        retencion = retencion_override
    if retencion < ZERO:
        retencion = ZERO

    neto_beneficio = beneficio_inversor - retencion
    neto_cobrar_override = _optional_decimal(inv_ov.get("neto_cobrar"))
    if neto_cobrar_override is not None:
        neto_beneficio = neto_cobrar_override

    total_a_percibir = capital + neto_beneficio

    if limit_loss_to_capital is None:
        limit_loss_to_capital = limit_loss_to_capital_enabled()
    if limit_loss_to_capital and total_a_percibir < ZERO:
        total_a_percibir = ZERO
        neto_beneficio = -capital

    roi_bruto_pct = (beneficio_inversor / capital * HUNDRED) if capital > ZERO else ZERO
    roi_neto_pct = (neto_beneficio / capital * HUNDRED) if capital > ZERO else ZERO

    return {
        # Operación / proyecto
        "beneficio_bruto": float(beneficio_bruto_total),
        "comision_eur": float(comision_eur_total),
        "beneficio_neto_total": float(beneficio_neto_total),
        # Inversor
        "participacion_pct": float(ratio * HUNDRED),
        "capital_invertido": float(capital),
        "beneficio_inversor": float(beneficio_inversor),
        "retencion_pct": float(ret_pct),
        "retencion": float(retencion),
        "neto_cobrar": float(neto_beneficio),
        "total_a_percibir": float(total_a_percibir),
        "roi_bruto_pct": float(roi_bruto_pct),
        "roi_neto_pct": float(roi_neto_pct),
    }
