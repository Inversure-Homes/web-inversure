from django.contrib import admin
from django.urls import path, include
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('landing.urls', 'landing'), namespace='landing')),
    path('app/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('app/', include(('core.urls', 'core'), namespace='core')),
    path('cms/', include(wagtailadmin_urls)),
    path('documents/', include(wagtaildocs_urls)),
]
