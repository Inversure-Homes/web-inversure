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
   REFORMA (OBRA + SEGURIDAD)
=============================== */

function recalcReforma() {
    const camposReforma = [
        // OBRA 4A
        "obra_demoliciones",
        "obra_albanileria",
        "obra_fontaneria",
        "obra_electricidad",
        "obra_carpinteria_interior",
        "obra_carpinteria_exterior",
        "obra_cocina",
        "obra_banos",
        "obra_pintura",
        "obra_otros",

        // SEGURIDAD 4B
        "seguridad_cerrajero",
        "seguridad_alarma"
    ];

    let total = 0;

    camposReforma.forEach(name => {
        const el = document.querySelector(`[name="${name}"]`);
        if (el) {
            total += parseEuro(el.value);
        }
    });

    const reformaInput = document.querySelector('[name="reforma"]');
    if (reformaInput && !reformaInput.dataset.manual) {
        reformaInput.value = formatEuro(total);
    }
}

function recalcMediaValoraciones() {
    const campos = [
        "val_idealista",
        "val_fotocasa",
        "val_registradores",
        "val_casafari",
        "val_tasacion"
    ];

    let total = 0;
    let count = 0;

    campos.forEach(name => {
        const el = document.querySelector(`[name="${name}"]`);
        if (el) {
            const v = parseEuro(el.value);
            if (v > 0) {
                total += v;
                count++;
            }
        }
    });

    const media = count > 0 ? total / count : 0;

    const mediaInput = document.querySelector('[name="media_valoraciones"]');
    if (mediaInput) mediaInput.value = formatEuro(media);

    const venta = document.querySelector('[name="precio_venta_estimado"]');
    if (venta && !venta.dataset.manual) {
        venta.value = formatEuro(media);
    }
}

function recalcPrecioCompraInmueble() {
    const escritura = parseEuro(document.querySelector('[name="precio_propiedad"]')?.value);

    const notaria = document.querySelector('[name="notaria"]');
    const registro = document.querySelector('[name="registro"]');
    const itp = document.querySelector('[name="itp"]');

    if (notaria && !notaria.dataset.manual) {
        notaria.value = formatEuro(Math.max(escritura * 0.002, 500));
    }
    if (registro && !registro.dataset.manual) {
        registro.value = formatEuro(Math.max(escritura * 0.002, 500));
    }
    if (itp && !itp.dataset.manual) {
        itp.value = formatEuro(escritura * 0.02);
    }
}

/* ===============================
   MAPA
=============================== */

function activarMapaAutomatico() {
    const iframe = document.getElementById("mapIframe");
    const direccionInput = document.getElementById("direccion");

    if (!iframe || !direccionInput) return;

    const direccion = direccionInput.value?.trim();
    if (!direccion) return;

    iframe.src = `https://www.google.com/maps?q=${encodeURIComponent(direccion)}&output=embed`;
}

/* ===============================
   CATASTRO
=============================== */

function abrirCatastro() {
    const refInput =
        document.querySelector('[name="ref_catastral"]') ||
        document.getElementById("ref_catastral");

    if (!refInput || !refInput.value.trim()) {
        alert("Introduce una referencia catastral válida.");
        return;
    }

    const ref = refInput.value.trim();
    const url = `/catastro/obtener/?ref=${encodeURIComponent(ref)}`;
    window.open(url, "_blank");
}

/* ===============================
   INIT
=============================== */

document.addEventListener("DOMContentLoaded", () => {

    activarFormatoEuroGlobal();
    recalcMediaValoraciones();
    recalcPrecioCompraInmueble();
    activarMapaAutomatico();
    aplicarFormatoEuroInicial();

    document.querySelectorAll('[data-euro], .euro-input').forEach(el => {
        el.addEventListener("input", () => el.dataset.manual = "1");
    });

    const direccion = document.getElementById("direccion");
    if (direccion) {
        direccion.addEventListener("input", activarMapaAutomatico);
        direccion.addEventListener("blur", activarMapaAutomatico);
    }

    // Recalcular reforma cuando se modifique obra o seguridad
    [
        "obra_demoliciones",
        "obra_albanileria",
        "obra_fontaneria",
        "obra_electricidad",
        "obra_carpinteria_interior",
        "obra_carpinteria_exterior",
        "obra_cocina",
        "obra_banos",
        "obra_pintura",
        "obra_otros",
        "seguridad_cerrajero",
        "seguridad_alarma"
    ].forEach(name => {
        const el = document.querySelector(`[name="${name}"]`);
        if (el) {
            el.addEventListener("input", recalcReforma);
            el.addEventListener("blur", recalcReforma);
        }
    });

    // Cálculo inicial
    recalcReforma();

    // ===============================
    // LIMPIAR FORMATO € ANTES DE ENVIAR
    // ===============================
    const form = document.querySelector("form");
    if (form) {
        form.addEventListener("submit", () => {
            document.querySelectorAll('[data-euro], .euro-input').forEach(input => {
                input.value = parseEuro(input.value);
            });
        });
    }
});