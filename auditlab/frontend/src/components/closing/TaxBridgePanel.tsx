import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";

interface Element { code: string | null; libelle: string; sens: string; calcule: string | null; montant: string; origine: string; id: string | null }
interface Bridge {
  resultat_net: string; impot_comptabilise: string; resultat_avant_impot: string; elements: Element[];
  reintegrations: string; deductions: string; resultat_fiscal: string; chiffre_affaires: string;
  impot: { impot_societes: string; impot_minimum: string; impot_du: string; regime: string; ecart_comptabilise: string } | null;
  parametres_manquants: string[];
}

/** Tableau de passage du résultat comptable au résultat fiscal (RCO-20). */
export default function TaxBridgePanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Bridge | null>(null);
  const [f, setF] = useState({ libelle: "", sens: "reintegration", montant: "" });
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/tax-bridge`;
  const load = useCallback(() => api<Bridge>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setData(await post<Bridge>(`${url}/lines`, f));
      setF({ libelle: "", sens: f.sens, montant: "" });
    } catch (err) {
      setError((err as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const row = (label: string, value: string, strong = false) => (
    <tr className={strong ? "font-semibold" : ""}><th scope="row" className="py-1 pr-3 text-left font-normal">{label}</th><td className="py-1 text-right font-mono">{formatDecimal(value)}</td></tr>
  );
  return (
    <section className="carte space-y-3" aria-labelledby="tp-titre">
      <h2 id="tp-titre" className="text-base font-semibold">{t("passageFiscal.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <table className="w-full max-w-2xl text-sm">
        <tbody className="divide-y divide-slate-100">
          {row(t("passageFiscal.resultatNet"), data.resultat_net)}
          {row(t("passageFiscal.impotComptabilise"), data.impot_comptabilise)}
          {row(t("passageFiscal.avantImpot"), data.resultat_avant_impot, true)}
          {data.elements.map((e) => (
            <tr key={`${e.code}-${e.id}`}>
              <th scope="row" className="py-1 pr-3 text-left font-normal">
                {e.sens === "reintegration" ? "+ " : "− "}{e.libelle}
                {e.origine === "saisi" && <span className="ml-1 text-xs text-slate-500">({t("passageFiscal.calcule", { montant: formatDecimal(e.calcule ?? "0") })})</span>}
                {e.id && <button type="button" className="ml-2 text-xs underline" onClick={() => void del(`${url}/lines/${e.id}`).then(load)}>{t("immobilisations.retirer")}</button>}
              </th>
              <td className="py-1 text-right font-mono">{formatDecimal(e.montant)}</td>
            </tr>
          ))}
          {row(t("passageFiscal.resultatFiscal"), data.resultat_fiscal, true)}
        </tbody>
      </table>
      {data.impot ? (
        <p className="text-sm">{t("passageFiscal.impot", { is: formatDecimal(data.impot.impot_societes), minimum: formatDecimal(data.impot.impot_minimum), du: formatDecimal(data.impot.impot_du), regime: t(`passageFiscal.regimes.${data.impot.regime}`), ecart: formatDecimal(data.impot.ecart_comptabilise) })}</p>
      ) : <Alert kind="info">{t("passageFiscal.parametres", { liste: data.parametres_manquants.join(", ") })}</Alert>}
      {file.peut_travailler && (
        <form onSubmit={(e) => void submit(e)} className="flex flex-wrap items-end gap-2" aria-label={t("passageFiscal.ajouter")}>
          <div className="min-w-64 flex-1"><label htmlFor="tp-lib" className="etiquette">{t("passageFiscal.libelle")}</label><input id="tp-lib" className="champ" required value={f.libelle} onChange={(e) => setF({ ...f, libelle: e.target.value })} /></div>
          <div>
            <label htmlFor="tp-sens" className="etiquette">{t("passageFiscal.sens")}</label>
            <select id="tp-sens" className="champ" value={f.sens} onChange={(e) => setF({ ...f, sens: e.target.value })}>
              <option value="reintegration">{t("passageFiscal.sensValeurs.reintegration")}</option>
              <option value="deduction">{t("passageFiscal.sensValeurs.deduction")}</option>
            </select>
          </div>
          <div><label htmlFor="tp-mt" className="etiquette">{t("passageFiscal.montant")}</label><input id="tp-mt" className="champ" required value={f.montant} onChange={(e) => setF({ ...f, montant: e.target.value })} /></div>
          <button type="submit" className="btn-secondaire">{t("passageFiscal.ajouter")}</button>
        </form>
      )}
    </section>
  );
}
