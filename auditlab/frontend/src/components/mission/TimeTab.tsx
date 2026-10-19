import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import type { Engagement, TimeActivity, TimeEntry, TimeSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { formatDate, formatNombre } from "../../lib/format";
import { today } from "../../lib/risk";
import Alert from "../Alert";

const ACTIVITIES: TimeActivity[] = ["preparation", "terrain", "revue", "rapport", "autre"];

export default function TimeTab({ mission, onChange }: { mission: Engagement; onChange: () => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [summary, setSummary] = useState<TimeSummary | null>(null);
  const [f, setF] = useState({ date: today(), heures: "7", activite: "terrain" as TimeActivity, commentaire: "" });
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);
  const isMember = mission.mon_role !== null;
  const open = mission.statut !== "cloturee";

  const load = useCallback(async () => {
    const [e, s] = await Promise.all([
      api<TimeEntry[]>(`/engagements/${mission.id}/time-entries`),
      api<TimeSummary>(`/engagements/${mission.id}/time-summary`),
    ]);
    setEntries(e);
    setSummary(s);
  }, [mission.id]);

  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const run = async (action: () => Promise<unknown>, text: string) => {
    setMessage(null);
    try {
      await action();
      setMessage({ kind: "succes", text });
      await load();
      onChange();
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run(
      () =>
        post(`/engagements/${mission.id}/time-entries`, {
          date: f.date,
          heures: Number(f.heures),
          activite: f.activite,
          commentaire: f.commentaire || null,
        }),
      t("temps.enregistre"),
    );
  };

  const max = Math.max(1, ...(summary?.par_personne.map((p) => p.jours) ?? [1]));
  return (
    <div className="space-y-6">
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {summary && (
        <section className="carte grid grid-cols-1 gap-6 md:grid-cols-3">
          <div>
            <h2 className="text-base font-semibold">{t("temps.budget")}</h2>
            <p className="mt-2 text-2xl font-semibold">
              {formatNombre(summary.jours_consommes)} / {formatNombre(summary.budget_jours)} j
            </p>
            <p className={`text-sm ${summary.ecart_jours < 0 ? "font-medium text-red-800" : "text-slate-600"}`}>
              {t(summary.ecart_jours < 0 ? "temps.depassement" : "temps.ecart", {
                ecart: formatNombre(Math.abs(summary.ecart_jours)),
                taux: formatNombre(summary.taux_consommation),
              })}
            </p>
            <p className="mt-1 text-xs text-slate-600">{t("temps.conversion", { heures: summary.heures_par_jour })}</p>
          </div>
          <Bars title={t("temps.parPersonne")} rows={summary.par_personne.map((p) => [p.libelle, p.jours])} max={max} />
          <Bars
            title={t("temps.parActivite")}
            rows={summary.par_activite.map((p) => [t(`temps.activites.${p.cle}`), p.jours])}
            max={Math.max(1, ...summary.par_activite.map((p) => p.jours))}
          />
        </section>
      )}
      {isMember && open && (
        <form onSubmit={submit} className="carte grid grid-cols-2 gap-4 md:grid-cols-5" aria-label={t("temps.saisir")}>
          <h2 className="col-span-full text-base font-semibold">{t("temps.saisir")}</h2>
          <div>
            <label htmlFor="t-date" className="etiquette">{t("temps.date")}</label>
            <input id="t-date" type="date" max={today()} className="champ" required value={f.date}
              onChange={(e) => setF({ ...f, date: e.target.value })} />
          </div>
          <div>
            <label htmlFor="t-h" className="etiquette">{t("temps.heures")}</label>
            <input id="t-h" type="number" min={0.25} max={24} step={0.25} className="champ" required value={f.heures}
              onChange={(e) => setF({ ...f, heures: e.target.value })} />
          </div>
          <div>
            <label htmlFor="t-act" className="etiquette">{t("temps.activite")}</label>
            <select id="t-act" className="champ" value={f.activite}
              onChange={(e) => setF({ ...f, activite: e.target.value as TimeActivity })}>
              {ACTIVITIES.map((a) => <option key={a} value={a}>{t(`temps.activites.${a}`)}</option>)}
            </select>
          </div>
          <div className="col-span-2">
            <label htmlFor="t-com" className="etiquette">{t("temps.commentaire")}</label>
            <input id="t-com" className="champ" value={f.commentaire} onChange={(e) => setF({ ...f, commentaire: e.target.value })} />
          </div>
          <div className="col-span-full">
            <button type="submit" className="btn-primaire">{t("temps.ajouter")}</button>
          </div>
        </form>
      )}
      <section className="carte overflow-x-auto">
        <h2 className="mb-2 text-base font-semibold">{mission.peut_gerer ? t("temps.saisies") : t("temps.mesSaisies")}</h2>
        {entries.length === 0 ? (
          <p className="text-sm text-slate-600">{t("temps.aucune")}</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-slate-600">
              <tr>
                <th scope="col" className="py-1">{t("temps.date")}</th>
                <th scope="col">{t("temps.personne")}</th>
                <th scope="col">{t("temps.activite")}</th>
                <th scope="col" className="text-right">{t("temps.heures")}</th>
                <th scope="col" className="pl-4">{t("temps.commentaire")}</th>
                <th scope="col"><span className="sr-only">{t("utilisateurs.actions")}</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="py-1.5">{formatDate(e.date)}</td>
                  <td>{e.user_nom}</td>
                  <td>{t(`temps.activites.${e.activite}`)}</td>
                  <td className="text-right">{formatNombre(e.heures)}</td>
                  <td className="pl-4 text-slate-600">{e.commentaire}</td>
                  <td className="text-right">
                    {e.user_id === user?.id && open && (
                      <button type="button" className="text-sm text-red-800 underline"
                        onClick={() => window.confirm(t("temps.confirmerSuppression")) &&
                          run(() => del(`/engagements/${mission.id}/time-entries/${e.id}`), t("temps.supprime"))}>
                        {t("commun.supprimer")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Bars({ title, rows, max }: { title: string; rows: [string, number][]; max: number }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      <ul className="space-y-1.5 text-sm">
        {rows.map(([label, value]) => (
          <li key={label}>
            <div className="flex justify-between"><span>{label}</span><span>{formatNombre(value)}</span></div>
            <div className="h-1.5 rounded bg-slate-200" aria-hidden>
              <div className="h-full rounded bg-marque-600" style={{ width: `${(value / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
