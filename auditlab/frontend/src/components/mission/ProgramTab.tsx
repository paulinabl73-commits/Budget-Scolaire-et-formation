import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import type { Control, Engagement, Matrix, Procedure, Risk, TestType } from "../../api/types";
import Alert from "../Alert";
import ProcedureLine from "./ProcedureLine";
import { ControlForm, controlPayload, RiskForm, riskPayload } from "../RiskControlForms";

const TEST_TYPES: TestType[] = ["conception", "efficacite", "substantif"];

export default function ProgramTab({ mission }: { mission: Engagement }) {
  const { t } = useTranslation();
  const editable = mission.peut_gerer && mission.statut !== "cloturee";
  const base = `/engagements/${mission.id}`;
  const [matrix, setMatrix] = useState<Matrix | null>(null);
  const [libRisks, setLibRisks] = useState<Risk[]>([]);
  const [libControls, setLibControls] = useState<Control[]>([]);
  const [pick, setPick] = useState("");
  const [newRisk, setNewRisk] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);

  const load = useCallback(async () => setMatrix(await api<Matrix>(`${base}/matrix`)), [base]);
  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
    if (editable) {
      api<Risk[]>("/library/risks").then(setLibRisks).catch(() => setLibRisks([]));
      api<Control[]>("/library/controls").then(setLibControls).catch(() => setLibControls([]));
    }
  }, [load, editable]);

  const run = async (action: () => Promise<unknown>) => {
    setMessage(null);
    try {
      await action();
      setMessage({ kind: "succes", text: t("programme.enregistre") });
      await load();
      return true;
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
      return false;
    }
  };
  const remove = (path: string, libelle: string) =>
    window.confirm(t("programme.confirmerSuppression", { libelle })) && run(() => del(`${base}/${path}`));

  if (!matrix) return <p>{t("commun.chargement")}</p>;
  const linked = new Set(matrix.risques.flatMap((r) => r.controles.map((c) => c.id)));
  const orphans = matrix.controles.filter((c) => !linked.has(c.id));
  const nbProcedures = matrix.controles.reduce((n, c) => n + c.procedures.length, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600">
          {t("programme.intro")}{" "}
          <span className="font-medium text-slate-800">
            {t("programme.risques", { count: matrix.risques.length })} ·{" "}
            {t("programme.controles", { count: matrix.controles.length })} ·{" "}
            {t("programme.procedures", { count: nbProcedures })}
          </span>
        </p>
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {editable && (
        <section className="carte flex flex-wrap items-end gap-3">
          <div className="min-w-72 flex-1">
            <label htmlFor="pg-lib" className="etiquette">{t("programme.importer")}</label>
            <select id="pg-lib" className="champ" value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">{t("programme.choisirRisque")}</option>
              {libRisks.map((r) => (
                <option key={r.id} value={r.id}>{t(`bibliotheque.cycles.${r.cycle}`)} — {r.libelle}</option>
              ))}
            </select>
          </div>
          <button type="button" className="btn-primaire" disabled={!pick}
            onClick={async () => { if (await run(() => post(`${base}/risks`, { library_risk_id: pick }))) setPick(""); }}>
            {t("programme.importerBtn")}
          </button>
          <button type="button" className="btn-secondaire" onClick={() => setNewRisk(true)}>{t("programme.nouveauRisque")}</button>
          {newRisk && (
            <div className="w-full">
              <RiskForm idPrefix="mr" onCancel={() => setNewRisk(false)}
                onSubmit={async (d) => { if (await run(() => post(`${base}/risks`, riskPayload(d)))) setNewRisk(false); }} />
            </div>
          )}
        </section>
      )}
      {matrix.risques.length === 0 && <p className="carte text-sm text-slate-600">{t("programme.aucunRisque")}</p>}
      {mission.peut_gerer && matrix.risques.length > 0 && (
        <form className="flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await run(() => post("/templates", { nom: templateName, from_engagement_id: mission.id }))) setTemplateName("");
          }}>
          <div>
            <label htmlFor="pg-tpl" className="etiquette">{t("modeles.nomDuModele")}</label>
            <input id="pg-tpl" className="champ" required value={templateName} onChange={(e) => setTemplateName(e.target.value)} />
          </div>
          <button type="submit" className="btn-secondaire">{t("modeles.enregistrerCommeModele")}</button>
        </form>
      )}
      {matrix.risques.map((r) => (
        <section key={r.id} className="carte space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold">{r.libelle}</h3>
              <p className="text-xs text-slate-600">
                {t(`bibliotheque.cycles.${r.cycle}`)} · {t(`bibliotheque.categories.${r.categorie}`)}
                {r.source_id && ` · ${t("programme.copie")}`}
              </p>
            </div>
            {editable && (
              <button type="button" className="text-sm text-red-800 underline" onClick={() => remove(`risks/${r.id}`, r.libelle)}>
                {t("commun.supprimer")}
              </button>
            )}
          </div>
          <ul className="space-y-3 border-l-2 border-marque-100 pl-4">
            {r.controles.map((c) => (
              <ControlBlock key={c.id} mission={mission} control={c} editable={editable} onChanged={() => void load()}
                onError={(text) => setMessage({ kind: "erreur", text })} onRemove={() => remove(`controls/${c.id}`, c.libelle)}
                onRemoveProcedure={(p) => remove(`procedures/${p.id}`, p.reference ?? p.description)}
                onAddProcedure={(description, type_test) => run(() => post(`${base}/procedures`, { control_id: c.id, description, type_test }))} />
            ))}
          </ul>
          {editable && (
            <AddControl riskId={r.id} cycle={r.cycle} libControls={libControls}
              onAdd={(body) => run(() => post(`${base}/controls`, body))} />
          )}
        </section>
      ))}
      {orphans.length > 0 && (
        <section className="carte space-y-3">
          <h3 className="font-semibold">{t("programme.controlesOrphelins")}</h3>
          <ul className="space-y-3">
            {orphans.map((c) => (
              <ControlBlock key={c.id} mission={mission} control={c} editable={editable} onChanged={() => void load()}
                onError={(text) => setMessage({ kind: "erreur", text })} onRemove={() => remove(`controls/${c.id}`, c.libelle)}
                onRemoveProcedure={(p) => remove(`procedures/${p.id}`, p.reference ?? p.description)}
                onAddProcedure={(description, type_test) => run(() => post(`${base}/procedures`, { control_id: c.id, description, type_test }))} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function ControlBlock({ mission, control, editable, onRemove, onRemoveProcedure, onAddProcedure, onChanged, onError }: {
  mission: Engagement;
  onChanged: () => void;
  onError: (message: string) => void;
  control: Control;
  editable: boolean;
  onRemove: () => void;
  onRemoveProcedure: (p: Procedure) => void;
  onAddProcedure: (description: string, type: TestType) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [description, setDescription] = useState("");
  const [type, setType] = useState<TestType>("efficacite");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (await onAddProcedure(description, type)) {
      setDescription("");
      setAdding(false);
    }
  };
  return (
    <li className="space-y-1">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium">
          {control.libelle}{" "}
          <span className="text-xs font-normal text-slate-600">
            ({t(`bibliotheque.types.${control.type_controle}`)}, {t(`bibliotheque.natures.${control.nature}`)},{" "}
            {t(`bibliotheque.frequences.${control.frequence}`)})
          </span>
        </p>
        {editable && (
          <button type="button" className="text-xs text-red-800 underline" onClick={onRemove}>{t("commun.supprimer")}</button>
        )}
      </div>
      {control.procedures.length === 0 ? (
        <p className="text-xs text-slate-600">{t("programme.aucuneProcedure")}</p>
      ) : (
        <ul className="space-y-1">
          {control.procedures.map((p) => (
            <ProcedureLine key={p.id} mission={mission} procedure={p} editable={editable}
              onRemove={() => onRemoveProcedure(p)} onChanged={onChanged} onError={onError} />
          ))}
        </ul>
      )}
      {editable && (adding ? (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <label htmlFor={`pr-${control.id}`} className="etiquette">{t("programme.procedure")}</label>
            <input id={`pr-${control.id}`} className="champ" required value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div>
            <label htmlFor={`pt-${control.id}`} className="etiquette">{t("programme.typeTest")}</label>
            <select id={`pt-${control.id}`} className="champ" value={type} onChange={(e) => setType(e.target.value as TestType)}>
              {TEST_TYPES.map((x) => <option key={x} value={x}>{t(`programme.typesTest.${x}`)}</option>)}
            </select>
          </div>
          <button type="submit" className="btn-primaire">{t("programme.ajouter")}</button>
          <button type="button" className="btn-secondaire" onClick={() => setAdding(false)}>{t("commun.annuler")}</button>
        </form>
      ) : (
        <button type="button" className="text-xs text-marque-700 underline" onClick={() => setAdding(true)}>
          {t("programme.ajouterProcedure")}
        </button>
      ))}
    </li>
  );
}

function AddControl({ riskId, cycle, libControls, onAdd }: {
  riskId: string;
  cycle: Risk["cycle"];
  libControls: Control[];
  onAdd: (body: Record<string, unknown>) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"none" | "lib" | "new">("none");
  const [pick, setPick] = useState("");
  if (mode === "none") {
    return (
      <div className="flex gap-3 text-sm">
        <button type="button" className="text-marque-700 underline" onClick={() => setMode("lib")}>
          {t("programme.ajouterControle")} — {t("programme.depuisBibliotheque")}
        </button>
        <button type="button" className="text-marque-700 underline" onClick={() => setMode("new")}>
          {t("programme.nouveauControle")}
        </button>
      </div>
    );
  }
  if (mode === "new") {
    return (
      <ControlForm idPrefix={`nc-${riskId}`} initialCycle={cycle} onCancel={() => setMode("none")}
        onSubmit={async (d) => { if (await onAdd({ ...controlPayload(d), risk_ids: [riskId] })) setMode("none"); }} />
    );
  }
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="min-w-72 flex-1">
        <label htmlFor={`lc-${riskId}`} className="etiquette">{t("programme.depuisBibliotheque")}</label>
        <select id={`lc-${riskId}`} className="champ" value={pick} onChange={(e) => setPick(e.target.value)}>
          <option value="">{t("programme.choisirControle")}</option>
          {libControls.map((c) => <option key={c.id} value={c.id}>{c.libelle}</option>)}
        </select>
      </div>
      <button type="button" className="btn-primaire" disabled={!pick}
        onClick={async () => { if (await onAdd({ library_control_id: pick, risk_ids: [riskId] })) setMode("none"); }}>
        {t("programme.ajouter")}
      </button>
      <button type="button" className="btn-secondaire" onClick={() => setMode("none")}>{t("commun.annuler")}</button>
    </div>
  );
}
