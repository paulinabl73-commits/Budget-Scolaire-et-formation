import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { Criticality, Engagement, Finding } from "../../api/types";
import Alert from "../Alert";
import CriticalityBadge from "../finding/CriticalityBadge";

export const CRITICITES: Criticality[] = ["faible", "moyenne", "elevee", "critique"];

/** Constats de la mission (Module 3), triés par criticité. */
export default function FindingsTab({ mission }: { mission: Engagement }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Finding[]>([]);
  const [titre, setTitre] = useState("");
  const [criticite, setCriticite] = useState<Criticality>("moyenne");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Finding[]>(`/engagements/${mission.id}/findings`).then(setRows), [mission.id]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const canWrite = mission.statut !== "cloturee" && (mission.mon_role === "auditeur" || mission.mon_role === "chef_mission");

  const create = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const f = await post<Finding>(`/engagements/${mission.id}/findings`, { titre, criticite });
      navigate(`/missions/${mission.id}/constats/${f.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      {error && <Alert kind="erreur">{error}</Alert>}
      {canWrite && (
        <form onSubmit={create} className="carte flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <label htmlFor="c-titre" className="etiquette">{t("constats.nouveau")}</label>
            <input id="c-titre" className="champ" required maxLength={300} value={titre} onChange={(e) => setTitre(e.target.value)} />
          </div>
          <div>
            <label htmlFor="c-crit" className="etiquette">{t("constats.criticite")}</label>
            <select id="c-crit" className="champ" value={criticite} onChange={(e) => setCriticite(e.target.value as Criticality)}>
              {CRITICITES.map((c) => <option key={c} value={c}>{t(`constats.criticites.${c}`)}</option>)}
            </select>
          </div>
          <button type="submit" className="btn-primaire">{t("constats.creer")}</button>
        </form>
      )}
      <div className="carte overflow-x-auto p-0">
        {rows.length === 0 ? (
          <p className="p-6 text-sm text-slate-600">{t("constats.aucun")}</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                {["reference", "titre", "criticite", "statut", "risque"].map((k) => (
                  <th key={k} scope="col" className="px-4 py-2">{t(`constats.col.${k}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {rows.map((f) => (
                <tr key={f.id}>
                  <td className="px-4 py-2 font-mono">{f.reference}</td>
                  <td className="px-4 py-2">
                    <Link to={`/missions/${mission.id}/constats/${f.id}`} className="text-marque-700 underline">{f.titre}</Link>
                  </td>
                  <td className="px-4 py-2"><CriticalityBadge value={f.criticite} /></td>
                  <td className="px-4 py-2">{t(`constats.statuts.${f.statut}`)}</td>
                  <td className="px-4 py-2">{f.risque}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
