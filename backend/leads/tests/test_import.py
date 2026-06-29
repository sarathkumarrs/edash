"""Tests for the lead CSV importer (Meta-ads friendly)."""

import pytest
from django.db import connection

from leads.models import Lead
from leads.services.csv_import import commit_rows, parse_and_validate


def _set_rls(org):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_org', %s, false)", [str(org.id)]
        )


@pytest.mark.django_db
class TestLeadImport:
    def test_meta_style_full_name_and_aliases(self, org_a):
        _set_rls(org_a)
        csv = (
            b"full_name,email,phone_number,company_name,source\n"
            b"Jane Roe,jane@example.com,+1 (202) 555-9911,Acme Inc,meta ads\n"
        )
        res = parse_and_validate(csv, org_a)
        assert res.header_error is None
        assert res.summary["valid"] == 1
        row = res.valid[0]
        assert (row.first_name, row.last_name) == ("Jane", "Roe")
        assert row.company == "Acme Inc"
        assert row.phone == "+1 (202) 555-9911"

    def test_commit_creates_assigned_lead(self, org_a, admin_profile):
        _set_rls(org_a)
        csv = b"full_name,email\nJohn Doe,john@example.com\n"
        out = commit_rows(csv, org_a, admin_profile)
        assert out["error"] is False
        assert out["created"] == 1
        assert out["skipped"] == 0
        lead = Lead.objects.get(email="john@example.com")
        assert lead.first_name == "John"
        assert lead.status == "assigned"

    def test_in_file_and_existing_email_dedup(self, org_a, admin_user):
        _set_rls(org_a)
        Lead.objects.create(email="dup@example.com", org=org_a, created_by=admin_user)
        csv = (
            b"full_name,email\n"
            b"A One,dup@example.com\n"        # exists in org
            b"B Two,new@example.com\n"
            b"C Three,new@example.com\n"      # dup within file
        )
        res = parse_and_validate(csv, org_a)
        msgs = {(e.row, e.field) for e in res.errors}
        assert (1, "email") in msgs  # already exists
        assert (3, "email") in msgs  # dup in file
        assert res.summary["valid"] == 1

    def test_phone_dedup_in_file_and_existing(self, org_a, admin_user):
        _set_rls(org_a)
        # Existing lead with a phone in a different format — must still match.
        Lead.objects.create(phone="(202) 555-1234", org=org_a, created_by=admin_user)
        csv = (
            b"full_name,phone\n"
            b"A One,+1 202 555 1234\n"     # same number as existing, different format
            b"B Two,202-777-0000\n"
            b"C Three,2027770000\n"        # dup of row 2 within file
        )
        res = parse_and_validate(csv, org_a)
        dup_rows = {(e.row, e.field) for e in res.errors}
        assert (1, "phone") in dup_rows  # matches existing
        assert (3, "phone") in dup_rows  # dup in file
        assert res.summary["valid"] == 1

    def test_skip_duplicates_mode(self, org_a, admin_user, admin_profile):
        _set_rls(org_a)
        Lead.objects.create(email="exists@example.com", org=org_a, created_by=admin_user)
        csv = (
            b"full_name,email\n"
            b"Dup Person,exists@example.com\n"   # skip
            b"Fresh Person,fresh@example.com\n"  # import
        )
        res = parse_and_validate(csv, org_a, skip_duplicates=True)
        assert res.summary["valid"] == 1
        assert res.summary["invalid"] == 0
        assert res.summary["skipped"] == 1

        out = commit_rows(csv, org_a, admin_profile, skip_duplicates=True)
        assert out["error"] is False
        assert out["created"] == 1
        assert out["skipped"] == 1
        assert Lead.objects.filter(email="fresh@example.com").exists()

    def test_row_needs_an_identifier(self, org_a):
        _set_rls(org_a)
        csv = b"first_name,last_name,email,phone,company\n,,,,Acme\n"
        res = parse_and_validate(csv, org_a)
        assert res.summary["valid"] == 0
        assert any(e.field == "row" for e in res.errors)

    def test_unknown_header_rejected(self, org_a):
        _set_rls(org_a)
        res = parse_and_validate(b"full_name,zzz\nJane Roe,x\n", org_a)
        assert res.header_error is not None
        assert "zzz" in res.header_error

    def test_invalid_rating_and_country(self, org_a):
        _set_rls(org_a)
        csv = b"full_name,email,rating,country\nJane Roe,j@example.com,Spicy,ZZ\n"
        res = parse_and_validate(csv, org_a)
        fields = {e.field for e in res.errors}
        assert "rating" in fields
        assert "country" in fields

    def test_xlsx_upload(self, org_a, admin_profile):
        import io

        from openpyxl import Workbook

        _set_rls(org_a)
        wb = Workbook()
        ws = wb.active
        ws.append(["full_name", "email", "phone_number", "company"])
        ws.append(["Excel Person", "xl@example.com", 7907017599, "XL Corp"])
        buf = io.BytesIO()
        wb.save(buf)

        res = parse_and_validate(buf.getvalue(), org_a)
        assert res.header_error is None
        assert res.summary["valid"] == 1
        row = res.valid[0]
        assert (row.first_name, row.last_name) == ("Excel", "Person")
        # Numeric Excel cell must not become "7907017599.0".
        assert row.phone == "7907017599"

        out = commit_rows(buf.getvalue(), org_a, admin_profile)
        assert out["created"] == 1

    def test_commit_refuses_when_errors(self, org_a, admin_profile):
        _set_rls(org_a)
        csv = b"full_name,email\nJane Roe,not-an-email\n"
        out = commit_rows(csv, org_a, admin_profile)
        assert out["error"] is True
        assert out["created"] == 0
        assert Lead.objects.filter(org=org_a).count() == 0


@pytest.mark.django_db
class TestManualCreatePhoneDedup:
    """The create endpoint blocks a phone already used by another lead."""

    def test_duplicate_phone_blocked(self, admin_client, org_a, admin_user):
        _set_rls(org_a)
        Lead.objects.create(
            title="Existing", phone="(202) 555-1234", org=org_a, created_by=admin_user
        )
        resp = admin_client.post(
            "/api/leads/",
            {"title": "New one", "phone": "+1 202 555 1234"},  # same number, new format
            format="json",
        )
        assert resp.status_code == 400
        assert "phone" in resp.json()["errors"]
