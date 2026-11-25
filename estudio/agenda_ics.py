"""Agenda do celular: arquivo .ics (iCalendar) com o que cada pessoa vai acompanhar.

O celular "assina" o link e atualiza sozinho. Cada ensaio/gravação vira um evento com
lembrete 1 dia antes. Cancelados e os que passaram pra outra pessoa somem do feed.
"""
from datetime import timedelta

from django.utils import timezone

from .models import Agendamento

ENDERECO = "Omega Studio – Av. dos Autonomistas, 4905, sala 7 – Osasco"
HISTORICO_DIAS = 30  # mantém os últimos 30 dias na agenda


def _texto(v):
    return (str(v or "").replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _dobrar(linha):
    """Quebra linhas longas (máx. 75 bytes) como manda o padrão iCalendar."""
    b = linha.encode("utf-8")
    if len(b) <= 75:
        return linha
    partes, atual, limite = [], b"", 75
    for ch in linha:
        c = ch.encode("utf-8")
        if len(atual) + len(c) > limite:
            partes.append(atual.decode("utf-8"))
            atual, limite = b"", 74
        atual += c
    partes.append(atual.decode("utf-8"))
    return "\r\n ".join(partes)


def _utc(dt):
    return dt.astimezone(timezone.UTC).strftime("%Y%m%dT%H%M%SZ")


def agendamentos_do_usuario(usuario, agora=None):
    agora = agora or timezone.now()
    return (
        Agendamento.objects.ativos()
        .filter(responsavel=usuario, fim__gte=agora - timedelta(days=HISTORICO_DIAS))
        .select_related("cliente")
        .order_by("inicio")
    )


def gerar_ics(usuario, url_app="", agora=None):
    agora = agora or timezone.now()
    carimbo = _utc(agora)
    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omega Studio//Agenda//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Omega Studio",
        "X-WR-TIMEZONE:America/Sao_Paulo",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for ag in agendamentos_do_usuario(usuario, agora):
        detalhes = [f"{ag.get_tipo_display()} de {ag.cliente}"]
        if ag.pratos:
            detalhes.append("Com aluguel de pratos")
        if ag.observacao:
            detalhes.append(f"Obs.: {ag.observacao}")
        if url_app:
            detalhes.append(f"{url_app}/agendamentos/{ag.pk}/")
        titulo = f"{ag.get_tipo_display()} · {ag.cliente}"
        linhas += [
            "BEGIN:VEVENT",
            f"UID:agendamento-{ag.pk}@estudio-omega",
            f"DTSTAMP:{carimbo}",
            f"DTSTART:{_utc(ag.inicio)}",
            f"DTEND:{_utc(ag.fim)}",
            f"SUMMARY:{_texto(titulo)}",
            f"LOCATION:{_texto(ENDERECO)}",
            f"DESCRIPTION:{_texto(chr(10).join(detalhes))}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
        ]
        if url_app:
            linhas.append(f"URL:{url_app}/agendamentos/{ag.pk}/")
        linhas += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_texto('Amanhã: ' + titulo)}",
            "TRIGGER:-P1D",
            "END:VALARM",
            "END:VEVENT",
        ]
    linhas.append("END:VCALENDAR")
    return "\r\n".join(_dobrar(l) for l in linhas) + "\r\n"
