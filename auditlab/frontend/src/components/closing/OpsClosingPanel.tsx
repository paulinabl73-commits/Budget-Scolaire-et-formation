import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import GenerateEntry from "./GenerateEntry";

const NATURES = ["cotisations_a_recevoir", "prestations_a_payer", "provision_technique"] as const;
interface Data {
  elements: { id: string; nature: string; branche: string; libelle: string; compte_debit: string; compte_credit: string; montant: string | null }[];
  provisions_techniques: { branche: string; requise: string; constituee: string; ecart: string }[];
  parametres_manquants: string[];
  postes_manquants: string[];
  branches: string[];
}
const EMPTY = { nature: "cotisations_a_recevoir", branche: "", libelle: "", compte_debit: "", compte_credit: "", compte_reprise: "", montant: "" };

/** Écritures de clôture d'un organisme de prévoyance sociale (RCO-16). */
export default function OpsClosingPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Data | null>(null);
  const [f, setF] = useState<Record<string, string>>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/ops-closing`;
  const load = useCallback(() => api<Data>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setData(await post<Data>(url, Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]))));
      setF({ ...EMPTY, nature: f.nature });
    } catch (err) {
      setError((err as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const technical = f.nature === "provision_technique";
  return (
    <section className="carte space-y-3" aria-labelledby="oc-titre">
      <h2 id="oc-titre" className="text-base font-semibold">{t("clotureOps.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {(data.parametres_manquants.length > 0 || data.postes_manquants.length > 0) && <Alert kind="info">{t("clotureOps.manquants", { liste: [...data.parametres_manquants, ...data.postes_manquants].join(", ") })}</Alert>}
      {data.provisions_techniques.map((p) => <p key={p.branche} className="text-sm">{t("clotureOps.reserve", { branche: p.branche, requise: formatDecimal(p.requise), constituee: formatDecimal(p.constituee), ecart: formatDecimal(p.ecart) })}</p>)}
      <ul className="divide-y divide-slate-100 text-sm">
        {data.elements.map((e) => (
          <li key={e.id} className="flex justify-between gap-2 py-1">
            <span>{t(`clotureOps.natures.${e.nature}`)} · {e.branche} · {e.libelle} · {e.compte_debit} / {e.compte_credit}</span>
            <span className="font-mono">{e.montant ? formatDecimal(e.montant) : "—"} <button type="button" className="ml-2 font-sans underline" onClick={() => void del(`${url}/${e.id}`).then(load)}>{t("immobilisations.retirer")}</button></span>
          </li>
        ))}
      </ul>
      {file.peut_travailler && (
        <>
          <GenerateEntry url={`${url}/entry`} disabled={data.elements.length === 0} />
          <form onSubmit={(e) => void submit(e)} className="grid gap-3 md:grid-cols-4" aria-label={t("clotureOps.ajouter")}>
            <div>
              <label htmlFor="oc-nature" className="etiquette">{t("clotureOps.champs.nature")}</label>
              <select id="oc-nature" className="champ" value={f.nature} onChange={(e) => setF({ ...f, nature: e.target.value })}>
                {NATURES.map((n) => <option key={n} value={n}>{t(`clotureOps.natures.${n}`)}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="oc-branche" className="etiquette">{t("clotureOps.champs.branche")}</label>
              <select id="oc-branche" className="champ" required value={f.branche} onChange={(e) => setF({ ...f, branche: e.target.value })}>
                <option value="">—</option>
                {data.branches.map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>
            {(["libelle", "compte_debit", "compte_credit", ...(technical ? ["compte_reprise"] : ["montant"])] as string[]).map((k) => (
              <div key={k}>
                <label htmlFor={`oc-${k}`} className="etiquette">{t(`clotureOps.champs.${k}`)}</label>
                <input id={`oc-${k}`} className="champ" required value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
              </div>
            ))}
            <div className="md:col-span-4"><button type="submit" className="btn-secondaire">{t("clotureOps.ajouter")}</button></div>
          </form>
        </>
      )}
    </section>
  );
}
