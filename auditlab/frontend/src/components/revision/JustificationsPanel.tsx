import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download, post, put, upload } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";

interface Row {
  compte: string;
  libelle: string | null;
  solde: string;
  montant_justifie: string | null;
  ecart: string | null;
  commentaire: string | null;
  statut: "justifie" | "sans_piece" | "ecart" | "non_justifie";
  fichiers: { id: string; nom_fichier: string }[];
  revu: boolean;
  commentaire_revue: string | null;
  signale: boolean;
}
interface Data { comptes: Row[]; justifies: number; signales: number; total: number }
const BADGE = { justifie: "bg-emerald-50 text-emerald-800", sans_piece: "bg-amber-50 text-amber-800", ecart: "bg-red-50 text-red-800", non_justifie: "bg-slate-100 text-slate-700" };

/** Justification des comptes de bilan d'une clôture (RCO-09). */
export default function JustificationsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const url = `/audit-files/${file.id}/justifications`;
  const load = useCallback(() => api<Data>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const run = async (action: () => Promise<Data>) => {
    setError(null);
    try {
      setData(await action());
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const justify = (r: Row) => {
    const amount = window.prompt(t("justifications.montant"), r.montant_justifie ?? r.solde);
    if (amount === null) return;
    const comment = window.prompt(t("justifications.commentaire"), r.commentaire ?? "") ?? r.commentaire;
    void run(() => put<Data>(`${url}/${r.compte}`, { montant_justifie: amount.replace(/\s/g, "").replace(",", ".") || null, commentaire: comment || null }));
  };
  const review = (r: Row) => {
    const comment = window.prompt(t("justifications.commentaireRevue"), "");
    if (comment === null) return;
    void run(() => post<Data>(`${url}/${r.compte}/review`, { commentaire: comment || null }));
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const rows = onlyFlagged ? data.comptes.filter((r) => r.signale) : data.comptes;
  return (
    <section className="carte space-y-3" aria-labelledby="just-titre">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="just-titre" className="text-base font-semibold">{t("justifications.titre")}</h2>
        <span className="text-sm text-slate-600">{t("justifications.synthese", { justifies: data.justifies, total: data.total, signales: data.signales })}</span>
      </div>
      {error && <Alert kind="erreur">{error}</Alert>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />{t("justifications.seulementSignales")}</label>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-600">
          <tr>{["compte", "solde", "justifie", "ecart", "statut", "pieces"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`justifications.col.${k}`)}</th>)}<th /></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.compte} className={r.signale ? "bg-amber-50/40" : ""}>
              <th scope="row" className="py-1 pr-3 font-normal"><span className="font-mono">{r.compte}</span> {r.libelle}{r.commentaire && <span className="block text-xs text-slate-600">{r.commentaire}</span>}</th>
              <td className="py-1 pr-3 text-right font-mono">{formatDecimal(r.solde)}</td>
              <td className="py-1 pr-3 text-right font-mono">{r.montant_justifie ? formatDecimal(r.montant_justifie) : "—"}</td>
              <td className="py-1 pr-3 text-right font-mono">{r.ecart && r.ecart !== "0.00" ? formatDecimal(r.ecart) : "—"}</td>
              <td className="py-1 pr-3">
                <span className={`rounded px-2 py-0.5 text-xs ${BADGE[r.statut]}`}>{t(`justifications.statuts.${r.statut}`)}</span>
                {r.revu && <span className="ml-1 text-xs text-slate-600" title={r.commentaire_revue ?? ""}>{t("justifications.revu")}</span>}
              </td>
              <td className="py-1 pr-3">{r.fichiers.map((f) => <button key={f.id} type="button" className="mr-2 underline" onClick={() => void download(`/client-files/${f.id}/content`, undefined, f.nom_fichier)}>{f.nom_fichier}</button>)}</td>
              <td className="py-1 text-right whitespace-nowrap">
                {file.peut_travailler && (
                  <>
                    <button type="button" className="mr-2 underline" onClick={() => justify(r)}>{t("justifications.justifier")}</button>
                    <label className="mr-2 cursor-pointer underline">{t("justifications.joindre")}
                      <input type="file" className="sr-only" aria-label={t("justifications.joindreA", { compte: r.compte })} onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(() => upload<Data>(`${url}/${r.compte}/files`, f)); }} />
                    </label>
                    {r.signale && file.peut_gerer && <button type="button" className="underline" onClick={() => review(r)}>{t("justifications.revoir")}</button>}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
