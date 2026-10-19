import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import { MonthlyTable } from "./TaxReviewPanel";

type Month = { mois: string; comptable: string; declare: string | null; ecart: string | null; concordant: boolean };
interface Vat {
  collectee: Month[];
  deductible: Month[];
  tva_theorique: string | null;
  taux_tva: string | null;
  tva_collectee_totale: string;
  ecart_theorique: string | null;
  credit_tva: { solde_comptable: string; credit_declare: string | null; mois_declaration: string | null; ecart: string | null; justifie: boolean };
}

/** TVA collectée et déductible comptabilisée et déclarée, crédit de TVA (RCO-19). */
export default function VatPanel({ file, version }: { file: AuditFile; version: number }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Vat | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Vat>(`/audit-files/${file.id}/vat-reconciliation`).then(setData).catch((e: Error) => setError(e.message));
  }, [file.id, version]);
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const c = data.credit_tva;
  return (
    <section className="carte space-y-3" aria-labelledby="tva-titre">
      <h2 id="tva-titre" className="text-base font-semibold">{t("fiscal.tvaTitre")}</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <div><h3 className="text-sm font-semibold">{t("fiscal.collectee")}</h3><MonthlyTable rows={data.collectee} label={t("fiscal.tva")} /></div>
        <div><h3 className="text-sm font-semibold">{t("fiscal.deductible")}</h3><MonthlyTable rows={data.deductible} label={t("fiscal.tva")} /></div>
      </div>
      <p className="text-sm">{data.tva_theorique === null ? t("fiscal.tauxManquant") : t("fiscal.theorique", { taux: data.taux_tva, theorique: formatDecimal(data.tva_theorique), collectee: formatDecimal(data.tva_collectee_totale), ecart: formatDecimal(data.ecart_theorique ?? "0") })}</p>
      <p className={`text-sm ${c.justifie ? "text-emerald-700" : "text-red-700"}`}>
        {c.credit_declare === null ? t("fiscal.creditSansDeclaration", { solde: formatDecimal(c.solde_comptable) })
          : t("fiscal.credit", { solde: formatDecimal(c.solde_comptable), declare: formatDecimal(c.credit_declare), mois: c.mois_declaration, ecart: formatDecimal(c.ecart ?? "0") })}
      </p>
    </section>
  );
}
