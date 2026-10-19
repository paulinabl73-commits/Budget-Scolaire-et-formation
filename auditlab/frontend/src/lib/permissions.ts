export const PERM = {
  USERS_MANAGE: "users:manage",
  SETTINGS_MANAGE: "settings:manage",
  AUDIT_LOG_READ: "audit_log:read",
  PLAN_READ: "plan:read",
  PLAN_MANAGE: "plan:manage",
  PLAN_VALIDATE: "plan:validate",
  MISSIONS_MANAGE: "missions:manage",
  MISSIONS_READ_ALL: "missions:read_all",
  MISSIONS_READ_OWN: "missions:read_own",
  FRAMEWORKS_MANAGE: "frameworks:manage",
  REVISION_READ: "revision:read",
  REVISION_WORK: "revision:work",
  REVISION_MANAGE: "revision:manage",
  OPINION_SIGN: "revision:sign",
  PORTFOLIO_MANAGE: "portfolio:manage",
  REPORT_PUBLISH: "report:publish",
  DASHBOARDS_GLOBAL: "dashboards:global",
} as const;

export type Role =
  | "administrateur"
  | "directeur_audit"
  | "chef_mission"
  | "auditeur"
  | "data_analyst"
  | "audite"
  | "associe_signataire"
  | "inspecteur_cipres"
  | "expert_comptable"
  | "collaborateur_comptable";

export const ROLES: Role[] = [
  "administrateur",
  "directeur_audit",
  "chef_mission",
  "auditeur",
  "data_analyst",
  "audite",
  "associe_signataire",
  "inspecteur_cipres",
  "expert_comptable",
  "collaborateur_comptable",
];

/** Affichage seulement : le serveur reste seul juge des droits sur chaque requête. */
export function can(permissions: string[] | undefined, perm: string): boolean {
  return !!permissions?.includes(perm);
}
