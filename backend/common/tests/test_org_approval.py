"""
Tests for the superadmin org-approval gate:
- new orgs are created pending and notify superadmins
- pending orgs are locked (middleware + org switch)
- the Django admin approve action unlocks an org and notifies the creator

Run with: pytest common/tests/test_org_approval.py -v
"""

from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from common.admin import OrgAdmin
from common.models import Org, Profile, User
from common.serializer import OrgAwareRefreshToken


def _client_for(user, org, profile):
    client = APIClient()
    token = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.mark.django_db
class TestOrgCreationIsPending:
    url = "/api/org/"

    def test_new_org_is_pending_and_creator_is_admin(self, admin_client, admin_user):
        with patch(
            "common.tasks.notify_superadmin_new_org.delay"
        ) as mock_notify:
            response = admin_client.post(
                self.url, {"name": "Pending Co"}, format="json"
            )
        assert response.status_code == status.HTTP_200_OK
        org = Org.objects.get(name="Pending Co")
        assert org.approval_status == Org.APPROVAL_PENDING
        assert not org.is_approved
        assert Profile.objects.filter(
            user=admin_user, org=org, role="ADMIN", is_organization_admin=True
        ).exists()
        mock_notify.assert_called_once_with(str(org.id), str(admin_user.id))


@pytest.mark.django_db
class TestPendingOrgIsLocked:
    def _pending_setup(self):
        user = User.objects.create_user(email="pend@test.com", password="x")
        org = Org.objects.create(
            name="Locked Org", approval_status=Org.APPROVAL_PENDING
        )
        profile = Profile.objects.create(
            user=user, org=org, role="ADMIN", is_active=True
        )
        return user, org, profile

    def test_middleware_blocks_org_scoped_request(self):
        user, org, profile = self._pending_setup()
        client = _client_for(user, org, profile)
        # HasOrgContext denies because middleware refuses to set org context.
        response = client.get("/api/accounts/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_switch_into_pending_org(self, admin_client, admin_user):
        org = Org.objects.create(
            name="Switch Pending", approval_status=Org.APPROVAL_PENDING
        )
        Profile.objects.create(
            user=admin_user, org=org, role="ADMIN", is_active=True
        )
        response = admin_client.post(
            "/api/auth/switch-org/", {"org_id": str(org.id)}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "pending" in response.data["error"].lower()

    def test_access_works_after_approval(self):
        user, org, profile = self._pending_setup()
        org.approval_status = Org.APPROVAL_APPROVED
        org.save(update_fields=["approval_status"])
        client = _client_for(user, org, profile)
        response = client.get("/api/accounts/")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestAdminApprovalAction:
    def _admin_request(self, superuser):
        # Minimal request stub carrying the acting user; admin actions only
        # read request.user.
        class _Req:
            user = superuser

            def __init__(self):
                self._messages = []

        return _Req()

    def test_approve_action_approves_and_notifies(self):
        superuser = User.objects.create_superuser(
            email="root@test.com", password="x"
        )
        creator = User.objects.create_user(email="owner@test.com", password="x")
        org = Org.objects.create(
            name="To Approve", approval_status=Org.APPROVAL_PENDING
        )
        Profile.objects.create(
            user=creator, org=org, role="ADMIN", is_active=True
        )

        org_admin = OrgAdmin(Org, AdminSite())
        request = self._admin_request(superuser)
        with patch("common.tasks.notify_org_approved.delay") as mock_notify, patch.object(
            org_admin, "message_user"
        ):
            org_admin.approve_organizations(request, Org.objects.filter(id=org.id))

        org.refresh_from_db()
        assert org.approval_status == Org.APPROVAL_APPROVED
        assert org.approved_by_id == superuser.id
        assert org.approved_at is not None
        mock_notify.assert_called_once_with(str(org.id))

    def test_reject_action_rejects_and_notifies(self):
        superuser = User.objects.create_superuser(
            email="root2@test.com", password="x"
        )
        org = Org.objects.create(
            name="To Reject", approval_status=Org.APPROVAL_PENDING
        )
        org_admin = OrgAdmin(Org, AdminSite())
        request = self._admin_request(superuser)
        with patch("common.tasks.notify_org_rejected.delay") as mock_notify, patch.object(
            org_admin, "message_user"
        ):
            org_admin.reject_organizations(request, Org.objects.filter(id=org.id))

        org.refresh_from_db()
        assert org.approval_status == Org.APPROVAL_REJECTED
        mock_notify.assert_called_once_with(str(org.id))

    def test_non_superuser_cannot_approve(self):
        staff = User.objects.create_user(email="staff@test.com", password="x")
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        org = Org.objects.create(
            name="Guarded", approval_status=Org.APPROVAL_PENDING
        )
        org_admin = OrgAdmin(Org, AdminSite())
        request = self._admin_request(staff)
        with patch("common.tasks.notify_org_approved.delay") as mock_notify, patch.object(
            org_admin, "message_user"
        ):
            org_admin.approve_organizations(request, Org.objects.filter(id=org.id))

        org.refresh_from_db()
        assert org.approval_status == Org.APPROVAL_PENDING
        mock_notify.assert_not_called()
