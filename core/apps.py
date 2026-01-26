from django.apps import AppConfig


def _register_auditlog():
    from auditlog.registry import auditlog
    from . import models

    auditlog.register(models.Estudio)
    auditlog.register(models.EstudioSnapshot)
    auditlog.register(models.Proyecto)
    auditlog.register(models.ProyectoSnapshot)
    auditlog.register(models.PresupuestoProyecto)
    auditlog.register(models.GastoProyecto)
    auditlog.register(models.FacturaGasto)
    auditlog.register(models.IngresoProyecto)
    auditlog.register(models.ChecklistItem)
    auditlog.register(models.Cliente)
    auditlog.register(models.Participacion)
    auditlog.register(models.InversorPerfil)
    auditlog.register(models.SolicitudParticipacion)
    auditlog.register(models.ComunicacionInversor)
    auditlog.register(models.DocumentoProyecto)
    auditlog.register(models.DocumentoInversor)
    auditlog.register(models.Simulacion)
    auditlog.register(models.GastosProyectoEstimacion)
    auditlog.register(models.DatosEconomicosProyecto)
    auditlog.register(models.MovimientoEconomicoProyecto)
    auditlog.register(models.MovimientoProyecto)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        _register_auditlog()
