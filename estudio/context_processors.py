from . import regras


def iniciais(usuario):
    """'Pedro Ruan' -> 'PE' (duas primeiras letras do primeiro nome, como o Pedro pediu)."""
    nome = (usuario.first_name or usuario.get_full_name() or usuario.username or "?").strip()
    return nome.split()[0][:2].upper() if nome else "?"


def meu_calendario(request):
    """Dados globais do usuário logado: badge do Meu Calendário e iniciais do avatar."""
    if not request.user.is_authenticated:
        return {}
    try:
        n = regras.convites_pendentes(request.user).count()
    except Exception:
        n = 0
    return {"meus_convites": n, "minhas_iniciais": iniciais(request.user)}
