import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import GenerateEntry from "./GenerateEntry";

interface Data {
  positions: { id: string; compte: string; libelle: string; nature: string; devise: string; montant_devise: string; valeur_comptable: string; cours: string | null; valeur_cloture: string | null; ecart: string | null }[];
  cours_manquants: string[];
  pertes_latentes: string;
  gains_latents: string;
  provision_requise: string;
  provision_comptabilisee: string;
}
const EMPTY = { compte: "", libelle: "", nature: "creance", devise: "", montant_devise: "", valeur_comptable: "" };

/** Opérations en devises : écarts de conversion et provision pour perte de change (RCO-15). */
export default function CurrencyPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Data | null>(null);
  const [f, setF] = useState<Record<string, string>>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/currency-positions`;
  const load = useCallback(() => api<Data>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setData(await post<Data>(url, { ...f, devise: f.devise.toUpperCase() }));
      setF(EMPTY);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  return (
    <section className="carte space-y-3" aria-labelledby="dv-titre">
      <h2 id="dv-titre" className="text-base font-semibold">{t("devisesCloture.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {data.cours_manquants.length > 0 && <Alert kind="info">{t("devisesCloture.coursManquants", { liste: data.cours_manquants.join(", "), devise: file.devise })}</Alert>}
      {data.positions.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600"><tr>{["operation", "devise", "comptable", "cours", "cloture", "ecart"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`devisesCloture.col.${k}`)}</th>)}<th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.positions.map((p) => (
              <tr key={p.id}>
                <th scope="row" className="py-1 pr-3 font-normal"><span className="font-mono">{p.compte}</span> {p.libelle} <span className="text-xs text-slate-600">({t(`devisesCloture.natures.${p.nature}`)})</span></th>
                <td className="py-1 pr-3 text-right font-mono">{formatDecimal(p.montant_devise)} {p.devise}</td>
                <td className="py-1 pr-3 text-right font-mono">{formatDecimal(p.valeur_comptable)}</td>
                <td className="py-1 pr-3 text-right font-mono">{p.cours ?? "—"}</td>
                <td className="py-1 pr-3 text-right font-mono">{p.valeur_cloture ? formatDecimal(p.valeur_cloture) : "—"}</td>
                <td className="py-1 pr-3 text-right font-mono">{p.ecart ? formatDecimal(p.ecart) : "—"}</td>
                <td className="py-1"><button type="button" className="underline" onClick={() => void del(`${url}/${p.id}`).then(load)}>{t("immobilisations.retirer")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-sm">{t("devisesCloture.synthese", { pertes: formatDecimal(data.pertes_latentes), gains: formatDecimal(data.gains_latents), requise: formatDecimal(data.provision_requise), comptabilisee: formatDecimal(data.provision_comptabilisee) })}</p>
      {file.peut_travailler && (
        <>
          <GenerateEntry url={`${url}/entry`} disabled={data.positions.length === 0} />
          <form onSubmit={(e) => void submit(e)} className="grid gap-3 md:grid-cols-6" aria-label={t("devisesCloture.ajouter")}>
            {(["compte", "libelle", "devise", "montant_devise", "valeur_comptable"] as const).map((k) => (
              <div key={k}>
                <label htmlFor={`dv-${k}`} className="etiquette">{t(`devisesCloture.champs.${k}`)}</label>
                <input id={`dv-${k}`} className="champ" required value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
              </div>
            ))}
            <div>
              <label htmlFor="dv-nature" className="etiquette">{t("devisesCloture.champs.nature")}</label>
              <select id="dv-nature" className="champ" value={f.nature} onChange={(e) => setF({ ...f, nature: e.target.value })}>
                <option value="creance">{t("devisesCloture.natures.creance")}</option>
                <option value="dette">{t("devisesCloture.natures.dette")}</option>
              </select>
            </div>
            <div className="md:col-span-6"><button type="submit" className="btn-secondaire">{t("devisesCloture.ajouter")}</button></div>
          </form>
        </>
      )}
    </section>
  );
}
