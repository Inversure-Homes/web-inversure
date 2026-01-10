// ==============================
// UTILIDADES FORMATO EURO
// ==============================
function parseEuro(value) {
  if (value === null || typeof value === "undefined") return 0;
  let s = String(value).trim();
  if (!s) return 0;

  // Remove currency symbol/spaces and keep only number chars
  s = s.replace(/€/g, "").replace(/\s+/g, "");
  s = s.replace(/[^0-9,\.\-]/g, "");

  const hasComma = s.includes(",");
  const dotCount = (s.match(/\./g) || []).length;

  if (hasComma) {
    // Spanish style: 147.199,66 -> 147199.66
    s = s.replace(/\./g, "").replace(/,/g, ".");
  } else {
    // No comma: accept dot as decimal (e.g., 147199.66)
    // If there are multiple dots, treat all but the last as thousand separators.
    if (dotCount > 1) {
      const last = s.lastIndexOf(".");
      s = s.slice(0, last).replace(/\./g, "") + s.slice(last);
    }
    s = s.replace(/,/g, "");
  }

  const n = parseFloat(s);
  return Number.isFinite(n) ? n : 0;
}

function formatEuro(value) {
  if (isNaN(value)) return "";
  return value.toLocaleString("es-ES", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }) + " €";
}

// Helpers para soportar INPUTs y también elementos tipo <span>/<div> en la vista de Proyecto
function _isValueElement(el) {
  if (!el || !el.tagName) return false;
  const t = el.tagName.toUpperCase();
  return t === "INPUT" || t === "TEXTAREA" || t === "SELECT";
}

function _getElText(el) {
  if (!el) return "";
  return _isValueElement(el) ? (el.value || "") : (el.textContent || "");
}

function _setElText(el, v) {
  if (!el) return;
  if (_isValueElement(el)) el.value = v;
  else el.textContent = v;
}

// ==============================
// UTILIDADES FORMATO NÚMERO (m², etc.)
// ==============================
function parseNumberEs(value) {
  if (value === null || typeof value === "undefined") return null;
  let s = String(value).trim();
  if (!s) return null;

  s = s.replace(/\s+/g, "");
  s = s.replace(/[^0-9,\.\-]/g, "");

  const hasComma = s.includes(",");
  const dotCount = (s.match(/\./g) || []).length;

  if (hasComma) {
    s = s.replace(/\./g, "").replace(/,/g, ".");
  } else {
    if (dotCount > 1) {
      const last = s.lastIndexOf(".");
      s = s.slice(0, last).replace(/\./g, "") + s.slice(last);
    }
    s = s.replace(/,/g, "");
  }

  const n = parseFloat(s);
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
  if (!input || !_isValueElement(input)) return;

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

// Este archivo SOLO gestiona Estudios. Los Proyectos usan `proyecto.js`.
const STORAGE_NS = "estudio_inversure";
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
  // Guard clause: si precio_escritura es null/undefined/0, NO debemos borrar datos guardados.
  // Solo limpiamos si realmente no hay datos introducidos.
  const _precio = estadoEstudio.precio_escritura;
  const _precioInputVal = precioEscritura ? parseEuro(_getElText(precioEscritura)) : 0;

  // Detectar si existen datos ya rellenados (en estado o en inputs) para evitar “autoborrado”.
  const _hayValoraciones = !!(estadoEstudio.valoraciones && Object.values(estadoEstudio.valoraciones).some(v => (v || 0) > 0));
  const _hayAlgoEnInputs = (() => {
    try {
      const extras = gastosExtrasInput ? parseEuro(_getElText(gastosExtrasInput)) : 0;
      const ref = valorReferenciaInput ? parseEuro(_getElText(valorReferenciaInput)) : 0;
      let algunaVal = false;
      valoracionesInputs.forEach(inp => {
        if (parseEuro(_getElText(inp)) > 0) algunaVal = true;
      });
      const sup = superficieM2Input ? (parseNumberEs(_getElText(superficieM2Input)) || 0) : 0;
      const tip = tipologiaInput ? (tipologiaInput.value || "").trim() : "";
      const est = estadoInmuebleInput ? (estadoInmuebleInput.value || "").trim() : "";
      const sit = situacionInput ? (situacionInput.value || "").trim() : "";
      return (extras > 0) || (ref > 0) || algunaVal || (sup > 0) || !!tip || !!est || !!sit;
    } catch (e) {
      return false;
    }
  })();

  const _hayDatos = (_precioInputVal > 0) || _hayValoraciones || _hayAlgoEnInputs;

  if (_precio === null || typeof _precio === "undefined" || _precio === 0) {
    // Si hay datos (por ejemplo al abrir un estudio guardado), NO limpiar ni persistir.
    // Solo repintar KPIs (saldrán como —) y salir.
    if (_hayDatos) {
      actualizarVistaComite();
      return;
    }

    // Si no hay datos reales, entonces sí limpiamos dependientes.
    if (itpInput) _setElText(itpInput, "");
    if (notariaInput) _setElText(notariaInput, "");
    if (registroInput) _setElText(registroInput, "");
    if (valorAdquisicionInput) _setElText(valorAdquisicionInput, "");
    if (mediaValoracionesInput) _setElText(mediaValoracionesInput, "");
    if (valorTransmisionInput) _setElText(valorTransmisionInput, "");

    actualizarVistaComite();
    // Importante: NO guardarEstado() aquí para no machacar datos por accidente.
    return;
  }
  // Leer siempre desde estadoEstudio
  const precio = estadoEstudio.precio_escritura || 0;

  // ITP 2%
  const itp = precio * 0.02;
  estadoEstudio.itp = itp;
  _setElText(itpInput, formatEuro(itp));

  // Notaría y Registro (0,2% mínimo 500 €)
  const notaria = Math.max(precio * 0.002, 500);
  const registro = Math.max(precio * 0.002, 500);
  estadoEstudio.notaria = notaria;
  estadoEstudio.registro = registro;
  _setElText(notariaInput, formatEuro(notaria));
  _setElText(registroInput, formatEuro(registro));

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
    _setElText(mediaValoracionesInput, "");
    _setElText(valorTransmisionInput, "");
  } else {
    const media = suma / contador;
    estadoEstudio.media_valoraciones = media;
    estadoEstudio.valor_transmision = media;
    _setElText(mediaValoracionesInput, media ? formatEuro(media) : "");
    _setElText(valorTransmisionInput, media ? formatEuro(media) : "");
  }

  // Gastos extras
  const gastosExtras = estadoEstudio.gastos_extras || 0;

  // Valor de adquisición
  const valorAdquisicion = precio + itp + notaria + registro + gastosExtras;
  estadoEstudio.valor_adquisicion = valorAdquisicion;
  _setElText(valorAdquisicionInput, precio ? formatEuro(valorAdquisicion) : "");

  // Pintar los valores de los inputs desde estadoEstudio (si no están enfocados)
  if (document.activeElement !== precioEscritura) {
    _setElText(precioEscritura, estadoEstudio.precio_escritura ? formatEuro(estadoEstudio.precio_escritura) : "");
  }
  if (document.activeElement !== notariaInput) {
    _setElText(notariaInput, estadoEstudio.notaria ? formatEuro(estadoEstudio.notaria) : "");
  }
  if (document.activeElement !== registroInput) {
    _setElText(registroInput, estadoEstudio.registro ? formatEuro(estadoEstudio.registro) : "");
  }
  if (valorReferenciaInput && document.activeElement !== valorReferenciaInput) {
    _setElText(valorReferenciaInput, estadoEstudio.valor_referencia
      ? formatEuro(estadoEstudio.valor_referencia)
      : "");
  }
  valoracionesInputs.forEach(input => {
    const id = input.getAttribute("data-id");
    if (document.activeElement !== input) {
      _setElText(input, estadoEstudio.valoraciones[id]
        ? formatEuro(estadoEstudio.valoraciones[id])
        : "");
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

  if (kpiRoi) {
    const v = estadoEstudio.comite.roi;
    kpiRoi.textContent = Number.isFinite(v) ? (formatNumberEs(v, 2) + " %") : "—";
  }

  if (kpiMargen) {
    const v = estadoEstudio.comite.margen_pct;
    kpiMargen.textContent = Number.isFinite(v) ? (formatNumberEs(v, 2) + " %") : "—";
  }

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
    const v = estadoEstudio.comite.colchon_mercado;
    kpiColchonMercado.textContent = Number.isFinite(v) ? (formatNumberEs(v, 2) + " %") : "—";
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
    const v = estadoEstudio.comite.ratio_euro_beneficio;
    kpiRatioEB.textContent = Number.isFinite(v) && v !== 0 ? formatNumberEs(v, 2) : "—";
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
  if (!input || !_isValueElement(input)) return;

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
    // Guardado general (último abierto)
    sessionStorage.setItem(`${STORAGE_NS}_actual`, JSON.stringify(estadoEstudio));

    // Guardado por ID del estudio
    if (estudioIdActual) {
      sessionStorage.setItem(`${STORAGE_NS}_${estudioIdActual}`, JSON.stringify(estadoEstudio));
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

let __estadoCargadoDesdeStorage = false;

function getEstudioIdFromPage() {
  try {
    const params = new URLSearchParams(window.location.search);
    const v = (params.get("estudio_id") || params.get("id") || params.get("codigo") || "").trim();
    if (v) return v;

    // Si el template expone el id en un input oculto
    const el1 = document.getElementById("estudio_id") || document.getElementById("id_estudio");
    if (el1 && el1.value) return String(el1.value).trim();

    // Si lo expone en el dataset del body o del form
    if (document.body && document.body.dataset && document.body.dataset.estudioId) {
      return String(document.body.dataset.estudioId).trim();
    }
    const form = document.getElementById("form-estudio");
    if (form && form.dataset && form.dataset.estudioId) {
      return String(form.dataset.estudioId).trim();
    }

    // Si lo expone como variable global
    if (window.ESTUDIO_ID) return String(window.ESTUDIO_ID).trim();
  } catch (e) {}
  return "";
}

function cargarEstado() {
  try {
    // Resolver el estudio actual desde URL/template (estudio_id / id / codigo)
    const idFromPage = getEstudioIdFromPage();
    if (idFromPage) {
      estudioIdActual = idFromPage;
      estadoEstudio.id = idFromPage;
    }

    // 1) Intentar cargar estado por ID (si existe)
    let data = null;
    if (estudioIdActual) {
      data = sessionStorage.getItem(`${STORAGE_NS}_${estudioIdActual}`);
    }

    // 2) Fallback SOLO si el "último estado" pertenece al mismo estudioIdActual
    if (!data) {
      const last = sessionStorage.getItem(`${STORAGE_NS}_actual`);
      if (last) {
        try {
          const lastParsed = JSON.parse(last);
          if (estudioIdActual && lastParsed && String(lastParsed.id || "") === String(estudioIdActual)) {
            data = last;
          }
        } catch (e) {}
      }
    }

    if (!data) {
      // 3) Si venimos desde lista_estudio, el servidor puede inyectar el estado guardado.
      // Reutilizamos el flujo normal convirtiéndolo a `data`.
      const serverRaw = window.ESTADO_INICIAL;
      let serverState = null;
      if (serverRaw && typeof serverRaw === "object" && Object.keys(serverRaw).length > 0) {
        serverState = serverRaw.snapshot && typeof serverRaw.snapshot === "object" ? serverRaw.snapshot : serverRaw;
      }

      if (serverState && typeof serverState === "object" && Object.keys(serverState).length > 0) {
        try {
          // Si el serverState trae id lo usamos; si no, respetamos el estudioIdActual resuelto por URL
          if (serverState.id && !estudioIdActual) {
            estudioIdActual = String(serverState.id);
            estadoEstudio.id = String(serverState.id);
          }
          data = JSON.stringify(serverState);
          __estadoCargadoDesdeStorage = false;
        } catch (e) {
          __estadoCargadoDesdeStorage = false;
          return;
        }
      } else {
        __estadoCargadoDesdeStorage = false;
        return;
      }
    }

    __estadoCargadoDesdeStorage = true;
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
  [precioEscritura, itpInput, notariaInput, registroInput, gastosExtrasInput, valorReferenciaInput, valorAdquisicionInput, valorTransmisionInput, mediaValoracionesInput].forEach(el => {
    if (!el) return;
    const v = parseEuro(_getElText(el));
    if (v) _setElText(el, formatEuro(v));
  });

  valoracionesInputs.forEach(el => {
    const v = parseEuro(_getElText(el));
    if (v) _setElText(el, formatEuro(v));
  });

  if (superficieM2Input) {
    const v = parseNumberEs(_getElText(superficieM2Input));
    if (v !== null) _setElText(superficieM2Input, formatNumberEs(v, 0));
  }
}

// ==============================
// FORMATO GLOBAL (todas las pestañas)
// ==============================
function _shouldFormatRaw(raw) {
  if (raw === null || typeof raw === "undefined") return false;
  const s = String(raw).trim();
  return s !== "";
}

function aplicarFormatoGlobal(root = document) {
  try {
    // 1) EUROS (inputs y spans/divs)
    root.querySelectorAll('[data-euro="true"], .fmt-euro').forEach(el => {
      // No tocar el elemento activo (evitar saltos de cursor)
      if (_isValueElement(el) && document.activeElement === el) return;

      const raw = _getElText(el);
      if (!_shouldFormatRaw(raw)) return;

      const n = parseEuro(raw);
      // Formatear incluso 0 si el usuario escribió algo (p.ej. "0")
      if (Number.isFinite(n)) {
        _setElText(el, formatEuro(n));
      }
    });

    // 2) NÚMEROS (sin €) — usar data-decimals si existe
    root.querySelectorAll('[data-number="true"], .fmt-number').forEach(el => {
      if (_isValueElement(el) && document.activeElement === el) return;

      const raw = _getElText(el);
      if (!_shouldFormatRaw(raw)) return;

      const decimals = (() => {
        const d = el && el.dataset ? el.dataset.decimals : null;
        const n = parseInt(d || "0", 10);
        return Number.isFinite(n) ? n : 0;
      })();

      const n = parseNumberEs(raw);
      if (n !== null) {
        _setElText(el, formatNumberEs(n, decimals));
      }
    });

    // 3) PORCENTAJES — data-decimals y añade " %"
    root.querySelectorAll('[data-percent="true"], .fmt-percent').forEach(el => {
      if (_isValueElement(el) && document.activeElement === el) return;

      let raw = _getElText(el);
      if (!_shouldFormatRaw(raw)) return;

      raw = String(raw).replace(/%/g, "");

      const decimals = (() => {
        const d = el && el.dataset ? el.dataset.decimals : null;
        const n = parseInt(d || "2", 10);
        return Number.isFinite(n) ? n : 2;
      })();

      const n = parseNumberEs(raw);
      if (n !== null) {
        _setElText(el, formatNumberEs(n, decimals) + " %");
      }
    });
  } catch (e) {
    // Ignore
  }
}

function enlazarAutoFormatoInputs(root = document) {
  try {
    // Euros
    root.querySelectorAll('input[data-euro="true"], textarea[data-euro="true"], input.fmt-euro, textarea.fmt-euro').forEach(el => {
      if (el.dataset && el.dataset.fmtBound === "1") return;
      if (el.dataset) el.dataset.fmtBound = "1";
      aplicarFormatoInput(el);
    });

    // Números
    root.querySelectorAll('input[data-number="true"], textarea[data-number="true"], input.fmt-number, textarea.fmt-number').forEach(el => {
      if (el.dataset && el.dataset.fmtBound === "1") return;
      if (el.dataset) el.dataset.fmtBound = "1";
      const decimals = (() => {
        const d = el && el.dataset ? el.dataset.decimals : null;
        const n = parseInt(d || "0", 10);
        return Number.isFinite(n) ? n : 0;
      })();
      aplicarFormatoNumeroInput(el, decimals);
    });

    // Porcentajes (inputs)
    root.querySelectorAll('input[data-percent="true"], textarea[data-percent="true"], input.fmt-percent, textarea.fmt-percent').forEach(el => {
      if (el.dataset && el.dataset.fmtBound === "1") return;
      if (el.dataset) el.dataset.fmtBound = "1";

      const decimals = (() => {
        const d = el && el.dataset ? el.dataset.decimals : null;
        const n = parseInt(d || "2", 10);
        return Number.isFinite(n) ? n : 2;
      })();

      el.addEventListener("blur", () => {
        const raw = String(el.value || "").replace(/%/g, "");
        const n = parseNumberEs(raw);
        if (n === null) {
          el.value = "";
          return;
        }
        el.value = formatNumberEs(n, decimals) + " %";
      });

      el.addEventListener("focus", () => {
        const raw = String(el.value || "").replace(/%/g, "");
        const n = parseNumberEs(raw);
        el.value = n === null ? "" : String(n);
      });
    });
  } catch (e) {
    // Ignore
  }
}

function _engancharFormatoEnPestanas() {
  // Bootstrap (si existe)
  try {
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => {
      tab.addEventListener('shown.bs.tab', () => {
        enlazarAutoFormatoInputs(document);
        aplicarFormatoGlobal(document);
      });
      // Fallback por click
      tab.addEventListener('click', () => {
        setTimeout(() => {
          enlazarAutoFormatoInputs(document);
          aplicarFormatoGlobal(document);
        }, 0);
      });
    });
  } catch (e) {}
}

// ==============================
// INICIALIZACIÓN
// ==============================
document.addEventListener("DOMContentLoaded", () => {
  window.__INV_DEBUG = { STORAGE_NS, estudioIdActual };
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

  // Formato global (Proyecto + Estudio) en todas las pestañas
  enlazarAutoFormatoInputs(document);
  aplicarFormatoGlobal(document);
  _engancharFormatoEnPestanas();


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

  // Convertir a proyecto (FASE 2)
  const btnConvertirProyecto =
    document.getElementById("btnConvertirProyecto") ||
    document.getElementById("btnConvertirAProyecto") ||
    document.querySelector('[data-action="convertir-a-proyecto"]');

  // PDF: mantener SOLO el botón del header (#btnGenerarPdf). Si existe el duplicado legacy (#btnGenerarPDF), eliminarlo.
  const btnGenerarPdf = document.getElementById("btnGenerarPdf");
  const btnGenerarPDFDup = document.getElementById("btnGenerarPDF");
  if (btnGenerarPDFDup && btnGenerarPDFDup !== btnGenerarPdf) {
    try { btnGenerarPDFDup.remove(); } catch (e) {}
  }

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

  // Guardar estudio (solo en modo estudio)
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
              valor_transmision: Number.isFinite(estadoEstudio.valor_transmision) ? estadoEstudio.valor_transmision : 0,

              beneficio_bruto: Number.isFinite(estadoEstudio.comite?.beneficio_bruto)
                ? estadoEstudio.comite.beneficio_bruto
                : 0,

              roi: roiSeguro,

              // --- Datos inmueble (para snapshot/PDF) ---
              valor_referencia: Number.isFinite(estadoEstudio.valor_referencia) ? estadoEstudio.valor_referencia : null,
              tipologia: (estadoEstudio.tipologia || "").trim(),
              superficie_m2: Number.isFinite(estadoEstudio.superficie_m2) ? estadoEstudio.superficie_m2 : null,
              estado_inmueble: (estadoEstudio.estado_inmueble || "").trim(),
              situacion: (estadoEstudio.situacion || "").trim(),

              // También lo enviamos agrupado (por compatibilidad con el builder del snapshot)
              inmueble: {
                nombre_proyecto: nombreProyecto,
                direccion: direccionCompleta,
                ref_catastral: referenciaCatastral,
                valor_referencia: Number.isFinite(estadoEstudio.valor_referencia) ? estadoEstudio.valor_referencia : null,
                tipologia: (estadoEstudio.tipologia || "").trim(),
                superficie_m2: Number.isFinite(estadoEstudio.superficie_m2) ? estadoEstudio.superficie_m2 : null,
                estado: (estadoEstudio.estado_inmueble || "").trim(),
                situacion: (estadoEstudio.situacion || "").trim()
              },

              // ---- Vista inversor (persistencia) ----
              inversure_comision_pct: (() => {
                const sel = document.getElementById("inv_porcentaje_comision");
                const v = sel ? parseFloat(sel.value) : 0;
                return Number.isFinite(v) ? v : 0;
              })(),

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

          // Opción B: tras guardar, limpiamos cache local y volvemos a la lista
          try {
            sessionStorage.removeItem("estudio_inversure_actual");
            sessionStorage.removeItem(`estudio_inversure_${estudioIdActual}`);
            sessionStorage.removeItem("estudios_inversure");
          } catch (e) {}

          window.location.assign("/estudios/");
        }
      } catch (e) {
        alert("Error de comunicación con el servidor");
      }
    });
  }

  // Convertir estudio a proyecto (FASE 2)
  if (btnConvertirProyecto) {
    // Si el script se carga dos veces (por incluirlo en base + plantilla), evitamos doble binding.
    if (btnConvertirProyecto.dataset.boundConvertir === "1") {
      // ya enlazado
    } else {
      btnConvertirProyecto.dataset.boundConvertir = "1";

      // Si el HTML trae onclick="return confirm(...)" u otro handler inline, lo anulamos
      try {
        btnConvertirProyecto.removeAttribute("onclick");
        btnConvertirProyecto.onclick = null;
      } catch (e) {}

      btnConvertirProyecto.addEventListener("click", async function (e) {
        e.preventDefault();

        if (!estudioIdActual) {
          alert("No se pudo identificar el estudio actual.");
          return;
        }

        // Evitar doble click (y doble confirm/fetch)
        if (btnConvertirProyecto.dataset.inflight === "1") return;

        const ok = confirm("¿Convertir este estudio en proyecto? El estudio quedará bloqueado.");
        if (!ok) return;

        btnConvertirProyecto.dataset.inflight = "1";
        const prevText = btnConvertirProyecto.textContent;
        btnConvertirProyecto.disabled = true;
        btnConvertirProyecto.textContent = "Convirtiendo…";

        try {
          const resp = await fetch(`/convertir-a-proyecto/${estudioIdActual}/`, {
            method: "POST",
            headers: {
              "X-CSRFToken": csrftoken
            }
          });

          if (!resp.ok) {
            // Intentar extraer mensaje de error si el backend lo devuelve
            let msg = "No se pudo convertir este estudio en proyecto.";
            try {
              const dataErr = await resp.json();
              if (dataErr && (dataErr.error || dataErr.detail)) msg = dataErr.error || dataErr.detail;
            } catch (e2) {
              // ignore
            }
            alert(msg);
            return;
          }

          let data = {};
          try {
            data = await resp.json();
          } catch (e3) {
            data = {};
          }

          const proyectoId = data.proyecto_id || data.id || (data.proyecto && data.proyecto.id);
          // Si el backend manda redirect, lo respetamos
          const redirectUrl = data.redirect;

          if (redirectUrl) {
            window.location.assign(redirectUrl);
            return;
          }

          if (proyectoId) {
            window.location.assign(`/proyectos/${proyectoId}/`);
            return;
          }

          // Fallback defensivo
          window.location.assign("/proyectos/");
        } catch (e) {
          alert("Error de comunicación con el servidor");
        } finally {
          // Si redirigimos, esto no se verá, pero si hay error sí reponemos estado
          btnConvertirProyecto.dataset.inflight = "0";
          btnConvertirProyecto.disabled = false;
          btnConvertirProyecto.textContent = prevText;
        }
      });
    }
  }