"""Relatórios e Auditoria (só Administrador)."""
from datetime import date, timedelta

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from . import auditoria as aud
from . import regras
from . import relatorios as rel
from .models import Acesso, Notificacao
from .views import MESES, admin_required, brl

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _baixar(conteudo, nome):
    resp = HttpResponse(conteudo, content_type=XLSX)
    resp["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resp


def _brl_curto(v):
    v = float(v)
    if abs(v) >= 1000:
        s = f"{v / 1000:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{s} mil"
    return f"{v:.0f}"


# ---------- Relatórios ----------

@admin_required
def relatorios(request):
    return render(request, "estudio/relatorios.html", {"aba": "mais"})


@admin_required
def relatorio_ensaios(request):
    linhas = rel.dados_ensaios()
    hoje = timezone.localdate()
    if request.GET.get("formato") == "xlsx":
        return _baixar(rel.planilha(
            "Ensaios por mês",
            ["Mês", "Ensaios", "Horas de ensaio", "Gravações", "Horas de gravação", "Cancelados", "Faltas", "Valor dos ensaios"],
            [[l["rotulo"], l["ensaios"], l["horas_ensaio"], l["gravacoes"], l["horas_gravacao"], l["cancelados"],
              l["faltas"], l["valor_ensaios"]] for l in linhas],
            [None, "int", "int", "int", "int", "int", "int", "brl"],
        ), f"omega-ensaios-por-mes-{hoje:%Y-%m}.xlsx")
    g = rel.grafico(
        [l["rotulo"] for l in linhas],
        [{"nome": "Ensaios", "cor": rel.COR_1, "valores": [l["ensaios"] for l in linhas]},
         {"nome": "Gravações", "cor": rel.COR_2, "valores": [l["gravacoes"] for l in linhas]}],
        formato=lambda v: f"{v:.0f}",
    )
    dicas = [{"rotulo": l["rotulo"], "linhas": [f"Ensaios: {l['ensaios']} ({l['horas_ensaio']}h)",
                                                 f"Gravações: {l['gravacoes']} ({l['horas_gravacao']}h)"]} for l in linhas]
    atual = linhas[-1]
    return render(request, "estudio/relatorio.html", {
        "titulo": "Ensaios por mês",
        "destaque": f"{atual['ensaios']} ensaio{'s' if atual['ensaios'] != 1 else ''}",
        "destaque_sub": f"em {MESES[hoje.month - 1]} · {atual['horas_ensaio']}h de sala",
        "g": g, "dicas": dicas,
        "cabecalho": ["Mês", "Ensaios", "Horas", "Gravações", "Canc.", "Faltas"],
        "linhas": [{"c": [l["rotulo"], l["ensaios"], f"{l['horas_ensaio']}h", l["gravacoes"], l["cancelados"], l["faltas"]],
                    "neg": False} for l in reversed(linhas)],
        "nota": "Últimos 12 meses. Contam só os agendamentos ativos (cancelados e faltas aparecem à parte).",
        "aba": "mais",
    })


@admin_required
def relatorio_receitas(request):
    linhas = rel.dados_receitas()
    hoje = timezone.localdate()
    if request.GET.get("formato") == "xlsx":
        return _baixar(rel.planilha(
            "Receitas - despesas",
            ["Mês", "Ensaios", "Gravações", "Receitas", "Despesas", "Resultado"],
            [[l["rotulo"], l["ensaios"], l["gravacoes"], l["receita"], l["despesa"], l["resultado"]] for l in linhas],
            [None, "brl", "brl", "brl", "brl", "brl"],
        ), f"omega-receitas-despesas-{hoje:%Y-%m}.xlsx")
    g = rel.grafico(
        [l["rotulo"] for l in linhas],
        [{"nome": "Receitas", "cor": rel.COR_1, "valores": [l["receita"] for l in linhas]},
         {"nome": "Despesas", "cor": rel.COR_2, "valores": [l["despesa"] for l in linhas]},
         {"nome": "Resultado", "cor": rel.COR_3, "valores": [l["resultado"] for l in linhas]}],
        formato=_brl_curto,
    )
    dicas = [{"rotulo": l["rotulo"], "linhas": [f"Receitas: {brl(l['receita'])}", f"Despesas: {brl(l['despesa'])}",
                                                 f"Resultado: {'−' if l['resultado'] < 0 else ''}{brl(abs(l['resultado']))}"]}
             for l in linhas]
    atual = linhas[-1]
    neg = atual["resultado"] < 0
    return render(request, "estudio/relatorio.html", {
        "titulo": "Receitas − despesas",
        "destaque": f"{'− ' if neg else ''}{brl(abs(atual['resultado']))}",
        "destaque_neg": neg,
        "destaque_sub": f"resultado de {MESES[hoje.month - 1]}",
        "g": g, "dicas": dicas,
        "cabecalho": ["Mês", "Receitas", "Despesas", "Resultado"],
        "linhas": [{"c": [l["rotulo"], brl(l["receita"]), brl(l["despesa"]),
                          ("− " if l["resultado"] < 0 else "") + brl(abs(l["resultado"]))],
                    "neg": l["resultado"] < 0} for l in reversed(linhas)],
        "nota": "Últimos 12 meses. Receitas = valor estimado dos ensaios e gravações ativos; despesas = média mensal atual cadastrada em Financeiro → Despesas.",
        "aba": "mais",
    })


# ---------- Auditoria ----------

def _abas_meses(request):
    meses = list(reversed(aud.ultimos_meses()))
    escolhido = meses[0]
    try:
        a, m = map(int, request.GET.get("m", "").split("-"))
        pedido = date(a, m, 1)
        if pedido in meses:
            escolhido = pedido
    except ValueError:
        pass
    i = meses.index(escolhido)  # meses vai do atual (0) ao mais antigo (11)
    nav = {
        "titulo": f"{MESES[escolhido.month - 1].capitalize()} {escolhido.year}",
        "anterior": f"{meses[i + 1]:%Y-%m}" if i + 1 < len(meses) else "",
        "proxima": f"{meses[i - 1]:%Y-%m}" if i > 0 else "",
    }
    ini, fim = rel._intervalo(escolhido)
    return nav, escolhido, ini, fim


def _por_dia(itens, quando):
    dias = []
    for it in itens:
        d = timezone.localtime(quando(it)).date()
        if not dias or dias[-1]["dia"] != d:
            dias.append({"dia": d, "itens": []})
        dias[-1]["itens"].append(it)
    return dias


@admin_required
def auditoria(request):
    aud.limpar_antigos()
    return render(request, "estudio/auditoria.html", {"aba": "mais"})


ESTILO_TIPO = {
    Notificacao.Tipo.AGENDOU: ("Agendou", "ok"),
    Notificacao.Tipo.CANCELOU: ("Cancelou", "perigo"),
    Notificacao.Tipo.REMARCOU: ("Remarcou", ""),
    Notificacao.Tipo.FALTA: ("Falta", "perigo"),
    Notificacao.Tipo.DIRECIONOU: ("Técnico", "cinza"),
    Notificacao.Tipo.ACEITOU: ("Aceitou", "cinza"),
    Notificacao.Tipo.RECUSOU: ("Recusou", "cinza"),
    Notificacao.Tipo.EXPIROU: ("Expirou", "cinza"),
    Notificacao.Tipo.CONVITE_CANCELADO: ("Convite cancelado", "cinza"),
}


@admin_required
def auditoria_agendamentos(request):
    aud.limpar_antigos()
    nav, escolhido, ini, fim = _abas_meses(request)
    registros = aud.registros_de_agendamentos(ini, fim)
    for r in registros:
        r.rotulo_tipo, r.estilo = ESTILO_TIPO.get(r.tipo, (r.get_tipo_display(), "cinza"))
        r.quem = (r.autor.get_full_name() or r.autor.username) if r.autor else "Sistema"
    contagem = {}
    for r in registros:
        contagem[r.rotulo_tipo] = contagem.get(r.rotulo_tipo, 0) + 1
    return render(request, "estudio/auditoria_agendamentos.html", {
        "nav": nav, "mes": f"{MESES[escolhido.month - 1].capitalize()} {escolhido.year}",
        "dias": _por_dia(registros, lambda r: r.criado_em), "total": len(registros),
        "contagem": sorted(contagem.items(), key=lambda kv: -kv[1]),
        "aba": "mais",
    })


@admin_required
def auditoria_acessos(request):
    aud.limpar_antigos()
    nav, escolhido, ini, fim = _abas_meses(request)
    acessos = list(Acesso.objects.filter(inicio__gte=ini, inicio__lt=fim).select_related("usuario"))
    feitos = list(Notificacao.objects.filter(criado_em__gte=ini - timedelta(hours=1), criado_em__lt=fim + timedelta(hours=1),
                                             autor__isnull=False).order_by("criado_em"))
    # Uma ação vira notificação só uma vez por fato; as pessoais (destinatário) repetem o fato.
    feitos = [n for n in feitos if n.destinatario_id is None or n.tipo in (Notificacao.Tipo.ACEITOU, Notificacao.Tipo.RECUSOU)]
    por_usuario = {}
    for n in feitos:
        por_usuario.setdefault(n.autor_id, []).append(n)
    resumo = {}
    for a in acessos:
        fim_janela = a.ultimo + timedelta(minutes=1)
        lista = [{"h": timezone.localtime(n.criado_em).strftime("%H:%M"), "t": n.texto}
                 for n in por_usuario.get(a.usuario_id, []) if a.inicio - timedelta(seconds=5) <= n.criado_em <= fim_janela]
        a.feito = sorted(lista + list(a.acoes or []), key=lambda x: x["h"])
        a.nome = a.usuario.get_full_name() or a.usuario.username
        dur = int((a.ultimo - a.inicio).total_seconds() // 60)
        a.duracao = "menos de 1 min" if dur < 1 else (f"{dur} min" if dur < 60 else f"{dur // 60}h{dur % 60:02d}")
        r = resumo.setdefault(a.nome, {"nome": a.nome, "n": 0})
        r["n"] += 1
    return render(request, "estudio/auditoria_acessos.html", {
        "nav": nav, "mes": f"{MESES[escolhido.month - 1].capitalize()} {escolhido.year}",
        "dias": _por_dia(acessos, lambda a: a.inicio), "total": len(acessos),
        "resumo": sorted(resumo.values(), key=lambda r: -r["n"]),
        "aba": "mais",
    })
