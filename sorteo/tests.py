"""
Pruebas de lo que no puede fallar.

No cubren la interfaz: cubren las cuatro cosas que, si se rompen, cuestan
dinero o credibilidad — vender dos veces la misma papeleta, cobrar sin
consentimiento, duplicar un pago y publicar un ganador que no compró.
"""

import datetime
import math
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Proyecto

from .calculadora import Config, escenarios, recomendar, umbral
from .comparador import comparar, desde_proyecto
from .impuestos import Operacion, calcular
from .models import (
    ActaSorteo,
    EstudioRifa,
    Interesado,
    Organizador,
    Papeleta,
    Pedido,
    Sorteo,
)
from .notaria import cerrar_venta, huella, listado_canonico
from .services import (
    NumeroNoVendido,
    PapeletasNoDisponibles,
    SinPapeletasSuficientes,
    confirmar_pago,
    liberar_caducadas,
    registrar_acta,
    reservar_cantidad,
    reservar_numeros,
)

DATOS = {"nombre": "Ana Ruiz", "email": "ana@ejemplo.com"}


class BaseSorteo(TestCase):
    def setUp(self):
        proyecto = Proyecto.objects.create(nombre="Proyecto de prueba")
        organizador = Organizador.objects.create(nombre="Organizador", email="o@ejemplo.com")
        self.sorteo = Sorteo.objects.create(
            proyecto=proyecto,
            organizador=organizador,
            slug="prueba",
            titulo="Sorteo de prueba",
            premio_descripcion="Plaza",
            precio_participacion=Decimal("10"),
            total_participaciones=50,
            fecha_inicio_venta=datetime.date(2026, 9, 1),
            fecha_sorteo=datetime.date(2026, 12, 22),
            inmueble_valor=Decimal("18000"),
            estado=Sorteo.Estado.EN_VENTA,
        )
        self.sorteo.generar_papeletas()


class Reservas(BaseSorteo):
    def test_no_se_vende_dos_veces_la_misma_papeleta(self):
        reservar_numeros(self.sorteo, [7], DATOS)
        with self.assertRaises(PapeletasNoDisponibles) as caso:
            reservar_numeros(self.sorteo, [7, 8], dict(DATOS, email="b@e.com"))
        self.assertEqual(caso.exception.numeros, [7])
        # La transacción se aborta entera: el 8 sigue libre.
        self.assertEqual(
            Papeleta.objects.get(sorteo=self.sorteo, numero=8).estado,
            Papeleta.Estado.LIBRE,
        )

    def test_la_compra_rapida_no_repite_numeros(self):
        p1 = reservar_cantidad(self.sorteo, 20, DATOS)
        p2 = reservar_cantidad(self.sorteo, 20, dict(DATOS, email="b@e.com"))
        self.assertEqual(len(set(p1.numeros) & set(p2.numeros)), 0)

    def test_no_se_puede_reservar_mas_de_lo_que_queda(self):
        reservar_cantidad(self.sorteo, 45, DATOS)
        with self.assertRaises(SinPapeletasSuficientes):
            reservar_cantidad(self.sorteo, 10, dict(DATOS, email="b@e.com"))

    def test_las_reservas_caducadas_vuelven_a_la_venta(self):
        pedido = reservar_numeros(self.sorteo, [3], DATOS)
        Papeleta.objects.filter(pedido=pedido).update(
            reserva_expira=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        )
        liberar_caducadas(self.sorteo)
        self.assertEqual(self.sorteo.disponibles, 50)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Pedido.Estado.CADUCADO)

    def test_el_importe_lo_calcula_el_servidor(self):
        pedido = reservar_cantidad(self.sorteo, 3, DATOS)
        self.assertEqual(pedido.importe, Decimal("30"))

    def test_se_guarda_la_prueba_del_consentimiento(self):
        pedido = reservar_cantidad(self.sorteo, 1, dict(DATOS, ip="1.2.3.4"))
        self.assertEqual(pedido.version_bases, self.sorteo.version_bases)
        self.assertIsNotNone(pedido.acepta_bases_en)
        self.assertEqual(pedido.ip, "1.2.3.4")


class Pagos(BaseSorteo):
    def test_confirmar_dos_veces_no_duplica(self):
        pedido = reservar_cantidad(self.sorteo, 2, DATOS)
        confirmar_pago(pedido.id)
        confirmar_pago(pedido.id)
        self.assertEqual(self.sorteo.vendidas, 2)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_solo_pasan_a_pagadas_las_papeletas_del_pedido(self):
        a = reservar_numeros(self.sorteo, [1], DATOS)
        reservar_numeros(self.sorteo, [2], dict(DATOS, email="b@e.com"))
        confirmar_pago(a.id)
        self.assertEqual(
            Papeleta.objects.get(sorteo=self.sorteo, numero=2).estado,
            Papeleta.Estado.RESERVADA,
        )


class PortalPublico(BaseSorteo):
    def test_sin_consentimiento_no_se_reserva(self):
        r = self.client.post(
            "/sorteo/reservar/",
            data='{"cantidad": 1, "nombre": "Ana", "email": "a@e.com"}',
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_con_consentimiento_se_reserva(self):
        r = self.client.post(
            "/sorteo/reservar/",
            data='{"cantidad": 2, "nombre": "Ana", "email": "a@e.com", "acepta_bases": true, "mayor_edad": true}',
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_no_se_puede_pedir_mas_del_maximo(self):
        r = self.client.post(
            "/sorteo/reservar/",
            data='{"cantidad": 999, "nombre": "Ana", "email": "a@e.com", "acepta_bases": true, "mayor_edad": true}',
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)


class Acta(BaseSorteo):
    def test_rechaza_un_numero_no_vendido(self):
        confirmar_pago(reservar_numeros(self.sorteo, [5], DATOS).id)
        with self.assertRaises(NumeroNoVendido):
            registrar_acta(self.sorteo, 6, "2026/1", datetime.date(2026, 12, 22))
        self.assertFalse(ActaSorteo.objects.exists())

    def test_acepta_un_numero_vendido_y_publica(self):
        pedido = reservar_numeros(self.sorteo, [5], DATOS)
        confirmar_pago(pedido.id)
        acta = registrar_acta(self.sorteo, 5, "2026/1487", datetime.date(2026, 12, 22))
        self.assertEqual(acta.numero_premiado, 5)
        self.assertEqual(acta.pedido, pedido)
        self.sorteo.refresh_from_db()
        self.assertEqual(self.sorteo.estado, Sorteo.Estado.SORTEADO)

    def test_no_se_registra_dos_veces(self):
        confirmar_pago(reservar_numeros(self.sorteo, [5], DATOS).id)
        registrar_acta(self.sorteo, 5, "2026/1", datetime.date(2026, 12, 22))
        self.sorteo.refresh_from_db()
        registrar_acta(self.sorteo, 5, "2026/2", datetime.date(2026, 12, 22))
        self.assertEqual(ActaSorteo.objects.count(), 1)


class ListadoNotarial(BaseSorteo):
    def test_la_huella_detecta_cualquier_cambio(self):
        confirmar_pago(reservar_numeros(self.sorteo, [1, 2], DATOS).id)
        self.sorteo.refresh_from_db()
        cerrar_venta(self.sorteo)
        self.sorteo.refresh_from_db()

        texto, _ = listado_canonico(self.sorteo)
        self.assertEqual(huella(texto), self.sorteo.hash_listado)

        # Una venta posterior cambia el listado, y la huella deja de cuadrar.
        confirmar_pago(reservar_numeros(self.sorteo, [3], dict(DATOS, email="b@e.com")).id)
        texto2, _ = listado_canonico(self.sorteo)
        self.assertNotEqual(huella(texto2), self.sorteo.hash_listado)

    def test_el_listado_es_estable(self):
        confirmar_pago(reservar_cantidad(self.sorteo, 5, DATOS).id)
        a, _ = listado_canonico(self.sorteo)
        b, _ = listado_canonico(self.sorteo)
        self.assertEqual(a, b)


class ListaDeEspera(BaseSorteo):
    def test_alta_y_baja(self):
        i = Interesado.objects.create(
            sorteo=self.sorteo,
            nombre="Ana",
            email="a@e.com",
            mayor_edad=True,
            acepta_aviso=True,
        )
        self.assertTrue(i.activo)
        r = self.client.get("/sorteo/baja/{}/".format(i.token_baja))
        self.assertEqual(r.status_code, 200)
        i.refresh_from_db()
        self.assertFalse(i.activo)
        self.assertFalse(i.acepta_aviso)


class Calculadora(BaseSorteo):
    def test_el_umbral_nunca_baja_del_tipo_de_la_tasa(self):
        # Sin gastos fijos, el umbral es exactamente la tasa corregida por la
        # comisión: ese es el suelo estructural.
        cfg = Config(precio=10, emitidas=1000, valor_premio=0, tasa_pct=20)
        n = umbral(cfg, 0)
        self.assertGreaterEqual(n / 1000, 0.20)
        self.assertLess(n / 1000, 0.22)

    def test_subir_el_precio_reduce_las_papeletas_a_vender(self):
        cfg = Config(precio=10, emitidas=5000, valor_premio=18000)
        opciones = recomendar(cfg, Decimal("21160"), Decimal("15000"))
        caras = [o for o in opciones if o["precio"] == Decimal("50.00")][0]
        baratas = [o for o in opciones if o["precio"] == Decimal("10.00")][0]
        self.assertLess(caras["umbral"], baratas["umbral"])

    def test_cancelar_no_cuenta_el_inmueble_como_perdida(self):
        cfg = Config(precio=10, emitidas=5000, valor_premio=18000)
        filas = escenarios(cfg, Decimal("21160"))["filas"]
        cancelacion = filas[0]
        # La perdida es mucho menor que el coste total, porque la plaza queda.
        self.assertGreater(cancelacion["resultado"], Decimal("-21160"))
        self.assertLess(cancelacion["resultado"], 0)


class ImpuestoDeCompra(TestCase):
    def test_el_tipo_depende_de_la_comunidad(self):
        self.assertEqual(calcular(100000, "madrid")["importe"], Decimal("6000.00"))
        self.assertEqual(calcular(100000, "cataluna")["importe"], Decimal("10000.00"))

    def test_la_base_es_el_valor_de_referencia_si_es_mayor(self):
        r = calcular(100000, "andalucia", valor_referencia=120000)
        self.assertEqual(r["base"], Decimal("120000"))
        self.assertEqual(r["importe"], Decimal("8400.00"))
        self.assertTrue(r["avisos"])

    def test_el_precio_manda_si_supera_al_valor_de_referencia(self):
        r = calcular(100000, "andalucia", valor_referencia=80000)
        self.assertEqual(r["base"], Decimal("100000"))

    def test_primera_entrega_va_por_iva_mas_ajd(self):
        r = calcular(100000, "madrid", Operacion.IVA)
        self.assertEqual(r["impuesto"], "IVA + AJD")
        # 21 % de IVA + 1,5 % de AJD
        self.assertEqual(r["importe"], Decimal("22500.00"))

    def test_sin_comunidad_no_se_inventa_un_tipo(self):
        r = calcular(100000, "")
        self.assertEqual(r["importe"], Decimal("0"))
        self.assertTrue(r["avisos"])


class TiposReducidos(TestCase):
    PERFIL = {"empresa_inmobiliaria": True, "reventa": True}

    def test_se_ofrecen_pero_no_se_aplican_solos(self):
        r = calcular(200000, "andalucia", perfil=self.PERFIL)
        # Al tipo general, aunque el perfil daría para el reducido.
        self.assertEqual(r["tipo"], Decimal("7"))
        self.assertEqual(r["importe"], Decimal("14000.00"))
        self.assertEqual(len(r["candidatos"]), 1)
        self.assertTrue(any("2 %" in a for a in r["avisos"]))

    def test_al_elegirlo_se_aplica_con_sus_requisitos(self):
        r = calcular(200000, "andalucia", supuesto="reventa_profesional", perfil=self.PERFIL)
        self.assertEqual(r["tipo"], Decimal("2"))
        self.assertEqual(r["importe"], Decimal("4000.00"))
        self.assertTrue(any("existencias" in a for a in r["avisos"]))
        self.assertTrue(any("intereses de demora" in a for a in r["avisos"]))

    def test_el_limite_de_valor_lo_desactiva(self):
        r = calcular(600000, "andalucia", supuesto="reventa_profesional", perfil=self.PERFIL)
        self.assertEqual(r["tipo"], Decimal("7"))
        self.assertTrue(any("supera el límite" in a for a in r["avisos"]))

    def test_sin_perfil_no_se_ofrece(self):
        r = calcular(200000, "andalucia", perfil={"empresa_inmobiliaria": True, "reventa": False})
        self.assertEqual(r["candidatos"], [])

    def test_un_supuesto_inexistente_no_baja_el_tipo(self):
        r = calcular(200000, "madrid", supuesto="joven", perfil=self.PERFIL)
        self.assertEqual(r["tipo"], Decimal("6"))
        self.assertTrue(any("no consta como aplicable" in a for a in r["avisos"]))


class CoberturaDelCatalogo(TestCase):
    PERFIL = {"empresa_inmobiliaria": True, "reventa": True}

    def test_avisa_donde_no_consta_el_supuesto(self):
        r = calcular(200000, "galicia", perfil=self.PERFIL)
        self.assertEqual(r["candidatos"], [])
        self.assertTrue(any("No consta un tipo reducido" in a for a in r["avisos"]))

    def test_avisa_de_la_bonificacion_catalana_suprimida(self):
        r = calcular(200000, "cataluna", perfil=self.PERFIL)
        self.assertEqual(r["tipo"], Decimal("10"))
        self.assertTrue(any("suprimida" in a for a in r["avisos"]))

    def test_los_supuestos_sin_contrastar_lo_dicen(self):
        r = calcular(200000, "aragon", supuesto="reventa_profesional", perfil=self.PERFIL)
        self.assertEqual(r["tipo"], Decimal("2"))
        self.assertTrue(any("sin contrastar" in a for a in r["avisos"]))

    def test_murcia_y_madrid_tienen_el_2_por_ciento(self):
        for comunidad in ("murcia", "madrid"):
            r = calcular(200000, comunidad, supuesto="reventa_profesional", perfil=self.PERFIL)
            self.assertEqual(r["tipo"], Decimal("2"), comunidad)


class ComentariosDePlantilla(TestCase):
    """
    Los comentarios {# #} de Django son de UNA sola línea: si abarcan varias se
    imprimen tal cual en el HTML. Pasó en el pie de la landing y en la ficha de
    proyecto, y se vio en producción, así que queda comprobado en todas las
    apps y no solo en las plantillas del sorteo.
    """

    def test_ninguna_plantilla_imprime_comentarios(self):
        import re
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent
        fallos = []
        for carpeta in (
            "sorteo/templates",
            "landing/templates",
            "core/templates",
            "accounts/templates",
            "cms/templates",
        ):
            directorio = raiz / carpeta
            if not directorio.exists():
                continue
            for ruta in directorio.rglob("*.html"):
                texto = ruta.read_text()
                for m in re.finditer(r"\{#.*?#\}", texto, re.S):
                    if "\n" in m.group(0):
                        fallos.append(str(ruta.relative_to(raiz)))
        self.assertEqual(fallos, [], "Comentarios multilínea con {{# #}}: {}".format(fallos))


class EstudiosDeRifa(TestCase):
    def setUp(self):
        self.proyecto = Proyecto.objects.create(nombre="Plaza en estudio")
        self.estudio = EstudioRifa.objects.create(
            nombre="Plaza 18k a 10 €",
            proyecto=self.proyecto,
            precio_compra=Decimal("18000"),
            comunidad="andalucia",
            otros_gastos=Decimal("0"),
            precio_participacion=Decimal("10"),
            participaciones=5000,
            precio_venta_estimado=Decimal("24000"),
        )

    def test_mide_las_dos_rutas_sobre_el_mismo_inmueble(self):
        a = comparar(self.estudio.como_datos())
        # Entrada = compra + ITP 7 % + el desglose de gastos calculados
        self.assertEqual(
            a["entrada"]["total"],
            Decimal("18000") + Decimal("1260.00") + self.estudio.gastos_totales,
        )
        self.assertEqual(a["venta"]["ingresos"], Decimal("24000.00"))
        self.assertEqual(a["rifa"]["ingresos"], Decimal("50000.00"))
        self.assertGreater(a["rifa"]["beneficio"], a["venta"]["beneficio"])
        self.assertTrue(a["lecturas"])

    def test_subir_el_precio_baja_el_umbral(self):
        barato = comparar(self.estudio.como_datos())
        self.estudio.precio_participacion = Decimal("25")
        self.estudio.participaciones = 2000
        caro = comparar(self.estudio.como_datos())
        self.assertLess(caro["rifa"]["umbral"], barato["rifa"]["umbral"])

    def test_el_tipo_reducido_se_traslada_a_la_entrada(self):
        general = comparar(self.estudio.como_datos())
        self.estudio.supuesto_reducido = "reventa_profesional"
        reducido = comparar(self.estudio.como_datos())
        self.assertLess(reducido["entrada"]["total"], general["entrada"]["total"])

    def test_convertir_exige_proyecto(self):
        suelto = EstudioRifa.objects.create(nombre="Sin proyecto", precio_compra=Decimal("10000"))
        self.assertIsNone(suelto.proyecto)
        self.assertIsNone(suelto.sorteo)


class PrecargaDesdeProyecto(TestCase):
    """
    `desde_proyecto` alimenta el formulario, no al comparador: sus claves son
    las del formulario. Se comprobó porque el precio de venta se perdía por
    llamarse distinto en cada sitio.
    """

    def test_las_claves_son_las_del_formulario(self):
        from .views_estudios import EstudioForm

        proyecto = Proyecto.objects.create(
            nombre="Piso a estudiar",
            precio_compra_inmueble=Decimal("35000"),
            precio_venta_estimado=Decimal("48000"),
            notaria=Decimal("700"),
            meses=8,
        )
        datos = desde_proyecto(proyecto)
        campos = set(EstudioForm().fields)
        self.assertTrue(set(datos).issubset(campos), set(datos) - campos)
        self.assertEqual(datos["precio_venta_estimado"], Decimal("48000"))
        self.assertEqual(datos["otros_gastos"], Decimal("700"))


class Veredicto(TestCase):
    """
    El KPI de decisión mira el umbral, no el beneficio: un margen estupendo que
    exige colocar casi todas las papeletas no es una buena operación.
    """

    BASE = {
        "precio_compra": Decimal("18000"),
        "comunidad": "andalucia",
        "otros_gastos": Decimal("1300"),
        "precio_participacion": Decimal("10"),
        "participaciones": 5000,
        "precio_venta": Decimal("24000"),
        "meses_venta": 6,
        "meses_rifa": 6,
    }

    def test_recomienda_vender_si_la_rifa_no_supera_a_la_venta(self):
        d = comparar(dict(self.BASE, precio_venta=Decimal("60000")))["decision"]
        self.assertEqual(d["texto"], "Vender")

    def test_avisa_cuando_hacen_falta_demasiados_compradores(self):
        d = comparar(dict(self.BASE, participaciones=8000))["decision"]
        self.assertEqual(d["texto"], "Revisar")

    def test_recomienda_rifar_si_bastan_pocos_compradores(self):
        # Menos papeletas y más caras: mismo dinero, mucha menos gente.
        d = comparar(dict(self.BASE, participaciones=1000, precio_participacion=Decimal("50")))["decision"]
        self.assertEqual(d["texto"], "Rifar")

    def test_el_porcentaje_del_umbral_no_decide(self):
        """
        El caso que motivó el cambio: emitir más baja el umbral porcentual un
        punto y multiplica por cinco los compradores. Con el criterio viejo el
        peor escenario salía mejor valorado.
        """
        pocos = comparar(dict(self.BASE, participaciones=1000, precio_participacion=Decimal("50")))
        muchos = comparar(dict(self.BASE, participaciones=5000))
        self.assertLessEqual(muchos["rifa"]["umbral_porcentaje"], pocos["rifa"]["umbral_porcentaje"])
        self.assertGreater(muchos["rifa"]["compradores"], pocos["rifa"]["compradores"])
        self.assertEqual(pocos["decision"]["texto"], "Rifar")
        self.assertEqual(muchos["decision"]["texto"], "Revisar")


class BorrarEstudio(TestCase):
    """
    Se llama a la vista directamente: el middleware de roles del ERP redirige
    al alta de 2FA, así que el cliente de pruebas nunca llegaría a ejecutarla.
    """

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("borrador", "b@e.com", "clave-larga-de-prueba")
        self.estudio = EstudioRifa.objects.create(nombre="Descartable", precio_compra=Decimal("10000"))

    def _peticion(self, metodo):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        req = getattr(RequestFactory(), metodo)("/borrar/")
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req._messages = FallbackStorage(req)
        req.user = self.usuario
        return req

    def test_no_se_borra_con_un_get(self):
        """Un GET que borra lo dispara cualquier precarga del navegador."""
        from .views_estudios import borrar

        r = borrar(self._peticion("get"), pk=self.estudio.pk)
        self.assertEqual(r.status_code, 405)
        self.assertTrue(EstudioRifa.objects.filter(pk=self.estudio.pk).exists())

    def test_se_borra_con_post(self):
        from .views_estudios import borrar

        r = borrar(self._peticion("post"), pk=self.estudio.pk)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(EstudioRifa.objects.filter(pk=self.estudio.pk).exists())

    def test_borrar_el_estudio_no_se_lleva_el_sorteo(self):
        """El estudio es el papel de trabajo; el sorteo tiene vida propia."""
        from .views_estudios import borrar

        proyecto = Proyecto.objects.create(nombre="Con sorteo propio")
        organizador = Organizador.objects.create(nombre="Org", email="o@e.com")
        sorteo = Sorteo.objects.create(
            proyecto=proyecto,
            organizador=organizador,
            slug="con-sorteo-propio",
            titulo="Con sorteo propio",
            premio_descripcion="Plaza",
            precio_participacion=Decimal("10"),
            total_participaciones=100,
            fecha_inicio_venta=datetime.date(2026, 9, 1),
            fecha_sorteo=datetime.date(2026, 12, 22),
        )
        self.estudio.sorteo = sorteo
        self.estudio.save(update_fields=["sorteo"])

        borrar(self._peticion("post"), pk=self.estudio.pk)
        self.assertFalse(EstudioRifa.objects.filter(pk=self.estudio.pk).exists())
        self.assertTrue(Sorteo.objects.filter(pk=sorteo.pk).exists())


class GastosDetallados(TestCase):
    """
    Los gastos de compra dejan de ser una casilla a ojo: notaría y registro
    salen del arancel, y el resto de valores por defecto conocidos. Todo
    editable, porque cuando llega la factura manda la factura.
    """

    def setUp(self):
        self.estudio = EstudioRifa.objects.create(
            nombre="Con gastos", precio_compra=Decimal("18000"), comunidad="andalucia"
        )

    def test_el_arancel_crece_por_tramos(self):
        from . import aranceles

        self.assertLess(aranceles.notaria(18000), aranceles.notaria(350000))
        self.assertLess(aranceles.registro(18000), aranceles.registro(350000))
        # Por debajo del primer tramo se aplica el importe fijo.
        self.assertEqual(aranceles.notaria(1000), aranceles.notaria(5000))

    def test_sin_valor_no_hay_arancel(self):
        from . import aranceles

        self.assertEqual(aranceles.notaria(0), Decimal("0"))
        self.assertEqual(aranceles.registro(None), Decimal("0"))

    def test_se_calculan_solos_y_se_marcan_como_calculados(self):
        desglose = {f["concepto"]: f for f in self.estudio.desglose_gastos()}
        self.assertTrue(desglose["Notaría de la compra"]["calculado"])
        self.assertGreater(desglose["Notaría de la compra"]["importe"], 0)
        self.assertEqual(desglose["Tasa de autorización DGOJ"]["importe"], Decimal("100"))

    def test_un_importe_a_mano_manda_sobre_el_calculo(self):
        calculado = self.estudio.desglose_gastos()[0]["importe"]
        self.estudio.gastos_notaria = Decimal("612.34")
        self.estudio.save(update_fields=["gastos_notaria"])

        fila = self.estudio.desglose_gastos()[0]
        self.assertEqual(fila["importe"], Decimal("612.34"))
        self.assertFalse(fila["calculado"])
        self.assertNotEqual(fila["importe"], calculado)

    def test_el_marketing_entra_en_el_coste(self):
        antes = comparar(self.estudio.como_datos())["entrada"]["total"]
        self.estudio.presupuesto_marketing = Decimal("3000")
        self.estudio.save(update_fields=["presupuesto_marketing"])
        despues = comparar(self.estudio.como_datos())["entrada"]["total"]
        self.assertEqual(despues - antes, Decimal("3000"))


class ComposicionDelUmbral(TestCase):
    """
    El umbral es la cifra que decide la operación, así que tiene que poder
    auditarse partida a partida: costes de adquisición más costes del proceso
    del activo, y de ahí las participaciones mínimas.
    """

    def setUp(self):
        self.estudio = EstudioRifa.objects.create(
            nombre="Umbral",
            precio_compra=Decimal("18000"),
            comunidad="andalucia",
            precio_participacion=Decimal("10"),
            participaciones=5000,
            presupuesto_marketing=Decimal("2000"),
        )
        self.analisis = comparar(self.estudio.como_datos())

    def test_los_dos_bloques_suman_el_coste_de_entrada(self):
        entrada = self.analisis["entrada"]
        self.assertEqual(entrada["adquisicion"] + entrada["proceso"], entrada["total"])
        # El inmueble y su impuesto van en adquisición, no en el proceso.
        self.assertGreater(entrada["adquisicion"], self.estudio.precio_compra)

    def test_el_marketing_cuenta_como_coste_del_proceso(self):
        antes = self.analisis["entrada"]["proceso"]
        self.estudio.presupuesto_marketing = Decimal("5000")
        self.estudio.save(update_fields=["presupuesto_marketing"])
        despues = comparar(self.estudio.como_datos())["entrada"]["proceso"]
        self.assertEqual(despues - antes, Decimal("3000"))

    def test_las_partidas_suman_lo_que_hay_que_cubrir(self):
        detalle = self.analisis["rifa"]["umbral_detalle"]
        self.assertEqual(sum(c["importe"] for c in detalle["conceptos"]), detalle["a_cubrir"])

    def test_la_ficha_pinta_el_desglose(self):
        from django.template.loader import render_to_string

        html = render_to_string("sorteo/erp_estudio.html", {"estudio": self.estudio, "analisis": self.analisis})
        self.assertIn("Participaciones mínimas a vender", html)
        self.assertIn("Costes de adquisición", html)
        self.assertIn("Costes del proceso del activo", html)

    def test_el_umbral_es_lo_a_cubrir_entre_el_neto_por_papeleta(self):
        detalle = self.analisis["rifa"]["umbral_detalle"]
        esperado = math.ceil(detalle["a_cubrir"] / detalle["neto_papeleta"])
        self.assertEqual(detalle["umbral"], esperado)
        self.assertEqual(detalle["umbral"], self.analisis["rifa"]["umbral"])


class FormularioDelEstudio(TestCase):
    """
    El reparto de campos por secciones es la clase de cosa que falla en
    silencio: un campo que no está en ninguna sección desaparece de la pantalla
    sin dar error, y con el `{% if campo.name in "a,b,c" %}` de Django —que
    compara subcadenas— `gastos_notaria` salía además duplicado dentro de
    `gastos_notaria_sorteo`. Aquí se comprueban las dos cosas.
    """

    def _form_y_secciones(self):
        from .views_estudios import EstudioForm, secciones

        form = EstudioForm()
        return form, secciones(form)

    def test_cada_campo_sale_una_vez_y_solo_una(self):
        form, repartidos = self._form_y_secciones()
        nombres = [campo.name for seccion in repartidos for grupo in seccion["grupos"] for campo in grupo["campos"]]

        repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
        self.assertEqual(repetidos, [], "campos duplicados en el formulario: {}".format(repetidos))

        faltan = sorted(set(form.fields) - set(nombres))
        self.assertEqual(faltan, [], "campos que no se pintan: {}".format(faltan))

    def test_un_campo_sin_seccion_no_desaparece(self):
        from django import forms

        from .views_estudios import EstudioForm, secciones

        form = EstudioForm()
        form.fields["inventado"] = forms.CharField(required=False)
        nombres = [
            campo.name for seccion in secciones(form) for grupo in seccion["grupos"] for campo in grupo["campos"]
        ]
        self.assertIn("inventado", nombres)

    def test_la_plantilla_pinta_todos_los_campos(self):
        from django.template.loader import render_to_string

        form, repartidos = self._form_y_secciones()
        html = render_to_string(
            "sorteo/erp_estudio_form.html",
            {"form": form, "secciones": repartidos, "titulo": "Nuevo estudio"},
        )
        for nombre in form.fields:
            self.assertEqual(
                html.count('name="{}"'.format(nombre)), 1, "«{}» no sale exactamente una vez".format(nombre)
            )


class InformeDeRentabilidad(TestCase):
    """
    El informe en PDF del estudio.

    Se comprueba sobre el HTML —que es lo que WeasyPrint recibe— porque la
    biblioteca no arranca en el entorno de pruebas: le faltan pango y cairo.
    Lo que importa aquí es que el documento lleve las cifras y que no dependa
    de nada externo, no que WeasyPrint sepa dibujar un PDF.
    """

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("informe", "i@e.com", "clave-larga-de-prueba")
        self.estudio = EstudioRifa.objects.create(
            nombre="Plaza 18k",
            precio_compra=Decimal("18000"),
            comunidad="andalucia",
            precio_participacion=Decimal("10"),
            participaciones=5000,
        )

    def _peticion(self, ruta="/informe/"):
        from django.test import RequestFactory

        req = RequestFactory().get(ruta)
        req.user = self.usuario
        return req

    def _html(self):
        from .views_estudios import informe

        return informe(self._peticion("/informe/?html=1"), pk=self.estudio.pk).content.decode()

    def test_lleva_el_umbral_y_su_desglose(self):
        html = self._html()
        analisis = comparar(self.estudio.como_datos())
        self.assertIn("Participaciones mínimas a vender", html)
        self.assertIn("Costes de adquisición", html)
        self.assertIn("Costes del proceso del activo", html)
        self.assertIn(analisis["rifa"]["umbral_detalle"]["formula"], html)

    def test_compara_las_dos_rutas(self):
        html = self._html()
        self.assertIn("Venta ordinaria", html)
        self.assertIn("Vender o rifar", html)
        self.assertIn(self.estudio.nombre, html)

    def test_no_pide_nada_a_la_red(self):
        """
        Un informe que se archiva tiene que verse igual dentro de diez años.
        Ni hojas de estilo externas, ni fuentes, ni el logo por URL: WeasyPrint
        se quedaría esperando o lo pintaría en blanco.
        """
        html = self._html()
        self.assertNotIn("<link", html)
        self.assertNotIn("<script", html)
        for marca in ('src="http', "src='http", 'src="/static', "@import"):
            self.assertNotIn(marca, html)

    def test_advierte_de_que_las_cifras_se_recalculan(self):
        self.assertIn("se recalculan en cada emisión", self._html())

    def test_genera_el_pdf_y_lo_nombra(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch

        from .views_estudios import informe

        class _FalsoHTML:
            def __init__(self, string, base_url=None):
                self.string = string

            def write_pdf(self):
                return b"%PDF-falso"

        with patch.dict(sys.modules, {"weasyprint": SimpleNamespace(HTML=_FalsoHTML)}):
            r = informe(self._peticion(), pk=self.estudio.pk)

        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertEqual(r.content, b"%PDF-falso")
        self.assertIn("informe-rifa-plaza-18k.pdf", r["Content-Disposition"])

    def test_sin_permisos_no_se_descarga(self):
        from .views_estudios import informe

        req = self._peticion()
        req.user = get_user_model().objects.create_user("mirón", "m@e.com", "clave-larga-de-prueba")
        r = informe(req, pk=self.estudio.pk)
        self.assertEqual(r.status_code, 302)


class ReservasCaducadasEnElErp(BaseSorteo):
    """
    La ficha interna cuenta lo mismo que la web pública.

    La portada libera las reservas caducadas antes de contar; el ERP no lo
    hacía, así que enseñaba menos participaciones disponibles de las que había
    —siempre a peor— hasta que alguien visitaba la web. Con esto no hace falta
    un proceso programado solo para esto.
    """

    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser("erp", "e@e.com", "clave-larga-de-prueba")
        pedido = reservar_numeros(self.sorteo, [1, 2, 3], DATOS)
        Papeleta.objects.filter(pedido=pedido).update(
            reserva_expira=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        )

    def _abrir_ficha(self):
        from django.test import RequestFactory

        from .views_erp import detalle

        peticion = RequestFactory().get("/ficha/")
        peticion.user = self.usuario
        return detalle(peticion, pk=self.sorteo.pk)

    def test_abrir_la_ficha_devuelve_las_caducadas_a_la_venta(self):
        self.assertEqual(self.sorteo.disponibles, 47)
        self.assertEqual(self._abrir_ficha().status_code, 200)
        self.assertEqual(self.sorteo.disponibles, 50)
        self.assertEqual(self.sorteo.reservadas, 0)

    def test_no_toca_las_reservas_vivas(self):
        reservar_numeros(self.sorteo, [10], dict(DATOS, email="b@e.com"))
        self._abrir_ficha()
        self.assertEqual(
            Papeleta.objects.get(sorteo=self.sorteo, numero=10).estado,
            Papeleta.Estado.RESERVADA,
        )
