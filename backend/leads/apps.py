from django.apps import AppConfig


class LeadsConfig(AppConfig):
    name = "leads"

    def ready(self):
        import leads.signals  # noqa: F401  # pylint: disable=unused-import
