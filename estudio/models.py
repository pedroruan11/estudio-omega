"""Modelos do sistema Omega Studio.

Resumo:
- Usuario: quem usa o sistema (sócios = Administrador, colaboradores = Edição).
- Configuracao: preços por hora, percentuais de taxa e antecedência (uma linha só).
- HorarioFuncionamento: horário da sala por dia da semana.
- Contato: a pessoa (nome + WhatsApp). O telefone NÃO é chave: uma pessoa pode ter várias bandas.
- Cliente: a banda ou o artista. Ligado a contatos por Vinculo (muitos-para-muitos).
- Agendamento: ensaio ou gravação de um cliente.
- Debito: taxa de cancelamento/remarcação tardia ou falta, em aberto até a baixa.
- Anotacao: observações da equipe sobre o cliente.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class Usuario(AbstractUser):
    class Perfil(models.TextChoices):
        ADMIN = "admin", "Administrador"
        EDICAO = "edicao", "Edição"

    perfil = models.CharField(max_length=10, choices=Perfil.choices, default=Perfil.EDICAO)
    notificacoes_vistas_em = models.DateTimeField(null=True, blank=True, help_text="Última vez que abriu Minhas notificações.")
    telefone = models.CharField(
        "WhatsApp", max_length=20, blank=True,
        help_text="Usado para mandar o pedido de confirmação quando essa pessoa é escolhida como responsável por um ensaio/gravação.",
    )

    @property
    def is_admin(self):
        return self.perfil == self.Perfil.ADMIN or self.is_superuser

    def save(self, *args, **kwargs):
        # Só Administrador entra no painel /admin do Django.
        self.is_staff = self.perfil == self.Perfil.ADMIN or self.is_superuser
        if self.telefone:
            self.telefone = normalizar_whatsapp(self.telefone)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def telefone_formatado(self):
        return _whatsapp_formatado(self.telefone)

    def dias_indisponiveis_entre(self, inicio, fim):
        """Datas (set) em que esse usuário marcou que não pode acompanhar, dentro do intervalo."""
        return set(
            self.dias_bloqueados.filter(data__gte=inicio, data__lte=fim).values_list("data", flat=True)
        )


class Configuracao(models.Model):
    preco_ensaio = models.DecimalField("Preço da hora de ensaio", max_digits=8, decimal_places=2, default=Decimal("70"))
    preco_gravacao = models.DecimalField("Preço da hora de gravação", max_digits=8, decimal_places=2, default=Decimal("400"))
    taxa_ensaio_pct = models.PositiveSmallIntegerField("Taxa tardia ensaio (%)", default=75)
    taxa_gravacao_pct = models.PositiveSmallIntegerField("Taxa tardia gravação (%)", default=50)
    antecedencia_horas = models.PositiveSmallIntegerField("Antecedência sem taxa (horas)", default=48)
    min_horas_ensaio = models.PositiveSmallIntegerField(default=2)
    min_horas_gravacao = models.PositiveSmallIntegerField(default=1)
    max_horas = models.PositiveSmallIntegerField(default=6)

    class Meta:
        verbose_name = "configuração"
        verbose_name_plural = "configuração"

    def __str__(self):
        return "Configuração do estúdio"

    @classmethod
    def atual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class HorarioFuncionamento(models.Model):
    DIAS = [(0, "Segunda"), (1, "Terça"), (2, "Quarta"), (3, "Quinta"), (4, "Sexta"), (5, "Sábado"), (6, "Domingo")]
    dia_semana = models.PositiveSmallIntegerField(choices=DIAS, unique=True)
    abre = models.PositiveSmallIntegerField("Abre (hora)", default=18)
    fecha = models.PositiveSmallIntegerField("Fecha (hora; 24 = meia-noite)", default=24)
    aberto = models.BooleanField(default=True)

    class Meta:
        ordering = ["dia_semana"]
        verbose_name = "horário de funcionamento"
        verbose_name_plural = "horários de funcionamento"

    def __str__(self):
        return f"{self.get_dia_semana_display()}: {self.abre:02d}h–{self.fecha % 24:02d}h"

    PADRAO = {0: (18, 24), 1: (18, 24), 2: (18, 24), 3: (18, 24), 4: (18, 24), 5: (9, 23), 6: (9, 23)}

    @classmethod
    def do_dia(cls, data):
        """(abre, fecha) do dia, ou None se fechado."""
        dia = data.weekday()
        h = cls.objects.filter(dia_semana=dia).first()
        if h is None:
            return cls.PADRAO[dia]
        return (h.abre, h.fecha) if h.aberto else None


def so_digitos(telefone):
    return "".join(c for c in (telefone or "") if c.isdigit())


def normalizar_whatsapp(telefone):
    """Guarda sempre com DDI 55: '(11) 99999-0000' -> '5511999990000'."""
    d = so_digitos(telefone)
    if not d:
        return ""
    if d.startswith("55") and len(d) >= 12:
        return d
    return "55" + d


def _whatsapp_formatado(d):
    if d.startswith("55") and len(d) in (12, 13):
        local = d[2:]
        ddd, num = local[:2], local[2:]
        if len(num) == 9:
            return f"({ddd}) {num[0]} {num[1:5]}-{num[5:]}"
        return f"({ddd}) {num[:4]}-{num[4:]}"
    return d


class Contato(models.Model):
    nome = models.CharField(max_length=120)
    whatsapp = models.CharField(max_length=20, db_index=True, help_text="Só números, com 55 na frente")
    instagram = models.CharField(max_length=60, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.whatsapp = normalizar_whatsapp(self.whatsapp)
        super().save(*args, **kwargs)

    @property
    def whatsapp_formatado(self):
        return _whatsapp_formatado(self.whatsapp)

    def debitos_abertos(self):
        return Debito.objects.filter(cliente__vinculos__contato=self, quitado_em__isnull=True).distinct()


class Cliente(models.Model):
    class Tipo(models.TextChoices):
        BANDA = "banda", "Banda"
        ARTISTA = "artista", "Artista / pessoa"

    class Origem(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        INDICACAO = "indicacao", "Indicação"
        GOOGLE = "google", "Google"
        PASSOU = "passou", "Passou na frente"
        OUTRO = "outro", "Outro"

    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.BANDA)
    nome = models.CharField(max_length=120)
    origem = models.CharField("Como nos conheceu?", max_length=12, choices=Origem.choices, blank=True)
    instagram = models.CharField(max_length=60, blank=True)
    blacklist_manual = models.BooleanField("Na blacklist (manual)", default=False)
    motivo_blacklist = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    contatos = models.ManyToManyField(Contato, through="Vinculo", related_name="clientes")

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def inicial(self):
        return (self.nome[:1] or "?").upper()

    @property
    def contato_principal(self):
        v = self.vinculos.select_related("contato").order_by("-principal", "id").first()
        return v.contato if v else None

    def debitos_abertos(self):
        return self.debitos.filter(quitado_em__isnull=True)

    def total_em_aberto(self):
        return self.debitos_abertos().aggregate(t=Sum("valor"))["t"] or Decimal("0")

    @property
    def na_blacklist(self):
        return self.blacklist_manual or self.debitos_abertos().exists()


class Vinculo(models.Model):
    contato = models.ForeignKey(Contato, on_delete=models.CASCADE, related_name="vinculos")
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="vinculos")
    principal = models.BooleanField(default=False)

    class Meta:
        unique_together = [("contato", "cliente")]


class Anotacao(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="anotacoes")
    autor = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]


class AgendamentoQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(status=Agendamento.Status.AGENDADO)

    def no_intervalo(self, inicio, fim):
        """Ativos que se sobrepõem ao intervalo [inicio, fim)."""
        return self.ativos().filter(inicio__lt=fim, fim__gt=inicio)


class Agendamento(models.Model):
    class Tipo(models.TextChoices):
        ENSAIO = "ensaio", "Ensaio"
        GRAVACAO = "gravacao", "Gravação"

    class Status(models.TextChoices):
        AGENDADO = "agendado", "Agendado"
        CANCELADO = "cancelado", "Cancelado"
        FALTA = "falta", "Falta"

    class RespStatus(models.TextChoices):
        ACEITO = "aceito", "Aceito"
        PENDENTE = "pendente", "Aguardando resposta"
        RECUSADO = "recusado", "Recusado"
        EXPIRADO = "expirado", "Expirado"

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="agendamentos")
    contato = models.ForeignKey(Contato, on_delete=models.SET_NULL, null=True, blank=True, related_name="agendamentos")
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.ENSAIO)
    inicio = models.DateTimeField(db_index=True)
    fim = models.DateTimeField(db_index=True)
    horas = models.PositiveSmallIntegerField()
    valor_hora = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AGENDADO, db_index=True)
    observacao = models.CharField(max_length=255, blank=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    remarcacoes = models.PositiveSmallIntegerField(default=0)
    cobranca_conferida = models.BooleanField(
        default=False, help_text="Depois do ensaio, a equipe já confirmou se a multa foi paga ou não."
    )

    # ---- responsável por acompanhar (quem fica no estúdio durante o ensaio/gravação) ----
    responsavel = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="agendamentos_responsavel",
        help_text="Quem vai acompanhar esse ensaio/gravação no estúdio.",
    )
    responsavel_status = models.CharField(
        max_length=10, choices=RespStatus.choices, default=RespStatus.ACEITO, db_index=True,
    )
    responsavel_definido_em = models.DateTimeField(null=True, blank=True)
    # Quem foi convidado e ainda não respondeu. Enquanto isso, `responsavel` continua sendo
    # quem atende de fato (se o convidado recusar ou não responder, nada muda).
    responsavel_convidado = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="convites_em_aberto",
        help_text="Convidado pra assumir o acompanhamento, aguardando resposta.",
    )
    lembrete_enviado_em = models.DateTimeField(null=True, blank=True, help_text="Quando alguém da equipe marcou o lembrete do dia como enviado.")

    objects = AgendamentoQuerySet.as_manager()

    class Meta:
        ordering = ["inicio"]

    def __str__(self):
        return f"{self.cliente} · {self.get_tipo_display()} · {timezone.localtime(self.inicio):%d/%m %H:%M}"

    def save(self, *args, **kwargs):
        self.fim = self.inicio + timedelta(hours=self.horas)
        super().save(*args, **kwargs)

    @property
    def valor_total(self):
        return self.valor_hora * self.horas

    @property
    def ja_comecou(self):
        return timezone.now() >= self.inicio

    @property
    def prazo_resposta_responsavel(self):
        """Convites não respondidos até 1 dia antes do início expiram."""
        return self.inicio - timedelta(days=1)

    @property
    def responsavel_pendente(self):
        return self.responsavel_status == self.RespStatus.PENDENTE

    def pode_trocar_responsavel(self, usuario):
        """Quem fez o agendamento ou quem está acompanhando hoje pode passar pra outra pessoa
        (regra do Pedro, 12/11/2026)."""
        return usuario.pk in (self.criado_por_id, self.responsavel_id)


class ConviteResponsavel(models.Model):
    """Histórico de cada convite para acompanhar um ensaio/gravação (quem convidou, quem respondeu e como)."""

    Status = Agendamento.RespStatus

    agendamento = models.ForeignKey(Agendamento, on_delete=models.CASCADE, related_name="convites_responsavel")
    convidado = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="convites_recebidos")
    convidado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name="convites_enviados")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    respondido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.convidado} · {self.agendamento} · {self.get_status_display()}"


class UsuarioDiaIndisponivel(models.Model):
    """Dias em que um usuário avisou que não pode ser escolhido como responsável por um ensaio/gravação."""

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="dias_bloqueados")
    data = models.DateField(db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data"]
        unique_together = [("usuario", "data")]
        verbose_name = "dia indisponível"
        verbose_name_plural = "dias indisponíveis"

    def __str__(self):
        return f"{self.usuario} · {self.data:%d/%m/%Y}"


class Notificacao(models.Model):
    """O que aconteceu na equipe (feed do sininho do Início). Sem destinatário = vale pra toda a equipe."""

    class Tipo(models.TextChoices):
        AGENDOU = "agendou", "Agendou"
        CANCELOU = "cancelou", "Cancelou"
        REMARCOU = "remarcou", "Remarcou"
        FALTA = "falta", "Falta"
        DIRECIONOU = "direcionou", "Direcionou pra você"
        ACEITOU = "aceitou", "Aceitou"
        RECUSOU = "recusou", "Recusou"
        EXPIROU = "expirou", "Convite expirou"
        CONVITE_CANCELADO = "convite_cancelado", "Convite cancelado"
        BLACKLIST = "blacklist", "Blacklist"
        MULTA = "multa", "Multa"

    autor = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    destinatario = models.ForeignKey(Usuario, on_delete=models.CASCADE, null=True, blank=True, related_name="notificacoes")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    texto = models.CharField(max_length=255)
    agendamento = models.ForeignKey(Agendamento, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "notificação"
        verbose_name_plural = "notificações"

    def __str__(self):
        return self.texto


class Debito(models.Model):
    class Motivo(models.TextChoices):
        CANCELAMENTO = "cancelamento", "Cancelamento com menos de 48h"
        REMARCACAO = "remarcacao", "Remarcação com menos de 48h"
        FALTA = "falta", "Falta sem aviso"
        AVULSO = "avulso", "Multa lançada manualmente"

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="debitos")
    agendamento = models.ForeignKey(Agendamento, on_delete=models.SET_NULL, null=True, blank=True, related_name="debitos")
    motivo = models.CharField(max_length=15, choices=Motivo.choices)
    descricao = models.CharField(max_length=255, blank=True)
    valor = models.DecimalField(max_digits=8, decimal_places=2)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name="+")
    quitado_em = models.DateTimeField(null=True, blank=True)
    quitado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-criado_em"]
        constraints = [models.CheckConstraint(condition=Q(valor__gte=0), name="debito_valor_positivo")]

    @property
    def aberto(self):
        return self.quitado_em is None


class Backup(models.Model):
    class Tipo(models.TextChoices):
        MANUAL = "manual", "Manual"
        AUTOMATICO = "automatico", "Automático"
        ANTES_RESTAURAR = "antes", "Antes de restaurar"

    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.MANUAL)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    tamanho = models.PositiveIntegerField(default=0, help_text="bytes (compactado)")
    registros = models.PositiveIntegerField(default=0)
    conteudo = models.BinaryField(help_text="JSON compactado (gzip)")
    drive_status = models.CharField(max_length=20, default="", blank=True)
    drive_detalhe = models.CharField(max_length=255, default="", blank=True)

    class Meta:
        ordering = ["-criado_em"]

    @property
    def nome_arquivo(self):
        return f"omega-backup-{timezone.localtime(self.criado_em):%Y-%m-%d_%H%M}.json.gz"
