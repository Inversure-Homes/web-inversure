# ADR 0002: Base común para migración progresiva a Decimal

## Estado

Aceptado como base técnica.

## Contexto

Inversure sigue calculando métricas financieras con una mezcla de `float`, `Decimal` y conversiones ad hoc.
Eso dificulta:

- migrar con seguridad a un tipo numérico coherente;
- evitar conversiones como `Decimal(float)`;
- centralizar reglas de redondeo;
- preparar futuras validaciones sobre importes y porcentajes.

Sin una capa común, cada PR de migración tendría que repetir la misma lógica de conversión y redondeo.

## Decisión

Se introduce `core/decimal_utils.py` como infraestructura reusable y aislada que ofrece:

- conversión segura a `Decimal`;
- cuantización monetaria explícita;
- cuantización porcentual explícita;
- conversión entre porcentaje y ratio;
- constantes `Decimal` básicas para evitar literales ambiguos.

Esta capa no se conecta todavía a las fórmulas financieras existentes.

## Alcance

Este ADR no cambia comportamiento de producción.

No modifica:

- fórmulas financieras;
- redondeos observables;
- vistas;
- templates;
- PDFs;
- liquidaciones;
- auditor;
- modelos;
- migraciones;
- configuración de producción.

## Política de conversión

`to_decimal()` acepta únicamente:

- `Decimal`;
- `int`;
- `float`;
- `str`;
- `None` con `default` explícito.

Reglas:

- `float` se convierte mediante su representación textual;
- `bool` se rechaza explícitamente;
- valores no finitos se rechazan;
- valores inválidos solo se sustituyen cuando existe un `default` explícito;
- el resultado siempre es `Decimal`.

## Política de redondeo preparada

La base común define dos cuantizaciones técnicas:

- dinero: `0.01`;
- porcentaje interno: `0.0001`.

Ambas usan `ROUND_HALF_UP` dentro de un contexto local, para no alterar el contexto global del proceso.

Importante:

- esta política es preparatoria;
- no sustituye todavía el redondeo real usado por las superficies de producción;
- la adopción en producción se hará métrica a métrica en PRs posteriores.

## Consecuencias

### Positivas

- Las siguientes migraciones podrán ser pequeñas y verificables.
- Se evita repetir conversiones y cuantizaciones.
- Se reduce el riesgo de errores al pasar de `float` a `Decimal`.

### Negativas

- Durante un tiempo convivirán dos estilos numéricos.
- El comportamiento de producción no cambia todavía.
- La unificación real requerirá PRs posteriores y tests de caracterización.

## Uso futuro previsto

Los próximos cambios financieros deberán:

- importar helpers desde `core.decimal_utils`;
- convertir entradas antes de operar;
- cuantizar explícitamente antes de exponer valores;
- no introducir nuevas conversiones `Decimal(float)`;
- validar el impacto con tests de regresión.

## Validación

La validación de esta capa común es puramente técnica:

- tests unitarios aislados;
- suite completa del proyecto;
- lint y formato;
- comprobación de que no se altera ningún resultado observable.
