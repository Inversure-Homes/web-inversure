/* ===============================
   UTILIDADES MONETARIAS
=============================== */

function parseEuro(value) {
    if (!value) return 0;
    return Number(
        value.toString()
            .replace(/\./g, "")
            .replace(",", ".")
            .replace("€", "")
            .trim()
    ) || 0;
}

function formatEuro(value) {
    if (value === null || value === "" || isNaN(value)) return "";
    return new Intl.NumberFormat("es-ES", {
        style: "currency",
        currency: "EUR",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

function activarFormatoEuroGlobal() {
    document.querySelectorAll('[data-euro], .euro-input').forEach(input => {
        input.addEventListener("blur", () => {
            input.value = formatEuro(parseEuro(input.value));
        });
    });
}

function aplicarFormatoEuroInicial() {
    document.querySelectorAll('[data-euro], .euro-input').forEach(input => {
        const valor = parseEuro(input.value);
        if (valor) {
            input.value = formatEuro(valor);
        }
    });
}

/* ===============================
   GASTOS DE ADQUISICIÓN AUTOMÁTICOS
=============================== */

function getFieldByNames(names) {
    for (const name of names) {
        const el = document.querySelector(`[name="${name}"]`);
        if (el) return el;
    }
    return null;
}

function recalcGastosAdquisicion() {
    // Soportar varios name="..." porque el template ha ido cambiando
    const escrituraInput = getFieldByNames([
        "precio_compra_inmueble",
        "precio_escritura",
        "precio_compra",
        "valor_escritura"
    ]);

    const itpInput = getFieldByNames(["itp", "gasto_itp"]);
    const notariaInput = getFieldByNames(["notaria", "gasto_notaria"]);
    const registroInput = getFieldByNames(["registro", "gasto_registro"]);

    // Campo visible que el usuario entiende como "venta estimada" (media valoraciones)
    const mediaValoracionesInput = getFieldByNames([
        "media_valoraciones",
        "venta_estimada",
        "precio_venta_estimado" // en algunos templates se reutiliza este name
    ]);

    const valorEscritura = parseEuro(escrituraInput?.value);

    // ITP: 2% del valor de escritura
    const itp = valorEscritura * 0.02;

    // Notaría: mínimo 500 €, si no 0,20 %
    const notaria = Math.max(500, valorEscritura * 0.002);

    // Registro: mínimo 400 €, si no 0,15 % (regla práctica; ajustable si teníais otro porcentaje)
    const registro = Math.max(400, valorEscritura * 0.0015);

    // Media de valoraciones (si existen 3 campos de valoración)
    const valoraciones = [
        parseEuro(getFieldByNames(["valoracion_1", "valoracion1"])?.value),
        parseEuro(getFieldByNames(["valoracion_2", "valoracion2"])?.value),
        parseEuro(getFieldByNames(["valoracion_3", "valoracion3"])?.value)
    ].filter(v => v > 0);

    const mediaValoraciones = valoraciones.length
        ? valoraciones.reduce((a, b) => a + b, 0) / valoraciones.length
        : 0;

    // Rellenar automáticos
    if (itpInput) itpInput.value = formatEuro(itp);
    if (notariaInput) notariaInput.value = formatEuro(notaria);
    if (registroInput) registroInput.value = formatEuro(registro);

    // La media de valoraciones es la "venta estimada" que alimenta la rentabilidad
    if (mediaValoracionesInput) mediaValoracionesInput.value = formatEuro(mediaValoraciones);

    // Valor de adquisición = escritura + gastos (ITP + notaría + registro + otros gastos si existen)
    const otrosNombres = [
        "gestoria",
        "tasacion",
        "comision_agencia",
        "otros_gastos",
        "gastos_adquisicion"
    ];

    let otros = 0;
    otrosNombres.forEach(n => {
        const el = getFieldByNames([n]);
        if (el) otros += parseEuro(el.value);
    });

    const valorAdquisicion = valorEscritura + itp + notaria + registro + otros;

    const valorAdquisicionInput = getFieldByNames([
        "valor_adquisicion",
        "valor_adquisicion_total",
        "valor_adquisicion_inmueble"
    ]);

    if (valorAdquisicionInput) valorAdquisicionInput.value = formatEuro(valorAdquisicion);
}

/* ===============================
   REFORMA (OBRA + SEGURIDAD)
=============================== */


// ===============================
// CÁLCULO SIMPLIFICADO RESULTADOS
// ===============================

function recalcResultados() {
    const compraInput = getFieldByNames(["precio_compra_inmueble", "precio_escritura", "precio_compra", "valor_escritura"]);
    const reformaInput = getFieldByNames(["reforma", "coste_reforma"]);

    // Venta: prioriza un campo explícito si existe; si no, usa la media de valoraciones
    const ventaInput = getFieldByNames(["precio_venta_estimado", "venta_estimada"]);
    const mediaValoracionesInput = getFieldByNames(["media_valoraciones", "precio_venta_estimado", "venta_estimada"]);

    const beneficioInput = getFieldByNames(["beneficio"]);
    const roiInput = getFieldByNames(["roi"]);

    const itpInput = getFieldByNames(["itp", "gasto_itp"]);
    const notariaInput = getFieldByNames(["notaria", "gasto_notaria"]);
    const registroInput = getFieldByNames(["registro", "gasto_registro"]);

    const compra = parseEuro(compraInput?.value);
    const reforma = parseEuro(reformaInput?.value);

    // Si no hay ventaInput o está vacío, toma la media (que se rellena en recalcGastosAdquisicion)
    let venta = parseEuro(ventaInput?.value);
    if (!venta) {
        venta = parseEuro(mediaValoracionesInput?.value);
    }

    const itp = parseEuro(itpInput?.value);
    const notaria = parseEuro(notariaInput?.value);
    const registro = parseEuro(registroInput?.value);

    // Coste total para ROI: compra + gastos adquisición automáticos + reforma
    const coste_total = compra + itp + notaria + registro + reforma;
    const beneficio = venta - coste_total;
    const roi = coste_total > 0 ? (beneficio / coste_total) * 100 : 0;

    if (beneficioInput) {
        beneficioInput.value = formatEuro(beneficio);
    }
    if (roiInput) {
        roiInput.value = isFinite(roi) ? roi.toFixed(2) : "0.00";
    }
}

/* ===============================
   INIT
=============================== */

document.addEventListener("DOMContentLoaded", () => {
    activarFormatoEuroGlobal();
    aplicarFormatoEuroInicial();
    recalcResultados();
    recalcGastosAdquisicion();

    // Añadir listeners para recalcular resultados y gastos de adquisición
    [
        "precio_compra_inmueble",
        "precio_escritura",
        "precio_compra",
        "valor_escritura",
        "reforma",
        "coste_reforma",
        "precio_venta_estimado",
        "venta_estimada",
        "media_valoraciones",
        "itp",
        "gasto_itp",
        "notaria",
        "gasto_notaria",
        "registro",
        "gasto_registro",
        "valoracion_1",
        "valoracion1",
        "valoracion_2",
        "valoracion2",
        "valoracion_3",
        "valoracion3",
        "gestoria",
        "tasacion",
        "comision_agencia",
        "otros_gastos",
        "gastos_adquisicion"
    ].forEach(name => {
        const el = document.querySelector(`[name="${name}"]`);
        if (el) {
            el.addEventListener("input", () => {
                recalcResultados();
                recalcGastosAdquisicion();
            });
            el.addEventListener("blur", () => {
                recalcResultados();
                recalcGastosAdquisicion();
            });
        }
    });

    // Limpiar formato euro antes de enviar (solo los campos que quedan)
    const form = document.querySelector("form");
    if (form) {
        form.addEventListener("submit", (e) => {
            document.querySelectorAll('[data-euro], .euro-input').forEach(input => {
                input.value = parseEuro(input.value);
            });
        });
    }
});
/* ===============================
   UTILIDADES MONETARIAS
=============================== */

function parseEuro(value) {
    if (!value) return 0;
    return Number(
        value.toString()
            .replace(/\./g, "")
            .replace(",", ".")
            .replace("€", "")
            .trim()
    ) || 0;
}

function formatEuro(value) {
    if (value === null || value === "" || isNaN(value)) return "";
    return new Intl.NumberFormat("es-ES", {
        style: "currency",
        currency: "EUR",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

function activarFormatoEuroGlobal() {
    document.querySelectorAll('[data-euro], .euro-input').forEach(input => {
        input.addEventListener("blur", () => {
            input.value = formatEuro(parseEuro(input.value));
        });
    });
}

function aplicarFormatoEuroInicial() {
    document.querySelectorAll('[data-euro], .euro-input').forEach(input => {
        const valor = parseEuro(input.value);
        if (valor) {
            input.value = formatEuro(valor);
        }
    });
}

/* ===============================
   CÁLCULOS
=============================== */

/* ===============================
   GASTOS DE ADQUISICIÓN AUTOMÁTICOS
=============================== */

function getFieldByNames(names) {
    for (const name of names) {
        const el = document.querySelector(`[name="${name}"]`);
        if (el) return el;
    }
    return null;
}

function recalcGastosAdquisicion() {
    // Soportar varios name="..." porque el template ha ido cambiando
    const escrituraInput = getFieldByNames([
        "precio_compra_inmueble",
        "precio_escritura",
        "precio_compra",
        "valor_escritura"
    ]);

    const itpInput = getFieldByNames(["itp", "gasto_itp"]);
    const notariaInput = getFieldByNames(["notaria", "gasto_notaria"]);
    const registroInput = getFieldByNames(["registro", "gasto_registro"]);

    // Campo visible que el usuario entiende como "venta estimada" (media valoraciones)
    const mediaValoracionesInput = getFieldByNames([
        "media_valoraciones",
        "venta_estimada",
        "precio_venta_estimado" // en algunos templates se reutiliza este name
    ]);

    const valorEscritura = parseEuro(escrituraInput?.value);

    // ITP: 2% del valor de escritura
    const itp = valorEscritura * 0.02;

    // Notaría: mínimo 500 €, si no 0,20 %
    const notaria = Math.max(500, valorEscritura * 0.002);

    // Registro: mínimo 400 €, si no 0,15 % (regla práctica; ajustable si teníais otro porcentaje)
    const registro = Math.max(400, valorEscritura * 0.0015);

    // Media de valoraciones (si existen 3 campos de valoración)
    const valoraciones = [
        parseEuro(getFieldByNames(["valoracion_1", "valoracion1"])?.value),
        parseEuro(getFieldByNames(["valoracion_2", "valoracion2"])?.value),
        parseEuro(getFieldByNames(["valoracion_3", "valoracion3"])?.value)
    ].filter(v => v > 0);

    const mediaValoraciones = valoraciones.length
        ? valoraciones.reduce((a, b) => a + b, 0) / valoraciones.length
        : 0;

    // Rellenar automáticos
    if (itpInput) itpInput.value = formatEuro(itp);
    if (notariaInput) notariaInput.value = formatEuro(notaria);
    if (registroInput) registroInput.value = formatEuro(registro);

    // La media de valoraciones es la "venta estimada" que alimenta la rentabilidad
    if (mediaValoracionesInput) mediaValoracionesInput.value = formatEuro(mediaValoraciones);

    // Valor de adquisición = escritura + gastos (ITP + notaría + registro + otros gastos si existen)
    const otrosNombres = [
        "gestoria",
        "tasacion",
        "comision_agencia",
        "otros_gastos",
        "gastos_adquisicion"
    ];

    let otros = 0;
    otrosNombres.forEach(n => {
        const el = getFieldByNames([n]);
        if (el) otros += parseEuro(el.value);
    });

    const valorAdquisicion = valorEscritura + itp + notaria + registro + otros;

    const valorAdquisicionInput = getFieldByNames([
        "valor_adquisicion",
        "valor_adquisicion_total",
        "valor_adquisicion_inmueble"
    ]);

    if (valorAdquisicionInput) valorAdquisicionInput.value = formatEuro(valorAdquisicion);
}

// ===============================
// CÁLCULO RESULTADOS
// ===============================

function recalcResultados() {
    const compraInput = getFieldByNames(["precio_compra_inmueble", "precio_escritura", "precio_compra", "valor_escritura"]);
    const reformaInput = getFieldByNames(["reforma", "coste_reforma"]);

    // Venta: prioriza un campo explícito si existe; si no, usa la media de valoraciones
    const ventaInput = getFieldByNames(["precio_venta_estimado", "venta_estimada"]);
    const mediaValoracionesInput = getFieldByNames(["media_valoraciones", "precio_venta_estimado", "venta_estimada"]);

    const beneficioInput = getFieldByNames(["beneficio"]);
    const roiInput = getFieldByNames(["roi"]);

    const itpInput = getFieldByNames(["itp", "gasto_itp"]);
    const notariaInput = getFieldByNames(["notaria", "gasto_notaria"]);
    const registroInput = getFieldByNames(["registro", "gasto_registro"]);

    const compra = parseEuro(compraInput?.value);
    const reforma = parseEuro(reformaInput?.value);

    // Si no hay ventaInput o está vacío, toma la media (que se rellena en recalcGastosAdquisicion)
    let venta = parseEuro(ventaInput?.value);
    if (!venta) {
        venta = parseEuro(mediaValoracionesInput?.value);
    }

    const itp = parseEuro(itpInput?.value);
    const notaria = parseEuro(notariaInput?.value);
    const registro = parseEuro(registroInput?.value);

    // Coste total para ROI: compra + gastos adquisición automáticos + reforma
    const coste_total = compra + itp + notaria + registro + reforma;
    const beneficio = venta - coste_total;
    const roi = coste_total > 0 ? (beneficio / coste_total) * 100 : 0;

    if (beneficioInput) {
        beneficioInput.value = formatEuro(beneficio);
    }
    if (roiInput) {
        roiInput.value = isFinite(roi) ? roi.toFixed(2) : "0.00";
    }
}

/* ===============================
   INIT
=============================== */

document.addEventListener("DOMContentLoaded", () => {
    activarFormatoEuroGlobal();
    aplicarFormatoEuroInicial();

    // Orden importante: primero calcula automáticos (incluye media), luego resultados
    recalcGastosAdquisicion();
    recalcResultados();

    // Añadir listeners para recalcular resultados y gastos de adquisición
    [
        "precio_compra_inmueble",
        "precio_escritura",
        "precio_compra",
        "valor_escritura",
        "reforma",
        "coste_reforma",
        "precio_venta_estimado",
        "venta_estimada",
        "media_valoraciones",
        "itp",
        "gasto_itp",
        "notaria",
        "gasto_notaria",
        "registro",
        "gasto_registro",
        "valoracion_1",
        "valoracion1",
        "valoracion_2",
        "valoracion2",
        "valoracion_3",
        "valoracion3",
        "gestoria",
        "tasacion",
        "comision_agencia",
        "otros_gastos",
        "gastos_adquisicion"
    ].forEach(name => {
        const el = document.querySelector(`[name="${name}"]`);
        if (el) {
            el.addEventListener("input", () => {
                recalcGastosAdquisicion();
                recalcResultados();
            });
            el.addEventListener("blur", () => {
                recalcGastosAdquisicion();
                recalcResultados();
            });
        }
    });

    // Limpiar formato euro antes de enviar
    const form = document.querySelector("form");
    if (form) {
        form.addEventListener("submit", () => {
            document.querySelectorAll('[data-euro], .euro-input').forEach(input => {
                input.value = parseEuro(input.value);
            });
        });
    }
});