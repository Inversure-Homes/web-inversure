# Contrato financiero actual de Inversure

Este documento es descriptivo, no normativo.

Su objetivo es fijar la semántica financiera que existe hoy en el código antes de refactorizar servicios, migrar a `Decimal` o unificar nombres.

No cambia reglas de negocio.

## Índice

- [Resumen de precedencia](#resumen-de-precedencia)
- [Mapa rápido de equivalencias](#mapa-rápido-de-equivalencias)
- [Métricas base del proyecto](#métricas-base-del-proyecto)
- [Métricas de ingresos y costes](#métricas-de-ingresos-y-costes)
- [Métricas de rentabilidad de la operación](#métricas-de-rentabilidad-de-la-operación)
- [Rendimiento, dashboard y series temporales](#rendimiento-dashboard-y-series-temporales)
- [Liquidación del inversor](#liquidación-del-inversor)
- [Auditor financiero independiente](#auditor-financiero-independiente)
- [Decisiones de negocio pendientes](#decisiones-de-negocio-pendientes)
- [Validación recomendada para futuros cambios](#validación-recomendada-para-futuros-cambios)

## Resumen de precedencia

La misma métrica puede tener fuentes distintas según la superficie:

- `detail` prioriza `snapshot.resultado` y solo después mezcla cálculos vivos.
- `dashboard` usa el `FinancialDashboardService`, que se alimenta de helpers de `core.views` y de `core.finance`.
- `pdf_memoria` calcula en vivo desde movimientos persistidos, pero acepta fallback a ingresos estimados cuando no hay ingresos reales confirmados.
- `pdf_estudio_rentabilidad` usa el snapshot congelado del estudio.
- `liquidacion_json` usa `_calc_beneficio_inversor()` y expone una liquidación por participación.
- `audit` recalcula de forma independiente con `Decimal` y solo compara con lo visible.

## Mapa rápido de equivalencias

| Nombre canónico en esta documentación | Alias / nombre visible actual | Superficies principales |
| --- | --- | --- |
| `capital_objetivo` | `captacion.capital_objetivo`, `captacion.capital_objetivo_fmt` | detail, dashboard, PDF estudio, auditor |
| `capital_aportado` | `captacion.capital_captado`, `capital_captado`, `capital_invertido` en liquidación | detail, dashboard, liquidaciones, auditor |
| `capital_pendiente` | `restante`, `capital_pendiente_total` | detail, dashboard, auditor |
| `capital_invertido` | `resultado.valor_adquisicion` en detail; `investment_return.capital_invertido` en dashboard/liquidación; `snapshot.inversor.inversion_total` en PDF estudio | detail, dashboard, PDF estudio, liquidaciones, auditor |
| `beneficio_operacion_raw` | `resultado.beneficio_neto`, `resultado.beneficio`, `beneficio_real` en PDF memoria | detail, dashboard, PDF memoria, landing, auditor |
| `beneficio_operacion_post_commission` | `beneficio_neto_real`, `beneficio_neto_estimado` en PDF memoria | PDF memoria, liquidaciones, auditor |
| `beneficio_operacion_post_tax` | `beneficio_neto_tras_impuestos`, `beneficio_neto_real_tras_impuestos` | detail, dashboard, PDF memoria, liquidaciones, auditor |
| `roi_snapshot` | `resultado.roi` cuando procede de `snapshot.resultado` | detail, PDF estudio, snapshots del simulador |
| `roi_live` | `resultado_mem.get("roi")`, `rentabilidad_estimada` en código de vista | detail, listados, landing, dashboard, PDF memoria, auditor |
| `roi_estimado` | `roi_estimado` | PDF memoria, auditor |
| `roi_estimado_tras_impuestos` | `roi_estimado_tras_impuestos` | PDF memoria, auditor |
| `roi_real` | `roi_real` | PDF memoria, auditor |
| `roi_real_tras_impuestos` | `roi_real_tras_impuestos` | PDF memoria, auditor |
| `margen_neto` | `margen_neto`, `margen_real`, `margen_estimado` | detail, PDF estudio, auditor |
| `roi_inversor_bruto` | `roi_bruto_pct`, `roi_bruto_medio` | liquidaciones, dashboard, auditor |
| `roi_inversor_neto` | `roi_neto_pct`, `roi_neto_medio` | liquidaciones, dashboard, auditor |

## Métricas base del proyecto

### `capital_objetivo`

- Fórmula actual:
  - `_capital_objetivo_desde_memoria()` devuelve primero `gastos_real_total`.
  - Si no existe, usa `gastos_est_total`.
  - Si tampoco existe, usa `valor_adquisicion`.
  - Si aún no hay base suficiente, cae a `Proyecto.precio_compra_inmueble` / `Proyecto.precio_propiedad`.
- Unidades: euros.
- Fuente de datos:
  - `GastoProyecto` confirmado o estimado.
  - `Proyecto.precio_compra_inmueble` / `precio_propiedad`.
  - `snapshot` del proyecto cuando se usa `_resultado_desde_memoria()`.
- Tipo de cálculo:
  - vivo, aunque puede apoyarse en snapshot si no hay movimientos.
- Redondeo:
  - en vistas y templates se formatea a 2 decimales.
  - el auditor mantiene `Decimal` y compara con tolerancias monetarias.
- Nulos:
  - si no hay base económica, termina en `0`.
- Fallback:
  - a precios persistidos del proyecto.
- Superficies:
  - detail, dashboard, PDF estudio, auditor, listados.
- Archivo / función:
  - `core/views.py::_capital_objetivo_desde_memoria`
  - `core/services/financial_dashboard.py::_build_project_metrics`
  - `core/services/inversure_metric_audit.py::recalculate_project`
- Diferencias conocidas:
  - en dashboard se usa como base de captación.
  - en PDF estudio se presenta como `valor_adquisicion` o `capital objetivo` según el bloque.

### `capital_aportado`

- Fórmula actual:
  - suma de `Participacion.importe_invertido` con `estado="confirmada"`.
  - en dashboard el total operativo es el mismo, aunque el KPI de `capital_en_vigor` deduplica por cliente y puede usar `InversorPerfil.aportacion_inicial_override`.
- Unidades: euros.
- Fuente de datos:
  - `Participacion` confirmadas.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - 2 decimales en superficie; `Decimal` en auditor.
- Nulos:
  - suma cero si no hay participaciones.
- Fallback:
  - no hay fallback real; si no hay participaciones es `0`.
- Superficies:
  - detail, dashboard, liquidaciones, auditor.
- Archivo / función:
  - `core/views.py` (cálculo de captación y liquidaciones)
  - `core/services/financial_dashboard.py::_build_summary`
  - `core/services/inversure_metric_audit.py::recalculate_project`
- Diferencias conocidas:
  - `capital_en_vigor` del dashboard no es igual a `capital_captado` cuando hay varios proyectos por cliente u overrides de aportación.

### `capital_pendiente`

- Fórmula actual:
  - `max(capital_objetivo - capital_aportado, 0)`.
- Unidades: euros.
- Fuente de datos:
  - derivada de `capital_objetivo` y `capital_aportado`.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - 2 decimales en superficie; `Decimal` en auditor.
- Nulos:
  - si alguno de los componentes es nulo, se trata como cero.
- Fallback:
  - no aplica.
- Superficies:
  - detail, dashboard, auditor.
- Archivo / función:
  - `core/views.py` (captación)
  - `core/services/financial_dashboard.py::_build_project_metrics`
  - `core/services/inversure_metric_audit.py::recalculate_project`

### `capital_invertido`

Este término está sobrecargado en el repositorio.

- En `detail`:
  - la tarjeta “Capital invertido” muestra `resultado.valor_adquisicion`.
  - no es el capital aportado por inversores.
- En `dashboard` y `liquidaciones`:
  - `capital_invertido` suele significar la suma de participaciones confirmadas del proyecto.
- En `PDF estudio`:
  - `snapshot.inversor.inversion_total`.

- Unidades: euros.
- Fuente de datos:
  - `Proyecto.snapshot_datos`, `GastoProyecto`, `Participacion`.
- Tipo de cálculo:
  - mezcla de snapshot y vivo, según superficie.
- Redondeo:
  - 2 decimales en superficie; `Decimal` en auditor.
- Nulos:
  - si no hay base válida, se muestra `0` o `—` según la vista.
- Fallback:
  - depende de la superficie.
- Superficies:
  - detail, dashboard, PDF estudio, liquidaciones, auditor.
- Archivo / función:
  - `core/views.py::_resultado_desde_memoria`
  - `core/services/financial_dashboard.py::_build_investment_return_summary`
  - `core/views.py::proyecto_liquidaciones`
  - `core/templates/core/pdf_estudio_rentabilidad.html`

## Métricas de ingresos y costes

### `ingresos_estimados`

- Fórmula actual:
  - suma de `IngresoProyecto.importe_estimado`.
  - si `importe_estimado` es `None`, solo se usa `IngresoProyecto.importe` cuando `estado="estimado"`.
- Unidades: euros.
- Fuente de datos:
  - `IngresoProyecto`.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - 2 decimales en superficies; `Decimal` en auditor.
- Nulos:
  - se ignoran.
- Fallback:
  - no se inventa a partir de `beneficio`.
- Superficies:
  - PDF memoria, auditor, y como base de cálculos internos del dashboard.
- Archivo / función:
  - `core/views.py::_beneficio_estimado_real_memoria`
  - `core/views.py::pdf_memoria_economica`
  - `core/services/inversure_metric_audit.py::recalculate_project`
- Diferencias conocidas:
  - el auditor ya no debe cruzarlo con `beneficio_estimado`.
  - si una línea confirmada conserva `importe_estimado`, también cuenta aquí.

### `ingresos_reales`

- Fórmula actual:
  - suma de `IngresoProyecto.importe_real` cuando `estado="confirmado"`.
  - si `importe_real` es `None`, se usa `IngresoProyecto.importe`.
  - si el total real es `0` o negativo y existen ingresos estimados positivos, `pdf_memoria` y `_beneficio_estimado_real_memoria()` hacen fallback a `ingresos_estimados`.
- Unidades: euros.
- Fuente de datos:
  - `IngresoProyecto`.
- Tipo de cálculo:
  - vivo con fallback.
- Redondeo:
  - 2 decimales en superficies; `Decimal` en auditor.
- Nulos:
  - se ignoran.
- Fallback:
  - a ingresos estimados si no hay ingresos reales confirmados.
- Superficies:
  - PDF memoria, dashboard de memorias, auditor.
- Archivo / función:
  - `core/views.py::_beneficio_estimado_real_memoria`
  - `core/views.py::pdf_memoria_economica`
  - `core/services/financial_dashboard.py::_build_project_metrics`
  - `core/services/inversure_metric_audit.py::recalculate_project`
- Diferencias conocidas:
  - el PDF de memoria etiqueta como “real” un valor que puede ser fallback estimado.
  - el auditor lo clasifica como `regla_de_negocio_pendiente` o `no_verificable_de_forma_independiente` cuando no hay dato real puro.

### `costes_estimados`

- Fórmula actual:
  - suma de `GastoProyecto.importe_estimado`.
  - si `importe_estimado` es `None`, solo se usa `GastoProyecto.importe` cuando `estado="estimado"`.
- Unidades: euros.
- Fuente de datos:
  - `GastoProyecto`.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - 2 decimales en superficies; `Decimal` en auditor.
- Nulos:
  - se ignoran.
- Fallback:
  - no se inventa.
- Superficies:
  - PDF memoria, dashboard de memorias, auditor.
- Archivo / función:
  - `core/views.py::_beneficio_estimado_real_memoria`
  - `core/views.py::pdf_memoria_economica`
  - `core/services/inversure_metric_audit.py::recalculate_project`

### `costes_reales`

- Fórmula actual:
  - suma de `GastoProyecto.importe_real` cuando `estado="confirmado"`.
  - si `importe_real` es `None`, se usa `GastoProyecto.importe`.
- Unidades: euros.
- Fuente de datos:
  - `GastoProyecto`.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - 2 decimales en superficies; `Decimal` en auditor.
- Nulos:
  - se ignoran.
- Fallback:
  - no se inventa.
- Superficies:
  - PDF memoria, dashboard de memorias, auditor.
- Archivo / función:
  - `core/views.py::_beneficio_estimado_real_memoria`
  - `core/views.py::pdf_memoria_economica`
  - `core/services/inversure_metric_audit.py::recalculate_project`

## Métricas de rentabilidad de la operación

### `beneficio_operacion_raw`

Este contrato agrupa la rentabilidad de proyecto antes de comisión e impuestos.

- En `detail` y `dashboard` suele aparecer bajo el alias histórico `beneficio_neto`.
- En `pdf_memoria` aparece como `beneficio_real` / `beneficio_estimado`.

- Fórmula actual en `_resultado_desde_memoria()`:
  - `beneficio = valor_transmision - valor_adquisicion`.
  - `valor_transmision` puede venir de ventas reales, ingresos confirmados o snapshot.
  - `valor_adquisicion` puede venir de gastos reales, gastos estimados o snapshot.
- Fórmula actual en `pdf_memoria`:
  - `beneficio_real = ingresos_reales - gastos_reales`.
  - `beneficio_estimado = ingresos_estimados - gastos_estimados`.
- Unidades: euros.
- Fuente de datos:
  - `GastoProyecto`, `IngresoProyecto`, `Proyecto.snapshot_datos`, `DatosEconomicosProyecto`.
- Tipo de cálculo:
  - vivo con fallback a snapshot.
- Redondeo:
  - `float` en vistas; `Decimal` en PDF memoria y auditor.
- Nulos:
  - se convierten a cero cuando el helper no encuentra dato.
- Fallback:
  - a snapshot o a precios persistidos del proyecto.
- Superficies:
  - detail, dashboard, PDF memoria, landing, auditor.
- Archivo / función:
  - `core/views.py::_resultado_desde_memoria`
  - `core/views.py::_beneficio_estimado_real_memoria`
  - `core/views.py::pdf_memoria_economica`
  - `core/services/financial_dashboard.py::_build_project_metrics`
  - `core/services/inversure_metric_audit.py::recalculate_project`
- Diferencias conocidas:
  - el nombre histórico `beneficio_neto` en el proyecto no coincide con el concepto financiero puro de “neto”; es el resultado operativo previo a comisión e impuesto.
  - `MEMORIA_BENEFICIO_NETO_DESDE_TRANSMISION` puede forzar `beneficio = valor_transmision - valor_adquisicion`.

### `beneficio_operacion_post_commission`

- Fórmula actual en PDF memoria:
  - `beneficio_neto_real = beneficio_real - comision_real`.
  - `beneficio_neto_estimado = beneficio_estimado - comision_estimada`.
- Fórmula actual en liquidaciones:
  - `beneficio_neto_total_operacion_pre_impuesto = beneficio_bruto_operacion - comision_eur`.
  - luego esa base se reparte entre inversores.
- Unidades: euros.
- Fuente de datos:
  - `beneficio_operacion_raw` y `% comisión`.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - 2 decimales en superficie; `Decimal` en auditor.
- Nulos:
  - si no hay beneficio positivo, la comisión es cero.
- Fallback:
  - comisión cero cuando el beneficio base es negativo o nulo.
- Superficies:
  - PDF memoria, liquidaciones, auditor.
- Archivo / función:
  - `core/views.py::pdf_memoria_economica`
  - `core/views.py::_calc_beneficio_inversor`
  - `core/finance.py::calc_operacion_economica`
  - `core/services/inversure_metric_audit.py::recalculate_project`

### `beneficio_operacion_post_tax`

- Fórmula actual en PDF memoria:
  - `beneficio_neto_real_tras_impuestos = beneficio_neto_real - impuesto_sociedades_real`.
  - `beneficio_neto_estimado_tras_impuestos = beneficio_neto_estimado - impuesto_sociedades_estimada`.
- Fórmula actual en detail / memoria del proyecto:
  - `_resultado_desde_memoria()` calcula `beneficio_neto_tras_impuestos = beneficio - impuesto_sociedades`.
- Fórmula actual en liquidaciones:
  - `beneficio_neto_total_operacion = beneficio_neto_total_operacion_pre_impuesto - impuesto_sociedades_total_operacion`.
  - por inversor: `neto_cobrar = beneficio_inversor - retencion`.
- Unidades: euros.
- Fuente de datos:
  - beneficio operativo y tipo impositivo.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - 2 decimales en superficies; `Decimal` en auditor.
- Nulos:
  - impuestos nulos se tratan como cero.
- Fallback:
  - impuesto cero si no existe tasa.
- Superficies:
  - detail, PDF memoria, liquidaciones, auditor.
- Archivo / función:
  - `core/views.py::_resultado_desde_memoria`
  - `core/views.py::pdf_memoria_economica`
  - `core/views.py::_calc_beneficio_inversor`
  - `core/services/inversure_metric_audit.py::recalculate_project`

### `roi_live`

- Fórmula actual:
  - `_resultado_desde_memoria().roi = beneficio / inversion_total * 100`.
  - `inversion_total` en esa helper es `gastos_base` si existe, si no `valor_adquisicion`.
- Unidades: porcentaje.
- Fuente de datos:
  - movimientos persistidos, snapshot, precios persistidos.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - `float` en vistas; el auditor conserva `Decimal`.
- Nulos:
  - `0.0` si no hay denominador.
- Fallback:
  - a gastos estimados o valor de adquisición.
- Superficies:
  - detail, listados, landing, dashboard, PDF memoria, comunicaciones internas, auditor.
- Archivo / función:
  - `core/views.py::_resultado_desde_memoria`
  - `landing/views.py` (helper duplicado para homepage)
  - `core/services/financial_dashboard.py::_build_project_metrics`
  - `core/services/inversure_metric_audit.py::recalculate_project`
- Diferencias conocidas:
  - no siempre coincide con `roi_snapshot`.
  - puede salir del valor calculado vivo incluso cuando el detalle visible usa el snapshot congelado.

### `roi_estimado`

- Fórmula actual:
  - en `pdf_memoria`: `beneficio_estimado / gastos_estimados * 100` si `gastos_estimados > 0`.
  - en el estudio y el detalle histórico puede venir de `snapshot.kpis.metricas.roi_estimado` o `snapshot.economico.roi_estimado`.
- Unidades: porcentaje.
- Fuente de datos:
  - `IngresoProyecto`, `GastoProyecto`, snapshot del estudio.
- Tipo de cálculo:
  - vivo en memoria económica; snapshot en estudio; auditor independiente.
- Redondeo:
  - `Decimal` en PDF memoria; 2 decimales visibles en plantilla.
- Nulos:
  - `None` o `—` si no existe denominador.
- Fallback:
  - a snapshot si no hay cálculo vivo en el estudio.
- Superficies:
  - PDF memoria, PDF estudio, auditor.
- Archivo / función:
  - `core/views.py::pdf_memoria_economica`
  - `core/views.py::_resultado_desde_memoria`
  - `core/services/inversure_metric_audit.py::recalculate_project`

### `roi_estimado_tras_impuestos`

- Fórmula actual:
  - `beneficio_neto_estimado_tras_impuestos / (gastos_estimados + impuesto_sociedades_estimada) * 100`.
- Unidades: porcentaje.
- Fuente de datos:
  - `IngresoProyecto`, `GastoProyecto`, tasa de impuesto.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - `Decimal` en PDF memoria; 2 decimales visibles en plantilla.
- Nulos:
  - `None` si no hay denominador.
- Fallback:
  - no hay alternativa real si no existen ingresos/costes estimados.
- Superficies:
  - PDF memoria, auditor.
- Archivo / función:
  - `core/views.py::pdf_memoria_economica`
  - `core/services/inversure_metric_audit.py::_compare_pdf_metrics`

### `roi_snapshot`

- Fórmula actual:
  - `snapshot.resultado.roi` si existe.
  - en el simulador/estudio también puede venir de `snapshot.kpis.metricas.roi` o `snapshot.economico.roi_estimado`.
- Unidades: porcentaje.
- Fuente de datos:
  - `Proyecto.snapshot_datos`, `Estudio.datos`, `snapshot.resultado`, `snapshot.kpis.metricas`.
- Tipo de cálculo:
  - snapshot histórico.
- Redondeo:
  - depende del valor almacenado; la superficie lo formatea a 2 decimales.
- Nulos:
  - si no existe snapshot, la vista cae a la variante viva.
- Fallback:
  - a `roi_live` o a campos equivalentes del snapshot económico.
- Superficies:
  - detail, PDF estudio, algunas comunicaciones, auditor (como `roi_snapshot`).
- Archivo / función:
  - `core/views.py` (construcción de `resultado`)
  - `core/templates/core/proyecto.html`
  - `core/templates/core/pdf_estudio_rentabilidad.html`
  - `core/services/inversure_metric_audit.py::compare_project`
- Diferencias conocidas:
  - el detalle histórico prioriza el snapshot aunque el cálculo vivo difiera.
  - este documento no decide cuál debe ser la verdad; eso queda pendiente.

### `roi_real`

- Fórmula actual:
  - `roi_real = beneficio_real / gastos_reales * 100` si `gastos_reales > 0`.
  - si no hay ingresos reales confirmados y hay ingresos estimados positivos, `beneficio_real` puede quedar construido con el estimado.
- Unidades: porcentaje.
- Fuente de datos:
  - `IngresoProyecto`, `GastoProyecto`.
- Tipo de cálculo:
  - vivo con fallback.
- Redondeo:
  - `Decimal` en `pdf_memoria`; `float` en `_beneficio_estimado_real_memoria`.
- Nulos:
  - `None` / `—` si no hay denominador.
- Fallback:
  - `ingresos_estimados` cuando no hay ingresos reales confirmados.
- Superficies:
  - `core/templates/core/pdf_memoria_economica.html`.
- Archivo / función:
  - `core/views.py::pdf_memoria_economica`
  - `core/services/inversure_metric_audit.py::_compare_pdf_metrics`
- Diferencias conocidas:
  - el PDF puede mostrar un ROI “real” construido con ingresos estimados.

### `roi_real_tras_impuestos`

- Fórmula actual:
  - `beneficio_neto_real_tras_impuestos / (gastos_reales + impuesto_sociedades_real) * 100`.
- Unidades: porcentaje.
- Fuente de datos:
  - `IngresoProyecto`, `GastoProyecto`, tasa de impuesto.
- Tipo de cálculo:
  - vivo con fallback.
- Redondeo:
  - `Decimal` en PDF memoria; `float` en auditor / vistas.
- Nulos:
  - `None` si el denominador es cero.
- Fallback:
  - `roi_estimado_tras_impuestos` cuando el real no existe.
- Superficies:
  - PDF memoria, auditor.
- Archivo / función:
  - `core/views.py::pdf_memoria_economica`
  - `core/services/inversure_metric_audit.py::_compare_pdf_metrics`

### `margen_neto`

- Fórmula actual:
  - `_resultado_desde_memoria()` calcula `beneficio / valor_transmision * 100`.
  - el auditor usa `beneficio_bruto_real / valor_transmision_real` y la variante estimada para reconstrucción independiente.
- Unidades: porcentaje.
- Fuente de datos:
  - `IngresoProyecto`, `GastoProyecto`, snapshot económico.
- Tipo de cálculo:
  - vivo con fallback a snapshot.
- Redondeo:
  - `float` en vistas; `Decimal` en auditor.
- Nulos:
  - `0.0` o `None` según la superficie.
- Fallback:
  - a la transmisión estimada si no hay transmisión real.
- Superficies:
  - detail, PDF estudio, auditor.
- Archivo / función:
  - `core/views.py::_resultado_desde_memoria`
  - `core/services/inversure_metric_audit.py::recalculate_project`

### `roi_inversor_bruto` y `roi_inversor_neto`

- Fórmula actual:
  - `roi_inversor_bruto = beneficio_bruto_inversor / capital_invertido * 100`.
  - `roi_inversor_neto = neto_cobrar / capital_invertido * 100`.
- Unidades: porcentaje.
- Fuente de datos:
  - `Participacion.importe_invertido`, `_calc_beneficio_inversor()` o `calc_inversor_settlement()`.
- Tipo de cálculo:
  - vivo.
- Redondeo:
  - `float` en vistas/dashboard; `Decimal` en auditor.
- Nulos:
  - `0` cuando capital invertido es cero.
- Fallback:
  - retención cero, neto igual a bruto cuando no hay base positiva.
- Superficies:
  - liquidaciones, dashboard comparativo, detalle inversor, auditor.
- Archivo / función:
  - `core/views.py::_calc_beneficio_inversor`
  - `core/finance.py::calc_inversor_settlement`
  - `core/services/financial_dashboard.py::_build_investment_return_summary`
  - `core/services/inversure_metric_audit.py::_build_liquidation_rows`

## Rendimiento, dashboard y series temporales

### Dashboard ejecutivo

`FinancialDashboardService` construye un payload estructurado con:

- `kpis`
- `period`
- `series.monthly`
- `charts`
- `rankings`
- `alerts`
- `projects`

Definiciones clave:

- `kpis.projects_activos` = proyectos con estado en `captacion`, `comprado`, `comercializacion`, `reservado`, `vendido`.
- `kpis.proyectos_finalizados` = proyectos con estado `cerrado` o `descartado`.
- `kpis.roi_medio` = media simple del `roi` de cada proyecto.
- `kpis.roi_medio_ponderado` = `sum(beneficio_neto) / sum(inversion_total) * 100`.
- `kpis.capital_pendiente` = suma de capital pendiente de proyectos activos.
- `series.monthly.investment` = participaciones confirmadas agrupadas por mes, usando `fecha_aportacion` o `creado`.
- `series.monthly.income` / `expense` = `importe_real` con fallback a `importe`.
- `series.monthly.performance` = `income - expense`.
- `charts.state_distribution` = distribución por estado del proyecto.
- `charts.benefit_bars` = ranking visual por `beneficio_neto`.
- `charts.deviation` = diferencia `beneficio_real - beneficio_estimado`.
- `rankings.best_roi` / `worst_roi` = ordenado por `roi`.
- `rankings.best_benefit` / `worst_benefit` = ordenado por `beneficio_neto`.
- `rankings.investment_return` = ordenado por `capital_captado`.

Archivos:

- `core/services/financial_dashboard.py`
- `core/views.py::dashboard_data`
- `core/templates/core/dashboard.html`
- `core/static/core/dashboard.js`

## Liquidación del inversor

La superficie `liquidacion_json` no usa el mismo significado que el proyecto.

### Cabecera / resumen

`core.views.proyecto_liquidaciones()` devuelve:

- `liquidaciones`: lista por participación.
- `resumen`:
  - `invertido`
  - `bruto`
  - `retencion`
  - `neto`
  - `total_a_percibir`

### Semántica real por fila

En `_calc_beneficio_inversor()`:

- `beneficio_bruto_operacion` arranca desde `resultado_mem["beneficio_neto"]`.
- Se calcula comisión sobre el beneficio positivo.
- Se calcula impuesto de sociedades sobre la base posterior a comisión.
- Se reparte el beneficio por `ratio = importe_invertido / total_proj`.
- `beneficio_neto_inversor` es la porción del beneficio para ese inversor antes de retención personal.
- `retencion` se aplica solo si el beneficio es positivo.
- `neto_cobrar` es el beneficio tras retención.
- `total_a_percibir = capital_invertido + neto_cobrar`.
- Si `CUENTAS_PARTICIPACION_LIMIT_LOSS_TO_CAPITAL` está activo y el total es negativo, se clampa a `0` y `neto_cobrar = -capital`.

### Diferencia clave

El campo `beneficio_bruto` que devuelve `proyecto_liquidaciones()` por fila no es el beneficio del proyecto completo, sino el beneficio repartido al inversor antes de retención.

## Auditor financiero independiente

El auditor vive en `core/services/inversure_metric_audit.py`.

Características relevantes:

- Recalcula con `Decimal`.
- No usa `FinancialDashboardService` como fuente de verdad.
- Sólo compara con lo visible.
- Clasifica discrepancias como:
  - `coincide`
  - `diferencia_de_redondeo`
  - `diferencia_de_definicion`
  - `dato_historico_inconsistente`
  - `error_de_calculo`
  - `regla_de_negocio_pendiente`
  - `presentacion_incorrecta`

### Casos que hoy quedan fuera de comparación estricta

- `detail.roi_snapshot`
  - procede del snapshot histórico del proyecto.
  - el auditor lo marca como `regla_de_negocio_pendiente` / `no_verificable_de_forma_independiente`.
- `pdf_memoria.ingresos_reales` y `pdf_memoria.beneficio_bruto_real`
  - pueden usar fallback estimado.
  - no son una reconstrucción real pura cuando falta ingreso real confirmado.
- `liquidacion_json`
  - si faltan datos persistidos para reconstruir de forma independiente, el auditor lo marca como no verificable.

## Decisiones de negocio pendientes

### DECISIÓN DE NEGOCIO PENDIENTE: `roi_snapshot` frente a `roi_live`

- Comportamiento actual:
  - `detail` y parte del PDF estudio priorizan el snapshot congelado si existe.
  - `dashboard` y `pdf_memoria` muestran cálculo vivo.
- Alternativas:
  1. Mantener ambos.
  2. Unificar en live.
  3. Mantener snapshot sólo como histórico explícito.
- Impacto:
  - afecta detail, dashboard, PDF estudio, comunicaciones, auditor y rankings.
- Riesgo:
  - alto si se cambia sin decidir si la superficie es histórica o operativa.

### DECISIÓN DE NEGOCIO PENDIENTE: `MEMORIA_BENEFICIO_NETO_DESDE_TRANSMISION`

- Comportamiento actual:
  - cuando está activo, `_resultado_desde_memoria()` fuerza `beneficio = valor_transmision - valor_adquisicion`.
- Alternativas:
  1. Mantener el override.
  2. Eliminarlo y respetar siempre movimientos.
  3. Aplicarlo sólo a estados cerrados/vendidos.
- Impacto:
  - detail, dashboard, PDF memoria, liquidaciones, rankings y auditor.
- Riesgo:
  - puede mover beneficios y ROIs de forma amplia en proyectos históricos.

### DECISIÓN DE NEGOCIO PENDIENTE: `CUENTAS_PARTICIPACION_LIMIT_LOSS_TO_CAPITAL`

- Comportamiento actual:
  - si el total a percibir cae por debajo de cero, se clampa a cero y el neto se fija en `-capital`.
- Alternativas:
  1. Mantener el clamp.
  2. Permitir pérdidas reales inferiores a la inversión.
  3. Aplicarlo solo a perfiles concretos.
- Impacto:
  - liquidaciones, detalle inversor, comunicaciones y auditor.
- Riesgo:
  - afecta a la lectura de pérdidas máximas y a la fiscalidad visible.

### DECISIÓN DE NEGOCIO PENDIENTE: uso real de `financiacion_pct`

- Comportamiento actual:
  - se muestra en PDFs y detalle como metadato del snapshot.
  - no alimenta los cálculos financieros principales.
- Alternativas:
  1. Mantenerlo como metadato.
  2. Convertirlo en input real de los cálculos.
  3. Deprecarlo del todo y eliminarlo de las superficies.
- Impacto:
  - PDF estudio, detalle, simulador y posible backoffice.
- Riesgo:
  - medio/alto si se usa como denominador o base de reparto sin especificación formal.

### DECISIÓN DE NEGOCIO PENDIENTE: estados legacy del dominio

- Comportamiento actual:
  - `Proyecto.estado`: `captacion`, `comprado`, `comercializacion`, `reservado`, `vendido`, `cerrado`, `descartado`.
  - `DatosEconomicosProyecto.estado_operativo`: `captacion`, `comercializacion`, `cierre`, `vendido`, `cancelado`.
  - el dashboard agrupa `cerrado` y `descartado` como terminales y trata `vendido`/`cerrado` como finalizados a efectos de liquidación.
- Alternativas:
  1. Mapear legacy a un vocabulario único.
  2. Mantener dos vocabularios con una tabla de equivalencia documentada.
  3. Migrar estados de dominio.
- Impacto:
  - filtros, rankings, alertas, cierre, liquidaciones y auditor.
- Riesgo:
  - alto si se reinterpreta un estado histórico sin una regla formal.

## Validación recomendada para futuros cambios

Todo cambio financiero posterior debería:

1. Referenciar este contrato.
2. Añadir o actualizar tests de caracterización.
3. Comparar detalle, dashboard, PDF memoria, PDF estudio, liquidaciones y auditor.
4. Aceptar explícitamente si el cambio altera snapshot, live o ambos.
5. Mantener la trazabilidad de cualquier redondeo o fallback nuevo.
