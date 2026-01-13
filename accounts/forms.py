from django import forms
from django.contrib.auth.models import Group, User


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    password_confirm = forms.CharField(widget=forms.PasswordInput, required=True)
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

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
        return user


class UserEditForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False)
    password_confirm = forms.CharField(widget=forms.PasswordInput, required=False)
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

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
        return user
