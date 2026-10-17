/** Miroir de app/risk_scoring.py, pour afficher la note d'ancienneté avant enregistrement. */
export function seniorityNote(lastAudit: string | null, on: string): number {
  if (!lastAudit) return 5;
  const [ly, lm, ld] = lastAudit.split("-").map(Number);
  const [y, m, d] = on.split("-").map(Number);
  const years = y - ly - (m < lm || (m === lm && d < ld) ? 1 : 0);
  return Math.max(1, Math.min(5, 1 + Math.max(years, 0)));
}

/** Classe de couleur d'un score sur 100 (vert → rouge). */
export function scoreClass(score: number | null): string {
  if (score === null) return "bg-slate-100 text-slate-700";
  if (score >= 75) return "bg-red-100 text-red-900";
  if (score >= 55) return "bg-orange-100 text-orange-900";
  if (score >= 35) return "bg-yellow-100 text-yellow-900";
  return "bg-green-100 text-green-900";
}

export function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export type Level = "faible" | "modere" | "eleve" | "critique";

/** Niveau d'une case de la carte selon impact × probabilité (1 à 25). */
export function cellLevel(impact: number, probabilite: number): Level {
  const p = impact * probabilite;
  if (p >= 15) return "critique";
  if (p >= 8) return "eleve";
  if (p >= 4) return "modere";
  return "faible";
}

export const LEVEL_CLASSES: Record<Level, string> = {
  faible: "bg-green-200 text-green-950",
  modere: "bg-yellow-200 text-yellow-950",
  eleve: "bg-orange-300 text-orange-950",
  critique: "bg-red-400 text-red-950",
};
