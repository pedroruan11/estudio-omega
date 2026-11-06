from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from estudio import views as v

urlpatterns = [
    path("", v.inicio, name="inicio"),
    path("saude", v.saude, name="saude"),
    path("manifest.webmanifest", v.manifest, name="manifest"),
    path("sw.js", v.service_worker, name="sw"),
    path("primeiro-acesso/", v.primeiro_acesso, name="primeiro_acesso"),
    path("entrar/", v.Entrar.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("senha/", v.TrocarSenha.as_view(), name="trocar_senha"),
    path("agenda/", v.agenda, name="agenda"),
    path("agenda/mes/", v.agenda_mes, name="agenda_mes"),
    path("agenda/horarios.json", v.horarios_json, name="horarios_json"),
    path("agendamentos/novo/", v.agendamento_novo, name="agendamento_novo"),
    path("agendamentos/<int:pk>/", v.agendamento, name="agendamento"),
    path("agendamentos/<int:pk>/cancelar/", v.agendamento_cancelar, name="agendamento_cancelar"),
    path("agendamentos/<int:pk>/remarcar/", v.agendamento_remarcar, name="agendamento_remarcar"),
    path("agendamentos/<int:pk>/falta/", v.agendamento_falta, name="agendamento_falta"),
    path("clientes/", v.clientes, name="clientes"),
    path("clientes/novo/", v.cliente_novo, name="cliente_novo"),
    path("clientes/<int:pk>/", v.cliente, name="cliente"),
    path("clientes/<int:pk>/editar/", v.cliente_editar, name="cliente_editar"),
    path("clientes/<int:pk>/situacao.json", v.cliente_situacao, name="cliente_situacao"),
    path("clientes/<int:pk>/anotacao/", v.cliente_anotacao, name="cliente_anotacao"),
    path("clientes/<int:pk>/blacklist/", v.cliente_blacklist, name="cliente_blacklist"),
    path("debitos/<int:pk>/quitar/", v.debito_quitar, name="debito_quitar"),
    path("mais/", v.mais, name="mais"),
    path("admin/", admin.site.urls),
]
