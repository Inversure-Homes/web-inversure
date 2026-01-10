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
        ["[name='otros_gastos']", "[name='kpis.metricas.otros_gastos']", "#otros_gastos"],
        ["[name='otros_gastos_adquisicion']", "[name='kpis.metricas.otros_gastos_adquisicion']", "#otros_gastos_adquisicion"],
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
    candidates.push(`/proyectos/${id}/guardar/`);
    candidates.push(`/proyectos/guardar/${id}/`);
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

    // Por defecto: lo guardamos como métrica (clave tal cual)
    payload.kpis.metricas[name] = value;
  });

  // --- Derivado (persistencia): Valor de adquisición = precio_escritura + gastos ---
  try {
    const m = payload.kpis && payload.kpis.metricas ? payload.kpis.metricas : {};

    const precio = Number.isFinite(m.precio_escritura) ? m.precio_escritura : null;

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
// Init
// -----------------------------
document.addEventListener("DOMContentLoaded", () => {
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
});
