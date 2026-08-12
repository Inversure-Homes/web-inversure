# Protección de datos · borrador para revisión jurídica

**Esto no es una política de privacidad válida.** Es un borrador y un
inventario técnico para que quien lleve vuestra asesoría jurídica trabaje sobre
algo concreto en lugar de empezar de cero. Todo lo marcado con `[...]` son
decisiones que no me corresponden.

Lo que sí aporta este documento y no puede salir de otro sitio: **qué datos
guarda el sistema de verdad, dónde, cifrados o no, quién puede verlos y a qué
terceros salen**. Eso lo he sacado del código, no de suposiciones.

Fecha: 12 de agosto de 2026 · Sobre `main` (`98539a5`)

---

## 1. Qué datos personales hay

### Categoría especialmente sensible: clientes e inversores

`core.Cliente` es el modelo con los datos más delicados. Está **cifrado a nivel
de campo** con Fernet, y cada campo cifrado tiene un hash aparte para poder
buscar sin descifrar:

| Campo | Cifrado |
|---|---|
| `dni_cif` | sí |
| `email` | sí |
| `telefono` | sí |
| `iban` | sí |
| `direccion_postal` | sí |
| `nombre`, `tipo_persona` | no |

`core.InversorPerfil` añade un token de acceso al portal (256 bits) y un hash
del PIN. `core.Participacion` vincula cliente y proyecto con importes.

### Documentos subidos

`core.DocumentoInversor` y `core.DocumentoProyecto` guardan ficheros que en la
práctica contienen datos personales: DNI escaneados, contratos, escrituras,
justificantes bancarios. Se almacenan en S3 y se sirven con URL firmada y
caducidad.

### Rifa

`sorteo.Interesado` (lista de espera: nombre, email, teléfono, provincia, IP) y
`sorteo.Pedido` (nombre, email, teléfono, IP, y la prueba del consentimiento:
versión de bases aceptada, fecha y hora). `sorteo.SolicitudReenvio` guarda email
e IP de cada petición de reenvío.

### Web y sistema

`landing.LandingLead` (nombre, email, teléfono de quien rellena un formulario),
`accounts.UserConnectionLog` y `accounts.UserSession` (IP de los empleados),
`core.IntentoPinPortal` (IP de intentos de PIN) y el registro de auditoría, que
guarda quién cambió qué y cuándo.

---

## 2. Quién puede ver cada cosa

Esto se cerró durante la auditoría del 12/08/2026 y ahora es exacto:

| Área | Permiso | Quién lo tiene por rol |
|---|---|---|
| Clientes (DNI, IBAN) | `can_clientes` | dirección y administración |
| Inversores y su posición | `can_inversores` | dirección y administración |
| Proyectos y panel económico | `can_proyectos` | dirección, comercial, marketing, moderadores |
| Estudios y simulador | `can_estudios` / `can_simulador` | según rol |

El portal del inversor es aparte: se entra con un enlace que lleva un token de
256 bits, opcionalmente con un PIN, y **no** requiere cuenta de usuario. Cada
inversor solo ve lo suyo.

Todo acceso al ERP exige doble factor.

---

## 3. A qué terceros salen los datos

Esto es lo que hoy **falta por completo** en la política publicada, y es
obligatorio según el artículo 13.1.e y 13.1.f del RGPD.

| Tercero | Para qué | Dónde | Datos |
|---|---|---|---|
| **Render** | alojamiento y base de datos | `[confirmar región: si es Oregón/Virginia, hay transferencia internacional]` | todos |
| **Amazon S3** | documentos subidos | `[confirmar región del bucket]` | documentos con datos personales |
| **Sentry** | avisos de error | `[confirmar]` | ver nota |
| Proveedor SMTP | correos a clientes e inversores | `[confirmar cuál]` | nombre y email |
| Servicio de notificaciones push | avisos al portal | navegador del usuario | suscripción |
| **Stripe** | cobro de la rifa | *aún no conectado* | nombre, email, importe |
| Notaría | acta del sorteo | España | nombre y localizador de participantes |

**Nota sobre Sentry.** Está gobernado por `SENTRY_SEND_DEFAULT_PII`, que por
defecto vale `0`: no envía datos personales. Si alguna vez se pone a `1`, Sentry
pasa a recibir cabeceras y datos de usuario, y entonces **cambia lo que hay que
declarar en la política**. Conviene dejarlo escrito para que nadie lo active sin
saber lo que implica.

**Las transferencias internacionales hay que confirmarlas.** Si Render o S3
están fuera del Espacio Económico Europeo, la política debe declararlo y hace
falta el mecanismo de garantía correspondiente. Esto se mira en el panel de cada
servicio.

---

## 4. Plazos de conservación propuestos

Ninguno está implementado hoy. Los propongo con el razonamiento para que la
asesoría los confirme o corrija:

| Dato | Propuesta | Por qué |
|---|---|---|
| Cliente con participación viva | mientras dure la relación | ejecución del contrato |
| Cliente con participación liquidada | `[6 años]` desde la liquidación | plazo mercantil del art. 30 del Código de Comercio |
| Facturas y justificantes | `[6 años]` | obligación contable y fiscal |
| Lista de espera de la rifa | hasta la baja, o `[2 años]` sin actividad | consentimiento revocable |
| Pedidos de la rifa | `[6 años]` | contable, más el plazo de reclamación del premio |
| Solicitudes de reenvío | `[90 días]` | solo sirven para detectar abuso |
| Intentos de PIN | `[90 días]` | igual |
| IP de conexión de empleados | `[1 año]` | seguridad |
| Registro de auditoría | `[6 años]` | trazabilidad de lo que mueve dinero |
| Leads de la web | `[1 año]` sin conversión | interés legítimo |

---

## 5. Cómo borrar, y qué no se puede borrar

Hoy no hay ningún procedimiento: el derecho de supresión (art. 17) solo puede
ejercerse borrando a mano desde el administrador. Y hay un obstáculo técnico
real que conviene entender antes de prometer nada a nadie.

**Un cliente con participaciones no se puede borrar sin más.** Las claves ajenas
están protegidas contra borrado en cascada, precisamente para que nadie destruya
un histórico económico por accidente. Y aunque se pudieran borrar, **no se debe**:
esos registros respaldan obligaciones contables y fiscales.

Lo correcto no es borrar, es **anonimizar**: sustituir nombre, DNI, IBAN,
teléfono, dirección y email por valores irreversibles, y conservar los importes
y las fechas, que ya no identifican a nadie. La operación sigue cuadrando en las
cuentas y la persona desaparece.

Propuesta de procedimiento:

1. La solicitud entra por `[dirección de contacto]` y se responde en un mes.
2. Se comprueba la identidad de quien la pide.
3. Si **no** tiene participaciones ni pedidos: se borra el registro entero.
4. Si los tiene: se anonimiza el cliente y se conservan los importes, marcando
   la fecha de anonimización.
5. Se borran sus documentos de S3, salvo los que respalden una obligación
   contable.
6. Queda constancia en el registro de auditoría.

**Esto lo puedo implementar** —un comando y una acción en el administrador— en
cuanto la asesoría confirme los plazos y qué se conserva. No lo he hecho aún
porque programarlo antes de decidirlo sería fijar en código una interpretación
legal que no me corresponde.

---

## 6. Borrador de la política de privacidad

> Sustituye a la que hay publicada, que tiene dieciséis líneas y no cumple el
> artículo 13. **No publicar hasta que la revise vuestra asesoría.**

### Responsable del tratamiento

`[Razón social completa]`, con NIF `[NIF]` y domicilio en `[domicilio]`.
Contacto: `[email]`. `[Delegado de Protección de Datos, si procede]`.

### Qué datos tratamos y para qué

**Si eres cliente o inversor:** nombre, DNI o CIF, dirección postal, teléfono,
email y cuenta bancaria. Los usamos para gestionar tu participación en las
operaciones, pagarte las liquidaciones y cumplir nuestras obligaciones
contables y fiscales. La base jurídica es la ejecución del contrato y el
cumplimiento de obligaciones legales.

**Si nos escribes desde la web:** nombre, email y teléfono, para responderte. La
base jurídica es tu consentimiento.

**Si te apuntas a un sorteo:** nombre, email, teléfono y la constancia de que
aceptaste las bases y declaraste ser mayor de edad. La base jurídica es la
ejecución del contrato y el cumplimiento de la normativa de juego, que nos
obliga a conservar esa prueba.

**En todos los casos** guardamos la dirección IP desde la que nos escribes, por
seguridad y para poder detectar abusos.

### Cuánto tiempo los guardamos

`[Insertar la tabla del apartado 4 una vez confirmada.]`

### A quién se los cedemos

No vendemos datos a nadie ni los cedemos con fines comerciales. Sí los tratan
por nuestra cuenta los proveedores que hacen funcionar el servicio:
alojamiento, almacenamiento de documentos, correo y avisos de error.
`[Insertar la tabla del apartado 3 una vez confirmadas las regiones.]`

### Tus derechos

Puedes pedirnos acceso a tus datos, que los rectifiquemos, que los suprimamos,
que limitemos su tratamiento, oponerte a él y pedir que te los entreguemos en
un formato que puedas llevarte. Escríbenos a `[email]` y te responderemos en un
plazo máximo de un mes.

Si tienes participaciones en operaciones ya liquidadas, hay datos que estamos
obligados a conservar por la normativa contable y fiscal aunque nos pidas
borrarlos. En ese caso anonimizamos todo lo que te identifica y conservamos solo
las cifras.

Si crees que no hemos atendido bien tu solicitud, puedes reclamar ante la
**Agencia Española de Protección de Datos** (www.aepd.es).

### Seguridad

Los datos más sensibles —DNI, cuenta bancaria, teléfono y dirección— se guardan
**cifrados**. El acceso al sistema interno exige doble factor de autenticación y
está limitado por perfiles. Los documentos se sirven mediante enlaces firmados y
con caducidad.

---

## 7. Lo que hay que decidir

1. Los datos identificativos del responsable y si procede nombrar un DPD.
2. Confirmar las regiones de Render y S3, y si hay transferencia internacional.
3. Los plazos de conservación del apartado 4.
4. Si el procedimiento de supresión por anonimización es aceptable.
5. Revisar el borrador del apartado 6 antes de publicarlo.

En cuanto haya respuesta a 3 y 4, implemento la anonimización y la purga
automática.
