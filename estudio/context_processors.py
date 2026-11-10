from . import regras


def meu_calendario(request):
    """Badge do rodapé: quantos convites de responsável estão esperando resposta do usuário logado."""
    if not request.user.is_authenticated:
        return {}
    try:
        n = regras.convites_pendentes(request.user).count()
    except Exception:
        n = 0
    return {"meus_convites": n}
