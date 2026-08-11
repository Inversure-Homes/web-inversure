"""
Lógica de negocio del sorteo. Las vistas no tocan la base de datos: llaman aquí.
"""

import secrets
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from .models import ActaSorteo, Papeleta, Pedido, Sorteo


class ErrorSorteo(Exception):
    """Errores de negocio que la vista puede enseñar al usuario tal cual."""


class PapeletasNoDisponibles(ErrorSorteo):
    def __init__(self, numeros):
        self.numeros = numeros
        super().__init__(
            "Los números {} acaban de ser comprados por otra persona. Elige otros.".format(
                ", ".join(str(n) for n in numeros)
            )
        )


class SinPapeletasSuficientes(ErrorSorteo):
    def __init__(self, disponibles):
        self.disponibles = disponibles
        super().__init__(
            "Solo quedan {} participaciones disponibles.".format(disponibles)
            if disponibles
            else "Se han agotado las participaciones."
        )


class NumeroNoVendido(ErrorSorteo):
    def __init__(self, numero):
        self.numero = numero
        super().__init__(
            "La participación {} no consta como vendida. Revisa el acta antes "
            "de registrarla: el notario extrae entre las vendidas.".format(numero)
        )


def _bloqueadas(qs):
    """
    Bloquea las filas para que dos compradores simultáneos no se lleven la
    misma papeleta.

    `skip_locked` hace que el segundo comprador no espere: se salta las filas
    que otro está reservando y se lleva otras distintas. Es la diferencia entre
    una cola y dos ventas en paralelo, y en un pico de tráfico se nota.

    SQLite (desarrollo) no soporta SELECT FOR UPDATE, pero serializa las
    escrituras con un lock de base de datos, así que dentro de la transacción
    el resultado es igual de correcto.
    """
    if connection.features.has_select_for_update:
        return qs.select_for_update(skip_locked=True)
    return qs


def _crear_pedido(sorteo, papeletas, datos, ahora):
    pedido = Pedido.objects.create(
        sorteo=sorteo,
        nombre=datos["nombre"],
        email=datos["email"],
        telefono=datos.get("telefono", ""),
        importe=sorteo.precio_participacion * len(papeletas),
        codigo=secrets.token_hex(4).upper(),
        version_bases=sorteo.version_bases,
        acepta_bases_en=ahora,
        ip=datos.get("ip"),
    )
    expira = ahora + timedelta(minutes=sorteo.reserva_minutos)
    Papeleta.objects.filter(pk__in=[p.pk for p in papeletas]).update(
        estado=Papeleta.Estado.RESERVADA, reserva_expira=expira, pedido=pedido
    )
    return pedido


@transaction.atomic
def reservar_cantidad(sorteo, cantidad, datos):
    """Reserva N papeletas al azar. Es la vía principal de compra."""
    liberar_caducadas(sorteo)
    ahora = timezone.now()

    libres = list(_bloqueadas(sorteo.papeletas.filter(estado=Papeleta.Estado.LIBRE).order_by("?"))[:cantidad])
    if len(libres) < cantidad:
        raise SinPapeletasSuficientes(len(libres))

    return _crear_pedido(sorteo, libres, datos, ahora)


@transaction.atomic
def reservar_numeros(sorteo, numeros, datos):
    """Reserva unos números concretos elegidos por el comprador."""
    liberar_caducadas(sorteo)
    ahora = timezone.now()

    disponibles = list(_bloqueadas(sorteo.papeletas.filter(numero__in=numeros, estado=Papeleta.Estado.LIBRE)))
    encontrados = {p.numero for p in disponibles}
    faltan = sorted(set(numeros) - encontrados)
    if faltan:
        raise PapeletasNoDisponibles(faltan)

    return _crear_pedido(sorteo, disponibles, datos, ahora)


@transaction.atomic
def registrar_venta_manual(sorteo, cantidad, datos, numeros=None, usuario=None):
    """
    Alta de una venta presencial (efectivo, transferencia, talonario).

    Entra en el sorteo exactamente igual que una compra web —el notario extrae
    entre todas las pagadas— pero queda marcada con `origen='manual'` para
    poder conciliarla aparte de los cobros de la pasarela.
    """
    if numeros:
        pedido = reservar_numeros(sorteo, numeros, datos)
    else:
        pedido = reservar_cantidad(sorteo, cantidad, datos)

    Pedido.objects.filter(pk=pedido.pk).update(
        origen=Pedido.Origen.MANUAL,
        medio_pago=datos.get("medio_pago", ""),
        registrado_por=usuario,
    )
    return confirmar_pago(pedido.id)


def liberar_caducadas(sorteo=None):
    """
    Devuelve al estado libre las reservas expiradas. Idempotente y barato.

    Se llama al reservar y desde el comando `liberar_reservas`, para que las
    papeletas no queden bloqueadas si la web se queda sin tráfico.
    """
    ahora = timezone.now()

    papeletas = Papeleta.objects.filter(estado=Papeleta.Estado.RESERVADA, reserva_expira__lt=ahora)
    pedidos = Pedido.objects.filter(estado=Pedido.Estado.PENDIENTE)
    if sorteo is not None:
        papeletas = papeletas.filter(sorteo=sorteo)
        pedidos = pedidos.filter(sorteo=sorteo)

    liberadas = papeletas.update(estado=Papeleta.Estado.LIBRE, reserva_expira=None, pedido=None)
    # Un pedido pendiente que se ha quedado sin papeletas ya no puede pagarse.
    # Los recién creados no corren peligro: hasta que la transacción que los
    # crea no confirma, ninguna otra conexión los ve.
    pedidos.filter(papeletas__isnull=True).update(estado=Pedido.Estado.CADUCADO)
    return liberadas


@transaction.atomic
def confirmar_pago(pedido_id):
    """
    Marca un pedido como pagado. Idempotente: los webhooks se reintentan y
    pueden llegar duplicados, así que llamar dos veces no debe duplicar nada.
    """
    try:
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
    except (Pedido.DoesNotExist, ValueError):
        return None

    if pedido.estado == Pedido.Estado.PAGADO:
        return pedido

    pedido.estado = Pedido.Estado.PAGADO
    pedido.pagado_en = timezone.now()
    pedido.save(update_fields=["estado", "pagado_en"])

    # Se marcan por pedido, no por número: si la reserva caducó y otra persona
    # compró la papeleta, esta consulta no se la quita.
    pedido.papeletas.filter(estado=Papeleta.Estado.RESERVADA).update(estado=Papeleta.Estado.PAGADA, reserva_expira=None)
    return pedido


@transaction.atomic
def registrar_acta(sorteo, numero_premiado, protocolo, fecha, usuario=None):
    """
    Transcribe el acta del sorteo notarial. No sortea nada.

    Rechaza cualquier número que no conste como vendido: es más fácil corregir
    una errata que retirar un ganador ya publicado.
    """
    if hasattr(sorteo, "acta"):
        return sorteo.acta

    papeleta = (
        sorteo.papeletas.filter(numero=numero_premiado, estado=Papeleta.Estado.PAGADA).select_related("pedido").first()
    )
    if papeleta is None:
        raise NumeroNoVendido(numero_premiado)

    acta = ActaSorteo.objects.create(
        sorteo=sorteo,
        numero_premiado=numero_premiado,
        pedido=papeleta.pedido,
        protocolo=protocolo,
        notario=sorteo.notaria_nombre,
        fecha=fecha,
        registrado_por=usuario,
    )
    Sorteo.objects.filter(pk=sorteo.pk).update(estado=Sorteo.Estado.SORTEADO)
    return acta
