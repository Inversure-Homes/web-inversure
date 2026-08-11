"""
Pruebas de lo que no puede fallar.

No cubren la interfaz: cubren las cuatro cosas que, si se rompen, cuestan
dinero o credibilidad — vender dos veces la misma papeleta, cobrar sin
consentimiento, duplicar un pago y publicar un ganador que no compró.
"""

import datetime
from decimal import Decimal

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
            otros_gastos=Decimal("1300"),
            precio_participacion=Decimal("10"),
            participaciones=5000,
            precio_venta_estimado=Decimal("24000"),
        )

    def test_mide_las_dos_rutas_sobre_el_mismo_inmueble(self):
        a = comparar(self.estudio.como_datos())
        # Entrada = compra + ITP 7 % + otros
        self.assertEqual(a["entrada"]["total"], Decimal("20560.00"))
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
