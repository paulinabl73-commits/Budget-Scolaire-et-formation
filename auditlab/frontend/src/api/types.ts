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
  cloturee_le: string | null;
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

export type Cycle =
  | "achats" | "ventes" | "paie" | "tresorerie" | "immobilisations" | "stocks"
  | "notes_de_frais" | "systemes_information" | "gouvernance" | "conformite" | "autre";
export type RiskCategory = "operationnel" | "reporting" | "conformite" | "strategique" | "fraude";
export type ControlType = "preventif" | "detectif";
export type ControlNature = "manuel" | "automatique" | "semi_automatique";
export type Frequency = "ponctuel" | "quotidien" | "hebdomadaire" | "mensuel" | "trimestriel" | "annuel";

export type TestType = "conception" | "efficacite" | "substantif";

export interface Procedure {
  id: string;
  control_id: string;
  reference: string | null;
  description: string;
  type_test: TestType;
  assigne_a: string | null;
  assigne_nom: string | null;
  echeance: string | null;
  statut: ProcedureStatus;
  en_retard: boolean;
}

export type ProcedureStatus = "a_faire" | "en_cours" | "terminee";

export interface MyProcedure extends Procedure {
  engagement_id: string;
  engagement_reference: string;
  engagement_titre: string;
  controle: string;
}

export interface Control {
  id: string;
  libelle: string;
  description: string | null;
  cycle: Cycle;
  type_controle: ControlType;
  nature: ControlNature;
  frequence: Frequency;
  source_id: string | null;
  procedures: Procedure[];
}

export interface Risk {
  id: string;
  libelle: string;
  description: string | null;
  cycle: Cycle;
  categorie: RiskCategory;
  source_id: string | null;
  controles: Control[];
}

export interface Matrix {
  risques: Risk[];
  controles: Control[];
}

export interface EngagementTemplate {
  id: string;
  nom: string;
  description: string | null;
  perimetre: string | null;
  objectifs: string | null;
  budget_jours: number | null;
  nb_risques: number;
  nb_controles: number;
  nb_procedures: number;
}

export type ControlAssessment = "efficace" | "partiellement_efficace" | "inefficace";
export type RichDoc = { type: "doc"; content?: unknown[] } & Record<string, unknown>;

export interface WorkpaperSummary {
  id: string;
  engagement_id: string;
  reference: string;
  titre: string;
  procedure_id: string | null;
  procedure_reference: string | null;
  evaluation: ControlAssessment | null;
  version: number;
  updated_at: string | null;
  statut_signature: SignoffStatus;
  signatures: Signoff[];
}

export type SignoffType = "prepare" | "revu" | "approuve";
export type SignoffStatus = "brouillon" | SignoffType;

export interface Signoff {
  id: string;
  type: SignoffType;
  user_id: string;
  user_nom: string;
  signed_at: string;
  version: number;
  hash_contenu: string;
  annule_le: string | null;
  motif_annulation: string | null;
}

export interface Workpaper extends WorkpaperSummary {
  objectif: string | null;
  travaux: RichDoc;
  conclusion: string | null;
  peut_modifier: boolean;
  signatures_possibles: SignoffType[];
  motifs_refus: Record<string, string>;
}

export interface Attachment {
  id: string;
  workpaper_id: string;
  nom_fichier: string;
  content_type: string;
  taille: number;
  sha256: string;
  version: number;
  created_at: string | null;
  url: string;
}

export interface Tickmark {
  id: string;
  symbole: string;
  libelle: string;
  couleur: string;
  ordre: number;
  actif: boolean;
}

export interface VersionSummary {
  version: number;
  created_at: string | null;
  auteur: string | null;
  hash_contenu: string;
}

export interface FieldDiff {
  champ: string;
  libelle: string;
  modifie: boolean;
  segments: { type: "egal" | "ajoute" | "supprime"; texte: string }[];
}

export type ReviewNoteStatus = "ouverte" | "repondue" | "cloturee";

export interface ReviewNote {
  id: string;
  workpaper_id: string;
  workpaper_reference: string | null;
  texte: string;
  ancre: { champ: string; citation: string | null };
  statut: ReviewNoteStatus;
  auteur: string | null;
  created_by: string | null;
  created_at: string | null;
  cloturee_le: string | null;
  reponses: { id: string; texte: string; auteur: string | null; created_at: string | null }[];
}

export interface AppNotification {
  id: string;
  type: string;
  titre: string;
  message: string;
  lien: string | null;
  lue_le: string | null;
  created_at: string | null;
}

export type ColumnType = "texte" | "entier" | "decimal" | "date" | "booleen" | "date_heure";

export interface Dataset {
  id: string;
  engagement_id: string;
  nom: string;
  description: string | null;
  kind: "import" | "vue" | "analyse";
  statut: "en_cours" | "pret" | "erreur";
  erreur: string | null;
  parent_dataset_id: string | null;
  source_nom: string | null;
  source_format: string | null;
  source_sha256: string | null;
  source_taille: number | null;
  nb_lignes: number | null;
  nb_colonnes: number | null;
  schema: { nom: string; type: ColumnType; dtype: string }[];
  totaux_controle: Record<string, { somme?: string; valeurs?: number; min?: string | null; max?: string | null }>;
  parquet_sha256: string | null;
  definition: Record<string, unknown>;
  options: Record<string, unknown>;
  duree_ms: number | null;
  created_at: string | null;
  lecture_seule: boolean;
  operation: string | null;
  resultat: Record<string, unknown>;
}

export interface AnalysisParam {
  nom: string;
  type: "colonne" | "colonnes" | "nombre" | "entier" | "graine" | "nombres" | "texte" | "expression" | "choix" | "date" | "agregats" | "paires";
  requis: boolean;
  defaut: unknown;
  choix: string[];
  table: number;
  types_colonne: string[];
  minimum: number | null;
  maximum: number | null;
}

export interface AnalysisOperation {
  code: string;
  exigence: string;
  entrees: number;
  params: AnalysisParam[];
}

export interface UploadInfo {
  id: string;
  nom_fichier: string;
  format: string;
  taille: number;
  sha256: string;
}

export interface DataSourceInfo {
  id: string;
  nom: string;
  description: string | null;
  actif: boolean;
  dialecte: string;
}

export type Criticality = "faible" | "moyenne" | "elevee" | "critique";

export interface Finding {
  id: string;
  engagement_id: string;
  reference: string;
  titre: string;
  critere: string | null;
  constat: string | null;
  cause: string | null;
  consequence: string | null;
  recommandation: string | null;
  criticite: Criticality;
  risk_id: string | null;
  control_id: string | null;
  workpaper_ids: string[];
  statut: "brouillon" | "envoye" | "repondu" | "valide";
  audite_id: string | null;
  envoye_le: string | null;
  date_limite_reponse: string | null;
  reponse_position: string | null;
  reponse_commentaire: string | null;
  repondu_le: string | null;
  valide_le: string | null;
  commentaire_validation: string | null;
  created_at: string | null;
  risque: string | null;
  controle: string | null;
  papiers: { id: string; reference: string; titre: string }[];
  audite_nom: string | null;
  peut_modifier: boolean;
}

export interface ActionPlan {
  id: string;
  finding_id: string;
  description: string;
  responsable_id: string | null;
  responsable_nom: string | null;
  echeance: string;
  statut: "a_lancer" | "en_cours" | "realise" | "verifie" | "risque_accepte";
  propose_par_audite: boolean;
  commentaire: string | null;
  verifie_le: string | null;
  relances: { type: string; date: string }[];
  created_at: string | null;
  responsable: string | null;
  en_retard: boolean;
  constat_reference: string | null;
  constat_titre: string | null;
  mission_id: string | null;
  transitions: string[];
}

export interface Auditee {
  id: string;
  nom: string;
  email: string;
}

export interface AuditFile {
  id: string;
  engagement_id: string;
  entity_id: string;
  exercice: number;
  date_debut: string;
  date_fin: string;
  framework_id: string;
  ifrs_framework_id: string | null;
  normative_id: string | null;
  devise: string;
  precedent_id: string | null;
  statut: string;
  base_seuil: string | null;
  montant_base: string | null;
  pct_seuil: string | null;
  seuil_signification: string | null;
  pct_planification: string | null;
  seuil_planification: string | null;
  pct_insignifiant: string | null;
  seuil_insignifiant: string | null;
  justification_seuil: string | null;
  seuil_variation_pct: string;
  entite: string | null;
  referentiel: string | null;
  referentiel_ifrs: string | null;
  cadre_normatif: string | null;
  precedent_exercice: number | null;
  peut_travailler: boolean;
  peut_gerer: boolean;
  peut_signer: boolean;
}

export interface FrameworkSummary {
  id: string;
  code: string;
  version: string;
  libelle: string;
  pays: string;
  actif: boolean;
}
