"""Banda FIRE (banda do Pedro) não paga ensaio — pedido do Pedro em 26/11/2026.

Separado da 0013 (campo) de propósito: estrutura e conversão de dados em migrações diferentes.
Marca a FIRE como "não paga ensaio" e zera o valor dos ensaios dela (passados e futuros),
pra não entrarem no valor estimado das Estatísticas.
"""
from decimal import Decimal

from django.db import migrations

NOMES = ("fire", "banda fire")


def marcar_fire(apps, schema_editor):
    Cliente = apps.get_model("estudio", "Cliente")
    Agendamento = apps.get_model("estudio", "Agendamento")
    ids = [c.pk for c in Cliente.objects.all() if c.nome.strip().lower() in NOMES]
    if not ids:
        return
    Cliente.objects.filter(pk__in=ids).update(nao_paga_ensaio=True)
    Agendamento.objects.filter(cliente_id__in=ids, tipo="ensaio").update(valor_hora=Decimal("0"))


class Migration(migrations.Migration):
    dependencies = [("estudio", "0013_cliente_nao_paga_ensaio")]
    operations = [migrations.RunPython(marcar_fire, migrations.RunPython.noop)]
