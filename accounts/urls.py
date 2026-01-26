from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("usuarios/", views.users_list, name="users_list"),
    path("actividad/", views.activity_dashboard, name="activity_dashboard"),
    path("usuarios/nuevo/", views.user_create, name="user_create"),
    path("usuarios/<int:user_id>/", views.user_edit, name="user_edit"),
    path("usuarios/<int:user_id>/borrar/", views.user_delete, name="user_delete"),
]
