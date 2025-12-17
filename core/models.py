from django.db import models

class Operacion(models.Model):
    nombre = models.CharField(max_length=255, blank=True)
    precio_compra = models.FloatField(default=0)
    precio_venta = models.FloatField(default=0)
    inversion_total = models.FloatField(default=0)
    beneficio_bruto = models.FloatField(default=0)
    rentabilidad = models.FloatField(default=0)
    creada = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre or f"Operacion {self.id}"

