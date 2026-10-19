import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { ScriptInfo, ScriptTemplateInfo } from "../../api/scripts";
import { useAuth } from "../../auth/AuthContext";
import { formatDate } from "../../lib/format";
import { can } from "../../lib/permissions";
import Alert from "../Alert";

/** Bibliothèque de tests prêts à l'emploi par cycle (DAT-28). */
export default function ScriptLibraryPanel({
  missionId,
  canUse,
}: {
  missionId: string;
  canUse: boolean;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const publisher = can(user?.permissions, "data:publish_library");
  const [cycles, setCycles] = useState<Record<string, string>>({});
  const [cycle, setCycle] = useState("");
  const [rows, setRows] = useState<ScriptTemplateInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    () =>
      api<ScriptTemplateInfo[]>(
        `/script-library?tous=${publisher}${cycle ? `&cycle=${cycle}` : ""}`,
      ).then(setRows),
    [cycle, publisher],
  );
  useEffect(() => {
    api<Record<string, string>>("/script-library/cycles").then(setCycles, () =>
      setCycles({}),
    );
  }, []);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const act = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const use = (id: string) =>
    act(async () => {
      const s = await post<ScriptInfo>(
        `/engagements/${missionId}/scripts/from-library`,
        { modele_id: id, entrees: [] },
      );
      navigate(`/missions/${missionId}/scripts/${s.id}`);
    });
  return (
    <section className="carte space-y-3" aria-labelledby="bibliotheque-scripts">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="bibliotheque-scripts" className="text-base font-semibold">
          {t("bibliothequeScripts.titre")}
        </h2>
        <label className="etiquette">
          {t("bibliothequeScripts.cycle")}
          <select
            className="champ"
            value={cycle}
            onChange={(e) => setCycle(e.target.value)}
          >
            <option value="">{t("bibliothequeScripts.tous")}</option>
            {Object.entries(cycles).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="divide-y divide-slate-200 text-sm">
        {rows.map((m) => (
          <li key={m.id} className="space-y-1 py-2">
            <p>
              <span className="font-semibold">{m.reference}</span> · {m.nom}{" "}
              <span className="text-xs text-slate-600">
                ({cycles[m.cycle] ?? m.cycle}, v{m.version})
              </span>
              {m.statut !== "publie" && (
                <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                  {t(`bibliothequeScripts.statuts.${m.statut}`)}
                </span>
              )}
            </p>
            {m.objectif && <p className="text-slate-700">{m.objectif}</p>}
            <p className="text-xs text-slate-600">
              {t("bibliothequeScripts.colonnes", {
                colonnes: m.colonnes.join(", ") || "—",
              })}
              {m.publie_le &&
                ` · ${t("bibliothequeScripts.publie", { le: formatDate(m.publie_le), par: m.publie_par ?? t("bibliothequeScripts.livre") })}`}
            </p>
            <div className="flex flex-wrap gap-2">
              {canUse && m.statut === "publie" && (
                <button
                  type="button"
                  className="btn-secondaire"
                  onClick={() => void use(m.id)}
                >
                  {t("bibliothequeScripts.utiliser")}
                </button>
              )}
              {publisher && m.statut === "brouillon" && (
                <button
                  type="button"
                  className="btn-secondaire"
                  onClick={() =>
                    void act(() => post(`/script-library/${m.id}/publish`))
                  }
                >
                  {t("bibliothequeScripts.publier")}
                </button>
              )}
              {publisher && m.statut === "publie" && (
                <button
                  type="button"
                  className="underline"
                  onClick={() =>
                    void act(() => post(`/script-library/${m.id}/retire`))
                  }
                >
                  {t("bibliothequeScripts.retirer")}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
