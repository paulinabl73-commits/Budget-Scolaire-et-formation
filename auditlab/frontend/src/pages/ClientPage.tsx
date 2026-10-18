import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, post } from "../api/client";
import type { PortfolioClient } from "../api/portfolio";
import Alert from "../components/Alert";
import DeadlinesPanel from "../components/portfolio/DeadlinesPanel";

/** Dossier client permanent et ses clôtures (Module 6). */
export default function ClientPage() {
  const { t } = useTranslation();
  const { cid } = useParams();
  const [c, setC] = useState<PortfolioClient | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exercice, setExercice] = useState(String(new Date().getFullYear()));
  const load = useCallback(() => api<PortfolioClient>(`/clients/${cid}`).then(setC), [cid]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  if (!c) return error ? <Alert kind="erreur">{error}</Alert> : <p>{t("commun.chargement")}</p>;
  const open = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await post(`/clients/${c.id}/closings`, { exercice: Number(exercice) });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const facts: [string, string | null][] = [
    ["forme", t(`portefeuille.formes.${c.forme_juridique}`)],
    ["regime", t(`portefeuille.regimes.${c.regime_fiscal}`)],
    ["referentiel", c.referentiel],
    ["pays", `${c.pays} · ${c.devise}`],
    ["cloture", c.date_cloture],
    ["taille", t(`portefeuille.tailles.${c.taille}`)],
    ["nif", c.identifiant_fiscal],
    ["rccm", c.rccm],
    ["expert", c.expert_nom],
    ["collaborateur", c.collaborateur_nom],
    ["superviseur", c.superviseur_nom],
    ["contact", c.contact_nom],
  ];
  return (
    <div className="space-y-4">
      <Link to="/portefeuille" className="text-sm text-marque-700 underline">← {t("portefeuille.retour")}</Link>
      <h1 className="text-2xl font-semibold">{c.raison_sociale}</h1>
      {error && <Alert kind="erreur">{error}</Alert>}
      <section className="carte" aria-label={t("portefeuille.raison")}>
        <dl className="grid gap-x-6 gap-y-2 text-sm md:grid-cols-3">
          {facts.map(([k, v]) => (
            <div key={k}><dt className="text-slate-600">{t(`portefeuille.${k}`)}</dt><dd>{v || "—"}</dd></div>
          ))}
        </dl>
      </section>
      <DeadlinesPanel clientId={c.id} canWork />
      <section className="carte space-y-3" aria-labelledby="cl-clotures">
        <h2 id="cl-clotures" className="text-base font-semibold">{t("portefeuille.clotures")}</h2>
        <ul className="divide-y divide-slate-100 text-sm">
          {c.clotures.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-3 py-2">
              <span className="font-medium">{t("portefeuille.exercice")} {x.exercice}</span>
              <span>{t(`portefeuille.etapes.${x.etape}`)}</span>
              <Link className="text-marque-700 underline" to={`/missions/${x.engagement_id}/revision/${x.audit_file_id}`}>{t("portefeuille.dossierRevision")}</Link>
              <Link className="text-marque-700 underline" to={`/missions/${x.engagement_id}`}>{t("portefeuille.mission")}</Link>
            </li>
          ))}
        </ul>
        {c.peut_gerer && c.actif && (
          <form onSubmit={open} className="flex items-end gap-2">
            <div>
              <label htmlFor="cl-exercice" className="etiquette">{t("portefeuille.exercice")}</label>
              <input id="cl-exercice" type="number" className="champ" required value={exercice} onChange={(e) => setExercice(e.target.value)} />
            </div>
            <button type="submit" className="btn-primaire">{t("portefeuille.ouvrir")}</button>
          </form>
        )}
      </section>
    </div>
  );
}
