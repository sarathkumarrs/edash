import logging
import secrets
import smtplib
from datetime import timedelta

from botocore.exceptions import ClientError
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import connection
from django.template.loader import render_to_string
from django.utils import timezone

from common.models import (
    Comment,
    MagicLinkToken,
    Notification,
    Org,
    Profile,
    Teams,
    User,
)

logger = logging.getLogger(__name__)


def set_rls_context(org_id):
    """
    Set RLS context for Celery tasks that query org-scoped tables.

    Celery workers don't go through Django middleware, so RLS context
    must be set explicitly before querying org-scoped data.

    Args:
        org_id: Organization UUID (string or UUID object)
    """
    # SQLite (test backend) has no set_config() — RLS is a Postgres feature.
    if connection.vendor != "postgresql":
        return
    if org_id:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_org', %s, false)", [str(org_id)]
            )


@shared_task
def send_welcome_email(user_id):
    """Send welcome email to newly created users."""
    user_obj = User.objects.filter(id=user_id).first()
    if not user_obj:
        return

    email = user_obj.email.strip()
    try:
        validate_email(email)
    except ValidationError:
        logger.warning("Welcome email skipped: invalid email for user %s", user_id)
        return

    context = {"url": settings.FRONTEND_URL}
    subject = "Welcome to EdashCRM"
    html_content = render_to_string("welcome_email.html", context=context)

    msg = EmailMessage(
        subject,
        html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.content_subtype = "html"
    try:
        msg.send()
    except (ClientError, smtplib.SMTPException, OSError):
        logger.exception("Failed to send welcome email for user %s", user_id)


def _org_admin_email(org):
    """Return the email of the org's admin (the creator), or None."""
    profile = (
        Profile.objects.filter(org=org, role="ADMIN", is_active=True)
        .select_related("user")
        .order_by("created_at")
        .first()
    )
    if not profile or not profile.user.email:
        return None
    email = profile.user.email.strip()
    try:
        validate_email(email)
    except ValidationError:
        return None
    return email


def _send_html_email(subject, template, context, recipients):
    """Render an HTML template and send it to recipients (shared helper)."""
    recipients = [e for e in recipients if e]
    if not recipients:
        return
    html_content = render_to_string(template, context=context)
    msg = EmailMessage(
        subject,
        html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    msg.content_subtype = "html"
    try:
        msg.send()
    except (ClientError, smtplib.SMTPException, OSError):
        logger.exception("Failed to send email '%s' to %s", subject, recipients)


@shared_task
def notify_superadmin_new_org(org_id, creator_user_id):
    """Email all superadmins that a new org is awaiting approval."""
    org = Org.objects.filter(id=org_id).first()
    if not org:
        return

    recipients = list(
        User.objects.filter(is_superuser=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not recipients:
        logger.warning("No superadmin recipients for new-org notification %s", org_id)
        return

    creator = User.objects.filter(id=creator_user_id).first()
    context = {
        "org_name": org.name,
        "creator_email": creator.email if creator else "",
        "creator_name": (creator.name if creator else "") or "",
        "admin_url": f"{getattr(settings, 'BACKEND_URL', '')}/admin/common/org/",
    }
    _send_html_email(
        f"[Action needed] New organization pending approval: {org.name}",
        "org_pending_approval_email.html",
        context,
        recipients,
    )


@shared_task
def notify_org_approved(org_id):
    """Email the org admin that their organization was approved."""
    org = Org.objects.filter(id=org_id).first()
    if not org:
        return
    email = _org_admin_email(org)
    if not email:
        return
    _send_html_email(
        f"Your organization '{org.name}' has been approved",
        "org_approved_email.html",
        {"org_name": org.name, "url": settings.FRONTEND_URL},
        [email],
    )


@shared_task
def notify_org_rejected(org_id):
    """Email the org admin that their organization was rejected."""
    org = Org.objects.filter(id=org_id).first()
    if not org:
        return
    email = _org_admin_email(org)
    if not email:
        return
    _send_html_email(
        f"Your organization '{org.name}' was not approved",
        "org_rejected_email.html",
        {
            "org_name": org.name,
            "url": settings.FRONTEND_URL,
            "reason": org.rejection_reason or "",
        },
        [email],
    )


@shared_task
def send_org_invitation(profile_id, inviter_id):
    """Email an organization invitation with a one-click magic link.

    The invitee's pending Profile already exists; this delivers a link that
    signs them in (reusing the magic-link flow), after which the first-login
    handler stamps their joined date.
    """
    profile = (
        Profile.objects.select_related("user", "org").filter(id=profile_id).first()
    )
    if not profile:
        return

    email = (profile.user.email or "").strip()
    try:
        validate_email(email)
    except ValidationError:
        logger.warning("Invitation skipped: invalid email for profile %s", profile_id)
        return

    org = profile.org
    inviter = User.objects.filter(id=inviter_id).first()
    inviter_name = (inviter.name or inviter.email) if inviter else ""

    token_obj = MagicLinkToken.objects.create(
        email=email,
        token=secrets.token_hex(32),
        delivery="link",
        code_hash="",
        expires_at=timezone.now() + timedelta(days=7),
    )
    join_url = f"{settings.FRONTEND_URL}/login/verify?token={token_obj.token}"

    _send_html_email(
        f"You've been invited to join {org.name} on EdashCRM",
        "org_invitation_email.html",
        {"org_name": org.name, "inviter": inviter_name, "join_url": join_url},
        [email],
    )


@shared_task
def send_magic_link_email(token_id, raw_code=None):
    """Send a magic-link or OTP-code email for passwordless authentication.

    For `delivery == "code"` rows, the caller passes `raw_code` (the plaintext
    OTP) — only the hash is stored on the token row, so the plaintext can't be
    recovered from the DB by this task.
    """
    magic_token = MagicLinkToken.objects.filter(id=token_id).first()
    if not magic_token:
        return

    email = magic_token.email.strip()
    try:
        validate_email(email)
    except ValidationError:
        logger.warning("Magic link skipped: invalid email format for token %s", token_id)
        return

    if magic_token.delivery == "code":
        if not raw_code:
            logger.warning(
                "Magic link skipped: raw_code missing for code-delivery token %s",
                token_id,
            )
            return
        subject = f"Your EdashCRM sign-in code: {raw_code}"
        html_content = render_to_string(
            "magic_link_code_email.html",
            {"code": raw_code},
        )
    else:
        magic_link_url = f"{settings.FRONTEND_URL}/login/verify?token={magic_token.token}"
        subject = "Your EdashCRM sign-in link"
        html_content = render_to_string(
            "magic_link_email.html",
            {"magic_link_url": magic_link_url},
        )

    msg = EmailMessage(
        subject,
        html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.content_subtype = "html"
    try:
        msg.send()
    except (ClientError, smtplib.SMTPException, OSError):
        logger.exception("Failed to send email for magic link token %s", token_id)


@shared_task
def send_email_user_mentions(
    comment_id,
    called_from,
    org_id=None,
):
    """Send Mail To Mentioned Users In The Comment"""
    # Set RLS context for org-scoped queries
    set_rls_context(org_id)

    comment = Comment.objects.filter(id=comment_id).first()
    if comment:
        comment_text = comment.comment
        comment_text_list = comment_text.split()
        recipients = []
        for comment_text in comment_text_list:
            if comment_text.startswith("@"):
                if comment_text.strip("@").strip(",") not in recipients:
                    if User.objects.filter(
                        username=comment_text.strip("@").strip(","), is_active=True
                    ).exists():
                        email = (
                            User.objects.filter(
                                username=comment_text.strip("@").strip(",")
                            )
                            .first()
                            .email
                        )
                        recipients.append(email)

        context = {}
        context["commented_by"] = comment.commented_by
        context["comment_description"] = comment.comment
        subject = None
        if called_from == "accounts":
            subject = "New comment on Account. "
        elif called_from == "contacts":
            subject = "New comment on Contact. "
        elif called_from == "leads":
            subject = "New comment on Lead. "
        elif called_from == "opportunity":
            subject = "New comment on Opportunity. "
        elif called_from == "cases":
            subject = "New comment on Case. "
        elif called_from == "tasks":
            subject = "New comment on Task. "
        elif called_from == "invoices":
            subject = "New comment on Invoice. "
        if subject:
            context["url"] = settings.DOMAIN_NAME
        else:
            context["url"] = ""
        # subject = 'Django CRM : comment '
        if recipients:
            for recipient in recipients:
                recipients_list = [
                    recipient,
                ]
                context["mentioned_user"] = recipient
                html_content = render_to_string("comment_email.html", context=context)
                msg = EmailMessage(
                    subject,
                    html_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=recipients_list,
                )
                msg.content_subtype = "html"
                msg.send()


@shared_task
def send_email_user_status(
    user_id,
    status_changed_user="",
):
    """Send Mail To Users Regarding their status i.e active or inactive"""
    user = User.objects.filter(id=user_id).first()
    if user:
        context = {}
        context["message"] = "deactivated"
        context["email"] = user.email
        context["url"] = settings.DOMAIN_NAME
        if user.has_marketing_access:
            context["url"] = context["url"] + "/marketing"
        if user.is_active:
            context["message"] = "activated"
        context["status_changed_user"] = status_changed_user
        if context["message"] == "activated":
            subject = "Account Activated "
            html_content = render_to_string(
                "user_status_activate.html", context=context
            )
        else:
            subject = "Account Deactivated "
            html_content = render_to_string(
                "user_status_deactivate.html", context=context
            )
        recipients = []
        recipients.append(user.email)
        if recipients:
            msg = EmailMessage(
                subject,
                html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.content_subtype = "html"
            msg.send()


@shared_task
def send_email_user_delete(
    user_email,
    deleted_by="",
):
    """Send Mail To Users When their account is deleted"""
    if user_email:
        context = {}
        context["message"] = "deleted"
        context["deleted_by"] = deleted_by
        context["email"] = user_email
        recipients = []
        recipients.append(user_email)
        subject = "CRM : Your account is Deleted. "
        html_content = render_to_string("user_delete_email.html", context=context)
        if recipients:
            msg = EmailMessage(
                subject,
                html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.content_subtype = "html"
            msg.send()


@shared_task
def remove_users(removed_users_list, team_id, org_id=None):
    # Set RLS context for org-scoped queries
    set_rls_context(org_id)

    removed_users_list = [i for i in removed_users_list if i.isdigit()]
    users_list = Profile.objects.filter(id__in=removed_users_list)
    if users_list.exists():
        team = Teams.objects.filter(id=team_id).first()
        if team:
            accounts = team.account_teams.all()
            for account in accounts:
                for user in users_list:
                    account.assigned_to.remove(user)

            contacts = team.contact_teams.all()
            for contact in contacts:
                for user in users_list:
                    contact.assigned_to.remove(user)

            leads = team.lead_teams.all()
            for lead in leads:
                for user in users_list:
                    lead.assigned_to.remove(user)

            opportunities = team.oppurtunity_teams.all()
            for opportunity in opportunities:
                for user in users_list:
                    opportunity.assigned_to.remove(user)

            cases = team.cases_teams.all()
            for case in cases:
                for user in users_list:
                    case.assigned_to.remove(user)

            docs = team.document_teams.all()
            for doc in docs:
                for user in users_list:
                    doc.shared_to.remove(user)

            tasks = team.tasks_teams.all()
            for task in tasks:
                for user in users_list:
                    task.assigned_to.remove(user)

            invoices = team.invoices_teams.all()
            for invoice in invoices:
                for user in users_list:
                    invoice.assigned_to.remove(user)


@shared_task
def update_team_users(team_id, org_id=None):
    """this function updates assigned_to field on all models when a team is updated"""
    # Set RLS context for org-scoped queries
    set_rls_context(org_id)

    team = Teams.objects.filter(id=team_id).first()
    if team:
        teams_members = team.users.all()

        accounts = team.account_teams.all()
        for account in accounts:
            account_assigned_to_users = account.assigned_to.all()
            for team_member in teams_members:
                if team_member not in account_assigned_to_users:
                    account.assigned_to.add(team_member)

        contacts = team.contact_teams.all()
        for contact in contacts:
            contact_assigned_to_users = contact.assigned_to.all()
            for team_member in teams_members:
                if team_member not in contact_assigned_to_users:
                    contact.assigned_to.add(team_member)

        leads = team.lead_teams.all()
        for lead in leads:
            lead_assigned_to_users = lead.assigned_to.all()
            for team_member in teams_members:
                if team_member not in lead_assigned_to_users:
                    lead.assigned_to.add(team_member)

        opportunities = team.oppurtunity_teams.all()
        for opportunity in opportunities:
            opportunity_assigned_to_users = opportunity.assigned_to.all()
            for team_member in teams_members:
                if team_member not in opportunity_assigned_to_users:
                    opportunity.assigned_to.add(team_member)

        cases = team.cases_teams.all()
        for case in cases:
            case_assigned_to_users = case.assigned_to.all()
            for team_member in teams_members:
                if team_member not in case_assigned_to_users:
                    case.assigned_to.add(team_member)

        docs = team.document_teams.all()
        for doc in docs:
            doc_assigned_to_users = doc.shared_to.all()
            for team_member in teams_members:
                if team_member not in doc_assigned_to_users:
                    doc.shared_to.add(team_member)

        tasks = team.tasks_teams.all()
        for task in tasks:
            task_assigned_to_users = task.assigned_to.all()
            for team_member in teams_members:
                if team_member not in task_assigned_to_users:
                    task.assigned_to.add(team_member)

        invoices = team.invoices_teams.all()
        for invoice in invoices:
            invoice_assigned_to_users = invoice.assigned_to.all()
            for team_member in teams_members:
                if team_member not in invoice_assigned_to_users:
                    invoice.assigned_to.add(team_member)


# Default cutoff for purging read notifications. Per
# `docs/cases/tier2/in-app-notifications.md` "Storage growth".
NOTIFICATION_PURGE_DAYS = 90


@shared_task
def purge_read_notifications(days=NOTIFICATION_PURGE_DAYS):
    """Delete already-read notifications older than ``days`` days.

    Schedule via celery-beat (recommended cadence: nightly). Runs once across
    all orgs — RLS does not need a per-org context here because the query
    targets `read_at`, which is intrinsic to the row, not org-scoped logic.
    """
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = Notification.objects.filter(
        read_at__isnull=False, read_at__lt=cutoff
    ).delete()
    if deleted:
        logger.info(
            "Purged %s read notifications older than %s days", deleted, days
        )
    return deleted
