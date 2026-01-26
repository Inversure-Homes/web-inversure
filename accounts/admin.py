from django.contrib import admin

from auditlog.models import LogEntry

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


@admin.register(LogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor", "action", "content_type", "object_pk")
    list_filter = ("action", "content_type")
    search_fields = ("actor__username", "object_pk", "changes")
