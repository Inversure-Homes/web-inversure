(function (root, factory) {
  const api = factory(root);

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }

  root.InversureFinancialDashboard = api;

  if (root && root.document && typeof root.document.addEventListener === "function") {
    const boot = () => {
      try {
        api.init();
      } catch (error) {
        if (root.console && typeof root.console.error === "function") {
          root.console.error("[dashboard] bootstrap failed", error);
        }
      }
    };

    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
      boot();
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof window !== "undefined" ? window : {}, function (root) {
  const DEFAULT_ENDPOINT = "/app/dashboard/data/";
  const FILTER_ORDER = ["fecha_desde", "fecha_hasta", "proyecto_id", "estado"];
  const BRAND_BLUE = "#122135";
  const BRAND_GOLD = "#d7b04c";
  const BRAND_LIGHT = "#94a3b8";
  const STATE_COLORS = {
    captacion: "#f59e0b",
    comprado: "#0ea5e9",
    comercializacion: "#6366f1",
    reservado: "#22c55e",
    vendido: "#10b981",
    cerrado: "#14b8a6",
    descartado: "#94a3b8",
  };

  function toNumber(value) {
    if (typeof value === "number") {
      return Number.isFinite(value) ? value : 0;
    }
    if (typeof value === "string") {
      const text = value.trim();
      if (!text) {
        return 0;
      }
      if (/^-?\d+(?:,\d+)?$/.test(text)) {
        return Number(text.replace(",", "."));
      }
      const normalized = Number(text);
      return Number.isFinite(normalized) ? normalized : 0;
    }
    if (typeof value === "bigint") {
      return Number(value);
    }
    return 0;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatInteger(value) {
    return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0, useGrouping: true }).format(
      Math.round(toNumber(value)),
    );
  }

  function formatPercent(value) {
    return `${new Intl.NumberFormat("es-ES", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      useGrouping: true,
    }).format(toNumber(value))} %`;
  }

  function formatCurrency(value) {
    return new Intl.NumberFormat("es-ES", {
      style: "currency",
      currency: "EUR",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      useGrouping: true,
    }).format(toNumber(value));
  }

  function formatDate(value) {
    if (!value) {
      return "";
    }
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return new Intl.DateTimeFormat("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(date);
  }

  function formatDateTime(value) {
    if (!value) {
      return "";
    }
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return new Intl.DateTimeFormat("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function getBrandColor(cssVariable, fallback) {
    const doc = root.document;
    if (!doc || typeof root.getComputedStyle !== "function" || !doc.documentElement) {
      return fallback;
    }
    try {
      const value = root.getComputedStyle(doc.documentElement).getPropertyValue(cssVariable).trim();
      return value || fallback;
    } catch (error) {
      return fallback;
    }
  }

  function readInitialPayload(doc) {
    if (!doc || typeof doc.getElementById !== "function") {
      return null;
    }
    const raw = doc.getElementById("financialDashboardData");
    if (!raw) {
      return null;
    }
    try {
      const parsed = JSON.parse(raw.textContent || "null");
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch (error) {
      return null;
    }
  }

  function normalizeFilters(filters) {
    const normalized = {
      fecha_desde: "",
      fecha_hasta: "",
      proyecto_id: "",
      estado: "",
    };

    if (!filters || typeof filters !== "object") {
      return normalized;
    }

    normalized.fecha_desde = String(filters.fecha_desde || "").trim();
    normalized.fecha_hasta = String(filters.fecha_hasta || "").trim();
    normalized.proyecto_id = String(filters.proyecto_id ?? "").trim();
    normalized.estado = String(filters.estado || "").trim();
    return normalized;
  }

  function filtersFromSearch(search) {
    const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
    return normalizeFilters({
      fecha_desde: params.get("fecha_desde"),
      fecha_hasta: params.get("fecha_hasta"),
      proyecto_id: params.get("proyecto_id"),
      estado: params.get("estado"),
    });
  }

  function filtersFromForm(form) {
    if (!form) {
      return normalizeFilters();
    }
    const data = new FormData(form);
    return normalizeFilters({
      fecha_desde: data.get("fecha_desde"),
      fecha_hasta: data.get("fecha_hasta"),
      proyecto_id: data.get("proyecto_id"),
      estado: data.get("estado"),
    });
  }

  function filtersToQuery(filters) {
    const normalized = normalizeFilters(filters);
    const params = new URLSearchParams();
    FILTER_ORDER.forEach((key) => {
      const value = normalized[key];
      if (value) {
        params.set(key, value);
      }
    });
    return params.toString();
  }

  function buildMonthlyPoints(monthly) {
    const monthMap = new Map();
    const seriesMap = {
      investment: "total",
      income: "total",
      expense: "total",
      performance: "beneficio",
    };

    Object.entries(seriesMap).forEach(([seriesName, fieldName]) => {
      const rows = Array.isArray(monthly?.[seriesName]) ? monthly[seriesName] : [];
      rows.forEach((row) => {
        const key = String(row?.month || row?.label || "").trim();
        if (!key) {
          return;
        }
        if (!monthMap.has(key)) {
          monthMap.set(key, {
            month: key,
            label: String(row?.label || row?.month || key),
            investment: 0,
            income: 0,
            expense: 0,
            performance: 0,
          });
        }
        const point = monthMap.get(key);
        point[seriesName] = toNumber(row?.[fieldName] ?? row?.total ?? row?.beneficio ?? row?.retorno ?? 0);
      });
    });

    return Array.from(monthMap.values()).sort((left, right) => left.month.localeCompare(right.month));
  }

  function getContext2d(canvas) {
    if (!canvas) {
      return null;
    }
    if (typeof canvas.getContext === "function") {
      try {
        return canvas.getContext("2d");
      } catch (error) {
        return canvas;
      }
    }
    return canvas;
  }

  function createDashboardController(options = {}) {
    const doc = options.document || root.document || null;
    const win = options.window || root || null;
    const endpoint = options.endpoint || (doc && doc.body && doc.body.dataset && doc.body.dataset.dashboardEndpoint) || DEFAULT_ENDPOINT;
    const rootEl = options.root || (doc && typeof doc.querySelector === "function" ? doc.querySelector("[data-dashboard-root]") : null);
    const formEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-filters-form]") : null;
    const statusEl = doc && typeof doc.getElementById === "function" ? doc.getElementById("dashboardStatus") : null;
    const errorEl = doc && typeof doc.getElementById === "function" ? doc.getElementById("dashboardError") : null;
    const lastUpdatedEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-last-update]") : null;
    const checklistPendingEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-checklist-pending]") : null;
    const checklistOverdueEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-checklist-overdue]") : null;
    const financialAlertCountEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-financial-alert-count]") : null;
    const projectSelect = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("#dashboardProyecto") : null;
    const stateDistributionEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-state-distribution]") : null;
    const benefitBarsEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-benefit-bars]") : null;
    const operationalAlertsEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-alerts='operational']") : null;
    const financialAlertsEl = rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-alerts='financial']") : null;
    const rankingEls = {
      best_roi: rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-ranking='best_roi']") : null,
      worst_roi: rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-ranking='worst_roi']") : null,
      investment_return: rootEl && typeof rootEl.querySelector === "function" ? rootEl.querySelector("[data-dashboard-ranking='investment_return']") : null,
    };
    const openBenefitsCanvas = doc && typeof doc.getElementById === "function" ? doc.getElementById("openBenefitsChart") : null;
    const monthlyCanvas = doc && typeof doc.getElementById === "function" ? doc.getElementById("monthlyEvolutionChart") : null;
    const deviationCanvas = doc && typeof doc.getElementById === "function" ? doc.getElementById("benefitDeviationChart") : null;
    const deviationListEl = doc && typeof doc.getElementById === "function" ? doc.getElementById("benefitDeviationList") : null;
    const initialPayload = options.initialPayload || readInitialPayload(doc);
    const fetchImpl = options.fetch || (win && typeof win.fetch === "function" ? win.fetch.bind(win) : null);
    const ChartCtor = options.Chart || (win && win.Chart ? win.Chart : null);
    const chartInstances = {
      openBenefits: null,
      monthly: null,
      deviation: null,
    };
    let latestPayload = initialPayload || null;
    let activeRequestId = 0;
    let activeAbortController = null;

    function setBusy(isBusy) {
      if (rootEl) {
        rootEl.setAttribute("aria-busy", isBusy ? "true" : "false");
      }
    }

    function setStatus(message) {
      if (statusEl) {
        statusEl.textContent = message || "";
      }
    }

    function showError(message) {
      if (!errorEl) {
        return;
      }
      if (message) {
        errorEl.textContent = message;
        errorEl.classList.remove("d-none");
        if (typeof errorEl.focus === "function") {
          errorEl.focus();
        }
      } else {
        errorEl.textContent = "";
        errorEl.classList.add("d-none");
      }
    }

    function updateLastUpdated(meta) {
      const generatedAt = meta && meta.generated_at ? formatDateTime(meta.generated_at) : "";
      if (lastUpdatedEl) {
        lastUpdatedEl.textContent = generatedAt ? `Actualizado · ${generatedAt}` : "Actualizado";
      }
      if (generatedAt) {
        setStatus(`Última actualización: ${generatedAt}`);
      } else {
        setStatus("Datos cargados");
      }
    }

    function syncFiltersToForm(filters) {
      if (!formEl) {
        return;
      }
      const normalized = normalizeFilters(filters);
      const fields = {
        fecha_desde: normalized.fecha_desde,
        fecha_hasta: normalized.fecha_hasta,
        proyecto_id: normalized.proyecto_id,
        estado: normalized.estado,
      };
      Object.entries(fields).forEach(([name, value]) => {
        const field = formEl.querySelector(`[name="${name}"]`);
        if (field) {
          field.value = value;
        }
      });
    }

    function renderProjectOptions(projects, selectedProjectId) {
      if (!projectSelect) {
        return;
      }
      const selectedValue = String(selectedProjectId || "").trim();
      const options = ['<option value="">Todos los proyectos</option>'];
      (Array.isArray(projects) ? projects : []).forEach((project) => {
        const value = String(project?.project_id ?? project?.id ?? "").trim();
        if (!value) {
          return;
        }
        const label = [
          project?.nombre || `Proyecto ${value}`,
          project?.estado_label ? `· ${project.estado_label}` : "",
        ]
          .filter(Boolean)
          .join(" ");
        const isSelected = selectedValue && selectedValue === value ? " selected" : "";
        options.push(`<option value="${escapeHtml(value)}"${isSelected}>${escapeHtml(label)}</option>`);
      });
      projectSelect.innerHTML = options.join("");
      if (selectedValue) {
        projectSelect.value = selectedValue;
      }
    }

    function renderKpis(kpis) {
      const nodes = doc && typeof doc.querySelectorAll === "function" ? Array.from(doc.querySelectorAll("[data-dashboard-kpi]")) : [];
      nodes.forEach((node) => {
        const key = node.dataset.dashboardKpi;
        const format = node.dataset.dashboardFormat || "number";
        const value = kpis?.[key];
        let formatted = String(value ?? "");
        if (format === "currency") {
          formatted = formatCurrency(value);
        } else if (format === "percent") {
          formatted = formatPercent(value);
        } else if (format === "integer") {
          formatted = formatInteger(value);
        }
        node.textContent = formatted;
      });
    }

    function renderStateDistribution(rows) {
      if (!stateDistributionEl) {
        return;
      }
      const items = Array.isArray(rows) ? rows : [];
      if (!items.length) {
        stateDistributionEl.innerHTML = '<div class="text-muted">Sin distribución por estado todavía.</div>';
        return;
      }
      stateDistributionEl.innerHTML = items
        .map((row) => {
          const state = String(row?.estado || "").trim();
          const label = row?.estado_label || state || "Estado";
          const pct = toNumber(row?.pct);
          const total = toNumber(row?.total);
          const color = STATE_COLORS[state] || BRAND_GOLD;
          return `
            <div class="chart-row" data-state="${escapeHtml(state)}">
              <span class="chart-label">
                ${escapeHtml(label)}
                <span class="chart-state">· ${escapeHtml(state)}</span>
              </span>
              <div class="chart-bar">
                <span style="width: ${Math.max(0, Math.min(pct, 100)).toFixed(0)}%; background-color: ${color};"></span>
              </div>
              <span class="chart-value">${formatInteger(total)}</span>
              <span class="chart-pct">${formatPercent(pct).replace(" %", " %")}</span>
            </div>
          `;
        })
        .join("");
    }

    function renderBenefitBars(rows) {
      if (!benefitBarsEl) {
        return;
      }
      const items = Array.isArray(rows) ? rows : [];
      if (!items.length) {
        benefitBarsEl.innerHTML = '<div class="text-muted">Sin datos de beneficios todavía.</div>';
        return;
      }
      benefitBarsEl.innerHTML = items
        .map((row) => {
          const pct = toNumber(row?.pct);
          const label = row?.nombre || "Proyecto";
          const state = row?.estado_label || row?.estado || "";
          const value = row?.valor_fmt || formatCurrency(row?.valor);
          const pctLabel = row?.pct_fmt || formatPercent(pct);
          const color = row?.color || BRAND_GOLD;
          return `
            <div class="chart-row">
              <span class="chart-label">
                ${escapeHtml(label)}
                ${state ? `<span class="chart-state">· ${escapeHtml(state)}</span>` : ""}
              </span>
              <div class="chart-bar">
                <span style="width: ${Math.max(0, Math.min(pct, 100)).toFixed(0)}%; background-color: ${color};"></span>
              </div>
              <span class="chart-value">${escapeHtml(value)}</span>
              <span class="chart-pct">${escapeHtml(pctLabel)}</span>
            </div>
          `;
        })
        .join("");
    }

    function renderRankingBlock(container, items, mode) {
      if (!container) {
        return;
      }
      const rows = Array.isArray(items) ? items : [];
      if (!rows.length) {
        container.innerHTML = '<div class="text-muted">Sin datos disponibles.</div>';
        return;
      }
      container.innerHTML = rows
        .map((item) => {
          const title = item?.nombre || "Proyecto";
          const state = item?.estado_label || item?.estado || "";
          const subtitleParts = [];
          if (state) {
            subtitleParts.push(escapeHtml(state));
          }
          if (mode !== "investment_return" && item?.capital_captado !== undefined) {
            subtitleParts.push(`Capital ${escapeHtml(formatCurrency(item.capital_captado))}`);
          }
          if (mode === "investment_return" && item?.capital_invertido !== undefined) {
            subtitleParts.push(`Invertido ${escapeHtml(formatCurrency(item.capital_invertido))}`);
          }
          const rightValue =
            mode === "investment_return"
              ? formatCurrency(item?.retorno_total)
              : formatPercent(item?.roi);
          return `
            <div class="metric-line">
              <span>
                ${escapeHtml(title)}
                <small class="d-block text-muted">${subtitleParts.join(" · ")}</small>
              </span>
              <strong>${escapeHtml(rightValue)}</strong>
            </div>
          `;
        })
        .join("");
    }

    function renderRankings(rankings) {
      renderRankingBlock(rankingEls.best_roi, rankings?.best_roi, "best_roi");
      renderRankingBlock(rankingEls.worst_roi, rankings?.worst_roi, "worst_roi");
      renderRankingBlock(rankingEls.investment_return, rankings?.investment_return, "investment_return");
    }

    function renderOperationalAlerts(items) {
      if (!operationalAlertsEl) {
        return;
      }
      const rows = Array.isArray(items) ? items : [];
      if (!rows.length) {
        operationalAlertsEl.innerHTML = '<div class="text-muted">Sin tareas pendientes.</div>';
        return;
      }
      operationalAlertsEl.innerHTML = rows
        .map((item) => {
          const overdue = Boolean(item?.overdue);
          const dateLabel = item?.fecha_objetivo ? formatDate(item.fecha_objetivo) : "";
          const delay = overdue ? `<span class="alert-delay">+${formatInteger(item?.dias_retraso || 0)}d</span>` : "";
          const meta = [
            item?.proyecto || "",
            item?.fase || "",
            item?.responsable || "",
          ]
            .filter(Boolean)
            .map((value) => `<span>${escapeHtml(value)}</span>`)
            .join("<span>·</span>");
          return `
            <div class="alert-item ${overdue ? "alert-overdue" : ""}">
              <div>
                <div class="alert-title">${escapeHtml(item?.titulo || "Tarea")}</div>
                <div class="alert-meta">${meta}</div>
              </div>
              <div class="alert-date">
                ${dateLabel ? escapeHtml(dateLabel) : '<span class="text-muted">Sin fecha</span>'}
                ${delay}
              </div>
            </div>
          `;
        })
        .join("");
    }

    function renderFinancialAlerts(alerts) {
      if (!financialAlertsEl) {
        return;
      }
      const items = Array.isArray(alerts?.items) ? alerts.items : [];
      if (financialAlertCountEl) {
        financialAlertCountEl.textContent = formatInteger(items.length);
      }
      if (!items.length) {
        financialAlertsEl.innerHTML = '<div class="text-muted">Sin alertas financieras relevantes.</div>';
        return;
      }
      financialAlertsEl.innerHTML = items
        .map((item) => {
          const severity = String(item?.severity || "info");
          const badgeClass = severity === "critical" ? "text-bg-danger" : severity === "warning" ? "text-bg-warning" : "text-bg-info";
          const metaParts = [];
          if (item?.detail) {
            metaParts.push(item.detail);
          }
          if (item?.project_id) {
            metaParts.push(`Proyecto ${item.project_id}`);
          }
          return `
            <div class="alert-item">
              <div>
                <div class="alert-title">${escapeHtml(item?.title || "Alerta")}</div>
                <div class="alert-meta">${metaParts.map((value) => `<span>${escapeHtml(value)}</span>`).join("<span>·</span>")}</div>
              </div>
              <div class="alert-date">
                <span class="badge ${badgeClass}">${escapeHtml(item?.category || severity)}</span>
              </div>
            </div>
          `;
        })
        .join("");
    }

    function renderDeviationChart(rows) {
      const items = Array.isArray(rows) ? rows : [];
      if (deviationListEl) {
        if (!items.length) {
          deviationListEl.innerHTML = '<div class="text-muted">Sin datos de desviación todavía.</div>';
        } else {
          deviationListEl.innerHTML = items
            .map((item) => {
              const estimado = toNumber(item?.estimado);
              const real = toNumber(item?.real);
              const delta = real - estimado;
              const pct = estimado ? (delta / estimado) * 100 : null;
              const badgeClass = delta > 0 ? "text-bg-success" : delta < 0 ? "text-bg-danger" : "text-bg-secondary";
              const pctLabel = pct === null ? "—" : formatPercent(pct);
              return `
                <div class="col-12 col-md-6">
                  <div class="border rounded-3 p-2 d-flex align-items-center justify-content-between">
                    <div>
                      <div class="fw-semibold">${escapeHtml(item?.nombre || "Proyecto")}</div>
                      <div class="text-muted small">Δ ${escapeHtml(formatCurrency(delta))} · ${escapeHtml(pctLabel)}</div>
                    </div>
                    <span class="badge ${badgeClass}">Desviación</span>
                  </div>
                </div>
              `;
            })
            .join("");
        }
      }

      if (!deviationCanvas || !ChartCtor) {
        return;
      }

      const labels = items.map((item) => item?.nombre || "Proyecto");
      const estimated = items.map((item) => toNumber(item?.estimado));
      const real = items.map((item) => toNumber(item?.real));
      const config = {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Estimado base",
              data: estimated,
              backgroundColor: BRAND_GOLD,
              borderRadius: 8,
              maxBarThickness: 24,
            },
            {
              label: "Real",
              data: real,
              backgroundColor: BRAND_BLUE,
              borderRadius: 8,
              maxBarThickness: 24,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "bottom",
              labels: { boxWidth: 10, color: "#64748b", font: { size: 11 } },
            },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${formatCurrency(ctx.parsed.y || 0)}`,
              },
            },
          },
          scales: {
            x: {
              ticks: { color: "#64748b", font: { size: 11 } },
              grid: { display: false },
            },
            y: {
              ticks: {
                color: "#94a3b8",
                callback: (value) => formatCurrency(value).replace(" €", " €"),
              },
              grid: { color: "rgba(148,163,184,0.15)" },
            },
          },
        },
      };

      renderChart("deviation", deviationCanvas, config);
    }

    function renderMonthlyChart(monthly) {
      if (!monthlyCanvas || !ChartCtor) {
        return;
      }
      const points = buildMonthlyPoints(monthly);
      if (!points.length) {
        if (chartInstances.monthly && typeof chartInstances.monthly.destroy === "function") {
          chartInstances.monthly.destroy();
          chartInstances.monthly = null;
        }
        return;
      }
      const labels = points.map((point) => point.label || point.month);
      const config = {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Inversión",
              data: points.map((point) => point.investment),
              borderColor: BRAND_BLUE,
              backgroundColor: BRAND_BLUE,
              tension: 0.35,
              fill: false,
            },
            {
              label: "Ingresos",
              data: points.map((point) => point.income),
              borderColor: BRAND_GOLD,
              backgroundColor: BRAND_GOLD,
              tension: 0.35,
              fill: false,
            },
            {
              label: "Gastos",
              data: points.map((point) => point.expense),
              borderColor: BRAND_LIGHT,
              backgroundColor: BRAND_LIGHT,
              tension: 0.35,
              fill: false,
            },
            {
              label: "Beneficio",
              data: points.map((point) => point.performance),
              borderColor: "#10b981",
              backgroundColor: "#10b981",
              tension: 0.35,
              fill: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "bottom",
              labels: { boxWidth: 10, color: "#64748b", font: { size: 11 } },
            },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${formatCurrency(ctx.parsed.y || 0)}`,
              },
            },
          },
          scales: {
            x: {
              ticks: { color: "#64748b", font: { size: 11 } },
              grid: { display: false },
            },
            y: {
              ticks: {
                color: "#94a3b8",
                callback: (value) => formatCurrency(value),
              },
              grid: { color: "rgba(148,163,184,0.15)" },
            },
          },
        },
      };

      renderChart("monthly", monthlyCanvas, config);
    }

    function renderOpenBenefitsChart(kpis) {
      if (!openBenefitsCanvas || !ChartCtor) {
        return;
      }
      const bruto = toNumber(kpis?.beneficio_abierto_bruto);
      const neto = toNumber(kpis?.beneficio_abierto_neto);
      const centerLabel = "Beneficio medio";
      const centerValue = kpis?.beneficio_cerrado_neto_medio ? formatCurrency(kpis.beneficio_cerrado_neto_medio) : "";
      const config = {
        type: "doughnut",
        data: {
          labels: ["Beneficio bruto", "Beneficio neto"],
          datasets: [
            {
              data: [bruto, neto],
              backgroundColor: [BRAND_BLUE, BRAND_GOLD],
              borderWidth: 0,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "62%",
          plugins: {
            legend: {
              position: "bottom",
              labels: { boxWidth: 10, color: "#64748b", font: { size: 11 } },
            },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.label}: ${formatCurrency(ctx.parsed || 0)}`,
              },
            },
          },
        },
        plugins: [
          {
            id: "centerText",
            beforeDraw(chart) {
              if (!centerValue) {
                return;
              }
              const context = chart.ctx;
              const { left, right, top, bottom } = chart.chartArea;
              const centerX = (left + right) / 2;
              const centerY = (top + bottom) / 2;
              context.save();
              context.textAlign = "center";
              context.textBaseline = "middle";
              context.fillStyle = "#64748b";
              context.font = "11px Inter, sans-serif";
              context.fillText(centerLabel, centerX, centerY - 8);
              context.fillStyle = "#0f172a";
              context.font = "600 14px Inter, sans-serif";
              context.fillText(centerValue, centerX, centerY + 10);
              context.restore();
            },
          },
        ],
      };

      renderChart("openBenefits", openBenefitsCanvas, config);
    }

    function renderChart(key, canvas, config) {
      if (!ChartCtor || !canvas) {
        return null;
      }
      const context = getContext2d(canvas);
      if (!context) {
        return null;
      }
      if (chartInstances[key]) {
        const chart = chartInstances[key];
        chart.data = config.data;
        chart.options = config.options;
        if (config.plugins) {
          chart.config.plugins = config.plugins;
        }
        if (typeof chart.update === "function") {
          chart.update();
        }
        return chart;
      }
      chartInstances[key] = new ChartCtor(context, config);
      return chartInstances[key];
    }

    function renderPayload(payload) {
      if (!payload || typeof payload !== "object") {
        return;
      }
      latestPayload = payload;
      clearError();
      updateLastUpdated(payload.meta || {});
      syncFiltersToForm(payload.filters || {});
      renderProjectOptions(payload.projects || [], payload.filters?.proyecto_id || "");
      renderKpis(payload.kpis || {});
      renderStateDistribution(payload.charts?.state_distribution || []);
      renderBenefitBars(payload.charts?.benefit_bars || []);
      renderDeviationChart(payload.charts?.deviation || []);
      renderOpenBenefitsChart(payload.kpis || {});
      renderMonthlyChart(payload.series?.monthly || {});
      renderRankings(payload.rankings || {});
      renderOperationalAlerts(payload.alerts?.operational?.items || []);
      renderFinancialAlerts(payload.alerts?.financial || {});

      if (checklistPendingEl) {
        checklistPendingEl.textContent = `Pendientes ${formatInteger(payload.alerts?.operational?.pendientes || 0)}`;
      }
      if (checklistOverdueEl) {
        checklistOverdueEl.textContent = `Vencidas ${formatInteger(payload.alerts?.operational?.vencidas || 0)}`;
      }
      if (financialAlertCountEl) {
        financialAlertCountEl.textContent = formatInteger(payload.alerts?.financial?.items?.length || 0);
      }
    }

    function clearError() {
      showError("");
    }

    async function safeResponseText(response) {
      try {
        return await response.text();
      } catch (error) {
        return "";
      }
    }

    async function loadFilters(filters, options = {}) {
      if (typeof fetchImpl !== "function") {
        return null;
      }

      const normalized = normalizeFilters(filters);
      const query = filtersToQuery(normalized);
      const nextUrl = query ? `${endpoint}?${query}` : endpoint;

      if (activeAbortController) {
        activeAbortController.abort();
      }

      const requestId = ++activeRequestId;
      const controller = new AbortController();
      activeAbortController = controller;
      setBusy(true);
      setStatus("Actualizando datos...");
      clearError();

      try {
        const response = await fetchImpl(nextUrl, {
          signal: controller.signal,
          headers: {
            "X-Requested-With": "XMLHttpRequest",
          },
        });

        if (!response || !response.ok) {
          const extra = response ? await safeResponseText(response) : "";
          throw new Error(
            response
              ? `No se pudo cargar el dashboard (${response.status})${extra ? `: ${extra}` : ""}`
              : "No se pudo cargar el dashboard",
          );
        }

        const payload = await response.json();
        if (controller.signal.aborted || requestId !== activeRequestId) {
          return null;
        }

        renderPayload(payload);

        if (win && win.history && typeof win.history.pushState === "function" && options.push !== false) {
          const nextPath = `${win.location.pathname}${query ? `?${query}` : ""}`;
          win.history.pushState({ payload }, "", nextPath);
        } else if (win && win.history && typeof win.history.replaceState === "function" && options.replace === true) {
          const nextPath = `${win.location.pathname}${query ? `?${query}` : ""}`;
          win.history.replaceState({ payload }, "", nextPath);
        }

        setBusy(false);
        return payload;
      } catch (error) {
        if (controller.signal.aborted || (error && error.name === "AbortError")) {
          return null;
        }
        if (requestId !== activeRequestId) {
          return null;
        }
        setBusy(false);
        showError("No se pudieron actualizar los datos. Se mantiene el último estado cargado.");
        setStatus("Error al actualizar el dashboard");
        return null;
      } finally {
        if (requestId === activeRequestId) {
          activeAbortController = null;
        }
      }
    }

    function onSubmit(event) {
      event.preventDefault();
      return loadFilters(filtersFromForm(formEl), { push: true });
    }

    function onChange(event) {
      if (!event || !event.target || !event.target.name) {
        return;
      }
      return loadFilters(filtersFromForm(formEl), { push: true });
    }

    function onReset(event) {
      event.preventDefault();
      if (formEl && typeof formEl.reset === "function") {
        formEl.reset();
      }
      return loadFilters(normalizeFilters(), { push: true });
    }

    function onPopState(event) {
      const statePayload = event && event.state && event.state.payload;
      if (statePayload) {
        renderPayload(statePayload);
        return;
      }
      const urlFilters = filtersFromSearch(win && win.location ? win.location.search : "");
      return loadFilters(urlFilters, { push: false, replace: true });
    }

    function init() {
      if (formEl) {
        formEl.addEventListener("submit", onSubmit);
        formEl.addEventListener("change", onChange);
        const resetButton = formEl.querySelector("[data-dashboard-reset]");
        if (resetButton) {
          resetButton.addEventListener("click", onReset);
        }
      }

      if (win && typeof win.addEventListener === "function") {
        win.addEventListener("popstate", onPopState);
      }

      if (initialPayload) {
        renderPayload(initialPayload);
        if (win && win.history && typeof win.history.replaceState === "function" && win.location) {
          win.history.replaceState({ payload: initialPayload }, "", win.location.href);
        }
      }

      setBusy(false);
      return initialPayload;
    }

    return {
      init,
      loadFilters,
      renderPayload,
      filtersFromForm: () => filtersFromForm(formEl),
      filtersFromSearch,
      filtersToQuery,
      normalizeFilters,
      latestPayload: () => latestPayload,
    };
  }

  function init(options = {}) {
    const controller = createDashboardController(options);
    controller.init();
    return controller;
  }

  return {
    init,
    createDashboardController,
    formatCurrency,
    formatDate,
    formatDateTime,
    formatInteger,
    formatPercent,
    filtersFromSearch,
    filtersToQuery,
    normalizeFilters,
    toNumber,
  };
});
