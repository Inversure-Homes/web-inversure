from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('landing.urls', 'landing'), namespace='landing')),
    path('app/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('app/', include(('core.urls', 'core'), namespace='core')),
]
