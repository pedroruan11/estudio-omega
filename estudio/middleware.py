from django.shortcuts import redirect

_ja_tem_usuario = False

LIVRES = ("/saude", "/static/", "/primeiro-acesso", "/manifest.webmanifest", "/sw.js")


class PrimeiroAcessoMiddleware:
    """Enquanto não existir nenhum usuário, manda tudo para a tela de primeiro acesso."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        global _ja_tem_usuario
        if not _ja_tem_usuario and not request.path.startswith(LIVRES):
            from .models import Usuario

            if Usuario.objects.exists():
                _ja_tem_usuario = True
            else:
                return redirect("primeiro_acesso")
        return self.get_response(request)
