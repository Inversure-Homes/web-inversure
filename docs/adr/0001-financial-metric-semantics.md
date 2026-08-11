# ADR 0001: Semántica financiera antes de refactorizar

## Estado

Propuesto / adoptado como contrato documental.

## Contexto

Inversure muestra métricas financieras en varias superficies:

- detalle del proyecto;
- dashboard ejecutivo;
- PDF de memoria económica;
- PDF de estudio de rentabilidad;
- liquidación del inversor;
- auditor independiente.

Esas superficies no comparten todavía una única definición canónica para todas las métricas.

En particular:

- algunas vistas priorizan snapshots históricos;
- otras usan cálculo vivo;
- otras aplican fallbacks a datos estimados cuando faltan confirmaciones reales;
- varias fórmulas siguen en `float` y otras en `Decimal`;
- los nombres visibles no siempre coinciden con la semántica financiera exacta.

Refactorizar o migrar a `Decimal` sin documentar primero esta semántica convertiría los cambios en una reescritura implícita de reglas de negocio.

## Alcance

Este ADR cubre únicamente la documentación y el contrato semántico actual de las métricas financieras.

No cambia:

- fórmulas;
- redondeos;
- modelos;
- migraciones;
- templates;
- vistas;
- lógica del auditor;
- configuración de producción.

## Decisión

Antes de unificar cálculos o migrar tipos numéricos:

1. Documentamos la semántica actual en `docs/financial-domain.md`.
2. Conservamos las diferencias conocidas entre snapshot, live y fallback.
3. Posponemos la migración general a `Decimal` hasta que exista un contrato explícito por métrica.
4. Validamos futuros cambios con tests de caracterización y comparación cruzada entre superficies.

## Motivo

La prioridad es reducir riesgo.

Sin un contrato explícito:

- un “arreglo” puede cambiar el significado de una métrica sin que se note;
- dos superficies pueden seguir mostrando cifras distintas aunque ambas sean internamente coherentes;
- el auditor puede dejar de coincidir con la experiencia visible si cambia la definición sin coordinación.

## Consecuencias

### Positivas

- Las siguientes PRs pueden ser pequeñas y verificables.
- Cada cambio financiero tendrá un punto de comparación claro.
- El auditor puede distinguir mejor entre:
  - error real de cálculo;
  - diferencia legítima de definición;
  - fallback;
  - dato histórico.

### Negativas

- No se unifican todavía definiciones ambiguas.
- No se fuerza una migración global a `Decimal`.
- Algunas duplicidades seguirán existiendo temporalmente.

## Reglas para cambios futuros

Todo cambio sobre una métrica financiera debe:

- indicar si afecta a snapshot, live o ambos;
- explicar la superficie visible que se modifica;
- incluir tests de regresión;
- no asumir una definición nueva sin decisión de negocio;
- preservar el comportamiento antiguo cuando no exista decisión explícita.

## Métricas y decisiones pendientes

Las siguientes decisiones no se resuelven en este ADR:

- `roi_snapshot` frente a `roi_live`;
- `MEMORIA_BENEFICIO_NETO_DESDE_TRANSMISION`;
- `CUENTAS_PARTICIPACION_LIMIT_LOSS_TO_CAPITAL`;
- uso real de `financiacion_pct`;
- estados legacy del dominio.

Esas decisiones quedan registradas en `docs/financial-domain.md` como:

`DECISIÓN DE NEGOCIO PENDIENTE`

## Validación

La validación mínima de cualquier cambio financiero futuro será:

- tests unitarios y de integración relevantes;
- comparación detalle / dashboard / PDF memoria / PDF estudio / liquidación / auditor;
- revisión explícita de redondeo y fallback;
- revisión de impacto sobre snapshots históricos.

## Referencias

- `docs/financial-domain.md`
- `core/views.py`
- `core/services/financial_dashboard.py`
- `core/services/inversure_metric_audit.py`
- `core/finance.py`
