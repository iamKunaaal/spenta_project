"""Role helpers shared by views, templates and bulk_upload.

A user has one primary role (UserProfile.role) and optionally extra roles (UserProfile.extra_roles).
Every permission check goes through these helpers so a person with two roles gets the combined access.
"""
from django.contrib.auth.models import User
from django.db.models import Q

from .models import CustomerAssignment

GRE_LIKE_ROLES = ('gre', 'digital_form')
# Roles that see every project / lead
ALL_ACCESS_ROLES = ('admin', 'super_admin', 'digital_form')
# Roles limited to the projects assigned to them (UserProfile.projects)
PROJECT_SCOPED_ROLES = ('site_head', 'gre')
# Roles limited to the leads assigned to them
ASSIGNMENT_ROLES = ('sourcing_manager', 'closing_manager')
# Who may edit a lead's details / its assessment / its source (CP, referral, source details)
EDIT_ROLES = ('admin', 'super_admin', 'closing_manager', 'site_head')
ASSESSMENT_EDIT_ROLES = ('closing_manager', 'admin', 'super_admin', 'site_head')
SOURCE_EDIT_ROLES = ('admin', 'super_admin', 'site_head')


def get_user_roles(user):
    """All roles of a user. A user without a profile (e.g. a plain Django superuser) acts as Admin."""
    try:
        return user.profile.all_roles()
    except Exception:
        return ['admin']


def get_user_role(user):
    """Primary role (kept for places that need a single role, like the login landing page)."""
    try:
        return user.profile.role
    except Exception:
        return 'admin'


def has_role(user, *roles):
    return any(r in roles for r in get_user_roles(user))


def users_with_role(role, active_only=True):
    """Users holding `role` as primary OR extra role."""
    qs = User.objects.filter(Q(profile__role=role) | Q(profile__extra_roles__contains=f',{role},'))
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.distinct()


def user_projects(user):
    from .models import Project
    try:
        return user.profile.projects.all()
    except Exception:
        return Project.objects.none()


def role_grants_access(user, role, customer):
    """Does this ONE role give `user` access to this customer?"""
    if role in ALL_ACCESS_ROLES:
        return True
    if role in PROJECT_SCOPED_ROLES:
        return customer.project_id is not None and user_projects(user).filter(id=customer.project_id).exists()
    if role == 'sourcing_manager':
        return CustomerAssignment.objects.filter(customer=customer, sourcing_manager=user).exists()
    if role == 'closing_manager':
        return CustomerAssignment.objects.filter(customer=customer, closing_manager=user).exists()
    return False


def can_access_customer(user, customer):
    return any(role_grants_access(user, r, customer) for r in get_user_roles(user))


def can_act_as(user, customer, allowed_roles):
    """True if one of the user's roles is in `allowed_roles` AND that role gives access to this customer."""
    return any(r in allowed_roles and role_grants_access(user, r, customer) for r in get_user_roles(user))


def scope_customers(user, qs):
    """Customers the user may see = union of what each of their roles allows."""
    roles = get_user_roles(user)
    if any(r in ALL_ACCESS_ROLES for r in roles):
        return qs
    q = Q(pk__in=[])
    if any(r in PROJECT_SCOPED_ROLES for r in roles):
        q |= Q(project__in=user_projects(user))
    if 'sourcing_manager' in roles:
        q |= Q(assignment__sourcing_manager=user)
    if 'closing_manager' in roles:
        q |= Q(assignment__closing_manager=user)
    return qs.filter(q)


def dashboard_links(user):
    """[(label, url_name)] of the dashboards this user can use (for the role switcher)."""
    roles = get_user_roles(user)
    links = []
    if 'sourcing_manager' in roles:
        links.append(('My Sourcing Leads', 'customer_enquiry:sourcing_manager_dashboard'))
    if 'closing_manager' in roles:
        links.append(('My Closing Leads', 'customer_enquiry:closing_manager_dashboard'))
    if 'site_head' in roles:
        links.append(('Site Head Dashboard', 'customer_enquiry:site_head_dashboard'))
    if any(r in roles for r in ('admin', 'super_admin', 'gre', 'digital_form')):
        links.append(('All Leads', 'customer_enquiry:dashboard'))
    return links
