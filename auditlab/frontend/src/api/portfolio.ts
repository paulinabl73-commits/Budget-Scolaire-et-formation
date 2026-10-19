/** Types du Module 6 (portefeuille de dossiers clients). */
export interface ClosingSummary {
  id: string;
  exercice: number;
  engagement_id: string;
  audit_file_id: string;
  etape: string;
  etapes: Record<string, string>;
  date_depot: string | null;
  revues?: Record<string, unknown>;
}

export interface PortfolioClient {
  id: string;
  raison_sociale: string;
  forme_juridique: string;
  regime_fiscal: string;
  framework_id: string;
  referentiel: string;
  pays: string;
  devise: string;
  jour_cloture: number;
  mois_cloture: number;
  date_cloture: string;
  taille: string;
  identifiant_fiscal: string | null;
  rccm: string | null;
  expert_id: string;
  expert_nom: string | null;
  collaborateur_id: string | null;
  collaborateur_nom: string | null;
  superviseur_id: string | null;
  superviseur_nom: string | null;
  contact_id: string | null;
  contact_nom: string | null;
  budget_jours: number;
  actif: boolean;
  clotures: ClosingSummary[];
  peut_gerer: boolean;
}

export interface PortfolioStaff {
  experts: { id: string; nom: string }[];
  collaborateurs: { id: string; nom: string }[];
  superviseurs: { id: string; nom: string }[];
  contacts: { id: string; nom: string }[];
}

export const FORMES = [
  "SA",
  "SARL",
  "SAS",
  "SNC",
  "SCS",
  "GIE",
  "EI",
  "association",
  "OPS",
  "autre",
] as const;
export const REGIMES = [
  "reel_normal",
  "reel_simplifie",
  "entreprenant",
  "exonere",
  "autre",
] as const;
export const TAILLES = ["tpe", "pme", "grande"] as const;
