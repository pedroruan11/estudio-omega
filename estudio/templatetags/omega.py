from datetime import datetime

from django import template
from django.utils import timezone

register = template.Library()

DIAS_LONGOS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


@register.filter
def dia_semana(valor):
    """'Quarta' a partir de uma data ou data/hora (no fuso do estúdio)."""
    if not valor:
        return ""
    if isinstance(valor, datetime):
        valor = timezone.localtime(valor)
    return DIAS_LONGOS[valor.weekday()]
