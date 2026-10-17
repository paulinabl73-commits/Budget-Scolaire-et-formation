import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Dataset } from "../api/types";
import Alert from "../components/Alert";
import AnalysisPanel from "../components/data/AnalysisPanel";
import AnalysisResult from "../components/data/AnalysisResult";
import CalculatedFields from "../components/data/CalculatedFields";
import ControlSheet from "../components/data/ControlSheet";
import DataGrid from "../components/data/DataGrid";
import FieldStats from "../components/data/FieldStats";
import LineageGraph from "../components/data/LineageGraph";
import MusEvaluation from "../components/data/MusEvaluation";
import type { GridQuery } from "../components/data/FieldStats";
import { useAuth } from "../auth/AuthContext";
import { can } from "../lib/permissions";

/** Fiche d'une table : empreinte et totaux (DAT-04), grille (DAT-07), statistiques (DAT-08). */
export default function DatasetPage() {
  const { t } = useTranslation();
  const { id, dsId } = useParams();
  const [ds, setDs] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();
  const [column, setColumn] = useState<string | null>(null);
  const [query, setQuery] = useState<GridQuery>({ filtres: {}, recherche: null });
  const onQuery = useCallback((q: GridQuery) => {
    setQuery((old) => (JSON.stringify(old) === JSON.stringify(q) ? old : q));
  }, []);
  const load = useCallback(async () => {
    setColumn(null);
    setQuery({ filtres: {}, recherche: null });
    setDs(await api<Dataset>(`/datasets/${dsId}`));
  }, [dsId]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  // Analyse ou import en tâche de fond : relecture jusqu'à la fin.
  useEffect(() => {
    if (ds?.statut !== "en_cours") return;
    const timer = setTimeout(() => {
      api<Dataset>(`/datasets/${ds.id}`).then(setDs).catch(() => undefined);
    }, 1500);
    return () => clearTimeout(timer);
  }, [ds]);

  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!ds) return <p>{t("commun.chargement")}</p>;
  return (
    <div className="space-y-4">
      <Link to={`/missions/${id}?onglet=donnees`} className="text-sm text-marque-700 underline">{t("table.retour")}</Link>
      <header>
        <h1 className="text-2xl font-semibold">{ds.nom}</h1>
        {ds.description && <p className="text-slate-600">{ds.description}</p>}
      </header>
      {ds.kind === "analyse" && <AnalysisResult ds={ds} />}
      {ds.operation === "echantillon" && ds.statut === "pret" && (ds.definition.parametres as Record<string, unknown>)?.methode === "mus" && (
        <MusEvaluation ds={ds} canEdit={can(user?.permissions, "data:analyze")} />
      )}
      {ds.statut === "en_cours" && <Alert kind="succes">{t("analyses.enCours")}</Alert>}
      {ds.statut === "erreur" && <Alert kind="erreur">{ds.erreur}</Alert>}
      {ds.kind !== "vue" && ds.statut === "pret" && <ControlSheet ds={ds} />}
      {ds.statut === "pret" && <LineageGraph key={`l-${ds.id}`} ds={ds} />}
      {ds.statut === "pret" && <DataGrid key={ds.id} ds={ds} onColumnFocus={setColumn} onQuery={onQuery} />}
      {ds.statut === "pret" && ds.schema.length > 0 && (
        <FieldStats ds={ds} column={column ?? ds.schema[0].nom} query={query} onColumn={setColumn} />
      )}
      {ds.statut === "pret" && can(user?.permissions, "data:analyze") && <AnalysisPanel key={`a-${ds.id}`} ds={ds} />}
      {ds.statut === "pret" && <CalculatedFields ds={ds} canEdit={can(user?.permissions, "data:analyze")} onChanged={setDs} />}
    </div>
  );
}
