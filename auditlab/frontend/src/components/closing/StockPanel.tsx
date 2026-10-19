import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, put, upload } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import GenerateEntry from "./GenerateEntry";

interface Stock {
  methode: "cmp" | "peps";
  articles: { article: string; libelle: string | null; compte: string; quantite: string; valeur: string; cout_unitaire: string; depreciation: string }[];
  comptes: { compte: string; stock_final: string; solde_comptable: string; variation: string }[];
  depreciations?: { compte: string; requise: string; comptabilisee: string; ecart: string }[];
  non_valorises: string[];
  comptes_sans_regle?: string[];
  fichiers: Record<string, { nom: string; lignes: number }>;
}

/** Inventaire physique, valorisation et variation de stock (RCO-12). */
export default function StockPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Stock | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/stock`;
  const load = useCallback(() => api<Stock>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const run = async (action: () => Promise<Stock>) => {
    setError(null);
    try {
      setData(await action());
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  return (
    <section className="carte space-y-3" aria-labelledby="st-titre">
      <h2 id="st-titre" className="text-base font-semibold">{t("stocks.titre")}</h2>
      <p className="text-sm text-slate-600">{t("stocks.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      {file.peut_travailler && (
        <div className="flex flex-wrap items-end gap-3 text-sm">
          {(["inventory", "movements"] as const).map((k) => (
            <label key={k} className="btn-secondaire cursor-pointer">
              {t(`stocks.importer.${k}`)}{data.fichiers[k] && ` (${data.fichiers[k].lignes})`}
              <input type="file" accept=".csv,.xlsx,.xls" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(() => upload<Stock>(`${url}/files/${k}`, f)); }} />
            </label>
          ))}
          <div>
            <label htmlFor="st-methode" className="etiquette">{t("stocks.methode")}</label>
            <select id="st-methode" className="champ" value={data.methode} onChange={(e) => void run(() => put<Stock>(`${url}/method`, { methode: e.target.value }))}>
              <option value="cmp">{t("stocks.methodes.cmp")}</option>
              <option value="peps">{t("stocks.methodes.peps")}</option>
            </select>
          </div>
        </div>
      )}
      {data.non_valorises.length > 0 && <Alert kind="info">{t("stocks.nonValorises", { liste: data.non_valorises.join(", ") })}</Alert>}
      {data.articles.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600"><tr>{["article", "compte", "quantite", "cout", "valeur", "depreciation"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`stocks.col.${k}`)}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.articles.map((a) => (
              <tr key={a.article}>
                <th scope="row" className="py-1 pr-3 font-normal"><span className="font-mono text-xs">{a.article}</span> {a.libelle}</th>
                <td className="py-1 pr-3 font-mono">{a.compte}</td>
                {[a.quantite, a.cout_unitaire, a.valeur, a.depreciation].map((v, i) => <td key={i} className="py-1 pr-3 text-right font-mono">{formatDecimal(v)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data.comptes.length > 0 && (
        <ul className="text-sm">
          {data.comptes.map((c) => <li key={c.compte}>{t("stocks.variation", { compte: c.compte, final: formatDecimal(c.stock_final), comptable: formatDecimal(c.solde_comptable), variation: formatDecimal(c.variation) })}</li>)}
          {data.depreciations?.map((d) => <li key={d.compte}>{t("stocks.depreciationLigne", { compte: d.compte, requise: formatDecimal(d.requise), comptabilisee: formatDecimal(d.comptabilisee) })}</li>)}
        </ul>
      )}
      {file.peut_travailler && <GenerateEntry url={`${url}/entry`} disabled={data.articles.length === 0} />}
    </section>
  );
}
