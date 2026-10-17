import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, post } from "../api/client";
import type {
  AuditableEntity,
  Engagement,
  EngagementSummary,
  Member,
  MissionRole,
  Plan,
  PlanSummary,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import TeamEditor, { teamPayload } from "../components/TeamEditor";
import { formatDate, formatNombre } from "../lib/format";
import { STATUS_BADGE, STATUSES } from "../lib/mission";
import { can, PERM } from "../lib/permissions";

interface PlanLine {
  id: string;
  label: string;
}

export default function MissionsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const canCreate = can(user?.permissions, PERM.MISSIONS_MANAGE);
  const [missions, setMissions] = useState<EngagementSummary[]>([]);
  const [statut, setStatut] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<EngagementSummary[]>(`/engagements${statut ? `?statut=${statut}` : ""}`)
      .then(setMissions)
      .catch((e: Error) => setError(e.message));
  }, [statut]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-2xl font-semibold">{t("missions.titre")}</h1>
        <div className="flex items-end gap-3">
          <div>
            <label htmlFor="f-statut" className="etiquette">{t("missions.statut")}</label>
            <select id="f-statut" className="champ" value={statut} onChange={(e) => setStatut(e.target.value)}>
              <option value="">{t("missions.tous")}</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{t(`missions.statuts.${s}`)}</option>
              ))}
            </select>
          </div>
          {canCreate && (
            <button type="button" className="btn-primaire" onClick={() => setShowForm((v) => !v)}>
              {t("missions.nouvelle")}
            </button>
          )}
        </div>
      </header>
      {error && <Alert kind="erreur">{error}</Alert>}
      {showForm && (
        <NewMissionForm
          onCancel={() => setShowForm(false)}
          onCreated={(m) => navigate(`/missions/${m.id}`, { state: { created: m.reference } })}
        />
      )}
      <div className="carte overflow-x-auto p-0">
        {missions.length === 0 ? (
          <p className="p-6 text-sm text-slate-600">{t("missions.aucune")}</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                {["reference", "intitule", "entite", "statut", "periode", "budget", "consomme", "chef"].map((k) => (
                  <th key={k} scope="col" className="px-4 py-2">{t(`missions.${k}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {missions.map((m) => (
                <tr key={m.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono">
                    <Link to={`/missions/${m.id}`} className="text-marque-700 underline">{m.reference}</Link>
                  </td>
                  <td className="px-4">{m.titre}</td>
                  <td className="px-4">{m.entity_nom ?? "—"}</td>
                  <td className="px-4">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[m.statut]}`}>
                      {t(`missions.statuts.${m.statut}`)}
                    </span>
                  </td>
                  <td className="px-4 whitespace-nowrap">
                    {formatDate(m.date_debut)} – {formatDate(m.date_fin)}
                  </td>
                  <td className="px-4 text-right">{formatNombre(m.budget_jours)}</td>
                  <td className={`px-4 text-right ${m.jours_consommes > m.budget_jours ? "font-semibold text-red-800" : ""}`}>
                    {formatNombre(m.jours_consommes)}
                  </td>
                  <td className="px-4">{m.chef_nom}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function NewMissionForm({ onCancel, onCreated }: { onCancel: () => void; onCreated: (m: Engagement) => void }) {
  const { t } = useTranslation();
  const [source, setSource] = useState<"plan" | "ponctuelle">("plan");
  const [lines, setLines] = useState<PlanLine[]>([]);
  const [entities, setEntities] = useState<AuditableEntity[]>([]);
  const [staff, setStaff] = useState<Member[]>([]);
  const [team, setTeam] = useState<Record<string, MissionRole>>({});
  const [f, setF] = useState({
    plan_item_id: "", entity_id: "", titre: "", perimetre: "", objectifs: "",
    date_debut: "", date_fin: "", budget_jours: "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));

  useEffect(() => {
    (async () => {
      setStaff(await api<Member[]>("/staff"));
      setEntities(await api<AuditableEntity[]>("/universe/entities").catch(() => []));
      const plans = await api<PlanSummary[]>("/plans").catch(() => []);
      const valid = plans.filter((p) => p.statut === "valide");
      const full = await Promise.all(valid.map((p) => api<Plan>(`/plans/${p.id}`)));
      setLines(full.flatMap((p) => p.items.map((i) => ({ id: i.id, label: `${p.annee} — ${i.titre}` }))));
    })().catch((e: Error) => setError(e.message));
  }, []);

  const fromPlan = source === "plan";
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const body = {
      plan_item_id: fromPlan ? f.plan_item_id || null : null,
      entity_id: !fromPlan ? f.entity_id || null : null,
      titre: f.titre || null,
      perimetre: f.perimetre || null,
      objectifs: f.objectifs || null,
      date_debut: f.date_debut || null,
      date_fin: f.date_fin || null,
      budget_jours: f.budget_jours ? Number(f.budget_jours) : null,
      membres: teamPayload(team),
    };
    try {
      onCreated(await post<Engagement>("/engagements", body));
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const sortedEntities = useMemo(
    () => [...entities].sort((a, b) => a.nom.localeCompare(b.nom, "fr")),
    [entities],
  );

  return (
    <form onSubmit={submit} className="carte grid grid-cols-2 gap-4" aria-label={t("missions.nouvelle")}>
      <h2 className="col-span-2 text-lg font-semibold">{t("missions.nouvelle")}</h2>
      {error && <div className="col-span-2"><Alert kind="erreur">{error}</Alert></div>}
      <fieldset className="col-span-2 flex gap-6">
        <legend className="etiquette mb-1">{t("missions.source")}</legend>
        {(["plan", "ponctuelle"] as const).map((s) => (
          <label key={s} className="flex items-center gap-2 text-sm">
            <input type="radio" name="source" checked={source === s} onChange={() => setSource(s)} />
            {s === "plan" ? t("missions.depuisPlan") : t("missions.ponctuelle")}
          </label>
        ))}
      </fieldset>
      {fromPlan ? (
        <div className="col-span-2">
          <label htmlFor="m-ligne" className="etiquette">{t("missions.ligneDuPlan")}</label>
          <select id="m-ligne" className="champ" required value={f.plan_item_id}
            onChange={(e) => set("plan_item_id", e.target.value)}>
            <option value="">{lines.length ? t("missions.choisirLigne") : t("missions.aucuneLigne")}</option>
            {lines.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
          <p className="mt-1 text-xs text-slate-600">{t("missions.prefill")}</p>
        </div>
      ) : (
        <div className="col-span-2">
          <label htmlFor="m-entite" className="etiquette">{t("missions.entiteOptionnelle")}</label>
          <select id="m-entite" className="champ" value={f.entity_id} onChange={(e) => set("entity_id", e.target.value)}>
            <option value="">{t("missions.aucuneEntite")}</option>
            {sortedEntities.map((x) => <option key={x.id} value={x.id}>{x.nom}</option>)}
          </select>
        </div>
      )}
      <div className="col-span-2">
        <label htmlFor="m-titre" className="etiquette">{t("missions.intitule")}</label>
        <input id="m-titre" className="champ" required={!fromPlan} value={f.titre} onChange={(e) => set("titre", e.target.value)} />
      </div>
      <div>
        <label htmlFor="m-debut" className="etiquette">{t("missions.debut")}</label>
        <input id="m-debut" type="date" className="champ" required={!fromPlan} value={f.date_debut} onChange={(e) => set("date_debut", e.target.value)} />
      </div>
      <div>
        <label htmlFor="m-fin" className="etiquette">{t("missions.fin")}</label>
        <input id="m-fin" type="date" className="champ" required={!fromPlan} value={f.date_fin} onChange={(e) => set("date_fin", e.target.value)} />
      </div>
      <div>
        <label htmlFor="m-budget" className="etiquette">{t("plan.budget")}</label>
        <input id="m-budget" type="number" min={0.5} step={0.5} className="champ" required={!fromPlan} value={f.budget_jours} onChange={(e) => set("budget_jours", e.target.value)} />
      </div>
      <div />
      <div>
        <label htmlFor="m-perim" className="etiquette">{t("missions.perimetre")}</label>
        <textarea id="m-perim" rows={2} className="champ" value={f.perimetre} onChange={(e) => set("perimetre", e.target.value)} />
      </div>
      <div>
        <label htmlFor="m-obj" className="etiquette">{t("missions.objectifs")}</label>
        <textarea id="m-obj" rows={2} className="champ" value={f.objectifs} onChange={(e) => set("objectifs", e.target.value)} />
      </div>
      <div className="col-span-2">
        <h3 className="etiquette">{t("missions.equipe")}</h3>
        <p className="mb-2 text-xs text-slate-600">{t("missions.equipeAide")}</p>
        <TeamEditor staff={staff} value={team} onChange={setTeam} />
      </div>
      <div className="col-span-2 flex gap-3">
        <button type="submit" className="btn-primaire">{t("missions.creer")}</button>
        <button type="button" className="btn-secondaire" onClick={onCancel}>{t("commun.annuler")}</button>
      </div>
    </form>
  );
}
