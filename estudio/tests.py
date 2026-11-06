from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from . import regras
from .models import Agendamento, Cliente, Contato, Debito, HorarioFuncionamento, Usuario, Vinculo

SEG = date(2030, 1, 7)  # segunda-feira: 18h–00h
SAB = date(2030, 1, 12)  # sábado: 09h–23h
ANTES = regras.inicio_em(date(2030, 1, 1), 12)  # "agora" bem antes dos testes


def criar_cliente(nome="FIRE", contato=None):
    c = Cliente.objects.create(nome=nome)
    if contato:
        Vinculo.objects.create(contato=contato, cliente=c, principal=True)
    return c


class Base(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("pedro", password="x", perfil=Usuario.Perfil.ADMIN)
        self.edicao = Usuario.objects.create_user("colab", password="x", perfil=Usuario.Perfil.EDICAO)
        self.leandro = Contato.objects.create(nome="Leandro", whatsapp="(11) 99999-0000")
        self.fire = criar_cliente("FIRE", self.leandro)

    def agendar(self, cliente=None, data=SEG, hora=18, horas=2, tipo="ensaio", usuario=None, **kw):
        return regras.criar_agendamento(usuario or self.edicao, cliente or self.fire, tipo, data, hora, horas, agora=ANTES, **kw)


class HorariosTest(Base):
    def test_horarios_padrao(self):
        self.assertEqual(HorarioFuncionamento.do_dia(SEG), (18, 24))
        self.assertEqual(HorarioFuncionamento.do_dia(SAB), (9, 23))

    def test_ensaio_minimo_2h(self):
        with self.assertRaisesMessage(regras.RegraErro, "mínimo 2h"):
            self.agendar(horas=1)

    def test_gravacao_aceita_1h(self):
        ag = self.agendar(tipo="gravacao", horas=1)
        self.assertEqual(ag.valor_total, Decimal("400"))

    def test_maximo_6h(self):
        self.agendar(hora=18, horas=6)  # 18h–00h cabe
        with self.assertRaisesMessage(regras.RegraErro, "máximo"):
            self.agendar(data=SAB, hora=9, horas=7)

    def test_fora_do_horario(self):
        with self.assertRaisesMessage(regras.RegraErro, "Fora do horário"):
            self.agendar(hora=17)
        with self.assertRaisesMessage(regras.RegraErro, "Fora do horário"):
            self.agendar(hora=23, horas=2)
        with self.assertRaisesMessage(regras.RegraErro, "Fora do horário"):
            self.agendar(data=SAB, hora=22, horas=2)

    def test_termina_meia_noite(self):
        ag = self.agendar(hora=22, horas=2)
        self.assertEqual(ag.fim, regras.inicio_em(SEG + timedelta(days=1), 0))

    def test_choque_de_horario(self):
        self.agendar(hora=18, horas=3)
        with self.assertRaisesMessage(regras.RegraErro, "ocupado"):
            self.agendar(hora=20, horas=2)
        self.agendar(hora=21, horas=2)  # encosta, não choca

    def test_horarios_livres(self):
        self.agendar(data=SAB, hora=13, horas=4)  # 13–17
        livres = regras.horarios_livres(SAB, "ensaio", 2, agora=ANTES)
        self.assertEqual(livres, [9, 10, 11, 17, 18, 19, 20, 21])

    def test_passado(self):
        with self.assertRaisesMessage(regras.RegraErro, "já passou"):
            regras.criar_agendamento(self.edicao, self.fire, "ensaio", SEG, 18, 2, agora=regras.inicio_em(SEG, 19))

    def test_valor_ensaio(self):
        ag = self.agendar(horas=4)
        self.assertEqual(ag.valor_total, Decimal("280"))


class CancelamentoTest(Base):
    def test_cancelar_com_antecedencia_sem_taxa(self):
        ag = self.agendar()
        debito = regras.cancelar(self.edicao, ag, agora=ag.inicio - timedelta(hours=49))
        self.assertIsNone(debito)
        self.assertFalse(self.fire.na_blacklist)

    def test_cancelar_tardio_ensaio_70(self):
        ag = self.agendar(horas=4)  # R$ 280
        debito = regras.cancelar(self.edicao, ag, agora=ag.inicio - timedelta(hours=47))
        self.assertEqual(debito.valor, Decimal("196.00"))
        self.assertEqual(debito.motivo, Debito.Motivo.CANCELAMENTO)
        self.assertTrue(self.fire.na_blacklist)

    def test_cancelar_tardio_gravacao_50(self):
        ag = self.agendar(tipo="gravacao", horas=3)  # R$ 1.200
        debito = regras.cancelar(self.edicao, ag, agora=ag.inicio - timedelta(hours=10))
        self.assertEqual(debito.valor, Decimal("600.00"))

    def test_falta(self):
        ag = self.agendar()
        with self.assertRaises(regras.RegraErro):
            regras.marcar_falta(self.edicao, ag, agora=ag.inicio - timedelta(minutes=1))
        debito = regras.marcar_falta(self.edicao, ag, agora=ag.inicio + timedelta(minutes=30))
        self.assertEqual(debito.valor, Decimal("98.00"))
        ag.refresh_from_db()
        self.assertEqual(ag.status, Agendamento.Status.FALTA)


class RemarcacaoTest(Base):
    def test_edicao_remarca_com_antecedencia(self):
        ag = self.agendar()
        debito = regras.remarcar(self.edicao, ag, SAB, 10, agora=ag.inicio - timedelta(hours=72))
        self.assertIsNone(debito)
        ag.refresh_from_db()
        self.assertEqual(ag.inicio, regras.inicio_em(SAB, 10))
        self.assertEqual(ag.remarcacoes, 1)

    def test_edicao_nao_remarca_tardio(self):
        ag = self.agendar()
        with self.assertRaises(regras.SemPermissao):
            regras.remarcar(self.edicao, ag, SAB, 10, agora=ag.inicio - timedelta(hours=5))

    def test_admin_remarca_tardio_com_taxa(self):
        ag = self.agendar()  # R$ 140
        debito = regras.remarcar(self.admin, ag, SAB, 10, agora=ag.inicio - timedelta(hours=5))
        self.assertEqual(debito.valor, Decimal("98.00"))
        self.assertEqual(debito.motivo, Debito.Motivo.REMARCACAO)

    def test_remarcar_no_proprio_horario_nao_choca(self):
        ag = self.agendar(hora=18, horas=2)
        regras.remarcar(self.edicao, ag, SEG, 19, agora=ANTES)  # sobrepõe a si mesmo: ok


class BlacklistTest(Base):
    def test_edicao_nao_agenda_cliente_na_blacklist(self):
        self.fire.blacklist_manual = True
        self.fire.save()
        with self.assertRaises(regras.ClienteNaBlacklist):
            self.agendar()

    def test_admin_agenda_se_confirmar(self):
        self.fire.blacklist_manual = True
        self.fire.save()
        with self.assertRaises(regras.ClienteNaBlacklist):
            self.agendar(usuario=self.admin)
        self.agendar(usuario=self.admin, confirmar_blacklist=True)

    def test_baixa_no_debito_tira_da_blacklist(self):
        ag = self.agendar()
        debito = regras.cancelar(self.edicao, ag, agora=ag.inicio - timedelta(hours=1))
        self.assertTrue(self.fire.na_blacklist)
        with self.assertRaises(regras.SemPermissao):
            regras.quitar_debito(self.edicao, debito)
        regras.quitar_debito(self.admin, debito)
        self.assertFalse(self.fire.na_blacklist)

    def test_aviso_de_debito_em_outra_banda_do_contato(self):
        outra = criar_cliente("Banda B", self.leandro)
        ag = self.agendar()
        regras.cancelar(self.edicao, ag, agora=ag.inicio - timedelta(hours=1))
        self.assertFalse(outra.na_blacklist)  # outra banda não fica bloqueada
        avisos = regras.avisos_do_contato(outra)
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0]["contato"], self.leandro)
        self.agendar(cliente=outra, data=SAB, hora=10)  # agenda normalmente

    def test_so_admin_tira_da_blacklist(self):
        self.fire.blacklist_manual = True
        self.fire.save()
        with self.assertRaises(regras.SemPermissao):
            regras.tirar_da_blacklist(self.edicao, self.fire)
        regras.tirar_da_blacklist(self.admin, self.fire)
        self.assertFalse(self.fire.na_blacklist)


class ContatoTest(TestCase):
    def test_whatsapp_normalizado(self):
        c = Contato.objects.create(nome="A", whatsapp="(11) 9 8765-4321")
        self.assertEqual(c.whatsapp, "5511987654321")
        self.assertEqual(c.whatsapp_formatado, "(11) 9 8765-4321")

    def test_mesmo_telefone_varias_bandas(self):
        c = Contato.objects.create(nome="Leandro", whatsapp="11999990000")
        criar_cliente("Banda A", c)
        criar_cliente("Banda B", c)
        self.assertEqual(c.clientes.count(), 2)


class TelasTest(Base):
    def test_saude_sem_login(self):
        r = self.client.get("/saude")
        self.assertEqual(r.status_code, 200)

    def test_exige_login(self):
        r = self.client.get(reverse("inicio"))
        self.assertEqual(r.status_code, 302)

    def test_telas_abrem(self):
        self.client.force_login(self.admin)
        ag = self.agendar()
        for nome, args in [
            ("inicio", []),
            ("agenda", []),
            ("agenda_mes", []),
            ("clientes", []),
            ("cliente_novo", []),
            ("cliente", [self.fire.pk]),
            ("agendamento_novo", []),
            ("agendamento", [ag.pk]),
            ("mais", []),
            ("trocar_senha", []),
        ]:
            r = self.client.get(reverse(nome, args=args))
            self.assertEqual(r.status_code, 200, nome)

    def test_edicao_nao_ve_admin(self):
        self.client.force_login(self.edicao)
        r = self.client.get(reverse("mais"))
        self.assertNotContains(r, "Estatísticas")

    def test_agendar_pela_tela(self):
        self.client.force_login(self.edicao)
        r = self.client.post(reverse("agendamento_novo"), {
            "cliente": self.fire.pk, "tipo": "ensaio", "data": "2030-01-12", "hora": "10", "horas": "2",
        })
        self.assertEqual(r.status_code, 302, getattr(r, "content", b"")[:500])
        self.assertTrue(Agendamento.objects.filter(cliente=self.fire, horas=2).exists())

    def test_cadastro_detecta_telefone_existente(self):
        self.client.force_login(self.edicao)
        r = self.client.post(reverse("cliente_novo"), {
            "tipo": "banda", "nome": "Banda Nova", "responsavel": "Leandro", "whatsapp": "(11) 99999-0000",
        })
        self.assertContains(r, "já está cadastrado")
        r = self.client.post(reverse("cliente_novo"), {
            "tipo": "banda", "nome": "Banda Nova", "responsavel": "Leandro", "whatsapp": "(11) 99999-0000",
            "usar_contato": self.leandro.pk,
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.leandro.clientes.count(), 2)
        self.assertEqual(Contato.objects.count(), 1)
