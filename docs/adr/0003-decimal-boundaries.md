# ADR 0003: Fronteras numéricas entre Decimal interno y float público

## Estado

Aceptado como contrato documental.

## Contexto

Inversure aún convive con tres capas numéricas:

- aritmética interna con `Decimal` en helpers técnicos y servicios nuevos;
- fronteras públicas que siguen devolviendo `float` por compatibilidad;
- coerciones legacy que aceptan `None`, cadenas vacías y algunos valores atípicos según la superficie.

Sin documentar esta separación, un refactor numérico puede cambiar el contrato visible sin tocar las fórmulas.

## Decisión

La política numérica del proyecto se describe así:

1. La recomendación es hacer los cálculos financieros con `Decimal` dentro del dominio cuando la superficie lo permita.
2. Toda entrada externa debe convertirse explícitamente antes de operar.
3. Las salidas públicas siguen usando `float` cuando ese es el contrato observable ya existente.
4. No se introduce `Decimal(float_value)` directamente.
5. No se añaden `round()` ni `quantize()` en el dominio salvo decisión explícita y documentada.
6. La política de coerción legacy se conserva en las fronteras que ya la admiten, pero no se generaliza a helpers comunes si eso altera el contrato actual.

## Definiciones

### Aritmética interna con `Decimal`

Es toda operación que:

- suma, resta, multiplica o divide importes o porcentajes;
- decide clamps financieros;
- calcula ROI, márgenes, retenciones o beneficio neto;
- debe preservar precisión monetaria antes de salir de la capa de dominio.

### Frontera pública

Es el punto donde el valor deja de ser una magnitud interna y pasa a:

- una respuesta JSON;
- un `dict` o dataclass que ya forma parte del contrato observable;
- contexto de plantilla;
- salida de comando;
- formato visual que depende de un tipo público concreto.

En esas fronteras puede ser correcto volver a `float` si el contrato histórico ya lo usa.

### Coerción legacy

Es la compatibilidad que conserva el comportamiento antiguo de algunas funciones:

- `None` y `""` pueden convertirse en cero o en ausencia de valor según la función;
- cadenas inválidas no deben inventarse como un número válido;
- booleanos solo se preservan cuando la función actual ya los acepta por compatibilidad histórica.

### Política de redondeo

El proyecto no debe añadir `round()` ni `quantize()` de forma ad hoc.

Si una superficie necesita redondeo explícito, debe:

- estar documentada;
- usar una decisión de negocio verificable;
- apoyarse en una infraestructura común ya existente;
- no mezclarse con un refactor numérico sin especificación.

## Política de conversión

### Desde tipos externos a `Decimal`

La entrada numérica debe convertirse antes de operar cuando provenga de:

- ORM;
- snapshot;
- request/querystring;
- `settings`;
- payloads JSON;
- datos legacy de vistas o PDFs.

La conversión segura debe preferir `core.decimal_utils.to_decimal()` o la lógica de compatibilidad mínima ya existente en la propia frontera.

Reglas actuales de `core.decimal_utils.to_decimal()`:

- acepta `Decimal`, `int`, `float` y `str`;
- convierte `float` mediante representación textual;
- trata `None` y cadenas vacías/inválidas como error si no se pasa `default`;
- si se pasa `default`, devuelve ese `default` convertido;
- rechaza `bool` como número válido por defecto;
- no usa `Decimal(float_value)`.

### De `Decimal` a `float`

Solo debe hacerse en la frontera donde el contrato observable ya es `float`.

Hoy eso ocurre, entre otros, en:

- `core.finance.calc_operacion_economica()`;
- `core.finance.calc_inversor_settlement()`;
- partes del dashboard que exponen ratios y porcentajes legacy;
- superficies visuales que formatean a texto a partir de valores ya calculados.

No debe usarse `float()` para volver a entrar en la aritmética interna si ya existe una ruta `Decimal` disponible.

## Ejemplos concretos

### `calc_operacion_economica`

La función ya actúa como frontera de compatibilidad:

- recibe valores numéricos legacy;
- convierte internamente a `Decimal`;
- calcula comisión y beneficio neto sin cambiar las fórmulas;
- retorna `OperacionEconomica` con campos `float`.

Ejemplo de contrato actual:

```python
result = calc_operacion_economica(beneficio_bruto="1000.10", comision_pct="12.5")
# result.beneficio_bruto == 1000.10
# result.comision_eur == 125.0125
# result.beneficio_neto_total == 875.0875
# tipos públicos: float
```

Compatibilidad legacy actual:

```python
calc_operacion_economica(beneficio_bruto=True, comision_pct=False)
# True -> 1.0, False -> 0.0 por compatibilidad histórica en esta frontera
```

### `calc_inversor_settlement`

La función mantiene una frontera pública basada en `float`, pero su aritmética interna ya puede apoyarse en `Decimal`:

- capital, total invertido del proyecto y beneficio de operación se convierten antes de operar;
- ratio, retención, neto y total a percibir se calculan internamente;
- el resultado público vuelve a `float` al construir el `dict`.

Ejemplo de contrato actual:

```python
result = calc_inversor_settlement(
    capital_invertido=Decimal("1000.50"),
    total_proyecto_invertido="2000",
    beneficio_bruto_operacion=1500.1,
    comision_pct=10,
    retencion_pct=20,
    limit_loss_to_capital=False,
)
# result["capital_invertido"] == 1000.5
# result["beneficio_inversor"] == 675.3825225
# result["retencion"] == 135.0765045
# result["total_a_percibir"] == 1540.806018
# tipos públicos: float
```

Compatibilidad legacy actual:

```python
calc_inversor_settlement(
    capital_invertido=True,
    total_proyecto_invertido=2,
    beneficio_bruto_operacion=True,
    comision_pct=False,
    retencion_pct=True,
    limit_loss_to_capital=False,
)
# True -> 1.0 y False -> 0.0 en esta frontera legacy
```

### `core/services/financial_dashboard.py`

El servicio del dashboard ya usa una mezcla intencional:

- `to_decimal(..., default=ZERO)` para sumar importes y capitales con precisión;
- `calc_inversor_settlement()` como frontera de compatibilidad para el reparto por inversor;
- `float()` solo en puntos donde el payload visible ya espera ese tipo o donde la función pública llamada lo exige.

Ejemplos de frontera actual:

```python
capital_objetivo = to_decimal(core_views._capital_objetivo_desde_memoria(project, snapshot), default=ZERO)
capital_captado = sum((to_decimal(part.importe_invertido, default=ZERO) for part in participaciones_confirmadas), ZERO)
settlement = calc_inversor_settlement(...)
roi_bruto = settlement["roi_bruto_pct"]  # float público
```

En el payload del dashboard, los importes monetarios siguen en `Decimal` cuando la superficie así lo viene consumiendo, mientras que algunos ratios y porcentajes permanecen en `float` por contrato legado.

## Consecuencias

### Positivas

- Se pueden migrar funciones financieras de forma gradual.
- La frontera entre dominio y presentación queda explícita.
- El comportamiento legacy se conserva donde ya existe.

### Negativas

- Durante un tiempo convivirán `Decimal` y `float`.
- No todas las superficies pueden unificarse sin renegociar contrato.
- Los cambios de redondeo siguen requiriendo decisión explícita.

## Reglas orientativas para futuros PRs

Si un PR posterior decide tocar una métrica numérica, conviene que:

- indicar si modifica una frontera pública o solo aritmética interna;
- demostrar equivalencia con tests;
- no usar `Decimal(float_value)`;
- no introducir `round()`/`quantize()` nuevos sin justificación;
- mantenga `float` en las fronteras públicas ya existentes salvo decisión de negocio.

## Validación

La validación esperable para esta política es documental y técnica:

- suite completa del proyecto;
- linters y formato;
- tests de caracterización de las funciones afectadas;
- comparación de superficies cuando se toque una frontera pública.
