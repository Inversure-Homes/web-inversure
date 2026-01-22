from django.contrib import admin

from .models import Hero, LandingLead, MediaAsset, Noticia, Seccion


@admin.register(LandingLead)
class LandingLeadAdmin(admin.ModelAdmin):
    list_display = ("tipo", "nombre", "email", "telefono", "ubicacion", "creado")
    list_filter = ("tipo", "creado")
    search_fields = ("nombre", "email", "telefono", "ubicacion", "mensaje")


admin.site.register(Hero)
admin.site.register(Seccion)
admin.site.register(Noticia)
admin.site.register(MediaAsset)
