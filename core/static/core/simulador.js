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

function getAppBase() {
  try {
    const base = (window.APP_BASE || (document.body && document.body.dataset && document.body.dataset.appBase) || "/");
    return base.endsWith("/") ? base : base + "/";
  } catch (e) {
    return "/";
  }
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

  // Datos principales
  meses: null,
  financiacion_pct: null,

  // Valoraciones mercado
  valoraciones: {}, // { [data-id]: valor }

  // Datos inmueble (nuevos)
  nombre_proyecto: "",
  direccion: "",
  ref_catastral: "",
  tipologia: "",
  superficie_m2: null,
  estado_inmueble: "",
  situacion: "",

  // ==============================
  // VISTA INVERSOR (PERSISTENTE)
  // ==============================
  // Comisión Inversure (%) y su cálculo en €
  comision_inversure_pct: 0,
  comision_inversure_eur: 0,
  // Legacy/compatibilidad
  inversure_comision_pct: 0,
  inversure_comision_eur: 0,

  // KPIs inversor
  inversion_total: 0,
  beneficio: 0,
  beneficio_neto: 0,
  roi_neto: 0,

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
const mesesInput = document.getElementById("meses");
const financiacionPctInput = document.getElementById("financiacion_pct");
const valorAdquisicionInput = document.getElementById("valor_adquisicion");
const valorTransmisionInput = document.getElementById("valor_transmision");
const mediaValoracionesInput = document.getElementById("media_valoraciones");
const valoracionesInputs = document.querySelectorAll(".valoracion");
const tipologiaInput = document.getElementById("tipologia");
const superficieM2Input = document.getElementById("superficie_m2");
const estadoInmuebleInput = document.getElementById("estado_inmueble") || document.getElementById("estado");
const situacionInput = document.getElementById("situacion");
function _byIdOrName(ids = [], names = []) {
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) return el;
  }
  for (const nm of names) {
    const el = document.querySelector(`[name="${nm}"]`);
    if (el) return el;
  }
  return null;
}

const nombreProyectoInput = _byIdOrName(
  ["nombre_proyecto", "proyecto_nombre", "nombre", "nombre_estudio", "nombre_operacion"],
  ["nombre_proyecto", "proyecto_nombre", "nombre", "nombre_estudio", "nombre_operacion"]
);
const direccionInput = _byIdOrName(
  ["direccion", "direccion_inmueble", "direccion_completa"],
  ["direccion", "direccion_inmueble", "direccion_completa"]
);
const refCatastralInput = _byIdOrName(
  ["ref_catastral", "referencia_catastral", "refCat", "ref_catastral_inmueble"],
  ["ref_catastral", "referencia_catastral", "refCat", "ref_catastral_inmueble"]
);
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
// VISTA INVERSOR · ELEMENTOS DOM
// ==============================
const comisionInversurePctInput = _byIdOrName(
  ["comision_inversure_pct", "inversure_comision_pct", "comision_pct", "comisionInversurePct"],
  ["comision_inversure_pct", "inversure_comision_pct", "comision_pct"]
);

// Salidas típicas (pueden ser <input> o <span>/<div>)
const inversionTotalEl = document.getElementById("inversion_total") || document.getElementById("kpi_inversion_total");
const comisionInversureEurEl = document.getElementById("comision_inversure_eur") || document.getElementById("inversure_comision_eur");
const beneficioNetoEl = document.getElementById("beneficio_neto") || document.getElementById("kpi_beneficio_neto");
const roiNetoEl = document.getElementById("roi_neto") || document.getElementById("kpi_roi_neto");

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
      const nom = nombreProyectoInput ? (nombreProyectoInput.value || "").trim() : "";
      const dir = direccionInput ? (direccionInput.value || "").trim() : "";
      const rc = refCatastralInput ? (refCatastralInput.value || "").trim() : "";
      return (extras > 0) || (ref > 0) || algunaVal || (sup > 0) || !!tip || !!est || !!sit || !!nom || !!dir || !!rc;
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
      actualizarVistaInversor();
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
    actualizarVistaInversor();
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
  if (nombreProyectoInput && document.activeElement !== nombreProyectoInput) {
    nombreProyectoInput.value = estadoEstudio.nombre_proyecto || "";
  }
  if (direccionInput && document.activeElement !== direccionInput) {
    direccionInput.value = estadoEstudio.direccion || "";
  }
  if (refCatastralInput && document.activeElement !== refCatastralInput) {
    refCatastralInput.value = estadoEstudio.ref_catastral || "";
  }
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
  const beneficio = (estadoEstudio.valor_transmision || 0) - (estadoEstudio.valor_adquisicion || 0);

  // ==============================
  // MÉTRICAS VISTA INVERSOR
  // ==============================
  // Beneficio bruto (para inversor también)
  estadoEstudio.beneficio = beneficio;

  // Comisión Inversure (%) configurable. Si no existe input, mantener lo que hubiera en estado o 0.
  let comisionPct = null;

  // 1) Si el input está ENFOCADO o tiene valor explícito, mandan los inputs
  if (comisionInversurePctInput) {
    const raw = _getElText(comisionInversurePctInput);
    const v = parseNumberEs(raw);
    if (v !== null && Number.isFinite(v)) {
      comisionPct = v;
    }
  }

  // 2) Si el input está vacío/no editable, usar el estado persistido
  if (comisionPct === null) {
    if (Number.isFinite(estadoEstudio.comision_inversure_pct)) {
      comisionPct = estadoEstudio.comision_inversure_pct;
    } else if (Number.isFinite(estadoEstudio.inversure_comision_pct)) {
      comisionPct = estadoEstudio.inversure_comision_pct;
    } else {
      comisionPct = 0;
    }
  }

  // Normalizar rango
  comisionPct = Math.max(0, Math.min(100, comisionPct));
  estadoEstudio.comision_inversure_pct = comisionPct;
  estadoEstudio.inversure_comision_pct = comisionPct; // legacy

  // Comisión en €: por defecto se aplica SOLO sobre beneficio positivo
  const baseComision = Math.max(0, beneficio);
  const comisionEur = baseComision * (comisionPct / 100);
  estadoEstudio.comision_inversure_eur = comisionEur;
  estadoEstudio.inversure_comision_eur = comisionEur; // legacy

  // Inversión total del inversor: por defecto, valor de adquisición
  const inversionTotal = estadoEstudio.valor_adquisicion || 0;
  estadoEstudio.inversion_total = inversionTotal;

  // Beneficio neto y ROI neto
  const beneficioNeto = beneficio - comisionEur;
  estadoEstudio.beneficio_neto = beneficioNeto;
  estadoEstudio.roi_neto = inversionTotal > 0 ? (beneficioNeto / inversionTotal) * 100 : 0;

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
  actualizarVistaInversor();

  guardarEstado();
}

// ==============================
// PINTADO · VISTA INVERSOR
// ==============================
function actualizarVistaInversor() {
  try {
    // Si existen elementos en la vista inversor, los actualizamos.
    if (inversionTotalEl) {
      const v = estadoEstudio.inversion_total;
      _setElText(
        inversionTotalEl,
        Number.isFinite(v) ? formatEuro(v) : "—"
      );
    }

    if (comisionInversureEurEl) {
      const v = estadoEstudio.comision_inversure_eur;
      _setElText(
        comisionInversureEurEl,
        Number.isFinite(v) ? formatEuro(v) : "—"
      );
    }

    if (beneficioNetoEl) {
      const v = estadoEstudio.beneficio_neto;
      _setElText(
        beneficioNetoEl,
        Number.isFinite(v) ? formatEuro(v) : "—"
      );
    }

    if (roiNetoEl) {
      const v = estadoEstudio.roi_neto;
      _setElText(
        roiNetoEl,
        Number.isFinite(v) ? formatNumberEs(v, 2) : "—"
      );
    }

    // Mantener el select/input de % sincronizado con el estado (UX limpia)
    if (comisionInversurePctInput) {
      const pct = estadoEstudio.comision_inversure_pct;

      if (Number.isFinite(pct) && pct > 0) {
        // Forzar visualización coherente (aunque no esté enfocado)
        comisionInversurePctInput.value = String(pct);
      } else {
        // Mostrar placeholder "Selecciona…"
        comisionInversurePctInput.value = "";
      }
    }
  } catch (e) {
    // Ignore
  }
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
    kpiRoi.textContent = Number.isFinite(v) ? formatNumberEs(v, 2) : "—";
  }

  if (kpiMargen) {
    const v = estadoEstudio.comite.margen_pct;
    kpiMargen.textContent = Number.isFinite(v) ? formatNumberEs(v, 2) : "—";
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
 if (typeof renderSemaforoVisual === "function") renderSemaforoVisual();
if (typeof renderRoiBarra === "function") renderRoiBarra();
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
// EVENTO · % COMISIÓN INVERSURE (VISTA INVERSOR)
// ==============================
if (comisionInversurePctInput) {
  comisionInversurePctInput.addEventListener("input", () => {
    const v = parseNumberEs(_getElText(comisionInversurePctInput));
    estadoEstudio.comision_inversure_pct = (v === null) ? 0 : v;
    estadoEstudio.inversure_comision_pct = estadoEstudio.comision_inversure_pct; // legacy
    recalcularTodo();
  });

  // Formateo suave en blur/focus (por si es input)
  if (_isValueElement(comisionInversurePctInput)) {
    comisionInversurePctInput.addEventListener("blur", () => {
      const v = parseNumberEs(comisionInversurePctInput.value);
      comisionInversurePctInput.value = (v === null) ? "" : formatNumberEs(v, 2);
    });
    comisionInversurePctInput.addEventListener("focus", () => {
      const v = parseNumberEs(comisionInversurePctInput.value);
      comisionInversurePctInput.value = (v === null) ? "" : String(v);
    });
  }
}

// ==============================
// EVENTOS CAMPOS INMUEBLE (PERSISTENCIA)
// ==============================
if (nombreProyectoInput) {
  nombreProyectoInput.addEventListener("input", () => {
    estadoEstudio.nombre_proyecto = (nombreProyectoInput.value || "").trim();
    guardarEstado();
  });
}

if (direccionInput) {
  direccionInput.addEventListener("input", () => {
    estadoEstudio.direccion = (direccionInput.value || "").trim();
    guardarEstado();
  });
}

if (refCatastralInput) {
  refCatastralInput.addEventListener("input", () => {
    estadoEstudio.ref_catastral = (refCatastralInput.value || "").trim();
    guardarEstado();
  });
}

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

// ==============================
// EVENTOS · DATOS PRINCIPALES
// ==============================
if (mesesInput) {
  aplicarFormatoNumeroInput(mesesInput, 0);
  mesesInput.addEventListener("input", () => {
    const v = parseNumberEs(mesesInput.value);
    estadoEstudio.meses = (v === null) ? null : v;
    guardarEstado();
  });
}

if (financiacionPctInput) {
  aplicarFormatoNumeroInput(financiacionPctInput, 2);
  financiacionPctInput.addEventListener("input", () => {
    const v = parseNumberEs(financiacionPctInput.value);
    estadoEstudio.financiacion_pct = (v === null) ? null : v;
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
    const v = resumenEjecutivoComite.value || "";
    estadoEstudio.comite.resumen_ejecutivo = v;
    estadoEstudio.comite.observaciones = v;
    guardarEstado();
  });
}

function persistirValoracionComite() {
  estadoEstudio.comite.valoracion.mercado = valoracionMercado?.value || "";
  estadoEstudio.comite.valoracion.riesgo = valoracionRiesgo?.value || "";
  estadoEstudio.comite.valoracion.ejecucion = valoracionEjecucion?.value || "";
  estadoEstudio.comite.valoracion.timing = valoracionTiming?.value || "";
  const comentario = comentarioComite?.value || "";
  estadoEstudio.comite.comentario = comentario;
  if (comentario) estadoEstudio.comite.observaciones = comentario;
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
    estadoEstudio.comite.decision = nuevaDecision;

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

  // Nombre / dirección / ref catastral
  if ((estadoEstudio.nombre_proyecto === null || typeof estadoEstudio.nombre_proyecto === "undefined" || estadoEstudio.nombre_proyecto === "") && nombreProyectoInput?.value) {
    estadoEstudio.nombre_proyecto = (nombreProyectoInput.value || "").trim();
  }
  if ((estadoEstudio.direccion === null || typeof estadoEstudio.direccion === "undefined" || estadoEstudio.direccion === "") && direccionInput?.value) {
    estadoEstudio.direccion = (direccionInput.value || "").trim();
  }
  if ((estadoEstudio.ref_catastral === null || typeof estadoEstudio.ref_catastral === "undefined" || estadoEstudio.ref_catastral === "") && refCatastralInput?.value) {
    estadoEstudio.ref_catastral = (refCatastralInput.value || "").trim();
  }

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

  // Meses de operación
  if ((estadoEstudio.meses === null || typeof estadoEstudio.meses === "undefined") && mesesInput?.value) {
    const v = parseNumberEs(mesesInput.value);
    if (v !== null) estadoEstudio.meses = v;
  }

  // % financiación
  if ((estadoEstudio.financiacion_pct === null || typeof estadoEstudio.financiacion_pct === "undefined") && financiacionPctInput?.value) {
    const v = parseNumberEs(financiacionPctInput.value);
    if (v !== null) estadoEstudio.financiacion_pct = v;
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

  if (mesesInput) {
    const v = parseNumberEs(_getElText(mesesInput));
    if (v !== null) _setElText(mesesInput, formatNumberEs(v, 0));
  }

  if (financiacionPctInput) {
    const v = parseNumberEs(_getElText(financiacionPctInput));
    if (v !== null) _setElText(financiacionPctInput, formatNumberEs(v, 2));
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
      // NO tocar KPIs (ni por clase ni por id)
      if (el.closest && el.closest('.kpi')) return; // NO tocar KPIs
      if (el.id && el.id.startsWith('kpi_')) return; // NO tocar KPIs
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
      if (el.closest && el.closest('.kpi')) return; // NO tocar KPIs
      if (el.id && el.id.startsWith('kpi_')) return; // NO tocar KPIs
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
      if (el.closest && el.closest('.kpi')) return; // NO tocar KPIs
      if (el.id && el.id.startsWith('kpi_')) return; // NO tocar KPIs
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
  // ACCIONES (GUARDAR / CONVERTIR) · ROBUSTO
  // ==============================
  const formEstudio = document.getElementById("form-estudio");
  const isAdmin = formEstudio && formEstudio.dataset && formEstudio.dataset.isAdmin === "1";

  function _inferActionFromElement(el) {
    if (!el) return "";
    const txt = (
      el.dataset?.action ||
      el.getAttribute?.("data-action") ||
      el.id ||
      el.name ||
      el.value ||
      el.textContent ||
      ""
    )
      .toString()
      .toLowerCase();

    if (txt.includes("convert")) return "convert";
    if (txt.includes("guardar") || txt.includes("save")) return "save";
    return "";
  }

  async function _runAction(action) {
    if (!formEstudio) return;

    if (formEstudio.dataset.busy === "1") return;
    formEstudio.dataset.busy = "1";

    try {
      if (action === "convert") {
        if (typeof convertirAProyectoFallback === "function") {
          await convertirAProyectoFallback();
        }
      } else {
        if (typeof guardarEstudioFallback === "function") {
          await guardarEstudioFallback();
        }
      }
    } finally {
      formEstudio.dataset.busy = "0";
    }
  }

  // Bind acciones una sola vez (Guardar / Convertir)
  function _bind(el, action) {
    if (!el) return;
    if (el.dataset && el.dataset.boundAction === "1") return;
    if (el.dataset) el.dataset.boundAction = "1";

    el.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      await _runAction(action);
    });
  }

  // Resolver ID del estudio (URL -> hidden input -> dataset)
  (function _ensureStudyId() {
    const fromPage = getEstudioIdFromPage();
    if (fromPage) {
      estudioIdActual = fromPage;
      estadoEstudio.id = fromPage;
      return;
    }
    const hid = document.getElementById("estudio_id") || document.getElementById("id_estudio");
    if (hid && hid.value) {
      estudioIdActual = String(hid.value).trim();
      estadoEstudio.id = estudioIdActual;
      return;
    }
    if (formEstudio && formEstudio.dataset && formEstudio.dataset.estudioId) {
      estudioIdActual = String(formEstudio.dataset.estudioId).trim();
      estadoEstudio.id = estudioIdActual;
    }
  })();

  // Fallback de guardado (si no existe en el resto del archivo)
  window.guardarEstudioFallback = window.guardarEstudioFallback || (async function guardarEstudioFallback() {
    try { guardarEstado(); } catch (e) {}

    // Sincronizar campos de inmueble justo antes de guardar (por si el usuario no ha perdido foco)
    if (nombreProyectoInput) estadoEstudio.nombre_proyecto = (nombreProyectoInput.value || "").trim();
    if (direccionInput) estadoEstudio.direccion = (direccionInput.value || "").trim();
    if (refCatastralInput) estadoEstudio.ref_catastral = (refCatastralInput.value || "").trim();
    if (mesesInput) {
      const v = parseNumberEs(mesesInput.value);
      estadoEstudio.meses = (v === null) ? null : v;
    }
    if (financiacionPctInput) {
      const v = parseNumberEs(financiacionPctInput.value);
      estadoEstudio.financiacion_pct = (v === null) ? null : v;
      estadoEstudio.porcentaje_financiacion = estadoEstudio.financiacion_pct;
    }

    // Aliases legacy por compatibilidad (si alguna vista/serializer espera estos nombres)
    estadoEstudio.nombre = estadoEstudio.nombre_proyecto;
    estadoEstudio.direccion_inmueble = estadoEstudio.direccion;
    estadoEstudio.referencia_catastral = estadoEstudio.ref_catastral;

    const id = String(estudioIdActual || "").trim();
    if (!id) {
      alert("No se ha podido guardar: falta el ID del estudio.");
      return;
    }

    const url = (formEstudio && (formEstudio.dataset.guardarUrl || formEstudio.getAttribute("action"))) || (getAppBase() + "guardar-estudio/");
    const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRFToken": csrf } : {})
      },
      body: JSON.stringify({ estudio_id: parseInt(id, 10), datos: estadoEstudio }),
    });

    if (!resp.ok) {
      const t = await resp.text().catch(() => "");
      console.error("Error guardando estudio:", resp.status, t);
      alert("No se pudo guardar (error del servidor). Mira consola/terminal.");
      return;
    }

    window.location.href = getAppBase() + "estudios/";
  });

  // Fallback de convertir (si no existe en el resto del archivo)
  window.convertirAProyectoFallback = window.convertirAProyectoFallback || (async function convertirAProyectoFallback() {
    const id = String(estudioIdActual || "").trim();
    if (!id) {
      alert("No se ha podido convertir: falta el ID del estudio.");
      return;
    }

    const ok = confirm("¿Convertir este estudio en proyecto? El estudio quedará bloqueado.");
    if (!ok) return;

    const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
    let url = (formEstudio && formEstudio.dataset.convertirUrl) || (getAppBase() + `convertir-a-proyecto/${parseInt(id, 10)}/`);
    if (url.startsWith("/convertir-a-proyecto/")) {
      const base = getAppBase().replace(/\/$/, "");
      url = `${base}${url}`;
    }

    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRFToken": csrf } : {})
      },
      body: JSON.stringify({ estudio_id: parseInt(id, 10), approve: isAdmin })
    });

    const data = await resp.json().catch(() => ({}));
    if (resp.status === 202 && data && data.status === "pending_approval") {
      alert(data.message || "Solicitud enviada. Un administrador debe aprobar la conversión.");
      return;
    }
    if (resp.status === 409 && data && data.requires_approval) {
      alert(data.error || "Se requiere aprobación de administrador.");
      return;
    }
    if (!resp.ok || data.ok === false) {
      console.error("Error convirtiendo a proyecto:", resp.status, data);
      alert("No se pudo convertir este estudio en proyecto.");
      return;
    }

    window.location.href = data.redirect || data.redirect_url || (getAppBase() + "proyectos/");
  });

  // 1) Bind por data-action / ids / name
  Array.from(document.querySelectorAll("button, a, input[type='button'], input[type='submit']")).forEach((el) => {
    const inferred = _inferActionFromElement(el);
    if (inferred === "save") _bind(el, "save");
    if (inferred === "convert") _bind(el, "convert");
  });

  // 2) Delegación: si el HTML cambia, seguimos capturando clicks por texto
  document.addEventListener("click", (ev) => {
    const el = ev.target && ev.target.closest ? ev.target.closest("button, a, input[type='button'], input[type='submit']") : null;
    if (!el) return;
    const t = (el.textContent || el.value || "").toString().toLowerCase();
    if (t.includes("guardar")) {
      ev.preventDefault();
      _runAction("save");
    }
    if (t.includes("convert") || t.includes("proyecto")) {
      // evitar que cualquier botón con 'proyecto' dispare convertir si no es el botón
      if (t.includes("convert")) {
        ev.preventDefault();
        _runAction("convert");
      }
    }
  }, true);

  // Guardado local continuo (para no perder datos al volver al listado)
  let _saveT = null;
  document.addEventListener("input", () => {
    clearTimeout(_saveT);
    _saveT = setTimeout(() => {
      try { guardarEstado(); } catch (e) {}
    }, 250);
  }, true);

  // Cargar + inicializar + formato
  cargarEstado();
  inicializarEstadoDesdeInputsSiVacio();
  enlazarAutoFormatoInputs(document);
  formateoInicialInputs();
  _engancharFormatoEnPestanas();
  aplicarFormatoGlobal(document);
  recalcularTodo();
});
