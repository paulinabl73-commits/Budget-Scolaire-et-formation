import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { AnalysisParam, AuditFile, Dataset } from "../../api/types";
import { formatDate } from "../../lib/format";
import Alert from "../Alert";

interface Regulatory { code: string; branche: string | null; valeur: string; unite: string | null; pays: string | null; exercice: number | null }
interface OpsControl {
  code: string;
  exigence: string;
  libelle: string;
  operation: string;
  tables: string[];
  parametres: AnalysisParam[];
  reglementaires: Regulatory[];
  manquants: string[];
  executions: { id: string; nom: string; statut: string; nb_lignes: number | null; cree_le: string }[];
}
interface Listing { pays: string | null; exercice: number; controles: OpsControl[] }

/** Contrôles des organismes de prévoyance sociale sur leurs fichiers (CIP-02 à CIP-05). */
export default function OpsControlsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Listing | null>(null);
  const [tables, setTables] = useState<Dataset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Listing>(`/audit-files/${file.id}/ops-controls`).then(setData), [file.id]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    api<Dataset[]>(`/engagements/${file.engagement_id}/datasets`).then((all) => setTables(all.filter((d) => d.statut === "pret"))).catch(() => setTables([]));
  }, [load, file.engagement_id]);
  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!data) return null;
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">{t("ops.intro", { pays: data.pays ?? t("ops.paysNonPrecise"), exercice: data.exercice })}</p>
      {data.controles.map((c) => <ControlCard key={c.code} file={file} control={c} tables={tables} />)}
    </div>
  );
}

function ControlCard({ file, control: c, tables }: { file: AuditFile; control: OpsControl; tables: Dataset[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [ids, setIds] = useState<string[]>(c.tables.map(() => ""));
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(c.parametres.map((p) => [p.nom, p.defaut == null ? "" : String(p.defaut)])));
  const [error, setError] = useState<string | null>(null);
  const schema = (i: number) => tables.find((d) => d.id === ids[i])?.schema ?? [];
  const label = (p: AnalysisParam) => t(`analyses.${c.operation}.params.${p.nom}`) + (p.requis && p.defaut == null ? "" : ` (${t("analyses.facultatif")})`);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const parametres = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
      const r = await post<{ dataset_id: string }>(`/audit-files/${file.id}/ops-controls/${c.code}`, { table_id: ids[0], seconde_table_id: ids[1] || null, parametres });
      navigate(`/missions/${file.engagement_id}/donnees/${r.dataset_id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const id = (s: string) => `ops-${c.code}-${s}`;
  return (
    <section className="carte space-y-3" aria-labelledby={id("titre")}>
      <h2 id={id("titre")} className="text-base font-semibold">{c.exigence} · {c.libelle}</h2>
      <p className="text-sm text-slate-600">{t(`analyses.${c.operation}.description`)}</p>
      {c.manquants.length > 0
        ? <Alert kind="info">{t("ops.manquants", { liste: c.manquants.join(", ") })}</Alert>
        : (
          <ul className="flex flex-wrap gap-2 text-xs" aria-label={t("ops.reglementaires")}>
            {c.reglementaires.map((r) => (
              <li key={`${r.code}-${r.branche}`} className="rounded bg-slate-100 px-2 py-0.5">
                {r.code}{r.branche ? ` (${r.branche})` : ""} = {r.valeur}{r.unite === "%" ? " %" : r.unite && r.unite !== "montant" ? ` ${r.unite}` : ""}
              </li>
            ))}
          </ul>
        )}
      {error && <Alert kind="erreur">{error}</Alert>}
      {file.peut_travailler && c.manquants.length === 0 && (
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
          {c.tables.map((name, i) => (
            <div key={name}>
              <label htmlFor={id(`table-${i}`)} className="etiquette">{name}</label>
              <select id={id(`table-${i}`)} className="champ" required value={ids[i]} onChange={(e) => setIds(ids.map((x, j) => (j === i ? e.target.value : x)))}>
                <option value="">—</option>
                {tables.map((d) => <option key={d.id} value={d.id}>{d.nom}</option>)}
              </select>
            </div>
          ))}
          {c.parametres.map((p) => (
            <div key={p.nom}>
              <label htmlFor={id(p.nom)} className="etiquette">{label(p)}</label>
              {p.type === "colonne" || p.type === "choix" ? (
                <select id={id(p.nom)} className="champ" required={p.requis && p.defaut == null} value={values[p.nom]} onChange={(e) => setValues({ ...values, [p.nom]: e.target.value })}>
                  <option value="">—</option>
                  {(p.type === "choix" ? p.choix : schema(p.table).map((col) => col.nom)).map((v) => <option key={v} value={v}>{p.type === "choix" ? t(`analyses.${c.operation}.choix.${v}`, { defaultValue: v }) : v}</option>)}
                </select>
              ) : (
                <input id={id(p.nom)} className="champ" type={p.type === "date" ? "date" : "text"} inputMode={p.type === "date" ? undefined : "decimal"} value={values[p.nom]} onChange={(e) => setValues({ ...values, [p.nom]: e.target.value })} />
              )}
            </div>
          ))}
          <div className="md:col-span-2"><button type="submit" className="btn-primaire">{t("ops.lancer")}</button></div>
        </form>
      )}
      {c.executions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold">{t("ops.executions")}</h3>
          <ul className="text-sm">
            {c.executions.map((x) => (
              <li key={x.id}>
                <Link className="text-marque-700 underline" to={`/missions/${file.engagement_id}/donnees/${x.id}`}>{x.nom}</Link>
                {" "}· {formatDate(x.cree_le)} · {x.statut === "pret" ? t("ops.lignes", { count: x.nb_lignes ?? 0 }) : x.statut}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
