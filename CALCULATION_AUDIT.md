# Calculation Audit - Inversure

Fecha: 2026-07-16
Rama: `feature/dashboard-financiero`

## 1. Alcance y método

Auditoría integral de la lógica de cálculo detectada en el repositorio:

- Python de negocio, vistas, servicios, comandos y tests.
- JavaScript de simulador, proyecto y dashboard.
- Plantillas HTML y PDFs.
- Consultas ORM con `aggregate`, `annotate`, `select_related`, `prefetch_related`.
- Endpoints JSON y exportaciones.

No se ha usado producción ni datos reales. No se han creado migraciones. No se han hecho refactors amplios.

Hallazgos principales:

- La lógica económica está bastante concentrada en `core/views.py`, `core/finance.py` y `core/services/financial_dashboard.py`.
- La capa frontend duplica parte de la lógica de simulación y detalle de proyecto, pero no el dashboard nuevo.
- No se ha encontrado SQL crudo (`cursor.execute`, `.raw()`, `RawSQL`) en el código de aplicación.
- Se ha corregido un bug objetivo de presentación: un ratio estaba mostrándose con símbolo de euro en el detalle de proyecto y en el PDF de estudio.
- Se ha corregido un hallazgo de seguridad de Bandit: el `cache_key` del dashboard usaba SHA-1 y ahora usa SHA-256.
- Bloques principales auditados: 27.

## 2. Inventario completo de cálculo

### 2.1 Matriz principal

| Módulo | Archivo / función | Métrica | Fórmula | Campos de origen | Unidad / tipo / redondeo | Filtros / estados | Salida |
|---|---|---|---|---|---|---|---|
| `core/views.py` | `_resultado_desde_memoria` | Beneficio, ROI, ratio, margen, precio mínimo, colchón | `ingresos_base - gastos_base`; `beneficio / inversion_total * 100`; `beneficio / inversion_total`; `beneficio / valor_transmision * 100`; `valor_adq + max(30000, 0.15*valor_adq) + gastos_venta_base` | `GastoProyecto.importe[_real|_estimado]`, `IngresoProyecto.importe[_real|_estimado]`, `Proyecto.precio_compra_inmueble`, `Proyecto.precio_propiedad`, `snapshot.economico`, `snapshot.kpis` | € y %; `Decimal` en cálculo, `float` al salir; sin redondeo interno | `only_imputable_inversores`; ingresos confirmados/estimados; venta/anticipo/señal en proyectos `vendido/cerrado` | Proyectos, dashboard, PDFs, cartas |
| `core/views.py` | `_calc_beneficio_inversor` | Comisión, impuesto, beneficio inversor, retención, total a percibir, ROI bruto/neto | `comision = max(0, beneficio_bruto_operacion) * pct`; `beneficio_neto_operacion = bruto - comision - impuesto_sociedades`; `beneficio_inversor = beneficio_neto_operacion * ratio`; `retencion = max(0, beneficio_inversor) * pct_ret`; `total = capital + (beneficio_inversor - retencion)` | `Participacion.importe_invertido`, `Participacion.beneficio_neto_override`, `Participacion.beneficio_override_data`, `snapshot.inversor`, `snapshot.economico.impuesto_sociedades_pct` | € y %; `float`; sin redondeo interno | Solo participaciones confirmadas; comisión e impuesto clamped 0..100; pérdidas no generan comisión/retención | Liquidaciones, cartas, portal inversor |
| `core/views.py` | `_build_comunicacion_context`, `_irr_2point`, `_moic` | Rentabilidad proyecto, rentabilidad inversor, IRR, MOIC, participación | `ROI proyecto` desde `_resultado_desde_memoria`; `ROI inversor bruto/neto = beneficio / capital * 100`; `IRR = (fv/abs(pv)) ** (365/days) - 1`; `MOIC = fv / abs(pv)`; `participación = importe / capital_objetivo * 100` | `Participacion`, `Proyecto`, `ProyectoSnapshot`, `snapshot.economico`, `snapshot.kpis`, `fecha_aportacion` | € / % / múltiplo; `float`; formateo a 2 o 3 decimales según salida | Usa fecha de aportación, fecha de salida y estado del proyecto; fallback a `capital_objetivo` o total invertido | Cartas PDF, certificados, portal |
| `core/views.py` | `_metricas_desde_estudio` | Beneficio, ROI, margen, beneficio neto tras impuestos | `beneficio = precio_transmision - valor_adquisicion`; `roi = beneficio / valor_adquisicion * 100`; `margen = beneficio / precio_transmision * 100`; impuesto sobre `beneficio` si hay `%` | `Estudio.datos`, `kpis.metricas`, `economico`, `comite`, `inversor` | € y %; `float`; 2 decimales en formato | Sin filtros; usa JSON del estudio si existe | Estudio, simulador, PDF de rentabilidad |
| `core/views.py` | `pdf_memoria_economica` | Totales estimado/real, comisión, impuesto, beneficio neto, ROI antes/después de impuestos | `ingresos = sum(lines)`; `gastos = sum(lines)`; `beneficio = ingresos - gastos`; `comision = max(0, beneficio) * pct`; `impuesto = max(0, beneficio_neto) * pct_impuesto`; `ROI = beneficio / gastos * 100`; `ROI post = beneficio_neto_tras_impuestos / (gastos + impuesto) * 100` | `GastoProyecto`, `IngresoProyecto`, `snapshot.inversor`, `snapshot.economico` | € y %; `Decimal` en cálculo, render final formateado | `estado=confirmado/estimado`; si no hay reales, cae a estimados | PDF memoria económica |
| `core/views.py` | `pdf_estudio_rentabilidad` / `_build_presentacion_context` | Exposición de métricas congeladas | No recalcula negocio; consume `snapshot` y `resultado_mem` | `snapshot`, `estudio`, `proyecto` | Presentación | Depende del snapshot congelado | PDF estudio / dossier |
| `core/finance.py` | `calc_operacion_economica` | Beneficio bruto, comisión, beneficio neto total | `comision = bruto * pct` solo si `bruto > 0`; `neto = bruto - comision` | Valor bruto de la operación | €; `float`; sin redondeo | Comisión clamped 0..100; pérdidas sin comisión | Settlement base |
| `core/finance.py` | `calc_inversor_settlement` | Participación, retención, neto a cobrar, ROI bruto/neto | `ratio = capital / total_proyecto`; `beneficio_inversor = neto_operacion * ratio`; `retencion = max(0, beneficio_inversor) * pct_ret`; `total = capital + neto` | `Participacion.importe_invertido`, total proyecto, beneficio bruto operación, override data | € y %; `float`; sin redondeo | Limitación opcional de pérdida a capital; retención solo sobre beneficio positivo | Dashboard, liquidaciones, portal |
| `core/services/financial_dashboard.py` | `_build_project_metrics` | KPI por proyecto | Orquesta `_resultado_desde_memoria`, `_beneficio_estimado_real_memoria`, `_capital_objetivo_desde_memoria`, `calc_inversor_settlement` | `Proyecto` + relaciones prefetched | € y %; mezcla `Decimal` y `float` según salida API | Solo proyectos visibles por filtros | Payload del dashboard |
| `core/services/financial_dashboard.py` | `_build_summary` | Capital total, capital pendiente, ROI medio, ROI ponderado, beneficio cerrado/abierto | `sum(confirmadas)`; `capital_en_vigor = primera aportación por cliente con override`; `roi_medio = mean(roi)`; `roi_medio_ponderado = sum(beneficio_neto) / sum(inversion_total) * 100`; cerrados/abiertos por estado | `Participacion`, `Cliente`, `InversorPerfil`, `project_metrics` | € y %; `Decimal` + `float`; sin redondeo | Estados activos: `captacion/comprado/comercializacion/reservado/vendido`; cerrados: `cerrado`; terminales: `cerrado/descartado` | KPI del dashboard |
| `core/services/financial_dashboard.py` | `_build_monthly_rows` | Evolución mensual | `participaciones` por `fecha_aportacion` o `creado`; `ingresos`/`gastos` por `fecha`; `performance = income - expense` | `Participacion`, `IngresoProyecto`, `GastoProyecto` | €; `Decimal`; mes `YYYY-MM` | Filtro por rango de fechas y proyecto | Series del dashboard |
| `core/services/financial_dashboard.py` | `_build_charts` | Distribución por estado, barras de beneficio, desviación | `% estado = count/total`; barra beneficio = orden por `beneficio_neto`; desviación = `beneficio_real - beneficio_estimado` | `project_metrics` | € y %; `float`; display con 2 decimales | Estados de proyecto; solo proyectos con movimientos para desviación | Gráficos y comparativas |
| `core/services/financial_dashboard.py` | `_build_rankings` | Mejor/peor ROI, mejor/peor beneficio, inversión vs retorno | Ordenación descendente por `roi`, `beneficio_neto`, `capital_captado` | `project_metrics` | € y %; `float` | Ranking global sobre universo filtrado | Ranking cards |
| `core/services/financial_dashboard.py` | `_build_alerts` | Alertas operativas y financieras | `checklist vencida`; `roi < 0`; `gastos_real_total > gastos_est_total > 0`; `pendientes` solicitudes; líneas confirmadas sin factura/justificante | `ChecklistItem`, `SolicitudParticipacion`, `FacturaGasto`, `JustificanteIngreso`, `project_metrics` | Conteos, € y %; `int`/`float` | Checklist: `estado != hecho`; permisos comerciales filtran responsables | Alertas dashboard |
| `landing/views.py` | `_roi_memoria` | ROI de landing / resumen | `beneficio = ingresos - gastos`; `ROI = beneficio / gastos * 100` con fallback estimado | `GastoProyecto`, `IngresoProyecto` | %; `float`; sin redondeo interno | Si no hay reales, usa estimados | Landing y portada |
| `landing/views.py` | `landing_home` | Desviación estimado vs real | `total_real - total_estimado`; `% = delta / estimado * 100` | `dashboard_ctx["beneficio_deviation_chart"]` | € y %; `float` | Resumen portfolio | Hero / cards landing |
| `core/static/core/simulador.js` | Cálculo comité / estudio | Beneficio, ROI, margen, ratio, colchón, breakeven, comisión | `beneficio = valor_transmision - valor_adquisicion`; `ROI = beneficio / valor_adquisicion * 100`; `margen = beneficio / valor_transmision * 100`; `ratio = valor_adquisicion / beneficio`; `colchón = valor_transmision - valor_adquisicion - 30000`; `breakeven = valor_adquisicion + 30000`; `comisión = max(0, beneficio) * pct` | Inputs de simulador y estado `estadoEstudio` | € y %; `Number`; 2 decimales en UI | `beneficio > 0` para ratio y comisión; `semáforo` por ROI `>=20`, `>=10` | Simulador y estudio |
| `core/static/core/proyecto.js` | `bindAutocalcGastos`, `bindAutocalcValorTransmision` | Valor adquisición, valor transmisión y gastos de venta | `ITP = precio * 0.02`; `notaria = max(precio*0.002, 500)`; `registro = max(precio*0.002, 500)`; `valor_adq = precio + impuestos + notaría + registro + extras`; `valor_trans = venta - gastos_venta` | Inputs del proyecto | €; `Number`; 2 decimales en UI | Formulario de proyecto; updates por input | Detalle de proyecto |
| `core/static/core/proyecto.js` | `updateComisionInversureMetrics` | Comisión, impuesto sociedades, ROI antes/después de impuestos | `comision = max(0, beneficioBase) * pct`; `beneficioAntes = beneficioBase - comision`; `impuesto = max(0, beneficioAntes) * pct_impuesto`; `ROI antes/después = beneficio / capital * 100`; `ratio = beneficio / capital` | Inputs y estado del proyecto | € y %; `Number`; 2 decimales | Capital captado / objetivo / valor adquisición como denominadores según bloque | Panel Inversure |
| `core/static/core/proyecto.js` | `updateInvestmentAnalysis` | ROI, ratio, margen, ajustes de precio/gastos, viabilidad | `beneficio = ingresosBase - gastosBase`; `valorAdq = basePrecio + gastosAdq`; `valorTrans = ventaBruta - gastosVenta`; `beneficioBruto = valorTrans - valorAdq`; `ROI = beneficioBruto / valorAdq * 100`; `ratio = beneficioBruto / valorAdq`; `margen = beneficioBruto / valorTrans * 100`; `viable = roi >= 15 && beneficio >= 30000` | Inputs del proyecto y memoria | € y %; `Number`; 2 decimales | Usa reales si existen, si no estimados | Resultado de proyecto |
| `core/static/core/dashboard.js` | `renderKpis`, `renderMonthlyChart`, `renderDeviationChart` | Presentación y gráficas | No recalcula negocio; formatea y agrega series ya calculadas; `performance = beneficio` del payload mensual | Payload JSON del servicio | €/%/enteros; `Number` + `Intl` | Filtra por datos recibidos | Dashboard visual |
| `core/management/commands/audit_kpis.py` | Auditoría y sync | Compara ROI memoria vs snapshot/modelo; sincroniza ROI y `% participación` | `roi_mem`, `roi_snapshot`, `roi_model`; `pct_participación = importe / capital_objetivo * 100` | `Proyecto`, `Participacion`, `snapshot_datos`, `extra` | €/%; `float` + `Decimal(str(round(...)))` | Solo discrepancias según umbral | CLI de mantenimiento |
| `core/management/commands/audit_integridad_datos.py` | Integridad de tipos | Cuenta ingresos confirmados / estimados; retipa `otro` a `venta` si es seguro | `Count(confirmados)`, `Count(estimados)`, `Count(confirmados_no_venta)`; regla segura para cierres | `IngresoProyecto`, `Proyecto` | Conteos; `int` | Estados `vendido/cerrado`; tipos `venta/senal/anticipo` | CLI de mantenimiento |
| `core/management/commands/recalcular_roi_proyectos.py` | Persistencia ROI | Guarda `beneficio_neto` y `roi` desde memoria | Toma `_resultado_desde_memoria`; persiste si difiere | `Proyecto`, memoria económica | €/%; `Decimal(str(float(...)))` | Filtro por `--ids` | CLI de mantenimiento |
| `core/management/commands/seed_demo_kpis.py` | Dataset demo | Genera un proyecto ejemplo y calcula ROI | Usa el mismo cálculo de memoria y resume por inversor | `Proyecto`, `Participacion`, `GastoProyecto`, `IngresoProyecto` | €/%; `float` para logging | Entorno demo | CLI de seed |
| `core/management/commands/regenerar_dossier_pdfs.py` | Regeneración PDF | Barra ROI y dossier reutilizando snapshot actual | `roi_bar = min(max(roi, 0), 30) / 30 * 100` | `Proyecto`, `DocumentoProyecto`, snapshot | % y barra visual | Solo proyectos con dossier si se pide | CLI de exportación |
| `core/management/commands/audit_logica_economica.py` | Contraste | Compara `beneficio_neto` con `valor_transmision - valor_adquisicion` | `diff = beneficio - (valor_trans - valor_adq)` | `_resultado_desde_memoria` | €/%; `float` | Umbral por `epsilon` | CLI de contraste |
| `core/templates/core/proyecto.html` | Plantilla detalle | Presentación de `ratio_euro`, ROI, beneficio, impuestos | Sin fórmula nueva; solo render. Bug corregido: el ratio ya no lleva `€` | `resultado`, `metricas`, `inv` | Presentación | Proyectos / inversión | HTML |
| `core/templates/core/pdf_estudio_rentabilidad.html` | Plantilla PDF estudio | Presentación de ratio, ROI, financiación, colchón, break-even | Sin fórmula nueva; solo render. Bug corregido: `ratio_euro_beneficio` ya no lleva `€` | `snapshot`, `estudio` | Presentación | Estudios y PDFs | PDF |

### 2.2 Mapa de datos por KPI

| KPI | Fuente canónica | Campos y modelos | Regla |
|---|---|---|---|
| Capital total invertido | `FinancialDashboardService._build_summary` | `Participacion.importe_invertido` con `estado="confirmada"` | Suma de participaciones confirmadas del universo filtrado |
| Capital pendiente | `FinancialDashboardService._build_project_metrics` | `capital_objetivo` desde `_capital_objetivo_desde_memoria`; `capital_captado` desde participaciones confirmadas | `max(capital_objetivo - capital_captado, 0)` |
| Beneficio estimado | `_beneficio_estimado_real_memoria` | `IngresoProyecto.importe_estimado`, `GastoProyecto.importe_estimado` | `ingresos_estimados - gastos_estimados` |
| Beneficio realizado | `_beneficio_estimado_real_memoria` | `IngresoProyecto.importe_real`, `GastoProyecto.importe_real` | `ingresos_reales - gastos_reales` |
| ROI medio | `_build_summary` | `project_metrics.roi` | Media simple de ROI por proyecto |
| ROI medio ponderado | `_build_summary` | `beneficio_neto`, `inversion_total` | `sum(beneficio_neto) / sum(inversion_total) * 100` |
| Proyectos activos / finalizados | `FinancialDashboardService.build` | `Proyecto.estado` | Activos: `captacion`, `comprado`, `comercializacion`, `reservado`, `vendido`; finalizados: `cerrado`, `descartado` |
| Distribución por estado | `_build_charts` | `Proyecto.estado` | `count / total * 100` |
| Evolución mensual | `_build_monthly_rows` | `Participacion.fecha_aportacion` / `creado`, `IngresoProyecto.fecha`, `GastoProyecto.fecha` | Agrupación por `TruncMonth` |
| Comparativa inversión vs retorno | `_build_investment_return_summary` | `Participacion`, `calc_inversor_settlement` | `retorno_total`, `beneficio_neto`, `roi_bruto_medio`, `roi_neto_medio` |
| Mejor/peor rentabilidad | `_build_rankings` | `project_metrics.roi`, `project_metrics.beneficio_neto` | Ordenación descendente |
| Alertas financieras | `_build_alerts` | checklist, facturas, justificantes, solicitudes, ROI, sobrecoste | Umbrales: ROI < 0, gasto real > gasto estimado, ausencia de documentos, solicitudes pendientes |

### 2.3 Modelos y campos de origen

- `Proyecto`: `estado`, `precio_propiedad`, `precio_compra_inmueble`, `precio_venta_estimado`, `beneficio_bruto`, `beneficio_neto`, `roi`, `capital_objetivo`, `extra`, `snapshot_datos`, `origen_estudio`, `origen_snapshot`, `datos_economicos`.
- `GastoProyecto`: `fecha`, `categoria`, `concepto`, `importe`, `importe_estimado`, `importe_real`, `estado`, `imputable_inversores`, `pagado`.
- `IngresoProyecto`: `fecha`, `tipo`, `concepto`, `importe`, `importe_estimado`, `importe_real`, `estado`, `imputable_inversores`, `pagado`.
- `Participacion`: `importe_invertido`, `porcentaje_participacion`, `estado`, `fecha_aportacion`, `beneficio_neto_override`, `beneficio_override_data`.
- `InversorPerfil`: `aportacion_inicial_override`, `proyectos_visibles`, `token`.
- `SolicitudParticipacion`: `importe_solicitado`, `estado`, `decision_by`, `decision_at`.
- `Cliente`: `cuota_abonada`, `presente_en_comunidad`.
- `DocumentoProyecto`: `fecha_factura`, `importe_factura`, `categoria`, `usar_dossier`, `es_principal`, `usar_pdf`.
- `JustificanteIngreso` y `FacturaGasto`: vínculo documental para cobros y gastos.
- `Estudio` / `EstudioSnapshot`: `datos` JSON y campos congelados de comité/inversor/económico.
- `GastosProyectoEstimacion`: gastos estimados de adquisición, obra, comercialización y gestión.
- `DatosEconomicosProyecto`: estado operativo, precios reales, impuestos reales, comisión de gestión, gastos de venta, plusvalía, honorarios de agencia.
- `MovimientoEconomicoProyecto` / `MovimientoProyecto`: trazabilidad contable, no fuente principal de los KPIs del dashboard.

## 3. Fuente única de verdad y duplicidades

### 3.1 Canonical

- Proyecto y memoria económica:
  - `core/views.py::_resultado_desde_memoria`
  - `core/views.py::_calc_beneficio_inversor`
  - `core/views.py::pdf_memoria_economica`
- Dashboard ejecutivo:
  - `core/services/financial_dashboard.py::FinancialDashboardService`
- Estudio / simulador:
  - `core/views.py::_metricas_desde_estudio`
  - `core/static/core/simulador.js`
- Landing:
  - `landing/views.py::_roi_memoria`

### 3.2 Duplicidades detectadas

- `ROI`, `beneficio`, `ratio` y `margen` aparecen en backend, frontend y PDFs con la misma semántica general, pero con rutas de fallback distintas.
- `ROI medio` y `ROI medio ponderado` conviven en dashboard; no son el mismo KPI.
- `beneficio_neto` en memoria económica y en liquidación inversor no significa lo mismo:
  - en memoria es beneficio del proyecto;
  - en liquidación es beneficio del inversor.
- `dashboard.js` no duplica negocio; solo formatea y dibuja.

### 3.3 Divergencias documentadas

- `core/views.py::_calc_beneficio_inversor` aplica impuesto de sociedades antes de la retención.
- `core/finance.py::calc_inversor_settlement` no modela impuesto de sociedades; es una versión simplificada para settlement.
- `landing/views.py::_roi_memoria` usa `beneficio / gastos * 100`, sin comisión ni impuestos.
- `core/views.py::_resultado_desde_memoria` usa `inversion_total = gastos_base` si hay gastos, y si no usa adquisición; `pdf_memoria_economica` usa directamente gastos reales/estimados.
- `FinancialDashboardService._build_charts` usa dos porcentajes distintos en la tarjeta de beneficios:
  - barra: `beneficio / max_beneficio`;
  - etiqueta: `beneficio / valor_adquisicion`.
  Esto es una decisión visual, no una coincidencia matemática.

## 4. Validación matemática y económica

### 4.1 Comprobaciones realizadas

- Denominador correcto:
  - ROI de proyecto sobre inversión/gastos según la ruta.
  - ROI inversor sobre capital invertido.
  - Margen sobre valor de transmisión.
- División por cero:
  - tratada en todos los cálculos principales con guardas `> 0`.
- Nulos:
  - `None` y `""` tratados como ausencia en helpers de parseo.
- Negativos:
  - pérdidas no generan comisión ni retención.
  - ROI negativo se conserva y se usa para alertas.
- Cancelaciones / estados intermedios:
  - proyectos `descartado` o `cerrado` quedan fuera del bloque activo.
  - ingresos/gastos estimados vs reales se separan por estado.
- Doble conteo:
  - `_resultado_desde_memoria` evita sumar la compra dos veces cuando ya existe `precio_compra_inmueble` / `precio_propiedad`.
  - `FinancialDashboardService._load_projects` prefetch + filtros evita N+1 obvio.
- Filtros:
  - `fecha_desde`, `fecha_hasta`, `proyecto_id`, `estado`.
- Consistencia multientidad:
  - no existe una capa real de workspace multitenant; la segregación es por permisos de usuario y por filtro de proyecto.

### 4.2 Precisión y redondeo

- La persistencia monetaria usa `DecimalField`.
- Parte de la lógica de negocio convierte a `float` al salir de los helpers.
- JavaScript usa `Number`, `parseFloat` y `Intl.NumberFormat`.
- Se formatea a 2 decimales en moneda y porcentaje en la mayoría de salidas.
- Hay puntos de riesgo:
  - `calc_operacion_economica`, `calc_inversor_settlement`, `seed_demo_kpis`, `audit_kpis`, `recalcular_roi_proyectos`.
  - `recalcular_roi_proyectos.py` convierte `float -> Decimal(str(float(...)))`, que puede arrastrar ruido binario.
- Conclusión de precisión:
  - suficiente para UI y reporting actual;
  - no ideal para contabilidad fina;
  - pendiente centralizar cálculo monetario en `Decimal` extremo a extremo.

## 5. Auditoría SQL / ORM

### 5.1 ORM usado correctamente

- `select_related`:
  - `FinancialDashboardService._load_projects`
  - varias vistas de detalle (`select_related("proyecto")`, `select_related("cliente")`, etc.).
- `prefetch_related`:
  - gastos, ingresos, participaciones confirmadas, checklist del dashboard.
- `annotate`:
  - agrupación mensual con `TruncMonth`.
  - algunos conteos de alertas y listados por proyecto.
- `aggregate`:
  - capital total, contadores y sumas de participaciones.

### 5.2 Riesgos SQL / ORM

- Los `JOIN` múltiples podrían duplicar filas si se mezclara `annotate` sobre relaciones no prefetched.
- `TruncMonth` puede comportarse distinto entre SQLite y PostgreSQL.
- Las comparativas cross-DB no se han ejecutado en este entorno.
- No hay SQL manual en el código de aplicación, así que el riesgo es ORM, no SQL crudo.

## 6. Auditoría de frontend

### 6.1 JavaScript con cálculo real

- `core/static/core/simulador.js`
  - calcula ROI, margen, ratio, colchón, breakeven, comisión y rentabilidades del comité.
  - usa `Number`, `parseNumberEs`, `parseEuro`, `formatEuro`, `formatNumberEs`.
  - riesgo de float y de redondeo visual frente a backend.
- `core/static/core/proyecto.js`
  - autocalcula adquisición, transmisión, comisión, impuesto, ROI, ratio, margen y viabilidad.
  - también calcula liquidaciones y comparativas para inversores.
  - es la segunda gran ruta de cálculo que puede divergir si se cambia backend.
- `core/static/core/dashboard.js`
  - no duplica negocio; solo normaliza payload, formatea y pinta gráficas.

### 6.2 Riesgos detectados

- `parseFloat` / `Number` pueden perder precisión.
- Entradas vacías o strings numéricos europeos requieren parseo defensivo.
- Algunas métricas usan `0` como valor válido y como “ausente”; hay que distinguirlo explícitamente.
- La UI debe seguir siendo un consumidor, no una fuente de verdad.

## 7. PDFs, informes y exportaciones

- `pdf_memoria_economica`:
  - incluye comisión e impuesto de sociedades.
  - utiliza un ROI con denominador de gastos.
- `pdf_estudio_rentabilidad`:
  - muestra el snapshot del estudio y métricas congeladas.
  - el bug de ratio con símbolo de euro se ha corregido.
- `pdf_carta_inversor` y `pdf_certificado_retenciones`:
  - reutilizan `rentabilidad_estimada`, `rentabilidad_inversor_bruta`, `rentabilidad_inversor_neta`, `retencion`, `impuesto_sociedades`.
- `regenerar_dossier_pdfs.py`:
  - reutiliza la misma lógica de memoria y solo cambia la capa de exportación.
- `audit_kpis.py` y `audit_logica_economica.py`:
  - sirven de contraste, no de cálculo canónico.

## 8. Bugs encontrados y correcciones

### 8.1 Bug objetivo corregido

- Problema:
  - `core/templates/core/proyecto.html` mostraba `resultado.ratio_euro` con símbolo `€`.
  - `core/templates/core/pdf_estudio_rentabilidad.html` mostraba `snapshot.kpis.ratio_euro_beneficio` con símbolo `€`.
- Por qué es incorrecto:
  - un ratio es una razón adimensional, no un importe monetario.
- Ejemplo:
  - `1.25` debe verse como `1,25` o `1.25`, no como `1,25 €`.
- Corrección:
  - se ha retirado el símbolo de euro en ambas plantillas.
- Regresión:
  - añadido test en `tests/test_pdf.py`.

### 8.2 Divergencias pendientes

- La capa backend sigue usando `float` en varios helpers financieros.
- Existen varias rutas de ROI según contexto:
  - memoria económica;
  - estudio;
  - liquidación inversor;
  - landing;
  - dashboard.
- No se ha unificado una sola fórmula universal porque hay semánticas distintas por dominio.
- `pip-audit` encontró una vulnerabilidad en `pytest 8.4.2` (`PYSEC-2026-1845`, fix `9.0.3`); no se ha actualizado la dependencia en esta auditoría para evitar un refactor de entorno.

## 9. Escenarios manuales por dominio

### 9.1 Inversiones y proyectos

- Operación con beneficio.
- Operación con pérdidas.
- Financiación parcial.
- Aportaciones parciales.
- Comisión del gestor.
- Gastos y impuestos.
- Proyecto abierto, cerrado y cancelado.
- ROI con inversión cero.
- ROI ponderado.
- Beneficio estimado frente a real.

### 9.2 Hipotecas y financiación

- No existe un motor hipotecario completo.
- Solo hay campos de `% financiación` / `porcentaje_financiación` en simulador, proyecto y PDFs.
- No hay amortización, cuota o TIN/TAE calculados por el sistema.

### 9.3 Gestoría / seguros / inmobiliaria / comunidades

- No hay subsistemas aislados con fórmulas propias.
- Los importes viven como líneas de gasto/ingreso o como campos económicos del proyecto.
- Las categorías de gasto y los campos reales/estimados cubren honorarios, impuestos, comercialización, administración, comunidad, seguros y plusvalía cuando se guardan.

### 9.4 Extremos

- Cero.
- Negativo.
- Nulo.
- Máximo razonable.
- Cambio de estado.
- Empates en rankings.
- Múltiples proyectos.
- Múltiples clientes con override de aportación.

## 10. Reconciliaciones cruzadas

- Pantalla frente a endpoint JSON:
  - el dashboard nuevo usa el mismo payload del servicio.
- Endpoint frente a PDF:
  - misma fuente; diferencias solo de formato y layout.
- Endpoint frente a exportación:
  - `regenerar_dossier_pdfs.py` y `audit_kpis.py` consumen el mismo núcleo.
- Dashboard frente a detalle:
  - comparten `resultado_mem`, pero el dashboard agrega portfolio y rankings.
- Agregados frente a suma de registros:
  - conciliación correcta en el dashboard con `aggregate` y `TruncMonth`.
- Rankings frente al universo:
  - ranking es una vista ordenada del universo filtrado.
- Totales frente a líneas:
  - memoria/PDF suman líneas; el dashboard agrega por proyecto y por mes.
- Empresa frente a workspace:
  - no hay workspace explícito; la separación real es por permisos de usuario.

## 11. Riesgos y decisiones pendientes

### 11.1 Riesgos técnicos

- `float` en negocio financiero.
- Divergencia entre denominadores de ROI según módulo.
- Doble lógica backend/frontend.
- Posibles diferencias SQLite/PostgreSQL en `TruncMonth`.
- Carga creciente del dashboard por `calc_inversor_settlement` por participación y por alertas documentales.

### 11.2 Decisiones pendientes

- ¿Se centraliza toda la aritmética monetaria en `Decimal`?
- ¿Se define una única semántica de ROI por dominio, o se mantienen varias con nombre explícito?
- ¿Se cachea el dashboard financiero por rol y filtros?
- ¿Se unifican los textos de ratio para evitar ambigüedad visual?
- ¿Se crea un motor separado para financiación/hipoteca, o se deja como dato informativo?
- ¿Debe renombrarse `roi_neto_inversor` para dejar claro que usa beneficio bruto / capital objetivo en el estudio?
- ¿Debe el margen de proyectos con devoluciones usar `valor_transmision` bruto o neto de ajustes? La validación ejecutable confirma el uso bruto actual.

## 12. Cobertura y pruebas

### 12.1 Tests existentes relevantes

- `tests/test_finance.py`
- `tests/test_financial_dashboard.py`
- `tests/test_dashboard_data.py`
- `tests/test_dashboard_page.py`
- `tests/test_dashboard_frontend.py`
- `tests/test_pdf.py`
- `core/tests.py`

### 12.2 Nueva regresión añadida

- `tests/test_pdf.py::test_ratio_metrics_are_not_rendered_as_currency_symbols`

### 12.3 Escenarios ya cubiertos por tests

- Comisión sobre beneficio positivo.
- Pérdidas con limitación de capital.
- ROI desde memoria.
- Impuesto de sociedades sobre base neta.
- PDF de memoria con impuesto como gasto extra.
- Estructura del payload del dashboard.
- Filtros y permisos del dashboard.
- Interacción frontend del dashboard.

### 12.4 Escenarios que siguen siendo manuales o pendientes

- Comparación real SQLite vs PostgreSQL.
- Stress test de portfolios muy grandes.
- Simulación de hipoteca real con amortización.
- Seguro/comunidad con liquidación propia.

## 13. Nivel de confianza por módulo

- Alto:
  - `core/services/financial_dashboard.py`
  - `core/views.py` detalle de proyecto, memoria económica, PDF y liquidación
  - `core/finance.py`
  - `tests/test_inversure_calculation_audit.py`
  - `tests` de dashboard, finanzas y PDF
- Medio:
  - `landing/views.py`
  - `core/static/core/proyecto.js`
  - `core/static/core/simulador.js`
  - comandos de auditoría / regeneración
- Bajo:
  - campos legacy del modelo `Proyecto`
  - rutas que mezclan `float` y `Decimal`
  - módulos sin motor económico propio

## 14. Conclusión

Los números del sistema son razonablemente fiables para el uso actual de dashboard, memoria, cartas y PDFs, con estas reservas:

- hay varias rutas de cálculo con semánticas distintas por dominio;
- todavía existe uso de `float` en partes relevantes del backend y del frontend;
- la comparación SQLite/PostgreSQL no se ha podido ejecutar aquí;
- la coherencia visual del ratio ya se ha corregido.

Conclusión operativa:

- fiable para producción en el estado actual;
- confianza alta en el dashboard nuevo y en los cálculos canónicos revisados;
- confianza media en rutas legacy y frontend con lógica duplicada;
- pendiente una futura unificación de precisión y denominadores si se quiere nivel contable.

## 15. Validación ejecutada

- `pytest -q`: 66 passed.
- `ruff check .`: passed.
- `pre-commit run --all-files`: passed.
- `git diff --check`: passed.
- `node --check` sobre todos los `.js` del repo: passed.
- `bandit -q -r core accounts cms landing config tests`:
  - el hallazgo alto de SHA-1 quedó corregido;
  - persisten avisos bajos preexistentes, sobre todo `try/except pass` y `assert_used` en tests.
- `mypy core landing accounts cms config tests`:
  - falla por deuda preexistente amplia en el repo, no introducida por esta auditoría.
- `pip-audit`:
  - ejecutado con red habilitada;
  - reporta 1 vulnerabilidad conocida en `pytest 8.4.2` (`PYSEC-2026-1845`).

### 15.1 Validación ejecutable Inversure

- `tests/test_inversure_calculation_audit.py`: 7 tests nuevos, 7 passed.
- Escenarios validados:
  - proyecto rentable;
  - proyecto con pérdidas;
  - proyecto financiado;
  - proyecto con aportaciones parciales;
  - proyecto cerrado con beneficio real;
  - proyecto con inversión cero;
  - portfolio completo de los cinco escenarios.
- Reconciliación confirmada:
  - detalle de proyecto frente a dashboard, endpoint JSON, PDF y liquidación;
  - `FinancialDashboardService` frente al endpoint `GET /dashboard/data/`;
  - filtros por fecha, proyecto y estado;
  - rankings, series mensuales y alertas coherentes con los datos del repositorio.
- Diferencias documentadas y ahora fijadas por tests:
  - `roi_neto_inversor` del estudio usa beneficio bruto sobre capital objetivo;
  - `roi_neto_tras_impuestos` sí usa el beneficio neto tras impuestos;
  - en pérdidas con devoluciones, el margen usa `valor_transmision` bruto como denominador;
  - `financiacion_pct` sigue siendo metadato y no altera los importes.

### 15.2 Auditor ejecutable de métricas Inversure

- Archivos añadidos:
  - `core/services/inversure_metric_audit.py`
  - `core/management/commands/audit_inversure_metricas.py`
  - `tests/test_inversure_metricas_audit.py`
- Fuente de verdad del recálculo:
  - datos persistidos de `Proyecto`, `GastoProyecto`, `IngresoProyecto`, `Participacion` y `DatosEconomicosProyecto`;
  - no reutiliza `FinancialDashboardService` ni helpers de cálculo visibles como fuente de verdad.
- Corrección objetiva encontrada:
  - el impuesto de sociedades se estaba tratando como porcentaje entero en una ruta del auditor y se corregió para aplicar la tasa como ratio en el cálculo;
  - la métrica expuesta sigue mostrándose en porcentaje.
- Decisiones pendientes documentadas:
  - métricas sin `DatosEconomicosProyecto` quedan como `no_verificable_de_forma_independiente`;
  - `financiacion_pct` se considera metadato y no se reconstruye como KPI financiero.
- Validación ejecutada:
  - `tests/test_inversure_metricas_audit.py`: 11 passed;
  - `pytest -q`: 77 passed.
- Cobertura añadida:
  - recálculo independiente;
  - comparación de detalle, dashboard, endpoint JSON, PDF y liquidación;
  - exportación CSV y Markdown;
  - detección de discrepancias;
  - clasificación de métricas no verificables;
  - escenarios de inversión cero, pérdidas, aportaciones parciales y beneficio cerrado.
