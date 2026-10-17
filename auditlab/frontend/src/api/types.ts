import type { Role } from "../lib/permissions";

export interface TeamRef {
  id: string;
  nom: string;
}

export interface User {
  id: string;
  email: string;
  nom: string;
  role: Role;
  actif: boolean;
  mfa_enabled: boolean;
  is_locked: boolean;
  teams: TeamRef[];
  created_at: string | null;
}

export interface Me extends User {
  permissions: string[];
  mfa_required: boolean;
}

export interface Team extends TeamRef {
  description: string | null;
  members: { id: string; nom: string; role: Role }[];
}

export interface AuditEntry {
  seq: number;
  horodatage: string;
  user_id: string | null;
  user_nom: string | null;
  action: string;
  object_type: string | null;
  object_id: string | null;
  avant: Record<string, unknown> | null;
  apres: Record<string, unknown> | null;
  hash_precedent: string;
  hash: string;
}

export interface AuditPage {
  total: number;
  items: AuditEntry[];
}

export interface ChainReport {
  ok: boolean;
  entries: number;
  first_broken_seq: number | null;
  reason: string | null;
}

export interface LoginResult {
  token: string;
  mfa_enrollment_required: boolean;
}

export type EntityType = "direction" | "filiale" | "processus" | "systeme";

export interface AuditableEntity {
  id: string;
  nom: string;
  type: EntityType;
  parent_id: string | null;
  description: string | null;
  responsable: string | null;
  date_dernier_audit: string | null;
  score_risque: number | null;
}
