import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { MapEntity, RiskMap } from "../api/types";
import Alert from "../components/Alert";
import { cellLevel, LEVEL_CLASSES } from "../lib/risk";
import type { Level } from "../lib/risk";

const LEVELS: Level[] = ["faible", "modere", "eleve", "critique"];

function EntityList({ items }: { items: MapEntity[] }) {
  const { t } = useTranslation();
  return (
    <ul className="divide-y divide-slate-200 text-sm">
      {items.map((e) => (
        <li key={e.id} className="flex items-center justify-between py-2">
          <span>
            {e.nom}{" "}
            <span className="text-xs text-slate-500">{t(`univers.types.${e.type}`)}</span>
          </span>
          <span className="flex items-center gap-3">
            {e.score_risque !== null && (
              <span className="font-semibold">{e.score_risque.toLocaleString("fr-FR")}</span>
            )}
            <Link to={`/univers?entite=${e.id}`} className="text-marque-700 underline">
              {t("carte.ouvrir")}
            </Link>
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function RiskMapPage() {
  const { t } = useTranslation();
  const [map, setMap] = useState<RiskMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cell, setCell] = useState<{ impact: number; probabilite: number } | null>(null);

  useEffect(() => {
    api<RiskMap>("/risk/map")
      .then(setMap)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!map) return <p>{t("commun.chargement")}</p>;

  const scale = Array.from({ length: map.echelle }, (_, i) => i + 1);
  const at = (i: number, p: number) =>
    map.cellules.find((c) => c.impact === i && c.probabilite === p)?.entites ?? [];
  const selected = cell ? at(cell.impact, cell.probabilite) : [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("carte.titre")}</h1>
        <p className="text-slate-600">{t("carte.intro")}</p>
      </header>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="carte">
          <div className="flex">
            <div className="flex items-center">
              <span className="-rotate-90 whitespace-nowrap text-sm font-medium text-slate-700">
                {t("carte.impact")}
              </span>
            </div>
            <div className="flex-1">
              <div className="grid grid-cols-[2rem_repeat(5,minmax(0,1fr))] gap-1">
                {[...scale].reverse().map((i) => (
                  <div key={i} className="contents">
                    <div className="flex items-center justify-center text-sm text-slate-600">{i}</div>
                    {scale.map((p) => {
                      const items = at(i, p);
                      const active = cell?.impact === i && cell?.probabilite === p;
                      return (
                        <button
                          key={p}
                          type="button"
                          aria-pressed={active}
                          aria-label={t("carte.case", { impact: i, probabilite: p, count: items.length })}
                          onClick={() => setCell({ impact: i, probabilite: p })}
                          className={`flex aspect-square items-center justify-center rounded text-lg font-semibold ${
                            LEVEL_CLASSES[cellLevel(i, p)]
                          } ${active ? "ring-4 ring-marque-900" : "hover:ring-2 hover:ring-marque-600"}`}
                        >
                          {items.length > 0 ? items.length : ""}
                        </button>
                      );
                    })}
                  </div>
                ))}
                <div />
                {scale.map((p) => (
                  <div key={p} className="text-center text-sm text-slate-600">{p}</div>
                ))}
              </div>
              <p className="mt-2 text-center text-sm font-medium text-slate-700">
                {t("carte.probabilite")}
              </p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs" aria-label={t("carte.legende")}>
            {LEVELS.map((l) => (
              <span key={l} className={`rounded px-2 py-1 ${LEVEL_CLASSES[l]}`}>
                {t(`carte.niveaux.${l}`)}
              </span>
            ))}
          </div>
        </section>
        <section className="carte space-y-4" aria-live="polite">
          {cell ? (
            <>
              <h2 className="text-lg font-semibold">{t("carte.selection", cell)}</h2>
              {selected.length ? (
                <EntityList items={selected} />
              ) : (
                <p className="text-sm text-slate-600">{t("carte.aucune")}</p>
              )}
            </>
          ) : (
            <p className="text-sm text-slate-600">{t("carte.choisir")}</p>
          )}
          {map.non_evaluees.length > 0 && (
            <details className="border-t border-slate-200 pt-3">
              <summary className="cursor-pointer text-sm font-medium">
                {t("carte.nonEvaluees", { count: map.non_evaluees.length })}
              </summary>
              <EntityList items={map.non_evaluees} />
            </details>
          )}
        </section>
      </div>
    </div>
  );
}
