from django.urls import resolve, reverse


def test_primary_urls_resolve():
    assert resolve(reverse("landing:home")).view_name == "landing:home"
    assert resolve(reverse("landing:noticias_list")).view_name == "landing:noticias_list"
    assert resolve(reverse("accounts:login")).view_name == "accounts:login"
    assert resolve(reverse("core:home")).view_name == "core:home"
    assert resolve("/app/estudios/pdf/1/").view_name == "core:pdf_estudio_preview"
    assert resolve("/app/proyectos/1/memoria/pdf/").view_name == "core:pdf_memoria_economica"
    assert resolve("/healthz/").view_name == "healthz"
