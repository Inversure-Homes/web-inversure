/*
  Proyecto JS (aislado del simulador)
  - Mapa (verMapa) para la vista Proyecto
  - Formateo numérico global en todas las pestañas del Proyecto

  Convención en HTML:
  - Euros:      data-euro="true" o clase .fmt-euro
  - Números:    data-number="true" o clase .fmt-number (opcional data-decimals="0|1|2")
  - Porcent.:   data-percent="true" o clase .fmt-percent (opcional data-decimals="2")
*/

// -----------------------------
// Parsers / formatters (es-ES)
// -----------------------------
function _normStr(v) {
  return String(v ?? "").replace(/\u00A0/g, " ").trim();
}

function parseNumberEs(value) {
  const raw = _normStr(value);
  if (!raw) return null;

  // Quita espacios
  let s = raw.replace(/\s+/g, "");

  // Limpia símbolos comunes
  s = s.replace(/€/g, "").replace(/%/g, "");

  const hasDot = s.includes(".");
  const hasComma = s.includes(",");

  if (hasDot && hasComma) {
    // Si la última coma va después del último punto => formato ES (miles con punto, decimales con coma)
    if (s.lastIndexOf(",") > s.lastIndexOf(".")) {
      s = s.replace(/\./g, "").replace(/,/g, ".");
    } else {
      // formato EN (miles con coma, decimales con punto)
      s = s.replace(/,/g, "");
    }
  } else if (hasComma && !hasDot) {
    // 12,34 -> 12.34
    s = s.replace(/,/g, ".");
  }

  // Deja solo números, signo y punto
  s = s.replace(/[^0-9.-]/g, "");
  if (!s || s === "-" || s === ".") return null;

  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function parseEuro(value) {
  const n = parseNumberEs(value);
  return n === null ? null : n;
}

function calcCaptacionObjectiveFromInputs() {
  const estadoEl = document.getElementById("estado_proyecto");
  const estado = estadoEl ? String(_getElText(estadoEl)).toLowerCase() : "";
  const usarEstimados = ["estudio", "captacion"].includes(estado);

  const baseInput = parseEuro(_getElText(document.querySelector("[name='precio_compra_inmueble']")));
  const baseRealText = parseEuro(_getElText(document.getElementById("valor_adq_real")));
  const baseEstText = parseEuro(_getElText(document.getElementById("valor_adq_estimado")));
  const gastosDashEst = parseEuro(_getElText(document.getElementById("dash_gastos_estimados")));
  const gastosDashReal = parseEuro(_getElText(document.getElementById("dash_gastos_reales")));
  const gastosEstText = parseEuro(_getElText(document.getElementById("eco_total_estimado")));
  const gastosRealText = parseEuro(_getElText(document.getElementById("eco_total_real")));

  const gastosPreferidos = usarEstimados ? gastosDashEst : gastosDashReal;
  const gastosFallback = usarEstimados ? gastosEstText : gastosRealText;
  const base =
    (Number.isFinite(gastosPreferidos) && gastosPreferidos > 0)
      ? gastosPreferidos
      : ((Number.isFinite(gastosFallback) && gastosFallback > 0)
        ? gastosFallback
        : ((Number.isFinite(baseInput) && baseInput > 0)
          ? baseInput
          : ((Number.isFinite(baseRealText) && baseRealText > 0)
            ? baseRealText
            : (Number.isFinite(baseEstText) && baseEstText > 0 ? baseEstText : 0))));

  const objetivo = base;
  return Number.isFinite(objetivo) ? Math.max(0, objetivo) : 0;
}

function formatNumberEs(num, decimals = 0) {
  if (!Number.isFinite(num)) return "";
  return new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num);
}

function formatEuro(num) {
  if (!Number.isFinite(num)) return "";
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

function _isValueElement(el) {
  if (!el || !el.tagName) return false;
  const t = el.tagName.toUpperCase();
  return t === "INPUT" || t === "TEXTAREA" || t === "SELECT";
}

function _getElText(el) {
  if (!el) return "";
  return _isValueElement(el) ? (el.value ?? "") : (el.textContent ?? "");
}

function _setElText(el, v) {
  if (!el) return;
  if (_isValueElement(el)) el.value = v;
  else el.textContent = v;
}

function _shouldFormatRaw(raw) {
  const s = _normStr(raw);
  return s !== "";
}

// -----------------------------
// Formateo global (Proyecto)
// -----------------------------
function aplicarFormatoGlobal(root = document) {
  try {
    // EUROS
    root.querySelectorAll('[data-euro="true"], .fmt-euro').forEach(el => {
      if (_isValueElement(el) && document.activeElement === el) return;
      const raw = _getElText(el);
      if (!_shouldFormatRaw(raw)) return;
      const n = parseEuro(raw);
      if (n === null) return;
      _setElText(el, formatEuro(n));
    });

    // NÚMEROS (sin €)
    root.querySelectorAll('[data-number="true"], .fmt-number').forEach(el => {
      if (_isValueElement(el) && document.activeElement === el) return;
      const raw = _getElText(el);
      if (!_shouldFormatRaw(raw)) return;
      const decimals = (() => {
        const d = el?.dataset?.decimals;
        const n = parseInt(d ?? "0", 10);
        return Number.isFinite(n) ? n : 0;
      })();
      const n = parseNumberEs(raw);
      if (n === null) return;
      _setElText(el, formatNumberEs(n, decimals));
    });

    // PORCENTAJES
    root.querySelectorAll('[data-percent="true"], .fmt-percent').forEach(el => {
      if (_isValueElement(el) && document.activeElement === el) return;
      let raw = _getElText(el);
      if (!_shouldFormatRaw(raw)) return;
      raw = String(raw).replace(/%/g, "");
      const decimals = (() => {
        const d = el?.dataset?.decimals;
        const n = parseInt(d ?? "2", 10);
        return Number.isFinite(n) ? n : 2;
      })();
      const n = parseNumberEs(raw);
      if (n === null) return;
      _setElText(el, formatNumberEs(n, decimals) + " %");
    });
  } catch (e) {
    // Silencioso: no queremos romper la vista
  }
}

function enlazarAutoFormatoInputs(root = document) {
  try {
    // Euros (inputs)
    root.querySelectorAll('input[data-euro="true"], textarea[data-euro="true"], input.fmt-euro, textarea.fmt-euro').forEach(el => {
      if (el?.dataset?.fmtBound === "1") return;
      if (el.dataset) el.dataset.fmtBound = "1";

      el.addEventListener("blur", () => {
        const n = parseEuro(el.value);
        if (n === null) {
          el.value = "";
          return;
        }
        el.value = formatEuro(n);
      });

      el.addEventListener("focus", () => {
        const n = parseEuro(el.value);
        el.value = n === null ? "" : String(n);
      });
    });

    // Números (inputs)
    root.querySelectorAll('input[data-number="true"], textarea[data-number="true"], input.fmt-number, textarea.fmt-number').forEach(el => {
      if (el?.dataset?.fmtBound === "1") return;
      if (el.dataset) el.dataset.fmtBound = "1";

      const decimals = (() => {
        const d = el?.dataset?.decimals;
        const n = parseInt(d ?? "0", 10);
        return Number.isFinite(n) ? n : 0;
      })();

      el.addEventListener("blur", () => {
        const n = parseNumberEs(el.value);
        if (n === null) {
          el.value = "";
          return;
        }
        el.value = formatNumberEs(n, decimals);
      });

      el.addEventListener("focus", () => {
        const n = parseNumberEs(el.value);
        el.value = n === null ? "" : String(n);
      });
    });

    // Porcentajes (inputs)
    root.querySelectorAll('input[data-percent="true"], textarea[data-percent="true"], input.fmt-percent, textarea.fmt-percent').forEach(el => {
      if (el?.dataset?.fmtBound === "1") return;
      if (el.dataset) el.dataset.fmtBound = "1";

      const decimals = (() => {
        const d = el?.dataset?.decimals;
        const n = parseInt(d ?? "2", 10);
        return Number.isFinite(n) ? n : 2;
      })();

      el.addEventListener("blur", () => {
        const raw = String(el.value ?? "").replace(/%/g, "");
        const n = parseNumberEs(raw);
        if (n === null) {
          el.value = "";
          return;
        }
        el.value = formatNumberEs(n, decimals) + " %";
      });

      el.addEventListener("focus", () => {
        const raw = String(el.value ?? "").replace(/%/g, "");
        const n = parseNumberEs(raw);
        el.value = n === null ? "" : String(n);
      });
    });
  } catch (e) {
    // Silencioso
  }
}

function engancharFormatoEnPestanas() {
  try {
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => {
      tab.addEventListener("shown.bs.tab", () => {
        enlazarAutoFormatoInputs(document);
        aplicarFormatoGlobal(document);
      });
      tab.addEventListener("click", () => {
        setTimeout(() => {
          enlazarAutoFormatoInputs(document);
          aplicarFormatoGlobal(document);
        }, 0);
      });
    });
  } catch (e) {}
}

// -----------------------------
// Mapa (Proyecto)
// -----------------------------
function _findValueBySelectors(selectors) {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (!el) continue;
    const v = _normStr(_getElText(el));
    if (v) return v;
  }
  return "";
}

function construirQueryMapa() {
  // Intentamos dirección primero, luego ref catastral
  const direccion = _findValueBySelectors([
    "#direccion_completa",
    "#direccion",
    "#id_direccion",
    "[name='direccion']",
    "[name='direccion_completa']",
  ]);

  const ref = _findValueBySelectors([
    "#ref_catastral",
    "#id_ref_catastral",
    "[name='ref_catastral']",
  ]);

  return direccion || ref || "";
}

let __mapLastQuery = "";

function setMapaSrc(query) {
  const iframe = document.querySelector("#mapIframe") || document.querySelector("iframe[data-role='map']");
  if (!iframe) return;
  const q = _normStr(query);
  if (!q) return;

  // Evita recargar el iframe si la query no ha cambiado (mejora UX y rendimiento)
  if (q === __mapLastQuery) return;
  __mapLastQuery = q;

  iframe.src = "https://www.google.com/maps?q=" + encodeURIComponent(q) + "&output=embed";
}


const MAPA_DEBOUNCE_MS = 500;
let __mapDebounceTimer = null;

function bindMapaAutoUpdate() {
  try {
    const selectors = [
      "#direccion_completa",
      "#direccion",
      "#id_direccion",
      "[name='direccion']",
      "[name='direccion_completa']",
      "#ref_catastral",
      "#id_ref_catastral",
      "[name='ref_catastral']",
    ];

    const targets = selectors
      .map(sel => document.querySelector(sel))
      .filter(Boolean);

    if (!targets.length) return;

    const schedule = () => {
      if (__mapDebounceTimer) clearTimeout(__mapDebounceTimer);
      __mapDebounceTimer = setTimeout(() => {
        try {
          const q = construirQueryMapa();
          if (q) setMapaSrc(q);
        } catch (e) {}
      }, MAPA_DEBOUNCE_MS);
    };

    targets.forEach(el => {
      // Evitar dobles bindings si el script se re-ejecuta
      if (el.dataset && el.dataset.mapBound === "1") return;
      if (el.dataset) el.dataset.mapBound = "1";

      el.addEventListener("input", schedule);
      el.addEventListener("change", schedule);
      el.addEventListener("blur", schedule);
    });
  } catch (e) {
    // Silencioso
  }
}

// Exponer verMapa para que el HTML lo pueda llamar

window.verMapa = function verMapa() {
  const q = construirQueryMapa();
  if (q) setMapaSrc(q);
};

// -----------------------------
// Título (Proyecto) - sync en vivo
// -----------------------------
function _setProyectoTituloEnHeader(nombre) {
  try {
    const n = _normStr(nombre);
    if (!n) return;

    // Targets típicos: id, data-role, clase o cabecera principal
    const targets = [
      "#proyectoTitulo",
      "[data-role='proyecto-titulo']",
      "[data-proyecto-titulo]",
      ".proyecto-titulo",
      "h1.proyecto-titulo",
      "h1[data-proyecto]",
    ];

    let updated = false;
    for (const sel of targets) {
      const el = document.querySelector(sel);
      if (!el) continue;
      _setElText(el, n);
      updated = true;
    }

    // Si no hay un target específico, como fallback intentamos el primer H1 de la página
    if (!updated) {
      const h1 = document.querySelector("main h1") || document.querySelector("h1");
      if (h1) _setElText(h1, n);
    }

    // Título de la pestaña del navegador
    try {
      if (document && document.title) {
        const base = document.title.split("|").pop()?.trim() || "Inversure";
        document.title = `${n} | ${base}`;
      }
    } catch (e) {}
  } catch (e) {}
}

function bindNombreProyectoLiveUpdate() {
  try {
    const inputs = [
      "[name='nombre_proyecto']",
      "[name='inmueble.nombre_proyecto']",
      "#nombre_proyecto",
      "#id_nombre_proyecto",
      "[name='nombre']",
      "#nombre",
      "#id_nombre",
    ]
      .map(sel => document.querySelector(sel))
      .filter(Boolean);

    if (!inputs.length) return;

    const handler = (ev) => {
      const el = ev && ev.target ? ev.target : inputs[0];
      if (!el) return;
      const val = _getElText(el);
      if (!_normStr(val)) return;
      _setProyectoTituloEnHeader(val);
    };

    inputs.forEach(el => {
      if (el.dataset && el.dataset.titleBound === "1") return;
      if (el.dataset) el.dataset.titleBound = "1";

      el.addEventListener("input", handler);
      el.addEventListener("change", handler);
      el.addEventListener("blur", handler);

      // Inicializar al cargar
      try { handler({ target: el }); } catch (e) {}
    });
  } catch (e) {}
}

// -----------------------------
// Derivados (Proyecto)
// -----------------------------
(function initDerivadosProyecto() {
  // Setter seguro para actualizar el DOM cuando calculamos derivados
  window.__setValorAdquisicionDom = function (valor) {
    try {
      const targets = [
        "[name='valor_adquisicion_total']",
        "[name='valor_adquisicion']",
        "[name='precio_compra_inmueble']",
        "[data-bind='kpis.metricas.valor_adquisicion_total']",
        "[data-bind='kpis.metricas.valor_adquisicion']",
        "#valor_adquisicion_total",
        "#valor_adquisicion",
      ];

      for (const sel of targets) {
        const el = document.querySelector(sel);
        if (!el) continue;
        if (_isValueElement(el) && document.activeElement === el) continue; // no pisar si el usuario lo edita
        _setElText(el, String(valor));
      }

      // Dejarlo bonito con el formato global
      aplicarFormatoGlobal(document);
    } catch (e) {}
  };

  function getEuroFromSelectors(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (!el) continue;
      const raw = _getElText(el);
      const n = parseEuro(raw);
      if (n !== null) return n;
    }
    return null;
  }

  // Recalcula en vivo: Valor de adquisición = Precio escritura + gastos
  window.__recalcValorAdquisicion = function () {
    try {
      const precio = getEuroFromSelectors([
        "[name='precio_escritura']",
        "[name='precio_propiedad']",
        "[name='kpis.metricas.precio_escritura']",
        "#precio_escritura",
      ]);
      if (precio === null) return;

      const gastoGroups = [
        ["[name='itp']", "[name='kpis.metricas.itp']", "#itp"],
        ["[name='notaria']", "[name='kpis.metricas.notaria']", "#notaria"],
        ["[name='registro']", "[name='kpis.metricas.registro']", "#registro"],
        ["[name='gestoria']", "[name='kpis.metricas.gestoria']", "#gestoria"],
        ["[name='tasacion']", "[name='kpis.metricas.tasacion']", "#tasacion"],
        ["[name='otros_gastos']", "[name='otros_gastos_compra']", "[name='kpis.metricas.otros_gastos']", "#otros_gastos"],
        ["[name='otros_gastos_adquisicion']", "[name='kpis.metricas.otros_gastos_adquisicion']", "#otros_gastos_adquisicion"],
        ["[name='reforma']", "[name='kpis.metricas.reforma']"],
        ["[name='limpieza_inicial']", "[name='kpis.metricas.limpieza_inicial']"],
        ["[name='mobiliario']", "[name='kpis.metricas.mobiliario']"],
        ["[name='otros_puesta_marcha']", "[name='kpis.metricas.otros_puesta_marcha']"],
        ["[name='obra_demoliciones']", "[name='kpis.metricas.obra_demoliciones']"],
        ["[name='obra_albanileria']", "[name='kpis.metricas.obra_albanileria']"],
        ["[name='obra_fontaneria']", "[name='kpis.metricas.obra_fontaneria']"],
        ["[name='obra_electricidad']", "[name='kpis.metricas.obra_electricidad']"],
        ["[name='obra_carpinteria_interior']", "[name='kpis.metricas.obra_carpinteria_interior']"],
        ["[name='obra_carpinteria_exterior']", "[name='kpis.metricas.obra_carpinteria_exterior']"],
        ["[name='obra_cocina']", "[name='kpis.metricas.obra_cocina']"],
        ["[name='obra_banos']", "[name='kpis.metricas.obra_banos']"],
        ["[name='obra_pintura']", "[name='kpis.metricas.obra_pintura']"],
        ["[name='obra_otros']", "[name='kpis.metricas.obra_otros']"],
        ["[name='cerrajero']", "[name='kpis.metricas.cerrajero']"],
        ["[name='alarma']", "[name='kpis.metricas.alarma']"],
        ["[name='comunidad']", "[name='kpis.metricas.comunidad']"],
        ["[name='ibi']", "[name='kpis.metricas.ibi']"],
        ["[name='seguros']", "[name='kpis.metricas.seguros']"],
        ["[name='suministros']", "[name='kpis.metricas.suministros']"],
        ["[name='limpieza_periodica']", "[name='kpis.metricas.limpieza_periodica']"],
        ["[name='ocupas']", "[name='kpis.metricas.ocupas']"],
      ];

      let gastos = 0;
      for (const selectors of gastoGroups) {
        const v = getEuroFromSelectors(selectors);
        if (v !== null) gastos += v;
      }

      const valorAdq = precio + gastos;
      window.__setValorAdquisicionDom(valorAdq);
    } catch (e) {}
  };
})();

// -----------------------------
// Autosave (Proyecto) -> BD
// -----------------------------

const AUTOSAVE_DEBOUNCE_MS = 1200;
const AUTOSAVE_STORAGE_KEY = "inversure_proyecto_autosave_last";

let __autosaveTimer = null;
let __autosaveInFlight = false;
let __autosaveQueued = false;
let __autosaveResolvedUrl = null;
let __autosaveBound = false;
let __autosaveLastPayloadSig = "";

function getCsrfToken() {
  try {
    const m = document.cookie.match(/(^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[2]) : "";
  } catch (e) {
    return "";
  }
}

function getAppBase() {
  try {
    const base = (window.APP_BASE || (document.body && document.body.dataset && document.body.dataset.appBase) || "/");
    return base.endsWith("/") ? base : base + "/";
  } catch (e) {
    return "/";
  }
}

function getProyectoIdFromPath() {
  try {
    const p = (window.location && window.location.pathname) ? window.location.pathname : "";
    const m = p.match(/\/proyectos\/(\d+)\/?/);
    return m ? m[1] : "";
  } catch (e) {
    return "";
  }
}

function getSaveUrlCandidates() {
  const id = getProyectoIdFromPath();
// 0) Prioridad máxima: URL real inyectada por la plantilla en el form
try {
  const form = document.querySelector("#proyectoForm");
  const u = form && form.dataset ? (form.dataset.guardarUrl || "") : "";
  if (u) return [u];
} catch (e) {}
  // 1) Si la plantilla define un global, úsalo
  if (window.PROYECTO_GUARDAR_URL && typeof window.PROYECTO_GUARDAR_URL === "string") {
    return [window.PROYECTO_GUARDAR_URL];
  }

  // 2) Si hay un atributo data-save-url en body o en un contenedor
  const el = document.querySelector("[data-proyecto-save-url]") || document.body;
  const attr = el && el.getAttribute ? el.getAttribute("data-proyecto-save-url") : "";
  if (attr) return [attr];

  // 3) Heurísticas por rutas típicas
  const pathname = (window.location && window.location.pathname) ? window.location.pathname : "";
  const normalized = pathname.endsWith("/") ? pathname : (pathname + "/");

  const candidates = [];
  if (id) {
    const base = getAppBase();
    candidates.push(`${base}proyectos/${id}/guardar/`);
    candidates.push(`${base}proyectos/guardar/${id}/`);
  }
  // Por si la vista detalle es /proyectos/<id>/
  candidates.push(normalized + "guardar/");

  return candidates;
}

function _deepSet(obj, pathParts, value) {
  let cur = obj;
  for (let i = 0; i < pathParts.length; i++) {
    const k = pathParts[i];
    const isLast = i === pathParts.length - 1;
    if (isLast) {
      cur[k] = value;
    } else {
      if (!cur[k] || typeof cur[k] !== "object") cur[k] = {};
      cur = cur[k];
    }
  }
}

function buildOverlayPayloadFromDOM() {
  // Payload con estructura compatible con snapshots
  const payload = {
    proyecto: {},
    inmueble: {},
    kpis: { metricas: {} },
    economico: {},
  };

  const inmuebleKeys = new Set([
    "nombre_proyecto",
    "direccion",
    "direccion_completa",
    "ref_catastral",
    "valor_referencia",
    "tipologia",
    "estado",
    "situacion",
    "superficie_m2",
  ]);

  // Distinguir campos de estado del PROYECTO (ciclo de vida) vs estado del INMUEBLE (conservación)
  function _isProyectoLifecycleField(el, name) {
    if (!el || !name) return false;
    // En proyecto.html el selector de estado del proyecto tiene id="estado_proyecto"
    if (name === "estado" && el.id === "estado_proyecto") return true;
    if (name === "fecha" || name === "responsable") return true;
    // Resultado del cierre: id="resultado_cierre" (solo visible si estado=cerrado)
    if (name === "resultado_cierre" && el.id === "resultado_cierre") return true;
    return false;
  }

  // Nombre del proyecto: debe persistir en columnas del modelo Proyecto (y también puede vivir en inmueble.nombre_proyecto)
  function _isProyectoNameField(el, name) {
    if (!el || !name) return false;
    if (name === "nombre" || name === "nombre_proyecto") return true;
    // variantes habituales en ids
    const id = (el.id || "").toLowerCase();
    if (id === "nombre" || id === "id_nombre" || id === "nombre_proyecto" || id === "id_nombre_proyecto") return true;
    return false;
  }

  // Capturamos valores editables (inputs/select/textarea con name)
  const fields = Array.from(document.querySelectorAll("input[name], select[name], textarea[name]"));

  fields.forEach(el => {
    if (!el || el.disabled) return;
    const name = (el.getAttribute("name") || "").trim();
    if (!name) return;

    // No persistimos CSRF hidden ni cosas vacías sin intención
    if (name.toLowerCase() === "csrfmiddlewaretoken") return;

    const raw = _getElText(el);
    if (!_shouldFormatRaw(raw)) return;

    // Decide tipo de dato según data-*
    let value = raw;

    const isEuro = el.matches('[data-euro="true"], .fmt-euro');
    const isPct = el.matches('[data-percent="true"], .fmt-percent');
    const isNum = el.matches('[data-number="true"], .fmt-number');

    if (isEuro) {
      const n = parseEuro(raw);
      if (n === null) return;
      value = n;
    } else if (isPct) {
      const n = parseNumberEs(String(raw).replace(/%/g, ""));
      if (n === null) return;
      value = n;
    } else if (isNum) {
      const n = parseNumberEs(raw);
      if (n === null) return;
      value = n;
    }

    // Si el name viene con puntos, lo interpretamos como ruta (ej: inmueble.valor_referencia)
    if (name.includes(".")) {
      _deepSet(payload, name.split("."), value);
      return;
    }

    // Campos del ciclo de vida del PROYECTO (no deben ir a inmueble.estado)
    if (_isProyectoLifecycleField(el, name)) {
      if (name === "resultado_cierre") {
        payload.proyecto[name] = (value === "" ? null : value);
      } else {
        payload.proyecto[name] = value;
      }
      return;
    }

    // Nombre del proyecto: guardarlo también en payload.proyecto para que el backend lo persista en BD
    if (_isProyectoNameField(el, name)) {
      payload.proyecto.nombre_proyecto = value;
      payload.proyecto.nombre = value;
      // Si el input se llama exactamente "nombre", evitamos que caiga en kpis.metricas por defecto.
      if (name === "nombre") return;
      // Si es "nombre_proyecto", dejamos que siga y también se guarde en inmueble.nombre_proyecto.
    }

    // Mapeo simple: claves de inmueble al bloque inmueble
    if (inmuebleKeys.has(name)) {
      payload.inmueble[name] = value;
      return;
    }

    // Campos económicos que deben quedar en economico (trazabilidad)
    const economicoKeys = new Set([
      "precio_propiedad",
      "precio_escritura",
      "venta_estimada",
      "precio_compra_inmueble",
      "precio_venta_estimado",
      "precio_transmision",
      "valor_adquisicion",
      "valor_adquisicion_total",
      "valor_transmision",
      "beneficio_bruto",
      "beneficio_neto",
      "meses",
      "financiacion_pct",
      "porcentaje_financiacion",
      "notaria",
      "registro",
      "itp",
      "otros_gastos_compra",
      "otros_gastos",
      "reforma",
      "limpieza_inicial",
      "mobiliario",
      "otros_puesta_marcha",
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
      "cerrajero",
      "alarma",
      "comunidad",
      "ibi",
      "seguros",
      "suministros",
      "limpieza_periodica",
      "ocupas",
      "plusvalia",
      "inmobiliaria",
      "gestion_comercial",
      "gestion_administracion",
      "val_idealista",
      "val_fotocasa",
      "val_registradores",
      "val_casafari",
      "val_tasacion",
      "media_valoraciones",
    ]);
    if (economicoKeys.has(name)) {
      payload.economico[name] = value;
      // Alias para financiación
      if (name === "financiacion_pct") {
        payload.economico.porcentaje_financiacion = value;
      }
      if (name === "precio_compra_inmueble") {
        payload.economico.valor_adquisicion = value;
        payload.economico.valor_adquisicion_total = value;
      }
      if (name === "precio_venta_estimado") {
        payload.economico.valor_transmision = value;
      }
      return;
    }

    // Por defecto: lo guardamos como métrica (clave tal cual)
    payload.kpis.metricas[name] = value;
  });

  // --- Derivado (persistencia): Valor de adquisición = precio_escritura + gastos ---
  try {
    const m = payload.kpis && payload.kpis.metricas ? payload.kpis.metricas : {};
    const e = payload.economico || {};

    const precio = Number.isFinite(m.precio_escritura) ? m.precio_escritura : (Number.isFinite(e.precio_propiedad) ? e.precio_propiedad : null);

    const gastoKeys = [
      "itp",
      "notaria",
      "registro",
      "gestoria",
      "tasacion",
      "otros_gastos",
      "otros_gastos_adquisicion",
    ];

    let gastos = 0;
    for (const k of gastoKeys) {
      if (Number.isFinite(m[k])) gastos += m[k];
    }

    if (Number.isFinite(precio)) {
      const valorAdq = precio + gastos;

      // Guardamos con claves compatibles
      m.valor_adquisicion = valorAdq;
      m.valor_adquisicion_total = valorAdq;
      e.valor_adquisicion = valorAdq;
      e.valor_adquisicion_total = valorAdq;

      // Reflejo en DOM si hay hueco
      try {
        window.__setValorAdquisicionDom && window.__setValorAdquisicionDom(valorAdq);
      } catch (e) {}
    }
  } catch (e) {
    // Silencioso
  }

  return payload;
}

function updateComisionInversureMetrics({ beneficioBase = 0, valorAdqBase = 0 } = {}) {
  const pctInput = document.getElementById("inv_comision_pct");
  const eurInput = document.getElementById("inv_comision_eur");
  const netoInput = document.getElementById("inv_beneficio_neto");
  const roiInput = document.getElementById("inv_roi_neto");
  const dashComision = document.getElementById("dash_comision_inversure");
  const dashNeto = document.getElementById("dash_beneficio_neto_inversor");
  const dashRoi = document.getElementById("dash_roi_neto_inversor");

  if (!pctInput || !eurInput || !netoInput || !roiInput) return;

  const pct = parseNumberEs(_getElText(pctInput)) || 0;
  const bruto = Number.isFinite(beneficioBase) ? beneficioBase : 0;
  const comision = bruto > 0 ? (bruto * (pct / 100)) : 0;
  const neto = bruto - comision;
  const roi = valorAdqBase > 0 ? (neto / valorAdqBase) * 100 : 0;

  _setElText(eurInput, formatEuro(comision));
  _setElText(netoInput, formatEuro(neto));
  _setElText(roiInput, formatNumberEs(roi, 2));

  if (dashComision) dashComision.textContent = formatEuro(comision);
  if (dashNeto) dashNeto.textContent = formatEuro(neto);
  if (dashRoi) dashRoi.textContent = formatNumberEs(roi, 2) + " %";
}

function bindComisionInversureInputs() {
  const pctInput = document.getElementById("inv_comision_pct");
  if (!pctInput) return;
  const recalc = () => {
    const base = window.__dashEconomico || {};
    updateComisionInversureMetrics({
      beneficioBase: Number.isFinite(base.beneficioBase) ? base.beneficioBase : 0,
      valorAdqBase: Number.isFinite(base.valorAdqBase) ? base.valorAdqBase : 0,
    });
  };
  pctInput.addEventListener("input", recalc);
  pctInput.addEventListener("blur", recalc);
  recalc();
}

async function postJson(url, data, { keepalive = false } = {}) {
  const csrf = getCsrfToken();
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRFToken": csrf } : {}),
    },
    credentials: "same-origin",
    body: JSON.stringify(data),
    keepalive,
  });
  return resp;
}

async function tryAutosaveOnce(payload, { keepalive = false } = {}) {
  const candidates = __autosaveResolvedUrl ? [__autosaveResolvedUrl] : getSaveUrlCandidates();

  // Envolvemos el payload en {payload: ...} para que el backend pueda extraerlo con seguridad
  const body = { payload };

  let lastErr = null;
  for (const url of candidates) {
    try {
      const resp = await postJson(url, body, { keepalive });
      if (resp && resp.ok) {
        __autosaveResolvedUrl = url;
        try {
          sessionStorage.setItem(AUTOSAVE_STORAGE_KEY, String(Date.now()));
        } catch (e) {}
        return true;
      }
      lastErr = new Error(`Autosave HTTP ${resp ? resp.status : "?"}`);
    } catch (e) {
      lastErr = e;
    }
  }

  // Silencioso para no romper UX
  return false;
}

async function autosaveNow({ keepalive = false } = {}) {
  if (__autosaveInFlight) {
    __autosaveQueued = true;
    return;
  }
  __autosaveInFlight = true;
  __autosaveQueued = false;

  try {
    const payload = buildOverlayPayloadFromDOM();

    // Evitar guardar payload vacío
    const hasSomething = payload && (
      (payload.proyecto && Object.keys(payload.proyecto).length) ||
      (payload.inmueble && Object.keys(payload.inmueble).length) ||
      (payload.economico && Object.keys(payload.economico).length) ||
      (payload.kpis && payload.kpis.metricas && Object.keys(payload.kpis.metricas).length)
    );

    if (hasSomething) {
      // Firma estable del payload para evitar envíos duplicados
      const sig = JSON.stringify(payload);
      if (sig === __autosaveLastPayloadSig) return;
      __autosaveLastPayloadSig = sig;

      const ok = await tryAutosaveOnce(payload, { keepalive });
      // Si falló, permitimos reintento en el siguiente cambio
      if (!ok) {
        __autosaveLastPayloadSig = "";
      }
    }
  } catch (e) {
    // Silencioso
  } finally {
    __autosaveInFlight = false;
    if (__autosaveQueued) {
      // Si hubo cambios mientras guardábamos, guardamos una vez más
      __autosaveQueued = false;
      setTimeout(() => autosaveNow({ keepalive: false }), 0);
    }
  }
}

function scheduleAutosave() {
  try {
    if (__autosaveTimer) clearTimeout(__autosaveTimer);
    __autosaveTimer = setTimeout(() => {
      autosaveNow({ keepalive: false });
    }, AUTOSAVE_DEBOUNCE_MS);
  } catch (e) {}
}

function bindAutosaveListeners() {
  // Evitar dobles bindings (muy típico si el script se carga 2 veces o la vista se re-renderiza)
  if (__autosaveBound) return;
  __autosaveBound = true;

  // Guardar al escribir (inputs/textarea). Incluimos select también por si cambia por teclado.
  document.addEventListener(
    "input",
    (ev) => {
      const t = ev && ev.target;
      if (!t) return;
      if (!(t.matches && t.matches("input[name], textarea[name], select[name]"))) return;
      if (t.disabled) return;
      // Derivado en vivo (Valor de adquisición)
      try {
        window.__recalcValorAdquisicion && window.__recalcValorAdquisicion();
      } catch (e) {}
      scheduleAutosave();
    },
    true
  );

  // Guardar en cambios de SELECT (evita duplicados típicos input+change en inputs numéricos)
  document.addEventListener(
    "change",
    (ev) => {
      const t = ev && ev.target;
      if (!t) return;
      if (!(t.matches && t.matches("select[name]"))) return;
      if (t.disabled) return;
      scheduleAutosave();
    },
    true
  );

  // Guardado final al salir (Safari-friendly)
  window.addEventListener("pagehide", () => {
    autosaveNow({ keepalive: true });
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      autosaveNow({ keepalive: true });
    }
  });
}

// -----------------------------
// Autocálculo (Proyecto) -> Notaría / Registro / ITP
// -----------------------------
function bindAutocalcGastos() {
  const precioInput = document.querySelector("[name='precio_propiedad']");
  const itpInput = document.querySelector("[name='itp']");
  const notariaInput = document.querySelector("[name='notaria']");
  const registroInput = document.querySelector("[name='registro']");

  if (!precioInput || !itpInput || !notariaInput || !registroInput) return;

  const markEdited = (el) => {
    if (!el || !el.dataset) return;
    el.dataset.userEdited = "1";
  };

  const setIfAuto = (el, value) => {
    if (!el) return;
    const edited = el.dataset && el.dataset.userEdited === "1";
    if (edited && _shouldFormatRaw(_getElText(el))) return;
    _setElText(el, formatEuro(value));
  };

  const recalc = () => {
    const precio = parseEuro(_getElText(precioInput));
    if (precio === null) return;

    const itp = precio * 0.02;
    const notaria = Math.max(precio * 0.002, 500);
    const registro = Math.max(precio * 0.002, 500);

    setIfAuto(itpInput, itp);
    setIfAuto(notariaInput, notaria);
    setIfAuto(registroInput, registro);
  };

  // Si el usuario edita manualmente, respetamos.
  [itpInput, notariaInput, registroInput].forEach((el) => {
    el.addEventListener("input", () => markEdited(el));
  });

  // Recalcular cuando cambia el precio
  precioInput.addEventListener("input", recalc);
  precioInput.addEventListener("blur", recalc);

  // Cálculo inicial al cargar si hay precio
  recalc();
}

// -----------------------------
// Autocálculo (Proyecto) -> Media de valoraciones
// -----------------------------
function bindAutocalcValoraciones() {
  const inputs = Array.from(document.querySelectorAll("[data-valuation='true']"));
  const mediaInput = document.querySelector("[name='media_valoraciones']");
  if (!inputs.length || !mediaInput) return;

  const recalc = () => {
    let suma = 0;
    let count = 0;
    inputs.forEach((el) => {
      const v = parseEuro(_getElText(el));
      if (Number.isFinite(v) && v > 0) {
        suma += v;
        count += 1;
      }
    });
    const media = count > 0 ? (suma / count) : null;
    if (media === null) {
      _setElText(mediaInput, "");
      return;
    }
    _setElText(mediaInput, formatEuro(media));
  };

  inputs.forEach((el) => {
    el.addEventListener("input", recalc);
    el.addEventListener("blur", recalc);
  });

  recalc();
}

// -----------------------------
// Autocálculo (Proyecto) -> Valor de transmisión
// -----------------------------
function bindAutocalcValorTransmision() {
  const ventaInput = document.querySelector("[name='venta_estimada']");
  const valorAdqInput = document.querySelector("[name='precio_compra_inmueble']") || document.querySelector("[name='valor_adquisicion']");
  const valorTransInput = document.querySelector("[name='precio_venta_estimado']");
  const valorTransAltInput = document.querySelector("[name='valor_transmision']");
  const plusvaliaInput = document.querySelector("[name='plusvalia']");
  const inmobiliariaInput = document.querySelector("[name='inmobiliaria']");
  const comercialInput = document.querySelector("[name='gestion_comercial']");
  const adminInput = document.querySelector("[name='gestion_administracion']");

  if (!ventaInput || !valorAdqInput || !valorTransInput) return;

  const markEdited = (el) => {
    if (!el || !el.dataset) return;
    el.dataset.userEdited = "1";
  };

  const setIfAuto = (el, value) => {
    if (!el) return;
    const edited = el.dataset && el.dataset.userEdited === "1";
    if (edited && _shouldFormatRaw(_getElText(el))) return;
    _setElText(el, formatEuro(value));
  };

  const recalc = () => {
    const venta = parseEuro(_getElText(ventaInput));
    const valorAdq = parseEuro(_getElText(valorAdqInput));
    if (venta === null || valorAdq === null) return;

    const beneficio = venta - valorAdq;
    const base = Math.max(beneficio, 0);
    const gastoComercial = Math.min(base * 0.05, 2000);
    const gastoAdministracion = Math.min(base * 0.05, 1500);
    const plusvalia = plusvaliaInput ? (parseEuro(_getElText(plusvaliaInput)) || 0) : 0;
    const inmobiliaria = inmobiliariaInput ? (parseEuro(_getElText(inmobiliariaInput)) || 0) : 0;
    const comercial = comercialInput ? (parseEuro(_getElText(comercialInput)) || gastoComercial) : gastoComercial;
    const admin = adminInput ? (parseEuro(_getElText(adminInput)) || gastoAdministracion) : gastoAdministracion;
    const gastosVenta = comercial + admin + plusvalia + inmobiliaria;

    // Valor de transmisión = venta estimada - gastos de venta.
    const valorTrans = venta - gastosVenta;
    setIfAuto(valorTransInput, valorTrans);
    if (valorTransAltInput) setIfAuto(valorTransAltInput, valorTrans);
  };

  valorTransInput.addEventListener("input", () => markEdited(valorTransInput));

  ventaInput.addEventListener("input", recalc);
  ventaInput.addEventListener("blur", recalc);
  [plusvaliaInput, inmobiliariaInput, comercialInput, adminInput].forEach((el) => {
    if (!el) return;
    el.addEventListener("input", recalc);
    el.addEventListener("blur", recalc);
  });
  recalc();
}

// -----------------------------
// Autocálculo (Proyecto) -> Gastos de venta (5% + 5% sobre beneficio)
// -----------------------------
function bindAutocalcGastosVenta() {
  const ventaInput = document.querySelector("[name='venta_estimada']");
  const valorAdqInput = document.querySelector("[name='precio_compra_inmueble']") || document.querySelector("[name='valor_adquisicion']");
  const comercialInput = document.querySelector("[name='gestion_comercial']");
  const adminInput = document.querySelector("[name='gestion_administracion']");
  if (!ventaInput || !valorAdqInput || !comercialInput || !adminInput) return;

  const markEdited = (el) => {
    if (!el || !el.dataset) return;
    el.dataset.userEdited = "1";
  };

  const setIfAuto = (el, value) => {
    if (!el) return;
    const edited = el.dataset && el.dataset.userEdited === "1";
    if (edited && _shouldFormatRaw(_getElText(el))) return;
    _setElText(el, formatEuro(value));
  };

  const recalc = () => {
    const venta = parseEuro(_getElText(ventaInput));
    const valorAdq = parseEuro(_getElText(valorAdqInput));
    if (venta === null || valorAdq === null) return;

    const beneficio = venta - valorAdq;
    const base = Math.max(beneficio, 0);
    const gastoComercial = Math.min(base * 0.05, 2000);
    const gastoAdministracion = Math.min(base * 0.05, 1500);

    setIfAuto(comercialInput, gastoComercial);
    setIfAuto(adminInput, gastoAdministracion);
  };

  [comercialInput, adminInput].forEach((el) => {
    el.addEventListener("input", () => markEdited(el));
  });

  ventaInput.addEventListener("input", recalc);
  ventaInput.addEventListener("blur", recalc);
  recalc();
}

// -----------------------------
// Autocálculo (Proyecto) -> Beneficio bruto / neto
// -----------------------------
function bindAutocalcBeneficios() {
  const ventaInput = document.querySelector("[name='venta_estimada']");
  const valorAdqInput = document.querySelector("[name='precio_compra_inmueble']") || document.querySelector("[name='valor_adquisicion']");
  const valorTransInput = document.querySelector("[name='precio_venta_estimado']");
  const brutoInput = document.querySelector("[name='beneficio_bruto']");
  const netoInput = document.querySelector("[name='beneficio_neto']");

  if (!ventaInput || !valorAdqInput || !brutoInput || !netoInput) return;

  const setOrClear = (el, value) => {
    if (!el) return;
    if (!Number.isFinite(value)) {
      _setElText(el, "");
      return;
    }
    _setElText(el, formatEuro(value));
  };

  const recalc = () => {
    const venta = parseEuro(_getElText(ventaInput));
    const valorAdq = parseEuro(_getElText(valorAdqInput));
    const valorTrans = parseEuro(_getElText(valorTransInput));

    if (venta !== null && valorAdq !== null) {
      setOrClear(brutoInput, venta - valorAdq);
    } else {
      setOrClear(brutoInput, NaN);
    }

    if (valorTrans !== null && valorAdq !== null) {
      setOrClear(netoInput, valorTrans - valorAdq);
    } else {
      setOrClear(netoInput, NaN);
    }
  };

  [ventaInput, valorAdqInput, valorTransInput].forEach((el) => {
    if (!el) return;
    el.addEventListener("input", recalc);
    el.addEventListener("blur", recalc);
  });

  recalc();
}

// -----------------------------
// Memoria económica (Proyecto)
// -----------------------------
function bindMemoriaEconomica() {
  const tabla = document.getElementById("eco_tabla_rows");
  const btnAdd = document.getElementById("eco_add_btn");
  const btnCancel = document.getElementById("eco_cancel_btn");

  if (!tabla || !btnAdd) return;

  const urlGastos = window.PROYECTO_GASTOS_URL || "";
  const urlIngresos = window.PROYECTO_INGRESOS_URL || "";

  const elFecha = document.getElementById("eco_fecha");
  const elTipo = document.getElementById("eco_tipo");
  const elCategoria = document.getElementById("eco_categoria");
  const elTipoIngreso = document.getElementById("eco_tipo_ingreso");
  const elConcepto = document.getElementById("eco_concepto");
  const elImporte = document.getElementById("eco_importe");
  const elEstado = document.getElementById("eco_estado");
  const elImputable = document.getElementById("eco_imputable");
  const elObs = document.getElementById("eco_obs");

  const totalEstimadoEl = document.getElementById("eco_total_estimado");
  const totalRealEl = document.getElementById("eco_total_real");
  const totalIngresosEl = document.getElementById("eco_total_ingresos");
  const totalIngresosEstEl = document.getElementById("eco_total_ingresos_estimado");
  const balanceNetoEl = document.getElementById("eco_balance_neto");

  let rows = [];
  let editState = null;

  function fmtEuroLocal(n) {
    return formatEuro(n);
  }

  function renderTotals() {
    let totalEstimado = 0;
    let totalReal = 0;
    let totalIngresosEstimados = 0;
    let totalIngresosReales = 0;
    let ventaEstimado = 0;
    let ventaReal = 0;
    let gastosAdqEstimado = 0;
    let gastosAdqReal = 0;
    let gastosVentaEstimado = 0;
    let gastosVentaReal = 0;
    let compraEstimada = 0;
    let compraReal = 0;

    const catsAdq = new Set([
      "adquisicion",
      "reforma",
      "seguridad",
      "operativos",
      "financieros",
      "legales",
      "otros",
    ]);

    const normLower = (val) => (val || "").toString().trim().toLowerCase();
    const isCompraRow = (row) => {
      if (row.tipo !== "gasto") return false;
      if (normLower(row.categoria) !== "adquisicion") return false;
      const concepto = (row.concepto || "").toLowerCase();
      const normalized = concepto.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
      return (
        normalized.includes("compraventa") ||
        normalized.includes("compra") ||
        normalized.includes("precio compra") ||
        normalized.includes("precio inmueble") ||
        normalized.includes("propiedad")
      );
    };

    rows.forEach(r => {
      const isCompra = isCompraRow(r);
      const categoria = normLower(r.categoria);
      if (r.tipo === "gasto") {
        if (r.estado === "estimado") totalEstimado += r.importe;
        if (r.estado === "confirmado") totalReal += r.importe;
        if (isCompra) {
          if (r.estado === "estimado") compraEstimada += r.importe;
          if (r.estado === "confirmado") compraReal += r.importe;
          return;
        }
        if (catsAdq.has(categoria)) {
          if (r.estado === "estimado") gastosAdqEstimado += r.importe;
          if (r.estado === "confirmado") gastosAdqReal += r.importe;
        }
        if (categoria === "venta") {
          if (r.estado === "estimado") gastosVentaEstimado += r.importe;
          if (r.estado === "confirmado") gastosVentaReal += r.importe;
        }
      } else if (r.tipo === "ingreso") {
        if (r.estado === "confirmado") totalIngresosReales += r.importe;
        else totalIngresosEstimados += r.importe;
        const ingresoTipo = normLower(r.categoria || r.tipo_ingreso || "");
        if (ingresoTipo === "venta") {
          if (r.estado === "confirmado") ventaReal += r.importe;
          else ventaEstimado += r.importe;
        }
      }
    });

    if (totalEstimadoEl) totalEstimadoEl.textContent = fmtEuroLocal(totalEstimado);
    if (totalRealEl) totalRealEl.textContent = fmtEuroLocal(totalReal);
    if (totalIngresosEl) {
      const shown = totalIngresosReales > 0 ? totalIngresosReales : totalIngresosEstimados;
      totalIngresosEl.textContent = fmtEuroLocal(shown);
    }
    if (totalIngresosEstEl) totalIngresosEstEl.textContent = `Estimado: ${fmtEuroLocal(totalIngresosEstimados)}`;
    if (balanceNetoEl) {
      const hasReal = totalIngresosReales > 0 || totalReal > 0;
      const balance = hasReal
        ? (totalIngresosReales - totalReal)
        : (totalIngresosEstimados - totalEstimado);
      balanceNetoEl.textContent = fmtEuroLocal(balance);
    }

    // Derivados: valores estimados / reales desde memoria económica
    const precioCompraInput = parseEuro(_getElText(document.querySelector("[name='precio_propiedad']"))) ??
      parseEuro(_getElText(document.querySelector("[name='precio_escritura']")));
    const precioCompraBase = (Number.isFinite(precioCompraInput) && precioCompraInput > 0)
      ? precioCompraInput
      : ((compraReal > 0) ? compraReal : compraEstimada);
    const ventaEstimada = parseEuro(_getElText(document.querySelector("[name='venta_estimada']")));

    const valAdqEstimado = totalEstimado;
    const valAdqReal = totalReal;
    const valTransEstimado = totalIngresosEstimados - gastosVentaEstimado;
    const valTransReal = totalIngresosReales - gastosVentaReal;

    const adqEstEl = document.getElementById("valor_adq_estimado");
    const adqRealEl = document.getElementById("valor_adq_real");
    const transEstEl = document.getElementById("valor_trans_estimado");
    const transRealEl = document.getElementById("valor_trans_real");
    if (adqEstEl) adqEstEl.textContent = fmtEuroLocal(valAdqEstimado);
    if (adqRealEl) adqRealEl.textContent = fmtEuroLocal(valAdqReal);
    if (transEstEl) transEstEl.textContent = fmtEuroLocal(valTransEstimado);
    if (transRealEl) transRealEl.textContent = fmtEuroLocal(valTransReal);

    // Actualizar inputs principales: preferimos real si existe (gastos reales > 0)
    const valAdqInput = document.querySelector("[name='precio_compra_inmueble']");
    const valTransInput = document.querySelector("[name='precio_venta_estimado']");
    const valTransInputAlt = document.querySelector("[name='valor_transmision']");
    if (valAdqInput) {
      const chosen = gastosAdqReal > 0 ? valAdqReal : valAdqEstimado;
      _setElText(valAdqInput, formatEuro(chosen));
    }
    if (valTransInput) {
      const chosen = gastosVentaReal > 0 ? valTransReal : valTransEstimado;
      _setElText(valTransInput, formatEuro(chosen));
    }
    if (valTransInputAlt) {
      const chosen = gastosVentaReal > 0 ? valTransReal : valTransEstimado;
      _setElText(valTransInputAlt, formatEuro(chosen));
    }

    // Dashboard
    const getProyectoEstado = () => {
      const el = document.getElementById("estado_proyecto");
      return (el && _getElText(el)) ? String(_getElText(el)).toLowerCase() : "";
    };
    const estadoProyecto = getProyectoEstado();
    const usarEstimados = ["estudio", "captacion"].includes(estadoProyecto);
    const dashIngresosEstimados = usarEstimados ? (totalIngresosEstimados + totalIngresosReales) : totalIngresosEstimados;
    const dashIngresosReales = usarEstimados ? 0 : totalIngresosReales;
    const dashGastosEstimados = usarEstimados ? (totalEstimado + totalReal) : totalEstimado;
    const dashGastosReales = usarEstimados ? 0 : totalReal;
    const dashGastosAdqEstimado = usarEstimados ? (gastosAdqEstimado + gastosAdqReal) : gastosAdqEstimado;
    const dashGastosAdqReal = usarEstimados ? 0 : gastosAdqReal;
    const dashGastosVentaEstimado = usarEstimados ? (gastosVentaEstimado + gastosVentaReal) : gastosVentaEstimado;
    const dashGastosVentaReal = usarEstimados ? 0 : gastosVentaReal;
    const dashVentaEstimado = usarEstimados ? (ventaEstimado + ventaReal) : ventaEstimado;
    const dashVentaReal = usarEstimados ? 0 : ventaReal;
    const ingresosBaseDash = usarEstimados ? dashIngresosEstimados : totalIngresosReales;
    const gastosBaseDash = usarEstimados ? dashGastosEstimados : totalReal;

    const dash = {
      ingresosEstimados: dashIngresosEstimados,
      ingresosReales: dashIngresosReales,
      gastosEstimados: dashGastosEstimados,
      gastosReales: dashGastosReales,
      beneficioEstimado: dashIngresosEstimados - dashGastosEstimados,
      beneficioReal: dashIngresosReales - dashGastosReales,
      roiEstimado: null,
      roiReal: null,
    };

    const baseEst = usarEstimados
      ? (dashGastosEstimados || 0)
      : (valAdqEstimado || 0);
    const baseReal = valAdqReal || 0;
    dash.roiEstimado = baseEst > 0 ? (dash.beneficioEstimado / baseEst) * 100 : null;
    dash.roiReal = usarEstimados ? null : (baseReal > 0 ? (dash.beneficioReal / baseReal) * 100 : null);

    const beneficioRealRaw = totalIngresosReales - totalReal;
    const roiRealRaw = baseReal > 0 ? (beneficioRealRaw / baseReal) * 100 : null;

    const labelIngresos = document.getElementById("dash_label_ingresos");
    const labelGastos = document.getElementById("dash_label_gastos");
    const labelBeneficio = document.getElementById("dash_label_beneficio");
    const labelRoi = document.getElementById("dash_label_roi");
    const subIngresosLabel = document.getElementById("dash_sub_ingresos_label");
    const subGastosLabel = document.getElementById("dash_sub_gastos_label");
    const subBeneficioLabel = document.getElementById("dash_sub_beneficio_label");
    const subRoiLabel = document.getElementById("dash_sub_roi_label");
    if (labelIngresos) labelIngresos.textContent = usarEstimados ? "Ingresos estimados" : "Ingresos reales";
    if (labelGastos) labelGastos.textContent = usarEstimados ? "Gastos estimados" : "Gastos reales";
    if (labelBeneficio) labelBeneficio.textContent = usarEstimados ? "Beneficio neto estimado" : "Beneficio neto real";
    if (labelRoi) labelRoi.textContent = usarEstimados ? "ROI estimado" : "ROI real";
    if (subIngresosLabel) subIngresosLabel.textContent = usarEstimados ? "Real:" : "Estimado:";
    if (subGastosLabel) subGastosLabel.textContent = usarEstimados ? "Real:" : "Estimado:";
    if (subBeneficioLabel) subBeneficioLabel.textContent = usarEstimados ? "Real:" : "Estimado:";
    if (subRoiLabel) subRoiLabel.textContent = usarEstimados ? "Real:" : "Estimado:";

    const display = {
      ingresosMain: usarEstimados ? dash.ingresosEstimados : dash.ingresosReales,
      ingresosSub: usarEstimados ? totalIngresosReales : totalIngresosEstimados,
      gastosMain: usarEstimados ? dash.gastosEstimados : dash.gastosReales,
      gastosSub: usarEstimados ? totalReal : totalEstimado,
      beneficioMain: usarEstimados ? dash.beneficioEstimado : dash.beneficioReal,
      beneficioSub: usarEstimados ? beneficioRealRaw : dash.beneficioEstimado,
      roiMain: usarEstimados ? dash.roiEstimado : dash.roiReal,
      roiSub: usarEstimados ? roiRealRaw : dash.roiEstimado,
    };

    const setDash = (id, value, isPct = false) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (value === null || typeof value === "undefined" || Number.isNaN(value)) {
        el.textContent = "—";
        return;
      }
      el.textContent = isPct ? (formatNumberEs(value, 2) + " %") : fmtEuroLocal(value);
    };

    setDash("dash_ingresos_reales", display.ingresosMain);
    setDash("dash_ingresos_estimados", display.ingresosSub);
    setDash("dash_gastos_reales", display.gastosMain);
    setDash("dash_gastos_estimados", display.gastosSub);
    setDash("dash_beneficio_real", display.beneficioMain);
    setDash("dash_beneficio_estimado", display.beneficioSub);
    setDash("dash_roi_real", display.roiMain, true);
    setDash("dash_roi_estimado", display.roiSub, true);

    updateDashboardVisuals({
      ingresosReales: dash.ingresosReales,
      gastosReales: dash.gastosReales,
      beneficioReal: dash.beneficioReal,
      ingresosEstimados: dash.ingresosEstimados,
      gastosEstimados: dash.gastosEstimados,
      ingresosBase: ingresosBaseDash,
      gastosBase: gastosBaseDash,
      beneficioBase: ingresosBaseDash - gastosBaseDash,
      rows,
    });

    updateInvestmentAnalysis({
      ingresosEstimados: dash.ingresosEstimados,
      ingresosReales: dash.ingresosReales,
      gastosEstimados: dash.gastosEstimados,
      gastosReales: dash.gastosReales,
      gastosAdqEstimado: dashGastosAdqEstimado,
      gastosAdqReal: dashGastosAdqReal,
      gastosVentaEstimado: dashGastosVentaEstimado,
      gastosVentaReal: dashGastosVentaReal,
      ventaEstimado: dashVentaEstimado,
      ventaReal: dashVentaReal,
    });

    const objetivoCaptacion = calcCaptacionObjectiveFromInputs();
    window.__captacionObjetivo = Number.isFinite(objetivoCaptacion) ? objetivoCaptacion : 0;
    updateCaptacionDashboard({
      capitalObjetivo: window.__captacionObjetivo,
      capitalCaptado: Number.isFinite(window.__captacionCaptado) ? window.__captacionCaptado : 0,
    });

    const beneficioBase = ingresosBaseDash - gastosBaseDash;
    const valorAdqBase = usarEstimados
      ? (dashGastosEstimados || 0)
      : (valAdqReal > 0 ? valAdqReal : valAdqEstimado);
    window.__dashEconomico = { beneficioBase, valorAdqBase };
    updateComisionInversureMetrics({
      beneficioBase,
      valorAdqBase,
    });
  }

  function updateInvestmentAnalysis(data) {
    const card = document.getElementById("resultado_card");
    const roiEl = document.getElementById("resultado_roi");
    const roiKpiEl = document.getElementById("resultado_roi_kpi");
    const beneficioEl = document.getElementById("resultado_beneficio");
    const beneficioKpiEl = document.getElementById("resultado_beneficio_kpi");
    const valorAdqEl = document.getElementById("resultado_valor_adquisicion");
    const ratioEl = document.getElementById("resultado_ratio_euro");
    const minVentaEl = document.getElementById("resultado_precio_minimo_venta");
    const colchonEl = document.getElementById("resultado_colchon_seguridad");
    const margenEl = document.getElementById("resultado_margen_neto");
    const ajusteVentaEl = document.getElementById("resultado_ajuste_precio_venta");
    const ajusteGastosEl = document.getElementById("resultado_ajuste_gastos");
    const veredictoEl = document.getElementById("resultado_veredicto");
    const decisionEl = document.getElementById("resultado_decision");
    const roiWrap = document.getElementById("resultado_roi_wrap");
    const beneficioWrap = document.getElementById("resultado_beneficio_wrap");

    if (!card) return;

    const ingresosBase = data.ingresosReales > 0 ? data.ingresosReales : data.ingresosEstimados;
    const gastosBase = data.gastosReales > 0 ? data.gastosReales : data.gastosEstimados;
    const beneficio = ingresosBase - gastosBase;

    const gastosAdqBase = data.gastosAdqReal > 0 ? data.gastosAdqReal : data.gastosAdqEstimado;
    const basePrecio =
      parseEuro(_getElText(document.querySelector("[name='precio_propiedad']"))) ??
      parseEuro(_getElText(document.querySelector("[name='precio_escritura']"))) ??
      parseEuro(_getElText(document.querySelector("[name='precio_compra_inmueble']"))) ??
      0;
    const valorAdq = (basePrecio || 0) + (gastosAdqBase || 0);

    const ventaBaseMem = data.ventaReal > 0 ? data.ventaReal : data.ventaEstimado;
    const gastosVentaBase = data.gastosVentaReal > 0 ? data.gastosVentaReal : data.gastosVentaEstimado;
    const ventaInput =
      parseEuro(_getElText(document.querySelector("[name='venta_estimada']"))) ??
      parseEuro(_getElText(document.querySelector("[name='valor_transmision']"))) ??
      parseEuro(_getElText(document.querySelector("[name='precio_venta_estimado']"))) ??
      0;
    const ventaBruta = ventaBaseMem > 0 ? ventaBaseMem : (ventaInput || 0);
    const valorTrans = ventaBruta > 0 ? (ventaBruta - (gastosVentaBase || 0)) : 0;

    const beneficioBruto = valorTrans - valorAdq;
    const roi = valorAdq > 0 ? (beneficioBruto / valorAdq) * 100 : 0;
    const ratio = valorAdq > 0 ? (beneficioBruto / valorAdq) : 0;
    const margen = valorTrans > 0 ? (beneficioBruto / valorTrans) * 100 : 0;

    const beneficioObj = 30000;
    const objetivoRoi = valorAdq * 0.15;
    const objetivoBenef = Math.max(beneficioObj, objetivoRoi);
    const minValorTrans = valorAdq + objetivoBenef;
    const minVenta = minValorTrans + (gastosVentaBase || 0);
    const ajusteVenta = valorTrans > 0 ? Math.max(minValorTrans - valorTrans, 0) : minValorTrans;

    const costoReqRoi = valorTrans > 0 ? (valorTrans / 1.15) : 0;
    const costoReqBenef = valorTrans > 0 ? (valorTrans - beneficioObj) : 0;
    const costoReq = Math.min(costoReqRoi, costoReqBenef);
    const ajusteGastos = valorTrans > 0 ? Math.max(valorAdq - Math.max(costoReq, 0), 0) : valorAdq;

    const colchon = valorTrans > 0 ? (valorTrans - valorAdq - objetivoBenef) : 0;

    const viable = roi >= 15 && beneficio >= 30000;
    const ajustada = roi >= 15 && beneficio > 0 && beneficio < 30000;

    const setText = (el, value) => { if (el) el.textContent = value; };
    setText(roiEl, formatNumberEs(roi, 2) + " %");
    setText(roiKpiEl, formatNumberEs(roi, 2) + " %");
    setText(beneficioEl, formatEuro(beneficio));
    setText(beneficioKpiEl, formatEuro(beneficio));
    setText(valorAdqEl, formatEuro(valorAdq));
    setText(ratioEl, formatNumberEs(ratio, 2));
    setText(minVentaEl, formatEuro(minVenta));
    setText(colchonEl, formatEuro(colchon));
    setText(margenEl, formatNumberEs(margen, 2) + " %");
    if (ajusteVentaEl) ajusteVentaEl.textContent = formatEuro(ajusteVenta);
    if (ajusteGastosEl) ajusteGastosEl.textContent = formatEuro(ajusteGastos);

    if (roiWrap) {
      roiWrap.classList.remove("text-success", "text-warning", "text-danger");
      roiWrap.classList.add(viable ? "text-success" : (ajustada ? "text-warning" : "text-danger"));
    }
    if (beneficioWrap) {
      beneficioWrap.classList.remove("text-success", "text-warning", "text-danger");
      beneficioWrap.classList.add(beneficio >= 30000 ? "text-success" : (beneficio > 0 ? "text-warning" : "text-danger"));
    }
    if (card) {
      card.classList.remove("resultado-viable", "resultado-ajustada", "resultado-no-viable");
      card.classList.add(viable ? "resultado-viable" : (ajustada ? "resultado-ajustada" : "resultado-no-viable"));
    }
    if (veredictoEl) {
      veredictoEl.classList.remove("text-success", "text-warning", "text-danger");
      if (viable) {
        veredictoEl.classList.add("text-success");
        veredictoEl.textContent = "✔ OPERACIÓN VIABLE";
      } else if (ajustada) {
        veredictoEl.classList.add("text-warning");
        veredictoEl.textContent = "⚠ OPERACIÓN AJUSTADA";
      } else {
        veredictoEl.classList.add("text-danger");
        veredictoEl.textContent = "✖ OPERACIÓN NO VIABLE";
      }
    }
    if (decisionEl) {
      decisionEl.textContent = viable ? "✅ Apta para inversión" : (ajustada ? "⚠ Requiere ajuste" : "❌ No invertir");
    }
  }

  function updateDashboardVisuals(data) {
    const barIngresos = document.querySelector("#dash_bar_ingresos span");
    const barGastos = document.querySelector("#dash_bar_gastos span");
    const barBalance = document.querySelector("#dash_bar_balance span");
    const catRows = document.getElementById("dash_categorias_rows");
    const ultimos = document.getElementById("dash_ultimos_movimientos");
    if (!barIngresos || !barGastos || !barBalance || !catRows || !ultimos) return;

    const ingresosBase = Number.isFinite(data.ingresosBase)
      ? data.ingresosBase
      : ((data.ingresosReales || 0) > 0 ? data.ingresosReales : (data.ingresosEstimados || 0));
    const gastosBase = Number.isFinite(data.gastosBase)
      ? data.gastosBase
      : ((data.gastosReales || 0) > 0 ? data.gastosReales : (data.gastosEstimados || 0));
    const maxBase = Math.max(ingresosBase || 0, gastosBase || 0, 1);
    barIngresos.style.width = `${Math.min(100, (ingresosBase / maxBase) * 100)}%`;
    barGastos.style.width = `${Math.min(100, (gastosBase / maxBase) * 100)}%`;

    const beneficioBase = Number.isFinite(data.beneficioBase)
      ? data.beneficioBase
      : ((data.beneficioReal || 0) !== 0 ? data.beneficioReal : (data.ingresosEstimados - data.gastosEstimados));
    const balanceAbs = Math.abs(beneficioBase || 0);
    const balBase = Math.max(balanceAbs, 1);
    barBalance.style.width = `${Math.min(100, (balanceAbs / balBase) * 100)}%`;
    barBalance.parentElement.classList.toggle("good", (beneficioBase || 0) >= 0);
    barBalance.parentElement.classList.toggle("warn", (beneficioBase || 0) < 0);

    const catLabels = {
      adquisicion: "Adquisición",
      reforma: "Reforma",
      seguridad: "Seguridad",
      operativos: "Operativos",
      financieros: "Financieros",
      legales: "Legales",
      venta: "Venta",
      otros: "Otros",
    };
    const totals = {};
    data.rows.forEach(r => {
      if (r.tipo !== "gasto") return;
      const key = normLower(r.categoria) || "otros";
      if (!totals[key]) totals[key] = { real: 0, estimado: 0 };
      if (r.estado === "confirmado") totals[key].real += r.importe;
      else totals[key].estimado += r.importe;
    });

    const totalCats = Object.values(totals).reduce((acc, v) => {
      return acc + (v.real > 0 ? v.real : v.estimado);
    }, 0);

    const catHtml = Object.keys(catLabels).map(key => {
      const t = totals[key] || { real: 0, estimado: 0 };
      const value = t.real > 0 ? t.real : t.estimado;
      if (value <= 0) return "";
      const pct = totalCats > 0 ? Math.round((value / totalCats) * 100) : 0;
      return `
        <div class="mb-2">
          <div class="d-flex justify-content-between small text-muted">
            <span>${catLabels[key]}</span>
            <span>${formatEuro(value)}</span>
          </div>
          <div class="dash-bar"><span style="width:${pct}%;"></span></div>
        </div>
      `;
    }).join("");

    catRows.innerHTML = catHtml || "<div class=\"small text-muted\">Sin gastos registrados.</div>";

    const sorted = [...data.rows].sort((a, b) => {
      const da = new Date(a.fecha || "1970-01-01").getTime();
      const db = new Date(b.fecha || "1970-01-01").getTime();
      return db - da;
    }).slice(0, 6);

    if (!sorted.length) {
      ultimos.innerHTML = "<li><span class=\"text-muted\">Sin movimientos aún.</span><span></span></li>";
      return;
    }

    const formatDate = (iso) => {
      if (!iso) return "";
      const [y, m, d] = iso.split("-");
      return d && m && y ? `${d}/${m}/${y}` : iso;
    };

    ultimos.innerHTML = sorted.map(r => {
      const tipo = r.tipo === "gasto" ? "Gasto" : "Ingreso";
      const estado = r.estado === "confirmado" ? "Real" : "Estimado";
      const label = `${tipo} · ${r.concepto || (r.categoria || "")}`;
      return `
        <li>
          <span>${formatDate(r.fecha)} · ${label}</span>
          <span>${formatEuro(r.importe)} <span class="dash-pill">${estado}</span></span>
        </li>
      `;
    }).join("");
  }

  function updateCaptacionDashboard(data) {
    const captadoEl = document.getElementById("dash_captado_val");
    const objetivoEl = document.getElementById("dash_captado_obj");
    const captadoPctEl = document.getElementById("dash_captado_pct");
    const captadoBar = document.getElementById("dash_captado_bar");
    const restanteEl = document.getElementById("dash_restante_val");
    const restantePctEl = document.getElementById("dash_restante_pct");
    const restanteBar = document.getElementById("dash_restante_bar");

    if (!captadoEl || !objetivoEl || !captadoPctEl || !captadoBar || !restanteEl || !restantePctEl || !restanteBar) {
      return;
    }

    const capitalObjetivo = Number.isFinite(data.capitalObjetivo) ? data.capitalObjetivo : 0;
    const capitalCaptado = Number.isFinite(data.capitalCaptado) ? data.capitalCaptado : 0;
    const pctCaptado = capitalObjetivo > 0 ? Math.min(100, Math.max(0, (capitalCaptado / capitalObjetivo) * 100)) : 0;
    const restante = Math.max(capitalObjetivo - capitalCaptado, 0);
    const pctRestante = Math.max(0, 100 - pctCaptado);

    captadoEl.textContent = formatEuro(capitalCaptado);
    objetivoEl.textContent = formatEuro(capitalObjetivo);
    captadoPctEl.textContent = formatNumberEs(pctCaptado, 0) + " %";
    captadoBar.style.width = `${Math.round(pctCaptado)}%`;

    restanteEl.textContent = formatEuro(restante);
    restantePctEl.textContent = formatNumberEs(pctRestante, 0) + " %";
    restanteBar.style.width = `${Math.round(pctRestante)}%`;
  }

  window.__updateCaptacionDashboard = updateCaptacionDashboard;

  function renderTable() {
    if (!tabla) return;
    if (!rows.length) {
      tabla.innerHTML = "<tr><td colspan=\"7\" class=\"text-muted\">Sin asientos todavía.</td></tr>";
      renderTotals();
      return;
    }

    const _capFirst = (s) => {
      const t = String(s || "").toLowerCase();
      return t ? (t.charAt(0).toUpperCase() + t.slice(1)) : "";
    };
    const ingresoLabels = {
      senal: "Señal / Arras",
      venta: "Venta",
      anticipo: "Anticipo",
      devolucion: "Devolución",
      indemnizacion: "Indemnización",
      otro: "Otro ingreso",
    };

    tabla.innerHTML = rows.map(r => {
      const catLabel = (r.tipo === "ingreso")
        ? (ingresoLabels[r.categoria] || ingresoLabels[r.tipo_ingreso] || r.categoria || "")
        : (r.categoria || "");
      return `
        <tr data-id="${r.id}" data-tipo="${r.tipo}">
          <td>${r.fecha || ""}</td>
          <td>${_capFirst(r.tipo)}</td>
          <td>${r.tipo === "ingreso" ? catLabel : _capFirst(catLabel)}</td>
          <td>${r.concepto || ""}</td>
          <td class="text-end">${fmtEuroLocal(r.importe)}</td>
          <td>${r.estado ? _capFirst(r.estado) : "-"}</td>
          <td class="text-end">
            <button type="button" class="btn btn-sm btn-outline-secondary eco-edit">Editar</button>
            <button type="button" class="btn btn-sm btn-outline-danger eco-del">Borrar</button>
          </td>
        </tr>
      `;
    }).join("");
    renderTotals();
  }

  async function loadRows() {
    rows = [];
    try {
      if (urlGastos) {
        const rg = await fetch(urlGastos, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        const dg = await rg.json();
        if (dg && dg.ok && Array.isArray(dg.gastos)) {
          dg.gastos.forEach(g => {
            rows.push({
              id: g.id,
              tipo: "gasto",
              fecha: g.fecha,
              categoria: g.categoria,
              concepto: g.concepto,
              importe: Number(g.importe) || 0,
              estado: g.estado,
              imputable_inversores: g.imputable_inversores,
              observaciones: g.observaciones,
            });
          });
        }
      }

      if (urlIngresos) {
        const ri = await fetch(urlIngresos, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        const di = await ri.json();
        if (di && di.ok && Array.isArray(di.ingresos)) {
          di.ingresos.forEach(i => {
            rows.push({
              id: i.id,
              tipo: "ingreso",
              fecha: i.fecha,
              categoria: i.tipo,
              tipo_ingreso: i.tipo,
              concepto: i.concepto,
              importe: Number(i.importe) || 0,
              estado: i.estado || "estimado",
              imputable_inversores: i.imputable_inversores,
              observaciones: i.observaciones,
            });
          });
        }
      }
    } catch (e) {}
    renderTable();
  }

  const dashRecalcInputs = [
    "[name='precio_propiedad']",
    "[name='precio_escritura']",
    "[name='precio_compra_inmueble']",
    "[name='venta_estimada']",
    "[name='valor_transmision']",
    "[name='precio_venta_estimado']",
    "[name='financiacion_pct']",
    "[name='porcentaje_financiacion']",
  ];
  dashRecalcInputs.forEach((sel) => {
    const el = document.querySelector(sel);
    if (!el) return;
    el.addEventListener("input", renderTotals);
    el.addEventListener("blur", renderTotals);
  });

  const comisionInput = document.getElementById("inv_comision_pct");
  if (comisionInput) {
    comisionInput.addEventListener("input", () => renderTotals());
    comisionInput.addEventListener("blur", () => renderTotals());
  }

  const estadoProyecto = document.getElementById("estado_proyecto");
  if (estadoProyecto) {
    estadoProyecto.addEventListener("change", () => renderTotals());
  }
  window.__captacionObjetivo = calcCaptacionObjectiveFromInputs();
  if (typeof window.__updateCaptacionDashboard === "function") {
    window.__updateCaptacionDashboard({
      capitalObjetivo: window.__captacionObjetivo,
      capitalCaptado: Number.isFinite(window.__captacionCaptado) ? window.__captacionCaptado : 0,
    });
  }

  function clearForm() {
    if (elFecha) elFecha.value = "";
    if (elConcepto) elConcepto.value = "";
    if (elImporte) elImporte.value = "";
    if (elObs) elObs.value = "";
    if (elTipo) elTipo.value = "gasto";
    if (elCategoria) elCategoria.value = "adquisicion";
    if (elTipoIngreso) elTipoIngreso.value = "venta";
    if (elEstado) elEstado.value = "estimado";
    if (elImputable) elImputable.value = "1";
    if (btnAdd) btnAdd.textContent = "Añadir";
    if (btnCancel) btnCancel.classList.add("d-none");
    editState = null;
  }

  async function addRow() {
    if (!elFecha || !elTipo || !elConcepto || !elImporte) return;

    let fecha = elFecha.value;
    const tipo = elTipo.value || "gasto";
    const concepto = elConcepto.value.trim();
    const importe = parseEuro(_getElText(elImporte));

    if (!fecha) {
      const hoy = new Date();
      const iso = hoy.toISOString().slice(0, 10);
      fecha = iso;
      elFecha.value = iso;
    }

    if (!concepto || importe === null) {
      alert("Fecha, concepto e importe son obligatorios.");
      return;
    }

    const payload = {
      fecha,
      concepto,
      importe,
    };

    if (tipo === "gasto") {
      payload.categoria = (elCategoria && elCategoria.value) || "otros";
      payload.estado = (elEstado && elEstado.value) || "estimado";
      payload.imputable_inversores = (elImputable && elImputable.value === "1");
      payload.observaciones = (elObs && elObs.value) || "";
    } else {
      payload.tipo = (elTipoIngreso && elTipoIngreso.value) || "venta";
      payload.estado = (elEstado && elEstado.value) || "estimado";
      payload.imputable_inversores = (elImputable && elImputable.value === "1");
      payload.observaciones = (elObs && elObs.value) || "";
    }

    const url = (tipo === "gasto") ? urlGastos : urlIngresos;
    if (!url) return;

    let resp;
    if (editState && editState.id && editState.tipo === tipo) {
      const targetUrl = (tipo === "gasto") ? `${urlGastos}${editState.id}/` : `${urlIngresos}${editState.id}/`;
      resp = await fetch(targetUrl, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(getCsrfToken() ? { "X-CSRFToken": getCsrfToken() } : {}),
        },
        body: JSON.stringify(payload),
      });
    } else {
      resp = await postJson(url, payload, { keepalive: false });
    }
    if (!resp.ok) {
      alert("No se pudo guardar el asiento.");
      return;
    }
    clearForm();
    await loadRows();
  }

  async function deleteRow(tr) {
    if (!tr) return;
    const id = tr.getAttribute("data-id");
    const tipo = tr.getAttribute("data-tipo");
    if (!id || !tipo) return;
    if (!confirm("¿Borrar asiento?")) return;

    const url = (tipo === "gasto") ? `${urlGastos}${id}/` : `${urlIngresos}${id}/`;
    const csrf = getCsrfToken();
    const resp = await fetch(url, { method: "DELETE", headers: { ...(csrf ? { "X-CSRFToken": csrf } : {}) } });
    if (!resp.ok) {
      alert("No se pudo borrar el asiento.");
      return;
    }
    await loadRows();
  }

  function editRow(tr) {
    const id = tr.getAttribute("data-id");
    const tipo = tr.getAttribute("data-tipo");
    if (!id || !tipo) return;
    const row = rows.find(r => String(r.id) === String(id) && r.tipo === tipo);
    if (!row) return;

    if (elFecha) elFecha.value = row.fecha || "";
    if (elTipo) elTipo.value = tipo;
    if (elCategoria && tipo === "gasto") elCategoria.value = row.categoria || "otros";
    if (elTipoIngreso && tipo === "ingreso") elTipoIngreso.value = row.tipo_ingreso || row.categoria || "venta";
    if (elConcepto) elConcepto.value = row.concepto || "";
    if (elImporte) _setElText(elImporte, formatEuro(row.importe || 0));
    if (elEstado) elEstado.value = row.estado || "estimado";
    if (elImputable) elImputable.value = row.imputable_inversores ? "1" : "0";
    if (elObs) elObs.value = row.observaciones || "";

    editState = { id, tipo };
    if (btnAdd) btnAdd.textContent = "Guardar";
    if (btnCancel) btnCancel.classList.remove("d-none");
  }

  function toggleTipoFields() {
    const isIngreso = elTipo && elTipo.value === "ingreso";
    document.querySelectorAll(".eco-only-gasto").forEach(el => {
      el.classList.toggle("d-none", isIngreso);
    });
    document.querySelectorAll(".eco-only-ingreso").forEach(el => {
      el.classList.toggle("d-none", !isIngreso);
    });
  }

  btnAdd.addEventListener("click", addRow);
  if (btnCancel) btnCancel.addEventListener("click", () => clearForm());
  if (elTipo) elTipo.addEventListener("change", toggleTipoFields);
  tabla.addEventListener("click", (e) => {
    const btn = e.target.closest(".eco-del");
    const btnEdit = e.target.closest(".eco-edit");
    if (btnEdit) {
      const tr = btnEdit.closest("tr");
      editRow(tr);
      return;
    }
    if (!btn) return;
    const tr = btn.closest("tr");
    deleteRow(tr);
  });

  // Recalcular si cambia compra/venta base
  ["precio_propiedad", "precio_escritura", "venta_estimada"].forEach((name) => {
    const el = document.querySelector(`[name='${name}']`);
    if (!el) return;
    el.addEventListener("input", renderTotals);
    el.addEventListener("blur", renderTotals);
  });

  // Fecha por defecto: hoy
  if (elFecha && !elFecha.value) {
    const hoy = new Date().toISOString().slice(0, 10);
    elFecha.value = hoy;
  }

  toggleTipoFields();
  loadRows();
}

// -----------------------------
// Checklist operativo
// -----------------------------
function bindChecklistOperativo() {
  const tabla = document.getElementById("chk_tabla_rows");
  if (!tabla) return;

  const urlChecklist = window.PROYECTO_CHECKLIST_URL || "";
  if (!urlChecklist) return;

  const faseLabel = {
    compra: "Compra",
    post_compra: "Post-compra",
    operacion: "Operación",
    venta: "Venta",
    post_venta: "Post-venta",
  };

  let rows = [];

  function renderTable() {
    if (!rows.length) {
      tabla.innerHTML = "<tr><td colspan=\"6\" class=\"text-muted\">Sin tareas todavía.</td></tr>";
      return;
    }
    tabla.innerHTML = rows.map(r => {
      const estadoOptions = ["pendiente", "en_curso", "hecho"].map(v => {
        const selected = r.estado === v ? "selected" : "";
        const label = v === "pendiente" ? "Pendiente" : (v === "en_curso" ? "En curso" : "Hecho");
        return `<option value="${v}" ${selected}>${label}</option>`;
      }).join("");
      const fechaVal = r.fecha_objetivo || "";
      return `
        <tr data-id="${r.id}">
          <td>${faseLabel[r.fase] || r.fase || ""}</td>
          <td>${r.titulo || ""}</td>
          <td><input type="text" class="form-control form-control-sm chk-resp" value="${r.responsable || ""}"></td>
          <td><input type="date" class="form-control form-control-sm chk-fecha" value="${fechaVal}"></td>
          <td>
            <select class="form-select form-select-sm chk-estado">
              ${estadoOptions}
            </select>
          </td>
          <td class="text-end">
            <button type="button" class="btn btn-sm btn-outline-secondary chk-save">Guardar</button>
          </td>
        </tr>
      `;
    }).join("");
  }

  async function loadRows() {
    try {
      const resp = await fetch(urlChecklist, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      const data = await resp.json();
      if (data && data.ok && Array.isArray(data.items)) {
        rows = data.items;
      } else {
        return;
      }
    } catch (e) {
      return;
    }
    renderTable();
    updateChecklistDashboard(rows);
  }

  tabla.addEventListener("click", async (e) => {
    const btn = e.target.closest(".chk-save");
    if (!btn) return;
    const tr = btn.closest("tr");
    const id = tr.getAttribute("data-id");
    if (!id) return;
    const respInput = tr.querySelector(".chk-resp");
    const fechaInput = tr.querySelector(".chk-fecha");
    const estadoInput = tr.querySelector(".chk-estado");
    const todayIso = new Date().toISOString().slice(0, 10);
    if (estadoInput && estadoInput.value === "hecho" && fechaInput && !fechaInput.value) {
      fechaInput.value = todayIso;
    }
    const payload = {
      responsable: respInput ? respInput.value : "",
      fecha_objetivo: fechaInput ? fechaInput.value : "",
      estado: estadoInput ? estadoInput.value : "pendiente",
    };
    const resp = await fetch(`${urlChecklist}${id}/`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...(getCsrfToken() ? { "X-CSRFToken": getCsrfToken() } : {}),
      },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      alert("No se pudo guardar la tarea.");
      return;
    }
    await loadRows();
  });

  loadRows();
}

function updateChecklistDashboard(rows) {
  const wrap = document.getElementById("dash_checklist_rows");
  if (!wrap) return;
  if (!Array.isArray(rows) || !rows.length) {
    wrap.innerHTML = "<div class=\"small text-muted\">Sin tareas todavía.</div>";
    return;
  }

  const fases = [
    { key: "compra", label: "Compra" },
    { key: "post_compra", label: "Post-compra" },
    { key: "operacion", label: "Operación" },
    { key: "venta", label: "Venta" },
    { key: "post_venta", label: "Post-venta" },
  ];

  const itemsByFase = {};
  fases.forEach(f => { itemsByFase[f.key] = { total: 0, done: 0 }; });
  rows.forEach(r => {
    const key = r.fase || "compra";
    if (!itemsByFase[key]) itemsByFase[key] = { total: 0, done: 0 };
    itemsByFase[key].total += 1;
    if (r.estado === "hecho") itemsByFase[key].done += 1;
  });

  wrap.innerHTML = fases.map(f => {
    const data = itemsByFase[f.key] || { total: 0, done: 0 };
    const pct = data.total > 0 ? Math.round((data.done / data.total) * 100) : 0;
    return `
      <div class="mb-2">
        <div class="d-flex justify-content-between small text-muted">
          <span>${f.label}</span>
          <span>${data.done}/${data.total} · ${pct}%</span>
        </div>
        <div class="dash-bar"><span style="width:${pct}%;"></span></div>
      </div>
    `;
  }).join("");
}

// -----------------------------
// Participaciones (Inversores)
// -----------------------------
function bindParticipaciones() {
  const tabla = document.getElementById("inv_tabla_rows");
  const btnAdd = document.getElementById("inv_add_btn");
  const elCliente = document.getElementById("inv_cliente");
  const elImporte = document.getElementById("inv_importe");
  const url = window.PROYECTO_PARTICIPACIONES_URL || "";
  if (!tabla || !btnAdd || !url) return;

  async function loadRows() {
    try {
      const resp = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      const data = await resp.json();
      if (!data || !data.ok) return;
      const rows = data.participaciones || [];
      if (!rows.length) {
        tabla.innerHTML = "<tr><td colspan=\"7\" class=\"text-muted\">No hay participaciones todavía.</td></tr>";
        window.__captacionCaptado = 0;
        if (!Number.isFinite(window.__captacionObjetivo) || window.__captacionObjetivo <= 0) {
          window.__captacionObjetivo = calcCaptacionObjectiveFromInputs();
        }
        if (typeof window.__updateCaptacionDashboard === "function") {
          window.__updateCaptacionDashboard({
            capitalObjetivo: Number.isFinite(window.__captacionObjetivo) ? window.__captacionObjetivo : 0,
            capitalCaptado: 0,
          });
        }
        return;
      }
      const captado = rows.reduce((acc, r) => {
        if (r.estado === "confirmada") {
          return acc + (Number(r.importe_invertido) || 0);
        }
        return acc;
      }, 0);
      const totalConfirmadas = captado || 0;
      const inversureName = "INVERSURE HOME & INVESTMENT";
      const pctParticipe = rows.reduce((acc, r) => {
        if (r.estado !== "confirmada") return acc;
        const clienteNombre = String(r.cliente_nombre || "").trim().toUpperCase();
        if (clienteNombre === inversureName) return acc;
        const pct = Number.isFinite(r.porcentaje_participacion)
          ? Number(r.porcentaje_participacion)
          : (totalConfirmadas > 0 ? ((Number(r.importe_invertido) || 0) / totalConfirmadas) * 100 : 0);
        return acc + (Number.isFinite(pct) ? pct : 0);
      }, 0);
      const pctFinanciacion = Math.max(0, Math.min(100, pctParticipe));
      const finInputs = [
        document.querySelector("[name='financiacion_pct']"),
        document.querySelector("[name='porcentaje_financiacion']"),
      ].filter(Boolean);
      finInputs.forEach((el) => {
        _setElText(el, formatNumberEs(pctFinanciacion, 2));
      });
      window.__captacionCaptado = captado;
      if (!Number.isFinite(window.__captacionObjetivo) || window.__captacionObjetivo <= 0) {
        window.__captacionObjetivo = calcCaptacionObjectiveFromInputs();
      }
      if (typeof window.__updateCaptacionDashboard === "function") {
        window.__updateCaptacionDashboard({
          capitalObjetivo: Number.isFinite(window.__captacionObjetivo) ? window.__captacionObjetivo : 0,
          capitalCaptado: captado,
        });
      }
      tabla.innerHTML = rows.map(r => {
        const pct = r.porcentaje_participacion !== null ? (formatNumberEs(r.porcentaje_participacion, 2) + " %") : "—";
        const fecha = r.fecha ? r.fecha.slice(0, 10).split("-").reverse().join("/") : "";
        const estado = r.estado || "pendiente";
        return `
          <tr data-id="${r.id}">
            <td>${r.cliente_nombre}</td>
            <td class="text-end">${formatEuro(r.importe_invertido)}</td>
            <td class="text-end">${pct}</td>
            <td>${fecha}</td>
            <td>
              <select class="form-select form-select-sm inv-estado">
                <option value="pendiente" ${estado === "pendiente" ? "selected" : ""}>Pendiente</option>
                <option value="confirmada" ${estado === "confirmada" ? "selected" : ""}>Confirmada</option>
                <option value="cancelada" ${estado === "cancelada" ? "selected" : ""}>Cancelada</option>
              </select>
            </td>
            <td class="text-end">
              <button type="button" class="btn btn-sm btn-outline-secondary inv-save">Guardar</button>
              <button type="button" class="btn btn-sm btn-outline-danger inv-del">Borrar</button>
            </td>
          </tr>
        `;
      }).join("");
    } catch (e) {}
  }

  btnAdd.addEventListener("click", async () => {
    const clienteId = elCliente ? elCliente.value : "";
    const importe = parseEuro(_getElText(elImporte));
    if (!clienteId || importe === null) {
      alert("Selecciona cliente e importe.");
      return;
    }
    const resp = await postJson(url, { cliente_id: clienteId, importe_invertido: importe }, { keepalive: false });
    if (!resp.ok) {
      alert("No se pudo añadir la participación.");
      return;
    }
    if (elImporte) elImporte.value = "";
    await loadRows();
  });

  tabla.addEventListener("click", async (e) => {
    const btnDel = e.target.closest(".inv-del");
    const btnSave = e.target.closest(".inv-save");
    const tr = e.target.closest("tr");
    if (!tr) return;
    const id = tr.getAttribute("data-id");
    if (!id) return;
    if (btnSave) {
      const estadoSel = tr.querySelector(".inv-estado");
      const estado = estadoSel ? estadoSel.value : "pendiente";
      const resp = await fetch(`${url}${id}/`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(getCsrfToken() ? { "X-CSRFToken": getCsrfToken() } : {}),
        },
        body: JSON.stringify({ estado }),
      });
      if (!resp.ok) {
        alert("No se pudo guardar el estado.");
        return;
      }
      await loadRows();
      return;
    }
    if (btnDel) {
      if (!confirm("¿Borrar participación?")) return;
      const resp = await fetch(`${url}${id}/`, {
        method: "DELETE",
        headers: { ...(getCsrfToken() ? { "X-CSRFToken": getCsrfToken() } : {}) },
      });
      if (!resp.ok) {
        alert("No se pudo borrar la participación.");
        return;
      }
      await loadRows();
    }
  });

  loadRows();
}

function bindSolicitudes() {
  const tabla = document.getElementById("inv_solicitudes_rows");
  const url = window.PROYECTO_SOLICITUDES_URL || "";
  if (!tabla || !url) return;

  async function loadRows() {
    try {
      const resp = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      const data = await resp.json();
      if (!data || !data.ok) return;
      const rows = data.solicitudes || [];
      if (!rows.length) {
        tabla.innerHTML = "<tr><td colspan=\"5\" class=\"text-muted\">Sin solicitudes todavía.</td></tr>";
        return;
      }
      tabla.innerHTML = rows.map(r => {
        const fecha = r.fecha ? r.fecha.slice(0, 10).split("-").reverse().join("/") : "";
        return `
          <tr data-id="${r.id}">
            <td>${r.cliente_nombre}</td>
            <td class="text-end">${formatEuro(r.importe_solicitado)}</td>
            <td>${fecha}</td>
            <td>${r.estado}</td>
            <td class="text-end">
              <button type="button" class="btn btn-sm btn-outline-success sol-aprobar">Aprobar</button>
              <button type="button" class="btn btn-sm btn-outline-danger sol-rechazar">Rechazar</button>
            </td>
          </tr>
        `;
      }).join("");
    } catch (e) {}
  }

  tabla.addEventListener("click", async (e) => {
    const btnAprobar = e.target.closest(".sol-aprobar");
    const btnRechazar = e.target.closest(".sol-rechazar");
    if (!btnAprobar && !btnRechazar) return;
    const tr = e.target.closest("tr");
    const id = tr.getAttribute("data-id");
    if (!id) return;
    const estado = btnAprobar ? "aprobada" : "rechazada";
    const resp = await fetch(`${url}${id}/`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...(getCsrfToken() ? { "X-CSRFToken": getCsrfToken() } : {}),
      },
      body: JSON.stringify({ estado }),
    });
    if (!resp.ok) {
      alert("No se pudo actualizar la solicitud.");
      return;
    }
    await loadRows();
    if (typeof bindParticipaciones === "function") {
      // refrescar participaciones al aprobar
      setTimeout(() => {
        try { bindParticipaciones(); } catch (e) {}
      }, 300);
    }
  });

  loadRows();
}

function bindComunicaciones() {
  const tabla = document.getElementById("inv_comunicaciones_rows");
  const btnSend = document.getElementById("com_send_btn");
  const elTitulo = document.getElementById("com_titulo");
  const elMensaje = document.getElementById("com_mensaje");
  const url = window.PROYECTO_COMUNICACIONES_URL || "";
  if (!tabla || !btnSend || !url) return;

  async function loadRows() {
    try {
      const resp = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      const data = await resp.json();
      if (!data || !data.ok) return;
      const rows = data.comunicaciones || [];
      if (!rows.length) {
        tabla.innerHTML = "<tr><td colspan=\"4\" class=\"text-muted\">Sin comunicaciones todavía.</td></tr>";
        return;
      }
      tabla.innerHTML = rows.map(r => {
        const fecha = r.fecha ? r.fecha.slice(0, 10).split("-").reverse().join("/") : "";
        return `
          <tr>
            <td>${r.cliente_nombre}</td>
            <td>${r.titulo}</td>
            <td>${r.mensaje}</td>
            <td>${fecha}</td>
          </tr>
        `;
      }).join("");
    } catch (e) {}
  }

  btnSend.addEventListener("click", async () => {
    const titulo = (elTitulo && elTitulo.value || "").trim();
    const mensaje = (elMensaje && elMensaje.value || "").trim();
    if (!titulo || !mensaje) {
      alert("Título y mensaje son obligatorios.");
      return;
    }
    const resp = await postJson(url, { titulo, mensaje }, { keepalive: false });
    if (!resp.ok) {
      alert("No se pudo enviar la comunicación.");
      return;
    }
    if (elTitulo) elTitulo.value = "";
    if (elMensaje) elMensaje.value = "";
    await loadRows();
  });

  loadRows();
}

function bindDocumentos() {
  const wrap = document.getElementById("doc_upload_wrap");
  const btn = document.getElementById("doc_upload_btn");
  const elTitulo = document.getElementById("doc_titulo");
  const elCategoria = document.getElementById("doc_categoria");
  const elArchivo = document.getElementById("doc_archivo");
  const status = document.getElementById("doc_upload_status");
  if (!wrap || !btn || !elArchivo) return;

  const url = wrap.getAttribute("data-upload-url") || "";
  if (!url) return;

  btn.addEventListener("click", async () => {
    const files = elArchivo.files ? Array.from(elArchivo.files) : [];
    if (!files.length) {
      if (status) status.textContent = "Selecciona un archivo para subir.";
      return;
    }
    if (status) status.textContent = "Subiendo documento...";
    const fd = new FormData();
    files.forEach(file => fd.append("archivo", file));
    fd.append("titulo", (elTitulo && elTitulo.value || "").trim());
    fd.append("categoria", (elCategoria && elCategoria.value || "otros").trim());
    const csrf = getCsrfToken();
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          ...(csrf ? { "X-CSRFToken": csrf } : {}),
        },
        body: fd,
      });
      if (!resp.ok) {
        if (status) status.textContent = "No se pudo subir el documento.";
        return;
      }
      window.location.hash = "vista-documentacion";
      window.location.reload();
    } catch (e) {
      if (status) status.textContent = "No se pudo subir el documento.";
    }
  });

  document.querySelectorAll(".doc-delete-btn").forEach(btnDel => {
    if (btnDel.dataset.bindDocDelete === "1") return;
    btnDel.dataset.bindDocDelete = "1";
    btnDel.addEventListener("click", async () => {
      const delUrl = btnDel.getAttribute("data-url") || "";
      if (!delUrl) return;
      if (!confirm("¿Eliminar este documento?")) return;
      const csrf = getCsrfToken();
      try {
        const resp = await fetch(delUrl, {
          method: "POST",
          headers: {
            ...(csrf ? { "X-CSRFToken": csrf } : {}),
          },
        });
        if (!resp.ok) {
          alert("No se pudo borrar el documento.");
          return;
        }
        window.location.hash = "vista-documentacion";
        window.location.reload();
      } catch (e) {
        alert("No se pudo borrar el documento.");
      }
    });
  });

  document.querySelectorAll(".doc-principal-btn").forEach(btnPrincipal => {
    if (btnPrincipal.dataset.bindDocPrincipal === "1") return;
    btnPrincipal.dataset.bindDocPrincipal = "1";
    btnPrincipal.addEventListener("click", async () => {
      const setUrl = btnPrincipal.getAttribute("data-url") || "";
      if (!setUrl) return;
      const csrf = getCsrfToken();
      try {
        const resp = await fetch(setUrl, {
          method: "POST",
          headers: {
            ...(csrf ? { "X-CSRFToken": csrf } : {}),
          },
        });
        if (!resp.ok) {
          alert("No se pudo marcar como principal.");
          return;
        }
        window.location.hash = "vista-documentacion";
        window.location.reload();
      } catch (e) {
        alert("No se pudo marcar como principal.");
      }
    });
  });
}

// -----------------------------
// Init
// -----------------------------
document.addEventListener("DOMContentLoaded", () => {
  try {
    const hash = window.location.hash || "";
    if (hash.startsWith("#vista-")) {
      const tabBtn = document.querySelector(`[data-bs-target="${hash}"]`);
      if (tabBtn && typeof bootstrap !== "undefined") {
        const tab = new bootstrap.Tab(tabBtn);
        tab.show();
      } else if (tabBtn) {
        tabBtn.click();
      }
    }
  } catch (e) {}

  // 1) Formato
  enlazarAutoFormatoInputs(document);
  aplicarFormatoGlobal(document);
  engancharFormatoEnPestanas();

  // 1.b) Sync del nombre del proyecto en la cabecera/card superior
  try {
    bindNombreProyectoLiveUpdate();
  } catch (e) {}

  // 2) Mapa (auto)
  try {
    // Pintar al cargar si ya hay dirección/ref
    window.verMapa();
    // Y actualizar automáticamente cuando el usuario escriba
    bindMapaAutoUpdate();
  } catch (e) {}

  // 3) Autosave (sin botón)
  try {
    window.__recalcValorAdquisicion && window.__recalcValorAdquisicion();
  } catch (e) {}
  bindAutosaveListeners();
  bindAutocalcGastos();
  bindAutocalcValoraciones();
  bindAutocalcValorTransmision();
  bindAutocalcGastosVenta();
  bindAutocalcBeneficios();
  bindMemoriaEconomica();
  bindChecklistOperativo();
  bindParticipaciones();
  bindSolicitudes();
  bindComunicaciones();
  bindComisionInversureInputs();
  bindDocumentos();
});
