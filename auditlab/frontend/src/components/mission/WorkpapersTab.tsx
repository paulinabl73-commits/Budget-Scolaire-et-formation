import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { Engagement, Matrix, Workpaper, WorkpaperSummary } from "../../api/types";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

export const SIGN_BADGE: Record<string, string> = {
  brouillon: "bg-slate-100 text-slate-700",
  prepare: "bg-sky-100 text-sky-900",
  revu: "bg-indigo-100 text-indigo-900",
  approuve: "bg-green-100 text-green-900",
};

export const EVAL_BADGE: Record<string, string> = {
  efficace: "bg-green-100 text-green-900",
  partiellement_efficace: "bg-amber-100 text-amber-900",
  inefficace: "bg-red-100 text-red-900",
};

export default function WorkpapersTab({ mission }: { mission: Engagement }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [rows, setRows] = useState<WorkpaperSummary[]>([]);
  const [procedures, setProcedures] = useState<{ id: string; label: string }[]>([]);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ reference: "", titre: "", procedure_id: "" });
  const [error, setError] = useState<string | null>(null);
  const canWrite =
    mission.statut !== "cloturee" && (mission.mon_role === "auditeur" || mission.mon_role === "chef_mission");

  const load = useCallback(async () => {
    setRows(await api<WorkpaperSummary[]>(`/engagements/${mission.id}/workpapers`));
    const m = await api<Matrix>(`/engagements/${mission.id}/matrix`);
    setProcedures(
      m.controles.flatMap((c) => c.procedures.map((p) => ({ id: p.id, label: `${p.reference} — ${p.description}` }))),
    );
  }, [mission.id]);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const wp = await post<Workpaper>(`/engagements/${mission.id}/workpapers`, {
        reference: f.reference.toUpperCase(),
        titre: f.titre,
        procedure_id: f.procedure_id || null,
      });
      navigate(`/missions/${mission.id}/papiers/${wp.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      {error && <Alert kind="erreur">{error}</Alert>}
      {canWrite && !adding && (
        <button type="button" className="btn-primaire" onClick={() => setAdding(true)}>{t("papiers.nouveau")}</button>
      )}
      {adding && (
        <form onSubmit={submit} className="carte grid grid-cols-2 gap-3 md:grid-cols-4">
          <div>
            <label htmlFor="wp-ref" className="etiquette">{t("papiers.reference")}</label>
            <input id="wp-ref" className="champ font-mono" required aria-describedby="wp-ref-aide" value={f.reference}
              onChange={(e) => setF({ ...f, reference: e.target.value.toUpperCase() })} />
            <p id="wp-ref-aide" className="mt-1 text-xs text-slate-600">{t("papiers.referenceAide")}</p>
          </div>
          <div className="md:col-span-3">
            <label htmlFor="wp-titre" className="etiquette">{t("papiers.intitule")}</label>
            <input id="wp-titre" className="champ" required value={f.titre} onChange={(e) => setF({ ...f, titre: e.target.value })} />
          </div>
          <div className="col-span-2 md:col-span-4">
            <label htmlFor="wp-proc" className="etiquette">{t("papiers.procedure")}</label>
            <select id="wp-proc" className="champ" value={f.procedure_id} onChange={(e) => setF({ ...f, procedure_id: e.target.value })}>
              <option value="">{t("papiers.aucuneProcedure")}</option>
              {procedures.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>
          <div className="col-span-2 flex gap-2 md:col-span-4">
            <button type="submit" className="btn-primaire">{t("papiers.creer")}</button>
            <button type="button" className="btn-secondaire" onClick={() => setAdding(false)}>{t("commun.annuler")}</button>
          </div>
        </form>
      )}
      <div className="carte overflow-x-auto p-0">
        {rows.length === 0 ? (
          <p className="p-6 text-sm text-slate-600">{t("papiers.aucun")}</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th scope="col" className="px-4 py-2">{t("papiers.reference")}</th>
                <th scope="col" className="px-4">{t("papiers.intitule")}</th>
                <th scope="col" className="px-4">{t("papiers.procedure")}</th>
                <th scope="col" className="px-4">{t("papiers.evaluation")}</th>
                <th scope="col" className="px-4">{t("signatures.titre")}</th>
                <th scope="col" className="px-4">{t("papiers.modifie")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {rows.map((w) => (
                <tr key={w.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono">
                    <Link to={`/missions/${mission.id}/papiers/${w.id}`} className="text-marque-700 underline">{w.reference}</Link>
                  </td>
                  <td className="px-4">{w.titre}</td>
                  <td className="px-4 font-mono text-xs">{w.procedure_reference ?? "—"}</td>
                  <td className="px-4">
                    {w.evaluation && (
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${EVAL_BADGE[w.evaluation]}`}>
                        {t(`papiers.evaluations.${w.evaluation}`)}
                      </span>
                    )}
                  </td>
                  <td className="px-4">
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${SIGN_BADGE[w.statut_signature]}`}>
                      {t(`signatures.statuts.${w.statut_signature}`)}
                    </span>
                  </td>
                  <td className="px-4 text-xs text-slate-600">{formatDateHeure(w.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
