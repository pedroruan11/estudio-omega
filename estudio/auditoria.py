"""Auditoria (só Administrador): histórico de agendamentos e de acessos, por mês, guardado por 12 meses.

- Agendamentos: vem do registro de notificações (agendou, cancelou, remarcou, falta, convites...).
- Acessos: modelo Acesso, preenchido pelo AcessoMiddleware e pelo sinal de login.
"""
from datetime import timedelta

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from .models import Acesso, Notificacao

MESES_GUARDADOS = 12
INATIVIDADE = timedelta(minutes=30)
ATUALIZA_A_CADA = timedelta(minutes=2)

TIPOS_AGENDAMENTO = [
    Notificacao.Tipo.AGENDOU, Notificacao.Tipo.CANCELOU, Notificacao.Tipo.REMARCOU, Notificacao.Tipo.FALTA,
    Notificacao.Tipo.DIRECIONOU, Notificacao.Tipo.ACEITOU, Notificacao.Tipo.RECUSOU, Notificacao.Tipo.EXPIROU,
    Notificacao.Tipo.CONVITE_CANCELADO,
]

# O que cada ação (POST) significa, pro "o que fez" dos Acessos. As ações que já viram notificação
# (agendar, cancelar, remarcar, falta, convites, multa, blacklist, travar) vêm das notificações.
ACOES = {
    "lembrete_marcar": "marcou lembrete como enviado",
    "dias_indisponiveis": "salvou dias impedidos",
    "cliente_novo": "cadastrou cliente",
    "cliente_editar": "editou cliente",
    "cliente_anotacao": "anotou na ficha de cliente",
    "debito_quitar": "deu baixa em débito",
    "financeiro_quitar": "deu baixa em débito",
    "cobranca_pagou": "confirmou multa paga",
    "cobranca_nao_pagou": "marcou multa não paga",
    "financeiro_configurar": "alterou preços/taxas",
    "financeiro_despesas": "salvou as despesas",
    "configuracoes": "alterou horário da sala",
    "usuario_novo": "criou usuário",
    "usuario_editar": "editou usuário",
    "usuario_senha": "redefiniu senha de usuário",
    "trocar_senha": "trocou a própria senha",
    "agenda_celular": "gerou link da agenda do celular",
    "backup_gerar": "gerou backup",
    "backup_drive": "enviou backup ao Drive",
    "backup_excluir": "excluiu backup",
    "backup_restaurar": "restaurou backup",
    "backup_restaurar_arquivo": "restaurou backup de arquivo",
}

IGNORAR = ("/static/", "/saude", "/sw.js", "/manifest", "/favicon", "/entrar", "/sair")


def dispositivo(ua):
    ua = (ua or "").lower()
    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "Android"
    if "windows" in ua:
        return "Computador (Windows)"
    if "mac os" in ua or "macintosh" in ua:
        return "Computador (Mac)"
    if "linux" in ua:
        return "Computador (Linux)"
    return "Outro"


def _ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", ""))[:45]


def _novo_acesso(request, agora, com_senha=False):
    a = Acesso.objects.create(
        usuario=request.user, inicio=agora, ultimo=agora, com_senha=com_senha,
        dispositivo=dispositivo(request.META.get("HTTP_USER_AGENT")), ip=_ip(request),
    )
    request.session["acesso_id"] = a.pk
    return a


@receiver(user_logged_in)
def _ao_entrar(sender, request, user, **kwargs):
    try:
        if request is not None and hasattr(request, "session"):
            _novo_acesso(request, timezone.now(), com_senha=True)
    except Exception:
        pass


def registrar(request, response):
    """Chamado pelo middleware depois de cada resposta. Nunca pode quebrar a tela."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated) or request.path.startswith(IGNORAR):
        return
    eh_post = request.method == "POST"
    if not eh_post and (request.path.endswith((".json", ".ics")) or response.status_code >= 400):
        return
    agora = timezone.now()
    a = None
    aid = request.session.get("acesso_id")
    if aid:
        a = Acesso.objects.filter(pk=aid, usuario=user).first()
    if a is None or agora - a.ultimo > INATIVIDADE:
        a = _novo_acesso(request, agora)
    campos = []
    if agora - a.ultimo > ATUALIZA_A_CADA or eh_post:
        a.ultimo = agora
        campos.append("ultimo")
    if eh_post and response.status_code < 400:
        nome = getattr(getattr(request, "resolver_match", None), "url_name", None)
        rotulo = ACOES.get(nome)
        # Tela de formulário que voltou com erro (200) não conta; sucesso redireciona (302).
        if rotulo and response.status_code in (301, 302, 303):
            a.acoes = (a.acoes or []) + [{"h": timezone.localtime(agora).strftime("%H:%M"), "t": rotulo}]
            campos.append("acoes")
    if campos:
        a.save(update_fields=campos)


def limpar_antigos(agora=None):
    """Guarda só os últimos 12 meses de auditoria (acessos e registros de agendamentos)."""
    agora = agora or timezone.now()
    corte = primeiro_dia_meses_atras(timezone.localdate(agora), MESES_GUARDADOS - 1)
    from .regras import inicio_em

    limite = inicio_em(corte, 0)
    Acesso.objects.filter(inicio__lt=limite).delete()
    Notificacao.objects.filter(criado_em__lt=limite).delete()


def primeiro_dia_meses_atras(hoje, n):
    ano, mes = hoje.year, hoje.month - n
    while mes < 1:
        mes += 12
        ano -= 1
    return hoje.replace(year=ano, month=mes, day=1)


def ultimos_meses(hoje=None, n=MESES_GUARDADOS):
    """Primeiro dia dos últimos n meses, do mais antigo ao atual."""
    hoje = hoje or timezone.localdate()
    return [primeiro_dia_meses_atras(hoje, k) for k in range(n - 1, -1, -1)]


def registros_de_agendamentos(ini, fim):
    """Tudo que foi feito com agendamentos no período, sem repetir o mesmo fato (ex.: 'agendou' + 'agendou no seu dia')."""
    qs = list(
        Notificacao.objects.filter(criado_em__gte=ini, criado_em__lt=fim, tipo__in=TIPOS_AGENDAMENTO)
        .select_related("autor", "cliente", "agendamento").order_by("-criado_em", "-id")
    )
    agendou = {}
    for n in qs:
        if n.tipo == Notificacao.Tipo.AGENDOU and n.agendamento_id:
            agendou.setdefault((n.agendamento_id, n.autor_id), []).append(n.criado_em)
    saida, vistos = [], set()
    for n in qs:
        if n.tipo == Notificacao.Tipo.DIRECIONOU and any(
            abs((t - n.criado_em).total_seconds()) < 10 for t in agendou.get((n.agendamento_id, n.autor_id), [])
        ):
            continue  # é o aviso pessoal de um agendamento que já aparece como "agendou"
        chave = (n.tipo, n.agendamento_id, n.autor_id, n.texto, n.criado_em.replace(microsecond=0))
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(n)
    return saida
