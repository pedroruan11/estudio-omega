from django.db import migrations

# Pedido do Pedro (09/11/2026): taxa de cancelamento/falta/remarcação tardia do ensaio
# sobe de 70% para 75%. Só atualiza quem ainda estava no valor antigo (70) -- se alguém
# já tinha mudado manualmente em Financeiro, respeita o que foi configurado.


def subir_taxa(apps, schema_editor):
    Configuracao = apps.get_model("estudio", "Configuracao")
    Configuracao.objects.filter(taxa_ensaio_pct=70).update(taxa_ensaio_pct=75)


def descer_taxa(apps, schema_editor):
    Configuracao = apps.get_model("estudio", "Configuracao")
    Configuracao.objects.filter(taxa_ensaio_pct=75).update(taxa_ensaio_pct=70)


class Migration(migrations.Migration):
    dependencies = [("estudio", "0005_agendamento_lembrete_enviado_em_and_more")]
    operations = [migrations.RunPython(subir_taxa, descer_taxa)]
