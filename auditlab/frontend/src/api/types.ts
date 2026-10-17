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
  impact: number | null;
  probabilite: number | null;
  date_evaluation: string | null;
}

export type Axis = "impact" | "probabilite" | "autre";
export type CriterionMode = "note" | "anciennete";

export interface RiskCriterion {
  id: string;
  code: string;
  libelle: string;
  description: string | null;
  axe: Axis;
  mode: CriterionMode;
  poids: number;
  ordre: number;
  actif: boolean;
}

export interface AssessedCriterion {
  code: string;
  libelle: string;
  axe: Axis;
  mode: CriterionMode;
  poids: number;
  note: number;
}

export interface RiskAssessment {
  id: string;
  entity_id: string;
  date_evaluation: string;
  criteres: AssessedCriterion[];
  score: number;
  impact: number | null;
  probabilite: number | null;
  commentaire: string | null;
  created_at: string | null;
}

export interface MapEntity {
  id: string;
  nom: string;
  type: EntityType;
  score_risque: number | null;
  impact: number | null;
  probabilite: number | null;
}

export interface RiskMap {
  echelle: number;
  cellules: { impact: number; probabilite: number; entites: MapEntity[] }[];
  non_evaluees: MapEntity[];
}

export type PlanStatus = "brouillon" | "valide" | "remplace";

export interface PlanItem {
  id: string;
  entity_id: string;
  entity_nom: string;
  score_risque: number | null;
  titre: string;
  budget_jours: number;
  periode_debut: string;
  periode_fin: string;
  justification: string | null;
}

export interface PlanSummary {
  id: string;
  annee: number;
  version: number;
  statut: PlanStatus;
  capacite_jours: number | null;
  commentaire: string | null;
  nb_missions: number;
  total_jours: number;
  valide_par: string | null;
  valide_par_nom: string | null;
  valide_le: string | null;
  version_precedente_id: string | null;
  created_at: string | null;
}

export interface Plan extends PlanSummary {
  items: PlanItem[];
}

export type EngagementStatus =
  | "planifiee"
  | "preparation"
  | "terrain"
  | "revue"
  | "rapport"
  | "cloturee";
export type MissionRole = "chef_mission" | "auditeur" | "data_analyst" | "superviseur";

export interface Member {
  user_id: string;
  nom: string;
  email: string;
  role_mission: MissionRole;
}

export interface EngagementSummary {
  id: string;
  reference: string;
  titre: string;
  statut: EngagementStatus;
  date_debut: string;
  date_fin: string;
  budget_jours: number;
  jours_consommes: number;
  entity_id: string | null;
  entity_nom: string | null;
  plan_id: string | null;
  plan_item_id: string | null;
  chef_nom: string | null;
  mon_role: MissionRole | null;
}

export interface Engagement extends EngagementSummary {
  perimetre: string | null;
  objectifs: string | null;
  membres: Member[];
  transitions: Transition[];
  peut_gerer: boolean;
}

export interface Transition {
  statut: EngagementStatus;
  sens: "suivant" | "precedent";
  motif_blocage: string | null;
}

export interface StatusChange {
  horodatage: string;
  utilisateur: string | null;
  avant: EngagementStatus;
  apres: EngagementStatus;
}

export type TimeActivity = "preparation" | "terrain" | "revue" | "rapport" | "autre";

export interface TimeEntry {
  id: string;
  user_id: string;
  user_nom: string;
  date: string;
  heures: number;
  activite: TimeActivity;
  commentaire: string | null;
}

export interface TimeSummary {
  budget_jours: number;
  jours_consommes: number;
  ecart_jours: number;
  taux_consommation: number;
  heures_par_jour: number;
  par_personne: { cle: string; libelle: string; jours: number }[];
  par_activite: { cle: string; libelle: string; jours: number }[];
}
