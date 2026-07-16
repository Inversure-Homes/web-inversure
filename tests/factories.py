from decimal import Decimal

import factory
from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import UserAccess
from core.models import Cliente, Estudio, InversorPerfil, Proyecto
from landing.models import Noticia


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Faker("email")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    is_active = True
    is_staff = False
    is_superuser = False

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        raw_password = extracted or "password123"
        self.set_password(raw_password)
        if create:
            self.save(update_fields=["password"])


class UserAccessFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserAccess

    user = factory.SubFactory(UserFactory)
    role = UserAccess.ROLE_DIRECCION
    use_custom_perms = False
    can_simulador = True
    can_estudios = True
    can_proyectos = True
    can_clientes = True
    can_inversores = True
    can_usuarios = True
    can_cms = True
    can_facturas_preview = True


class ClienteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cliente

    tipo_persona = "F"
    nombre = factory.Faker("name")
    dni_cif = factory.Sequence(lambda n: f"X{n:08d}A")
    email = factory.Sequence(lambda n: f"cliente{n}@example.com")
    telefono = factory.Sequence(lambda n: f"600000{n:03d}")
    iban = ""
    observaciones = ""
    fecha_introduccion = factory.LazyFunction(timezone.localdate)
    direccion_postal = ""
    cuota_abonada = False
    presente_en_comunidad = False


class ProyectoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Proyecto

    nombre = factory.Sequence(lambda n: f"Proyecto {n}")
    fecha = factory.LazyFunction(timezone.localdate)
    estado = "captacion"
    precio_propiedad = Decimal("100000.00")
    precio_compra_inmueble = Decimal("100000.00")
    mostrar_en_landing = False
    acceso_comercial = False


class EstudioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Estudio

    nombre = factory.Sequence(lambda n: f"Estudio {n}")
    direccion = "Calle Falsa 123"
    ref_catastral = factory.Sequence(lambda n: f"1234567AB{n:03d}C")
    datos = factory.LazyFunction(dict)


class InversorPerfilFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InversorPerfil

    cliente = factory.SubFactory(ClienteFactory)
    token = factory.Sequence(lambda n: f"token-{n}")
    activo = True


class NoticiaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Noticia

    titulo = factory.Sequence(lambda n: f"Noticia {n}")
    slug = factory.Sequence(lambda n: f"noticia-{n}")
    extracto = factory.Faker("sentence")
    cuerpo = factory.Faker("paragraph")
    autor = "Equipo Inversure"
    fecha_publicacion = factory.LazyFunction(timezone.localdate)
    estado = "publicado"
