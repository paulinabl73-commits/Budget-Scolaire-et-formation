import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { AnalysisOperation, AnalysisParam, Dataset } from "../../api/types";
import Alert from "../Alert";
import ConditionBuilder from "./ConditionBuilder";

type Values = Record<string, unknown>;

function initial(op: AnalysisOperation): Values {
  return Object.fromEntries(op.params.map((p) => [p.nom, p.defaut ?? (["colonnes", "agregats", "paires"].includes(p.type) ? [] : "")]));
}

/** Lancement d'une analyse de la bibliothèque (lot 6) ; formulaire tiré du catalogue. */
export default function AnalysisPanel({ ds }: { ds: Dataset }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<AnalysisOperation[]>([]);
  const [tables, setTables] = useState<Dataset[]>([]);
  const [code, setCode] = useState("");
  const [values, setValues] = useState<Values>({});
  const [second, setSecond] = useState("");
  const [nom, setNom] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<AnalysisOperation[]>("/analyses").then(setCatalog).catch((e: Error) => setError(e.message));
    api<Dataset[]>(`/engagements/${ds.engagement_id}/datasets`)
      .then((all) => setTables(all.filter((d) => d.statut === "pret")))
      .catch(() => setTables([]));
  }, [ds.engagement_id]);

  const op = catalog.find((o) => o.code === code);
  const secondTable = tables.find((d) => d.id === second);
  const schemas = [ds.schema, secondTable?.schema ?? []];
  const set = (nomParam: string, v: unknown) => setValues((old) => ({ ...old, [nomParam]: v }));

  const choose = (c: string) => {
    setCode(c);
    const o = catalog.find((x) => x.code === c);
    setValues(o ? initial(o) : {});
    setNom(o ? `${ds.nom} — ${t(`analyses.${c}.titre`)}` : "");
    setError(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!op) return;
    setError(null);
    setBusy(true);
    try {
      const parametres = Object.fromEntries(
        Object.entries(values).filter(([, v]) => v !== "" && v !== null && !(Array.isArray(v) && v.length === 0)),
      );
      const res = await post<Dataset>(`/datasets/${ds.id}/analyses`, {
        operation: op.code,
        nom,
        parametres,
        seconde_table_id: op.entrees === 2 ? second || null : null,
      });
      navigate(`/missions/${ds.engagement_id}/donnees/${res.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const columnsFor = (p: AnalysisParam) =>
    schemas[p.table].filter((c) => p.types_colonne.length === 0 || p.types_colonne.includes(c.type)).map((c) => c.nom);

  const field = (p: AnalysisParam) => {
    const id = `an-${p.nom}`;
    const label = (
      <label htmlFor={id} className="etiquette">
        {t(`analyses.${code}.params.${p.nom}`, { defaultValue: p.nom })}
        {!p.requis && <span className="font-normal text-slate-500"> ({t("analyses.facultatif")})</span>}
      </label>
    );
    const v = values[p.nom];
    switch (p.type) {
      case "colonne":
        return (
          <div key={p.nom}>
            {label}
            <select id={id} className="champ" required={p.requis} value={String(v ?? "")} onChange={(e) => set(p.nom, e.target.value)}>
              <option value="">—</option>
              {columnsFor(p).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        );
      case "colonnes":
        return (
          <fieldset key={p.nom} className="md:col-span-2">
            <legend className="etiquette">{t(`analyses.${code}.params.${p.nom}`, { defaultValue: p.nom })}</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {columnsFor(p).map((c) => (
                <label key={c} className="flex items-center gap-1 text-sm">
                  <input type="checkbox" checked={(v as string[]).includes(c)}
                    onChange={(e) => set(p.nom, e.target.checked ? [...(v as string[]), c] : (v as string[]).filter((x) => x !== c))} />
                  {c}
                </label>
              ))}
            </div>
          </fieldset>
        );
      case "choix":
        return (
          <div key={p.nom}>
            {label}
            <select id={id} className="champ" value={String(v ?? "")} onChange={(e) => set(p.nom, e.target.value)}>
              {p.choix.map((c) => <option key={c} value={c}>{t(`analyses.choix.${c}`, { defaultValue: c })}</option>)}
            </select>
          </div>
        );
      case "nombres":
        return (
          <div key={p.nom}>
            {label}
            <input id={id} className="champ" required={p.requis} placeholder="30 ; 60 ; 90"
              value={Array.isArray(v) ? v.join(" ; ") : String(v ?? "")}
              onChange={(e) => set(p.nom, e.target.value.split(";").map((x) => x.trim()).filter(Boolean))} />
          </div>
        );
      case "date":
        return (
          <div key={p.nom}>
            {label}
            <input id={id} type="date" className="champ" required={p.requis} value={String(v ?? "")} onChange={(e) => set(p.nom, e.target.value)} />
          </div>
        );
      case "expression":
        return (
          <div key={p.nom} className="md:col-span-2 space-y-2">
            <ConditionBuilder columns={ds.schema} onChange={(expr) => set(p.nom, expr)} />
            {label}
            <textarea id={id} className="champ font-mono" rows={2} required={p.requis} value={String(v ?? "")}
              onChange={(e) => set(p.nom, e.target.value)} />
          </div>
        );
      case "agregats":
        return <AggregatesField key={p.nom} columns={ds.schema.map((c) => c.nom)} value={v as { champ: string; fonction: string }[]} onChange={(x) => set(p.nom, x)} label={t(`analyses.${code}.params.${p.nom}`)} />;
      case "paires":
        return <PairsField key={p.nom} left={schemas[0].map((c) => c.nom)} right={schemas[1].map((c) => c.nom)} value={v as { gauche: string; droite: string }[]} onChange={(x) => set(p.nom, x)} label={t(`analyses.${code}.params.${p.nom}`)} />;
      default:
        return (
          <div key={p.nom}>
            {label}
            <input id={id} className="champ" inputMode={p.type === "texte" ? undefined : "decimal"} required={p.requis && p.defaut === null}
              value={String(v ?? "")} onChange={(e) => set(p.nom, e.target.value)} />
          </div>
        );
    }
  };

  return (
    <section className="carte space-y-3" aria-labelledby="analyse-titre">
      <h2 id="analyse-titre" className="text-base font-semibold">{t("analyses.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div>
        <label htmlFor="an-op" className="etiquette">{t("analyses.choisir")}</label>
        <select id="an-op" className="champ" value={code} onChange={(e) => choose(e.target.value)}>
          <option value="">—</option>
          {catalog.map((o) => <option key={o.code} value={o.code}>{o.exigence} · {t(`analyses.${o.code}.titre`)}</option>)}
        </select>
        {op && <p className="mt-1 text-sm text-slate-600">{t(`analyses.${op.code}.description`)}</p>}
      </div>
      {op && (
        <form onSubmit={submit} className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            {op.entrees === 2 && (
              <div>
                <label htmlFor="an-second" className="etiquette">{t("analyses.secondeTable")}</label>
                <select id="an-second" className="champ" required value={second} onChange={(e) => setSecond(e.target.value)}>
                  <option value="">—</option>
                  {tables.map((d) => <option key={d.id} value={d.id}>{d.nom}</option>)}
                </select>
              </div>
            )}
            {op.params.map(field)}
            <div>
              <label htmlFor="an-nom" className="etiquette">{t("analyses.nomResultat")}</label>
              <input id="an-nom" className="champ" required maxLength={200} value={nom} onChange={(e) => setNom(e.target.value)} />
            </div>
          </div>
          <button type="submit" className="btn-primaire" disabled={busy}>{t("analyses.lancer")}</button>
        </form>
      )}
    </section>
  );
}

function AggregatesField({ columns, value, onChange, label }: { columns: string[]; value: { champ: string; fonction: string }[]; onChange: (v: { champ: string; fonction: string }[]) => void; label: string }) {
  const { t } = useTranslation();
  const fns = ["somme", "moyenne", "min", "max", "nombre", "distincts", "ecart_type"];
  return (
    <fieldset className="md:col-span-2 space-y-1">
      <legend className="etiquette">{label}</legend>
      {value.map((a, i) => (
        <div key={i} className="flex gap-2">
          <select aria-label={t("analyses.fonction")} className="champ mt-0 w-40" value={a.fonction}
            onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, fonction: e.target.value } : x)))}>
            {fns.map((f) => <option key={f} value={f}>{t(`analyses.choix.${f}`)}</option>)}
          </select>
          <select aria-label={t("analyses.champ")} className="champ mt-0 flex-1" value={a.champ}
            onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, champ: e.target.value } : x)))}>
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button type="button" className="text-sm text-red-700 underline" onClick={() => onChange(value.filter((_, j) => j !== i))}>{t("analyses.retirer")}</button>
        </div>
      ))}
      <button type="button" className="text-sm text-marque-700 underline" onClick={() => onChange([...value, { champ: columns[0], fonction: "somme" }])}>
        {t("analyses.ajouterAgregat")}
      </button>
    </fieldset>
  );
}

function PairsField({ left, right, value, onChange, label }: { left: string[]; right: string[]; value: { gauche: string; droite: string }[]; onChange: (v: { gauche: string; droite: string }[]) => void; label: string }) {
  const { t } = useTranslation();
  return (
    <fieldset className="md:col-span-2 space-y-1">
      <legend className="etiquette">{label}</legend>
      {value.map((a, i) => (
        <div key={i} className="flex items-center gap-2">
          <select aria-label={t("analyses.cleGauche")} className="champ mt-0 flex-1" value={a.gauche}
            onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, gauche: e.target.value } : x)))}>
            {left.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <span aria-hidden="true">=</span>
          <select aria-label={t("analyses.cleDroite")} className="champ mt-0 flex-1" value={a.droite}
            onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, droite: e.target.value } : x)))}>
            {right.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button type="button" className="text-sm text-red-700 underline" onClick={() => onChange(value.filter((_, j) => j !== i))}>{t("analyses.retirer")}</button>
        </div>
      ))}
      <button type="button" className="text-sm text-marque-700 underline" disabled={right.length === 0}
        onClick={() => onChange([...value, { gauche: left[0], droite: right[0] }])}>
        {t("analyses.ajouterCle")}
      </button>
    </fieldset>
  );
}
