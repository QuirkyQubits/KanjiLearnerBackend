from django.apps import AppConfig


class KanjilearnerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'kanjilearner'

    def ready(self):
        import kanjilearner.signals
