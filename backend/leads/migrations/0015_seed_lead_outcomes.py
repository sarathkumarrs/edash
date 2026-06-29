"""Seed the default lead-interaction outcome dropdown for existing orgs.

New orgs get this via the org-creation flow (common.views.organization_views).
Admins can edit the options afterwards at /settings/custom-fields.
"""

from django.db import connection, migrations

from leads.outcomes import seed_default_outcomes


def _set_org_context(org_id):
    # custom_field_definition is RLS-protected and Django connects as a
    # non-superuser, so the INSERT needs app.current_org set for each org.
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_org', %s, false)", [str(org_id)]
        )


def seed_outcomes(apps, schema_editor):
    Org = apps.get_model("common", "Org")
    CustomFieldDefinition = apps.get_model("common", "CustomFieldDefinition")
    for org in Org.objects.all():
        _set_org_context(org.id)
        seed_default_outcomes(org, CustomFieldDefinition=CustomFieldDefinition)
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_org', '', false)")


def unseed_outcomes(apps, schema_editor):
    CustomFieldDefinition = apps.get_model("common", "CustomFieldDefinition")
    CustomFieldDefinition.objects.filter(
        target_model="LeadInteraction", key="outcome"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0014_leadinteraction"),
    ]

    operations = [
        migrations.RunPython(seed_outcomes, reverse_code=unseed_outcomes),
    ]
