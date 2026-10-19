import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDate, formatDecimal } from "../../lib/format";
import Alert from "../Alert";

interface Controls {
  regles_disponibles: boolean;
  soldes_anormaux: { compte: string; libelle: string | null; solde: string; anomalie: string }[];
  grand_livre: boolean;
  tiers_non_lettres: { compte: string; lignes_non_lettrees: number; montant_non_lettre: string; plus_ancienne: string | null; anomalies: string[] }[] | null;
  analyses: { id: string; nom: string; statut: string; nb_lignes: number | null }[];
}

/** Contrôles automatiques de la comptabilité sur balance et grand livre (RCO-08). */
export default function AccountingControlsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Controls | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/accounting-controls`;
  const load = useCallback(() => api<Controls>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const launch = async () => {
    setError(null);
    try {
      await post(`${url}/ledger`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  return (
    <div className="space-y-4">
      {error && <Alert kind="erreur">{error}</Alert>}
      <section className="carte space-y-2" aria-labelledby="cc-soldes">
        <h2 id="cc-soldes" className="text-base font-semibold">{t("controlesComptables.soldes")}</h2>
        {!data.regles_disponibles ? <p className="text-sm text-slate-600">{t("controlesComptables.sansRegles")}</p>
          : data.soldes_anormaux.length === 0 ? <p className="text-sm text-emerald-700">{t("controlesComptables.aucunSolde")}</p> : (
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-slate-600"><tr><th scope="col" className="py-1 pr-3">{t("controlesComptables.compte")}</th><th scope="col" className="py-1 pr-3 text-right">{t("controlesComptables.solde")}</th><th scope="col" className="py-1 pr-3">{t("controlesComptables.anomalie")}</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.soldes_anormaux.map((r) => (
                  <tr key={r.compte}><th scope="row" className="py-1 pr-3 font-normal"><span className="font-mono">{r.compte}</span> {r.libelle}</th><td className="py-1 pr-3 text-right font-mono">{formatDecimal(r.solde)}</td><td className="py-1 pr-3 text-red-700">{r.anomalie}</td></tr>
                ))}
              </tbody>
            </table>
          )}
      </section>
      <section className="carte space-y-2" aria-labelledby="cc-gl">
        <h2 id="cc-gl" className="text-base font-semibold">{t("controlesComptables.grandLivre")}</h2>
        {!data.grand_livre ? <p className="text-sm text-slate-600">{t("controlesComptables.sansGrandLivre")}</p> : (
          <>
            <h3 className="text-sm font-semibold">{t("controlesComptables.tiers")}</h3>
            {data.tiers_non_lettres && data.tiers_non_lettres.length > 0 ? (
              <ul className="text-sm">
                {data.tiers_non_lettres.map((r) => (
                  <li key={r.compte}><span className="font-mono">{r.compte}</span> · {t("controlesComptables.lignes", { count: r.lignes_non_lettrees })} · {formatDecimal(r.montant_non_lettre)}{r.plus_ancienne && ` · ${t("controlesComptables.depuis", { date: formatDate(r.plus_ancienne) })}`}{r.anomalies.length > 0 && <span className="text-red-700"> · {r.anomalies.join(" ; ")}</span>}</li>
                ))}
              </ul>
            ) : <p className="text-sm text-emerald-700">{t("controlesComptables.tousLettres")}</p>}
            {file.peut_travailler && <button type="button" className="btn-secondaire" onClick={() => void launch()}>{t("controlesComptables.lancer")}</button>}
            {data.analyses.length > 0 && (
              <ul className="text-sm">
                {data.analyses.map((a) => <li key={a.id}><Link className="text-marque-700 underline" to={`/missions/${file.engagement_id}/donnees/${a.id}`}>{a.nom}</Link> · {a.statut === "pret" ? t("ops.lignes", { count: a.nb_lignes ?? 0 }) : a.statut}</li>)}
              </ul>
            )}
          </>
        )}
      </section>
    </div>
  );
}
