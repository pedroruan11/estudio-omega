"""Telas de gestão (fase 2): Financeiro, Estatísticas, Configurações e Backup. Só Administrador,
exceto 'Trocar minha senha' (na fase 1)."""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import backup as bkp
from . import regras
from .forms import FinanceiroForm, HorarioFormSet, RedefinirSenhaForm, UsuarioEditarForm, UsuarioNovoForm
from .models import Agendamento, Backup, Cliente, Configuracao, Debito, HorarioFuncionamento, Usuario
from .views import MESES, admin_required, brl


# ---------- Financeiro ----------

@admin_required
def financeiro(request):
    cfg = Configuracao.atual()
    form = FinanceiroForm(request.POST or None, instance=cfg)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Valores atualizados. Valem para os próximos agendamentos; os já marcados mantêm o preço da época.")
        return redirect("financeiro")
    abertos = Debito.objects.filter(quitado_em__isnull=True).select_related("cliente", "agendamento")
    quitados = Debito.objects.filter(quitado_em__isnull=False).select_related("cliente", "quitado_por").order_by("-quitado_em")[:20]
    return render(request, "estudio/financeiro.html", {
        "form": form,
        "abertos": abertos,
        "total_aberto": brl(abertos.aggregate(t=Sum("valor"))["t"] or 0),
        "quitados": quitados,
        "aba": "mais",
    })


@admin_required
@require_POST
def financeiro_quitar(request, pk):
    d = get_object_or_404(Debito, pk=pk)
    try:
        regras.quitar_debito(request.user, d)
    except regras.RegraErro as e:
        messages.error(request, str(e))
    else:
        extra = "" if d.cliente.na_blacklist else f" {d.cliente} saiu da blacklist."
        messages.success(request, f"Débito de {brl(d.valor)} de {d.cliente} quitado.{extra}")
    return redirect("financeiro")


# ---------- Estatísticas ----------

def _mes_param(request):
    hoje = timezone.localdate()
    try:
        ano, mes = map(int, request.GET.get("m", "").split("-"))
        return date(ano, mes, 1)
    except ValueError:
        return hoje.replace(day=1)


@admin_required
def estatisticas(request):
    base = _mes_param(request)
    ultimo = calendar.monthrange(base.year, base.month)[1]
    ini = regras.inicio_em(base, 0)
    fim = regras.inicio_em(base.replace(day=ultimo), 0) + timedelta(days=1)

    no_mes = Agendamento.objects.filter(inicio__gte=ini, inicio__lt=fim)
    validos = no_mes.filter(status=Agendamento.Status.AGENDADO)
    ensaios = validos.filter(tipo=Agendamento.Tipo.ENSAIO)
    gravacoes = validos.filter(tipo=Agendamento.Tipo.GRAVACAO)
    horas = validos.aggregate(h=Sum("horas"))["h"] or 0
    valor = sum((a.valor_total for a in validos.only("valor_hora", "horas")), Decimal("0"))
    valor_ensaio = sum((a.valor_total for a in ensaios.only("valor_hora", "horas")), Decimal("0"))
    valor_grav = valor - valor_ensaio

    disponiveis = 0
    por_dia_semana = [0] * 7
    d = base
    while d.month == base.month:
        j = HorarioFuncionamento.do_dia(d)
        if j:
            disponiveis += j[1] - j[0]
        d += timedelta(days=1)
    for a in validos.only("inicio", "horas"):
        por_dia_semana[timezone.localtime(a.inicio).weekday()] += a.horas
    maior = max(por_dia_semana) or 1
    dias_semana = [
        {"nome": n, "horas": h, "pct": int(h * 100 / maior)}
        for n, h in zip(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"], por_dia_semana)
    ]

    ranking = (
        validos.values("cliente__id", "cliente__nome")
        .annotate(horas=Sum("horas"), qtd=Count("id"))
        .order_by("-horas", "-qtd")[:10]
    )
    maior_r = ranking[0]["horas"] if ranking else 1
    ranking = [{**r, "pct": int(r["horas"] * 100 / maior_r)} for r in ranking]

    taxas_geradas = Debito.objects.filter(criado_em__gte=ini, criado_em__lt=fim)
    taxas_recebidas = Debito.objects.filter(quitado_em__gte=ini, quitado_em__lt=fim)

    novos = Cliente.objects.filter(criado_em__gte=ini, criado_em__lt=fim)
    origens_qs = Cliente.objects.exclude(origem="").values("origem").annotate(n=Count("id")).order_by("-n")
    rotulos = dict(Cliente.Origem.choices)
    total_or = sum(o["n"] for o in origens_qs) or 1
    origens = [{"nome": rotulos.get(o["origem"], o["origem"]), "n": o["n"], "pct": int(o["n"] * 100 / total_or)} for o in origens_qs]

    ant = (base - timedelta(days=1)).replace(day=1)
    prox = base.replace(day=ultimo) + timedelta(days=1)
    return render(request, "estudio/estatisticas.html", {
        "titulo": f"{MESES[base.month - 1].capitalize()} {base.year}",
        "anterior": f"{ant.year}-{ant.month:02d}",
        "proxima": f"{prox.year}-{prox.month:02d}",
        "qtd_ensaios": ensaios.count(),
        "qtd_gravacoes": gravacoes.count(),
        "horas": horas,
        "disponiveis": disponiveis,
        "ocupacao": int(horas * 100 / disponiveis) if disponiveis else 0,
        "valor": brl(valor),
        "valor_ensaio": brl(valor_ensaio),
        "valor_grav": brl(valor_grav),
        "cancelados": no_mes.filter(status=Agendamento.Status.CANCELADO).count(),
        "faltas": no_mes.filter(status=Agendamento.Status.FALTA).count(),
        "taxas_geradas": brl(taxas_geradas.aggregate(t=Sum("valor"))["t"] or 0),
        "taxas_recebidas": brl(taxas_recebidas.aggregate(t=Sum("valor"))["t"] or 0),
        "ranking": ranking,
        "dias_semana": dias_semana,
        "novos": novos.count(),
        "origens": origens,
        "aba": "mais",
    })


# ---------- Configurações ----------

@admin_required
def configuracoes(request):
    formset = HorarioFormSet(request.POST or None, queryset=HorarioFuncionamento.objects.order_by("dia_semana"), prefix="h")
    if request.method == "POST" and formset.is_valid():
        formset.save()
        messages.success(request, "Horários da sala atualizados.")
        return redirect("configuracoes")
    usuarios = Usuario.objects.order_by("-is_active", "first_name", "username")
    return render(request, "estudio/configuracoes.html", {"formset": formset, "usuarios": usuarios, "aba": "mais"})


@admin_required
def usuario_novo(request):
    form = UsuarioNovoForm(request.POST or None, initial={"perfil": Usuario.Perfil.EDICAO})
    if request.method == "POST" and form.is_valid():
        u = form.save()
        messages.success(request, f"Usuário {u.username} criado. Passe a senha provisória para a pessoa e peça para trocar no primeiro acesso.")
        return redirect("configuracoes")
    return render(request, "estudio/usuario_form.html", {"form": form, "novo": True, "aba": "mais"})


def _admins_ativos_exceto(u):
    return Usuario.objects.filter(is_active=True, perfil=Usuario.Perfil.ADMIN).exclude(pk=u.pk).count()


@admin_required
def usuario_editar(request, pk):
    u = get_object_or_404(Usuario, pk=pk)
    era_admin = u.perfil == Usuario.Perfil.ADMIN  # o form altera a instância ao validar
    form = UsuarioEditarForm(request.POST or None, instance=u)
    senha_form = RedefinirSenhaForm(u)
    if request.method == "POST" and form.is_valid():
        perde_admin = era_admin and (
            form.cleaned_data["perfil"] != Usuario.Perfil.ADMIN or not form.cleaned_data["is_active"]
        )
        if perde_admin and _admins_ativos_exceto(u) == 0:
            messages.error(request, "Precisa existir pelo menos um Administrador ativo.")
        elif u == request.user and not form.cleaned_data["is_active"]:
            messages.error(request, "Você não pode desativar o seu próprio usuário.")
        else:
            form.save()
            messages.success(request, "Usuário atualizado.")
            return redirect("configuracoes")
    return render(request, "estudio/usuario_form.html", {"form": form, "senha_form": senha_form, "u": u, "aba": "mais"})


@admin_required
@require_POST
def usuario_senha(request, pk):
    u = get_object_or_404(Usuario, pk=pk)
    form = RedefinirSenhaForm(u, request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, f"Senha de {u.username} redefinida. Passe a nova senha para a pessoa.")
        return redirect("configuracoes")
    return render(request, "estudio/usuario_form.html", {"form": UsuarioEditarForm(instance=u), "senha_form": form, "u": u, "aba": "mais"})


# ---------- Backup ----------

@admin_required
def backups(request):
    lista = Backup.objects.defer("conteudo").select_related("criado_por")[:60]
    ultimo = Backup.objects.defer("conteudo").first()
    return render(request, "estudio/backups.html", {
        "lista": lista,
        "ultimo": ultimo,
        "drive": bkp.drive_configurado(),
        "aba": "mais",
    })


@admin_required
@require_POST
def backup_gerar(request):
    b = bkp.gerar(request.user, Backup.Tipo.MANUAL)
    if b.drive_status == "enviado":
        messages.success(request, f"Backup criado e enviado ao Google Drive ({b.registros} registros).")
    elif b.drive_status == "erro":
        messages.warning(request, f"Backup criado aqui, mas o envio ao Drive falhou: {b.drive_detalhe}")
    else:
        messages.success(request, f"Backup criado ({b.registros} registros).")
    return redirect("backups")


@admin_required
def backup_baixar(request, pk):
    b = get_object_or_404(Backup, pk=pk)
    resp = HttpResponse(bytes(b.conteudo), content_type="application/gzip")
    resp["Content-Disposition"] = f'attachment; filename="{b.nome_arquivo}"'
    return resp


@admin_required
@require_POST
def backup_drive(request, pk):
    b = get_object_or_404(Backup, pk=pk)
    if bkp.enviar_para_drive(b):
        messages.success(request, "Enviado ao Google Drive.")
    else:
        messages.error(request, f"Não foi possível enviar ao Drive. {b.drive_detalhe}")
    return redirect("backups")


@admin_required
@require_POST
def backup_excluir(request, pk):
    b = get_object_or_404(Backup, pk=pk)
    b.delete()
    messages.success(request, "Backup excluído (a cópia no Google Drive, se houver, continua lá).")
    return redirect("backups")


FRASE = "RESTAURAR"


@admin_required
def backup_restaurar(request, pk=None):
    b = get_object_or_404(Backup.objects.defer("conteudo"), pk=pk) if pk else None
    erro = None
    if request.method == "POST":
        if request.POST.get("frase", "").strip().upper() != FRASE:
            erro = f"Para confirmar, digite {FRASE}."
        else:
            try:
                if b:
                    texto = bkp.conteudo_json(Backup.objects.get(pk=b.pk))
                    bkp.ler_arquivo_enviado(_ArquivoTexto(texto))  # valida
                else:
                    arq = request.FILES.get("arquivo")
                    if not arq:
                        raise ValueError("Escolha o arquivo de backup.")
                    texto = bkp.ler_arquivo_enviado(arq)
                bkp.restaurar(texto, request.user)
            except Exception as e:
                erro = f"Não foi possível restaurar: {e}"
            else:
                messages.success(request, "Dados restaurados. Um backup de segurança do estado anterior foi guardado na lista.")
                return redirect("backups")
    return render(request, "estudio/backup_restaurar.html", {"b": b, "erro": erro, "frase": FRASE, "aba": "mais"})


class _ArquivoTexto:
    def __init__(self, texto):
        self._t = texto

    def read(self):
        return self._t.encode("utf-8")
