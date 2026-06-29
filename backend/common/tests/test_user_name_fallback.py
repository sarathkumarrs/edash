"""Tests for the User.name auto-fill on creation."""

import pytest

from common.models import User


@pytest.mark.django_db
class TestUserNameAutoFill:
    """User.save() / UserManager.create_user() set name from email-local-part."""

    def test_create_user_without_name_falls_back_to_email_prefix(self):
        user = User.objects.create(email="aswin.1231@example.com")
        assert user.name == "aswin.1231"

    def test_create_user_with_explicit_name_is_preserved(self):
        user = User.objects.create(email="x@example.com", name="Alex Carter")
        assert user.name == "Alex Carter"

    def test_get_or_create_falls_back_when_creating(self):
        user, created = User.objects.get_or_create(email="foo.bar@example.com")
        assert created is True
        assert user.name == "foo.bar"

    def test_manager_create_user_sets_name_when_missing(self):
        user = User.objects.create_user(email="manager@example.com")
        assert user.name == "manager"

    def test_subsequent_save_does_not_overwrite_cleared_name(self):
        """If a user PATCHes name to "", the next save() must keep it empty."""
        user = User.objects.create(email="keep.empty@example.com")
        assert user.name == "keep.empty"  # auto-filled on creation
        user.name = ""
        user.save()
        user.refresh_from_db()
        assert user.name == ""

    def test_long_email_local_part_is_truncated_to_255(self):
        long_local = "a" * 300
        user = User.objects.create(email=f"{long_local}@example.com")
        assert len(user.name) == 255
