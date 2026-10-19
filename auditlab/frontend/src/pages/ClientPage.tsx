import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, post, put } from "../api/client";
import type { PortfolioClient } from "../api/portfolio";
import Alert from "../components/Alert";
import ClosingDocumentsPanel from "../components/portfolio/ClosingDocumentsPanel";
import ClosingIndicatorsPanel from "../components/portfolio/ClosingIndicatorsPanel";
import ClosingReviewPanel from "../components/portfolio/ClosingReviewPanel";
import ChecklistPanel from "../components/portfolio/ChecklistPanel";
import DeadlinesPanel from "../components/portfolio/DeadlinesPanel";
import PermanentPanel from "../components/portfolio/PermanentPanel";
import PiecesPanel from "../components/portfolio/PiecesPanel";
import { STAGES } from "../components/portfolio/PortfolioDashboard";

/** Dossier client permanent et ses clôtures (Module 6). */
export default function ClientPage() {
  const { t } = useTranslation();
  const { cid } = useParams();
  const [c, setC] = useState<PortfolioClient | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState<
    { libelle: string; date_validite: string }[]
  >([]);
  const [exercice, setExercice] = useState(String(new Date().getFullYear()));
  const load = useCallback(
    () => api<PortfolioClient>(`/clients/${cid}`).then(setC),
    [cid],
  );
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  if (!c)
    return error ? (
      <Alert kind="erreur">{error}</Alert>
    ) : (
      <p>{t("commun.chargement")}</p>
    );
  const open = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const r = await post<{
        documents_expires: { libelle: string; date_validite: string }[];
      }>(`/clients/${c.id}/closings`, { exercice: Number(exercice) });
      setStale(r.documents_expires);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const stage = async (id: string, etape: string) => {
    setError(null);
    try {
      await put(`/closings/${id}/stage`, { etape });
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
      <Link to="/portefeuille" className="text-sm text-marque-700 underline">
        ← {t("portefeuille.retour")}
      </Link>
      <h1 className="text-2xl font-semibold">{c.raison_sociale}</h1>
      {error && <Alert kind="erreur">{error}</Alert>}
      {stale.length > 0 && (
        <Alert kind="info">
          {t("permanent.expiresOuverture", {
            liste: stale.map((d) => d.libelle).join(", "),
          })}
        </Alert>
      )}
      <section className="carte" aria-label={t("portefeuille.raison")}>
        <dl className="grid gap-x-6 gap-y-2 text-sm md:grid-cols-3">
          {facts.map(([k, v]) => (
            <div key={k}>
              <dt className="text-slate-600">{t(`portefeuille.${k}`)}</dt>
              <dd>{v || "—"}</dd>
            </div>
          ))}
        </dl>
      </section>
      {c.clotures[0] && (
        <ClosingReviewPanel
          key={`rv-${c.clotures[0].id}`}
          closingId={c.clotures[0].id}
          onChange={() => void load()}
        />
      )}
      {c.clotures[0] && (
        <ClosingDocumentsPanel
          key={`doc-${c.clotures[0].id}-${Object.keys(c.clotures[0].revues ?? {}).join()}`}
          closingId={c.clotures[0].id}
          exercice={c.clotures[0].exercice}
        />
      )}
      {c.clotures[0] && (
        <ClosingIndicatorsPanel
          key={`ind-${c.clotures[0].id}`}
          closingId={c.clotures[0].id}
        />
      )}
      {c.clotures[0] && (
        <ChecklistPanel
          key={`ck-${c.clotures[0].id}`}
          closingId={c.clotures[0].id}
        />
      )}
      {c.clotures[0] && (
        <PiecesPanel
          key={c.clotures[0].id}
          closingId={c.clotures[0].id}
          exercice={c.clotures[0].exercice}
        />
      )}
      <DeadlinesPanel clientId={c.id} canWork />
      <PermanentPanel clientId={c.id} />
      <section className="carte space-y-3" aria-labelledby="cl-clotures">
        <h2 id="cl-clotures" className="text-base font-semibold">
          {t("portefeuille.clotures")}
        </h2>
        <ul className="divide-y divide-slate-100 text-sm">
          {c.clotures.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-3 py-2">
              <span className="font-medium">
                {t("portefeuille.exercice")} {x.exercice}
              </span>
              <span>{t(`portefeuille.etapes.${x.etape}`)}</span>
              {STAGES.indexOf(x.etape as (typeof STAGES)[number]) > 0 && (
                <button
                  type="button"
                  className="underline"
                  onClick={() =>
                    void stage(
                      x.id,
                      STAGES[
                        STAGES.indexOf(x.etape as (typeof STAGES)[number]) - 1
                      ],
                    )
                  }
                >
                  {t("tableauPortefeuille.revenirA", {
                    etape: t(
                      `portefeuille.etapes.${STAGES[STAGES.indexOf(x.etape as (typeof STAGES)[number]) - 1]}`,
                    ),
                  })}
                </button>
              )}
              {x.etape !== "termine" && (
                <button
                  type="button"
                  className="btn-secondaire"
                  onClick={() =>
                    void stage(
                      x.id,
                      STAGES[
                        STAGES.indexOf(x.etape as (typeof STAGES)[number]) + 1
                      ],
                    )
                  }
                >
                  {t("tableauPortefeuille.passerA", {
                    etape: t(
                      `portefeuille.etapes.${STAGES[STAGES.indexOf(x.etape as (typeof STAGES)[number]) + 1]}`,
                    ),
                  })}
                </button>
              )}
              <Link
                className="text-marque-700 underline"
                to={`/missions/${x.engagement_id}/revision/${x.audit_file_id}`}
              >
                {t("portefeuille.dossierRevision")}
              </Link>
              <Link
                className="text-marque-700 underline"
                to={`/missions/${x.engagement_id}`}
              >
                {t("portefeuille.mission")}
              </Link>
            </li>
          ))}
        </ul>
        {c.peut_gerer && c.actif && (
          <form onSubmit={open} className="flex items-end gap-2">
            <div>
              <label htmlFor="cl-exercice" className="etiquette">
                {t("portefeuille.exercice")}
              </label>
              <input
                id="cl-exercice"
                type="number"
                className="champ"
                required
                value={exercice}
                onChange={(e) => setExercice(e.target.value)}
              />
            </div>
            <button type="submit" className="btn-primaire">
              {t("portefeuille.ouvrir")}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
