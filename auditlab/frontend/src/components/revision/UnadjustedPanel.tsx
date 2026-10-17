import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Table {
  seuils: { signification: string; planification: string; insignifiant: string };
  anomalies: { numero: number; libelle: string; type: string; statut: string; effet_resultat: string; montant: string; insignifiant: boolean; individuellement_significatif: boolean }[];
  cumul_resultat: string;
  cumul_reclassements: string;
  conclusion: "non_significatif" | "vigilance" | "significatif";
}
const KIND = { non_significatif: "succes", vigilance: "info", significatif: "erreur" } as const;

/** Anomalies non corrigées cumulées et comparées au seuil de signification (REV-22). */
export default function UnadjustedPanel({ file, version }: { file: AuditFile; version: number }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Table | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Table>(`/audit-files/${file.id}/unadjusted`).then((d) => { setData(d); setError(null); }).catch((e: Error) => setError(e.message));
  }, [file.id, version]);
  const n = (v: string) => formatNombre(Number(v));
  return (
    <section className="carte space-y-3" aria-labelledby="anc-titre">
      <h2 id="anc-titre" className="text-base font-semibold">{t("nonCorrigees.titre")}</h2>
      {error && <Alert kind="info">{error}</Alert>}
      {data && (
        <>
          <Alert kind={KIND[data.conclusion]}>
            {t(`nonCorrigees.conclusions.${data.conclusion}`, { cumul: n(data.cumul_resultat), seuil: n(data.seuils.signification), plan: n(data.seuils.planification) })}
          </Alert>
          {data.anomalies.length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-xs text-slate-600"><tr>{["ecriture", "nature", "statut", "resultat", "montant", "appreciation"].map((k) => <th key={k} scope="col" className="py-1 pr-3 text-left">{t(`nonCorrigees.col.${k}`)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.anomalies.map((a) => (
                  <tr key={a.numero} className={a.insignifiant ? "text-slate-400" : ""}>
                    <td className="py-1 pr-3">AJE {a.numero} · {a.libelle}</td>
                    <td className="py-1 pr-3">{t(`ajustements.types.${a.type}`)}</td>
                    <td className="py-1 pr-3">{t(`ajustements.statuts.${a.statut}`)}</td>
                    <td className="py-1 pr-3 text-right font-mono">{n(a.effet_resultat)}</td>
                    <td className="py-1 pr-3 text-right font-mono">{n(a.montant)}</td>
                    <td className="py-1 text-xs">{a.individuellement_significatif ? t("nonCorrigees.significatif") : a.insignifiant ? t("nonCorrigees.insignifiant") : ""}</td>
                  </tr>
                ))}
                <tr className="font-semibold"><td className="py-1 pr-3" colSpan={3}>{t("nonCorrigees.cumul")}</td><td className="py-1 pr-3 text-right font-mono">{n(data.cumul_resultat)}</td><td className="py-1 pr-3 text-right font-mono">{n(data.cumul_reclassements)}</td><td /></tr>
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
