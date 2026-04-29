from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from core import views as core_views
from core.models import Estudio


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
