from django import forms

from .models import Hero, Seccion, Noticia, MediaAsset


class HeroForm(forms.ModelForm):
    class Meta:
        model = Hero
        fields = ["titulo", "subtitulo", "cta_texto", "cta_url", "imagen", "activo"]


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
