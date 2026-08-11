# App de sorteos

Rifas ocasionales de inmuebles (Ley 13/2011) integradas en el ERP.

## Mapa

| Fichero | Qué hace |
| --- | --- |
| `models.py` | Sorteo (cuelga de `core.Proyecto`), Papeleta, Pedido, Interesado, ActaSorteo |
| `services.py` | Reserva atómica, confirmación de pago, alta manual, acta |
| `notaria.py` | Cierre de venta, huella del listado y relación para el notario |
| `calculadora.py` | Escenarios y dimensionado. Funciona con y sin sorteo creado |
| `economia.py` | Puente con `core.Proyecto`: ingresos por día, gastos, demanda |
| `correo.py` | Alta, justificante y aviso al ganador |
| `views.py` / `urls.py` | Portal público en `/sorteo/` |
| `views_erp.py` / `urls_erp.py` | Panel interno en `/app/sorteos/` |

## Los cinco puntos que sostienen esto

**La reserva es atómica.** `select_for_update(skip_locked=True)` dentro de una
transacción: dos compradores simultáneos se llevan papeletas distintas sin
hacer cola. En SQLite, que no lo soporta, cae al bloqueo de escritura, que es
igual de correcto aunque más lento.

**El importe lo calcula el servidor.** El cliente manda una cantidad, nunca un
precio.

**El consentimiento se guarda con el pedido**: versión de las bases, fecha e
IP. Se valida en el servidor, no solo en el formulario.

**El sorteo no se genera, se transcribe.** El acta notarial se registra y se
rechaza cualquier número que no conste vendido.

**El listado se sella.** Al cerrar la venta se calcula un SHA-256 del listado
canónico y se publica. Quien reciba la relación puede recalcularlo.

## Antes de abrir la venta

1. **Autorización de la DGOJ** cargada en el organizador. Sin ella, el sorteo
   se queda en borrador y la web muestra la lista de espera, no la compra.
2. **Completar las bases**: los huecos salen en rojo en `/sorteo/bases/`.
3. **Pasarela de pago.** Hoy hay una simulada en `views.pago_pendiente`. Al
   integrar Stripe o Redsys, el pago debe confirmarse **por webhook**, nunca
   por la redirección de vuelta.
4. **Cron de reservas** en Render: `python manage.py liberar_reservas` cada
   pocos minutos. Sin él, quien no termina de pagar bloquea papeletas hasta que
   alguien visite la web.
5. **Revisar el plan de Render**: esto mete tráfico público en la misma
   aplicación que el ERP.
6. **Límite de peticiones** en `/sorteo/reservar/`: hoy un script puede
   bloquear papeletas en bucle.

## Secuencia de una rifa

```
estudio (calculadora libre)
  → comprar o asegurar el inmueble
  → solicitar autorización a la DGOJ
  → cargar datos y bases, abrir venta        [estado: en_venta]
  → vender
  → cerrar venta y sellar listado            [estado: cerrado]
  → entregar la relación al notario
  → registrar el acta                        [estado: sorteado]
  → entregar el premio
```

## Pruebas

```bash
python manage.py test sorteo
```

Cubren lo que cuesta dinero si falla: vender dos veces la misma papeleta,
cobrar sin consentimiento, duplicar un pago, publicar un ganador que no compró
y que la huella del listado detecte cualquier cambio.
