from django import forms
from django.contrib import admin, messages
from django.utils import timezone

from common.models import Address, Comment, CommentFiles, Org, SessionToken, User
from common.modules import MODULE_CHOICES

# Register your models here.

admin.site.register(User)
admin.site.register(Address)
admin.site.register(Comment)
admin.site.register(CommentFiles)


class OrgAdminForm(forms.ModelForm):
    """Render enabled_modules (a JSON list) as a checkbox list of modules."""

    enabled_modules = forms.MultipleChoiceField(
        choices=MODULE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Modules this workspace can see. Unchecked modules are hidden "
        "from its sidebar and routes.",
    )

    class Meta:
        model = Org
        fields = "__all__"


@admin.register(Org)
class OrgAdmin(admin.ModelAdmin):
    form = OrgAdminForm
    list_display = (
        "name",
        "approval_status",
        "is_active",
        "module_count",
        "approved_by",
        "approved_at",
        "created_at",
    )
    list_filter = ("approval_status", "is_active")
    search_fields = ("name", "email")
    readonly_fields = ("api_key", "approved_at", "approved_by", "created_at")
    ordering = ("-created_at",)
    actions = ["approve_organizations", "reject_organizations"]

    @admin.display(description="Modules")
    def module_count(self, obj):
        return f"{len(obj.enabled_modules or [])}/{len(MODULE_CHOICES)}"

    @admin.action(description="Approve selected organizations")
    def approve_organizations(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(
                request,
                "Only superadmins can approve organizations.",
                level=messages.ERROR,
            )
            return

        from common.tasks import notify_org_approved

        updated = 0
        for org in queryset.exclude(approval_status=Org.APPROVAL_APPROVED):
            org.approval_status = Org.APPROVAL_APPROVED
            org.approved_at = timezone.now()
            org.approved_by = request.user
            org.save()
            notify_org_approved.delay(str(org.id))
            updated += 1
        self.message_user(request, f"{updated} organization(s) approved.")

    @admin.action(description="Reject selected organizations")
    def reject_organizations(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(
                request,
                "Only superadmins can reject organizations.",
                level=messages.ERROR,
            )
            return

        from common.tasks import notify_org_rejected

        updated = 0
        for org in queryset.exclude(approval_status=Org.APPROVAL_REJECTED):
            org.approval_status = Org.APPROVAL_REJECTED
            org.save()
            notify_org_rejected.delay(str(org.id))
            updated += 1
        self.message_user(request, f"{updated} organization(s) rejected.")


@admin.register(SessionToken)
class SessionTokenAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "token_jti_short",
        "is_active",
        "expires_at",
        "last_used_at",
        "created_at",
    )
    list_filter = ("is_active", "expires_at", "created_at")
    search_fields = ("user__email", "token_jti", "ip_address")
    raw_id_fields = ("user",)
    readonly_fields = (
        "token_jti",
        "refresh_token_jti",
        "created_at",
        "last_used_at",
        "revoked_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    actions = ["revoke_tokens", "cleanup_expired"]

    def token_jti_short(self, obj):
        return f"{obj.token_jti[:16]}..."

    token_jti_short.short_description = "Token JTI"

    def revoke_tokens(self, request, queryset):
        for token in queryset:
            token.revoke()
        self.message_user(request, f"{queryset.count()} tokens revoked successfully.")

    revoke_tokens.short_description = "Revoke selected tokens"

    def cleanup_expired(self, request, queryset):
        count, _ = SessionToken.cleanup_expired()
        self.message_user(request, f"{count} expired tokens cleaned up.")

    cleanup_expired.short_description = "Cleanup expired tokens"
