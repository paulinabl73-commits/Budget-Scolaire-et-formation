import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download, put } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Synthesis {
  cycles: { cycle: string; "N-1": string; N: string; ajustements: string; revise: string; papiers: { reference: string; statut: string }[] }[];
  ajustements_acceptes: { numero: number; libelle: string; effet_resultat: string }[];
  non_corrigees: { cumul_resultat: string; conclusion: string } | null;
  points_en_suspens: { vue: string; texte: string }[];
  conclusion: string | null;
}

/** Note de synthèse générée (REV-26). */
export default function SynthesisPanel({ file, onNavigate }: { file: AuditFile; onNavigate: (vue: string) => void }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Synthesis | null>(null);
  const [conclusion, setConclusion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const url = `/audit-files/${file.id}/synthesis`;
  useEffect(() => {
    api<Synthesis>(url).then((d) => { setData(d); setConclusion(d.conclusion ?? ""); }).catch((e: Error) => setError(e.message));
  }, [url]);
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const n = (v: string) => formatNombre(Number(v));
  const save = async () => {
    setError(null);
    try {
      setData(await put<Synthesis>(`${url}/conclusion`, { conclusion }));
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const exportAs = (fmt: string) => download(`${url}/export?format=${fmt}`, undefined, `note_synthese.${fmt}`).catch((e: Error) => setError(e.message));

  return (
    <section className="carte space-y-4" aria-labelledby="syn-titre">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="syn-titre" className="text-base font-semibold">{t("synthese.titre")}</h2>
        <div className="flex gap-2">
          <button type="button" className="btn-secondaire" onClick={() => void exportAs("pdf")}>{t("synthese.pdf")}</button>
          <button type="button" className="btn-secondaire" onClick={() => void exportAs("docx")}>{t("synthese.word")}</button>
        </div>
      </div>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div>
        <h3 className="font-semibold">{t("synthese.suspens")}</h3>
        {data.points_en_suspens.length === 0 ? <p className="text-sm text-emerald-800">{t("synthese.aucunSuspens")}</p> : (
          <ul className="list-disc pl-5 text-sm">
            {data.points_en_suspens.map((p, i) => <li key={i}><button type="button" className="text-left underline" onClick={() => onNavigate(p.vue)}>{p.texte}</button></li>)}
          </ul>
        )}
      </div>
      <div>
        <h3 className="font-semibold">{t("synthese.cycles")}</h3>
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-600"><tr>{["cycle", "N-1", "N", "ajustements", "revise", "papiers"].map((k) => <th key={k} scope="col" className="py-1 pr-3 text-left">{t(`synthese.col.${k}`)}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.cycles.map((c) => (
              <tr key={c.cycle}><td className="py-1 pr-3">{c.cycle}</td>{(["N-1", "N", "ajustements", "revise"] as const).map((k) => <td key={k} className="py-1 pr-3 text-right font-mono">{n(c[k])}</td>)}
                <td className="py-1 text-xs">{c.papiers.map((p) => `${p.reference} (${t(`synthese.statuts.${p.statut}`, { defaultValue: p.statut })})`).join(", ")}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-sm">
        <h3 className="font-semibold">{t("synthese.anomalies")}</h3>
        <ul className="list-disc pl-5">{data.ajustements_acceptes.map((a) => <li key={a.numero}>AJE {a.numero} — {a.libelle} ({n(a.effet_resultat)})</li>)}</ul>
        {data.non_corrigees && <p>{t("synthese.nonCorrigees", { cumul: n(data.non_corrigees.cumul_resultat), conclusion: t(`synthese.verdicts.${data.non_corrigees.conclusion}`) })}</p>}
      </div>
      <div>
        <label htmlFor="syn-conclusion" className="font-semibold">{t("synthese.conclusion")}</label>
        <textarea id="syn-conclusion" rows={4} className="champ mt-1" readOnly={!file.peut_gerer} value={conclusion} onChange={(e) => { setConclusion(e.target.value); setSaved(false); }} />
        {file.peut_gerer && <button type="button" className="btn-primaire mt-2" onClick={() => void save()}>{saved ? t("synthese.enregistree") : t("commun.enregistrer")}</button>}
      </div>
    </section>
  );
}
