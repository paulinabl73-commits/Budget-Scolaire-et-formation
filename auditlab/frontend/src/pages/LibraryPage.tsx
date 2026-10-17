import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post, put } from "../api/client";
import type { Control, Cycle, Risk } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import { ControlForm, controlPayload, RiskForm, riskPayload } from "../components/RiskControlForms";
import TemplatesPanel from "../components/TemplatesPanel";
import { CYCLES } from "../lib/library";
import { can, PERM } from "../lib/permissions";

export default function LibraryPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canManage = can(user?.permissions, PERM.MISSIONS_MANAGE);
  const [tab, setTab] = useState<"risques" | "controles" | "modeles">("risques");
  const [cycle, setCycle] = useState<Cycle | "">("");
  const [risks, setRisks] = useState<Risk[]>([]);
  const [controls, setControls] = useState<Control[]>([]);
  const [adding, setAdding] = useState(false);
  const [editingLinks, setEditingLinks] = useState<string | null>(null);
  const [links, setLinks] = useState<string[]>([]);
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);

  const load = useCallback(async () => {
    const q = cycle ? `?cycle=${cycle}` : "";
    const [r, c] = await Promise.all([api<Risk[]>(`/library/risks${q}`), api<Control[]>(`/library/controls${q}`)]);
    setRisks(r);
    setControls(c);
  }, [cycle]);

  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setMessage(null);
    try {
      await action();
      setMessage({ kind: "succes", text: t("bibliotheque.enregistre") });
      setAdding(false);
      setEditingLinks(null);
      await load();
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("bibliotheque.titre")}</h1>
        <p className="text-slate-600">{t("bibliotheque.intro")}</p>
      </header>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <nav className="flex gap-1 border-b border-slate-200" aria-label={t("bibliotheque.titre")}>
          {(["risques", "controles", "modeles"] as const).map((k) => (
            <button key={k} type="button" aria-current={k === tab ? "page" : undefined}
              onClick={() => { setTab(k); setAdding(false); }}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${k === tab ? "border-marque-600 text-marque-700" : "border-transparent text-slate-600"}`}>
              {k === "modeles" ? t("modeles.onglet") : t(`bibliotheque.${k}`)}
            </button>
          ))}
        </nav>
        <div className="flex items-end gap-3">
          <div>
            <label htmlFor="lib-cycle" className="etiquette">{t("bibliotheque.cycle")}</label>
            <select id="lib-cycle" className="champ" value={cycle} onChange={(e) => setCycle(e.target.value as Cycle | "")}>
              <option value="">{t("bibliotheque.tousCycles")}</option>
              {CYCLES.map((c) => <option key={c} value={c}>{t(`bibliotheque.cycles.${c}`)}</option>)}
            </select>
          </div>
          {canManage && tab !== "modeles" && (
            <button type="button" className="btn-primaire" onClick={() => setAdding(true)}>
              {tab === "risques" ? t("bibliotheque.nouveauRisque") : t("bibliotheque.nouveauControle")}
            </button>
          )}
        </div>
      </div>
      {adding && tab === "risques" && (
        <RiskForm initialCycle={cycle || "achats"} onCancel={() => setAdding(false)}
          onSubmit={(d) => run(() => post("/library/risks", riskPayload(d)))} />
      )}
      {adding && tab === "controles" && (
        <ControlForm initialCycle={cycle || "achats"} onCancel={() => setAdding(false)}
          onSubmit={(d) => run(() => post("/library/controls", controlPayload(d)))} />
      )}

      {tab === "modeles" ? (
        <TemplatesPanel canManage={canManage} />
      ) : tab === "risques" ? (
        <ul className="space-y-3">
          {risks.map((r) => (
            <li key={r.id} className="carte space-y-2">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium">{r.libelle}</p>
                  <p className="text-xs text-slate-600">
                    {t(`bibliotheque.cycles.${r.cycle}`)} · {t(`bibliotheque.categories.${r.categorie}`)}
                  </p>
                  {r.description && <p className="mt-1 text-sm text-slate-700">{r.description}</p>}
                </div>
                {canManage && (
                  <div className="flex gap-3 text-sm">
                    <button type="button" className="text-marque-700 underline"
                      onClick={() => { setEditingLinks(r.id); setLinks(r.controles.map((c) => c.id)); }}>
                      {t("bibliotheque.modifierLiens")}
                    </button>
                    <button type="button" className="text-red-800 underline"
                      onClick={() => window.confirm(t("bibliotheque.confirmerSuppression", { libelle: r.libelle })) &&
                        run(() => del(`/library/risks/${r.id}`))}>
                      {t("commun.supprimer")}
                    </button>
                  </div>
                )}
              </div>
              <div>
                <p className="text-xs font-medium text-slate-600">{t("bibliotheque.controlesLies")}</p>
                {editingLinks === r.id ? (
                  <fieldset className="mt-1 space-y-1">
                    <legend className="sr-only">{t("bibliotheque.controlesLies")}</legend>
                    {controls.map((c) => (
                      <label key={c.id} className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={links.includes(c.id)}
                          onChange={(e) => setLinks(e.target.checked ? [...links, c.id] : links.filter((x) => x !== c.id))} />
                        {c.libelle}
                      </label>
                    ))}
                    <div className="flex gap-2 pt-1">
                      <button type="button" className="btn-primaire"
                        onClick={() => run(() => put(`/library/risks/${r.id}/controls`, { control_ids: links }))}>
                        {t("bibliotheque.enregistrerLiens")}
                      </button>
                      <button type="button" className="btn-secondaire" onClick={() => setEditingLinks(null)}>{t("commun.annuler")}</button>
                    </div>
                  </fieldset>
                ) : r.controles.length ? (
                  <ul className="mt-1 list-disc pl-5 text-sm">
                    {r.controles.map((c) => (
                      <li key={c.id}>
                        {c.libelle}{" "}
                        <span className="text-xs text-slate-500">
                          ({t(`bibliotheque.types.${c.type_controle}`)}, {t(`bibliotheque.natures.${c.nature}`)}, {t(`bibliotheque.frequences.${c.frequence}`)})
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-500">{t("bibliotheque.aucunControle")}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="carte overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-600">
              <tr>
                {["libelle", "cycle", "type", "nature", "frequence"].map((k) => (
                  <th key={k} scope="col" className="py-2 pr-3">{t(`bibliotheque.${k}`)}</th>
                ))}
                <th scope="col"><span className="sr-only">{t("utilisateurs.actions")}</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {controls.map((c) => (
                <tr key={c.id}>
                  <td className="py-2 pr-3">{c.libelle}</td>
                  <td className="pr-3">{t(`bibliotheque.cycles.${c.cycle}`)}</td>
                  <td className="pr-3">{t(`bibliotheque.types.${c.type_controle}`)}</td>
                  <td className="pr-3">{t(`bibliotheque.natures.${c.nature}`)}</td>
                  <td className="pr-3">{t(`bibliotheque.frequences.${c.frequence}`)}</td>
                  <td>
                    {canManage && (
                      <button type="button" className="text-sm text-red-800 underline"
                        onClick={() => window.confirm(t("bibliotheque.confirmerSuppression", { libelle: c.libelle })) &&
                          run(() => del(`/library/controls/${c.id}`))}>
                        {t("commun.supprimer")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
