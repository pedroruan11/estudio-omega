from django.db import migrations

# Seg a sex 18h–00h; sáb e dom 09h–23h. Editável depois em Configurações.
HORARIOS = {0: (18, 24), 1: (18, 24), 2: (18, 24), 3: (18, 24), 4: (18, 24), 5: (9, 23), 6: (9, 23)}


def criar(apps, schema_editor):
    Configuracao = apps.get_model("estudio", "Configuracao")
    Horario = apps.get_model("estudio", "HorarioFuncionamento")
    Configuracao.objects.get_or_create(pk=1)
    for dia, (abre, fecha) in HORARIOS.items():
        Horario.objects.get_or_create(dia_semana=dia, defaults={"abre": abre, "fecha": fecha})


class Migration(migrations.Migration):
    dependencies = [("estudio", "0001_initial")]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
