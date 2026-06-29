"""Central registry of toggleable CRM modules.

A workspace (Org) shows only the modules in its ``enabled_modules`` list. The
superadmin controls this from the Django admin. Keep these keys in sync with the
frontend registry at ``frontend/src/lib/modules.js``.

Always-on shell areas (Home, profile, settings, users, org selection) are NOT
listed here — they are never gated.
"""

# (key, human label) — order is the order shown in the admin checkbox list.
MODULE_CHOICES = (
    ("leads", "Leads"),
    ("contacts", "Contacts"),
    ("accounts", "Accounts"),
    ("deals", "Deals (Opportunities)"),
    ("tickets", "Tickets / Knowledge base"),
    ("tasks", "Tasks"),
    ("timesheet", "Timesheet"),
    ("goals", "Goals"),
    ("invoices", "Invoices"),
    ("helpdesk", "Help desk"),
)

ALL_MODULE_KEYS = [key for key, _ in MODULE_CHOICES]


def default_enabled_modules():
    """New orgs start with every module enabled; the superadmin trims."""
    return list(ALL_MODULE_KEYS)
