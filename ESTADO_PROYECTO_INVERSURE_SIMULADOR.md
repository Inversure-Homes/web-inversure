
# ESTADO DEL PROYECTO – SIMULADOR INVERSURE

Fecha: 19/12/2025
Estado: ESTABLE (LOCAL + RENDER)

---

## 1. OBJETIVO
Simulador profesional de operaciones inmobiliarias para Inversure, orientado a análisis de inversión y gestión.

---

## 2. BLOQUES FUNCIONALES DEFINITIVOS

### 1. Datos del inmueble
- Precio de compra del inmueble
- Precio estimado de venta
- Referencia catastral
- Valor de referencia catastral
- Botón externo a Sede del Catastro

### 2. Datos principales
- Precio compra (operación)
- Precio venta
- Meses de la operación
- % financiación

### 3. Gastos de adquisición
- Notaría (automático)
- Registro (automático)
- ITP
- Gestoría
- Otros gastos

### 4. Inversión inicial
Campos consolidados (no tocar)

### 5. Gastos recurrentes
Campos consolidados (no tocar)

### 6. Gastos de venta
- Coste de administración (0,5 % del beneficio)
- Coste de comercialización (0,5 % del beneficio)

---

## 3. RESULTADOS (CONCEPTO CERRADO)
- Precio total de compra
- Precio estimado de venta
- Rentabilidad bruta
- Rentabilidad neta
- ROI
- Break-even
- Colchón de seguridad
- Rendimiento por euro invertido
- Aviso visual ROI > 15 %
- Separación rentabilidad operación / inversor

---

## 4. DECISIONES TÉCNICAS CLAVE

- Render correctamente configurado
- Problemas previos debidos a:
  - Cache de navegador
  - Cambios en la vista raíz
- No había duplicados de plantillas
- Solución: hard refresh + confirmación de vista

---

## 5. ARCHIVOS CLAVE

- core/templates/core/simulador.html → plantilla única
- core/templates/core/base.html → estructura neutra
- core/static/core/style.css → restaurado y estable
- core/views.py → vista simulador correcta
- core/urls.py → / apunta a simulador

---

## 6. DEPLOY

- collectstatic correcto
- whitenoise activo
- build.sh correcto
- Local y Render sincronizados

---

## 7. REGLAS PARA CONTINUAR

1. No borrar bloques cerrados
2. Un cambio = un commit
3. Hard refresh tras cambios HTML
4. Estabilidad antes de mejoras

---

Estado final: SIMULADOR ESTABLE Y LISTO PARA CONTINUAR
