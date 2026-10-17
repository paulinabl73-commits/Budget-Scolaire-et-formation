import type { ControlNature, ControlType, Cycle, Frequency, RiskCategory } from "../api/types";

export const CYCLES: Cycle[] = [
  "achats", "ventes", "paie", "tresorerie", "immobilisations", "stocks", "notes_de_frais",
  "systemes_information", "gouvernance", "conformite", "autre",
];
export const CATEGORIES: RiskCategory[] = ["operationnel", "reporting", "conformite", "strategique", "fraude"];
export const CONTROL_TYPES: ControlType[] = ["preventif", "detectif"];
export const NATURES: ControlNature[] = ["manuel", "automatique", "semi_automatique"];
export const FREQUENCIES: Frequency[] = ["ponctuel", "quotidien", "hebdomadaire", "mensuel", "trimestriel", "annuel"];
