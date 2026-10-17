"""Rôles et droits (section 2).

Les droits sont attribués par rôle global ; la restriction par mission (un auditeur ne voit
que ses missions) sera appliquée par les lots suivants via l'équipe de chaque mission.
"""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "administrateur"
    DIRECTEUR = "directeur_audit"
    CHEF_MISSION = "chef_mission"
    AUDITEUR = "auditeur"
    DATA_ANALYST = "data_analyst"
    AUDITE = "audite"


ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Administrateur",
    Role.DIRECTEUR: "Directeur d'audit",
    Role.CHEF_MISSION: "Chef de mission",
    Role.AUDITEUR: "Auditeur",
    Role.DATA_ANALYST: "Data analyst",
    Role.AUDITE: "Audité",
}

# Double authentification obligatoire.
MFA_REQUIRED: frozenset[Role] = frozenset({Role.ADMIN, Role.DIRECTEUR})


class Perm(StrEnum):
    # Administration
    USERS_MANAGE = "users:manage"
    SETTINGS_MANAGE = "settings:manage"
    AUDIT_LOG_READ = "audit_log:read"
    DASHBOARDS_GLOBAL = "dashboards:global"
    # Missions
    MISSIONS_READ_ALL = "missions:read_all"
    MISSIONS_READ_OWN = "missions:read_own"
    PLAN_MANAGE = "plan:manage"
    PLAN_VALIDATE = "plan:validate"
    MISSIONS_MANAGE = "missions:manage"
    # Papiers de travail
    WORKPAPERS_READ = "workpapers:read"
    WORKPAPERS_PREPARE = "workpapers:prepare"
    WORKPAPERS_REVIEW = "workpapers:review"
    WORKPAPERS_APPROVE_FINAL = "workpapers:approve_final"
    # Analyses de données
    DATA_READ = "data:read"
    DATA_ANALYZE = "data:analyze"
    DATA_PUBLISH_LIBRARY = "data:publish_library"
    # Constats
    FINDINGS_READ = "findings:read"
    FINDINGS_WRITE = "findings:write"
    FINDINGS_VALIDATE = "findings:validate"
    REPORT_PUBLISH = "report:publish"
    FINDINGS_RESPOND = "findings:respond"


# Transcription de la matrice de la section 2.
ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.ADMIN: frozenset(
        {
            Perm.USERS_MANAGE,
            Perm.SETTINGS_MANAGE,
            Perm.AUDIT_LOG_READ,
            Perm.MISSIONS_READ_ALL,
            Perm.WORKPAPERS_READ,
            Perm.DATA_READ,
            Perm.FINDINGS_READ,
        }
    ),
    Role.DIRECTEUR: frozenset(
        {
            Perm.DASHBOARDS_GLOBAL,
            Perm.AUDIT_LOG_READ,
            Perm.MISSIONS_READ_ALL,
            Perm.PLAN_MANAGE,
            Perm.PLAN_VALIDATE,
            Perm.MISSIONS_MANAGE,
            Perm.WORKPAPERS_READ,
            Perm.WORKPAPERS_APPROVE_FINAL,
            Perm.DATA_READ,
            Perm.FINDINGS_READ,
            Perm.FINDINGS_VALIDATE,
            Perm.REPORT_PUBLISH,
        }
    ),
    Role.CHEF_MISSION: frozenset(
        {
            Perm.MISSIONS_READ_OWN,
            Perm.MISSIONS_MANAGE,
            Perm.WORKPAPERS_READ,
            Perm.WORKPAPERS_REVIEW,
            Perm.DATA_READ,
            Perm.DATA_ANALYZE,
            Perm.FINDINGS_READ,
            Perm.FINDINGS_WRITE,
            Perm.FINDINGS_VALIDATE,
        }
    ),
    Role.AUDITEUR: frozenset(
        {
            Perm.MISSIONS_READ_OWN,
            Perm.WORKPAPERS_READ,
            Perm.WORKPAPERS_PREPARE,
            Perm.DATA_READ,
            Perm.DATA_ANALYZE,
            Perm.FINDINGS_READ,
            Perm.FINDINGS_WRITE,
        }
    ),
    Role.DATA_ANALYST: frozenset(
        {
            Perm.MISSIONS_READ_OWN,
            Perm.WORKPAPERS_READ,
            Perm.DATA_READ,
            Perm.DATA_ANALYZE,
            Perm.DATA_PUBLISH_LIBRARY,
            Perm.FINDINGS_READ,
        }
    ),
    Role.AUDITE: frozenset({Perm.FINDINGS_RESPOND}),
}


def has_permission(role: str, perm: Perm) -> bool:
    try:
        return perm in ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return False


def can_review(preparer_id: object, reviewer_id: object) -> bool:
    """Séparation des tâches : le préparateur d'un papier de travail n'en est pas le réviseur."""
    return preparer_id != reviewer_id
