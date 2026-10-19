import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import GenerateEntry from "./GenerateEntry";

interface Data {
  creances: { depreciation_requise: string; depreciation_comptabilisee: string; ecart: string } | null;
  provisions: { id: string; nature: string; libelle: string; montant_requis: string; compte_provision: string }[];
  comptes: { compte: string; requis: string; comptabilise: string; ecart: string }[];
}
const EMPTY = { nature: "litige", libelle: "", montant_requis: "", compte_provision: "", compte_dotation: "", compte_reprise: "" };

/** Provisions et dépréciations de la clôture (RCO-14). */
export default function ProvisionsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Data | null>(null);
  const [f, setF] = useState<Record<string, string>>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/provisions`;
  const load = useCallback(() => api<Data>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setData(await post<Data>(url, Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]))));
      setF(EMPTY);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  return (
    <section className="carte space-y-3" aria-labelledby="pv-titre">
      <h2 id="pv-titre" className="text-base font-semibold">{t("provisions.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <p className="text-sm">{data.creances
        ? t("provisions.creances", { requise: formatDecimal(data.creances.depreciation_requise), comptabilisee: formatDecimal(data.creances.depreciation_comptabilisee), ecart: formatDecimal(data.creances.ecart) })
        : t("provisions.sansGrandLivre")}</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {data.provisions.map((p) => (
          <li key={p.id} className="flex justify-between gap-2 py-1">
            <span>{t(`provisions.natures.${p.nature}`)} · {p.libelle} · {p.compte_provision}</span>
            <span className="font-mono">{formatDecimal(p.montant_requis)} <button type="button" className="ml-2 font-sans underline" onClick={() => void del(`${url}/${p.id}`).then(load)}>{t("immobilisations.retirer")}</button></span>
          </li>
        ))}
      </ul>
      {data.comptes.map((a) => <p key={a.compte} className="text-sm">{t("provisions.compte", { compte: a.compte, requis: formatDecimal(a.requis), comptabilise: formatDecimal(a.comptabilise), ecart: formatDecimal(a.ecart) })}</p>)}
      {file.peut_travailler && (
        <>
          <GenerateEntry url={`${url}/entry`} />
          <form onSubmit={(e) => void submit(e)} className="grid gap-3 md:grid-cols-4" aria-label={t("provisions.ajouter")}>
            <div>
              <label htmlFor="pv-nature" className="etiquette">{t("provisions.nature")}</label>
              <select id="pv-nature" className="champ" value={f.nature} onChange={(e) => setF({ ...f, nature: e.target.value })}>
                {["litige", "risque", "autre"].map((n) => <option key={n} value={n}>{t(`provisions.natures.${n}`)}</option>)}
              </select>
            </div>
            {(["libelle", "montant_requis", "compte_provision"] as const).map((k) => (
              <div key={k}>
                <label htmlFor={`pv-${k}`} className="etiquette">{t(`provisions.champs.${k}`)}</label>
                <input id={`pv-${k}`} className="champ" required={k !== "compte_provision"} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
              </div>
            ))}
            <div className="md:col-span-4"><button type="submit" className="btn-secondaire">{t("provisions.ajouter")}</button></div>
          </form>
        </>
      )}
    </section>
  );
}
