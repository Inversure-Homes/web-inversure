from django import forms
from django.contrib.auth.models import Group, User

from .models import UserAccess

class UserCreateForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    password_confirm = forms.CharField(widget=forms.PasswordInput, required=True)
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    use_custom_perms = forms.BooleanField(required=False, label="Usar permisos individuales")
    can_simulador = forms.BooleanField(required=False, label="Acceso a Simulador")
    can_estudios = forms.BooleanField(required=False, label="Acceso a Estudios")
    can_proyectos = forms.BooleanField(required=False, label="Acceso a Proyectos")
    can_clientes = forms.BooleanField(required=False, label="Acceso a Clientes")
    can_inversores = forms.BooleanField(required=False, label="Acceso a Inversores")
    can_usuarios = forms.BooleanField(required=False, label="Acceso a Usuarios")
    can_cms = forms.BooleanField(required=False, label="Acceso a CMS")
    can_facturas_preview = forms.BooleanField(required=False, label="Ver vistas previas de facturas")

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "groups",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Usar checkbox simples para permisos individuales
        for name in (
            "use_custom_perms",
            "can_simulador",
            "can_estudios",
            "can_proyectos",
            "can_clientes",
            "can_inversores",
            "can_usuarios",
            "can_cms",
            "can_facturas_preview",
        ):
            if name in self.fields:
                self.fields[name].widget = forms.CheckboxInput()

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get("password")
        pw2 = cleaned.get("password_confirm")
        if pw1 and pw2 and pw1 != pw2:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            self.save_m2m()
            access, _ = UserAccess.objects.get_or_create(user=user)
            access.use_custom_perms = bool(self.cleaned_data.get("use_custom_perms"))
            access.can_simulador = bool(self.cleaned_data.get("can_simulador"))
            access.can_estudios = bool(self.cleaned_data.get("can_estudios"))
            access.can_proyectos = bool(self.cleaned_data.get("can_proyectos"))
            access.can_clientes = bool(self.cleaned_data.get("can_clientes"))
            access.can_inversores = bool(self.cleaned_data.get("can_inversores"))
            access.can_usuarios = bool(self.cleaned_data.get("can_usuarios"))
            access.can_cms = bool(self.cleaned_data.get("can_cms"))
            access.can_facturas_preview = bool(self.cleaned_data.get("can_facturas_preview"))
            access.save()
        return user


class UserEditForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False)
    password_confirm = forms.CharField(widget=forms.PasswordInput, required=False)
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    use_custom_perms = forms.BooleanField(required=False, label="Usar permisos individuales")
    can_simulador = forms.BooleanField(required=False, label="Acceso a Simulador")
    can_estudios = forms.BooleanField(required=False, label="Acceso a Estudios")
    can_proyectos = forms.BooleanField(required=False, label="Acceso a Proyectos")
    can_clientes = forms.BooleanField(required=False, label="Acceso a Clientes")
    can_inversores = forms.BooleanField(required=False, label="Acceso a Inversores")
    can_usuarios = forms.BooleanField(required=False, label="Acceso a Usuarios")
    can_cms = forms.BooleanField(required=False, label="Acceso a CMS")
    can_facturas_preview = forms.BooleanField(required=False, label="Ver vistas previas de facturas")

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "groups",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = kwargs.get("instance")
        for name in (
            "use_custom_perms",
            "can_simulador",
            "can_estudios",
            "can_proyectos",
            "can_clientes",
            "can_inversores",
            "can_usuarios",
            "can_cms",
            "can_facturas_preview",
        ):
            if name in self.fields:
                self.fields[name].widget = forms.CheckboxInput()
        if not user:
            return
        access = getattr(user, "user_access", None)
        if access:
            self.fields["use_custom_perms"].initial = access.use_custom_perms
            self.fields["can_simulador"].initial = access.can_simulador
            self.fields["can_estudios"].initial = access.can_estudios
            self.fields["can_proyectos"].initial = access.can_proyectos
            self.fields["can_clientes"].initial = access.can_clientes
            self.fields["can_inversores"].initial = access.can_inversores
            self.fields["can_usuarios"].initial = access.can_usuarios
            self.fields["can_cms"].initial = access.can_cms
            self.fields["can_facturas_preview"].initial = access.can_facturas_preview
    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get("password")
        pw2 = cleaned.get("password_confirm")
        if pw1 or pw2:
            if pw1 != pw2:
                raise forms.ValidationError("Las contraseñas no coinciden.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        pw1 = self.cleaned_data.get("password")
        if pw1:
            user.set_password(pw1)
        if commit:
            user.save()
            self.save_m2m()
            access, _ = UserAccess.objects.get_or_create(user=user)
            access.use_custom_perms = bool(self.cleaned_data.get("use_custom_perms"))
            access.can_simulador = bool(self.cleaned_data.get("can_simulador"))
            access.can_estudios = bool(self.cleaned_data.get("can_estudios"))
            access.can_proyectos = bool(self.cleaned_data.get("can_proyectos"))
            access.can_clientes = bool(self.cleaned_data.get("can_clientes"))
            access.can_inversores = bool(self.cleaned_data.get("can_inversores"))
            access.can_usuarios = bool(self.cleaned_data.get("can_usuarios"))
            access.can_cms = bool(self.cleaned_data.get("can_cms"))
            access.can_facturas_preview = bool(self.cleaned_data.get("can_facturas_preview"))
            access.save()
        return user
