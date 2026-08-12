# Auditoría de Inversure

Fecha: 12 de agosto de 2026 · Revisión sobre `main` (`22d3cc1`)

## Alcance

Revisado: 32.600 líneas de Python (`core`, `sorteo`, `accounts`, `landing`,
`config`), la configuración de despliegue, los modelos de datos personales y
las plantillas de las superficies públicas. Cuatro ejes: seguridad y permisos,
corrección de los cálculos, salud del código y cumplimiento.

**No** revisado con profundidad: las 83.000 líneas de JavaScript, la lógica de
Wagtail y el detalle de cada una de las 190 funciones de `core/views.py`.
Cuando un hallazgo no he podido confirmarlo desde fuera, lo digo.

---

## Gravedad alta

### A1 · Un inversor puede modificar las cifras económicas del proyecto — CERRADO

`core/views.py:6044` — `inversor_beneficio_update`, servida en
`/app/inversor/<token>/beneficio/<id>/`.

`accounts/middleware.py:70` exime del login toda ruta que empiece por
`/app/inversor/`, porque ahí vive el portal del inversor y el token hace de
credencial. Esa exención alcanza también a este endpoint, que **escribe**:

- `participacion.beneficio_neto_override` y `beneficio_override_data` — el
  beneficio, la retención y el neto a cobrar de esa participación;
- `proyecto.extra["beneficio_operacion_override"]` — el **beneficio bruto, la
  comisión, el impuesto de sociedades y su tipo del proyecto entero**.

El formulario solo se pinta con `internal_view` (`inversor_portal.html:658`),
o sea para uso interno. Pero esconderlo en la interfaz no cierra el endpoint:
basta un POST.

Comprobado en producción sin tocar datos reales, con un token inventado:

```
/app/inversor/token-inventado/                     404   ← la vista se ejecuta
/app/inversor/token-inventado/beneficio/1/         404   ← la vista se ejecuta
/app/inversores/                                   302   ← redirige al login
/app/clientes/                                     302   ← redirige al login
```

El 404 frente al 302 lo confirma: esas dos rutas corren **sin autenticar**.

**Impacto.** Cualquiera que tenga el enlace del portal de un inversor —él
mismo, quien reenvíe ese correo, quien use su ordenador— puede alterar cifras
a nivel de proyecto que se muestran a los **demás** inversores del mismo
proyecto y en la memoria económica.

**Arreglado** el 12/08/2026. La ruta pasa a
`/app/inversores/<perfil_id>/beneficio/<participacion_id>/`, fuera de la zona
exenta, y la vista exige `_user_can_edit_project`. La ruta antigua ya no
resuelve. Cinco pruebas lo fijan, incluidas las dos que importan: sin permiso
no se escribe nada, y quien gestiona el proyecto sigue pudiendo.

### A2 · La clave que cifra los DNI y los IBAN — DESCARTADO

`core/security.py:29` y `config/settings.py:34`:

```
SENSITIVE_DATA_KEY  →  si está vacía, usa SECRET_KEY
SECRET_KEY          →  si está vacía, usa "django-insecure-cambia-esto-en-produccion"
```

Si en Render no está definida ninguna de las dos variables, el DNI, el IBAN, el
teléfono y la dirección postal de todos los clientes están cifrados con una
cadena que está escrita en el repositorio.

**Comprobado el 12/08/2026**: las variables están puestas en Render. Los datos
sensibles están cifrados con una clave real, no con la constante del
repositorio. **No hay problema.**

Queda una recomendación, no un hallazgo: que la aplicación **se niegue a
arrancar** sin esas variables cuando `DEBUG` es falso. Hoy el sistema está bien
configurado, pero nada impide que un servicio nuevo —una copia de pruebas, una
migración de hosting— arranque sin ellas y cifre con la constante pública sin
que nadie se entere.

### A3 · Fallo silencioso al descifrar — CERRADO

`core/security.py:58` — al descifrar, si el token no es válido:

```python
except InvalidToken:
    return value          # devuelve el texto cifrado tal cual
```

Como la clave de cifrado cae por defecto en `SECRET_KEY`, cambiarla —algo que
se hace ante una filtración, y que parece inofensivo— deja todos los campos
sensibles ilegibles. Y no salta ningún error: las fichas empiezan a mostrar
`enc::gAAAAA…` y nadie se entera hasta que alguien lo mira.

Peor: `encrypt_value` no vuelve a cifrar lo que ya empieza por `enc::`, así que
un guardado posterior tampoco lo arregla.

**Matizado tras comprobar el entorno.** Con `SENSITIVE_DATA_KEY` puesta, la
clave de cifrado ya no depende de la de firma: rotar `SECRET_KEY` **no** rompe
los datos. Eso rebaja mucho la gravedad.

Lo que sigue en pie es el fallo silencioso: si algún día se rota la
`SENSITIVE_DATA_KEY` —o se restaura una copia de la base de datos en un entorno
con otra clave— los campos se muestran como `enc::gAAAAA…` sin que salte ningún
error. **Arreglo:** que un fallo al descifrar quede al menos registrado en el
log en vez de devolver el texto cifrado como si fuera el dato.

**Arreglado** el 12/08/2026: el fallo se registra con `log.error` señalando la
causa probable. Sigue devolviendo el cifrado para que un dato ilegible no tumbe
la ficha entera, pero deja de ser invisible.

---

## Gravedad media

### M1 · 24 rutas de `core` sin control propio de permisos — CERRADO

De 62 rutas, 38 comprueban permisos y 24 no: dependen solo del middleware, que
exige estar autenticado con **cualquier** permiso del ERP. Es la misma clase de
agujero que ya cerramos en estudios y simulador.

Las que más pesan:

| Ruta | Qué permite |
|---|---|
| `/app/clientes/` · `/app/clientes/nuevo/` · `/app/clientes/editar/<id>/` | ver y editar la cartera de clientes |
| `/app/clientes/importar/` | importación masiva |
| `/app/inversores/` | ver todos los inversores |
| `/app/inversores/<id>/portal/config/` | cambiar qué ve un inversor y su aportación |
| `/app/inversores/<id>/comunicaciones/send/` | **enviar correos a inversores** |
| `/app/inversores/<id>/documentos/` y `.../borrar/` | subir y borrar documentos |
| `/app/dashboard/data/` | los datos económicos agregados |

**Arreglado** el 12/08/2026. Tres helpers —`_user_can_view_clientes`,
`_user_can_view_inversores` y `_user_can_view_proyectos`— delegando en
`resolve_permissions`, que es la misma función con la que `home.html` decide si
enseña cada tarjeta. Aplicados a 17 vistas; las de JavaScript devuelven 403 en
JSON y no un 302, que llegaría como HTML donde se espera JSON.

De 62 rutas quedan 7 sin control propio, y las 7 son correctas: seis del portal
del inversor, que van por token —esa es su credencial—, y el service worker,
que es un `.js` sin datos. Hay una prueba que cruza `urls.py` con el cuerpo de
cada vista y falla si aparece cualquier otra.

**Cambia quién entra**, y conviene decidirlo a conciencia: el rol **comercial**
tiene `can_proyectos` pero no `can_clientes` ni `can_inversores`. El menú ya le
escondía esas dos tarjetas; lo que había es que el servidor le dejaba entrar
escribiendo la URL. Si un comercial debe gestionar clientes, lo que hay que
cambiar es la tabla de permisos de `accounts/utils.py`, no reabrir la puerta en
las vistas.

### M2 · El PIN del portal del inversor — CERRADO

`core/views.py:5923` validaba el PIN con `check_password` sin contar fallos.
`django-axes` protege el formulario de acceso del ERP, no este. Un PIN es un
secreto corto: sin bloqueo, se prueba entero.

**Arreglado** el 12/08/2026. Cinco intentos fallidos cada quince minutos,
contados contra el modelo `IntentoPinPortal` —la caché de Django es por proceso
y con varios workers cada uno llevaría su cuenta—. El bloqueo frena también el
PIN correcto, o bastaría con acertar al sexto.

Se cuenta por **(inversor, IP)** y no solo por inversor: bloquear por inversor
dejaría que cualquiera echase al legítimo de su propio portal fallando cinco
veces. No para un ataque repartido entre muchas IP, pero sí el caso realista.

### M3 · Documentos subidos sin validar — CERRADO

`core/views.py:6014` guarda lo que llegue: sin comprobar extensión ni tipo de
contenido, hasta 25 MB.

*Corregido a la baja tras revisarlo mejor:* escribí que el enlace
`{{ d.signed_url|default:d.archivo.url }}` podía caer en una URL sin firmar y
sin caducidad. En realidad `_apply_project_signed_url` se llama sobre todos los
documentos del inversor (`core/views.py:5442` y `:5881`), así que la ruta normal
siempre va firmada. El respaldo sin firmar solo aparecería si fallase la propia
firma. Queda como detalle a limpiar, no como fuga.

**Arreglado** el 12/08/2026 lo que sí era un hueco: `comprobar_fichero` valida
extensión, tamaño y tipo declarado en los cuatro puntos de subida —documentos
del inversor, facturas de gasto, justificantes de ingreso y documentos de
proyecto—. La lista es de permitidos y no de prohibidos, porque las de
prohibidos siempre se quedan cortas. Lo que evita: que alguien deje un `.html`
o un `.svg` con JavaScript en un sitio que después se sirve desde nuestro
dominio.

### M4 · Persistencia de los documentos — DESCARTADO

`config/settings.py:288` deja `MEDIA_ROOT` en el disco local, que en Render es
efímero, y `/media/` da 404 en producción. Eso habría significado perder los
documentos en cada despliegue.

**Comprobado el 12/08/2026**: las variables de AWS están puestas, así que los
ficheros van a S3 y persisten. **No hay problema.**

### M5 · La política de privacidad no cumple el artículo 13 del RGPD

`landing/templates/landing/privacidad.html` tiene 16 líneas para una empresa
que guarda DNI, IBAN, teléfono y dirección postal. Faltan: identidad completa
del responsable (razón social, NIF, domicilio), base jurídica de cada
tratamiento, categorías de datos, destinatarios, transferencias
internacionales —hay S3—, plazos de conservación y la vía de reclamación ante
la AEPD.

### M6 · No hay borrado ni anonimización de datos personales

No encontré nada de supresión ni de plazos de conservación. El derecho de
supresión (art. 17) hoy solo puede ejercerse borrando a mano desde el admin, lo
que además choca con las claves protegidas de participaciones y liquidaciones.

### M7 · Django fuera de soporte — CERRADO

`requirements.txt` fijaba `Django==4.2.30`, cuyo soporte extendido terminó en
abril de 2026: sin parches de seguridad.

**Actualizado a 5.2.17 LTS** el 12/08/2026, con soporte hasta abril de 2028.
Probado en un entorno aparte y ejecutando todo contra las dos versiones: 462
pruebas en verde en ambas, sin migraciones nuevas, `collectstatic` correcto y
los mismos códigos de respuesta en el 2FA, el admin y el CMS. El único punto
que lo impedía era `STATICFILES_STORAGE`, que desapareció en la 5.1 y se ignora
en silencio; sustituido por `STORAGES`, que vale para las dos.

Verificado en producción: portada, política, noticias y `healthz` en 200; ERP,
admin y CMS redirigiendo al login; y los estáticos servidos con su hash, que es
lo que prueba que el manifiesto se generó.

`django-auditlog` (2.3.0 → 3.4.1) y `django-two-factor-auth` (1.15.2 → 1.18.1)
actualizadas también el 12/08/2026, en commits separados. auditlog aporta cinco
migraciones sobre una tabla de 10.703 filas, que se aplican en segundos;
verificado en producción por la columna «Correlation ID» del admin, que solo
existe después de migrar, y porque el contador sigue subiendo. De
two-factor-auth se comprobó lo que ninguna prueba mira: que un dispositivo TOTP
existente sigue validando, con el mismo código generado en las dos versiones.

---

## Deuda técnica

### D1 · `core/views.py`: 9.350 líneas y 190 funciones

Vistas, helpers de cálculo, generación de PDF, envío de correo y lógica de
negocio en el mismo fichero. No es un fallo, pero es lo que hace que un cambio
pequeño obligue a leer mucho, y es la razón de fondo de que 24 rutas se
quedaran sin comprobar permisos: no se ven.

### D2 · Dinero en `float`: fragilidad, no un fallo de hoy

197 usos de `float()` sobre importes en `core`. Lo medí con cifras vuestras:

```
Comisión 10 % sobre 187.432,17 €     diferencia 0,00
Impuesto 25 % sobre  62.477,39 €     diferencia 0,00
Reparto entre 7 de   45.891,33 €     diferencia 0,00
Sumar 0,10 € diez mil veces  →  Decimal 1000.00 · float 1000.0000000001588
```

A vuestra escala no está torciendo ninguna cifra. El error aparece acumulando
muchas operaciones, y la presentación redondea a dos decimales. Lo anoto como
fragilidad, no como urgencia.

### D3 · `_safe_float` convierte un dato inválido en «0 €»

`core/views.py:2585` devuelve el valor por defecto ante cualquier entrada que no
sepa interpretar. En una cifra económica, un cero silencioso miente más que un
error. Esto sí merece revisarse antes que D2.

### D4 · Cobertura desigual

446 tests, y muy buenos en la parte financiera y del sorteo. Pero
`core/views.py` tiene 9.350 líneas y `core/tests.py` 818: casi todo lo probado
del ERP entra por los tests de dashboard y de auditoría de métricas, no por las
vistas.

---

## Lo que está bien

No todo son avisos. Hay decisiones que no son habituales y que conviene no
perder:

- **Cifrado a nivel de campo** para DNI, IBAN, teléfono y dirección, con hash
  aparte para poder buscar sin descifrar. Muy poca gente hace esto.
- **Cabeceras de seguridad completas**: HSTS un año con preload y subdominios,
  `nosniff`, `X-Frame-Options: DENY`, cookies seguras y `HttpOnly`, redirección
  a HTTPS, `Referrer-Policy: same-origin`.
- **2FA obligatorio** para entrar al ERP, y `django-axes` con bloqueo a los
  cinco intentos en el login.
- **Registro de auditoría** sobre los modelos que mueven dinero: proyectos,
  gastos, ingresos, facturas y clientes.
- **Una herramienta propia de auditoría de métricas** de 2.050 líneas que
  contrasta que el dashboard, la ficha del proyecto, el PDF y las liquidaciones
  digan lo mismo, con su comando de gestión. Es raro encontrarse esto y es
  exactamente lo que evita que las cifras se separen entre pantallas.
- **Sin migraciones pendientes** y una suite que pasa entera.

---

## Estado a 12 de agosto de 2026

| | |
|---|---|
| A1 · Edición del beneficio sin login | **cerrado** |
| A2 · Clave de cifrado | **descartado** — variables puestas |
| A3 · Fallo silencioso al descifrar | **cerrado** |
| M1 · Rutas sin control de permisos | **cerrado** |
| M2 · PIN sin límite de intentos | **cerrado** |
| M3 · Documentos sin validar | **cerrado** |
| M4 · Persistencia de documentos | **descartado** — S3 activo |
| M5 · Política de privacidad | abierto |
| M6 · Sin borrado ni retención de datos | abierto |
| M7 · Django fuera de soporte | **cerrado** |
| D1–D4 · Deuda técnica | abierto |

**Por dónde seguiría**, ahora que los dos sustos han quedado descartados:

1. **M5 y M6**, que son cumplimiento y no dependen de nosotros: una política de
   privacidad seria y un procedimiento de supresión. Guardáis DNI e IBAN.
2. **M2**, el límite de intentos del PIN. Es pequeño y cierra la única puerta
   que queda con un secreto corto detrás.
3. **A3 y M3**, que son endurecimiento.
4. **D1–D4**, cuando haya aire.
