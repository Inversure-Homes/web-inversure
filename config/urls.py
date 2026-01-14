from django.contrib import admin
from django.urls import path, include
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from cms import views as cms_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('landing.urls', 'landing'), namespace='landing')),
    path('app/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('app/', include(('core.urls', 'core'), namespace='core')),
    path('cms/', include(wagtailadmin_urls)),
    path('documents/', include(wagtaildocs_urls)),
    path('', cms_views.root_or_app),
    path('', include(wagtail_urls)),
]
