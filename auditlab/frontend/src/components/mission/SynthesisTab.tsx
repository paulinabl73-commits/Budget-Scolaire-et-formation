import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, patch, put } from "../../api/client";
import type { Engagement, Member, MissionRole } from "../../api/types";
import { formatNombre } from "../../lib/format";
import { budgetRatio } from "../../lib/mission";
import Alert from "../Alert";
import TeamEditor, { teamPayload } from "../TeamEditor";

interface Props {
  mission: Engagement;
  onChange: (m: Engagement) => void;
}

export default function SynthesisTab({ mission, onChange }: Props) {
  const { t } = useTranslation();
  const editable = mission.peut_gerer && mission.statut !== "cloturee";
  const [f, setF] = useState(() => toForm(mission));
  const [staff, setStaff] = useState<Member[]>([]);
  const [team, setTeam] = useState<Record<string, MissionRole>>({});
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);

  useEffect(() => {
    setF(toForm(mission));
    setTeam(Object.fromEntries(mission.membres.map((m) => [m.user_id, m.role_mission])));
  }, [mission]);

  useEffect(() => {
    if (!editable) return;
    api<Member[]>(`/engagements/${mission.id}/candidates`)
      .then(setStaff)
      .catch(() => setStaff([]));
  }, [editable, mission.id]);

  const run = async (action: () => Promise<Engagement>, text: string) => {
    setMessage(null);
    try {
      onChange(await action());
      setMessage({ kind: "succes", text });
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    }
  };

  const save = (e: FormEvent) => {
    e.preventDefault();
    void run(
      () =>
        patch<Engagement>(`/engagements/${mission.id}`, {
          ...f,
          budget_jours: Number(f.budget_jours),
          perimetre: f.perimetre || null,
          objectifs: f.objectifs || null,
        }),
      t("missions.enregistree"),
    );
  };

  const ratio = budgetRatio(mission.jours_consommes, mission.budget_jours);
  const over = mission.jours_consommes > mission.budget_jours;
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));
  // Membres actuels toujours listés, même s'ils ne sont plus candidats.
  const people = [
    ...staff,
    ...mission.membres.filter((m) => !staff.some((s) => s.user_id === m.user_id)),
  ];

  return (
    <div className="space-y-6">
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <section className="carte space-y-2">
        <h2 className="text-base font-semibold">{t("temps.budget")}</h2>
        <p className="text-sm">
          {t("temps.consommation", {
            consomme: formatNombre(mission.jours_consommes),
            budget: formatNombre(mission.budget_jours),
          })}
        </p>
        <div className="h-2 w-full overflow-hidden rounded bg-slate-200" aria-hidden>
          <div className={`h-full ${over ? "bg-red-600" : "bg-marque-600"}`} style={{ width: `${ratio * 100}%` }} />
        </div>
      </section>
      <form onSubmit={save} className="carte grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label htmlFor="s-titre" className="etiquette">{t("missions.intitule")}</label>
          <input id="s-titre" className="champ" disabled={!editable} required value={f.titre} onChange={(e) => set("titre", e.target.value)} />
        </div>
        <div>
          <label htmlFor="s-debut" className="etiquette">{t("missions.debut")}</label>
          <input id="s-debut" type="date" className="champ" disabled={!editable} value={f.date_debut} onChange={(e) => set("date_debut", e.target.value)} />
        </div>
        <div>
          <label htmlFor="s-fin" className="etiquette">{t("missions.fin")}</label>
          <input id="s-fin" type="date" className="champ" disabled={!editable} value={f.date_fin} onChange={(e) => set("date_fin", e.target.value)} />
        </div>
        <div>
          <label htmlFor="s-budget" className="etiquette">{t("plan.budget")}</label>
          <input id="s-budget" type="number" min={0.5} step={0.5} className="champ" disabled={!editable} value={f.budget_jours} onChange={(e) => set("budget_jours", e.target.value)} />
        </div>
        <div>
          <p className="etiquette">{t("missions.entite")}</p>
          <p className="mt-2 text-sm">{mission.entity_nom ?? "—"}</p>
        </div>
        <div>
          <label htmlFor="s-perim" className="etiquette">{t("missions.perimetre")}</label>
          <textarea id="s-perim" rows={3} className="champ" disabled={!editable} value={f.perimetre} onChange={(e) => set("perimetre", e.target.value)} />
        </div>
        <div>
          <label htmlFor="s-obj" className="etiquette">{t("missions.objectifs")}</label>
          <textarea id="s-obj" rows={3} className="champ" disabled={!editable} value={f.objectifs} onChange={(e) => set("objectifs", e.target.value)} />
        </div>
        {editable && (
          <div className="col-span-2">
            <button type="submit" className="btn-primaire">{t("commun.enregistrer")}</button>
          </div>
        )}
      </form>
      <section className="carte space-y-3">
        <h2 className="text-base font-semibold">{t("missions.equipe")}</h2>
        {editable ? (
          <>
            <TeamEditor staff={people} value={team} onChange={setTeam} />
            <button
              type="button"
              className="btn-secondaire"
              onClick={() =>
                run(() => put<Engagement>(`/engagements/${mission.id}/members`, teamPayload(team)), t("missions.equipeEnregistree"))
              }
            >
              {t("missions.enregistrerEquipe")}
            </button>
          </>
        ) : (
          <ul className="divide-y divide-slate-200 text-sm">
            {mission.membres.map((m) => (
              <li key={m.user_id} className="flex justify-between py-1.5">
                <span>{m.nom}</span>
                <span className="text-slate-600">{t(`missions.roles.${m.role_mission}`)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function toForm(m: Engagement) {
  return {
    titre: m.titre,
    date_debut: m.date_debut,
    date_fin: m.date_fin,
    budget_jours: String(m.budget_jours),
    perimetre: m.perimetre ?? "",
    objectifs: m.objectifs ?? "",
  };
}
