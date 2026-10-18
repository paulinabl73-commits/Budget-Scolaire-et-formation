import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { AuditFile } from "../api/types";
import Alert from "../components/Alert";
import AdjustmentsPanel from "../components/revision/AdjustmentsPanel";
import AnalyticalPanel from "../components/revision/AnalyticalPanel";
import BankReconciliationsPanel from "../components/revision/BankReconciliationsPanel";
import ConfirmationsPanel from "../components/revision/ConfirmationsPanel";
import FinancialStatementsPanel from "../components/revision/FinancialStatementsPanel";
import ImportsPanel from "../components/revision/ImportsPanel";
import LeadSchedulesPanel from "../components/revision/LeadSchedulesPanel";
import MappingPanel from "../components/revision/MappingPanel";
import MaterialityPanel from "../components/revision/MaterialityPanel";
import type { Mapping } from "../components/revision/MappingPanel";
import RatiosPanel from "../components/revision/RatiosPanel";
import RiskMatrixPanel from "../components/revision/RiskMatrixPanel";
import StatementsPreview from "../components/revision/StatementsPreview";
import ThirdPartiesPanel from "../components/revision/ThirdPartiesPanel";
import UnadjustedPanel from "../components/revision/UnadjustedPanel";
import { formatDate } from "../lib/format";

const VIEWS = ["donnees", "affectation", "planification", "analytique", "ratios", "risques", "ajustements", "cycles", "etats", "tiers", "circularisation", "tresorerie"] as const;
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
  const [version, setVersion] = useState(0);
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
      {view === "ratios" && <RatiosPanel file={file} />}
      {view === "risques" && <RiskMatrixPanel file={file} />}
      {view === "ajustements" && (
        <>
          <AdjustmentsPanel file={file} onChange={() => setVersion((v) => v + 1)} />
          {file.seuil_signification && <UnadjustedPanel file={file} version={version} />}
        </>
      )}
      {view === "cycles" && <LeadSchedulesPanel file={file} />}
      {view === "tiers" && <ThirdPartiesPanel file={file} />}
      {view === "circularisation" && <ConfirmationsPanel file={file} />}
      {view === "tresorerie" && <BankReconciliationsPanel file={file} />}
      {view === "etats" && (unmapped > 0 ? <Alert kind="info">{t("affectation.bloque")}</Alert> : <FinancialStatementsPanel file={file} />)}
    </div>
  );
}
