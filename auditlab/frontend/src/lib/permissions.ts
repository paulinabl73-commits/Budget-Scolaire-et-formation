export const PERM = {
  USERS_MANAGE: "users:manage",
  SETTINGS_MANAGE: "settings:manage",
  AUDIT_LOG_READ: "audit_log:read",
  PLAN_READ: "plan:read",
  PLAN_MANAGE: "plan:manage",
  PLAN_VALIDATE: "plan:validate",
} as const;

export type Role =
  | "administrateur"
  | "directeur_audit"
  | "chef_mission"
  | "auditeur"
  | "data_analyst"
  | "audite";

export const ROLES: Role[] = [
  "administrateur",
  "directeur_audit",
  "chef_mission",
  "auditeur",
  "data_analyst",
  "audite",
];

/** Affichage seulement : le serveur reste seul juge des droits sur chaque requête. */
export function can(permissions: string[] | undefined, perm: string): boolean {
  return !!permissions?.includes(perm);
}
