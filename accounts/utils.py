ROLE_ADMIN = "Administrador"
ROLE_MARKETING = "Marketing"
ROLE_COMERCIAL = "Comercial"


def _has_group(user, name: str) -> bool:
    if not user.is_authenticated:
        return False
    return user.groups.filter(name=name).exists()


def is_admin_user(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or _has_group(user, ROLE_ADMIN)))


def is_marketing_user(user) -> bool:
    return bool(user.is_authenticated and _has_group(user, ROLE_MARKETING))


def is_comercial_user(user) -> bool:
    return bool(user.is_authenticated and _has_group(user, ROLE_COMERCIAL))


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

    if is_marketing_user(user):
        perms["can_cms"] = True
        return perms

    if is_comercial_user(user):
        perms["can_simulador"] = True
        perms["can_estudios"] = True
        perms["can_proyectos"] = True
        return perms

    return perms
