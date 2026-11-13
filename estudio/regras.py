"""Regras de negócio do Omega Studio.

Toda criação, cancelamento, remarcação e falta passa por aqui, para que as
regras valham igual em qualquer tela (e, no futuro, no atendente de IA do WhatsApp).
"""
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    Agendamento, Configuracao, ConviteResponsavel, Debito, HorarioFuncionamento, Notificacao,
    UsuarioDiaIndisponivel, Usuario,
)


class RegraErro(Exception):
    """Erro de regra de negócio com mensagem pronta para mostrar na tela."""


class ClienteNaBlacklist(RegraErro):
    def __init__(self, cliente):
        self.cliente = cliente
        super().__init__(f"{cliente} está na blacklist. Só um administrador pode concluir este agendamento.")


class SemPermissao(RegraErro):
    pass


# ---------- notificações (feed do sininho) ----------

_DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _quando(ag):
    ini, fim = timezone.localtime(ag.inicio), timezone.localtime(ag.fim)
    return f"{_DIAS[ini.weekday()]} {ini:%d/%m}, {ini:%H}h–{fim:%H}h"


def _tipo_txt(ag):
    return ag.get_tipo_display().lower()


def notificar(autor, tipo, texto, ag=None, destinatario=None, cliente=None):
    """Registra no feed. Nunca pode atrapalhar a operação principal."""
    try:
        return Notificacao.objects.create(
            autor=autor if getattr(autor, "pk", None) else None, tipo=tipo, texto=texto[:255],
            agendamento=ag, cliente=cliente or (ag.cliente if ag else None), destinatario=destinatario,
        )
    except Exception:
        return None


def notificacoes_do_usuario(usuario, desde=None):
    """O que os outros fizeram (geral da equipe ou direcionado a esse usuário)."""
    from django.db.models import Q

    qs = (
        Notificacao.objects.filter(Q(destinatario__isnull=True) | Q(destinatario=usuario))
        .exclude(autor=usuario)
        .select_related("autor", "agendamento", "cliente")
    )
    if desde:
        qs = qs.filter(criado_em__gte=desde)
    return qs


def notificacoes_nao_lidas(usuario):
    qs = notificacoes_do_usuario(usuario)
    if usuario.notificacoes_vistas_em:
        qs = qs.filter(criado_em__gt=usuario.notificacoes_vistas_em)
    return qs


# ---------- tempo ----------

def inicio_em(data, hora):
    return timezone.make_aware(datetime.combine(data, time(hour=hora)))


def esta_no_prazo_de_taxa(agendamento, agora=None, cfg=None):
    """True quando faltam menos de 48h (ou o configurado) para o início."""
    cfg = cfg or Configuracao.atual()
    agora = agora or timezone.now()
    return agora > agendamento.inicio - timedelta(hours=cfg.antecedencia_horas)


# ---------- valores ----------

def preco_hora(tipo, cfg=None):
    cfg = cfg or Configuracao.atual()
    return cfg.preco_ensaio if tipo == Agendamento.Tipo.ENSAIO else cfg.preco_gravacao


def percentual_taxa(tipo, cfg=None):
    cfg = cfg or Configuracao.atual()
    return cfg.taxa_ensaio_pct if tipo == Agendamento.Tipo.ENSAIO else cfg.taxa_gravacao_pct


def valor_taxa(agendamento, cfg=None):
    pct = Decimal(percentual_taxa(agendamento.tipo, cfg))
    return (agendamento.valor_total * pct / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------- duração e janela ----------

def limites_duracao(tipo, cfg=None):
    cfg = cfg or Configuracao.atual()
    minimo = cfg.min_horas_ensaio if tipo == Agendamento.Tipo.ENSAIO else cfg.min_horas_gravacao
    return minimo, cfg.max_horas


def validar_duracao(tipo, horas, cfg=None):
    minimo, maximo = limites_duracao(tipo, cfg)
    if horas < minimo:
        nome = "Ensaio" if tipo == Agendamento.Tipo.ENSAIO else "Gravação"
        raise RegraErro(f"{nome} precisa de no mínimo {minimo}h.")
    if horas > maximo:
        raise RegraErro(f"O máximo por agendamento é {maximo}h.")


def validar_janela(data, hora, horas):
    janela = HorarioFuncionamento.do_dia(data)
    if janela is None:
        raise RegraErro("A sala não funciona nesse dia.")
    abre, fecha = janela
    if hora < abre or hora + horas > fecha:
        fim = (hora + horas) % 24
        raise RegraErro(
            f"Fora do horário da sala ({abre:02d}:00–{fecha % 24:02d}:00). "
            f"O agendamento {hora:02d}:00–{fim:02d}:00 não cabe."
        )


def conflitos(inicio, fim, ignorar_id=None):
    qs = Agendamento.objects.no_intervalo(inicio, fim)
    if ignorar_id:
        qs = qs.exclude(pk=ignorar_id)
    return qs


def horarios_livres(data, tipo, horas, ignorar_id=None, agora=None):
    """Horas de início possíveis para essa duração nesse dia."""
    janela = HorarioFuncionamento.do_dia(data)
    if janela is None:
        return []
    abre, fecha = janela
    agora = agora or timezone.now()
    dia_ini = inicio_em(data, 0)
    ocupados = list(
        Agendamento.objects.no_intervalo(dia_ini, dia_ini + timedelta(days=1, hours=6))
        .exclude(pk=ignorar_id or 0)
        .values_list("inicio", "fim")
    )
    livres = []
    for h in range(abre, fecha - horas + 1):
        ini = inicio_em(data, h)
        fim = ini + timedelta(hours=horas)
        if ini <= agora:
            continue
        if any(ini < f and fim > i for i, f in ocupados):
            continue
        livres.append(h)
    return livres


def faixas_do_dia(data):
    """Linha do tempo do dia: blocos ocupados e livres dentro do horário da sala."""
    janela = HorarioFuncionamento.do_dia(data)
    if janela is None:
        return []
    abre, fecha = janela
    ini_dia, fim_dia = inicio_em(data, abre), inicio_em(data, 0) + timedelta(hours=fecha)
    ags = list(
        Agendamento.objects.no_intervalo(ini_dia, fim_dia).select_related("cliente", "contato", "responsavel", "responsavel_convidado").order_by("inicio")
    )
    faixas, cursor = [], ini_dia
    for ag in ags:
        if ag.inicio > cursor:
            faixas.append({"livre": True, "inicio": cursor, "fim": ag.inicio, "horas": int((ag.inicio - cursor).total_seconds() // 3600)})
        faixas.append({"livre": False, "inicio": ag.inicio, "fim": ag.fim, "ag": ag, "horas": ag.horas})
        cursor = max(cursor, ag.fim)
    if cursor < fim_dia:
        faixas.append({"livre": True, "inicio": cursor, "fim": fim_dia, "horas": int((fim_dia - cursor).total_seconds() // 3600)})
    return faixas


# ---------- operações ----------

def _travar():
    """Serializa agendamentos concorrentes (dois celulares marcando o mesmo horário)."""
    return Configuracao.objects.select_for_update().get_or_create(pk=1)[0]


def _checar_horario(data, hora, horas, tipo, ignorar_id=None, agora=None):
    validar_duracao(tipo, horas)
    validar_janela(data, hora, horas)
    inicio = inicio_em(data, hora)
    agora = agora or timezone.now()
    if inicio <= agora:
        raise RegraErro("Não dá para agendar num horário que já passou.")
    fim = inicio + timedelta(hours=horas)
    choque = conflitos(inicio, fim, ignorar_id).select_related("cliente").first()
    if choque:
        ini = timezone.localtime(choque.inicio)
        fim_c = timezone.localtime(choque.fim)
        raise RegraErro(f"Horário ocupado por {choque.cliente} ({ini:%H:%M}–{fim_c:%H:%M}).")
    return inicio


def pode_transferir_responsavel(data, agora=None):
    """Só dá para escolher outra pessoa pra acompanhar em ensaios a partir de amanhã
    (regra do Pedro, 09/11/2026): no mesmo dia há risco de a pessoa não ver a tempo."""
    agora = agora or timezone.now()
    return data > timezone.localdate(agora)


def usuarios_bloqueados_em(data):
    """IDs de quem marcou que não pode acompanhar ensaios/gravações nesse dia."""
    return set(UsuarioDiaIndisponivel.objects.filter(data=data).values_list("usuario_id", flat=True))


def usuarios_disponiveis_para_responsavel(data):
    """Usuários ativos que podem ser escolhidos como responsável nesse dia."""
    bloqueados = usuarios_bloqueados_em(data)
    qs = Usuario.objects.filter(is_active=True).order_by("first_name", "username")
    return [u for u in qs if u.pk not in bloqueados]


def criar_agendamento(
    usuario, cliente, tipo, data, hora, horas, contato=None, confirmar_blacklist=False,
    observacao="", agora=None, responsavel=None,
):
    if cliente.na_blacklist and not (usuario.is_admin and confirmar_blacklist):
        raise ClienteNaBlacklist(cliente)
    agora = agora or timezone.now()
    responsavel = responsavel or usuario
    if responsavel.pk != usuario.pk:
        if not pode_transferir_responsavel(data, agora):
            raise RegraErro("Só é possível escolher outra pessoa pra acompanhar em ensaios a partir de amanhã.")
        if responsavel.pk in usuarios_bloqueados_em(data):
            raise RegraErro(f"{responsavel} marcou que não pode acompanhar nesse dia.")
    with transaction.atomic():
        cfg = _travar()
        inicio = _checar_horario(data, hora, horas, tipo, agora=agora)
        pendente = responsavel.pk != usuario.pk
        # Enquanto o convidado não aceita, quem agendou continua sendo o responsável de fato.
        ag = Agendamento.objects.create(
            cliente=cliente,
            contato=contato or cliente.contato_principal,
            tipo=tipo,
            inicio=inicio,
            horas=horas,
            valor_hora=preco_hora(tipo, cfg),
            criado_por=usuario,
            observacao=observacao,
            responsavel=usuario,
            responsavel_convidado=responsavel if pendente else None,
            responsavel_status=Agendamento.RespStatus.PENDENTE if pendente else Agendamento.RespStatus.ACEITO,
            responsavel_definido_em=agora,
        )
        if pendente:
            ConviteResponsavel.objects.create(agendamento=ag, convidado=responsavel, convidado_por=usuario)
        notificar(usuario, Notificacao.Tipo.AGENDOU, f"agendou {_tipo_txt(ag)} de {cliente} · {_quando(ag)}", ag)
        if pendente:
            notificar(usuario, Notificacao.Tipo.DIRECIONOU,
                      f"direcionou pra você o {_tipo_txt(ag)} de {cliente} · {_quando(ag)}. Aceite ou recuse em Meu Calendário.",
                      ag, destinatario=responsavel)
        return ag


def _gerar_debito(usuario, ag, motivo, cfg):
    valor = valor_taxa(ag, cfg)
    pct = percentual_taxa(ag.tipo, cfg)
    ini = timezone.localtime(ag.inicio)
    return Debito.objects.create(
        cliente=ag.cliente,
        agendamento=ag,
        motivo=motivo,
        valor=valor,
        criado_por=usuario,
        descricao=f"{ag.get_tipo_display()} de {ag.horas}h em {ini:%d/%m %H:%M} · taxa de {pct}%",
    )


def previa_cancelamento(ag, agora=None):
    """O que acontece se cancelar agora: (tem_taxa, valor)."""
    cfg = Configuracao.atual()
    if esta_no_prazo_de_taxa(ag, agora, cfg):
        return True, valor_taxa(ag, cfg)
    return False, Decimal("0")


def cancelar(usuario, ag, agora=None):
    if ag.status != Agendamento.Status.AGENDADO:
        raise RegraErro("Esse agendamento não está ativo.")
    agora = agora or timezone.now()
    with transaction.atomic():
        cfg = _travar()
        debito = None
        if esta_no_prazo_de_taxa(ag, agora, cfg):
            debito = _gerar_debito(usuario, ag, Debito.Motivo.CANCELAMENTO, cfg)
        ag.status = Agendamento.Status.CANCELADO
        ag.cancelado_em = agora
        ag.cancelado_por = usuario
        ag.save()
        notificar(usuario, Notificacao.Tipo.CANCELOU,
                  f"cancelou {_tipo_txt(ag)} de {ag.cliente} · {_quando(ag)}" + (" (com taxa)" if debito else ""), ag)
    return debito


def remarcar(usuario, ag, data, hora, horas=None, agora=None):
    if ag.status != Agendamento.Status.AGENDADO:
        raise RegraErro("Esse agendamento não está ativo.")
    agora = agora or timezone.now()
    horas = horas or ag.horas
    with transaction.atomic():
        cfg = _travar()
        tardio = esta_no_prazo_de_taxa(ag, agora, cfg)
        if tardio and not usuario.is_admin:
            raise SemPermissao("Faltam menos de 48h para o horário: só um administrador pode remarcar.")
        novo_inicio = _checar_horario(data, hora, horas, ag.tipo, ignorar_id=ag.pk, agora=agora)
        debito = _gerar_debito(usuario, ag, Debito.Motivo.REMARCACAO, cfg) if tardio else None
        antes = _quando(ag)
        ag.inicio = novo_inicio
        ag.horas = horas
        ag.remarcacoes += 1
        ag.save()
        notificar(usuario, Notificacao.Tipo.REMARCOU, f"remarcou {_tipo_txt(ag)} de {ag.cliente}: {antes} → {_quando(ag)}", ag)
    return debito


def marcar_falta(usuario, ag, agora=None):
    agora = agora or timezone.now()
    if ag.status != Agendamento.Status.AGENDADO:
        raise RegraErro("Esse agendamento não está ativo.")
    if agora < ag.inicio:
        raise RegraErro("Só dá para marcar falta depois do horário de início.")
    with transaction.atomic():
        cfg = _travar()
        debito = _gerar_debito(usuario, ag, Debito.Motivo.FALTA, cfg)
        ag.status = Agendamento.Status.FALTA
        ag.save()
        notificar(usuario, Notificacao.Tipo.FALTA, f"marcou falta de {ag.cliente} · {_quando(ag)}", ag)
    return debito


def quitar_debito(usuario, debito, agora=None):
    if not usuario.is_admin:
        raise SemPermissao("Só um administrador pode dar baixa em débitos.")
    if debito.quitado_em:
        raise RegraErro("Esse débito já foi quitado.")
    debito.quitado_em = agora or timezone.now()
    debito.quitado_por = usuario
    debito.save()
    if not debito.cliente.debitos_abertos().exists():
        _liberar_blacklist_manual(usuario, debito.cliente)
    return debito


def _liberar_blacklist_manual(usuario, cliente):
    """Multa paga: a banda sai também da blacklist manual (regra do Pedro, 06/11/2026)."""
    if cliente.blacklist_manual:
        from .models import Anotacao

        motivo = cliente.motivo_blacklist
        cliente.blacklist_manual = False
        cliente.motivo_blacklist = ""
        cliente.save(update_fields=["blacklist_manual", "motivo_blacklist"])
        Anotacao.objects.create(
            cliente=cliente, autor=usuario,
            texto=f"Saiu da blacklist ao pagar a multa (motivo anterior: {motivo or 'não informado'}).",
        )


def tirar_da_blacklist(usuario, cliente):
    if not usuario.is_admin:
        raise SemPermissao("Só um administrador pode tirar um cliente da blacklist.")
    cliente.blacklist_manual = False
    cliente.motivo_blacklist = ""
    cliente.save()


def avisos_do_contato(cliente):
    """Débitos em aberto de qualquer banda dos contatos deste cliente (só aviso)."""
    avisos = []
    vistos = set()
    for v in cliente.vinculos.select_related("contato"):
        for d in v.contato.debitos_abertos().select_related("cliente"):
            if d.pk in vistos or d.cliente_id == cliente.pk:
                continue
            vistos.add(d.pk)
            avisos.append({"contato": v.contato, "debito": d})
    return avisos


# ---------- cobrança de multa no dia do ensaio ----------

def multa_a_cobrar(cliente):
    """Total de débitos em aberto do cliente (o que deve ser cobrado junto com o próximo ensaio)."""
    return cliente.total_em_aberto()


def pendencias_cobranca(agora=None):
    """Agendamentos que já terminaram, de clientes com multa em aberto, ainda não conferidos."""
    agora = agora or timezone.now()
    com_debito = Debito.objects.filter(quitado_em__isnull=True).values("cliente_id")
    return (
        Agendamento.objects.ativos()
        .filter(fim__lte=agora, cobranca_conferida=False, cliente_id__in=com_debito)
        .select_related("cliente")
        .order_by("fim")
    )


def confirmar_pagamento_multa(usuario, ag, agora=None):
    """Banda pagou a multa junto com o ensaio: dá baixa em todos os débitos em aberto dela."""
    if not usuario.is_admin:
        raise SemPermissao("Só um administrador confirma o pagamento da multa.")
    agora = agora or timezone.now()
    with transaction.atomic():
        quitados = list(ag.cliente.debitos_abertos())
        for d in quitados:
            d.quitado_em = agora
            d.quitado_por = usuario
            d.save(update_fields=["quitado_em", "quitado_por"])
        Agendamento.objects.filter(cliente=ag.cliente, cobranca_conferida=False, fim__lte=agora).update(cobranca_conferida=True)
        _liberar_blacklist_manual(usuario, ag.cliente)
    return quitados


def multa_nao_paga(usuario, ag):
    """A banda ensaiou mas não pagou a multa: some o aviso deste ensaio; o débito e a blacklist continuam."""
    ag.cobranca_conferida = True
    ag.save(update_fields=["cobranca_conferida"])


# ---------- responsável por acompanhar ----------
#
# `responsavel` é sempre quem vai atender de fato. Um convite em aberto fica em
# `responsavel_convidado` (status PENDENTE): se for aceito, o convidado vira o responsável;
# se for recusado ou expirar, nada muda e o responsável atual continua (regra do Pedro, 12/11/2026).

def convites_pendentes(usuario):
    """Convites que esse usuário recebeu e ainda não respondeu."""
    return (
        Agendamento.objects.ativos()
        .filter(responsavel_convidado=usuario, responsavel_status=Agendamento.RespStatus.PENDENTE)
        .select_related("cliente", "responsavel", "criado_por")
        .order_by("inicio")
    )


def responsabilidades_aceitas(usuario, agora=None):
    """Tudo o que esse usuário vai acompanhar daqui pra frente: inclusive os que ele mesmo agendou,
    os convites que ele mandou e ainda não foram aceitos e os que foram recusados/expiraram
    (nesses casos quem atende é ele)."""
    agora = agora or timezone.now()
    return (
        Agendamento.objects.ativos()
        .filter(responsavel=usuario, fim__gte=agora)
        .select_related("cliente", "responsavel_convidado")
        .order_by("inicio")
    )


def historico_convites(usuario, limite=10):
    return (
        ConviteResponsavel.objects.filter(
            convidado=usuario, status__in=[Agendamento.RespStatus.RECUSADO, Agendamento.RespStatus.EXPIRADO]
        )
        .select_related("agendamento", "agendamento__cliente", "agendamento__criado_por")
        .order_by("-criado_em")[:limite]
    )


def convites_enviados(usuario, agora=None):
    """Convites que esse usuário mandou pra outra pessoa acompanhar (só de ensaios/gravações que
    ainda vão acontecer), com o status de cada um. Tela 'Agendamentos que direcionei'."""
    agora = agora or timezone.now()
    return (
        ConviteResponsavel.objects.filter(
            convidado_por=usuario,
            agendamento__status=Agendamento.Status.AGENDADO,
            agendamento__fim__gte=agora,
        )
        .select_related("agendamento", "agendamento__cliente", "agendamento__responsavel", "convidado")
        .order_by("agendamento__inicio", "-criado_em")
    )


def _fechar_convite(ag, status, agora):
    convite = (
        ag.convites_responsavel.filter(status=Agendamento.RespStatus.PENDENTE, convidado_id=ag.responsavel_convidado_id)
        .order_by("-criado_em").first()
    )
    if convite:
        convite.status = status
        convite.respondido_em = agora
        convite.save(update_fields=["status", "respondido_em"])
    # convites antigos que tenham ficado pendurados
    ag.convites_responsavel.filter(status=Agendamento.RespStatus.PENDENTE).update(status=status, respondido_em=agora)
    return convite


def responder_convite(usuario, ag, aceitar, agora=None):
    """Retorna (agendamento, convite)."""
    agora = agora or timezone.now()
    if ag.responsavel_convidado_id != usuario.pk or ag.responsavel_status != Agendamento.RespStatus.PENDENTE:
        raise RegraErro("Esse convite não está mais disponível pra você responder.")
    with transaction.atomic():
        convite = _fechar_convite(ag, Agendamento.RespStatus.ACEITO if aceitar else Agendamento.RespStatus.RECUSADO, agora)
        if aceitar:
            ag.responsavel = usuario
            ag.responsavel_definido_em = agora
        ag.responsavel_convidado = None
        ag.responsavel_status = Agendamento.RespStatus.ACEITO
        ag.save(update_fields=["responsavel", "responsavel_convidado", "responsavel_status", "responsavel_definido_em"])
        avisar = (convite.convidado_por if convite else None) or ag.criado_por
        if aceitar:
            notificar(usuario, Notificacao.Tipo.ACEITOU,
                      f"aceitou acompanhar o {_tipo_txt(ag)} de {ag.cliente} · {_quando(ag)}", ag, destinatario=avisar)
        else:
            notificar(usuario, Notificacao.Tipo.RECUSOU,
                      f"recusou acompanhar o {_tipo_txt(ag)} de {ag.cliente} · {_quando(ag)}. Continua com {ag.responsavel}.",
                      ag, destinatario=avisar)
    return ag, convite


def trocar_responsavel(usuario, ag, novo, agora=None):
    """Passa o acompanhamento pra outra pessoa. Só quem agendou ou o responsável atual podem.
    O novo precisa aceitar no app; até lá (e se recusar ou não responder) continua o atual."""
    agora = agora or timezone.now()
    if ag.status != Agendamento.Status.AGENDADO:
        raise RegraErro("Esse agendamento não está ativo.")
    if not ag.pode_trocar_responsavel(usuario):
        raise SemPermissao("Só quem fez o agendamento ou quem está acompanhando pode trocar o responsável.")
    if novo is None or not novo.is_active:
        raise RegraErro("Escolha quem vai acompanhar.")
    if novo.pk == ag.responsavel_id:
        raise RegraErro(f"{novo} já é o responsável.")
    data = timezone.localdate(ag.inicio)
    if not pode_transferir_responsavel(data, agora):
        raise RegraErro("Só dá pra passar o acompanhamento pra outra pessoa a partir de amanhã. Hoje, quem está responsável atende.")
    if novo.pk in usuarios_bloqueados_em(data):
        raise RegraErro(f"{novo} marcou que não pode acompanhar nesse dia.")
    with transaction.atomic():
        if ag.responsavel_pendente:  # já havia um convite em aberto: é substituído
            _fechar_convite(ag, Agendamento.RespStatus.EXPIRADO, agora)
        ag.responsavel_convidado = novo
        ag.responsavel_status = Agendamento.RespStatus.PENDENTE
        ag.save(update_fields=["responsavel_convidado", "responsavel_status"])
        ConviteResponsavel.objects.create(agendamento=ag, convidado=novo, convidado_por=usuario)
        notificar(usuario, Notificacao.Tipo.DIRECIONOU,
                  f"direcionou pra você o {_tipo_txt(ag)} de {ag.cliente} · {_quando(ag)}. Aceite ou recuse em Meu Calendário.",
                  ag, destinatario=novo)
    return ag


def cancelar_convite(usuario, ag, agora=None):
    """Desiste do convite em aberto: o responsável atual continua."""
    agora = agora or timezone.now()
    if not ag.responsavel_pendente:
        raise RegraErro("Não há convite em aberto nesse agendamento.")
    if not ag.pode_trocar_responsavel(usuario):
        raise SemPermissao("Só quem fez o agendamento ou quem está acompanhando pode mexer no responsável.")
    with transaction.atomic():
        _fechar_convite(ag, Agendamento.RespStatus.EXPIRADO, agora)
        if ag.responsavel_convidado:
            notificar(usuario, Notificacao.Tipo.CONVITE_CANCELADO,
                      f"cancelou o convite pra você acompanhar o {_tipo_txt(ag)} de {ag.cliente} · {_quando(ag)}",
                      ag, destinatario=ag.responsavel_convidado)
        ag.responsavel_convidado = None
        ag.responsavel_status = Agendamento.RespStatus.ACEITO
        ag.save(update_fields=["responsavel_convidado", "responsavel_status"])
    return ag


def expirar_convites_pendentes(agora=None):
    """Convites sem resposta até 1 dia antes do início expiram; o responsável atual continua.
    Retorna [(agendamento, usuario_que_nao_respondeu, quem_convidou), ...]."""
    agora = agora or timezone.now()
    expirados = []
    pendentes = (
        Agendamento.objects.ativos()
        .filter(responsavel_status=Agendamento.RespStatus.PENDENTE, inicio__lte=agora + timedelta(days=1))
        .select_related("criado_por", "responsavel", "responsavel_convidado", "cliente")
    )
    with transaction.atomic():
        for ag in pendentes:
            convidado = ag.responsavel_convidado
            convite = _fechar_convite(ag, Agendamento.RespStatus.EXPIRADO, agora)
            ag.responsavel_convidado = None
            ag.responsavel_status = Agendamento.RespStatus.ACEITO
            if ag.responsavel_id is None:
                ag.responsavel = ag.criado_por
            ag.save(update_fields=["responsavel", "responsavel_convidado", "responsavel_status"])
            quem = convite.convidado_por if convite else ag.criado_por
            expirados.append((ag, convidado, quem))
            if quem:
                notificar(None, Notificacao.Tipo.EXPIROU,
                          f"O convite pra {convidado} acompanhar o {_tipo_txt(ag)} de {ag.cliente} ({_quando(ag)}) "
                          f"expirou sem resposta. Continua com {ag.responsavel}.", ag, destinatario=quem)
    return expirados


def bloquear_dia(usuario, data):
    UsuarioDiaIndisponivel.objects.get_or_create(usuario=usuario, data=data)


def desbloquear_dia(usuario, data):
    UsuarioDiaIndisponivel.objects.filter(usuario=usuario, data=data).delete()


# ---------- lembrete do dia (meio-dia) ----------

def agendamentos_de_hoje_para_lembrar(agora=None):
    agora = agora or timezone.now()
    hoje = timezone.localdate(agora)
    return (
        Agendamento.objects.ativos()
        .filter(inicio__gte=inicio_em(hoje, 0), inicio__lt=inicio_em(hoje, 0) + timedelta(days=1))
        .select_related("cliente", "contato")
        .order_by("inicio")
    )


def marcar_lembrete_enviado(ag, agora=None):
    ag.lembrete_enviado_em = agora or timezone.now()
    ag.save(update_fields=["lembrete_enviado_em"])


def lancar_multa(usuario, cliente, valor, descricao):
    if not usuario.is_admin:
        raise SemPermissao("Só um administrador lança multas.")
    if valor is None or valor <= 0:
        raise RegraErro("Informe um valor maior que zero.")
    d = Debito.objects.create(
        cliente=cliente, motivo=Debito.Motivo.AVULSO, valor=valor, descricao=descricao[:255], criado_por=usuario
    )
    notificar(usuario, Notificacao.Tipo.MULTA, f"lançou multa pra {cliente}: {descricao[:120]}", cliente=cliente)
    return d


# ---------- horários disponíveis (varinha mágica da Agenda) ----------

DIAS_SEMANA_CURTO = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def janelas_livres(dias=20, agora=None, minimo_horas=None):
    """Blocos livres da sala nos próximos `dias` dias (a partir de hoje), só os que comportam
    pelo menos `minimo_horas` (padrão: mínimo do ensaio). Retorna [(data, [(ini_h, fim_h), ...]), ...]
    com horas inteiras (fim pode ser 24 = meia-noite). Poucas consultas ao banco."""
    agora = agora or timezone.now()
    cfg = Configuracao.atual()
    minimo = minimo_horas or cfg.min_horas_ensaio
    hoje = timezone.localdate(agora)
    horarios = {h.dia_semana: h for h in HorarioFuncionamento.objects.all()}
    ini_total = inicio_em(hoje, 0)
    fim_total = inicio_em(hoje + timedelta(days=dias), 0) + timedelta(hours=6)
    ocupados = list(Agendamento.objects.no_intervalo(ini_total, fim_total).values_list("inicio", "fim"))
    resultado = []
    for i in range(dias):
        d = hoje + timedelta(days=i)
        h = horarios.get(d.weekday())
        if h is None:
            abre, fecha = HorarioFuncionamento.PADRAO[d.weekday()]
        elif not h.aberto:
            continue
        else:
            abre, fecha = h.abre, h.fecha
        livres = []
        for hora in range(abre, fecha):
            ini = inicio_em(d, 0) + timedelta(hours=hora)
            fim = ini + timedelta(hours=1)
            livre = ini > agora and not any(ini < f and fim > o for o, f in ocupados)
            if livre and livres and livres[-1][1] == hora:
                livres[-1][1] = hora + 1
            elif livre:
                livres.append([hora, hora + 1])
        blocos = [(a, b) for a, b in livres if b - a >= minimo]
        if blocos:
            resultado.append((d, blocos))
    return resultado


def texto_horarios_disponiveis(dias=20, agora=None):
    """Mensagem pronta pra colar no WhatsApp do cliente com os horários livres."""
    def h(x):
        return "00h" if x % 24 == 0 else f"{x:02d}h"

    linhas = ["🎸 *Omega Studio – horários disponíveis*", f"(próximos {dias} dias)", ""]
    janelas = janelas_livres(dias, agora)
    if not janelas:
        linhas.append("No momento a agenda está cheia nos próximos dias. Me chama que a gente encaixa! 🙏")
    for d, blocos in janelas:
        faixas = " · ".join(f"{h(a)} às {h(b)}" for a, b in blocos)
        linhas.append(f"*{DIAS_SEMANA_CURTO[d.weekday()]} {d:%d/%m}:* {faixas}")
    linhas += ["", "Me fala o dia e o horário que fica melhor pra vocês que eu já reservo! 🤘"]
    return "\n".join(linhas)
