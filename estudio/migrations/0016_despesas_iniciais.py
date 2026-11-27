"""Despesas mensais médias do estúdio informadas pelo Pedro em 26/11/2026.
Separado da 0015 (tabela) de propósito: estrutura e dados em migrações diferentes."""
from decimal import Decimal

from django.db import migrations

ITENS = [
    # nome, detalhe, tipo, valor, em_breve
    ("Aluguel", "", "fixa", "1200", False),
    ("Energia", "", "fixa", "350", False),
    ("Água", "", "fixa", "200", False),
    ("Limpeza", "", "fixa", "200", False),
    ("Extras", "Copos, papel higiênico, produtos de limpeza", "fixa", "200", False),
    ("Acompanhamentos", "", "fixa", "0", True),
    ("Cartão de crédito", "", "variavel", "1400", False),
]


def criar(apps, schema_editor):
    Despesa = apps.get_model("estudio", "Despesa")
    if Despesa.objects.exists():
        return
    for i, (nome, detalhe, tipo, valor, em_breve) in enumerate(ITENS):
        Despesa.objects.create(nome=nome, detalhe=detalhe, tipo=tipo, valor=Decimal(valor), em_breve=em_breve, ordem=i)


class Migration(migrations.Migration):
    dependencies = [("estudio", "0015_despesa")]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
