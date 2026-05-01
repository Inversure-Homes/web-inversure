import os
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.test.utils import override_settings

from core import views as core_views
from core.models import Estudio, Proyecto, GastoProyecto, IngresoProyecto


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
