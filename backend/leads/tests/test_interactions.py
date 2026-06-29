"""Tests for lead interactions (logged contacts) and the assignment follow-up.

Covers: logging a contact updates the lead's last_contacted / next_follow_up,
notes are required, outcome is validated against the admin-managed list,
author/admin-only edit-delete, and the assignment signal setting due-today.
"""

from datetime import date

import pytest
from django.db import connection

from leads.models import Lead, LeadInteraction
from leads.outcomes import seed_default_outcomes
from tasks.models import Task


def _set_rls(org):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_org', %s, false)", [str(org.id)]
        )


def _interactions_url(lead_id):
    return f"/api/leads/{lead_id}/interactions/"


def _interaction_detail_url(pk):
    return f"/api/leads/interactions/{pk}/"


@pytest.fixture
def lead_a(admin_user, org_a):
    _set_rls(org_a)
    return Lead.objects.create(
        title="Acme deal", first_name="John", created_by=admin_user, org=org_a
    )


@pytest.mark.django_db
class TestAssignmentDueToday:
    def test_assignment_sets_followup_today(self, admin_user, org_a, admin_profile):
        _set_rls(org_a)
        lead = Lead.objects.create(title="New", created_by=admin_user, org=org_a)
        assert lead.next_follow_up is None
        lead.assigned_to.add(admin_profile)
        lead.refresh_from_db()
        assert lead.next_follow_up == date.today()

    def test_existing_followup_not_overwritten(self, admin_user, org_a, admin_profile):
        _set_rls(org_a)
        future = date(2099, 1, 1)
        lead = Lead.objects.create(
            title="Scheduled", next_follow_up=future, created_by=admin_user, org=org_a
        )
        lead.assigned_to.add(admin_profile)
        lead.refresh_from_db()
        assert lead.next_follow_up == future


@pytest.mark.django_db
class TestLogContact:
    def test_log_contact_updates_lead(self, admin_client, org_a, lead_a):
        _set_rls(org_a)
        seed_default_outcomes(org_a)
        resp = admin_client.post(
            _interactions_url(lead_a.id),
            {
                "interaction_type": "call",
                "outcome": "connected",
                "notes": "Spoke with the buyer",
                "next_follow_up": "2026-07-15",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        lead_a.refresh_from_db()
        assert lead_a.last_contacted == date.today()
        assert lead_a.next_follow_up == date(2026, 7, 15)
        assert lead_a.interactions.count() == 1

    def test_notes_required(self, admin_client, org_a, lead_a):
        _set_rls(org_a)
        seed_default_outcomes(org_a)
        resp = admin_client.post(
            _interactions_url(lead_a.id),
            {"interaction_type": "note", "notes": "   "},
            format="json",
        )
        assert resp.status_code == 400
        assert "notes" in resp.json()["errors"]

    def test_invalid_outcome_rejected(self, admin_client, org_a, lead_a):
        _set_rls(org_a)
        seed_default_outcomes(org_a)
        resp = admin_client.post(
            _interactions_url(lead_a.id),
            {"interaction_type": "call", "outcome": "banana", "notes": "x"},
            format="json",
        )
        assert resp.status_code == 400
        assert "outcome" in resp.json()["errors"]

    def test_outcome_optional_when_no_list(self, admin_client, org_a, lead_a):
        # No outcome definition seeded -> any/empty outcome accepted.
        _set_rls(org_a)
        resp = admin_client.post(
            _interactions_url(lead_a.id),
            {"interaction_type": "note", "notes": "Just a note"},
            format="json",
        )
        assert resp.status_code == 201, resp.content

    def test_list_returns_timeline(self, admin_client, org_a, lead_a, admin_user):
        _set_rls(org_a)
        LeadInteraction.objects.create(
            lead=lead_a, org=org_a, notes="first", created_by=admin_user
        )
        resp = admin_client.get(_interactions_url(lead_a.id))
        assert resp.status_code == 200
        assert len(resp.json()["interactions"]) == 1


@pytest.mark.django_db
class TestFollowupTask:
    """A logged follow-up becomes a CRM task (visible in My Tasks / Due Today)."""

    def test_followup_creates_task(self, admin_client, org_a, lead_a, admin_profile):
        _set_rls(org_a)
        resp = admin_client.post(
            _interactions_url(lead_a.id),
            {"interaction_type": "call", "notes": "called", "next_follow_up": "2026-07-20"},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        task = Task.objects.filter(lead=lead_a).first()
        assert task is not None
        assert str(task.due_date) == "2026-07-20"
        assert task.status == "New"
        assert admin_profile in task.assigned_to.all()

    def test_followup_reschedules_same_task(self, admin_client, org_a, lead_a):
        _set_rls(org_a)
        admin_client.post(
            _interactions_url(lead_a.id),
            {"interaction_type": "call", "notes": "first", "next_follow_up": "2026-07-20"},
            format="json",
        )
        admin_client.post(
            _interactions_url(lead_a.id),
            {"interaction_type": "call", "notes": "second", "next_follow_up": "2026-07-25"},
            format="json",
        )
        tasks = Task.objects.filter(lead=lead_a)
        assert tasks.count() == 1
        assert str(tasks.first().due_date) == "2026-07-25"

    def test_no_followup_no_task(self, admin_client, org_a, lead_a):
        _set_rls(org_a)
        resp = admin_client.post(
            _interactions_url(lead_a.id),
            {"interaction_type": "note", "notes": "no follow up"},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert Task.objects.filter(lead=lead_a).count() == 0


@pytest.mark.django_db
class TestLeadDetailForAssignedUser:
    """Regression: a non-admin who didn't create the lead must be able to open
    the lead detail page (the Log Contact deep-link target). Previously crashed
    with AttributeError: 'User' object has no attribute 'username'."""

    def test_non_admin_non_creator_can_open_lead(
        self, user_client, admin_user, org_a, user_profile
    ):
        _set_rls(org_a)
        lead = Lead.objects.create(
            title="Assigned to rep", created_by=admin_user, org=org_a
        )
        lead.assigned_to.add(user_profile)
        resp = user_client.get(f"/api/leads/{lead.id}/")
        assert resp.status_code == 200, resp.content


@pytest.mark.django_db
class TestInteractionPermissions:
    def test_non_author_cannot_delete(
        self, user_client, admin_user, org_a, lead_a
    ):
        # Interaction authored by admin; a regular (non-admin) user may not delete.
        _set_rls(org_a)
        interaction = LeadInteraction.objects.create(
            lead=lead_a, org=org_a, notes="admin note", created_by=admin_user
        )
        resp = user_client.delete(_interaction_detail_url(interaction.id))
        assert resp.status_code == 403
        assert LeadInteraction.objects.filter(id=interaction.id).exists()

    def test_admin_can_delete(self, admin_client, admin_user, org_a, lead_a):
        _set_rls(org_a)
        interaction = LeadInteraction.objects.create(
            lead=lead_a, org=org_a, notes="note", created_by=admin_user
        )
        resp = admin_client.delete(_interaction_detail_url(interaction.id))
        assert resp.status_code == 200
        assert not LeadInteraction.objects.filter(id=interaction.id).exists()
