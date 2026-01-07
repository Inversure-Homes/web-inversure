// ==============================
// UTILIDADES FORMATO EURO
// ==============================
function parseEuro(value) {
  if (!value) return 0;
  return parseFloat(
    value
      .replace(/\./g, "")
      .replace(",", ".")
      .replace(/[^\d.-]/g, "")
  ) || 0;
}

function formatEuro(value) {
  if (isNaN(value)) return "";
  return value.toLocaleString("es-ES", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }) + " €";
}

// ==============================
// UTILIDADES FORMATO NÚMERO (m², etc.)
// ==============================
function parseNumberEs(value) {
  if (value === null || typeof value === "undefined") return null;
  const s = String(value).trim();
  if (!s) return null;

  const n = parseFloat(
    s.replace(/\./g, "").replace(",", ".").replace(/[^\d.-]/g, "")
  );

  return Number.isFinite(n) ? n : null;
}

function formatNumberEs(value, decimals = 0) {
  if (value === null || typeof value === "undefined" || !Number.isFinite(value)) return "";
  return value.toLocaleString("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function aplicarFormatoNumeroInput(input, decimals = 0) {
  if (!input) return;

  input.addEventListener("blur", () => {
    const value = parseNumberEs(input.value);
    if (value === null) {
      input.value = "";
      return;
    }
    input.value = formatNumberEs(value, decimals);
  });

  input.addEventListener("focus", () => {
    const value = parseNumberEs(input.value);
    input.value = value === null ? "" : String(value);
  });
}

let estudioIdActual = null;
// ==============================
// ESTADO PERSISTENTE DEL ESTUDIO
// ==============================
const estadoEstudio = {
  // Identificación / persistencia
  id: null,

  // Datos adquisición
  precio_escritura: null,
  itp: null,
  notaria: null,
  registro: null,
  gastos_extras: null,
  valor_referencia: null,

  // Totales
  valor_adquisicion: null,
  valor_transmision: null,
  media_valoraciones: null,

  // Valoraciones mercado
  valoraciones: {}, // { [data-id]: valor }

  // Datos inmueble (nuevos)
  tipologia: "",
  superficie_m2: null,
  estado_inmueble: "",
  situacion: "",

  // ==============================
  // MÉTRICAS VISTA COMITÉ
  // ==============================
  comite: {
    beneficio_bruto: 0,
    roi: 0,
    margen_pct: 0,
    semáforo: 0,

    // Métricas de robustez
    ratio_euro_beneficio: 0,
    colchon_seguridad: 0,
    breakeven: 0,

    // Presentación comité (automática)
    colchon_mercado: 0,
    decision_texto: "",
    conclusion: "",
    nivel_riesgo: "",

    // ==============================
    // NUEVO · VALORACIÓN Y DECISIÓN
    // ==============================
    decision_estado: "", // aprobada | estudio | denegada
    valoracion: {
      mercado: "",
      riesgo: "",
      ejecucion: "",
      timing: ""
    },
    comentario: "",
    resumen_ejecutivo: "",
    fecha_decision: ""
  }
};

// ==============================
// MÉTRICAS VISTA COMITÉ
// ==============================
estadoEstudio.comite = {
  beneficio_bruto: 0,
  roi: 0,
  margen_pct: 0,
  semáforo: 0,

  // Métricas de robustez
  ratio_euro_beneficio: 0,
  colchon_seguridad: 0,
  breakeven: 0,

  // Presentación comité (automática)
  colchon_mercado: 0,
  decision_texto: "",
  conclusion: "",
  nivel_riesgo: "",

  // ==============================
  // NUEVO · VALORACIÓN Y DECISIÓN
  // ==============================
  decision_estado: "", // aprobada | estudio | denegada
  valoracion: {
    mercado: "",
    riesgo: "",
    ejecucion: "",
    timing: ""
  },
  comentario: "",
  resumen_ejecutivo: "",
  fecha_decision: ""
};

// ==============================
// ELEMENTOS DOM
// ==============================
const precioEscritura = document.getElementById("precio_escritura");
const itpInput = document.getElementById("itp");
const notariaInput = document.getElementById("notaria");
const registroInput = document.getElementById("registro");
const gastosExtrasInput = document.getElementById("gastos_extras");
const valorReferenciaInput = document.getElementById("valor_referencia");
const valorAdquisicionInput = document.getElementById("valor_adquisicion");
const valorTransmisionInput = document.getElementById("valor_transmision");
const mediaValoracionesInput = document.getElementById("media_valoraciones");
const valoracionesInputs = document.querySelectorAll(".valoracion");
const tipologiaInput = document.getElementById("tipologia");
const superficieM2Input = document.getElementById("superficie_m2");
const estadoInmuebleInput = document.getElementById("estado_inmueble") || document.getElementById("estado");
const situacionInput = document.getElementById("situacion");
// Asegura que cada input tenga un data-id único
valoracionesInputs.forEach((input, idx) => {
  if (!input.getAttribute("data-id")) {
    input.setAttribute("data-id", `valoracion_${idx}`);
  }
});

const valoracionMercado = document.getElementById("valoracion_mercado");
const valoracionRiesgo = document.getElementById("valoracion_riesgo");
const valoracionEjecucion = document.getElementById("valoracion_ejecucion");
const valoracionTiming = document.getElementById("valoracion_timing");
const comentarioComite = document.getElementById("comentario_comite");
const decisionComite = document.getElementById("decision_comite");
const resumenEjecutivoComite = document.getElementById("resumen_ejecutivo_comite");
const fechaDecisionComite = document.getElementById("fecha_decision_comite");

// ==============================
// MOTOR DE CÁLCULO CENTRAL
// ==============================
function recalcularTodo() {
  // Guard clause: si precio_escritura es null, undefined o 0, salir
  if (
    estadoEstudio.precio_escritura === null ||
    typeof estadoEstudio.precio_escritura === "undefined" ||
    estadoEstudio.precio_escritura === 0
  ) {
    // Limpiar los campos dependientes
    itpInput.value = "";
    notariaInput.value = "";
    registroInput.value = "";
    valorAdquisicionInput.value = "";
    mediaValoracionesInput.value = "";
    valorTransmisionInput.value = "";
    // Limpiar KPIs visuales
    actualizarVistaComite();
    guardarEstado();
    return;
  }
  // Leer siempre desde estadoEstudio
  const precio = estadoEstudio.precio_escritura || 0;

  // ITP 2%
  const itp = precio * 0.02;
  estadoEstudio.itp = itp;
  itpInput.value = formatEuro(itp);

  // Notaría y Registro (0,2% mínimo 500 €)
  const notaria = Math.max(precio * 0.002, 500);
  const registro = Math.max(precio * 0.002, 500);
  estadoEstudio.notaria = notaria;
  estadoEstudio.registro = registro;
  notariaInput.value = formatEuro(notaria);
  registroInput.value = formatEuro(registro);

  // Media de valoraciones
  let suma = 0;
  let contador = 0;
  valoracionesInputs.forEach(input => {
    const id = input.getAttribute("data-id");
    const val = estadoEstudio.valoraciones[id] || 0;
    if (val > 0) {
      suma += val;
      contador++;
    }
  });
  if (contador === 0) {
    estadoEstudio.media_valoraciones = null;
    estadoEstudio.valor_transmision = null;
    mediaValoracionesInput.value = "";
    valorTransmisionInput.value = "";
  } else {
    const media = suma / contador;
    estadoEstudio.media_valoraciones = media;
    estadoEstudio.valor_transmision = media;
    mediaValoracionesInput.value = media ? formatEuro(media) : "";
    valorTransmisionInput.value = media ? formatEuro(media) : "";
  }

  // Gastos extras
  const gastosExtras = estadoEstudio.gastos_extras || 0;

  // Valor de adquisición
  const valorAdquisicion = precio + itp + notaria + registro + gastosExtras;
  estadoEstudio.valor_adquisicion = valorAdquisicion;
  valorAdquisicionInput.value = precio ? formatEuro(valorAdquisicion) : "";

  // Pintar los valores de los inputs desde estadoEstudio (si no están enfocados)
  if (document.activeElement !== precioEscritura) {
    precioEscritura.value = estadoEstudio.precio_escritura ? formatEuro(estadoEstudio.precio_escritura) : "";
  }
  if (document.activeElement !== notariaInput) {
    notariaInput.value = estadoEstudio.notaria ? formatEuro(estadoEstudio.notaria) : "";
  }
  if (document.activeElement !== registroInput) {
    registroInput.value = estadoEstudio.registro ? formatEuro(estadoEstudio.registro) : "";
  }
  if (valorReferenciaInput && document.activeElement !== valorReferenciaInput) {
    valorReferenciaInput.value = estadoEstudio.valor_referencia
      ? formatEuro(estadoEstudio.valor_referencia)
      : "";
  }
  valoracionesInputs.forEach(input => {
    const id = input.getAttribute("data-id");
    if (document.activeElement !== input) {
      input.value = estadoEstudio.valoraciones[id]
        ? formatEuro(estadoEstudio.valoraciones[id])
        : "";
    }
  });

  // Pintar campos de inmueble (persistencia al cambiar de vista)
  if (tipologiaInput && document.activeElement !== tipologiaInput) {
    tipologiaInput.value = estadoEstudio.tipologia || "";
  }
  if (estadoInmuebleInput && document.activeElement !== estadoInmuebleInput) {
    estadoInmuebleInput.value = estadoEstudio.estado_inmueble || "";
  }
  if (situacionInput && document.activeElement !== situacionInput) {
    situacionInput.value = estadoEstudio.situacion || "";
  }
  if (superficieM2Input && document.activeElement !== superficieM2Input) {
    const v = estadoEstudio.superficie_m2;
    superficieM2Input.value = (v === null || typeof v === "undefined") ? "" : formatNumberEs(v, 0);
  }

  // Métricas comité
  const beneficio = estadoEstudio.valor_transmision - estadoEstudio.valor_adquisicion;
  estadoEstudio.comite.beneficio_bruto = beneficio;
  estadoEstudio.comite.roi = estadoEstudio.valor_adquisicion > 0
    ? (beneficio / estadoEstudio.valor_adquisicion) * 100
    : 0;
  // Margen sobre transmisión
  estadoEstudio.comite.margen_pct = estadoEstudio.valor_transmision > 0
    ? (beneficio / estadoEstudio.valor_transmision) * 100
    : 0;
  // Semáforo por ROI
  if (estadoEstudio.comite.roi >= 20) {
    estadoEstudio.comite.semáforo = "verde";
  } else if (estadoEstudio.comite.roi >= 10) {
    estadoEstudio.comite.semáforo = "amarillo";
  } else {
    estadoEstudio.comite.semáforo = "rojo";
  }

  // ==============================
  // MÉTRICAS DE ROBUSTEZ (COMITÉ)
  // ==============================
  if (beneficio > 0) {
    estadoEstudio.comite.ratio_euro_beneficio =
      estadoEstudio.valor_adquisicion / beneficio;
  } else {
    estadoEstudio.comite.ratio_euro_beneficio = 0;
  }

  // Colchón de seguridad: diferencia entre beneficio esperado y beneficio mínimo exigido
  const BENEFICIO_MINIMO = 30000;

  estadoEstudio.comite.colchon_seguridad =
    estadoEstudio.valor_transmision > 0
      ? (estadoEstudio.valor_transmision - estadoEstudio.valor_adquisicion) - BENEFICIO_MINIMO
      : 0;

  // Breakeven: precio mínimo de venta para beneficio objetivo fijo de 30.000 €
  const BENEFICIO_OBJETIVO = 30000;
  estadoEstudio.comite.breakeven =
    estadoEstudio.valor_adquisicion > 0
      ? estadoEstudio.valor_adquisicion + BENEFICIO_OBJETIVO
      : 0;

  // Nivel de riesgo derivado del semáforo (NO recalcula nada)
  if (estadoEstudio.comite.semáforo === "verde") {
    estadoEstudio.comite.nivel_riesgo = "Bajo";
  } else if (estadoEstudio.comite.semáforo === "amarillo") {
    estadoEstudio.comite.nivel_riesgo = "Medio";
  } else if (estadoEstudio.comite.semáforo === "rojo") {
    estadoEstudio.comite.nivel_riesgo = "Alto";
  } else {
    estadoEstudio.comite.nivel_riesgo = "—";
  }

  // ==============================
  // AMPLIACIÓN MÉTRICAS VISTA COMITÉ
  // ==============================
  // Colchón de mercado: porcentaje entre valor_transmision y valor_adquisicion
  estadoEstudio.comite.colchon_mercado = estadoEstudio.valor_adquisicion > 0
    ? (estadoEstudio.valor_transmision / estadoEstudio.valor_adquisicion) * 100
    : 0;

  // Texto de decisión según semáforo
  if (estadoEstudio.comite.semáforo === "verde") {
    estadoEstudio.comite.decision_texto = "Aprobación recomendada";
  } else if (estadoEstudio.comite.semáforo === "amarillo") {
    estadoEstudio.comite.decision_texto = "Requiere revisión adicional";
  } else if (estadoEstudio.comite.semáforo === "rojo") {
    estadoEstudio.comite.decision_texto = "No recomendable";
  } else {
    estadoEstudio.comite.decision_texto = "";
  }

  // Conclusión ejecutiva breve
  if (estadoEstudio.comite.semáforo === "verde") {
    estadoEstudio.comite.conclusion = "La operación presenta un margen atractivo y bajo riesgo.";
  } else if (estadoEstudio.comite.semáforo === "amarillo") {
    estadoEstudio.comite.conclusion = "La operación es viable, aunque el margen es ajustado.";
  } else if (estadoEstudio.comite.semáforo === "rojo") {
    estadoEstudio.comite.conclusion = "El margen es insuficiente. Se desaconseja la operación.";
  } else {
    estadoEstudio.comite.conclusion = "";
  }

  actualizarVistaComite();

  guardarEstado();
}

function actualizarVistaComite() {
  const kpiAdq = document.getElementById("kpi_valor_adquisicion");
  const kpiTrans = document.getElementById("kpi_valor_transmision");
  const kpiBenef = document.getElementById("kpi_beneficio_bruto");
  const kpiRoi = document.getElementById("kpi_roi");
  const kpiMargen = document.getElementById("kpi_margen");
  const kpiSemaforo = document.getElementById("kpi_semaforo");

  // Nuevos KPIs ampliados
  const kpiColchonMercado = document.getElementById("kpi_colchon_mercado");
  const kpiDecisionTexto = document.getElementById("kpi_decision_texto");
  const kpiConclusion = document.getElementById("kpi_conclusion");

  // KPIs de robustez
  const kpiRatioEB = document.getElementById("kpi_ratio_beneficio");
  const kpiColchonSeg = document.getElementById("kpi_colchon_seguridad");
  const kpiBreakeven = document.getElementById("kpi_breakeven");

  if (kpiAdq) kpiAdq.textContent = estadoEstudio.valor_adquisicion
    ? formatEuro(estadoEstudio.valor_adquisicion)
    : "—";

  if (kpiTrans) kpiTrans.textContent = estadoEstudio.valor_transmision
    ? formatEuro(estadoEstudio.valor_transmision)
    : "—";

  if (kpiBenef) kpiBenef.textContent = estadoEstudio.comite.beneficio_bruto
    ? formatEuro(estadoEstudio.comite.beneficio_bruto)
    : "—";

  if (kpiRoi) kpiRoi.textContent = estadoEstudio.comite.roi
    ? estadoEstudio.comite.roi.toFixed(2) + " %"
    : "—";

  if (kpiMargen)
    kpiMargen.textContent = estadoEstudio.comite.margen_pct
      ? estadoEstudio.comite.margen_pct.toFixed(2) + " %"
      : "—";

  if (kpiSemaforo) {
    let txt = "—";

    // Limpiar clases previas
    kpiSemaforo.classList.remove("semaforo-verde", "semaforo-amarillo", "semaforo-rojo");
    // Limpiar clases corporativas genéricas
    kpiSemaforo.classList.remove("kpi-ok", "kpi-warning", "kpi-bad");

    if (estadoEstudio.comite.semáforo === "verde") {
      txt = "Operación muy viable";
      kpiSemaforo.classList.add("semaforo-verde");
      kpiSemaforo.classList.add("kpi-ok");
    } else if (estadoEstudio.comite.semáforo === "amarillo") {
      txt = "Operación justa";
      kpiSemaforo.classList.add("semaforo-amarillo");
      kpiSemaforo.classList.add("kpi-warning");
    } else if (estadoEstudio.comite.semáforo === "rojo") {
      txt = "Operación no viable";
      kpiSemaforo.classList.add("semaforo-rojo");
      kpiSemaforo.classList.add("kpi-bad");
    }

    kpiSemaforo.textContent = txt;
  }

  // Ampliación: actualizar nuevos KPIs si existen
  if (kpiColchonMercado) {
    kpiColchonMercado.textContent = estadoEstudio.comite.colchon_mercado
      ? estadoEstudio.comite.colchon_mercado.toFixed(2) + " %"
      : "—";
  }
  if (kpiDecisionTexto) {
    kpiDecisionTexto.textContent = estadoEstudio.comite.decision_texto || "—";
  }
  if (kpiConclusion) {
    kpiConclusion.textContent = estadoEstudio.comite.conclusion || "—";
  }
  // Sincronizar nivel de riesgo con semáforo si no está definido
  if (!estadoEstudio.comite.nivel_riesgo) {
    if (estadoEstudio.comite.semáforo === "verde") {
      estadoEstudio.comite.nivel_riesgo = "Bajo";
    } else if (estadoEstudio.comite.semáforo === "amarillo") {
      estadoEstudio.comite.nivel_riesgo = "Medio";
    } else if (estadoEstudio.comite.semáforo === "rojo") {
      estadoEstudio.comite.nivel_riesgo = "Alto";
    }
  }
  const kpiRiesgo = document.getElementById("kpi_nivel_riesgo");

  if (kpiRiesgo) {
    kpiRiesgo.textContent = estadoEstudio.comite.nivel_riesgo || "—";

    kpiRiesgo.classList.remove("riesgo-bajo", "riesgo-medio", "riesgo-alto");

    if (estadoEstudio.comite.nivel_riesgo === "Bajo") {
      kpiRiesgo.classList.add("riesgo-bajo");
    } else if (estadoEstudio.comite.nivel_riesgo === "Medio") {
      kpiRiesgo.classList.add("riesgo-medio");
    } else if (estadoEstudio.comite.nivel_riesgo === "Alto") {
      kpiRiesgo.classList.add("riesgo-alto");
    }
  }
  if (kpiRatioEB) {
    kpiRatioEB.textContent = estadoEstudio.comite.ratio_euro_beneficio
      ? estadoEstudio.comite.ratio_euro_beneficio.toFixed(2)
      : "—";
  }

  if (kpiColchonSeg) {
    kpiColchonSeg.textContent = estadoEstudio.comite.colchon_seguridad
      ? formatEuro(estadoEstudio.comite.colchon_seguridad)
      : "—";
  }

  if (kpiBreakeven) {
    kpiBreakeven.textContent = estadoEstudio.comite.breakeven
      ? formatEuro(estadoEstudio.comite.breakeven)
      : "—";
  }
  renderSemaforoVisual();
  renderRoiBarra();
}

// ==============================
// FORMATO EN TIEMPO REAL
// ==============================
function aplicarFormatoInput(input) {
  input.addEventListener("blur", () => {
    const value = parseEuro(input.value);
    if (value) input.value = formatEuro(value);
  });

  input.addEventListener("focus", () => {
    input.value = parseEuro(input.value) || "";
  });
}

// ==============================
// EVENTOS
// ==============================
[precioEscritura, notariaInput, registroInput, gastosExtrasInput, valorReferenciaInput].forEach(input => {
  if (input) {
    aplicarFormatoInput(input);
    input.addEventListener("input", (e) => {
      // Guardar en estadoEstudio antes de recalcular
      if (input === precioEscritura) {
        estadoEstudio.precio_escritura = parseEuro(input.value);
      } else if (input === notariaInput) {
        estadoEstudio.notaria = parseEuro(input.value);
      } else if (input === registroInput) {
        estadoEstudio.registro = parseEuro(input.value);
      } else if (input === gastosExtrasInput) {
        estadoEstudio.gastos_extras = parseEuro(input.value);
      } else if (input === valorReferenciaInput) {
        estadoEstudio.valor_referencia = parseEuro(input.value);
      }
      recalcularTodo();
    });
  }
});


valoracionesInputs.forEach(input => {
  aplicarFormatoInput(input);
  input.addEventListener("input", (e) => {
    // Guardar en estadoEstudio.valoraciones antes de recalcular
    const id = input.getAttribute("data-id");
    estadoEstudio.valoraciones[id] = parseEuro(input.value);
    recalcularTodo();
  });
});

// ==============================
// EVENTOS CAMPOS INMUEBLE (PERSISTENCIA)
// ==============================
if (tipologiaInput) {
  tipologiaInput.addEventListener("change", () => {
    estadoEstudio.tipologia = tipologiaInput.value || "";
    guardarEstado();
  });
}

if (estadoInmuebleInput) {
  const persistirEstadoInmueble = () => {
    estadoEstudio.estado_inmueble = (estadoInmuebleInput.value || "").trim();
    guardarEstado();
  };

  // Para <select> dispara con change; para <input> necesitamos input para no perder el dato al cambiar de vista.
  estadoInmuebleInput.addEventListener("change", persistirEstadoInmueble);
  estadoInmuebleInput.addEventListener("input", persistirEstadoInmueble);
}

if (situacionInput) {
  situacionInput.addEventListener("change", () => {
    estadoEstudio.situacion = situacionInput.value || "";
    guardarEstado();
  });
}

if (superficieM2Input) {
  aplicarFormatoNumeroInput(superficieM2Input, 0);

  superficieM2Input.addEventListener("input", () => {
    estadoEstudio.superficie_m2 = parseNumberEs(superficieM2Input.value);
    guardarEstado();
  });
}

/* ==============================
   EVENTOS · VALORACIÓN Y DECISIÓN COMITÉ
   ============================== */

/* ==============================
   EVENTO · RESUMEN EJECUTIVO COMITÉ
   ============================== */
if (resumenEjecutivoComite) {
  resumenEjecutivoComite.addEventListener("input", () => {
    estadoEstudio.comite.resumen_ejecutivo = resumenEjecutivoComite.value || "";
    guardarEstado();
  });
}

function persistirValoracionComite() {
  estadoEstudio.comite.valoracion.mercado = valoracionMercado?.value || "";
  estadoEstudio.comite.valoracion.riesgo = valoracionRiesgo?.value || "";
  estadoEstudio.comite.valoracion.ejecucion = valoracionEjecucion?.value || "";
  estadoEstudio.comite.valoracion.timing = valoracionTiming?.value || "";
  estadoEstudio.comite.comentario = comentarioComite?.value || "";
  guardarEstado();
}

if (valoracionMercado) valoracionMercado.addEventListener("change", persistirValoracionComite);
if (valoracionRiesgo) valoracionRiesgo.addEventListener("change", persistirValoracionComite);
if (valoracionEjecucion) valoracionEjecucion.addEventListener("change", persistirValoracionComite);
if (valoracionTiming) valoracionTiming.addEventListener("change", persistirValoracionComite);
if (comentarioComite) comentarioComite.addEventListener("input", persistirValoracionComite);

if (decisionComite) {
  decisionComite.addEventListener("change", () => {
    const nuevaDecision = decisionComite.value || "";
    estadoEstudio.comite.decision_estado = nuevaDecision;

    if (nuevaDecision) {
      const hoy = new Date();
      estadoEstudio.comite.fecha_decision = hoy.toISOString();
      if (fechaDecisionComite) {
        fechaDecisionComite.value = hoy.toLocaleDateString("es-ES");
      }
    }

    guardarEstado();
  });
}

// ==============================
// ESTADO EN sessionStorage
// ==============================

function guardarEstado() {
  try {
    // Guardado general (último estudio abierto)
    sessionStorage.setItem("estudio_inversure_actual", JSON.stringify(estadoEstudio));

    // Guardado por estudio (para que no se pierdan datos al salir/volver)
    if (estudioIdActual) {
      sessionStorage.setItem(`estudio_inversure_${estudioIdActual}`, JSON.stringify(estadoEstudio));
    }
  } catch (e) {
    // Ignore
  }
}

// ==============================
// GUARDAR ESTUDIO EN LISTADO PERSISTENTE
// ==============================
function guardarEstudioEnListado() {
  try {
    let estudios = [];
    const raw = sessionStorage.getItem("estudios_inversure");
    if (raw) {
      estudios = JSON.parse(raw);
      if (!Array.isArray(estudios)) estudios = [];
    }

    if (!estudioIdActual) return;

    const estudio = {
      id: estudioIdActual,
      fecha: new Date().toISOString(),
      snapshot: JSON.parse(JSON.stringify(estadoEstudio))
    };

    const idx = estudios.findIndex(e => e.id === estudioIdActual);
    if (idx >= 0) {
      estudios[idx] = estudio;
    } else {
      estudios.push(estudio);
    }

    sessionStorage.setItem("estudios_inversure", JSON.stringify(estudios));
  } catch (e) {
    // Ignore
  }
}

function cargarEstado() {
  try {
    // Si venimos con un código en la URL, lo usamos como ID actual del estudio
    const params = new URLSearchParams(window.location.search);
    const codigoUrl = (params.get("codigo") || "").trim();
    if (codigoUrl) {
      estudioIdActual = codigoUrl;
      estadoEstudio.id = codigoUrl;
    }

    // 1) Intentar cargar estado por ID (si existe)
    let data = null;
    if (estudioIdActual) {
      data = sessionStorage.getItem(`estudio_inversure_${estudioIdActual}`);
    }

    // 2) Si no hay, cargar el último estado (fallback)
    if (!data) {
      data = sessionStorage.getItem("estudio_inversure_actual");
    }

    if (!data) return;

    const parsed = JSON.parse(data);

    if (parsed.id) {
      estudioIdActual = parsed.id;
      estadoEstudio.id = parsed.id;
    }

    // Copiar propiedades existentes
    Object.keys(estadoEstudio).forEach(k => {
      if (typeof parsed[k] !== "undefined") estadoEstudio[k] = parsed[k];
    });

    // Asegurar objeto valoraciones
    if (!estadoEstudio.valoraciones) estadoEstudio.valoraciones = {};
    if (!estadoEstudio.comite) {
      estadoEstudio.comite = {
        beneficio_bruto: 0,
        roi: 0,
        margen_pct: 0,
        semáforo: 0,
        ratio_euro_beneficio: 0,
        colchon_seguridad: 0,
        breakeven: 0,
        colchon_mercado: 0,
        decision_texto: "",
        conclusion: "",
        nivel_riesgo: "",
        decision_estado: "",
        valoracion: {
          mercado: "",
          riesgo: "",
          ejecucion: "",
          timing: ""
        },
        comentario: ""
      };
    }
  } catch (e) {
    // Ignore
  }
}

// ==============================
// Helper para inicializar estado desde inputs y formatear
// ==============================
function inicializarEstadoDesdeInputsSiVacio() {
  // Si no hay estado cargado, tomamos los valores que ya vienen pintados en el HTML
  // para evitar que `recalcularTodo()` limpie campos al entrar/salir del estudio.

  // precio escritura
  if ((estadoEstudio.precio_escritura === null || typeof estadoEstudio.precio_escritura === "undefined") && precioEscritura?.value) {
    const v = parseEuro(precioEscritura.value);
    if (v) estadoEstudio.precio_escritura = v;
  }

  // gastos extras
  if ((estadoEstudio.gastos_extras === null || typeof estadoEstudio.gastos_extras === "undefined") && gastosExtrasInput?.value) {
    const v = parseEuro(gastosExtrasInput.value);
    if (v) estadoEstudio.gastos_extras = v;
  }

  // valor referencia
  if ((estadoEstudio.valor_referencia === null || typeof estadoEstudio.valor_referencia === "undefined") && valorReferenciaInput?.value) {
    const v = parseEuro(valorReferenciaInput.value);
    if (v) estadoEstudio.valor_referencia = v;
  }

  // valoraciones de mercado
  if (!estadoEstudio.valoraciones) estadoEstudio.valoraciones = {};
  valoracionesInputs.forEach(input => {
    const id = input.getAttribute("data-id");
    if (!id) return;
    const ya = estadoEstudio.valoraciones[id];
    if ((ya === null || typeof ya === "undefined" || ya === 0) && input.value) {
      const v = parseEuro(input.value);
      if (v) estadoEstudio.valoraciones[id] = v;
    }
  });

  // Tipología
  if ((estadoEstudio.tipologia === null || typeof estadoEstudio.tipologia === "undefined" || estadoEstudio.tipologia === "") && tipologiaInput?.value) {
    estadoEstudio.tipologia = (tipologiaInput.value || "").trim();
  }

  // Superficie m²
  if ((estadoEstudio.superficie_m2 === null || typeof estadoEstudio.superficie_m2 === "undefined") && superficieM2Input?.value) {
    const v = parseNumberEs(superficieM2Input.value);
    if (v !== null) estadoEstudio.superficie_m2 = v;
  }

  // Estado
  if ((estadoEstudio.estado_inmueble === null || typeof estadoEstudio.estado_inmueble === "undefined" || estadoEstudio.estado_inmueble === "") && estadoInmuebleInput?.value) {
    estadoEstudio.estado_inmueble = (estadoInmuebleInput.value || "").trim();
  }

  // Situación
  if ((estadoEstudio.situacion === null || typeof estadoEstudio.situacion === "undefined" || estadoEstudio.situacion === "") && situacionInput?.value) {
    estadoEstudio.situacion = (situacionInput.value || "").trim();
  }
}

function formateoInicialInputs() {
  // Asegura que al entrar/volver se vean con formato euro
  [precioEscritura, itpInput, notariaInput, registroInput, gastosExtrasInput, valorReferenciaInput, valorAdquisicionInput, valorTransmisionInput, mediaValoracionesInput].forEach(input => {
    if (!input) return;
    const v = parseEuro(input.value);
    if (v) input.value = formatEuro(v);
  });

  valoracionesInputs.forEach(input => {
    const v = parseEuro(input.value);
    if (v) input.value = formatEuro(v);
  });

  if (superficieM2Input) {
    const v = parseNumberEs(superficieM2Input.value);
    if (v !== null) superficieM2Input.value = formatNumberEs(v, 0);
  }
}

// ==============================
// INICIALIZACIÓN
// ==============================
document.addEventListener("DOMContentLoaded", () => {
  // ==============================
  // BLOQUEO TOTAL DE SUBMIT DEL FORM
  // ==============================
  const formEstudio = document.getElementById("form-estudio");
  if (formEstudio) {
    // Neutralizar cualquier action HTML
    formEstudio.setAttribute("action", "javascript:void(0)");

    // Bloquear submit por cualquier vía
    formEstudio.addEventListener(
      "submit",
      function (e) {
        e.preventDefault();
        e.stopImmediatePropagation();
        return false;
      },
      true
    );
  }

  cargarEstado();
  inicializarEstadoDesdeInputsSiVacio();
  recalcularTodo();
  formateoInicialInputs();

  /* ==============================
     REPINTAR VALORACIÓN COMITÉ
     ============================== */
  if (valoracionMercado) valoracionMercado.value = estadoEstudio.comite.valoracion?.mercado || "";
  if (valoracionRiesgo) valoracionRiesgo.value = estadoEstudio.comite.valoracion?.riesgo || "";
  if (valoracionEjecucion) valoracionEjecucion.value = estadoEstudio.comite.valoracion?.ejecucion || "";
  if (valoracionTiming) valoracionTiming.value = estadoEstudio.comite.valoracion?.timing || "";
  if (comentarioComite) comentarioComite.value = estadoEstudio.comite.comentario || "";
  if (decisionComite) decisionComite.value = estadoEstudio.comite.decision_estado || "";

  if (resumenEjecutivoComite) {
    resumenEjecutivoComite.value = estadoEstudio.comite.resumen_ejecutivo || "";
  }

  if (fechaDecisionComite) {
    fechaDecisionComite.value = estadoEstudio.comite.fecha_decision
      ? new Date(estadoEstudio.comite.fecha_decision).toLocaleDateString("es-ES")
      : "";
  }

  // ==============================
  // LÓGICA DE BOTONES DE ESTUDIO
  // ==============================

  // 1. Selectores DOM
  const btnGuardarEstudio = document.getElementById("btnGuardarEstudio");
  const btnBorrarEstudio = document.getElementById("btnBorrarEstudio");
  const btnConvertirProyecto = document.getElementById("btnConvertirProyecto");
  const btnGenerarPDF = document.getElementById("btnGenerarPDF");

  // 3. CSRF helper
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        // Does this cookie string begin with the name we want?
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  const csrftoken = getCookie("csrftoken");

  // 2. Implementación de comportamientos

  // Guardar estudio
  if (btnGuardarEstudio) {
    btnGuardarEstudio.addEventListener("click", async function (e) {
      e.preventDefault();
      try {
        const nombreProyecto = document.getElementById("nombre_proyecto")?.value || "";
        const direccionCompleta = document.getElementById("direccion_completa")?.value || "";
        const referenciaCatastral = document.getElementById("referencia_catastral")?.value || "";

        // Comprobación defensiva de KPIs de comité y valor de adquisición
        const roiSeguro = Number.isFinite(estadoEstudio.comite?.roi) ? estadoEstudio.comite.roi : 0;
        const beneficioSeguro = Number.isFinite(estadoEstudio.comite?.beneficio_bruto) ? estadoEstudio.comite.beneficio_bruto : 0;
        const valorAdqSeguro = Number.isFinite(estadoEstudio.valor_adquisicion) ? estadoEstudio.valor_adquisicion : 0;

        const resp = await fetch("/guardar-estudio/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken
          },
          body: JSON.stringify({
            id: estudioIdActual,
            nombre: nombreProyecto,
            direccion: direccionCompleta,
            referencia_catastral: referenciaCatastral,

            datos: {
              valor_adquisicion: valorAdqSeguro,
              beneficio: beneficioSeguro,
              roi: roiSeguro,

              snapshot: estadoEstudio
            }
          })
        });

        if (!resp.ok) {
          alert("Error al guardar el estudio.");
          return;
        }

        const data = await resp.json();

        if (data && data.id) {
          estudioIdActual = data.id;
          estadoEstudio.id = data.id;
          guardarEstado();
          // Guardado correcto: no navegamos
        }
      } catch (e) {
        alert("Error de comunicación con el servidor");
      }
    });
  }

  // Borrar estudio
  if (btnBorrarEstudio) {
    btnBorrarEstudio.addEventListener("click", function () {
      // Eliminar del sessionStorage
      try {
        // Quitar el estudio actual del listado
        let estudios = [];
        const raw = sessionStorage.getItem("estudios_inversure");
        if (raw) {
          estudios = JSON.parse(raw);
          if (!Array.isArray(estudios)) estudios = [];
        }
        if (estudioIdActual) {
          estudios = estudios.filter(e => e.id !== estudioIdActual);
        }
        sessionStorage.setItem("estudios_inversure", JSON.stringify(estudios));
      } catch (e) {
        // Ignore
      }
      // Borrar el estado actual
      sessionStorage.removeItem("estudio_inversure_actual");
      // Resetear estadoEstudio y estudioIdActual
      Object.keys(estadoEstudio).forEach(k => {
        if (typeof estadoEstudio[k] === "object" && estadoEstudio[k] !== null) {
          if (Array.isArray(estadoEstudio[k])) {
            estadoEstudio[k] = [];
          } else {
            estadoEstudio[k] = {};
          }
        } else {
          estadoEstudio[k] = null;
        }
      });
      // Resetear comite a estructura inicial
      estadoEstudio.comite = {
        beneficio_bruto: 0,
        roi: 0,
        margen_pct: 0,
        semáforo: 0,
        ratio_euro_beneficio: 0,
        colchon_seguridad: 0,
        breakeven: 0,
        colchon_mercado: 0,
        decision_texto: "",
        conclusion: "",
        nivel_riesgo: ""
      };
      estudioIdActual = null;
      guardarEstado();
      recalcularTodo();
    });
  }

  // Convertir a proyecto
  if (btnConvertirProyecto) {
    btnConvertirProyecto.addEventListener("click", async function () {
      if (estadoEstudio.comite?.decision_estado !== "aprobada") {
        alert("El comité no ha aprobado este estudio. No se puede convertir en proyecto.");
        return;
      }
      if (!estudioIdActual) {
        alert("No hay estudio seleccionado.");
        return;
      }
      try {
        const resp = await fetch("/convertir-proyecto/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken
          },
          body: JSON.stringify({
            estudioIdActual: estudioIdActual
          })
        });
        if (!resp.ok) {
          alert("Error al convertir en proyecto.");
          return;
        }
        const data = await resp.json();
        if (data && data.ok) {
          // Limpiar el estudio actual tras conversión
          sessionStorage.removeItem("estudio_inversure_actual");
          let estudios = [];
          const raw = sessionStorage.getItem("estudios_inversure");
          if (raw) {
            estudios = JSON.parse(raw);
            if (!Array.isArray(estudios)) estudios = [];
          }
          estudios = estudios.filter(e => e.id !== estudioIdActual);
          sessionStorage.setItem("estudios_inversure", JSON.stringify(estudios));
          // Resetear estado local
          Object.keys(estadoEstudio).forEach(k => {
            if (typeof estadoEstudio[k] === "object" && estadoEstudio[k] !== null) {
              if (Array.isArray(estadoEstudio[k])) {
                estadoEstudio[k] = [];
              } else {
                estadoEstudio[k] = {};
              }
            } else {
              estadoEstudio[k] = null;
            }
          });
          estadoEstudio.comite = {
            beneficio_bruto: 0,
            roi: 0,
            margen_pct: 0,
            semáforo: 0,
            ratio_euro_beneficio: 0,
            colchon_seguridad: 0,
            breakeven: 0,
            colchon_mercado: 0,
            decision_texto: "",
            conclusion: "",
            nivel_riesgo: ""
          };
          estudioIdActual = null;
          guardarEstado();
          recalcularTodo();
        }
      } catch (e) {
        alert("Error de red al convertir en proyecto.");
      }
    });
  }

  // Generar PDF (placeholder)
  if (btnGenerarPDF) {
    btnGenerarPDF.addEventListener("click", function () {
      alert("Pendiente de implementación");
    });
  }
});

/* ==============================
   VISUALES VISTA COMITÉ (NO TOCAR CÁLCULOS)
   ============================== */

function resetSemaforoDots() {
  const bajo = document.getElementById("riesgo_bajo");
  const medio = document.getElementById("riesgo_medio");
  const alto = document.getElementById("riesgo_alto");

  [bajo, medio, alto].forEach(el => {
    if (!el) return;
    el.classList.remove(
      "activo",
      "semaforo-verde",
      "semaforo-amarillo",
      "semaforo-rojo"
    );
    // Reset inline styles (solo opacidad, no backgroundColor)
    el.style.opacity = "0.3";
    // el.style.backgroundColor = ""; // Eliminado para no sobreescribir estilos CSS
  });
}

function renderSemaforoVisual() {
  // Comprobación defensiva de existencia de elementos
  const bajo = document.getElementById("riesgo_bajo");
  const medio = document.getElementById("riesgo_medio");
  const alto = document.getElementById("riesgo_alto");
  if (!bajo || !medio || !alto) {
    console.warn("Semáforo no renderizado: faltan elementos riesgo_bajo/medio/alto en el DOM");
    return;
  }

  resetSemaforoDots();

  const nivel = estadoEstudio.comite.nivel_riesgo;

  if (nivel === "Bajo") {
    const el = bajo;
    if (el) {
      el.classList.add("activo", "semaforo-verde");
      el.style.opacity = "1";
      el.style.backgroundColor = "#2ecc71";
    }
  }

  if (nivel === "Medio") {
    const el = medio;
    if (el) {
      el.classList.add("activo", "semaforo-amarillo");
      el.style.opacity = "1";
      el.style.backgroundColor = "#f1c40f";
    }
  }

  if (nivel === "Alto") {
    const el = alto;
    if (el) {
      el.classList.add("activo", "semaforo-rojo");
      el.style.opacity = "1";
      el.style.backgroundColor = "#e74c3c";
    }
  }
}

function renderRoiBarra() {
  const barra = document.getElementById("roi_barra");
  if (!barra) return;

  const roi = estadoEstudio.comite.roi || 0;
  const valor = Math.max(0, Math.min(roi, 50));

  barra.style.width = (valor * 2) + "%";
  barra.textContent = roi.toFixed(2) + " %";

  barra.classList.remove("bg-success", "bg-warning", "bg-danger");
  if (roi >= 20) barra.classList.add("bg-success");
  else if (roi >= 10) barra.classList.add("bg-warning");
  else barra.classList.add("bg-danger");
}
