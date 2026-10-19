import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, upload } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import { MonthlyTable } from "./TaxReviewPanel";

type Month = { mois: string; comptable: string; declare: string | null; ecart: string | null; concordant: boolean };
interface Theory { taux: string | null; theorique: string | null; comptabilise: string; ecart: string | null }
interface Payroll { masse_salariale: Month[]; cotisations: Month[]; impots_salaires: Month[]; masse_salariale_totale: string; theorique: Record<string, Theory> }
const PARTS = ["masse_salariale", "cotisations", "impots_salaires"] as const;

/** Salaires comptabilisés et déclarations sociales et fiscales (RCO-21). */
export default function PayrollPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Payroll | null>(null);
  const [part, setPart] = useState<(typeof PARTS)[number]>("masse_salariale");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Payroll>(`/audit-files/${file.id}/payroll-reconciliation`).then(setData), [file.id]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const send = async (f: File | undefined) => {
    if (!f) return;
    setError(null);
    try {
      await upload(`/audit-files/${file.id}/payroll-returns`, f);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="carte space-y-3" aria-labelledby="pa-titre">
      <h2 id="pa-titre" className="text-base font-semibold">{t("salaires.titre")}</h2>
      <p className="text-sm text-slate-600">{t("salaires.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      {file.peut_travailler && (
        <label className="btn-secondaire cursor-pointer">{t("salaires.importer")}
          <input type="file" accept=".csv,.xlsx,.xls" className="sr-only" onChange={(e) => void send(e.target.files?.[0])} />
        </label>
      )}
      {data && (
        <>
          <div role="tablist" className="flex gap-2 text-sm">
            {PARTS.map((p) => <button key={p} type="button" role="tab" aria-selected={p === part} className={p === part ? "font-semibold underline" : "underline"} onClick={() => setPart(p)}>{t(`salaires.parts.${p}`)}</button>)}
          </div>
          <MonthlyTable rows={data[part]} label={t(`salaires.parts.${part}`)} />
          {(["cotisations", "impots_salaires"] as const).map((k) => {
            const th = data.theorique[k];
            return <p key={k} className="text-sm">{th.theorique === null ? t("salaires.tauxManquant", { part: t(`salaires.parts.${k}`) }) : t("salaires.theorique", { part: t(`salaires.parts.${k}`), taux: th.taux, theorique: formatDecimal(th.theorique), comptabilise: formatDecimal(th.comptabilise), ecart: formatDecimal(th.ecart ?? "0") })}</p>;
          })}
        </>
      )}
    </section>
  );
}
