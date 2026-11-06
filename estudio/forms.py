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
    observacao = forms.CharField(max_length=255, required=False)
    confirmar_blacklist = forms.BooleanField(required=False)


class RemarcarForm(forms.Form):
    data = forms.DateField()
    hora = forms.IntegerField(min_value=0, max_value=23)
    horas = forms.IntegerField(min_value=1, max_value=12)
