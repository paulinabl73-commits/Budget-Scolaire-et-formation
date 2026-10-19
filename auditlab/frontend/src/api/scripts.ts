export interface ScriptEntry {
  type: "table" | "fichier";
  id: string;
  nom: string | null;
}

export interface ScriptRunInfo {
  id: string;
  script_id: string;
  statut: "en_cours" | "termine" | "erreur";
  declenchement: string;
  code_sha256: string;
  entrees: ScriptEntry[];
  debut: string | null;
  cree_le: string;
  duree_ms: number | null;
  sortie: string;
  erreur: string | null;
  indicateurs: Record<string, number>;
  tables: { id: string; nom: string; nb_lignes: number | null }[];
  par: string | null;
}

export interface ScriptInfo {
  id: string;
  engagement_id: string;
  nom: string;
  description: string | null;
  code: string;
  entrees: ScriptEntry[];
  derniere_execution: ScriptRunInfo | null;
}

export interface SdkFunction {
  nom: string;
  signature: string;
  doc: string;
}
