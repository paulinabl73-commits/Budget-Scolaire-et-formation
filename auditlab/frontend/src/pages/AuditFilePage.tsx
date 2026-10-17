import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { AuditFile } from "../api/types";
import Alert from "../components/Alert";
import AnalyticalPanel from "../components/revision/AnalyticalPanel";
import ImportsPanel from "../components/revision/ImportsPanel";
import MappingPanel from "../components/revision/MappingPanel";
import MaterialityPanel from "../components/revision/MaterialityPanel";
import type { Mapping } from "../components/revision/MappingPanel";
import StatementsPreview from "../components/revision/StatementsPreview";
import { formatDate } from "../lib/format";

const VIEWS = ["donnees", "affectation", "planification", "analytique"] as const;
type View = (typeof VIEWS)[number];

/** Dossier de révision (Module 5) : balances, affectation, seuils, revue analytique. */
export default function AuditFilePage() {
  const { t } = useTranslation();
  const { id, fid } = useParams();
  const [params, setParams] = useSearchParams();
  const view: View = (VIEWS as readonly string[]).includes(params.get("vue") ?? "") ? (params.get("vue") as View) : "donnees";
  const [file, setFile] = useState<AuditFile | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setFile(await api<AuditFile>(`/audit-files/${fid}`));
    setMapping(await api<Mapping>(`/audit-files/${fid}/mapping`));
  }, [fid]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!file || !mapping) return <p>{t("commun.chargement")}</p>;
  const unmapped = mapping.non_affectes.length;
  return (
    <div className="space-y-4">
      <Link to={`/missions/${id}?onglet=revision`} className="text-sm text-marque-700 underline">{t("revision.retour")}</Link>
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{t("revision.titreDossier", { entite: file.entite, exercice: file.exercice })}</h1>
        <p className="text-sm text-slate-600">
          {formatDate(file.date_debut)} – {formatDate(file.date_fin)} · {file.referentiel}
          {file.referentiel_ifrs && ` · ${t("revision.restitution")} ${file.referentiel_ifrs}`} · {file.devise}
          {file.cadre_normatif && ` · ${file.cadre_normatif}`}
          {file.precedent_exercice && ` · ${t("revision.precedent", { exercice: file.precedent_exercice })}`}
        </p>
      </header>
      {/* REV-10 : liste des comptes non affectés signalée en permanence. */}
      {mapping.comptes.length > 0 && (
        <div role="status" className={`flex flex-wrap items-center justify-between gap-2 rounded border px-3 py-2 text-sm ${unmapped ? "border-red-300 bg-red-50 text-red-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
          <span>
            {unmapped ? t("affectation.bandeau", { count: unmapped }) : t("affectation.bandeauOk")}
            {unmapped > 0 && <span className="ml-1 font-mono">{mapping.non_affectes.slice(0, 10).join(", ")}{unmapped > 10 ? "…" : ""}</span>}
          </span>
          {unmapped > 0 && view !== "affectation" && (
            <button type="button" className="underline" onClick={() => setParams({ vue: "affectation" })}>{t("affectation.voir")}</button>
          )}
        </div>
      )}
      <nav aria-label={t("dossier.navigation")} className="flex flex-wrap gap-1 border-b border-slate-200">
        {VIEWS.map((k) => (
          <button key={k} type="button" aria-current={k === view ? "page" : undefined} onClick={() => setParams({ vue: k })}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${k === view ? "border-marque-600 text-marque-700" : "border-transparent text-slate-600 hover:text-slate-900"}`}>
            {t(`dossier.vues.${k}`)}
          </button>
        ))}
      </nav>
      {view === "donnees" && <ImportsPanel file={file} onChange={() => void load()} />}
      {view === "affectation" && (
        <>
          <MappingPanel file={file} mapping={mapping} onChange={setMapping} />
          <StatementsPreview file={file} blocked={unmapped > 0} />
        </>
      )}
      {view === "planification" && <MaterialityPanel file={file} onChange={() => void load()} />}
      {view === "analytique" && <AnalyticalPanel file={file} />}
    </div>
  );
}
