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

function applyEuroFormatting(input) {
    const val = parseEuro(input.value);
    input.value = formatEuro(val);
    // cursor at end by default after setting value
}

function getFieldByNames(names) {
    for (const name of names) {
        const el = document.querySelector(`[name="${name}"]`);
        if (el) return el;
    }
    return null;
}

/* ===============================
   GASTOS DE ADQUISICIÓN
=============================== */
function recalcGastosAdquisicion() {
    const escrituraInput = getFieldByNames([
        "precio_escritura",
        "precio_compra_inmueble",
        "precio_compra",
        "valor_escritura"
    ]);

    const itpInput = getFieldByNames(["itp", "gasto_itp"]);
    const notariaInput = getFieldByNames(["notaria", "gasto_notaria"]);
    const registroInput = getFieldByNames(["registro", "gasto_registro"]);

    const valorEscritura = parseEuro(escrituraInput?.value);

    const itp = valorEscritura * 0.02;
    const notaria = Math.max(500, valorEscritura * 0.002);
    const registro = Math.max(500, valorEscritura * 0.002);

    if (itpInput) itpInput.value = formatEuro(itp);
    if (notariaInput) notariaInput.value = formatEuro(notaria);
    if (registroInput) registroInput.value = formatEuro(registro);

    let otros = 0;
    document.querySelectorAll('[data-gasto="true"]').forEach(el => {
        otros += parseEuro(el.value);
    });

    const valorAdquisicion = valorEscritura + itp + notaria + registro + otros;

    const valorAdquisicionInput = getFieldByNames([
        "valor_adquisicion",
        "valor_adquisicion_total",
        "valor_adquisicion_inmueble"
    ]);

    if (valorAdquisicionInput) {
        valorAdquisicionInput.value = formatEuro(valorAdquisicion);
    }
}

/* ===============================
   RESULTADOS / RENTABILIDAD
=============================== */
function recalcMediaValoraciones() {
    const inputs = document.querySelectorAll('[data-valuation="true"]');

    let suma = 0;
    let count = 0;

    inputs.forEach(el => {
        const v = parseEuro(el.value);
        if (v > 0) {
            suma += v;
            count += 1;
        }
    });

    const media = count > 0 ? suma / count : 0;

    return media;
}

function recalcResultados() {
    const valorAdqInput = getFieldByNames([
        "valor_adquisicion",
        "valor_adquisicion_total",
        "valor_adquisicion_inmueble"
    ]);

    const reformaInput = getFieldByNames(["reforma", "coste_reforma"]);
    const ventaInput = getFieldByNames([
        "valor_transmision",
        "precio_venta",
        "precio_venta_estimado",
        "venta_estimada",
        "media_valoraciones"
    ]);

    const venta = recalcMediaValoraciones();

    if (ventaInput) {
        ventaInput.value = formatEuro(venta);
    }

    const beneficioInput = getFieldByNames(["beneficio"]);
    const roiInput = getFieldByNames(["roi"]);

    const valorAdq = parseEuro(valorAdqInput?.value);
    const reforma = parseEuro(reformaInput?.value);

    const costeTotal = valorAdq + reforma;
    const beneficio = venta - costeTotal;
    const roi = costeTotal > 0 ? (beneficio / costeTotal) * 100 : 0;

    if (beneficioInput) beneficioInput.value = formatEuro(beneficio);
    if (roiInput) roiInput.value = isFinite(roi) ? roi.toFixed(2) : "0.00";
}

function renderAnalisisViabilidad() {
    const valorAdqInput = getFieldByNames([
        "valor_adquisicion",
        "valor_adquisicion_total",
        "valor_adquisicion_inmueble"
    ]);
    const reformaInput = getFieldByNames(["reforma", "coste_reforma"]);

    const valorAdq = parseEuro(valorAdqInput?.value);
    const reforma = parseEuro(reformaInput?.value);

    const valorTransmision = recalcMediaValoraciones();

    const costeTotal = valorAdq + reforma;
    const beneficio = valorTransmision - costeTotal;
    const margen = valorTransmision > 0 ? (beneficio / valorTransmision) * 100 : 0;
    const roi = costeTotal > 0 ? (beneficio / costeTotal) * 100 : 0;

    let contenedor = document.getElementById("analisis-viabilidad");

    if (!contenedor) return;

    let card = contenedor.querySelector(".analisis-card");

    if (!card) {
        contenedor.innerHTML = `
            <div class="card mt-3 analisis-card">
                <div class="card-body">
                    <h5 class="card-title">Análisis de viabilidad</h5>
                    <ul class="list-unstyled mb-0">
                        <li><strong>Valor de adquisición:</strong> <span id="av-valor-adq"></span></li>
                        <li><strong>Valor de transmisión:</strong> <span id="av-valor-trans"></span></li>
                        <li><strong>Coste de reforma:</strong> <span id="av-reforma"></span></li>
                        <li><strong>Beneficio estimado:</strong> <span id="av-beneficio"></span></li>
                        <li><strong>Margen sobre venta:</strong> <span id="av-margen"></span></li>
                        <li><strong>ROI:</strong> <span id="av-roi"></span></li>
                    </ul>
                </div>
            </div>
        `;
    }

    document.getElementById("av-valor-adq").textContent = formatEuro(valorAdq);
    document.getElementById("av-valor-trans").textContent = formatEuro(valorTransmision);
    document.getElementById("av-reforma").textContent = formatEuro(reforma);
    document.getElementById("av-beneficio").textContent = formatEuro(beneficio);
    document.getElementById("av-margen").textContent = margen.toFixed(2) + " %";
    document.getElementById("av-roi").textContent = roi.toFixed(2) + " %";

    contenedor.style.display = "block";
}

/* ===============================
   INIT
=============================== */
document.addEventListener("DOMContentLoaded", () => {
    // Recalcular al cargar
    recalcGastosAdquisicion();
    recalcResultados();

    // Helpers
    const bindRecalcEuro = (el) => {
        if (!el) return;
        // Recalcula mientras escribe
        el.addEventListener("input", () => {
            recalcGastosAdquisicion();
            recalcResultados();
        });
        el.addEventListener("change", () => {
            recalcGastosAdquisicion();
            recalcResultados();
        });
        // Formatea al salir
        el.addEventListener("blur", () => {
            applyEuroFormatting(el);
            recalcGastosAdquisicion();
            recalcResultados();
        });
    };

    const bindRecalcValuation = (el) => {
        if (!el) return;

        el.addEventListener("input", () => {
            recalcResultados();
        });

        el.addEventListener("change", () => {
            recalcResultados();
        });

        el.addEventListener("blur", () => {
            applyEuroFormatting(el);
            recalcResultados();
        });
    };

    // 1) Asegurar que el campo de ESCRITURA siempre dispara recálculo (aunque falte data-euro en HTML)
    const escrituraInput = document.querySelector("#precio_escritura") || getFieldByNames([
        "precio_escritura",
        "precio_compra_inmueble",
        "precio_compra",
        "valor_escritura"
    ]);
    bindRecalcEuro(escrituraInput);

    // 2) Valuaciones: soportar data-valuation y fallback por nombre (si en HTML se perdió el data-valuation)
    const valuationByData = Array.from(document.querySelectorAll('[data-valuation="true"]'));
    const valuationByName = Array.from(document.querySelectorAll('input[name]')).filter(i => {
        const n = (i.getAttribute("name") || "").toLowerCase();
        return n.includes("valoracion") || n.includes("tasacion") || n.includes("valoracion_");
    });
    const valuationInputs = Array.from(new Set([...valuationByData, ...valuationByName]));
    valuationInputs.forEach(bindRecalcValuation);

    // 3) Resto de inputs monetarios con data-euro (excepto el de escritura ya ligado)
    document.querySelectorAll('input[data-euro="true"]').forEach(el => {
        if (el === escrituraInput) return;
        // No queremos tratar inputs de valoraciones como euro genérico para no duplicar listeners
        if (el.dataset.valuation === "true") return;
        bindRecalcEuro(el);
    });

    // 4) Inputs restantes (no monetarios): recálculo por seguridad
    document.querySelectorAll("input").forEach(el => {
        // Ya gestionados arriba
        if (el === escrituraInput) return;
        if (el.dataset.euro === "true") return;
        if (el.dataset.valuation === "true") return;
        const name = (el.getAttribute("name") || "").toLowerCase();
        if (name.includes("valoracion") || name.includes("tasacion")) return;

        ["input", "change"].forEach(evt => {
            el.addEventListener(evt, () => {
                recalcGastosAdquisicion();
                recalcResultados();
            });
        });
    });

    const btnAnalizar = document.getElementById("btn-analizar-viabilidad");
    if (btnAnalizar) {
        btnAnalizar.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            renderAnalisisViabilidad();
        });
    }
});