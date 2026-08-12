from django.test import TestCase


class PaginasDeError(TestCase):
    """
    Sin estas plantillas, Django sirve su página por defecto: en inglés, sin
    marca y sin salida.
    """

    def test_el_404_usa_la_plantilla_de_marca(self):
        with self.settings(DEBUG=False, ALLOWED_HOSTS=["testserver"]):
            respuesta = self.client.get("/una-pagina-que-no-existe/")
        self.assertEqual(respuesta.status_code, 404)
        self.assertTemplateUsed(respuesta, "404.html")
        contenido = respuesta.content.decode()
        self.assertIn("Esta página no existe", contenido)
        # Lo que hace útil un 404: una salida.
        self.assertIn('href="/"', contenido)

    def test_el_500_no_depende_de_nada(self):
        """
        Django lo pinta con un contexto vacío —sin `request` ni procesadores de
        contexto— así que no puede extender la base ni pedir recursos fuera: si
        algo falla al pintarlo, el visitante ve una página en blanco.
        """
        from django.template.loader import render_to_string

        html = render_to_string("500.html")
        self.assertIn("Inversure Homes", html)
        for prohibido in ("{% extends", "<link", "<script", 'src="'):
            self.assertNotIn(prohibido, html)
