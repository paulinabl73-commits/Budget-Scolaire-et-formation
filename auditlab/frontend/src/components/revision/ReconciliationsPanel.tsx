import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import BankReconciliationsPanel from "./BankReconciliationsPanel";

interface Aux { type: string; compte_collectif: string; nombre_tiers: number; total_auxiliaire: string; solde_collectif: string; ecart: string; rapproche: boolean; tiers: { code: string; libelle: string | null; solde: string }[] }

/** Rapprochements d'une clôture (RCO-10) : tiers / balances auxiliaires, banques / relevés. */
export default function ReconciliationsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<{ balance_generale: boolean; auxiliaires: Aux[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<{ balance_generale: boolean; auxiliaires: Aux[] }>(`/audit-files/${file.id}/reconciliations`).then(setData).catch((e: Error) => setError(e.message));
  }, [file.id]);
  return (
    <div className="space-y-4">
      {error && <Alert kind="erreur">{error}</Alert>}
      <section className="carte space-y-3" aria-labelledby="rap-aux">
        <h2 id="rap-aux" className="text-base font-semibold">{t("rapprochementsCloture.auxiliaires")}</h2>
        {data && data.auxiliaires.length === 0 && <p className="text-sm text-slate-600">{t("rapprochementsCloture.aucuneAuxiliaire")}</p>}
        {data?.auxiliaires.map((a) => (
          <details key={a.type} className="rounded border border-slate-200 p-2" open={!a.rapproche}>
            <summary className="cursor-pointer text-sm">
              <span className="font-medium">{t(`rapprochementsCloture.types.${a.type}`, { defaultValue: a.type })}</span> · {t("rapprochementsCloture.collectif", { compte: a.compte_collectif })} ·{" "}
              {formatDecimal(a.total_auxiliaire)} / {formatDecimal(a.solde_collectif)} ·{" "}
              {a.rapproche ? <span className="text-emerald-700">{t("rapprochementsCloture.rapproche")}</span> : <span className="font-medium text-red-700">{t("rapprochementsCloture.ecart", { montant: formatDecimal(a.ecart) })}</span>}
            </summary>
            <table className="mt-2 w-full text-left text-sm">
              <thead className="text-xs text-slate-600"><tr><th scope="col" className="py-1 pr-3">{t("rapprochementsCloture.tiers")}</th><th scope="col" className="py-1 pr-3 text-right">{t("rapprochementsCloture.solde")}</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {a.tiers.map((x) => <tr key={x.code}><th scope="row" className="py-1 pr-3 font-normal"><span className="font-mono">{x.code}</span> {x.libelle}</th><td className="py-1 pr-3 text-right font-mono">{formatDecimal(x.solde)}</td></tr>)}
              </tbody>
            </table>
          </details>
        ))}
      </section>
      <BankReconciliationsPanel file={file} />
    </div>
  );
}
