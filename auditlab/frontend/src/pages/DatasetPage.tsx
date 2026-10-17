import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Dataset } from "../api/types";
import Alert from "../components/Alert";
import CalculatedFields from "../components/data/CalculatedFields";
import ControlSheet from "../components/data/ControlSheet";
import { useAuth } from "../auth/AuthContext";
import { can } from "../lib/permissions";

/** Fiche d'une table : empreinte et totaux (DAT-04), grille (DAT-07), statistiques (DAT-08). */
export default function DatasetPage() {
  const { t } = useTranslation();
  const { id, dsId } = useParams();
  const [ds, setDs] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();
  const load = useCallback(async () => setDs(await api<Dataset>(`/datasets/${dsId}`)), [dsId]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!ds) return <p>{t("commun.chargement")}</p>;
  return (
    <div className="space-y-4">
      <Link to={`/missions/${id}?onglet=donnees`} className="text-sm text-marque-700 underline">{t("table.retour")}</Link>
      <header>
        <h1 className="text-2xl font-semibold">{ds.nom}</h1>
        {ds.description && <p className="text-slate-600">{ds.description}</p>}
      </header>
      {ds.kind !== "vue" && <ControlSheet ds={ds} />}
      <CalculatedFields ds={ds} canEdit={can(user?.permissions, "data:analyze")} onChanged={setDs} />
    </div>
  );
}
