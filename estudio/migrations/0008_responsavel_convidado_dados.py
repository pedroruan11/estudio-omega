"""Dados do novo campo responsavel_convidado, numa migração separada da que cria o campo
(no Postgres, criar o índice da FK e atualizar linhas na mesma transação dá
"cannot CREATE INDEX ... because it has pending trigger events")."""
from django.db import migrations, models


def converter_pendentes(apps, schema_editor):
    """Antes, num convite pendente o `responsavel` já era o convidado. Agora o convidado fica em
    `responsavel_convidado` e o `responsavel` continua sendo quem agendou até a resposta."""
    Agendamento = apps.get_model("estudio", "Agendamento")
    for ag in Agendamento.objects.filter(responsavel_status="pendente"):
        ag.responsavel_convidado_id = ag.responsavel_id
        ag.responsavel_id = ag.criado_por_id
        ag.save(update_fields=["responsavel_convidado", "responsavel"])
    # agendamentos antigos (de antes do recurso) sem responsável: quem agendou atende
    Agendamento.objects.filter(responsavel__isnull=True, criado_por__isnull=False).update(
        responsavel=models.F("criado_por")
    )


def desfazer(apps, schema_editor):
    Agendamento = apps.get_model("estudio", "Agendamento")
    for ag in Agendamento.objects.filter(responsavel_status="pendente", responsavel_convidado__isnull=False):
        ag.responsavel_id = ag.responsavel_convidado_id
        ag.save(update_fields=["responsavel"])



class Migration(migrations.Migration):

    dependencies = [
        ("estudio", "0007_responsavel_convidado"),
    ]

    operations = [
        migrations.RunPython(converter_pendentes, desfazer),
    ]
