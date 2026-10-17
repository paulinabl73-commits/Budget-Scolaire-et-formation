const dateHeure = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "short",
  timeStyle: "medium",
});
const nombre = new Intl.NumberFormat("fr-FR");

/** Date et heure au format français (jj/mm/aaaa hh:mm:ss). */
export function formatDateHeure(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : dateHeure.format(d);
}

/** Nombre au format français (espace pour les milliers, virgule décimale). */
export function formatNombre(n: number): string {
  return nombre.format(n);
}

/** Résumé lisible d'un objet JSON du journal ({"nom": "x"} → "nom : x"). */
export function resumeJson(value: Record<string, unknown> | null): string {
  if (!value) return "";
  return Object.entries(value)
    .map(([k, v]) => `${k} : ${typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}
