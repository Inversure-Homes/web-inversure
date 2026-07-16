import pytest
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import UserAccess

from .factories import UserAccessFactory, UserFactory


@pytest.fixture
def direccion_user(db):
    user = UserFactory()
    UserAccessFactory(user=user, role=UserAccess.ROLE_DIRECCION)
    return user


@pytest.fixture
def custom_perms_user(db):
    user = UserFactory()
    UserAccessFactory(
        user=user,
        role="",
        use_custom_perms=True,
        can_simulador=False,
        can_estudios=True,
        can_proyectos=False,
        can_clientes=False,
        can_inversores=False,
        can_usuarios=False,
        can_cms=False,
        can_facturas_preview=False,
    )
    return user


@pytest.fixture
def verified_client(client, direccion_user):
    device = TOTPDevice.objects.create(user=direccion_user, name="pytest-otp-device")
    client.force_login(direccion_user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    return client
