import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Dataset } from "../../api/types";
import { formatDate, formatNombre, formatTaille } from "../../lib/format";
import Alert from "../Alert";

/** Empreinte et totaux de contrôle d'une table (DAT-04). */
export default function ControlSheet({ ds }: { ds: Dataset }) {
  const { t } = useTranslation();
  const [check, setCheck] = useState<{ source_intacte: boolean | null; table_intacte: boolean | null } | null>(null);
  const totals = Object.entries(ds.totaux_controle);
  const warnings = Object.entries((ds.options.avertissements as Record<string, number>) ?? {});
  const ok = check && check.source_intacte !== false && check.table_intacte !== false;

  return (
    <section className="carte space-y-3" aria-labelledby="fiche-titre">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="text-sm">
          <h2 id="fiche-titre" className="text-base font-semibold">{t("table.empreinte")}</h2>
          <p>
            {t("table.lignes", { n: formatNombre(ds.nb_lignes ?? 0) })} · {t("table.colonnes", { n: ds.nb_colonnes ?? 0 })}
            {ds.lecture_seule && ` · ${t("table.lectureSeule")}`}
            {ds.duree_ms !== null && ` · ${t("table.duree", { s: formatNombre(Math.round(ds.duree_ms / 100) / 10) })}`}
          </p>
          {ds.source_nom && (
            <p className="text-slate-600">
              {t("table.source")} : {ds.source_nom}{ds.source_taille ? ` (${formatTaille(ds.source_taille)})` : ""}
            </p>
          )}
          {ds.source_sha256 && <p className="font-mono text-xs text-slate-600">{t("table.sha")} : {ds.source_sha256}</p>}
          {ds.parquet_sha256 && <p className="font-mono text-xs text-slate-600">{t("table.shaTable")} : {ds.parquet_sha256}</p>}
        </div>
        <button type="button" className="btn-secondaire"
          onClick={async () => setCheck(await api(`/datasets/${ds.id}/integrity`))}>
          {t("table.verifier")}
        </button>
      </div>
      {check && <Alert kind={ok ? "succes" : "erreur"}>{ok ? t("table.intacte") : t("table.alteree")}</Alert>}
      {warnings.length > 0 && (
        <Alert kind="erreur">
          {t("table.avertissements")} : {warnings.map(([c, n]) => `${c} (${n})`).join(", ")}
        </Alert>
      )}
      {totals.length > 0 && (
        <table className="w-full text-left text-sm">
          <caption className="mb-1 text-left text-xs font-semibold text-slate-700">{t("table.totaux")}</caption>
          <thead className="text-xs text-slate-600">
            <tr>
              <th scope="col">{t("table.colonne")}</th>
              <th scope="col" className="text-right">{t("table.somme")}</th>
              <th scope="col" className="text-right">{t("table.valeurs")}</th>
              <th scope="col" className="text-right">{t("table.min")}</th>
              <th scope="col" className="text-right">{t("table.max")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {totals.map(([col, v]) => (
              <tr key={col}>
                <td className="py-1">{col}</td>
                <td className="text-right font-mono">{v.somme !== undefined ? formatNombre(Number(v.somme)) : ""}</td>
                <td className="text-right">{v.valeurs !== undefined ? formatNombre(v.valeurs) : ""}</td>
                <td className="text-right">{v.min ? formatDate(v.min) : ""}</td>
                <td className="text-right">{v.max ? formatDate(v.max) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
