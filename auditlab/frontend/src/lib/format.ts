const dateHeure = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "short",
  timeStyle: "medium",
});
const dateCourte = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeZone: "UTC" });
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

/** Date seule (aaaa-mm-jj de l'API) au format jj/mm/aaaa. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? "" : dateCourte.format(d);
}

/** Taille de fichier lisible (Ko, Mo). */
export function formatTaille(octets: number): string {
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${formatNombre(Math.round(octets / 102.4) / 10)} Ko`;
  return `${formatNombre(Math.round(octets / (1024 * 102.4)) / 10)} Mo`;
}

/** Décimal transmis en texte par l'API (« 655.9570000000 ») : virgule, sans zéros inutiles. */
export function formatDecimal(value: string | null | undefined): string {
  if (!value) return "";
  return value.includes(".") ? value.replace(/\.?0+$/, "").replace(".", ",") : value;
}
