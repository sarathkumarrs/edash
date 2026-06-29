"""Tests for the admin overview dashboard (/api/dashboard/admin/)."""

from datetime import date, timedelta

import pytest
from django.db import connection

from leads.models import Lead

URL = "/api/dashboard/admin/"


def _set_rls(org):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_org', %s, false)", [str(org.id)]
        )


@pytest.mark.django_db
class TestAdminDashboard:
    def test_non_admin_forbidden(self, user_client, org_a):
        _set_rls(org_a)
        resp = user_client.get(URL)
        assert resp.status_code == 403

    def test_admin_ok_shape(self, admin_client, org_a):
        _set_rls(org_a)
        resp = admin_client.get(URL)
        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "overview",
            "status_breakdown",
            "followup_health",
            "user_metrics",
            "lead_activity",
        ):
            assert key in body

    def test_overview_and_assignment_counts(
        self, admin_client, admin_user, admin_profile, org_a
    ):
        _set_rls(org_a)
        # assigned + contacted
        a = Lead.objects.create(
            title="Assigned", status="assigned", org=org_a, created_by=admin_user
        )
        a.assigned_to.add(admin_profile)
        # unassigned
        Lead.objects.create(
            title="Unassigned", status="assigned", org=org_a, created_by=admin_user
        )
        # converted
        Lead.objects.create(
            title="Won", status="converted", org=org_a, created_by=admin_user
        )

        body = admin_client.get(URL).json()
        ov = body["overview"]
        assert ov["total"] == 3
        assert ov["assigned"] == 1
        assert ov["unassigned"] == 2
        assert ov["converted"] == 1

    def test_followup_health_overdue_and_uncontacted(
        self, admin_client, admin_user, admin_profile, org_a
    ):
        _set_rls(org_a)
        yesterday = date.today() - timedelta(days=1)
        overdue = Lead.objects.create(
            title="Overdue",
            status="assigned",
            next_follow_up=yesterday,
            org=org_a,
            created_by=admin_user,
        )
        overdue.assigned_to.add(admin_profile)

        body = admin_client.get(URL).json()
        assert body["followup_health"]["overdue"] >= 1
        # assigned + never contacted -> counts as a skipped first touch
        assert body["followup_health"]["never_contacted"] >= 1

        # And it shows in the per-rep overdue metric.
        me = next(
            (m for m in body["user_metrics"] if m["email"] == admin_user.email), None
        )
        assert me is not None
        assert me["overdue"] >= 1
