import type { ColDef, ICellRendererParams, NewValueParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, patch, post } from "../api/client";
import type { Team, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import { AG_GRID_FR } from "../lib/grid";
import { ROLES } from "../lib/permissions";
import type { Role } from "../lib/permissions";

const EMPTY = { email: "", nom: "", role: "auditeur" as Role, password: "", team_ids: [] as string[] };

export default function UsersPage() {
  const { t } = useTranslation();
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [teamName, setTeamName] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(
    null,
  );

  const load = useCallback(async () => {
    const [u, tm] = await Promise.all([api<User[]>("/users"), api<Team[]>("/teams")]);
    setUsers(u);
    setTeams(tm);
  }, []);

  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const run = useCallback(
    async (action: () => Promise<unknown>, success: string) => {
      setMessage(null);
      try {
        await action();
        setMessage({ kind: "succes", text: success });
      } catch (e) {
        setMessage({ kind: "erreur", text: (e as Error).message });
      }
      await load();
    },
    [load],
  );

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    await run(() => post("/users", form), t("utilisateurs.cree"));
    setForm(EMPTY);
    setShowForm(false);
  };

  const onCreateTeam = async (e: FormEvent) => {
    e.preventDefault();
    await run(() => post("/teams", { nom: teamName }), t("utilisateurs.modifie"));
    setTeamName("");
  };

  const columns = useMemo<ColDef<User>[]>(
    () => [
      { field: "nom", headerName: t("utilisateurs.nom"), filter: true, flex: 1, minWidth: 170 },
      { field: "email", headerName: t("utilisateurs.email"), filter: true, flex: 1, minWidth: 220 },
      {
        field: "role",
        headerName: t("utilisateurs.role"),
        editable: (p) => p.data?.id !== me?.id,
        cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: ROLES },
        valueFormatter: (p) => t(`roles.${p.value}`),
        onCellValueChanged: (p: NewValueParams<User>) =>
          void run(() => patch(`/users/${p.data.id}`, { role: p.newValue }), t("utilisateurs.modifie")),
      },
      {
        headerName: t("utilisateurs.equipes"),
        width: 150,
        valueGetter: (p) => p.data?.teams.map((x) => x.nom).join(", "),
      },
      {
        field: "actif",
        headerName: t("utilisateurs.actif"),
        width: 90,
        valueFormatter: (p) => (p.value ? t("commun.oui") : t("commun.non")),
      },
      {
        field: "mfa_enabled",
        headerName: t("utilisateurs.mfa"),
        width: 100,
        valueFormatter: (p) => (p.value ? t("commun.oui") : t("commun.non")),
      },
      {
        field: "is_locked",
        headerName: t("utilisateurs.verrouille"),
        width: 100,
        valueFormatter: (p) => (p.value ? t("commun.oui") : t("commun.non")),
      },
      {
        headerName: t("utilisateurs.actions"),
        width: 330,
        sortable: false,
        cellRenderer: (p: ICellRendererParams<User>) => {
          const u = p.data;
          if (!u || u.id === me?.id) return null;
          const lienClasse = "mr-3 text-sm text-marque-700 underline";
          return (
            <span>
              <button
                type="button"
                className={lienClasse}
                onClick={() =>
                  run(() => patch(`/users/${u.id}`, { actif: !u.actif }), t("utilisateurs.modifie"))
                }
              >
                {u.actif ? t("utilisateurs.desactiver") : t("utilisateurs.activer")}
              </button>
              {u.is_locked && (
                <button
                  type="button"
                  className={lienClasse}
                  onClick={() => run(() => post(`/users/${u.id}/unlock`), t("utilisateurs.modifie"))}
                >
                  {t("utilisateurs.deverrouiller")}
                </button>
              )}
              {u.mfa_enabled && (
                <button
                  type="button"
                  className={lienClasse}
                  onClick={() =>
                    run(() => post(`/users/${u.id}/reset-mfa`), t("utilisateurs.modifie"))
                  }
                >
                  {t("utilisateurs.reinitMfa")}
                </button>
              )}
              <button
                type="button"
                className="text-sm text-red-800 underline"
                onClick={() => {
                  if (window.confirm(t("utilisateurs.confirmerSuppression", { nom: u.nom }))) {
                    void run(() => del(`/users/${u.id}`), t("utilisateurs.modifie"));
                  }
                }}
              >
                {t("utilisateurs.supprimer")}
              </button>
            </span>
          );
        },
      },
    ],
    [t, me?.id, run],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("utilisateurs.titre")}</h1>
        <button type="button" className="btn-primaire" onClick={() => setShowForm((v) => !v)}>
          {t("utilisateurs.nouveau")}
        </button>
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      {showForm && (
        <form onSubmit={onCreate} className="carte grid grid-cols-2 gap-4" aria-label={t("utilisateurs.nouveau")}>
          <div>
            <label htmlFor="u-nom" className="etiquette">{t("utilisateurs.nom")}</label>
            <input id="u-nom" className="champ" required value={form.nom}
              onChange={(e) => setForm({ ...form, nom: e.target.value })} />
          </div>
          <div>
            <label htmlFor="u-email" className="etiquette">{t("utilisateurs.email")}</label>
            <input id="u-email" type="email" className="champ" required value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label htmlFor="u-role" className="etiquette">{t("utilisateurs.role")}</label>
            <select id="u-role" className="champ" value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>{t(`roles.${r}`)}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="u-pass" className="etiquette">{t("utilisateurs.motDePasseInitial")}</label>
            <input id="u-pass" type="password" autoComplete="new-password" className="champ" required
              aria-describedby="u-pass-aide" value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <p id="u-pass-aide" className="mt-1 text-xs text-slate-600">{t("utilisateurs.motDePasseAide")}</p>
          </div>
          <fieldset className="col-span-2">
            <legend className="etiquette">{t("utilisateurs.equipes")}</legend>
            <div className="mt-1 flex flex-wrap gap-4">
              {teams.map((tm) => (
                <label key={tm.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.team_ids.includes(tm.id)}
                    onChange={(e) => setForm({
                      ...form,
                      team_ids: e.target.checked
                        ? [...form.team_ids, tm.id]
                        : form.team_ids.filter((id) => id !== tm.id),
                    })} />
                  {tm.nom}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="col-span-2 flex gap-3">
            <button type="submit" className="btn-primaire">{t("utilisateurs.creer")}</button>
            <button type="button" className="btn-secondaire" onClick={() => setShowForm(false)}>
              {t("commun.annuler")}
            </button>
          </div>
        </form>
      )}

      <div className="ag-theme-quartz" style={{ height: 480 }}>
        <AgGridReact<User>
          rowData={users}
          columnDefs={columns}
          getRowId={(p) => p.data.id}
          localeText={AG_GRID_FR}
          singleClickEdit
        />
      </div>

      <form onSubmit={onCreateTeam} className="carte flex items-end gap-3">
        <div className="flex-1">
          <label htmlFor="team-nom" className="etiquette">{t("utilisateurs.nouvelleEquipe")}</label>
          <input id="team-nom" className="champ" required value={teamName}
            onChange={(e) => setTeamName(e.target.value)} />
        </div>
        <button type="submit" className="btn-secondaire">{t("utilisateurs.creerEquipe")}</button>
      </form>
    </div>
  );
}
