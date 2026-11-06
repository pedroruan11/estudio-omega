"""Regras de negócio do Omega Studio.

Toda criação, cancelamento, remarcação e falta passa por aqui, para que as
regras valham igual em qualquer tela (e, no futuro, no atendente de IA do WhatsApp).
"""
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from .models import Agendamento, Configuracao, Debito, HorarioFuncionamento


class RegraErro(Exception):
    """Erro de regra de negócio com mensagem pronta para mostrar na tela."""


class ClienteNaBlacklist(RegraErro):
    def __init__(self, cliente):
        self.cliente = cliente
        super().__init__(f"{cliente} está na blacklist. Só um administrador pode concluir este agendamento.")


class SemPermissao(RegraErro):
    pass


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
        Agendamento.objects.no_intervalo(ini_dia, fim_dia).select_related("cliente", "contato").order_by("inicio")
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


def criar_agendamento(usuario, cliente, tipo, data, hora, horas, contato=None, confirmar_blacklist=False, observacao="", agora=None):
    if cliente.na_blacklist and not (usuario.is_admin and confirmar_blacklist):
        raise ClienteNaBlacklist(cliente)
    with transaction.atomic():
        cfg = _travar()
        inicio = _checar_horario(data, hora, horas, tipo, agora=agora)
        return Agendamento.objects.create(
            cliente=cliente,
            contato=contato or cliente.contato_principal,
            tipo=tipo,
            inicio=inicio,
            horas=horas,
            valor_hora=preco_hora(tipo, cfg),
            criado_por=usuario,
            observacao=observacao,
        )


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
        ag.inicio = novo_inicio
        ag.horas = horas
        ag.remarcacoes += 1
        ag.save()
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


def lancar_multa(usuario, cliente, valor, descricao):
    if not usuario.is_admin:
        raise SemPermissao("Só um administrador lança multas.")
    if valor is None or valor <= 0:
        raise RegraErro("Informe um valor maior que zero.")
    return Debito.objects.create(
        cliente=cliente, motivo=Debito.Motivo.AVULSO, valor=valor, descricao=descricao[:255], criado_por=usuario
    )
