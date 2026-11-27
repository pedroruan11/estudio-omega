from django.apps import AppConfig


class EstudioConfig(AppConfig):
    name = "estudio"

    def ready(self):
        from . import auditoria  # noqa: F401  (registra o sinal de login dos Acessos)
