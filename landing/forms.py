from django import forms

from .models import Hero, Seccion, Noticia, MediaAsset


class HeroForm(forms.ModelForm):
    class Meta:
        model = Hero
        fields = [
            "etiqueta",
            "titulo",
            "subtitulo",
            "cta_texto",
            "cta_url",
            "fondo_color",
            "fondo_imagen",
            "imagen",
            "panel_titulo",
            "panel_texto",
            "panel_footer",
            "meta_1_valor",
            "meta_1_texto",
            "meta_2_valor",
            "meta_2_texto",
            "meta_3_valor",
            "meta_3_texto",
            "activo",
        ]


class SeccionForm(forms.ModelForm):
    class Meta:
        model = Seccion
        fields = ["titulo", "texto", "icono", "imagen", "orden", "activo"]


class NoticiaForm(forms.ModelForm):
    class Meta:
        model = Noticia
        fields = [
            "titulo",
            "extracto",
            "cuerpo",
            "imagen",
            "autor",
            "fecha_publicacion",
            "estado",
        ]


class MediaAssetForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ["titulo", "archivo", "categoria", "alt_texto"]
