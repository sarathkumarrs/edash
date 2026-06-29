"""Admin-managed outcome options for lead interactions.

The list of selectable outcomes for a logged contact is stored as a
``dropdown`` CustomFieldDefinition (target_model="LeadInteraction",
key="outcome"). Admins edit it at /settings/custom-fields. These helpers read
the active option values and seed a sensible default list for an org.
"""

OUTCOME_KEY = "outcome"
OUTCOME_TARGET = "LeadInteraction"

DEFAULT_OUTCOMES = [
    {"value": "connected", "label": "Connected"},
    {"value": "left_voicemail", "label": "Left voicemail"},
    {"value": "no_answer", "label": "No answer"},
    {"value": "email_sent", "label": "Email sent"},
    {"value": "meeting_booked", "label": "Meeting booked"},
    {"value": "not_interested", "label": "Not interested"},
]


def get_active_outcome_values(org):
    """Return the set of allowed outcome `value`s for an org (active only).

    Empty set means the admin has no active outcome list configured, in which
    case the API treats any/empty outcome as acceptable (outcome is optional).
    """
    from common.models import CustomFieldDefinition

    defn = CustomFieldDefinition.objects.filter(
        org=org,
        target_model=OUTCOME_TARGET,
        key=OUTCOME_KEY,
        field_type="dropdown",
        is_active=True,
    ).first()
    if not defn or not defn.options:
        return set()
    return {opt.get("value") for opt in defn.options if opt.get("value")}


def seed_default_outcomes(org, CustomFieldDefinition=None):
    """Create the default outcome dropdown for an org if it doesn't exist.

    Accepts an optional CustomFieldDefinition class so data migrations can pass
    the historical model via ``apps.get_model``.
    """
    if CustomFieldDefinition is None:
        from common.models import CustomFieldDefinition

    if CustomFieldDefinition.objects.filter(
        org=org, target_model=OUTCOME_TARGET, key=OUTCOME_KEY
    ).exists():
        return None

    return CustomFieldDefinition.objects.create(
        org=org,
        target_model=OUTCOME_TARGET,
        key=OUTCOME_KEY,
        label="Outcome",
        field_type="dropdown",
        options=DEFAULT_OUTCOMES,
        is_required=False,
        is_filterable=True,
        display_order=0,
        is_active=True,
    )
