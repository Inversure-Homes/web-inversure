from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UserCreateForm, UserEditForm


def _is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    error = ""
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("core:home")
        error = "Usuario o contraseña incorrectos."
    return render(request, "accounts/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@login_required
@user_passes_test(_is_admin)
def users_list(request):
    usuarios = User.objects.order_by("username")
    grupos = Group.objects.order_by("name")
    return render(request, "accounts/users_list.html", {"usuarios": usuarios, "grupos": grupos})


@login_required
@user_passes_test(_is_admin)
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("accounts:users_list")
    else:
        form = UserCreateForm()
    return render(request, "accounts/user_form.html", {"form": form, "modo": "nuevo"})


@login_required
@user_passes_test(_is_admin)
def user_edit(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            return redirect("accounts:users_list")
    else:
        form = UserEditForm(instance=user_obj)
    return render(request, "accounts/user_form.html", {"form": form, "modo": "editar", "user_obj": user_obj})


@login_required
@user_passes_test(_is_admin)
def user_delete(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        user_obj.delete()
        return redirect("accounts:users_list")
    return render(request, "accounts/confirm_delete.html", {"user_obj": user_obj})
