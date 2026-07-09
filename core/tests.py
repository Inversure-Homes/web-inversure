import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.test.utils import override_settings

from core import views as core_views
from core.models import Cliente, DatosEconomicosProyecto, Estudio, GastoProyecto, IngresoProyecto, InversorPerfil, Participacion, Proyecto


def _add_session(request):
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()


class SecurityHardeningTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(username="admin", email="admin@example.com", password="pass")

    def test_borrar_estudio_requires_post(self):
        estudio = Estudio.objects.create(nombre="Test", direccion="X", ref_catastral="", datos={})

        req_get = self.factory.get(f"/app/estudios/borrar/{estudio.id}/")
        req_get.user = self.user
        _add_session(req_get)
        res_get = core_views.borrar_estudio(req_get, estudio_id=estudio.id)
        self.assertEqual(res_get.status_code, 405)

        req_post = self.factory.post(
            f"/app/estudios/borrar/{estudio.id}/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        req_post.user = self.user
        _add_session(req_post)
        res_post = core_views.borrar_estudio(req_post, estudio_id=estudio.id)
        self.assertEqual(res_post.status_code, 200)

    def test_convertir_a_proyecto_requires_post(self):
        estudio = Estudio.objects.create(nombre="Test", direccion="X", ref_catastral="", datos={})

        req_get = self.factory.get(f"/app/convertir-a-proyecto/{estudio.id}/")
        req_get.user = self.user
        _add_session(req_get)
        res_get = core_views.convertir_a_proyecto(req_get, estudio_id=estudio.id)
        self.assertEqual(res_get.status_code, 405)

    def test_pdf_message_sanitizer_blocks_dangerous_tags(self):
        raw = '<strong>OK</strong><script>alert(1)</script><img src="https://evil.test/x.png">'
        out = core_views._sanitize_pdf_message_html(raw)
        self.assertIn("<strong>OK</strong>", out)
        self.assertNotIn("<script", out)
        self.assertNotIn("<img", out)

    def test_pdf_message_sanitizer_blocks_javascript_href(self):
        raw = '<a href="javascript:alert(1)">x</a><a href="https://ok.test">y</a>'
        out = core_views._sanitize_pdf_message_html(raw)
        self.assertNotIn("javascript:", out.lower())
        self.assertIn('href="https://ok.test"', out)

    def test_healthz_ok(self):
        res = self.client.get("/healthz/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, b"ok")

    def test_healthz_allowed_in_maintenance_mode(self):
        old = os.environ.get("MAINTENANCE_MODE")
        os.environ["MAINTENANCE_MODE"] = "1"

        def _restore():
            if old is None:
                os.environ.pop("MAINTENANCE_MODE", None)
            else:
                os.environ["MAINTENANCE_MODE"] = old

        self.addCleanup(_restore)

        res = self.client.get("/healthz/")
        self.assertEqual(res.status_code, 200)

    def test_roi_memoria_proyecto_matches_resultado_memoria(self):
        proyecto = Proyecto.objects.create(
            nombre="P",
            estado="comercializacion",
            fecha=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
            meses=4,
        )
        # Gasto de compra duplicado en movimientos + precio_compra en el modelo
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 1),
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 10),
            categoria="legales",
            concepto="Notaría",
            importe=Decimal("2500.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 1),
            tipo="venta",
            concepto="Venta estimada",
            importe=Decimal("130000.00"),
            estado="estimado",
            imputable_inversores=True,
        )
        res = core_views._resultado_desde_memoria(proyecto, {})
        roi_from_res = float(res.get("roi") or 0.0)
        roi_auto = core_views._roi_memoria_proyecto(proyecto)
        self.assertIsNotNone(roi_auto)
        self.assertAlmostEqual(float(roi_auto), roi_from_res, places=6)

    @override_settings(INVERSOR_RETENCION_PCT=0.0, INVERSOR_RETENCION_PCT_F=0.0, INVERSOR_RETENCION_PCT_J=0.0)
    def test_retencion_pct_can_be_overridden(self):
        class _P:
            importe_invertido = Decimal("100.00")
            beneficio_neto_override = None
            beneficio_override_data = {}
            cliente = type("C", (), {"tipo_persona": "F"})()

        part = _P()
        class _Proj:
            extra = {}

        proyecto = _Proj()
        snapshot = {"inversor": {"comision_inversure_pct": 0}}
        resultado_mem = {"beneficio_neto": 1000.0}
        out = core_views._calc_beneficio_inversor(part, proyecto, snapshot, resultado_mem, total_proj=100.0)
        self.assertEqual(out["retencion"], 0.0)

    @override_settings(MEMORIA_BENEFICIO_NETO_DESDE_TRANSMISION=True)
    def test_beneficio_neto_can_be_forced_from_transmision(self):
        proyecto = Proyecto.objects.create(
            nombre="P2",
            estado="comercializacion",
            fecha=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        # gastos confirmados (sin incluir venta)
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 1),
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        # venta + gasto de venta estimado
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 1),
            tipo="venta",
            concepto="Venta estimada",
            importe=Decimal("130000.00"),
            estado="estimado",
            imputable_inversores=True,
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 1),
            categoria="venta",
            concepto="Inmobiliaria",
            importe=Decimal("3900.00"),
            estado="estimado",
            imputable_inversores=True,
        )
        res = core_views._resultado_desde_memoria(proyecto, {})
        val_adq = float(res.get("valor_adquisicion") or 0.0)
        val_trans = float(res.get("valor_transmision") or 0.0)
        benef = float(res.get("beneficio_neto") or 0.0)
        self.assertAlmostEqual(benef, val_trans - val_adq, places=6)

    @override_settings(INVERSOR_RETENCION_PCT=19.0)
    def test_no_retencion_on_losses_and_total_includes_capital(self):
        class _Part:
            importe_invertido = Decimal("1000.00")
            beneficio_neto_override = None
            beneficio_override_data = {}
            cliente = type("C", (), {"tipo_persona": "F"})()

        class _Proj:
            extra = {}

        part = _Part()
        proyecto = _Proj()
        snapshot = {"inversor": {"comision_inversure_pct": 10}}
        # pérdida en operación
        resultado_mem = {"beneficio_neto": -500.0}
        out = core_views._calc_beneficio_inversor(part, proyecto, snapshot, resultado_mem, total_proj=1000.0)
        self.assertEqual(out["comision_eur"], 0.0)
        self.assertEqual(out["retencion"], 0.0)
        # total a percibir = capital + neto_beneficio (negativo)
        self.assertAlmostEqual(out["total_a_percibir"], 500.0, places=6)

    def test_closed_project_counts_anticipo_as_venta(self):
        proyecto = Proyecto.objects.create(
            nombre="P3",
            estado="cerrado",
            fecha=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 1),
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 10),
            categoria="legales",
            concepto="Notaría",
            importe=Decimal("2500.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 1),
            tipo="anticipo",
            concepto="Cobro anticipo",
            importe=Decimal("109000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        res = core_views._resultado_desde_memoria(proyecto, {})
        self.assertAlmostEqual(float(res.get("valor_transmision") or 0.0), 109000.0, places=6)
        self.assertAlmostEqual(
            float(res.get("beneficio_neto") or 0.0),
            float((res.get("valor_transmision") or 0.0) - (res.get("valor_adquisicion") or 0.0)),
            places=6,
        )

    def test_closed_project_falls_back_to_total_ingresos_as_venta(self):
        proyecto = Proyecto.objects.create(
            nombre="P4",
            estado="cerrado",
            fecha=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 1),
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 1),
            tipo="otro",
            concepto="Ingreso sin tipar como venta",
            importe=Decimal("109000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        res = core_views._resultado_desde_memoria(proyecto, {})
        self.assertAlmostEqual(float(res.get("valor_transmision") or 0.0), 109000.0, places=6)

    def test_metricas_desde_estudio_never_negative_commission(self):
        estudio = Estudio.objects.create(
            nombre="E",
            direccion="X",
            ref_catastral="",
            datos={"beneficio": -10000, "inversor": {"comision_inversure_pct": 10}},
        )
        out = core_views._metricas_desde_estudio(estudio)
        inversor = out.get("inversor") or {}
        self.assertEqual(float(inversor.get("comision_inversure_eur") or 0.0), 0.0)

    def test_metricas_estudio_clamps_negative_commission_and_recomputes(self):
        estudio = Estudio.objects.create(
            nombre="E",
            direccion="X",
            ref_catastral="",
            datos={
                "valor_adquisicion": 100000,
                "valor_transmision": 120000,
                "beneficio_estimado": 20000,
                "comision_inversure_pct": 10,
                "comision_inversure_eur": -999,  # inválida: nunca debería ser negativa
            },
        )
        out = core_views._metricas_desde_estudio(estudio)
        inv = out.get("inversor", {}) if isinstance(out.get("inversor"), dict) else {}
        self.assertGreaterEqual(float(inv.get("comision_inversure_eur") or 0.0), 0.0)
        self.assertAlmostEqual(float(inv.get("comision_inversure_eur") or 0.0), 2000.0, places=6)
        self.assertAlmostEqual(float(inv.get("beneficio_neto_inversor") or 0.0), 18000.0, places=6)

    def test_resultado_memoria_can_filter_non_imputable_items(self):
        proyecto = Proyecto.objects.create(
            nombre="P5",
            estado="cerrado",
            fecha=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 1),
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 15),
            categoria="otros",
            concepto="Gasto no imputable",
            importe=Decimal("15000.00"),
            estado="confirmado",
            imputable_inversores=False,
        )
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 1),
            tipo="venta",
            concepto="Venta",
            importe=Decimal("120000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 2),
            tipo="otro",
            concepto="Ingreso no imputable",
            importe=Decimal("5000.00"),
            estado="confirmado",
            imputable_inversores=False,
        )

        full_result = core_views._resultado_desde_memoria(proyecto, {})
        imputable_result = core_views._resultado_desde_memoria(
            proyecto,
            {},
            only_imputable_inversores=True,
        )

        self.assertGreater(float(full_result.get("beneficio_neto") or 0.0), 0.0)
        self.assertAlmostEqual(float(imputable_result.get("valor_transmision") or 0.0), 120000.0, places=6)
        self.assertAlmostEqual(float(imputable_result.get("beneficio_neto") or 0.0), 20000.0, places=6)

    @override_settings(INVERSOR_RETENCION_PCT=19.0, INVERSOR_RETENCION_PCT_F=19.0)
    def test_build_comunicacion_context_includes_liquidacion_fields(self):
        proyecto = Proyecto.objects.create(
            nombre="P6",
            estado="cerrado",
            fecha=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        cliente = Cliente.objects.create(
            nombre="Cliente cierre",
            dni_cif="X-TEST-0001",
            email="cliente-cierre@example.com",
            telefono="600000000",
        )
        participacion = Participacion.objects.create(
            proyecto=proyecto,
            cliente=cliente,
            importe_invertido=Decimal("50000.00"),
            estado="confirmada",
        )
        ctx = core_views._build_comunicacion_context(
            proyecto,
            participacion,
            {},
            {"beneficio_neto": 40000.0, "valor_adquisicion": 100000.0, "valor_transmision": 140000.0, "roi": 40.0},
            total_proj=100000.0,
        )
        self.assertEqual(ctx["capital_invertido"], "50.000,00 €")
        self.assertEqual(ctx["beneficio_bruto_inversor"], "20.000,00 €")
        self.assertEqual(ctx["retencion_pct_aplicada"], "19,00 %")
        self.assertEqual(ctx["beneficio_neto_liquidacion"], "16.200,00 €")
        self.assertEqual(ctx["total_a_percibir"], "66.200,00 €")

    @override_settings(INVERSOR_RETENCION_PCT=19.0, INVERSOR_RETENCION_PCT_F=19.0)
    def test_build_comunicacion_context_uses_certificate_dates(self):
        proyecto = Proyecto.objects.create(
            nombre="P6-dates",
            estado="cerrado",
            fecha=None,
            fecha_compra=None,
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        DatosEconomicosProyecto.objects.create(
            proyecto=proyecto,
            fecha_venta_real=date(2026, 6, 1),
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 1, 3),
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        cliente = Cliente.objects.create(
            nombre="Cliente fechas",
            dni_cif="X-TEST-0010",
            email="cliente-fechas@example.com",
            telefono="600000010",
        )
        participacion = Participacion.objects.create(
            proyecto=proyecto,
            cliente=cliente,
            importe_invertido=Decimal("50000.00"),
            estado="confirmada",
        )
        ctx = core_views._build_comunicacion_context(
            proyecto,
            participacion,
            {},
            {"beneficio_neto": 40000.0, "valor_adquisicion": 100000.0, "valor_transmision": 140000.0, "roi": 40.0},
            total_proj=100000.0,
        )
        self.assertEqual(ctx["fecha_compra"], "03/01/2026")
        self.assertEqual(ctx["fecha_transmision"], "01/06/2026")

    def test_normalize_match_text_handles_liquidacion_with_accent(self):
        self.assertEqual(core_views._normalize_match_text("Liquidación final de la operación"), "liquidacion final de la operacion")

    def test_certificado_retenciones_template_is_available(self):
        templates = core_views._comunicacion_templates()
        self.assertIn("certificado_retenciones", templates)
        self.assertEqual(templates["certificado_retenciones"]["label"], "Certificado retenciones")
        self.assertTrue(core_views._template_requires_settlement("certificado_retenciones"))
        self.assertEqual(
            core_views._pdf_document_kind_from_template("certificado_retenciones", "Certificado de retenciones"),
            "retenciones",
        )
        self.assertEqual(
            core_views._pdf_document_kind_from_template(None, "Liquidación final de la operación"),
            "liquidacion",
        )
        legal_text = (
            "Se advierte al inversor que las cantidades expresadas en el certificados, podrán ser eventualmente "
            "modificadada, en el caso de que posterior a  la liquidación practicada, se devenguen gastos no "
            "previstos ni previsibles de la emisión de la misma y que deberán ser asumidos en las mismas "
            "previsiones en que se ha participado en la inversión.En el caso de que esto se produzca se emitirá "
            "una liquidación complementaria"
        )
        self.assertIn(legal_text, templates["cierre"]["mensaje"])
        self.assertIn(legal_text, templates["certificado_retenciones"]["mensaje"])
        self.assertNotIn("Los datos son orientativos", templates["cierre"]["mensaje"])
        self.assertNotIn("Los datos son orientativos", templates["certificado_retenciones"]["mensaje"])

    def test_build_carta_pdf_uses_certificate_template_for_retenciones(self):
        cliente = Cliente.objects.create(
            nombre="Cliente retenciones",
            dni_cif="X-TEST-0000",
            email="retenciones@example.com",
            telefono="600000099",
        )
        perfil = InversorPerfil.objects.create(cliente=cliente)
        proyecto = Proyecto.objects.create(
            nombre="Proyecto retenciones",
            estado="cerrado",
            fecha=None,
            fecha_compra=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        DatosEconomicosProyecto.objects.create(
            proyecto=proyecto,
            fecha_venta_real=date(2026, 6, 1),
        )
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 1),
            tipo="venta",
            concepto="Venta final",
            importe=Decimal("140000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        Participacion.objects.create(
            proyecto=proyecto,
            cliente=cliente,
            importe_invertido=Decimal("25000.00"),
            estado="confirmada",
        )
        request = RequestFactory().get("/")

        class _FakeHTML:
            def __init__(self, string, base_url=None):
                self.string = string
                self.base_url = base_url

            def write_pdf(self):
                return b"pdf-bytes"

        fake_weasyprint = SimpleNamespace(HTML=_FakeHTML)
        with patch.dict("sys.modules", {"weasyprint": fake_weasyprint}):
            with patch.object(core_views, "render_to_string", return_value="<html></html>") as mock_render:
                pdf, error = core_views._build_carta_pdf_with_error(
                    request,
                    "Certificado de retenciones final",
                    "Mensaje de prueba",
                    perfil,
                    proyecto,
                    template_key="certificado_retenciones",
                )

        self.assertIsNone(error)
        self.assertEqual(pdf, b"pdf-bytes")
        self.assertEqual(mock_render.call_args.args[0], "core/pdf_certificado_retenciones.html")
        render_ctx = mock_render.call_args.args[1]
        self.assertEqual(render_ctx["fecha_compra"], "01/01/2026")
        self.assertEqual(render_ctx["fecha_transmision"], "01/06/2026")

    def test_proyecto_listo_para_liquidacion_requires_closed_state_and_confirmed_income(self):
        proyecto = Proyecto.objects.create(
            nombre="P7",
            estado="comercializacion",
            fecha=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        cliente = Cliente.objects.create(
            nombre="Cliente liquidacion",
            dni_cif="X-TEST-0002",
            email="cliente-liquidacion@example.com",
            telefono="600000001",
        )
        Participacion.objects.create(
            proyecto=proyecto,
            cliente=cliente,
            importe_invertido=Decimal("30000.00"),
            estado="confirmada",
        )
        ok, error = core_views._proyecto_listo_para_liquidacion(proyecto)
        self.assertFalse(ok)
        self.assertIn("vendidos o cerrados", error)

        proyecto.estado = "cerrado"
        proyecto.save(update_fields=["estado"])
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 1),
            tipo="venta",
            concepto="Venta no imputable",
            importe=Decimal("130000.00"),
            estado="confirmado",
            imputable_inversores=False,
        )
        ok, error = core_views._proyecto_listo_para_liquidacion(proyecto)
        self.assertFalse(ok)
        self.assertIn("imputables al inversor", error)

        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=date(2026, 6, 2),
            tipo="venta",
            concepto="Venta final",
            importe=Decimal("130000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        ok, error = core_views._proyecto_listo_para_liquidacion(proyecto)
        self.assertTrue(ok)
        self.assertIsNone(error)

    @override_settings(INVERSOR_RETENCION_PCT=19.0, INVERSOR_RETENCION_PCT_F=19.0)
    def test_inversor_portal_context_separates_liquidacion_from_estimacion(self):
        cliente = Cliente.objects.create(
            nombre="Inversor portal",
            dni_cif="X-TEST-0003",
            email="inversor-portal@example.com",
            telefono="600000002",
        )
        perfil = InversorPerfil.objects.create(cliente=cliente)

        coinversor = Cliente.objects.create(
            nombre="Coinversor",
            dni_cif="X-TEST-0004",
            email="coinversor@example.com",
            telefono="600000003",
        )

        proyecto_cerrado = Proyecto.objects.create(
            nombre="Proyecto cerrado",
            estado="cerrado",
            fecha=date(2026, 1, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        GastoProyecto.objects.create(
            proyecto=proyecto_cerrado,
            fecha=date(2026, 1, 1),
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        IngresoProyecto.objects.create(
            proyecto=proyecto_cerrado,
            fecha=date(2026, 6, 1),
            tipo="venta",
            concepto="Venta final",
            importe=Decimal("140000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        Participacion.objects.create(
            proyecto=proyecto_cerrado,
            cliente=cliente,
            importe_invertido=Decimal("25000.00"),
            estado="confirmada",
        )
        Participacion.objects.create(
            proyecto=proyecto_cerrado,
            cliente=coinversor,
            importe_invertido=Decimal("25000.00"),
            estado="confirmada",
        )

        proyecto_abierto = Proyecto.objects.create(
            nombre="Proyecto abierto",
            estado="comercializacion",
            fecha=date(2026, 2, 1),
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
        )
        GastoProyecto.objects.create(
            proyecto=proyecto_abierto,
            fecha=date(2026, 2, 1),
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        IngresoProyecto.objects.create(
            proyecto=proyecto_abierto,
            fecha=date(2026, 8, 1),
            tipo="venta",
            concepto="Venta estimada",
            importe=Decimal("130000.00"),
            estado="estimado",
            imputable_inversores=True,
        )
        Participacion.objects.create(
            proyecto=proyecto_abierto,
            cliente=cliente,
            importe_invertido=Decimal("25000.00"),
            estado="confirmada",
        )

        ctx = core_views._build_inversor_portal_context(perfil, internal_view=False)

        beneficios = {item["proyecto"].nombre: item for item in ctx["beneficios_por_proyecto"]}
        self.assertEqual(beneficios["Proyecto cerrado"]["calc_mode"], "liquidacion")
        self.assertEqual(beneficios["Proyecto abierto"]["calc_mode"], "estimacion")
        self.assertAlmostEqual(beneficios["Proyecto cerrado"]["participacion_pct"], 50.0, places=6)
        self.assertAlmostEqual(beneficios["Proyecto abierto"]["participacion_pct"], 100.0, places=6)
        self.assertAlmostEqual(ctx["total_beneficio_liquidado"], 20000.0, places=6)
        self.assertAlmostEqual(ctx["total_retencion_liquidada"], 3800.0, places=6)
        self.assertAlmostEqual(ctx["total_neto_liquidado"], 16200.0, places=6)
        self.assertAlmostEqual(ctx["total_a_percibir_liquidado"], 41200.0, places=6)
        self.assertAlmostEqual(ctx["total_beneficio_estimado"], 30000.0, places=6)
        self.assertAlmostEqual(ctx["total_retencion_estimada"], 5700.0, places=6)
        self.assertAlmostEqual(ctx["total_neto_estimado"], 24300.0, places=6)
        self.assertAlmostEqual(ctx["total_a_percibir_estimado"], 49300.0, places=6)
        participaciones_por_nombre = {p.proyecto.nombre: p for p in ctx["participaciones"]}
        self.assertAlmostEqual(float(participaciones_por_nombre["Proyecto cerrado"].porcentaje_participacion), 50.0, places=6)
