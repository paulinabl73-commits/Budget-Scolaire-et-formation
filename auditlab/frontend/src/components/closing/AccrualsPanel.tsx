import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDate, formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import GenerateEntry from "./GenerateEntry";

const TYPES = ["charge_a_payer", "produit_a_recevoir", "charge_constatee_avance", "produit_constate_avance"] as const;
interface Item { id: string; type: string; libelle: string; compte_gestion: string; compte_tiers: string; montant: string; periode_debut: string | null; periode_fin: string | null }
interface Data { elements: Item[]; totaux: Record<string, string>; comptes_proposes: Record<string, string> }
const EMPTY = { type: "charge_a_payer", libelle: "", compte_gestion: "", compte_tiers: "", montant: "", montant_total: "", periode_debut: "", periode_fin: "" };

/** Rattachement des charges et produits à l'exercice (RCO-13). */
export default function AccrualsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Data | null>(null);
  const [f, setF] = useState<Record<string, string>>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/accruals`;
  const load = useCallback(() => api<Data>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const deferredType = f.type.endsWith("avance");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]));
    try {
      setData(await post<Data>(url, body));
      setF({ ...EMPTY, type: f.type });
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const input = (k: string, type = "text") => (
    <div key={k}>
      <label htmlFor={`ac-${k}`} className="etiquette">{t(`rattachements.champs.${k}`)}</label>
      <input id={`ac-${k}`} type={type} className="champ" value={f[k]} placeholder={k === "compte_tiers" ? data?.comptes_proposes[f.type] : undefined} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </div>
  );
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  return (
    <section className="carte space-y-3" aria-labelledby="ac-titre">
      <h2 id="ac-titre" className="text-base font-semibold">{t("rattachements.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="flex flex-wrap gap-2 text-xs">{TYPES.map((k) => <li key={k} className="rounded bg-slate-100 px-2 py-0.5">{t(`rattachements.types.${k}`)} : {formatDecimal(data.totaux[k])}</li>)}</ul>
      {data.elements.length > 0 && (
        <ul className="divide-y divide-slate-100 text-sm">
          {data.elements.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-1">
              <span>{t(`rattachements.types.${a.type}`)} · {a.libelle} · {a.compte_gestion} / {a.compte_tiers}{a.periode_debut && ` · ${formatDate(a.periode_debut)} – ${formatDate(a.periode_fin)}`}</span>
              <span className="font-mono">{formatDecimal(a.montant)} <button type="button" className="ml-2 font-sans underline" onClick={() => void del(`${url}/${a.id}`).then(load)}>{t("immobilisations.retirer")}</button></span>
            </li>
          ))}
        </ul>
      )}
      {file.peut_travailler && (
        <>
          <GenerateEntry url={`${url}/entry`} disabled={data.elements.length === 0} />
          {file.precedent_exercice && <GenerateEntry url={`${url}/reversal`} />}
          <form onSubmit={(e) => void submit(e)} className="grid gap-3 md:grid-cols-4" aria-label={t("rattachements.ajouter")}>
            <div>
              <label htmlFor="ac-type" className="etiquette">{t("rattachements.champs.type")}</label>
              <select id="ac-type" className="champ" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>
                {TYPES.map((k) => <option key={k} value={k}>{t(`rattachements.types.${k}`)}</option>)}
              </select>
            </div>
            <div className="md:col-span-3">{input("libelle")}</div>
            {input("compte_gestion")}
            {input("compte_tiers")}
            {deferredType ? <>{input("montant_total")}{input("periode_debut", "date")}{input("periode_fin", "date")}</> : input("montant")}
            <div className="md:col-span-4"><button type="submit" className="btn-secondaire">{t("rattachements.ajouter")}</button></div>
          </form>
        </>
      )}
    </section>
  );
}
