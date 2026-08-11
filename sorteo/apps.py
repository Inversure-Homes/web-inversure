from django.apps import AppConfig


class SorteoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sorteo"
    verbose_name = "Sorteos"

    def ready(self):
        """
        Traza de auditoría sobre lo que no puede cambiarse sin dejar rastro.

        Un pedido es la prueba del consentimiento y un apunte contable; el acta
        y el sello del listado son lo que sostiene el sorteo ante un
        participante que pregunte. auditlog ya está en el proyecto.
        """
        from auditlog.registry import auditlog

        from .models import ActaSorteo, EstudioRifa, Papeleta, Pedido, Sorteo

        for modelo in (Sorteo, Pedido, Papeleta, ActaSorteo, EstudioRifa):
            auditlog.register(modelo)
