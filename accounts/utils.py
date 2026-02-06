ROLE_ADMIN = "administracion"
ROLE_DIRECCION = "direccion"
ROLE_MARKETING = "marketing"
ROLE_COMERCIAL = "comercial"
ROLE_MODERATORS = "moderators"


def _get_role(user):
    access = get_user_access(user)
    return (access.role or "").strip().lower() if access else ""


def is_admin_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return _get_role(user) == ROLE_ADMIN


def is_direccion_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return _get_role(user) == ROLE_DIRECCION


def is_marketing_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return _get_role(user) == ROLE_MARKETING


def is_comercial_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return _get_role(user) == ROLE_COMERCIAL


def is_moderators_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return _get_role(user) == ROLE_MODERATORS


def get_user_access(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, "user_access", None)


def use_custom_permissions(user) -> bool:
    access = get_user_access(user)
    return bool(access and access.use_custom_perms)


def resolve_permissions(user) -> dict:
    perms = {
        "can_simulador": False,
        "can_estudios": False,
        "can_proyectos": False,
        "can_clientes": False,
        "can_inversores": False,
        "can_usuarios": False,
        "can_cms": False,
        "can_facturas_preview": False,
    }
    if not user or not user.is_authenticated:
        return perms

    if is_admin_user(user):
        return {k: True for k in perms}

    access = get_user_access(user)
    if access and access.use_custom_perms:
        return {
            "can_simulador": bool(access.can_simulador),
            "can_estudios": bool(access.can_estudios),
            "can_proyectos": bool(access.can_proyectos),
            "can_clientes": bool(access.can_clientes),
            "can_inversores": bool(access.can_inversores),
            "can_usuarios": bool(access.can_usuarios),
            "can_cms": bool(access.can_cms),
            "can_facturas_preview": bool(access.can_facturas_preview),
        }

    role = _get_role(user)
    if role == ROLE_DIRECCION:
        perms.update(
            {
                "can_simulador": True,
                "can_estudios": True,
                "can_proyectos": True,
                "can_clientes": True,
                "can_inversores": True,
                "can_cms": True,
                "can_facturas_preview": True,
            }
        )
        return perms

    if role == ROLE_MARKETING:
        perms["can_estudios"] = True
        perms["can_proyectos"] = True
        perms["can_cms"] = True
        return perms

    if role == ROLE_COMERCIAL:
        perms["can_simulador"] = True
        perms["can_estudios"] = True
        perms["can_proyectos"] = True
        return perms

    if role == ROLE_MODERATORS:
        perms["can_proyectos"] = True
        return perms

    return perms
