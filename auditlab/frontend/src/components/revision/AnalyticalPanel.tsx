import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, put } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDateHeure, formatDecimal, formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Line {
  niveau: "poste" | "compte";
  code: string;
  libelle: string | null;
  N: string;
  "N-1": string;
  variation: string;
  variation_pct: string | null;
  signale: boolean;
  justification: string | null;
  justifie_le: string | null;
  total?: boolean;
}
interface Review {
  seuils: { planification: string; insignifiant: string; variation_pct: string };
  postes: Line[];
  comptes: Line[];
  nb_signales: number;
  nb_non_justifies: number;
}

/** Revue analytique N/N-1 avec justification obligatoire des variations signalées (REV-12). */
export default function AnalyticalPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Review | null>(null);
  const [level, setLevel] = useState<"postes" | "comptes">("postes");
  const [onlyFlagged, setOnlyFlagged] = useState(true);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/analytical-review`;
  useEffect(() => {
    api<Review>(url).then(setData).catch((e: Error) => setError(e.message));
  }, [url]);
  if (error && !data) return <Alert kind="erreur">{error}</Alert>;
  if (!data) return null;

  const save = async (l: Line) => {
    setError(null);
    try {
      setData(await put<Review>(`${url}/justifications`, { niveau: l.niveau, code: l.code, texte: drafts[`${l.niveau}:${l.code}`] ?? l.justification ?? "" }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const rows = data[level].filter((l) => !onlyFlagged || l.signale);

  return (
    <section className="carte space-y-3" aria-labelledby="ra-titre">
      <h2 id="ra-titre" className="text-base font-semibold">{t("analytique.titre")}</h2>
      <p className="text-sm text-slate-600">
        {t("analytique.regle", { plan: formatNombre(Number(data.seuils.planification)), pct: formatDecimal(data.seuils.variation_pct), insignifiant: formatNombre(Number(data.seuils.insignifiant)) })}
      </p>
      <p role="status" className={`text-sm font-medium ${data.nb_non_justifies ? "text-red-700" : "text-emerald-800"}`}>
        {t("analytique.bilan", { signales: data.nb_signales, restant: data.nb_non_justifies })}
      </p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="flex flex-wrap gap-4 text-sm">
        <fieldset className="flex gap-3">
          <legend className="sr-only">{t("analytique.niveau")}</legend>
          {(["postes", "comptes"] as const).map((k) => (
            <label key={k} className="flex items-center gap-1"><input type="radio" name="ra-niveau" checked={level === k} onChange={() => setLevel(k)} />{t(`analytique.niveaux.${k}`)}</label>
          ))}
        </fieldset>
        <label className="flex items-center gap-1"><input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />{t("analytique.seulementSignalees")}</label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr>{["ligne", "N", "N-1", "variation", "pct", "justification"].map((k) => <th key={k} scope="col" className={`py-1 pr-3 ${["N", "N-1", "variation", "pct"].includes(k) ? "text-right" : ""}`}>{t(`analytique.col.${k}`)}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100 align-top">
            {rows.map((l) => {
              const key = `${l.niveau}:${l.code}`;
              return (
                <tr key={key} className={l.total ? "bg-slate-50 font-semibold" : l.signale && !l.justification ? "bg-amber-50" : ""}>
                  <td className="py-1 pr-3"><span className="font-mono text-xs">{l.code}</span> {l.libelle}</td>
                  <td className="py-1 pr-3 text-right font-mono">{formatNombre(Number(l.N))}</td>
                  <td className="py-1 pr-3 text-right font-mono">{formatNombre(Number(l["N-1"]))}</td>
                  <td className="py-1 pr-3 text-right font-mono">{formatNombre(Number(l.variation))}</td>
                  <td className="py-1 pr-3 text-right">{l.variation_pct !== null ? `${formatDecimal(l.variation_pct)} %` : l.variation !== "0.00" ? t("analytique.nouveau") : ""}</td>
                  <td className="py-1 min-w-64">
                    {l.signale && (file.peut_travailler ? (
                      <div className="flex gap-1">
                        <label htmlFor={`ra-${key}`} className="sr-only">{t("analytique.justifier", { ligne: l.code })}</label>
                        <textarea id={`ra-${key}`} rows={1} className="champ" value={drafts[key] ?? l.justification ?? ""} onChange={(e) => setDrafts({ ...drafts, [key]: e.target.value })} />
                        <button type="button" className="btn-secondaire" onClick={() => void save(l)}>{t("commun.enregistrer")}</button>
                      </div>
                    ) : <span>{l.justification ?? t("analytique.aJustifier")}</span>)}
                    {l.justifie_le && <p className="text-xs text-slate-600">{t("analytique.justifieLe", { date: formatDateHeure(l.justifie_le) })}</p>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
