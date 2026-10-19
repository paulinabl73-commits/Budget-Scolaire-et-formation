import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { Engagement } from "../../api/types";
import type { ScriptInfo } from "../../api/scripts";
import { useAuth } from "../../auth/AuthContext";
import { formatDateHeure } from "../../lib/format";
import { can } from "../../lib/permissions";
import Alert from "../Alert";

export const RUN_BADGE: Record<string, string> = {
  en_cours: "bg-sky-100 text-sky-900",
  termine: "bg-green-100 text-green-900",
  erreur: "bg-red-100 text-red-900",
};

const MODELE = `# Tables et fichiers d'entrée : choisis sur la page du script.
# audit.tables() et audit.files() donnent leurs noms.
t = audit.table(audit.tables()[0])
print(t.head())
`;

/** Scripts Python de la mission (DAT-26). */
export default function ScriptsTab({ mission }: { mission: Engagement }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const canEdit =
    mission.statut !== "cloturee" &&
    can(user?.permissions, "data:analyze") &&
    mission.mon_role !== null;
  const [rows, setRows] = useState<ScriptInfo[]>([]);
  const [nom, setNom] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<ScriptInfo[]>(`/engagements/${mission.id}/scripts`).then(
      setRows,
      (e: Error) => setError(e.message),
    );
  }, [mission.id]);
  const create = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const s = await post<ScriptInfo>(`/engagements/${mission.id}/scripts`, {
        nom,
        code: MODELE,
        entrees: [],
      });
      navigate(`/missions/${mission.id}/scripts/${s.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <div className="space-y-4">
      {error && <Alert kind="erreur">{error}</Alert>}
      <section className="carte overflow-x-auto p-0">
        {rows.length === 0 ? (
          <p className="p-6 text-sm text-slate-600">{t("scripts.aucun")}</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                {["nom", "entrees", "derniere"].map((k) => (
                  <th key={k} scope="col" className="px-4 py-2">
                    {t(`scripts.col.${k}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {rows.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2">
                    <Link
                      to={`/missions/${mission.id}/scripts/${s.id}`}
                      className="font-semibold text-marque-700 underline"
                    >
                      {s.nom}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    {s.entrees.map((e) => e.nom).join(", ") || "—"}
                  </td>
                  <td className="px-4 py-2">
                    {s.derniere_execution ? (
                      <>
                        <span
                          className={`rounded px-2 py-0.5 text-xs ${RUN_BADGE[s.derniere_execution.statut]}`}
                        >
                          {t(`scripts.statuts.${s.derniere_execution.statut}`)}
                        </span>{" "}
                        {formatDateHeure(s.derniere_execution.cree_le)}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {canEdit && (
        <form
          onSubmit={create}
          className="carte flex flex-wrap items-end gap-2"
          aria-labelledby="nouveau-script"
        >
          <h2 id="nouveau-script" className="w-full text-base font-semibold">
            {t("scripts.nouveau")}
          </h2>
          <label className="etiquette">
            {t("scripts.col.nom")}
            <input
              className="champ"
              required
              minLength={2}
              maxLength={200}
              value={nom}
              onChange={(e) => setNom(e.target.value)}
            />
          </label>
          <button type="submit" className="btn-primaire">
            {t("scripts.creer")}
          </button>
        </form>
      )}
    </div>
  );
}
