from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Agendamento, Cliente, Usuario


class PrimeiroAcessoForm(UserCreationForm):
    first_name = forms.CharField(label="Seu nome", max_length=60)

    class Meta:
        model = Usuario
        fields = ("first_name", "username")
        labels = {"username": "Usuário (para entrar)"}


class ClienteForm(forms.Form):
    tipo = forms.ChoiceField(choices=Cliente.Tipo.choices, initial=Cliente.Tipo.BANDA)
    nome = forms.CharField(max_length=120)
    responsavel = forms.CharField(max_length=120, required=False)
    whatsapp = forms.CharField(max_length=30)
    instagram = forms.CharField(max_length=60, required=False)
    origem = forms.ChoiceField(choices=[("", "—")] + list(Cliente.Origem.choices), required=False)
    anotacao = forms.CharField(widget=forms.Textarea, required=False)
    usar_contato = forms.IntegerField(required=False)
    contato_novo = forms.BooleanField(required=False)

    def clean_whatsapp(self):
        from .models import so_digitos

        d = so_digitos(self.cleaned_data["whatsapp"])
        if len(d) < 10:
            raise forms.ValidationError("Informe o WhatsApp com DDD.")
        return self.cleaned_data["whatsapp"]

    def clean(self):
        data = super().clean()
        if data.get("tipo") == Cliente.Tipo.BANDA and not data.get("responsavel") and not data.get("usar_contato"):
            self.add_error("responsavel", "Informe quem é o responsável pela banda.")
        return data


class ClienteEditarForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ("tipo", "nome", "instagram", "origem")


class AgendamentoForm(forms.Form):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.all())
    tipo = forms.ChoiceField(choices=Agendamento.Tipo.choices)
    data = forms.DateField()
    hora = forms.IntegerField(min_value=0, max_value=23)
    horas = forms.IntegerField(min_value=1, max_value=12)
    responsavel = forms.ModelChoiceField(queryset=Usuario.objects.filter(is_active=True), required=False)
    observacao = forms.CharField(max_length=255, required=False)
    confirmar_blacklist = forms.BooleanField(required=False)


class RemarcarForm(forms.Form):
    data = forms.DateField()
    hora = forms.IntegerField(min_value=0, max_value=23)
    horas = forms.IntegerField(min_value=1, max_value=12)


# ---------- fase 2 ----------
from django.contrib.auth.forms import SetPasswordForm  # noqa: E402
from django.forms import modelformset_factory  # noqa: E402

from .models import Configuracao, HorarioFuncionamento  # noqa: E402


class FinanceiroForm(forms.ModelForm):
    class Meta:
        model = Configuracao
        fields = ("preco_ensaio", "preco_gravacao", "taxa_ensaio_pct", "taxa_gravacao_pct", "antecedencia_horas",
                  "min_horas_ensaio", "min_horas_gravacao", "max_horas")
        localized_fields = ("preco_ensaio", "preco_gravacao")  # aceita "70,00"

    def clean(self):
        d = super().clean()
        for campo in ("taxa_ensaio_pct", "taxa_gravacao_pct"):
            if d.get(campo) is not None and d[campo] > 100:
                self.add_error(campo, "Máximo de 100%.")
        if d.get("max_horas") and d.get("min_horas_ensaio") and d["min_horas_ensaio"] > d["max_horas"]:
            self.add_error("min_horas_ensaio", "O mínimo não pode passar do máximo.")
        if d.get("max_horas") is not None and not 1 <= d["max_horas"] <= 15:
            self.add_error("max_horas", "Entre 1 e 15 horas.")
        return d


class UsuarioNovoForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("first_name", "username", "telefone", "perfil")
        labels = {"first_name": "Nome", "username": "Usuário (para entrar)", "telefone": "WhatsApp"}

    def clean_telefone(self):
        from .models import so_digitos

        d = so_digitos(self.cleaned_data.get("telefone", ""))
        if d and len(d) < 10:
            raise forms.ValidationError("Informe o WhatsApp com DDD.")
        return self.cleaned_data["telefone"]


class UsuarioEditarForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ("first_name", "telefone", "perfil", "is_active")
        labels = {"first_name": "Nome", "telefone": "WhatsApp", "is_active": "Ativo (pode entrar no sistema)"}

    def clean_telefone(self):
        from .models import so_digitos

        d = so_digitos(self.cleaned_data.get("telefone", ""))
        if d and len(d) < 10:
            raise forms.ValidationError("Informe o WhatsApp com DDD.")
        return self.cleaned_data["telefone"]


class RedefinirSenhaForm(SetPasswordForm):
    pass


class HorarioForm(forms.ModelForm):
    class Meta:
        model = HorarioFuncionamento
        fields = ("aberto", "abre", "fecha")

    def clean(self):
        d = super().clean()
        abre, fecha = d.get("abre"), d.get("fecha")
        if abre is not None and fecha is not None:
            if not 0 <= abre <= 23:
                self.add_error("abre", "Hora entre 0 e 23.")
            if not 1 <= fecha <= 24:
                self.add_error("fecha", "Hora entre 1 e 24 (24 = meia-noite).")
            if abre >= fecha:
                self.add_error("fecha", "Precisa fechar depois de abrir.")
        return d


HorarioFormSet = modelformset_factory(HorarioFuncionamento, form=HorarioForm, extra=0)
