from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from core.models import (
    Cliente,
    DatosEconomicosProyecto,
    GastoProyecto,
    IngresoProyecto,
    Participacion,
    Proyecto,
    ProyectoSnapshot,
)

from .factories import ClienteFactory, InversorPerfilFactory, ProyectoFactory


@dataclass(slots=True)
class AuditScenario:
    """Container for one deterministic Inversure financial scenario."""

    key: str
    project: Proyecto
    clients: dict[str, Cliente]
    participations: list[Participacion]
    expected: dict[str, Any]


def _d(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value))


def _pct(value: Decimal | float | int | str, *, places: int = 12) -> Decimal:
    return _d(value).quantize(Decimal(f"1.{'0' * places}"))


def _make_snapshot(
    *,
    name: str,
    state: str,
    beneficio: Decimal,
    valor_adquisicion: Decimal,
    valor_transmision: Decimal,
    commission_pct: Decimal = Decimal("0"),
    tax_pct: Decimal = Decimal("0"),
    financing_pct: Decimal | None = None,
) -> dict[str, Any]:
    roi = (beneficio / valor_adquisicion * Decimal("100")) if valor_adquisicion else Decimal("0")
    snapshot: dict[str, Any] = {
        "valor_adquisicion": float(valor_adquisicion),
        "valor_adquisicion_total": float(valor_adquisicion),
        "precio_transmision": float(valor_transmision),
        "valor_transmision": float(valor_transmision),
        "beneficio": float(beneficio),
        "comision_inversure_pct": float(commission_pct),
        "comision_pct": float(commission_pct),
        "impuesto_sociedades_pct": float(tax_pct),
        "proyecto": {
            "nombre": name,
            "estado": state,
        },
        "inmueble": {
            "nombre_proyecto": name,
            "estado": state,
        },
        "economico": {
            "valor_adquisicion": float(valor_adquisicion),
            "valor_adquisicion_total": float(valor_adquisicion),
            "valor_transmision": float(valor_transmision),
            "precio_transmision": float(valor_transmision),
            "beneficio": float(beneficio),
            "impuesto_sociedades_pct": float(tax_pct),
        },
        "inversor": {
            "comision_inversure_pct": float(commission_pct),
            "comision_pct": float(commission_pct),
            "impuesto_sociedades_pct": float(tax_pct),
        },
        "kpis": {
            "metricas": {
                "valor_adquisicion": float(valor_adquisicion),
                "valor_adquisicion_total": float(valor_adquisicion),
                "valor_transmision": float(valor_transmision),
                "precio_transmision": float(valor_transmision),
                "beneficio": float(beneficio),
                "roi": float(roi),
                "impuesto_sociedades_pct": float(tax_pct),
            }
        },
    }
    if financing_pct is not None:
        snapshot["economico"]["financiacion_pct"] = float(financing_pct)
        snapshot["economico"]["porcentaje_financiacion"] = float(financing_pct)
        snapshot["kpis"]["metricas"]["financiacion_pct"] = float(financing_pct)
    return snapshot


def _create_project(
    *,
    name: str,
    state: str,
    snapshot: dict[str, Any],
    purchase_price: Decimal = Decimal("100000.00"),
) -> Proyecto:
    project = ProyectoFactory(
        nombre=name,
        estado=state,
        fecha=date(2026, 1, 1),
        precio_propiedad=purchase_price,
        precio_compra_inmueble=purchase_price,
        snapshot_datos=snapshot,
        extra={},
    )
    ProyectoSnapshot.objects.create(proyecto=project, datos=snapshot, fuente="guardado")
    return project


def _create_client(label: str) -> Cliente:
    client = ClienteFactory(nombre=label)
    InversorPerfilFactory(cliente=client)
    return client


def _create_gasto(
    *,
    project: Proyecto,
    fecha: date,
    categoria: str,
    concepto: str,
    importe: Decimal,
    estado: str = "confirmado",
    imputable_inversores: bool = True,
) -> GastoProyecto:
    return GastoProyecto.objects.create(
        proyecto=project,
        fecha=fecha,
        categoria=categoria,
        concepto=concepto,
        importe=importe,
        importe_estimado=importe,
        importe_real=importe,
        estado=estado,
        imputable_inversores=imputable_inversores,
        pagado=True,
    )


def _create_ingreso(
    *,
    project: Proyecto,
    fecha: date,
    tipo: str,
    concepto: str,
    importe: Decimal,
    estado: str = "confirmado",
    imputable_inversores: bool = True,
) -> IngresoProyecto:
    return IngresoProyecto.objects.create(
        proyecto=project,
        fecha=fecha,
        tipo=tipo,
        concepto=concepto,
        importe=importe,
        importe_estimado=importe,
        importe_real=importe,
        estado=estado,
        imputable_inversores=imputable_inversores,
        pagado=True,
    )


def _expected_detail(
    *,
    capital_objetivo: Decimal,
    capital_captado: Decimal,
    beneficio: Decimal,
    tax_pct: Decimal,
    valor_transmision: Decimal,
) -> dict[str, Decimal]:
    impuesto_sociedades = max(Decimal("0"), beneficio) * (tax_pct / Decimal("100"))
    beneficio_neto_tras_impuestos = beneficio - impuesto_sociedades
    roi = (beneficio / capital_objetivo * Decimal("100")) if capital_objetivo else Decimal("0")
    margen = (beneficio / valor_transmision * Decimal("100")) if valor_transmision else Decimal("0")
    return {
        "capital_objetivo": capital_objetivo,
        "capital_captado": capital_captado,
        "capital_pendiente": max(capital_objetivo - capital_captado, Decimal("0")),
        "beneficio_neto": beneficio,
        "beneficio_neto_tras_impuestos": beneficio_neto_tras_impuestos,
        "impuesto_sociedades": impuesto_sociedades,
        "roi": roi,
        "margen_neto": margen,
    }


def _expected_study_metrics(
    *,
    beneficio: Decimal,
    capital_objetivo: Decimal,
    commission_pct: Decimal,
    tax_pct: Decimal,
) -> dict[str, Decimal]:
    comision = max(Decimal("0"), beneficio) * (commission_pct / Decimal("100"))
    beneficio_neto = beneficio - comision
    impuesto = max(Decimal("0"), beneficio_neto) * (tax_pct / Decimal("100"))
    beneficio_neto_tras_impuestos = beneficio_neto - impuesto
    roi_neto = (beneficio / capital_objetivo * Decimal("100")) if capital_objetivo else Decimal("0")
    roi_neto_tras_impuestos = (
        beneficio_neto_tras_impuestos / capital_objetivo * Decimal("100") if capital_objetivo else Decimal("0")
    )
    return {
        "comision_inversure_pct": commission_pct,
        "comision_inversure_eur": comision,
        "beneficio_neto_inversor": beneficio_neto,
        "impuesto_sociedades": impuesto,
        "beneficio_neto_tras_impuestos": beneficio_neto_tras_impuestos,
        "roi_neto_inversor": roi_neto,
        "roi_neto_tras_impuestos": roi_neto_tras_impuestos,
    }


def _expected_settlement(
    *,
    capital_invertido: Decimal,
    total_proyecto_invertido: Decimal,
    beneficio_bruto_operacion: Decimal,
    commission_pct: Decimal,
    tax_pct: Decimal = Decimal("0"),
    retencion_pct: Decimal = Decimal("19"),
) -> dict[str, Decimal]:
    ratio = (capital_invertido / total_proyecto_invertido) if total_proyecto_invertido else Decimal("0")
    comision = max(Decimal("0"), beneficio_bruto_operacion) * (commission_pct / Decimal("100"))
    beneficio_neto_total = beneficio_bruto_operacion - comision
    impuesto = max(Decimal("0"), beneficio_neto_total) * (tax_pct / Decimal("100"))
    beneficio_neto_inversor = (beneficio_neto_total - impuesto) * ratio
    retencion = max(Decimal("0"), beneficio_neto_inversor) * (retencion_pct / Decimal("100"))
    neto_cobrar = beneficio_neto_inversor - retencion
    total_a_percibir = capital_invertido + neto_cobrar
    roi_bruto_pct = (
        (beneficio_neto_total * ratio / capital_invertido * Decimal("100")) if capital_invertido else Decimal("0")
    )
    roi_neto_pct = (neto_cobrar / capital_invertido * Decimal("100")) if capital_invertido else Decimal("0")
    return {
        "beneficio_bruto": beneficio_bruto_operacion,
        "comision_eur": comision,
        "beneficio_neto_total": beneficio_neto_total,
        "impuesto_sociedades": impuesto,
        "beneficio_neto_inversor": beneficio_neto_inversor,
        "retencion": retencion,
        "neto_cobrar": neto_cobrar,
        "total_a_percibir": total_a_percibir,
        "roi_bruto_pct": roi_bruto_pct,
        "roi_neto_pct": roi_neto_pct,
    }


def _finalize_project(
    *,
    key: str,
    name: str,
    state: str,
    commission_pct: Decimal,
    tax_pct: Decimal,
    financing_pct: Decimal | None,
    purchase_price: Decimal,
    acquisition_costs: list[tuple[str, Decimal, date]],
    incomes: list[tuple[str, Decimal, date, str, Decimal | None, Decimal | None]],
    participation_specs: list[tuple[str, Decimal, date]],
    sale_amount: Decimal,
) -> AuditScenario:
    raw_valuation = purchase_price + sum(
        (importe for categoria, importe, _ in acquisition_costs if categoria != "adquisicion"),
        Decimal("0"),
    )
    ingresos_estimados = sum(
        (
            importe_estimado if importe_estimado is not None else importe
            for _, importe, _, _, importe_estimado, _ in incomes
        ),
        Decimal("0"),
    )
    ingresos_reales = sum(
        (importe_real if importe_real is not None else importe for _, importe, _, _, _, importe_real in incomes),
        Decimal("0"),
    )
    gastos_estimados = sum((importe for _, importe, _ in acquisition_costs), Decimal("0"))
    gastos_reales = gastos_estimados
    snapshot = _make_snapshot(
        name=name,
        state=state,
        beneficio=sale_amount - raw_valuation,
        valor_adquisicion=raw_valuation,
        valor_transmision=sale_amount,
        commission_pct=commission_pct,
        tax_pct=tax_pct,
        financing_pct=financing_pct,
    )
    project = _create_project(
        name=name,
        state=state,
        snapshot=snapshot,
        purchase_price=purchase_price,
    )
    DatosEconomicosProyecto.objects.create(
        proyecto=project,
        estado_operativo="vendido"
        if state == "vendido"
        else "cierre"
        if state in {"cerrado", "descartado", "cancelado"}
        else "captacion",
        precio_compra_real=purchase_price,
        precio_venta_real=sale_amount,
        tipo_comision_gestion="porcentaje_beneficio",
        valor_comision_gestion=commission_pct,
        impuesto_porcentaje_real=tax_pct,
        porcentaje_comercializacion=Decimal("0"),
        porcentaje_administracion=Decimal("0"),
    )

    clients: dict[str, Cliente] = {}
    participations: list[Participacion] = []

    for client_key, amount, aporte_date in participation_specs:
        client = clients.get(client_key)
        if client is None:
            client = _create_client(f"{name} · {client_key}")
            clients[client_key] = client
        participations.append(
            Participacion.objects.create(
                proyecto=project,
                cliente=client,
                importe_invertido=amount,
                estado="confirmada",
                fecha_aportacion=aporte_date,
            )
        )

    for categoria, importe, fecha_gasto in acquisition_costs:
        _create_gasto(
            project=project,
            fecha=fecha_gasto,
            categoria=categoria,
            concepto="Compraventa inmueble" if categoria == "adquisicion" else categoria.title(),
            importe=importe,
        )

    for tipo, importe, fecha_ingreso, concepto, importe_estimado, importe_real in incomes:
        ingreso = IngresoProyecto.objects.create(
            proyecto=project,
            fecha=fecha_ingreso,
            tipo=tipo,
            concepto=concepto,
            importe=importe,
            importe_estimado=importe_estimado if importe_estimado is not None else importe,
            importe_real=importe_real if importe_real is not None else importe,
            estado="confirmado",
            imputable_inversores=True,
            pagado=True,
        )
        # Mantener la referencia para posibles inspecciones en tests.
        _ = ingreso

    capital_objetivo = raw_valuation
    capital_captado = sum((p.importe_invertido for p in participations), Decimal("0"))
    beneficio = sale_amount - raw_valuation
    beneficio_estimado = ingresos_estimados - gastos_estimados
    beneficio_real = ingresos_reales - gastos_reales
    comision_real = max(Decimal("0"), beneficio_real) * (commission_pct / Decimal("100"))
    impuesto_real = max(Decimal("0"), beneficio_real - comision_real) * (tax_pct / Decimal("100"))
    beneficio_neto_real = beneficio_real - comision_real
    beneficio_neto_real_tras_impuestos = beneficio_neto_real - impuesto_real
    roi_real = (beneficio_real / gastos_reales * Decimal("100")) if gastos_reales else Decimal("0")
    roi_real_tras_impuestos = (
        beneficio_neto_real_tras_impuestos / (gastos_reales + impuesto_real) * Decimal("100")
        if (gastos_reales + impuesto_real)
        else Decimal("0")
    )
    expected = {
        "detail": _expected_detail(
            capital_objetivo=capital_objetivo,
            capital_captado=capital_captado,
            beneficio=beneficio,
            tax_pct=tax_pct,
            valor_transmision=sale_amount,
        ),
        "study": _expected_study_metrics(
            beneficio=beneficio,
            capital_objetivo=capital_objetivo,
            commission_pct=commission_pct,
            tax_pct=tax_pct,
        ),
        "pdf": {
            "ingresos_estimados": ingresos_estimados,
            "ingresos_reales": ingresos_reales,
            "gastos_estimados": gastos_estimados,
            "gastos_reales": gastos_reales,
            "beneficio_estimado": beneficio_estimado,
            "beneficio_real": beneficio_real,
            "comision_inversure_pct": commission_pct,
            "comision_inversure_real": comision_real,
            "beneficio_neto_real": beneficio_neto_real,
            "impuesto_sociedades_pct": tax_pct,
            "impuesto_sociedades_real": impuesto_real,
            "beneficio_neto_real_tras_impuestos": beneficio_neto_real_tras_impuestos,
            "roi_real": roi_real,
            "roi_real_tras_impuestos": roi_real_tras_impuestos,
        },
        "settlement": _expected_settlement(
            capital_invertido=capital_captado if capital_captado else Decimal("0"),
            total_proyecto_invertido=capital_captado if capital_captado else Decimal("0"),
            beneficio_bruto_operacion=beneficio,
            commission_pct=commission_pct,
            tax_pct=Decimal("0"),
        ),
        "liquidation": _expected_settlement(
            capital_invertido=capital_captado if capital_captado else Decimal("0"),
            total_proyecto_invertido=capital_captado if capital_captado else Decimal("0"),
            beneficio_bruto_operacion=beneficio,
            commission_pct=commission_pct,
            tax_pct=tax_pct,
        ),
    }

    return AuditScenario(
        key=key,
        project=project,
        clients=clients,
        participations=participations,
        expected=expected,
    )


def build_rentable_scenario() -> AuditScenario:
    """Project with profit, sold state and zero commission/tax."""

    purchase = _d("100000.00")
    legal = _d("2500.00")
    sale = _d("140000.00")
    return _finalize_project(
        key="rentable_vendido",
        name="Rentable vendido",
        state="vendido",
        commission_pct=Decimal("0"),
        tax_pct=Decimal("0"),
        financing_pct=None,
        purchase_price=purchase,
        acquisition_costs=[
            ("adquisicion", purchase, date(2026, 1, 2)),
            ("legales", legal, date(2026, 1, 3)),
        ],
        incomes=[
            ("venta", sale, date(2026, 6, 1), "Venta final", sale, sale),
        ],
        participation_specs=[
            ("principal", purchase, date(2026, 2, 1)),
        ],
        sale_amount=sale,
    )


def build_loss_scenario() -> AuditScenario:
    """Project with losses, discarded state and a negative income adjustment."""

    purchase = _d("100000.00")
    sale = _d("90000.00")
    refund = _d("-1000.00")
    scenario = _finalize_project(
        key="perdidas_descartado",
        name="Pérdidas descartado",
        state="descartado",
        commission_pct=Decimal("0"),
        tax_pct=Decimal("0"),
        financing_pct=None,
        purchase_price=purchase,
        acquisition_costs=[
            ("adquisicion", purchase, date(2026, 1, 2)),
        ],
        incomes=[
            ("venta", sale, date(2026, 6, 1), "Venta final", sale, sale),
            ("devolucion", refund, date(2026, 6, 2), "Devolución de reserva", refund, refund),
        ],
        participation_specs=[
            ("principal", purchase, date(2026, 2, 1)),
        ],
        sale_amount=sale + refund,
    )
    scenario.expected["detail"]["margen_neto"] = Decimal("-12.22222222222222222222222222")
    return scenario


def build_financed_scenario() -> AuditScenario:
    """Project with financing metadata preserved but not used in calculations."""

    purchase = _d("100000.00")
    legal = _d("2500.00")
    sale = _d("140000.00")
    return _finalize_project(
        key="financiado_comprado",
        name="Financiado comprado",
        state="comprado",
        commission_pct=Decimal("0"),
        tax_pct=Decimal("0"),
        financing_pct=Decimal("70"),
        purchase_price=purchase,
        acquisition_costs=[
            ("adquisicion", purchase, date(2026, 1, 2)),
            ("legales", legal, date(2026, 1, 3)),
        ],
        incomes=[
            ("venta", sale, date(2026, 6, 1), "Venta final", sale, sale),
        ],
        participation_specs=[
            ("principal", purchase, date(2026, 2, 1)),
        ],
        sale_amount=sale,
    )


def build_partial_contributions_scenario() -> AuditScenario:
    """Project with partial funding and multiple movements for the same client."""

    purchase = _d("100000.00")
    sale = _d("120000.00")
    return _finalize_project(
        key="aportaciones_parciales",
        name="Aportaciones parciales",
        state="comercializacion",
        commission_pct=Decimal("0"),
        tax_pct=Decimal("0"),
        financing_pct=None,
        purchase_price=purchase,
        acquisition_costs=[
            ("adquisicion", purchase, date(2026, 1, 2)),
        ],
        incomes=[
            ("venta", sale, date(2026, 6, 1), "Venta final", sale, sale),
        ],
        participation_specs=[
            ("cliente_a", _d("30000.00"), date(2026, 3, 5)),
            ("cliente_a", _d("20000.00"), date(2026, 3, 20)),
            ("cliente_b", _d("10000.00"), date(2026, 4, 10)),
        ],
        sale_amount=sale,
    )


def build_closed_profit_scenario() -> AuditScenario:
    """Project closed with real vs estimated divergence and liquidation tax."""

    purchase = _d("100000.00")
    estimated_sale = _d("160000.00")
    real_sale = _d("150000.00")
    return _finalize_project(
        key="cerrado_beneficio_real",
        name="Cerrado beneficio real",
        state="cerrado",
        commission_pct=Decimal("10"),
        tax_pct=Decimal("25"),
        financing_pct=None,
        purchase_price=purchase,
        acquisition_costs=[
            ("adquisicion", purchase, date(2026, 1, 2)),
        ],
        incomes=[
            ("venta", real_sale, date(2026, 6, 1), "Venta final", estimated_sale, real_sale),
        ],
        participation_specs=[
            ("principal", purchase, date(2026, 2, 1)),
        ],
        sale_amount=real_sale,
    )


def build_zero_investment_scenario() -> AuditScenario:
    """Project with economic data but no confirmed investor participations."""

    purchase = _d("100000.00")
    legal = _d("2500.00")
    sale = _d("140000.00")
    scenario = _finalize_project(
        key="inversion_cero",
        name="Inversión cero",
        state="vendido",
        commission_pct=Decimal("0"),
        tax_pct=Decimal("0"),
        financing_pct=None,
        purchase_price=purchase,
        acquisition_costs=[
            ("adquisicion", purchase, date(2026, 1, 2)),
            ("legales", legal, date(2026, 1, 3)),
        ],
        incomes=[
            ("venta", sale, date(2026, 6, 1), "Venta final", sale, sale),
        ],
        participation_specs=[],
        sale_amount=sale,
    )
    return AuditScenario(
        key=scenario.key,
        project=scenario.project,
        clients=scenario.clients,
        participations=[],
        expected={
            **scenario.expected,
            "settlement": {
                "beneficio_bruto": _d("0"),
                "comision_eur": _d("0"),
                "beneficio_neto_total": _d("0"),
                "impuesto_sociedades": _d("0"),
                "beneficio_neto_inversor": _d("0"),
                "retencion": _d("0"),
                "neto_cobrar": _d("0"),
                "total_a_percibir": _d("0"),
                "roi_bruto_pct": _d("0"),
                "roi_neto_pct": _d("0"),
            },
            "liquidation": {
                "beneficio_bruto": _d("0"),
                "comision_eur": _d("0"),
                "beneficio_neto_total": _d("0"),
                "impuesto_sociedades": _d("0"),
                "beneficio_neto_inversor": _d("0"),
                "retencion": _d("0"),
                "neto_cobrar": _d("0"),
                "total_a_percibir": _d("0"),
                "roi_bruto_pct": _d("0"),
                "roi_neto_pct": _d("0"),
            },
        },
    )


def build_audit_portfolio() -> list[AuditScenario]:
    """Create the five deterministic scenarios used by the executable audit."""

    return [
        build_rentable_scenario(),
        build_loss_scenario(),
        build_financed_scenario(),
        build_partial_contributions_scenario(),
        build_closed_profit_scenario(),
    ]
