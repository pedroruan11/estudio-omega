from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Agendamento,
    Anotacao,
    Cliente,
    Configuracao,
    Contato,
    Debito,
    HorarioFuncionamento,
    Usuario,
    Vinculo,
)

admin.site.site_header = "Omega Studio · Administração"
admin.site.site_title = "Omega Studio"


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Perfil no estúdio", {"fields": ("perfil",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Perfil no estúdio", {"fields": ("perfil", "first_name")}),)
    list_display = ("username", "first_name", "perfil", "is_active", "last_login")


class VinculoInline(admin.TabularInline):
    model = Vinculo
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "origem", "blacklist_manual", "criado_em")
    search_fields = ("nome", "contatos__nome", "contatos__whatsapp")
    list_filter = ("tipo", "origem", "blacklist_manual")
    inlines = [VinculoInline]


@admin.register(Contato)
class ContatoAdmin(admin.ModelAdmin):
    list_display = ("nome", "whatsapp", "instagram")
    search_fields = ("nome", "whatsapp")


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "tipo", "inicio", "horas", "status", "criado_por")
    list_filter = ("tipo", "status")
    date_hierarchy = "inicio"
    search_fields = ("cliente__nome",)


@admin.register(Debito)
class DebitoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "motivo", "valor", "criado_em", "quitado_em")
    list_filter = ("motivo",)


admin.site.register(Configuracao)
admin.site.register(HorarioFuncionamento)
admin.site.register(Anotacao)
