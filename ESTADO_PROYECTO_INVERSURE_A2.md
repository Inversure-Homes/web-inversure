# ESTADO DEL PROYECTO · INVERSURE WEB
Fecha: 17/12/2025
Fase: A2 – Diseño profesional (en curso)

----------------------------------------
1. OBJETIVO DEL PROYECTO
----------------------------------------

Desarrollar una aplicación web profesional en Django para Inversure,
orientada a la simulación de operaciones inmobiliarias con financiación
mediante cuentas partícipes, garantizando trazabilidad, transparencia
y métricas de rentabilidad claras.

Uso inicial: empleados Inversure
Uso futuro: inversores (acceso controlado)

----------------------------------------
2. ESTADO TÉCNICO ACTUAL
----------------------------------------

Backend:
- Django 4.2.27
- Python 3.9
- Proyecto arranca correctamente
- Error 500 solucionado
- URLs funcionando
- Lógica de cálculo restaurada (fase A1)

Frontend base:
- base.html limpio y válido
- Bootstrap 5 integrado por CDN
- Fuente Inter aplicada
- Logo Inversure cargando
- CSS propio funcionando
- Formato contable europeo activo (98.000,00)

Pruebas locales OK:
GET / → 200
GET /static/core/style.css → 200
GET /static/core/logo.png → 200

----------------------------------------
3. ARCHIVOS CLAVE
----------------------------------------

core/templates/core/base.html
- Contiene head, body y layout general
- Bootstrap + CSS + logo
- Script formato contable
- NO duplicar head/body
Estado: correcto y estable

core/templates/core/simulador.html
- Formulario completo
- Secciones por bloques
- Cards Bootstrap
- Resultados y KPIs básicos
Estado: correcto

core/views.py
- Cálculo de:
  - inversión total
  - beneficio bruto
  - beneficio partícipes
  - rentabilidad
  - break-even
  - colchón de seguridad
Estado: restaurado y funcionando

config/settings.py
- STATIC_ROOT definido
- Ajustes que eliminaron error 500
Estado: correcto

----------------------------------------
4. CONTROL DE VERSIONES
----------------------------------------

Repositorio:
https://github.com/Maperez1983/web-inversure.git

Últimos commits:
- UI base + CSS corporativo
- Restauración HTML completo simulador
- Restauración métricas A1
- Fix error 500
Base estable confirmada

----------------------------------------
5. DESPLIEGUE (RENDER)
----------------------------------------

- Servicio activo
- Sin errores en logs
- Pendiente verificación visual final
- collectstatic ya contemplado

----------------------------------------
6. PUNTO DE PARADA
----------------------------------------

Fase actual: A2 – Diseño profesional

Completado:
- Bootstrap activo
- Layout web real
- Base estable

Pendiente:
- A2.1 KPIs visuales avanzados
- Semáforos ROI
- Tarjetas profesionales
- Jerarquía visual definitiva

----------------------------------------
7. SIGUIENTE PASO
----------------------------------------

Retomar desde:
A2.1 – Diseño de KPIs profesionales

----------------------------------------
8. REGLAS PARA CONTINUAR
----------------------------------------

- Siempre copiar código completo
- No duplicar head/body
- No mezclar base.html y simulador.html
- Probar primero en local
- Un cambio = un commit

----------------------------------------
ESTADO FINAL DEL DÍA
----------------------------------------

Proyecto sano
Base sólida
Sin errores críticos
Listo para continuar
