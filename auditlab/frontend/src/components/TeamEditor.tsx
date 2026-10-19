import { useTranslation } from "react-i18next";

import type { Member, MissionRole } from "../api/types";

const ROLES: MissionRole[] = ["chef_mission", "superviseur", "auditeur", "data_analyst"];

interface Props {
  staff: Member[];
  value: Record<string, MissionRole>;
  onChange: (value: Record<string, MissionRole>) => void;
  disabled?: boolean;
}

/** Choix de l'équipe : un rôle de mission par personne, ou « non membre ». */
export default function TeamEditor({ staff, value, onChange, disabled }: Props) {
  const { t } = useTranslation();
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-slate-600">
        <tr>
          <th scope="col" className="py-1">{t("utilisateurs.nom")}</th>
          <th scope="col">{t("missions.roleMission")}</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-200">
        {staff.map((s) => (
          <tr key={s.user_id}>
            <td className="py-1.5">
              {s.nom} <span className="text-xs text-slate-600">{s.email}</span>
            </td>
            <td>
              <select
                aria-label={`${t("missions.roleMission")} — ${s.nom}`}
                className="champ mt-0"
                disabled={disabled}
                value={value[s.user_id] ?? ""}
                onChange={(e) => {
                  const next = { ...value };
                  if (e.target.value) next[s.user_id] = e.target.value as MissionRole;
                  else delete next[s.user_id];
                  onChange(next);
                }}
              >
                <option value="">{t("missions.nonMembre")}</option>
                {ROLES.map((r) => (
                  <option key={r} value={r}>{t(`missions.roles.${r}`)}</option>
                ))}
              </select>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function teamPayload(value: Record<string, MissionRole>) {
  return Object.entries(value).map(([user_id, role_mission]) => ({ user_id, role_mission }));
}
