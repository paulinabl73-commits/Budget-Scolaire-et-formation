import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { AuditFile } from "../api/types";
import Alert from "../components/Alert";
import { formatDate } from "../lib/format";

/** Dossier de révision (Module 5) : balances, affectation, seuils, revue analytique. */
export default function AuditFilePage() {
  const { t } = useTranslation();
  const { id, fid } = useParams();
  const [file, setFile] = useState<AuditFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => setFile(await api<AuditFile>(`/audit-files/${fid}`)), [fid]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!file) return <p>{t("commun.chargement")}</p>;
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
    </div>
  );
}
