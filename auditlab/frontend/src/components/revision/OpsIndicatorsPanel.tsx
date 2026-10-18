import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";

interface FeesYear {
  exercice: number;
  frais_gestion: string;
  cotisations_emises: string;
  variation_creances: string;
  cotisations_encaissees: string;
  ratio: string | null;
  plafond: string | null;
  conforme: boolean | null;
}
export interface Indicators {
  frais_gestion: { postes_manquants: string[]; exercices: FeesYear[] };
  parametres_manquants: string[];
}

export function Verdict({ ok }: { ok: boolean | null }) {
  const { t } = useTranslation();
  if (ok === null) return <span className="text-slate-500">{t("indicateursOps.nonEvaluable")}</span>;
  return ok ? <span className="text-emerald-700">{t("indicateursOps.conforme")}</span> : <span className="font-medium text-red-700">{t("indicateursOps.depassement")}</span>;
}

/** Indicateurs des organismes de prévoyance sociale sur les soldes révisés (CIP-06, CIP-07). */
export default function OpsIndicatorsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Indicators | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Indicators>(`/audit-files/${file.id}/ops-indicators`).then(setData).catch((e: Error) => setError(e.message));
  }, [file.id]);
  if (error) return <Alert kind="info">{error}</Alert>;
  if (!data) return null;
  const fees = data.frais_gestion;
  const pct = (v: string | null) => (v === null ? "—" : `${formatDecimal(v)} %`);
  return (
    <div className="space-y-4">
      {data.parametres_manquants.length > 0 && <Alert kind="info">{t("indicateursOps.parametresManquants", { liste: data.parametres_manquants.join(", ") })}</Alert>}
      <section className="carte space-y-2" aria-labelledby="ops-frais">
        <h2 id="ops-frais" className="text-base font-semibold">{t("indicateursOps.frais.titre")}</h2>
        {fees.postes_manquants.length > 0 ? <p className="text-sm text-slate-600">{t("indicateursOps.postesManquants", { liste: fees.postes_manquants.join(", ") })}</p> : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-600">
              <tr>
                <th scope="col" className="py-1 pr-3">{t("indicateursOps.exercice")}</th>
                <th scope="col" className="py-1 pr-3 text-right">{t("indicateursOps.frais.frais")}</th>
                <th scope="col" className="py-1 pr-3 text-right">{t("indicateursOps.frais.emises")}</th>
                <th scope="col" className="py-1 pr-3 text-right">{t("indicateursOps.frais.variation")}</th>
                <th scope="col" className="py-1 pr-3 text-right">{t("indicateursOps.frais.encaissees")}</th>
                <th scope="col" className="py-1 pr-3 text-right">{t("indicateursOps.frais.ratio")}</th>
                <th scope="col" className="py-1 pr-3 text-right">{t("indicateursOps.plafond")}</th>
                <th scope="col" className="py-1 pr-3">{t("indicateursOps.verdict")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {fees.exercices.map((y) => (
                <tr key={y.exercice}>
                  <th scope="row" className="py-1 pr-3 font-normal">{y.exercice}</th>
                  <td className="py-1 pr-3 text-right font-mono">{formatDecimal(y.frais_gestion)}</td>
                  <td className="py-1 pr-3 text-right font-mono">{formatDecimal(y.cotisations_emises)}</td>
                  <td className="py-1 pr-3 text-right font-mono">{formatDecimal(y.variation_creances)}</td>
                  <td className="py-1 pr-3 text-right font-mono">{formatDecimal(y.cotisations_encaissees)}</td>
                  <td className="py-1 pr-3 text-right font-mono">{pct(y.ratio)}</td>
                  <td className="py-1 pr-3 text-right font-mono">{pct(y.plafond)}</td>
                  <td className="py-1 pr-3"><Verdict ok={y.conforme} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="text-xs text-slate-500">{t("indicateursOps.frais.note")}</p>
      </section>
    </div>
  );
}
