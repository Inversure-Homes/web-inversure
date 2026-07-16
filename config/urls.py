from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.urls.resolvers import URLPattern, URLResolver
from django.views.generic import RedirectView
from two_factor import urls as two_factor_urls
from two_factor.admin import AdminSiteOTPRequired
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from core import views as core_views

admin.site.__class__ = AdminSiteOTPRequired


def _flatten_two_factor_patterns(patterns):
    for pattern in patterns:
        if isinstance(pattern, (URLPattern, URLResolver)):
            yield pattern
        elif isinstance(pattern, (list, tuple)):
            yield from _flatten_two_factor_patterns(pattern)


two_factor_urlpatterns = list(_flatten_two_factor_patterns(two_factor_urls.urlpatterns))

urlpatterns = [
    path("healthz/", core_views.healthz, name="healthz"),
    path("sw.js", core_views.pwa_service_worker, name="pwa_service_worker"),
    path(
        "",
        include((two_factor_urlpatterns, "two_factor"), namespace="two_factor"),
    ),
    path(
        "account/account/login/",
        RedirectView.as_view(pattern_name="two_factor:login", permanent=False),
    ),
    path("admin/", admin.site.urls),
    path("", include(("landing.urls", "landing"), namespace="landing")),
    path("app/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("app/", include(("core.urls", "core"), namespace="core")),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
]

if getattr(settings, "DEBUG_TOOLBAR_ENABLED", False):
    import debug_toolbar

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
