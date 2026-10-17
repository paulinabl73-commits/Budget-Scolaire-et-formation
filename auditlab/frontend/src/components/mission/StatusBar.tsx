import { useState } from "react";
import { useTranslation } from "react-i18next";

import { post } from "../../api/client";
import type { Engagement, Transition } from "../../api/types";
import { STATUSES } from "../../lib/mission";
import Alert from "../Alert";

interface Props {
  mission: Engagement;
  onChange: (m: Engagement) => void;
}

/** Frise du cycle de vie (AUD-07) et boutons de passage, avec le motif d'un éventuel blocage. */
export default function StatusBar({ mission, onChange }: Props) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const current = STATUSES.indexOf(mission.statut);

  const go = async (tr: Transition) => {
    if (tr.statut === "cloturee" && !window.confirm(t("missions.confirmerCloture"))) return;
    setError(null);
    try {
      onChange(await post<Engagement>(`/engagements/${mission.id}/status`, { statut: tr.statut }));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section aria-label={t("missions.cycle")} className="space-y-3">
      <ol className="flex flex-wrap gap-1 text-xs">
        {STATUSES.map((s, i) => (
          <li
            key={s}
            aria-current={i === current ? "step" : undefined}
            className={`rounded px-3 py-1 font-medium ${
              i < current
                ? "bg-marque-100 text-marque-900"
                : i === current
                  ? "bg-marque-600 text-white"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            {i + 1}. {t(`missions.statuts.${s}`)}
          </li>
        ))}
      </ol>
      {mission.transitions.length > 0 && (
        <div className="flex flex-wrap items-start gap-2">
          {mission.transitions
            .slice()
            .sort((a) => (a.sens === "suivant" ? -1 : 1))
            .map((tr) => (
              <div key={tr.statut}>
                <button
                  type="button"
                  className={tr.sens === "suivant" ? "btn-primaire" : "btn-secondaire"}
                  disabled={!!tr.motif_blocage}
                  aria-describedby={tr.motif_blocage ? `blocage-${tr.statut}` : undefined}
                  onClick={() => go(tr)}
                >
                  {t(tr.sens === "suivant" ? "missions.avancer" : "missions.revenir", {
                    statut: t(`missions.statuts.${tr.statut}`),
                  })}
                </button>
                {tr.motif_blocage && (
                  <p id={`blocage-${tr.statut}`} className="mt-1 max-w-sm text-xs text-red-800">
                    {tr.motif_blocage}
                  </p>
                )}
              </div>
            ))}
        </div>
      )}
      {error && <Alert kind="erreur">{error}</Alert>}
    </section>
  );
}
