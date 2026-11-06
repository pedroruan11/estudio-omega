"""Backup do banco de dados do Omega Studio.

- Cada backup é um JSON (dumpdata do app 'estudio') compactado em gzip, guardado no próprio banco.
- Se DRIVE_BACKUP_URL e DRIVE_BACKUP_SEGREDO estiverem configurados no Render, uma cópia vai
  para a pasta "Omega Studio/Backups" do Google Drive, por meio de um pequeno Apps Script do Pedro.
- Backup automático: no máximo um por dia, disparado pelo primeiro acesso ao sistema no dia.
"""
import base64
import gzip
import io
import json
import logging
import os
import tempfile
import threading
import urllib.request
from datetime import timedelta

from django.core.management import call_command
from django.core.management.color import no_style
from django.db import connection, transaction
from django.utils import timezone

from .models import (
    Agendamento,
    Anotacao,
    Backup,
    Cliente,
    Configuracao,
    Contato,
    Debito,
    HorarioFuncionamento,
    Usuario,
    Vinculo,
)

log = logging.getLogger(__name__)

MANTER_AUTOMATICOS = 30
MANTER_MANUAIS = 30
# Ordem para apagar antes de restaurar (dependentes primeiro).
MODELOS_RESTAURACAO = [Debito, Agendamento, Anotacao, Vinculo, Cliente, Contato, HorarioFuncionamento, Configuracao, Usuario]


def _exportar_json():
    buf = io.StringIO()
    call_command("dumpdata", "estudio", exclude=["estudio.Backup"], indent=None, stdout=buf)
    return buf.getvalue()


def gerar(usuario=None, tipo=Backup.Tipo.MANUAL, enviar_drive=True):
    dados = _exportar_json()
    registros = len(json.loads(dados))
    compactado = gzip.compress(dados.encode("utf-8"))
    b = Backup.objects.create(
        tipo=tipo, criado_por=usuario, conteudo=compactado, tamanho=len(compactado), registros=registros
    )
    _limpar_antigos()
    if enviar_drive:
        enviar_para_drive(b)
    return b


def _limpar_antigos():
    for tipo, manter in ((Backup.Tipo.AUTOMATICO, MANTER_AUTOMATICOS), (Backup.Tipo.MANUAL, MANTER_MANUAIS), (Backup.Tipo.ANTES_RESTAURAR, 10)):
        ids = list(Backup.objects.filter(tipo=tipo).order_by("-criado_em").values_list("id", flat=True)[manter:])
        if ids:
            Backup.objects.filter(id__in=ids).delete()


def drive_configurado():
    return bool(os.environ.get("DRIVE_BACKUP_URL") and os.environ.get("DRIVE_BACKUP_SEGREDO"))


def enviar_para_drive(backup):
    if not drive_configurado():
        backup.drive_status = "desligado"
        backup.save(update_fields=["drive_status"])
        return False
    corpo = json.dumps({
        "segredo": os.environ["DRIVE_BACKUP_SEGREDO"],
        "nome": backup.nome_arquivo,
        "conteudo": base64.b64encode(bytes(backup.conteudo)).decode("ascii"),
    }).encode("utf-8")
    req = urllib.request.Request(
        os.environ["DRIVE_BACKUP_URL"], data=corpo, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resposta = json.loads(r.read().decode("utf-8") or "{}")
        ok = bool(resposta.get("ok"))
        backup.drive_status = "enviado" if ok else "erro"
        backup.drive_detalhe = (resposta.get("arquivo") or resposta.get("erro") or "")[:255]
    except Exception as e:  # rede, script fora do ar etc.
        log.warning("Falha ao enviar backup ao Drive: %s", e)
        ok = False
        backup.drive_status = "erro"
        backup.drive_detalhe = str(e)[:255]
    backup.save(update_fields=["drive_status", "drive_detalhe"])
    return ok


def conteudo_json(backup):
    return gzip.decompress(bytes(backup.conteudo)).decode("utf-8")


def ler_arquivo_enviado(arquivo):
    """Aceita .json ou .json.gz enviado pelo usuário; devolve o texto JSON validado."""
    bruto = arquivo.read()
    if bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)
    texto = bruto.decode("utf-8")
    dados = json.loads(texto)
    if not isinstance(dados, list) or not all(isinstance(x, dict) and str(x.get("model", "")).startswith("estudio.") for x in dados):
        raise ValueError("Esse arquivo não parece um backup do Omega Studio.")
    if not any(x.get("model") == "estudio.usuario" for x in dados):
        raise ValueError("O backup não tem nenhum usuário; restaurar deixaria o sistema sem acesso.")
    return texto


def restaurar(texto_json, usuario):
    """Substitui todos os dados pelos do backup. Antes, guarda um backup de segurança."""
    gerar(usuario, tipo=Backup.Tipo.ANTES_RESTAURAR, enviar_drive=False)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(texto_json)
        caminho = f.name
    try:
        with transaction.atomic():
            for modelo in MODELOS_RESTAURACAO:
                modelo.objects.all().delete()
            call_command("loaddata", caminho, verbosity=0)
            with connection.cursor() as cur:
                for sql in connection.ops.sequence_reset_sql(no_style(), MODELOS_RESTAURACAO):
                    cur.execute(sql)
    finally:
        os.unlink(caminho)


def backup_automatico_se_preciso():
    """Chamado nas telas; faz no máximo um backup automático por dia, em segundo plano."""
    limite = timezone.now() - timedelta(hours=20)
    if Backup.objects.filter(tipo=Backup.Tipo.AUTOMATICO, criado_em__gte=limite).exists():
        return False

    def _rodar():
        try:
            if not Backup.objects.filter(tipo=Backup.Tipo.AUTOMATICO, criado_em__gte=limite).exists():
                gerar(None, tipo=Backup.Tipo.AUTOMATICO)
        except Exception:
            log.exception("Falha no backup automático")
        finally:
            connection.close()

    if EM_SEGUNDO_PLANO:
        threading.Thread(target=_rodar, daemon=True).start()
    else:
        gerar(None, tipo=Backup.Tipo.AUTOMATICO)
    return True


EM_SEGUNDO_PLANO = True  # os testes desligam para rodar na hora
