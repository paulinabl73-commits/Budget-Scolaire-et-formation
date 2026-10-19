import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, upload } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";

interface Month { mois: string; comptable: string; declare: string | null; ecart: string | null; concordant: boolean }
interface Turnover { mois: Month[]; total_comptable: string; total_declare: string; ecart_total: string; tolerance: string; mois_sans_declaration: string[] }

export function MonthlyTable({ rows, label }: { rows: Month[]; label: string }) {
  const { t } = useTranslation();
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-xs text-slate-600"><tr><th scope="col" className="py-1 pr-3">{t("fiscal.mois")}</th><th scope="col" className="py-1 pr-3 text-right">{label} {t("fiscal.comptable")}</th><th scope="col" className="py-1 pr-3 text-right">{t("fiscal.declare")}</th><th scope="col" className="py-1 pr-3 text-right">{t("fiscal.ecart")}</th></tr></thead>
      <tbody className="divide-y divide-slate-100">
        {rows.map((m) => (
          <tr key={m.mois} className={m.declare !== null && !m.concordant ? "bg-red-50" : ""}>
            <th scope="row" className="py-1 pr-3 font-normal">{m.mois}</th>
            <td className="py-1 pr-3 text-right font-mono">{formatDecimal(m.comptable)}</td>
            <td className="py-1 pr-3 text-right font-mono">{m.declare === null ? t("fiscal.nonDeclare") : formatDecimal(m.declare)}</td>
            <td className="py-1 pr-3 text-right font-mono">{m.ecart === null ? "—" : formatDecimal(m.ecart)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Révision fiscale : chiffre d'affaires comptable et déclaré en TVA, mois par mois (RCO-18). */
export default function TaxReviewPanel({ file, onImported }: { file: AuditFile; onImported?: () => void }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Turnover | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Turnover>(`/audit-files/${file.id}/turnover-reconciliation`).then(setData), [file.id]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const send = async (f: File | undefined) => {
    if (!f) return;
    setError(null);
    try {
      await upload(`/audit-files/${file.id}/tax-returns`, f);
      await load();
      onImported?.();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="carte space-y-3" aria-labelledby="ca-titre">
      <h2 id="ca-titre" className="text-base font-semibold">{t("fiscal.caTitre")}</h2>
      <p className="text-sm text-slate-600">{t("fiscal.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      {file.peut_travailler && (
        <label className="btn-secondaire cursor-pointer">{t("fiscal.importer")}
          <input type="file" accept=".csv,.xlsx,.xls" className="sr-only" onChange={(e) => void send(e.target.files?.[0])} />
        </label>
      )}
      {data && (
        <>
          <MonthlyTable rows={data.mois} label={t("fiscal.ca")} />
          <p className="text-sm">{t("fiscal.totalCa", { comptable: formatDecimal(data.total_comptable), declare: formatDecimal(data.total_declare), ecart: formatDecimal(data.ecart_total), tolerance: formatDecimal(data.tolerance) })}</p>
        </>
      )}
    </section>
  );
}
