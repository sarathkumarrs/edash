"""Signals for the leads app.

Keeps lead follow-up scheduling in sync with assignment so that a newly
assigned lead automatically becomes due today and surfaces on the dashboard
"New Leads to Contact" card and the Focus Bar follow-up count.
"""

from datetime import date

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from leads.models import Lead


@receiver(m2m_changed, sender=Lead.assigned_to.through)
def set_followup_on_assignment(sender, instance, action, pk_set, **kwargs):
    """Make a lead due today the first time someone is assigned to it.

    Fires whenever assignees are added (creation, later assignment, CSV import,
    admin). Only sets ``next_follow_up`` when it is currently empty, so a
    manually scheduled follow-up date is never overwritten.
    """
    if action != "post_add" or not pk_set:
        return
    if instance.next_follow_up is None:
        instance.next_follow_up = date.today()
        instance.save(update_fields=["next_follow_up"])
