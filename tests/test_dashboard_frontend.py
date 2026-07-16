from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "core" / "static" / "core" / "dashboard.js"


def _run_node(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "node script failed\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}\n",
        )
    return json.loads(result.stdout)


def _payload() -> dict[str, object]:
    return {
        "meta": {"generated_at": "2026-07-16T12:00:00+02:00"},
        "filters": {"fecha_desde": "", "fecha_hasta": "", "proyecto_id": "", "estado": ""},
        "permissions": {"can_proyectos": True},
        "scope": {"project_count": 2, "active_project_count": 1, "finalized_project_count": 1, "has_filters": False},
        "kpis": {
            "inversores_activos": 7,
            "inversores_cuota": 5,
            "capital_en_vigor": "1000.00",
            "capital_actual": "1500.00",
            "capital_acumulado": "2500.00",
            "operaciones": 3,
            "beneficio_inversure": "125.00",
            "beneficio_abierto_bruto": "200.00",
            "beneficio_abierto_neto": "150.00",
            "beneficio_cerrado_neto_medio": "75.00",
            "beneficio_cerrado_bruto": "500.00",
            "beneficio_cerrado_neto": "450.00",
            "beneficio_cerrado_bruto_medio": "250.00",
            "beneficio_cerrado_roi_bruto_total": "12.5",
            "beneficio_cerrado_roi_neto_total": "10.0",
            "beneficio_cerrado_roi_bruto_medio": "6.25",
            "beneficio_cerrado_roi_neto_medio": "5.00",
        },
        "series": {
            "monthly": {
                "investment": [
                    {"month": "2026-06-01", "label": "Jun 2026", "total": "1000.00"},
                    {"month": "2026-07-01", "label": "Jul 2026", "total": "1500.00"},
                ],
                "income": [
                    {"month": "2026-06-01", "label": "Jun 2026", "total": "1200.00"},
                    {"month": "2026-07-01", "label": "Jul 2026", "total": "1600.00"},
                ],
                "expense": [
                    {"month": "2026-06-01", "label": "Jun 2026", "total": "800.00"},
                    {"month": "2026-07-01", "label": "Jul 2026", "total": "900.00"},
                ],
                "performance": [
                    {"month": "2026-06-01", "label": "Jun 2026", "beneficio": "400.00"},
                    {"month": "2026-07-01", "label": "Jul 2026", "beneficio": "700.00"},
                ],
            }
        },
        "charts": {
            "state_distribution": [
                {"estado": "captacion", "estado_label": "Captación", "total": 1, "pct": 50.0},
                {"estado": "cerrado", "estado_label": "Cerrado", "total": 1, "pct": 50.0},
            ],
            "benefit_bars": [
                {
                    "nombre": "Proyecto A",
                    "estado": "captacion",
                    "estado_label": "Captación",
                    "valor_fmt": "1.000,00 €",
                    "valor": "1000.00",
                    "pct": 100.0,
                    "pct_fmt": "100,00 %",
                    "color": "#f59e0b",
                },
                {
                    "nombre": "Proyecto B",
                    "estado": "cerrado",
                    "estado_label": "Cerrado",
                    "valor_fmt": "2.000,00 €",
                    "valor": "2000.00",
                    "pct": 80.0,
                    "pct_fmt": "80,00 %",
                    "color": "#14b8a6",
                },
            ],
            "deviation": [
                {"nombre": "Proyecto A", "estimado": "100.00", "real": "120.00"},
                {"nombre": "Proyecto B", "estimado": "200.00", "real": "150.00"},
            ],
        },
        "rankings": {
            "best_roi": [
                {
                    "nombre": "Proyecto B",
                    "estado": "cerrado",
                    "estado_label": "Cerrado",
                    "capital_captado": "2000.00",
                    "roi": "18.00",
                }
            ],
            "worst_roi": [
                {
                    "nombre": "Proyecto A",
                    "estado": "captacion",
                    "estado_label": "Captación",
                    "capital_captado": "1000.00",
                    "roi": "-3.50",
                }
            ],
            "investment_return": [
                {
                    "nombre": "Proyecto B",
                    "estado": "cerrado",
                    "estado_label": "Cerrado",
                    "capital_invertido": "1500.00",
                    "retorno_total": "2400.00",
                }
            ],
        },
        "alerts": {
            "operational": {
                "pendientes": 2,
                "vencidas": 1,
                "items": [
                    {
                        "titulo": "Tarea 1",
                        "proyecto": "Proyecto A",
                        "fase": "Comité",
                        "responsable": "Ana",
                        "fecha_objetivo": "2026-07-15",
                        "overdue": True,
                        "dias_retraso": 1,
                    }
                ],
            },
            "financial": {
                "items": [
                    {
                        "severity": "warning",
                        "category": "roi_negativo",
                        "title": "ROI negativo en Proyecto A",
                        "detail": "ROI actual: -3.50%",
                        "project_id": 17,
                    }
                ]
            },
            "summary": {"total": 3, "critical": 0, "warning": 1, "info": 2},
        },
        "projects": [
            {"project_id": 17, "nombre": "Proyecto A", "estado_label": "Captación"},
            {"project_id": 22, "nombre": "Proyecto B", "estado_label": "Cerrado"},
        ],
    }


def _node_script(*, initial_payload: dict[str, object], next_payload: dict[str, object] | None = None, scenario: str) -> str:
    initial_json = json.dumps(initial_payload)
    next_json = json.dumps(next_payload) if next_payload is not None else "null"
    js_path = json.dumps(str(DASHBOARD_JS))
    return textwrap.dedent(
        f"""
        const dashboard = require({js_path});

        function makeClassList(initial = []) {{
          const values = new Set(initial);
          return {{
            add(...items) {{ items.forEach((item) => values.add(item)); }},
            remove(...items) {{ items.forEach((item) => values.delete(item)); }},
            contains(item) {{ return values.has(item); }},
            toArray() {{ return Array.from(values); }},
          }};
        }}

        function makeElement(initial = {{}}) {{
          const listeners = {{}};
          const el = {{
            id: initial.id || "",
            dataset: initial.dataset || {{}},
            value: initial.value || "",
            textContent: initial.textContent || "",
            innerHTML: initial.innerHTML || "",
            style: {{}},
            attributes: {{}},
            focusCount: 0,
            classList: makeClassList((initial.className || "").split(/\\s+/).filter(Boolean)),
            addEventListener(type, handler) {{
              (listeners[type] ||= []).push(handler);
            }},
            dispatchEvent(event) {{
              (listeners[event.type] || []).forEach((handler) => handler({{
                type: event.type,
                target: el,
                preventDefault() {{}},
                ...event,
              }}));
            }},
            focus() {{
              this.focusCount += 1;
            }},
            setAttribute(name, value) {{
              this.attributes[name] = String(value);
            }},
            getAttribute(name) {{
              return this.attributes[name];
            }},
            removeAttribute(name) {{
              delete this.attributes[name];
            }},
            querySelector(selector) {{
              return this._queryMap ? this._queryMap[selector] || null : null;
            }},
            querySelectorAll(selector) {{
              return this._queryAllMap ? this._queryAllMap[selector] || [] : [];
            }},
            getContext() {{
              return {{ canvas: el }};
            }},
          }};
          el._queryMap = initial.queryMap || {{}};
          el._queryAllMap = initial.queryAllMap || {{}};
          return el;
        }}

        function makeDocument(registry) {{
          return {{
            readyState: "complete",
            body: {{ dataset: {{ dashboardEndpoint: "/app/dashboard/data/" }} }},
            documentElement: makeElement(),
            querySelector(selector) {{
              return registry.query[selector] || null;
            }},
            querySelectorAll(selector) {{
              return registry.queryAll[selector] || [];
            }},
            getElementById(id) {{
              return registry.ids[id] || null;
            }},
            addEventListener() {{}},
            createElement() {{
              return makeElement();
            }},
          }};
        }}

        function makeHistory() {{
          const calls = [];
          return {{
            calls,
            pushState(state, title, url) {{
              calls.push({{ method: "push", state, url }});
            }},
            replaceState(state, title, url) {{
              calls.push({{ method: "replace", state, url }});
            }},
          }};
        }}

        function makeWindow(history) {{
          const listeners = {{}};
          return {{
            location: {{
              pathname: "/app/dashboard/",
              search: "",
              href: "http://testserver/app/dashboard/",
            }},
            history,
            addEventListener(type, handler) {{
              (listeners[type] ||= []).push(handler);
            }},
            dispatch(type, event = {{}}) {{
              (listeners[type] || []).forEach((handler) => handler(event));
            }},
            getComputedStyle() {{
              return {{
                getPropertyValue() {{
                  return "";
                }},
              }};
            }},
          }};
        }}

        function makeChartStub() {{
          function ChartStub(ctx, config) {{
            this.ctx = ctx;
            this.config = JSON.parse(JSON.stringify(config, (key, value) => typeof value === "function" ? "__fn__" : value));
            this.data = config.data;
            this.options = config.options;
            this.updateCount = 0;
            this.destroyed = false;
            ChartStub.instances.push(this);
          }}
          ChartStub.instances = [];
          ChartStub.prototype.update = function () {{
            this.updateCount += 1;
          }};
          ChartStub.prototype.destroy = function () {{
            this.destroyed = true;
          }};
          return ChartStub;
        }}

        function makeResponse(payload, ok = true, status = 200) {{
          return {{
            ok,
            status,
            json: async () => payload,
            text: async () => JSON.stringify(payload),
          }};
        }}

        const initialPayload = {initial_json};
        const nextPayload = {next_json};
        const history = makeHistory();
        const windowStub = makeWindow(history);
        const ChartStub = makeChartStub();

        const fields = {{
          fecha_desde: makeElement({{ value: initialPayload.filters.fecha_desde || "" }}),
          fecha_hasta: makeElement({{ value: initialPayload.filters.fecha_hasta || "" }}),
          proyecto_id: makeElement({{ value: initialPayload.filters.proyecto_id || "" }}),
          estado: makeElement({{ value: initialPayload.filters.estado || "" }}),
        }};
        const resetLink = makeElement();
        const form = makeElement({{
          queryMap: {{
            '[name="fecha_desde"]': fields.fecha_desde,
            '[name="fecha_hasta"]': fields.fecha_hasta,
            '[name="proyecto_id"]': fields.proyecto_id,
            '[name="estado"]': fields.estado,
            '[data-dashboard-reset]': resetLink,
          }},
        }});

        const root = makeElement({{
          dataset: {{ dashboardEndpoint: "/app/dashboard/data/" }},
          queryMap: {{
            "[data-dashboard-filters-form]": form,
            "[data-dashboard-last-update]": makeElement(),
            "[data-dashboard-checklist-pending]": makeElement(),
            "[data-dashboard-checklist-overdue]": makeElement(),
            "[data-dashboard-financial-alert-count]": makeElement(),
            "[data-dashboard-state-distribution]": makeElement(),
            "[data-dashboard-benefit-bars]": makeElement(),
            "[data-dashboard-alerts='operational']": makeElement(),
            "[data-dashboard-alerts='financial']": makeElement(),
            "[data-dashboard-ranking='best_roi']": makeElement(),
            "[data-dashboard-ranking='worst_roi']": makeElement(),
            "[data-dashboard-ranking='investment_return']": makeElement(),
            "#dashboardProyecto": makeElement({{ value: initialPayload.filters.proyecto_id || "" }}),
          }},
        }});

        const dashboardStatus = makeElement();
        const dashboardError = makeElement({{ className: "d-none" }});
        const openBenefitsChart = makeElement();
        const monthlyEvolutionChart = makeElement();
        const benefitDeviationChart = makeElement();
        const benefitDeviationList = makeElement();
        const initialPayloadNode = makeElement({{ textContent: JSON.stringify(initialPayload) }});

        const kpiNodes = [
          makeElement({{ dataset: {{ dashboardKpi: "inversores_activos", dashboardFormat: "integer" }}, textContent: "7" }}),
          makeElement({{ dataset: {{ dashboardKpi: "inversores_cuota", dashboardFormat: "integer" }}, textContent: "5" }}),
          makeElement({{ dataset: {{ dashboardKpi: "capital_en_vigor", dashboardFormat: "currency" }}, textContent: "1.000,00 €" }}),
          makeElement({{ dataset: {{ dashboardKpi: "capital_acumulado", dashboardFormat: "currency" }}, textContent: "2.500,00 €" }}),
          makeElement({{ dataset: {{ dashboardKpi: "operaciones", dashboardFormat: "integer" }}, textContent: "3" }}),
          makeElement({{ dataset: {{ dashboardKpi: "beneficio_inversure", dashboardFormat: "currency" }}, textContent: "125,00 €" }}),
        ];

        const registry = {{
          query: {{
            "[data-dashboard-root]": root,
          }},
          queryAll: {{
            "[data-dashboard-kpi]": kpiNodes,
          }},
          ids: {{
            dashboardStatus,
            dashboardError,
            openBenefitsChart,
            monthlyEvolutionChart,
            benefitDeviationChart,
            benefitDeviationList,
            financialDashboardData: initialPayloadNode,
          }},
        }};

        root.querySelector = (selector) => root._queryMap[selector] || null;
        root.querySelectorAll = () => kpiNodes;
        root._queryMap = root._queryMap || {{}};
        root._queryMap["[data-dashboard-filters-form]"] = form;
        root._queryMap["[data-dashboard-last-update]"] = makeElement();
        root._queryMap["[data-dashboard-checklist-pending]"] = makeElement();
        root._queryMap["[data-dashboard-checklist-overdue]"] = makeElement();
        root._queryMap["[data-dashboard-financial-alert-count]"] = makeElement();
        root._queryMap["[data-dashboard-state-distribution]"] = makeElement();
        root._queryMap["[data-dashboard-benefit-bars]"] = makeElement();
        root._queryMap["[data-dashboard-alerts='operational']"] = makeElement();
        root._queryMap["[data-dashboard-alerts='financial']"] = makeElement();
        root._queryMap["[data-dashboard-ranking='best_roi']"] = makeElement();
        root._queryMap["[data-dashboard-ranking='worst_roi']"] = makeElement();
        root._queryMap["[data-dashboard-ranking='investment_return']"] = makeElement();
        root._queryMap["#dashboardProyecto"] = fields.proyecto_id;
        root._queryMap["#dashboardError"] = dashboardError;
        root._queryMap["#dashboardStatus"] = dashboardStatus;

        const doc = makeDocument(registry);
        const fetchCalls = [];
        const fetchStub = async (url, options = {{}}) => {{
          fetchCalls.push({{ url, signal: options.signal }});
          if (nextPayload === null) {{
            return makeResponse(initialPayload);
          }}
          return makeResponse(nextPayload);
        }};

        const controller = dashboard.createDashboardController({{
          document: doc,
          window: windowStub,
          fetch: fetchStub,
          Chart: ChartStub,
          initialPayload,
          root,
        }});
        controller.init();
        history.calls.length = 0;

        {scenario}
        """
    )


@pytest.mark.parametrize(
    "scenario_name",
    [
        "update",
        "cancel",
        "error",
    ],
)
def test_dashboard_controller_scenarios(scenario_name):
    initial_payload = _payload()
    next_payload = _payload()
    next_payload["meta"] = {"generated_at": "2026-07-16T12:30:00+02:00"}
    next_payload["kpis"]["capital_en_vigor"] = "3500.00"
    next_payload["kpis"]["beneficio_inversure"] = "250.00"
    next_payload["rankings"]["best_roi"][0]["nombre"] = "Proyecto C"
    next_payload["alerts"]["financial"]["items"].append(
        {
            "severity": "critical",
            "category": "facturas_faltantes",
            "title": "Gastos confirmados sin factura",
            "detail": "2 líneas sin factura",
            "project_id": 22,
        }
    )

    if scenario_name == "update":
        scenario = """
          (async () => {
            const payload = await controller.loadFilters({
              fecha_desde: "2026-07-01",
              fecha_hasta: "2026-07-31",
              proyecto_id: "22",
              estado: "cerrado",
            });
            console.log(JSON.stringify({
              payload,
              fetchUrl: fetchCalls[0].url,
              pushUrl: history.calls.at(-1).url,
              kpi: root.querySelectorAll("[data-dashboard-kpi]")[2].textContent,
              ranking: root.querySelector("[data-dashboard-ranking='best_roi']").innerHTML,
              alerts: root.querySelector("[data-dashboard-alerts='financial']").innerHTML,
              financialCount: root.querySelector("[data-dashboard-financial-alert-count]").textContent,
              projectHtml: root.querySelector("#dashboardProyecto").innerHTML,
              chartCount: ChartStub.instances.length,
              chartLabels: ChartStub.instances.map((chart) => chart.data.labels || []),
            }));
          })().catch((error) => {
            console.error(error);
            process.exit(1);
          });
        """
        result = _run_node(_node_script(initial_payload=initial_payload, next_payload=next_payload, scenario=scenario))

        assert result["fetchUrl"].endswith("fecha_desde=2026-07-01&fecha_hasta=2026-07-31&proyecto_id=22&estado=cerrado")
        assert result["pushUrl"].endswith("fecha_desde=2026-07-01&fecha_hasta=2026-07-31&proyecto_id=22&estado=cerrado")
        assert result["kpi"] == "3.500,00\xa0€"
        assert "Proyecto C" in result["ranking"]
        assert "Gastos confirmados sin factura" in result["alerts"]
        assert result["financialCount"] == "2"
        assert "Proyecto B" in result["projectHtml"]
        assert result["chartCount"] >= 3
        assert any("Jun 2026" in labels for labels in result["chartLabels"])
        return

    if scenario_name == "cancel":
        scenario = """
          const calls = [];
          const abortableFetchStub = (url, options = {}) => {
            const call = { url, signal: options.signal, resolve: null, reject: null };
            const promise = new Promise((resolve, reject) => {
              call.resolve = resolve;
              call.reject = reject;
            });
            if (options.signal) {
              options.signal.addEventListener("abort", () => {
                const error = new Error("Aborted");
                error.name = "AbortError";
                call.reject(error);
              }, { once: true });
            }
            calls.push(call);
            return promise;
          };

          const controller2 = dashboard.createDashboardController({
            document: doc,
            window: windowStub,
            fetch: abortableFetchStub,
            Chart: ChartStub,
            initialPayload,
            root,
          });
          controller2.init();
          history.calls.length = 0;

          const first = controller2.loadFilters({ fecha_desde: "2026-07-01" });
          const second = controller2.loadFilters({ fecha_desde: "2026-07-02" });
          calls[1].resolve(makeResponse(nextPayload));

          Promise.allSettled([first, second]).then(() => {
            console.log(JSON.stringify({
              firstAborted: calls[0].signal.aborted,
              secondUrl: calls[1].url,
              finalCapital: root.querySelectorAll("[data-dashboard-kpi]")[2].textContent,
              historyMode: history.calls.at(-1).method,
              historyUrl: history.calls.at(-1).url,
            }));
          }).catch((error) => {
            console.error(error);
            process.exit(1);
          });
        """
        result = _run_node(_node_script(initial_payload=initial_payload, next_payload=next_payload, scenario=scenario))

        assert result["firstAborted"] is True
        assert result["secondUrl"].endswith("fecha_desde=2026-07-02")
        assert result["finalCapital"] == "3.500,00\xa0€"
        assert result["historyMode"] == "push"
        assert result["historyUrl"].endswith("fecha_desde=2026-07-02")
        return

    scenario = """
      const controller3 = dashboard.createDashboardController({
        document: doc,
        window: windowStub,
        fetch: async () => { throw new Error("network down"); },
        Chart: ChartStub,
        initialPayload,
        root,
      });
      controller3.init();
      history.calls.length = 0;
      controller3.loadFilters({ estado: "cerrado" }).then(() => {
        console.log(JSON.stringify({
          errorVisible: !root.querySelector("#dashboardError").classList.contains("d-none"),
          errorText: root.querySelector("#dashboardError").textContent,
          capital: root.querySelectorAll("[data-dashboard-kpi]")[2].textContent,
          historyCalls: history.calls.length,
        }));
      }).catch((error) => {
        console.error(error);
        process.exit(1);
      });
    """
    result = _run_node(_node_script(initial_payload=initial_payload, next_payload=None, scenario=scenario))

    assert result["errorVisible"] is True
    assert "No se pudieron actualizar" in result["errorText"]
    assert result["capital"] == "1.000,00\xa0€"
    assert result["historyCalls"] == 0
