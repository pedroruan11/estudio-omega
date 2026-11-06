import calendar
from datetime import date, timedelta
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import regras
from .forms import AgendamentoForm, ClienteEditarForm, ClienteForm, PrimeiroAcessoForm, RemarcarForm
from .models import (
    Agendamento,
    Backup,
    Anotacao,
    Cliente,
    Configuracao,
    Contato,
    Debito,
    HorarioFuncionamento,
    Usuario,
    Vinculo,
    normalizar_whatsapp,
)

DIAS_CURTOS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
DIAS_LONGOS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
ENDERECO = "Av. dos Autonomistas, 4905, sala 7 – Osasco"


def brl(valor):
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + (s[:-3] if s.endswith(",00") else s)


def data_extenso(d):
    return f"{DIAS_LONGOS[d.weekday()].lower()}, {d:%d/%m}"


def admin_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(wrapper)


def texto_janela(janela):
    if not janela:
        return ""
    return f"{janela[0]:02d}:00–{janela[1] % 24:02d}:00"


def parse_data(valor, padrao=None):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return padrao


# ---------- sistema ----------

def saude(request):
    """Rota leve para o 'despertador' (não consulta o banco)."""
    return HttpResponse("ok", content_type="text/plain")


def manifest(request):
    from django.templatetags.static import static

    dados = {
        "name": "Omega Studio",
        "short_name": "Omega",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#000000",
        "lang": "pt-BR",
        "icons": [
            {"src": static("estudio/img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("estudio/img/logo-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("estudio/img/icon-512-maskable.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return JsonResponse(dados, content_type="application/manifest+json")


def service_worker(request):
    js = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>self.clients.claim());self.addEventListener('fetch',()=>{});"
    return HttpResponse(js, content_type="application/javascript")


def primeiro_acesso(request):
    if Usuario.objects.exists():
        return redirect("login")
    form = PrimeiroAcessoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if Usuario.objects.select_for_update().exists():
                return redirect("login")
            user = form.save(commit=False)
            user.perfil = Usuario.Perfil.ADMIN
            user.is_superuser = True
            user.save()
        login(request, user)
        messages.success(request, "Pronto! Você é o primeiro administrador do sistema.")
        return redirect("inicio")
    return render(request, "estudio/primeiro_acesso.html", {"form": form})


class Entrar(auth_views.LoginView):
    template_name = "estudio/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        resp = super().form_valid(form)
        if not self.request.POST.get("lembrar"):
            self.request.session.set_expiry(0)
        return resp


class TrocarSenha(auth_views.PasswordChangeView):
    template_name = "estudio/trocar_senha.html"

    def get_success_url(self):
        messages.success(self.request, "Senha alterada.")
        return reverse("mais")


# ---------- início e agenda ----------

def _ocupacao(data):
    janela = HorarioFuncionamento.do_dia(data)
    if not janela:
        return 0, 0
    total = janela[1] - janela[0]
    ini = regras.inicio_em(data, janela[0])
    fim = regras.inicio_em(data, 0) + timedelta(hours=janela[1])
    usadas = Agendamento.objects.no_intervalo(ini, fim).aggregate(h=Sum("horas"))["h"] or 0
    return usadas, total


def _faixas_contexto(data):
    faixas = regras.faixas_do_dia(data)
    for f in faixas:
        f["ini"] = timezone.localtime(f["inicio"])
        f["fim_l"] = timezone.localtime(f["fim"])
        if not f["livre"]:
            f["whats"] = link_whatsapp_lembrete(f["ag"])
    return faixas


@login_required
def inicio(request):
    from .backup import backup_automatico_se_preciso

    try:
        backup_automatico_se_preciso()
    except Exception:  # backup nunca pode derrubar a tela inicial
        pass
    hoje = timezone.localdate()
    faixas = _faixas_contexto(hoje)
    ocupadas = sum(f["horas"] for f in faixas if not f["livre"])
    livres = sum(f["horas"] for f in faixas if f["livre"])
    janela = HorarioFuncionamento.do_dia(hoje)
    amanha = hoje + timedelta(days=1)
    proximos = (
        Agendamento.objects.ativos()
        .filter(inicio__gte=regras.inicio_em(amanha, 0), inicio__lt=regras.inicio_em(amanha, 0) + timedelta(days=1))
        .select_related("cliente")
    )
    return render(request, "estudio/inicio.html", {
        "hoje": hoje,
        "dia_curto": f"{DIAS_CURTOS[hoje.weekday()]} · {hoje:%d} {MESES[hoje.month - 1][:3].upper()}",
        "faixas": faixas,
        "qtd": sum(1 for f in faixas if not f["livre"]),
        "ocupadas": ocupadas,
        "livres": livres,
        "janela_txt": texto_janela(janela),
        "amanha": proximos,
        "aba": "inicio",
    })


@login_required
def agenda(request):
    hoje = timezone.localdate()
    dia = parse_data(request.GET.get("d"), hoje)
    seg = dia - timedelta(days=dia.weekday())
    semana = []
    for i in range(7):
        d = seg + timedelta(days=i)
        usadas, total = _ocupacao(d)
        semana.append({"data": d, "curto": DIAS_CURTOS[i], "usadas": usadas, "total": total, "sel": d == dia, "hoje": d == hoje})
    janela = HorarioFuncionamento.do_dia(dia)
    usadas, total = _ocupacao(dia)
    return render(request, "estudio/agenda.html", {
        "dia": dia,
        "dia_nome": DIAS_LONGOS[dia.weekday()].upper(),
        "semana": semana,
        "titulo_semana": f"{seg:%d} – {(seg + timedelta(days=6)):%d} de {MESES[(seg + timedelta(days=6)).month - 1]}",
        "anterior": (seg - timedelta(days=7)).isoformat(),
        "proxima": (seg + timedelta(days=7)).isoformat(),
        "faixas": _faixas_contexto(dia),
        "janela_txt": texto_janela(janela),
        "pct": int(usadas * 100 / total) if total else 0,
        "usadas": usadas,
        "total": total,
        "aba": "agenda",
    })


@login_required
def agenda_mes(request):
    hoje = timezone.localdate()
    try:
        ano, mes = map(int, request.GET.get("m", "").split("-"))
        base = date(ano, mes, 1)
    except ValueError:
        base = hoje.replace(day=1)
    ultimo = calendar.monthrange(base.year, base.month)[1]
    ini = regras.inicio_em(base, 0)
    fim = regras.inicio_em(base.replace(day=ultimo), 0) + timedelta(days=1)
    contagem = {}
    for ag in Agendamento.objects.ativos().filter(inicio__gte=ini, inicio__lt=fim).only("inicio", "horas"):
        d = timezone.localdate(ag.inicio)
        contagem[d] = contagem.get(d, 0) + ag.horas
    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(base.year, base.month):
        linha = []
        for d in semana:
            janela = HorarioFuncionamento.do_dia(d)
            total = (janela[1] - janela[0]) if janela else 0
            h = contagem.get(d, 0)
            nivel = 0 if not h else (3 if total and h >= total else (2 if total and h >= total / 2 else 1))
            linha.append({"data": d, "fora": d.month != base.month, "horas": h, "nivel": nivel, "hoje": d == hoje})
        semanas.append(linha)
    ant = (base - timedelta(days=1)).replace(day=1)
    prox = base.replace(day=ultimo) + timedelta(days=1)
    return render(request, "estudio/agenda_mes.html", {
        "semanas": semanas,
        "titulo": f"{MESES[base.month - 1].capitalize()} {base.year}",
        "anterior": f"{ant.year}-{ant.month:02d}",
        "proxima": f"{prox.year}-{prox.month:02d}",
        "dias": DIAS_CURTOS,
        "aba": "agenda",
    })


@login_required
def horarios_json(request):
    data = parse_data(request.GET.get("data"))
    tipo = request.GET.get("tipo", "ensaio")
    try:
        horas = int(request.GET.get("horas", 2))
        ignorar = int(request.GET.get("ignorar") or 0)
    except ValueError:
        return JsonResponse({"erro": "parâmetros inválidos"}, status=400)
    if not data:
        return JsonResponse({"livres": [], "janela": None})
    janela = HorarioFuncionamento.do_dia(data)
    return JsonResponse({
        "livres": regras.horarios_livres(data, tipo, horas, ignorar_id=ignorar),
        "janela": janela,
        "dia": data_extenso(data),
    })


# ---------- agendamentos ----------

def link_whatsapp(contato, texto):
    if not contato or not contato.whatsapp:
        return ""
    return f"https://wa.me/{contato.whatsapp}?text={quote(texto)}"


def _resumo(ag):
    ini, fim = timezone.localtime(ag.inicio), timezone.localtime(ag.fim)
    return f"{ag.get_tipo_display().lower()} no Omega Studio {data_extenso(ini.date())}, das {ini:%H}h às {fim:%H}h ({ag.horas}h, {brl(ag.valor_total)})"


def link_whatsapp_confirmacao(ag):
    nome = ag.contato.nome.split()[0] if ag.contato else ""
    texto = (
        f"Olá, {nome}! Seu {_resumo(ag)} está confirmado. 🎸\n"
        f"Cancelamento ou remarcação sem custo até 48h antes.\n"
        f"Endereço: {ENDERECO}."
    )
    return link_whatsapp(ag.contato, texto)


def link_whatsapp_lembrete(ag):
    nome = ag.contato.nome.split()[0] if ag.contato else ""
    texto = f"Olá, {nome}! Passando para lembrar do seu {_resumo(ag)}. Te esperamos! {ENDERECO}."
    return link_whatsapp(ag.contato, texto)


@login_required
def agendamento_novo(request):
    cfg = Configuracao.atual()
    inicial = {
        "tipo": request.GET.get("tipo", "ensaio"),
        "data": request.GET.get("data") or timezone.localdate().isoformat(),
        "horas": request.GET.get("horas", 2),
        "hora": request.GET.get("hora", ""),
        "cliente": request.GET.get("cliente", ""),
    }
    form = AgendamentoForm(request.POST or None, initial=inicial)
    erro = None
    if request.method == "POST" and form.is_valid():
        c = form.cleaned_data
        try:
            ag = regras.criar_agendamento(
                request.user, c["cliente"], c["tipo"], c["data"], c["hora"], c["horas"],
                confirmar_blacklist=c["confirmar_blacklist"], observacao=c["observacao"],
            )
        except regras.ClienteNaBlacklist as e:
            return render(request, "estudio/blacklist_alerta.html", _contexto_blacklist(request, e.cliente, form.data))
        except regras.RegraErro as e:
            erro = str(e)
        else:
            messages.success(request, "Agendamento confirmado.")
            return redirect(reverse("agendamento", args=[ag.pk]) + "?novo=1")
    elif request.method == "POST":
        erro = "Confira os campos: cliente, tipo, dia, duração e horário."
    clientes = Cliente.objects.order_by("nome").only("id", "nome", "blacklist_manual")
    selecionado = None
    cid = form.data.get("cliente") if form.is_bound else inicial["cliente"]
    if cid:
        selecionado = Cliente.objects.filter(pk=cid).first()
    return render(request, "estudio/agendamento_form.html", {
        "form": form,
        "erro": erro,
        "clientes": clientes,
        "selecionado": selecionado,
        "valores": {"tipo": form.data.get("tipo") if form.is_bound else inicial["tipo"],
                    "data": form.data.get("data") if form.is_bound else inicial["data"],
                    "horas": form.data.get("horas") if form.is_bound else inicial["horas"],
                    "hora": form.data.get("hora") if form.is_bound else inicial["hora"]},
        "cfg": cfg,
        "aba": "novo",
    })


def _contexto_blacklist(request, cliente, dados):
    return {
        "cliente": cliente,
        "debitos": cliente.debitos_abertos(),
        "total": brl(cliente.total_em_aberto()),
        "anotacoes": cliente.anotacoes.select_related("autor")[:3],
        "qtd": cliente.agendamentos.exclude(status=Agendamento.Status.CANCELADO).count(),
        "faltas": cliente.agendamentos.filter(status=Agendamento.Status.FALTA).count(),
        "tardios": cliente.debitos.exclude(motivo=Debito.Motivo.FALTA).count(),
        "dados": dados,
    }


@login_required
def cliente_situacao(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    avisos = [
        f"{a['contato'].nome} tem débito na casa: {brl(a['debito'].valor)} ({a['debito'].cliente})"
        for a in regras.avisos_do_contato(cliente)
    ]
    return JsonResponse({
        "blacklist": cliente.na_blacklist,
        "em_aberto": brl(cliente.total_em_aberto()) if cliente.debitos_abertos().exists() else "",
        "avisos": avisos,
        "is_admin": request.user.is_admin,
    })


@login_required
def agendamento(request, pk):
    ag = get_object_or_404(Agendamento.objects.select_related("cliente", "contato", "criado_por"), pk=pk)
    tardio = regras.esta_no_prazo_de_taxa(ag)
    return render(request, "estudio/agendamento.html", {
        "ag": ag,
        "ini": timezone.localtime(ag.inicio),
        "fim": timezone.localtime(ag.fim),
        "dia": data_extenso(timezone.localdate(ag.inicio)),
        "valor": brl(ag.valor_total),
        "ativo": ag.status == Agendamento.Status.AGENDADO,
        "tardio": tardio,
        "pode_remarcar": ag.status == Agendamento.Status.AGENDADO and (not tardio or request.user.is_admin),
        "pode_falta": ag.status == Agendamento.Status.AGENDADO and ag.ja_comecou,
        "whats_confirmacao": link_whatsapp_confirmacao(ag),
        "whats_lembrete": link_whatsapp_lembrete(ag),
        "novo": request.GET.get("novo") == "1",
        "debitos": ag.debitos.all(),
    })


@login_required
def agendamento_cancelar(request, pk):
    ag = get_object_or_404(Agendamento, pk=pk)
    if request.method == "POST":
        try:
            debito = regras.cancelar(request.user, ag)
        except regras.RegraErro as e:
            messages.error(request, str(e))
            return redirect("agendamento", pk=pk)
        if debito:
            messages.warning(request, f"Cancelado com taxa de {brl(debito.valor)}. {ag.cliente} entrou na blacklist até a baixa do débito.")
        else:
            messages.success(request, "Agendamento cancelado sem custo.")
        return redirect("agendamento", pk=pk)
    tem_taxa, valor = regras.previa_cancelamento(ag)
    return render(request, "estudio/confirmar.html", {
        "ag": ag,
        "titulo": "Cancelar agendamento?",
        "acao": reverse("agendamento_cancelar", args=[pk]),
        "botao": "Cancelar agendamento",
        "perigo": tem_taxa,
        "texto": (
            f"Faltam menos de 48h. Será gerada uma taxa de {brl(valor)} e {ag.cliente} entra na blacklist até pagar."
            if tem_taxa else "Ainda está dentro do prazo: cancelamento sem custo."
        ),
    })


@login_required
def agendamento_remarcar(request, pk):
    ag = get_object_or_404(Agendamento.objects.select_related("cliente"), pk=pk)
    tardio = regras.esta_no_prazo_de_taxa(ag)
    if tardio and not request.user.is_admin:
        messages.error(request, "Faltam menos de 48h: só um administrador pode remarcar.")
        return redirect("agendamento", pk=pk)
    form = RemarcarForm(request.POST or None, initial={"data": timezone.localdate(ag.inicio), "horas": ag.horas})
    erro = None
    if request.method == "POST" and form.is_valid():
        c = form.cleaned_data
        try:
            debito = regras.remarcar(request.user, ag, c["data"], c["hora"], c["horas"])
        except regras.RegraErro as e:
            erro = str(e)
        else:
            if debito:
                messages.warning(request, f"Remarcado com taxa de {brl(debito.valor)}.")
            else:
                messages.success(request, "Remarcado sem custo.")
            return redirect("agendamento", pk=pk)
    _, valor = regras.previa_cancelamento(ag)
    return render(request, "estudio/remarcar.html", {
        "ag": ag, "form": form, "erro": erro, "tardio": tardio, "taxa": brl(valor),
        "data": form.data.get("data") if form.is_bound else timezone.localdate(ag.inicio).isoformat(),
        "horas": form.data.get("horas") if form.is_bound else ag.horas,
        "cfg": Configuracao.atual(),
    })


@login_required
@require_POST
def agendamento_falta(request, pk):
    ag = get_object_or_404(Agendamento, pk=pk)
    try:
        debito = regras.marcar_falta(request.user, ag)
    except regras.RegraErro as e:
        messages.error(request, str(e))
    else:
        messages.warning(request, f"Falta registrada. Taxa de {brl(debito.valor)}; {ag.cliente} entrou na blacklist.")
    return redirect("agendamento", pk=pk)


# ---------- clientes ----------

@login_required
def clientes(request):
    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("f", "")
    qs = Cliente.objects.all().prefetch_related("vinculos__contato")
    if q:
        digitos = "".join(ch for ch in q if ch.isdigit())
        cond = Q(nome__icontains=q) | Q(contatos__nome__icontains=q)
        if len(digitos) >= 4:
            cond |= Q(contatos__whatsapp__contains=digitos)
        qs = qs.filter(cond).distinct()
    abertos = set(Debito.objects.filter(quitado_em__isnull=True).values_list("cliente_id", flat=True))
    lista = []
    for c in qs.order_by("nome")[:300]:
        bl = c.blacklist_manual or c.pk in abertos
        if filtro == "blacklist" and not bl:
            continue
        lista.append({"c": c, "bl": bl, "contato": c.contato_principal})
    return render(request, "estudio/clientes.html", {"lista": lista, "q": q, "f": filtro, "aba": "clientes"})


@login_required
def cliente_novo(request):
    form = ClienteForm(request.POST or None, initial={"tipo": "banda"})
    existentes = None
    if request.method == "POST" and form.is_valid():
        c = form.cleaned_data
        numero = normalizar_whatsapp(c["whatsapp"])
        contato = None
        if c.get("usar_contato"):
            contato = get_object_or_404(Contato, pk=c["usar_contato"])
        elif not c.get("contato_novo"):
            existentes = Contato.objects.filter(whatsapp=numero).prefetch_related("clientes")
            if existentes:
                return render(request, "estudio/cliente_form.html", {"form": form, "existentes": existentes, "aba": "clientes"})
        with transaction.atomic():
            if contato is None:
                nome_contato = c["responsavel"] if c["tipo"] == Cliente.Tipo.BANDA else c["nome"]
                contato = Contato.objects.create(nome=nome_contato or c["nome"], whatsapp=numero, instagram=c["instagram"] if c["tipo"] == Cliente.Tipo.ARTISTA else "")
            cliente = Cliente.objects.create(tipo=c["tipo"], nome=c["nome"], origem=c["origem"], instagram=c["instagram"])
            Vinculo.objects.create(contato=contato, cliente=cliente, principal=True)
            if c["anotacao"]:
                Anotacao.objects.create(cliente=cliente, autor=request.user, texto=c["anotacao"])
        messages.success(request, f"{cliente} cadastrado.")
        if request.POST.get("depois") == "agendar":
            return redirect(reverse("agendamento_novo") + f"?cliente={cliente.pk}")
        return redirect("cliente", pk=cliente.pk)
    return render(request, "estudio/cliente_form.html", {"form": form, "existentes": existentes, "aba": "clientes"})


@login_required
def cliente(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    agora = timezone.now()
    ags = c.agendamentos.all()
    realizados = ags.filter(status=Agendamento.Status.AGENDADO, fim__lte=agora)
    return render(request, "estudio/cliente.html", {
        "c": c,
        "vinculos": c.vinculos.select_related("contato"),
        "contato": c.contato_principal,
        "bl": c.na_blacklist,
        "debitos": c.debitos_abertos(),
        "total": brl(c.total_em_aberto()),
        "proximos": ags.filter(status=Agendamento.Status.AGENDADO, inicio__gte=agora).order_by("inicio")[:5],
        "historico": ags.filter(inicio__lt=agora).order_by("-inicio")[:10],
        "qtd": realizados.count(),
        "horas": realizados.aggregate(h=Sum("horas"))["h"] or 0,
        "faltas": ags.filter(status=Agendamento.Status.FALTA).count(),
        "anotacoes": c.anotacoes.select_related("autor"),
        "avisos": regras.avisos_do_contato(c),
        "aba": "clientes",
    })


@login_required
def cliente_editar(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    contato = c.contato_principal
    form = ClienteEditarForm(request.POST or None, instance=c)
    if request.method == "POST" and form.is_valid():
        form.save()
        if contato:
            contato.nome = request.POST.get("contato_nome", contato.nome).strip() or contato.nome
            novo = request.POST.get("contato_whatsapp", "").strip()
            if novo:
                contato.whatsapp = novo
            contato.save()
        messages.success(request, "Dados atualizados.")
        return redirect("cliente", pk=pk)
    return render(request, "estudio/cliente_editar.html", {"form": form, "c": c, "contato": contato, "aba": "clientes"})


@login_required
@require_POST
def cliente_anotacao(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    texto = request.POST.get("texto", "").strip()
    if texto:
        Anotacao.objects.create(cliente=c, autor=request.user, texto=texto)
    return redirect("cliente", pk=pk)


@login_required
@require_POST
def cliente_blacklist(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    if request.POST.get("acao") == "tirar":
        try:
            regras.tirar_da_blacklist(request.user, c)
        except regras.RegraErro as e:
            messages.error(request, str(e))
        else:
            messages.success(request, f"{c} saiu da blacklist manual.")
    else:
        motivo = request.POST.get("motivo", "").strip()
        if not motivo:
            messages.error(request, "Escreva o motivo para colocar na blacklist.")
            return redirect("cliente", pk=pk)
        c.blacklist_manual = True
        c.motivo_blacklist = motivo
        c.save()
        Anotacao.objects.create(cliente=c, autor=request.user, texto=f"Colocado na blacklist: {motivo}")
        messages.warning(request, f"{c} entrou na blacklist.")
    return redirect("cliente", pk=pk)


@admin_required
@require_POST
def debito_quitar(request, pk):
    d = get_object_or_404(Debito, pk=pk)
    try:
        regras.quitar_debito(request.user, d)
    except regras.RegraErro as e:
        messages.error(request, str(e))
    else:
        resto = d.cliente.na_blacklist
        messages.success(request, f"Débito de {brl(d.valor)} quitado." + ("" if resto else f" {d.cliente} saiu da blacklist."))
    return redirect("cliente", pk=d.cliente_id)


# ---------- menu ----------

@login_required
def mais(request):
    abertos = Debito.objects.filter(quitado_em__isnull=True).aggregate(n=Count("id"), t=Sum("valor"))
    return render(request, "estudio/mais.html", {
        "debitos_n": abertos["n"],
        "debitos_t": brl(abertos["t"] or 0),
        "ultimo_backup": Backup.objects.defer("conteudo").first() if request.user.is_admin else None,
        "blacklist_n": Cliente.objects.filter(Q(blacklist_manual=True) | Q(debitos__quitado_em__isnull=True, debitos__isnull=False)).distinct().count(),
        "aba": "mais",
    })
