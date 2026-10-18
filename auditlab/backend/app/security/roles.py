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
    # Module 5 : commissaire aux comptes signataire ; inspecteur de la CIPRES.
    ASSOCIE = "associe_signataire"
    INSPECTEUR_CIPRES = "inspecteur_cipres"
    # Module 6 : cabinet d'expertise comptable.
    EXPERT_COMPTABLE = "expert_comptable"
    COLLABORATEUR = "collaborateur_comptable"


ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Administrateur",
    Role.DIRECTEUR: "Directeur d'audit",
    Role.CHEF_MISSION: "Chef de mission",
    Role.AUDITEUR: "Auditeur",
    Role.DATA_ANALYST: "Data analyst",
    Role.AUDITE: "Audité",
    Role.ASSOCIE: "Associé signataire",
    Role.INSPECTEUR_CIPRES: "Inspecteur CIPRES",
    Role.EXPERT_COMPTABLE: "Expert-comptable",
    Role.COLLABORATEUR: "Collaborateur comptable",
}

# Double authentification obligatoire.
MFA_REQUIRED: frozenset[Role] = frozenset(
    {Role.ADMIN, Role.DIRECTEUR, Role.ASSOCIE, Role.EXPERT_COMPTABLE}
)


class Perm(StrEnum):
    # Administration
    USERS_MANAGE = "users:manage"
    SETTINGS_MANAGE = "settings:manage"
    AUDIT_LOG_READ = "audit_log:read"
    DASHBOARDS_GLOBAL = "dashboards:global"
    # Univers d'audit et plan annuel (lot 2)
    PLAN_READ = "plan:read"
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
    # Révision des comptes (Module 5)
    FRAMEWORKS_MANAGE = "frameworks:manage"  # importer et publier les référentiels
    REVISION_READ = "revision:read"
    REVISION_WORK = "revision:work"  # importer les balances, affecter, justifier
    REVISION_MANAGE = "revision:manage"  # ouvrir un dossier, fixer le seuil
    OPINION_SIGN = "revision:sign"  # signer et émettre l'opinion (REV-28)
    # Module 6 : portefeuille de dossiers clients (RCO-01)
    PORTFOLIO_MANAGE = "portfolio:manage"


# Transcription de la matrice de la section 2.
ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.ADMIN: frozenset(
        {
            Perm.USERS_MANAGE,
            Perm.SETTINGS_MANAGE,
            Perm.AUDIT_LOG_READ,
            Perm.PLAN_READ,
            Perm.MISSIONS_READ_ALL,
            Perm.WORKPAPERS_READ,
            Perm.DATA_READ,
            Perm.FINDINGS_READ,
            Perm.FRAMEWORKS_MANAGE,
            Perm.REVISION_READ,
        }
    ),
    Role.DIRECTEUR: frozenset(
        {
            Perm.DASHBOARDS_GLOBAL,
            Perm.AUDIT_LOG_READ,
            Perm.MISSIONS_READ_ALL,
            Perm.PLAN_READ,
            Perm.PLAN_MANAGE,
            Perm.PLAN_VALIDATE,
            Perm.MISSIONS_MANAGE,
            Perm.WORKPAPERS_READ,
            Perm.WORKPAPERS_APPROVE_FINAL,
            Perm.DATA_READ,
            Perm.FINDINGS_READ,
            Perm.FINDINGS_VALIDATE,
            Perm.REPORT_PUBLISH,
            Perm.FRAMEWORKS_MANAGE,
            Perm.REVISION_READ,
            Perm.REVISION_MANAGE,
            Perm.PORTFOLIO_MANAGE,
        }
    ),
    Role.CHEF_MISSION: frozenset(
        {
            Perm.PLAN_READ,
            Perm.MISSIONS_READ_OWN,
            Perm.MISSIONS_MANAGE,
            Perm.WORKPAPERS_READ,
            Perm.WORKPAPERS_REVIEW,
            Perm.DATA_READ,
            Perm.DATA_ANALYZE,
            Perm.FINDINGS_READ,
            Perm.FINDINGS_WRITE,
            Perm.FINDINGS_VALIDATE,
            Perm.REVISION_READ,
            Perm.REVISION_WORK,
            Perm.REVISION_MANAGE,
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
            Perm.REVISION_READ,
            Perm.REVISION_WORK,
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
            Perm.REVISION_READ,
        }
    ),
    Role.AUDITE: frozenset({Perm.FINDINGS_RESPOND}),
}
# Associé signataire : droits du Directeur, mais sur ses seuls dossiers, et signature.
ROLE_PERMISSIONS[Role.ASSOCIE] = (
    ROLE_PERMISSIONS[Role.DIRECTEUR]
    - {
        Perm.MISSIONS_READ_ALL,
        Perm.PLAN_MANAGE,
        Perm.PLAN_VALIDATE,
        Perm.DASHBOARDS_GLOBAL,
        Perm.FRAMEWORKS_MANAGE,
        Perm.AUDIT_LOG_READ,
    }
) | {Perm.MISSIONS_READ_OWN, Perm.WORKPAPERS_REVIEW, Perm.REVISION_WORK, Perm.OPINION_SIGN}
# Inspecteur CIPRES : droits du Chef de mission sur les missions d'inspection confiées.
ROLE_PERMISSIONS[Role.INSPECTEUR_CIPRES] = ROLE_PERMISSIONS[Role.CHEF_MISSION]


# Expert-comptable : droits du Directeur sur son seul portefeuille (Module 6).
ROLE_PERMISSIONS[Role.EXPERT_COMPTABLE] = (
    ROLE_PERMISSIONS[Role.DIRECTEUR]
    - {
        Perm.MISSIONS_READ_ALL,
        Perm.PLAN_MANAGE,
        Perm.PLAN_VALIDATE,
        Perm.DASHBOARDS_GLOBAL,
        Perm.FRAMEWORKS_MANAGE,
        Perm.AUDIT_LOG_READ,
    }
) | {Perm.MISSIONS_READ_OWN, Perm.WORKPAPERS_REVIEW, Perm.REVISION_WORK, Perm.DATA_ANALYZE}
# Collaborateur comptable : droits de l'Auditeur sur les dossiers clients qui lui sont affectés.
ROLE_PERMISSIONS[Role.COLLABORATEUR] = ROLE_PERMISSIONS[Role.AUDITEUR]


def has_permission(role: str, perm: Perm) -> bool:
    try:
        return perm in ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return False


def can_review(preparer_id: object, reviewer_id: object) -> bool:
    """Séparation des tâches : le préparateur d'un papier de travail n'en est pas le réviseur."""
    return preparer_id != reviewer_id
