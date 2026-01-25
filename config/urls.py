from django.contrib import admin
from django.urls import path, include
from two_factor import urls as two_factor_urls
from two_factor.admin import AdminSiteOTPRequired
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

admin.site.__class__ = AdminSiteOTPRequired

def _flatten_urlpatterns(patterns):
    for p in patterns:
        if isinstance(p, (list, tuple)):
            yield from _flatten_urlpatterns(p)
        else:
            yield p

two_factor_patterns = list(_flatten_urlpatterns(two_factor_urls.urlpatterns))

urlpatterns = [
    path('account/', include((two_factor_patterns, 'two_factor'), namespace='two_factor')),
    path('admin/', admin.site.urls),
    path('', include(('landing.urls', 'landing'), namespace='landing')),
    path('app/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('app/', include(('core.urls', 'core'), namespace='core')),
    path('cms/', include(wagtailadmin_urls)),
    path('documents/', include(wagtaildocs_urls)),
]
