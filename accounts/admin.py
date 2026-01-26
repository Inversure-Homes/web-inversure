from django.contrib import admin

from .models import UserSession, UserConnectionLog


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "session_key", "ip_address", "last_seen_at", "ended_at")
    search_fields = ("user__username", "session_key", "ip_address")
    list_filter = ("ended_at",)


@admin.register(UserConnectionLog)
class UserConnectionLogAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "ip_address", "created_at")
    search_fields = ("user__username", "ip_address")
    list_filter = ("event",)

