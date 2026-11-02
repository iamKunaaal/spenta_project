from django import template
from django.urls import reverse

from ..roles import get_user_roles, dashboard_links

register = template.Library()


@register.filter
def has_role(user, roles):
    """{% if request.user|has_role:"admin,super_admin" %}  -> True if the user holds any of those roles."""
    wanted = [r.strip() for r in str(roles).split(',') if r.strip()]
    return any(r in wanted for r in get_user_roles(user))


@register.simple_tag
def role_nav(user):
    """Dashboards available to the user: list of {label, url}. Used for the role switcher."""
    return [{'label': label, 'url': reverse(name)} for label, name in dashboard_links(user)]
