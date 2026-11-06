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
