from django.db import migrations


def approve_existing_orgs(apps, schema_editor):
    """Orgs that already existed before the approval gate are grandfathered in
    as approved, so the seeded admin org and any live tenants keep working.
    Only orgs created after this migration start as 'pending'."""
    Org = apps.get_model("common", "Org")
    Org.objects.update(approval_status="approved")


def noop_reverse(apps, schema_editor):
    # No safe reverse: we can't tell which orgs were originally pending.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0028_org_approval_status_org_approved_at_org_approved_by_and_more"),
    ]

    operations = [
        migrations.RunPython(approve_existing_orgs, noop_reverse),
    ]
