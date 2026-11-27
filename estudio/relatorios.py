"""Relatórios (só Administrador): ensaios por mês e receitas − despesas, últimos 12 meses,
com gráfico de linha (SVG feito no servidor) e exportação para Excel."""
import calendar
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.db.models import Sum

from . import regras
from .auditoria import ultimos_meses
from .models import Agendamento, Despesa

MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Cores validadas (dataviz/validate_palette.js) contra a superfície escura #141312: todas as checagens passam.
COR_1 = "#D28E05"  # dourado/âmbar: ensaios, receitas
COR_2 = "#338CED"  # azul: gravações, despesas
COR_3 = "#00A888"  # verde-água: resultado


def _intervalo(base):
    ultimo = calendar.monthrange(base.year, base.month)[1]
    return regras.inicio_em(base, 0), regras.inicio_em(base.replace(day=ultimo), 0) + timedelta(days=1)


def rotulo_mes(base):
    return f"{MESES_CURTOS[base.month - 1]}/{base.year % 100:02d}"


def dados_ensaios(hoje=None):
    linhas = []
    for base in ultimos_meses(hoje):
        ini, fim = _intervalo(base)
        no_mes = Agendamento.objects.filter(inicio__gte=ini, inicio__lt=fim)
        ativos = no_mes.filter(status=Agendamento.Status.AGENDADO)
        ensaios = ativos.filter(tipo=Agendamento.Tipo.ENSAIO)
        gravacoes = ativos.filter(tipo=Agendamento.Tipo.GRAVACAO)
        linhas.append({
            "mes": base,
            "rotulo": rotulo_mes(base),
            "ensaios": ensaios.count(),
            "horas_ensaio": ensaios.aggregate(h=Sum("horas"))["h"] or 0,
            "gravacoes": gravacoes.count(),
            "horas_gravacao": gravacoes.aggregate(h=Sum("horas"))["h"] or 0,
            "cancelados": no_mes.filter(status=Agendamento.Status.CANCELADO).count(),
            "faltas": no_mes.filter(status=Agendamento.Status.FALTA).count(),
            "valor_ensaios": sum((a.valor_total for a in ensaios.only("valor_hora", "horas")), Decimal("0")),
        })
    return linhas


def dados_receitas(hoje=None):
    from .views_gestao import receita_do_mes

    despesa = Despesa.total_mensal()
    linhas = []
    for base in ultimos_meses(hoje):
        r = receita_do_mes(base)
        linhas.append({
            "mes": base,
            "rotulo": rotulo_mes(base),
            "ensaios": r["valor_ensaio"],
            "gravacoes": r["valor_grav"],
            "receita": r["valor"],
            "despesa": despesa,
            "resultado": r["valor"] - despesa,
        })
    return linhas


# ---------- gráfico de linha (SVG) ----------

def _passo_bonito(bruto):
    if bruto <= 0:
        return 1
    exp = 10 ** (len(str(int(bruto))) - 1)
    for m in (1, 2, 2.5, 5, 10):
        if bruto <= m * exp:
            return m * exp
    return 10 * exp


def grafico(rotulos, series, largura=340, altura=210, formato=None):
    """series: [{"nome", "cor", "valores": [...]}]. Devolve tudo pronto pro template _grafico.html."""
    formato = formato or (lambda v: f"{v:g}")

    def n(v):  # número pro SVG sempre com ponto (o template formataria "46,5" em pt-BR)
        return f"{v:.1f}"
    esq, dir_, topo, base = 46, 20, 12, 26
    w, h = largura - esq - dir_, altura - topo - base
    todos = [float(v) for s in series for v in s["valores"]] or [0]
    vmin, vmax = min(0.0, min(todos)), max(0.0, max(todos))
    if vmax == vmin:
        vmax = vmin + 1
    passo = _passo_bonito((vmax - vmin) / 4)
    lo = passo * int(vmin // passo) if vmin < 0 else 0
    hi = lo
    while hi < vmax:
        hi += passo
    hi = max(hi, lo + passo)
    qtd = len(rotulos)

    def x(i):
        return esq + (w * i / (qtd - 1) if qtd > 1 else w / 2)

    def y(v):
        return topo + h - (float(v) - lo) * h / (hi - lo)

    ticks = []
    v = lo
    while v <= hi + 1e-9:
        ticks.append({"y": n(y(v)), "x_rot": n(esq - 6), "rotulo": formato(v), "zero": abs(v) < 1e-9})
        v += passo
    saida = []
    for s in series:
        pts = [(round(x(i), 1), round(y(val), 1)) for i, val in enumerate(s["valores"])]
        saida.append({**s, "caminho": "M" + " L".join(f"{a},{b}" for a, b in pts),
                      "pontos": [{"x": n(a), "y": n(b)} for a, b in pts]})
    colunas = [{"x": n(x(i)), "rotulo": r, "mostrar": (i % 2 == (qtd - 1) % 2)} for i, r in enumerate(rotulos)]
    return {
        "largura": largura, "altura": altura, "esq": esq, "dir": largura - dir_, "topo": topo, "chao": topo + h,
        "ticks": ticks, "series": saida, "colunas": colunas, "base_rotulos": altura - 6,
    }


# ---------- Excel ----------

def planilha(titulo, cabecalho, linhas, formatos):
    """formatos: um por coluna: None, "int" ou "brl"."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31]
    ws.append(cabecalho)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1C1A18")
        c.alignment = Alignment(horizontal="center")
    for linha in linhas:
        ws.append([float(v) if isinstance(v, Decimal) else v for v in linha])
    for col, fmt in enumerate(formatos, start=1):
        for row in range(2, ws.max_row + 1):
            if fmt == "brl":
                ws.cell(row, col).number_format = '"R$" #,##0.00;[Red]-"R$" #,##0.00'
            elif fmt == "int":
                ws.cell(row, col).number_format = "0"
        largura = max(len(str(ws.cell(r, col).value or "")) for r in range(1, ws.max_row + 1))
        ws.column_dimensions[ws.cell(1, col).column_letter].width = max(12, largura + 4)
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
