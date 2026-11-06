# Omega Studio · sistema de gestão

Sistema interno do Omega Studio (Osasco) para agenda da sala, clientes, blacklist e débitos.
Feito para usar no celular (iPhone e Android): no navegador, "Adicionar à tela inicial" para abrir como app.

## Tecnologia
- Python 3.13 + Django
- Banco PostgreSQL no Neon (variável `DATABASE_URL`)
- Hospedado no Render (serviço `estudio-omega`)

## Variáveis de ambiente (Render)
| Variável | Para quê |
|---|---|
| `DATABASE_URL` | Conexão com o Postgres do Neon |
| `SECRET_KEY` | Chave secreta do Django (gerar no Render) |

## Comandos no Render
- Build: `pip install -r requirements.txt`
- Start: `bash start.sh` (aplica migrações, coleta arquivos estáticos e sobe o gunicorn)

## Despertador (manter o app acordado)
O plano gratuito do Render desliga o app depois de 15 minutos sem acesso, e ele leva uns 40 segundos para voltar.
Para o app abrir rápido no celular, um serviço externo acessa a rota `/saude` (não consulta o banco) a cada 10 minutos.

- **Principal: [cron-job.org](https://console.cron-job.org/jobs)** (conta do Pedro)
  - URL: `https://estudio-omega.onrender.com/saude`, método GET
  - Horário: `*/10 0,7-23 * * *` (a cada 10 min, das 07h à 00h50), fuso America/Sao_Paulo
  - Timeout de 30 s: se o app estiver dormindo, o primeiro acesso pode aparecer como falha no histórico. É normal; os seguintes devem dar 200 OK.
- **Reserva manual: GitHub Actions** (`.github/workflows/despertador.yml`), sem agendamento (o cron do GitHub no plano gratuito não disparava). Para acordar o app na mão: Actions → Despertador → Run workflow.

## Primeiro acesso
Com o banco vazio, o sistema abre a tela **Primeiro acesso** para criar o primeiro Administrador.
Depois disso a tela some. Outros usuários são criados pelo Administrador em Mais → Usuários, preços e horários.

## Regras principais
- Sala: seg–sex 18h–00h, sáb–dom 09h–23h (editável). Uma sala, sem choque de horário.
- Ensaio: R$ 70/h, mínimo 2h. Gravação: R$ 400/h, mínimo 1h. Máximo 6h. Só horas cheias.
- Cancelar/remarcar grátis até 48h antes. Depois: taxa de 70% (ensaio) ou 50% (gravação) do total; falta sem aviso também.
- Taxa vira débito e o cliente entra na blacklist até o Administrador dar baixa.
- Perfil Edição não remarca com menos de 48h, não agenda cliente da blacklist e não tira ninguém da blacklist.
- Contato (pessoa) ≠ Cliente (banda): uma pessoa pode ter várias bandas; débito em uma banda gera aviso nas outras.

Toda regra fica em `estudio/regras.py`, com testes em `estudio/tests.py`.

## Rodar localmente
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
python manage.py test estudio
```
