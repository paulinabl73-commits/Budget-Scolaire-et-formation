import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { AuditFile, Engagement, FrameworkSummary } from "../../api/types";
import { formatDate } from "../../lib/format";
import Alert from "../Alert";

interface Normative {
  id: string;
  libelle: string;
  actif: boolean;
}

const DEVISES = ["XOF", "XAF", "EUR", "USD", "GNF", "CDF"];

interface Transmitted {
  id: string;
  client: string;
  exercice: number;
  transmis_le: string;
  repris: boolean;
}

/** Dossiers de révision de la mission (Module 5, REV-02 à REV-04). */
export default function RevisionTab({ mission }: { mission: Engagement }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [files, setFiles] = useState<AuditFile[]>([]);
  const [frameworks, setFrameworks] = useState<FrameworkSummary[]>([]);
  const [normatives, setNormatives] = useState<Normative[]>([]);
  const year = new Date().getFullYear() - 1;
  const [form, setForm] = useState({ exercice: String(year), date_debut: `${year}-01-01`, date_fin: `${year}-12-31`, framework_id: "", ifrs_framework_id: "", normative_id: "", devise: "XOF" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<AuditFile[]>(`/engagements/${mission.id}/audit-files`).then(setFiles), [mission.id]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    api<FrameworkSummary[]>("/frameworks").then((f) => setFrameworks(f.filter((x) => x.actif))).catch(() => setFrameworks([]));
    api<Normative[]>("/normative-frameworks").then((n) => setNormatives(n.filter((x) => x.actif))).catch(() => setNormatives([]));
  }, [load]);
  const canCreate = mission.peut_gerer && mission.statut !== "cloturee";
  // RCO-27 : dossiers de clôture transmis à la mission par l'expert-comptable de l'entité.
  const [transmitted, setTransmitted] = useState<Transmitted[]>([]);
  useEffect(() => {
    if (canCreate && mission.mode === "audit")
      api<Transmitted[]>(`/engagements/${mission.id}/transmitted-closings`).then(setTransmitted).catch(() => setTransmitted([]));
  }, [canCreate, mission.id, mission.mode]);
  const takeOver = async (closingId: string) => {
    try {
      const f = await post<AuditFile>(`/engagements/${mission.id}/audit-files/from-closing`, { closing_id: closingId });
      navigate(`/missions/${mission.id}/revision/${f.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const f = await post<AuditFile>(`/engagements/${mission.id}/audit-files`, {
        ...form,
        exercice: Number(form.exercice),
        ifrs_framework_id: form.ifrs_framework_id || null,
        normative_id: form.normative_id || null,
      });
      navigate(`/missions/${mission.id}/revision/${f.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="space-y-4">
      {error && <Alert kind="erreur">{error}</Alert>}
      <section className="carte overflow-x-auto p-0">
        {files.length === 0 ? (
          <p className="p-6 text-sm text-slate-600">{t("revision.aucun")}</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>{["exercice", "entite", "referentiel", "devise", "cadre", "statut"].map((k) => <th key={k} scope="col" className="px-4 py-2">{t(`revision.col.${k}`)}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {files.map((f) => (
                <tr key={f.id}>
                  <td className="px-4 py-2">
                    <Link to={`/missions/${mission.id}/revision/${f.id}`} className="font-semibold text-marque-700 underline">{f.exercice}</Link>
                    <div className="text-xs text-slate-600">{formatDate(f.date_debut)} – {formatDate(f.date_fin)}</div>
                  </td>
                  <td className="px-4 py-2">{f.entite}</td>
                  <td className="px-4 py-2">{f.referentiel}{f.referentiel_ifrs && ` + ${f.referentiel_ifrs}`}</td>
                  <td className="px-4 py-2">{f.devise}</td>
                  <td className="px-4 py-2">{f.cadre_normatif ?? "—"}</td>
                  <td className="px-4 py-2">{t(`revision.statuts.${f.statut}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {transmitted.some((c) => !c.repris) && (
        <section className="carte space-y-2" aria-labelledby="clotures-transmises">
          <h2 id="clotures-transmises" className="text-base font-semibold">{t("revision.transmis.titre")}</h2>
          <p className="text-sm text-slate-700">{t("revision.transmis.aide")}</p>
          <ul className="space-y-1 text-sm">
            {transmitted.filter((c) => !c.repris).map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-2">
                <span>{t("revision.transmis.ligne", { client: c.client, exercice: c.exercice, le: formatDate(c.transmis_le) })}</span>
                <button type="button" className="btn-secondaire" onClick={() => void takeOver(c.id)}>{t("revision.transmis.reprendre")}</button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {canCreate && (
        <form onSubmit={create} className="carte space-y-3" aria-labelledby="nouveau-dossier">
          <h2 id="nouveau-dossier" className="text-base font-semibold">{t("revision.nouveau")}</h2>
          {!mission.entity_id && <Alert kind="info">{t("revision.sansEntite")}</Alert>}
          <div className="grid gap-3 md:grid-cols-4">
            <div><label htmlFor="rv-ex" className="etiquette">{t("revision.col.exercice")}</label><input id="rv-ex" type="number" className="champ" required value={form.exercice} onChange={set("exercice")} /></div>
            <div><label htmlFor="rv-deb" className="etiquette">{t("revision.debut")}</label><input id="rv-deb" type="date" className="champ" required value={form.date_debut} onChange={set("date_debut")} /></div>
            <div><label htmlFor="rv-fin" className="etiquette">{t("revision.fin")}</label><input id="rv-fin" type="date" className="champ" required value={form.date_fin} onChange={set("date_fin")} /></div>
            <div>
              <label htmlFor="rv-dev" className="etiquette">{t("revision.col.devise")}</label>
              <select id="rv-dev" className="champ" value={form.devise} onChange={set("devise")}>{DEVISES.map((d) => <option key={d} value={d}>{t(`devises.${d}`, { defaultValue: d })}</option>)}</select>
            </div>
            <div>
              <label htmlFor="rv-fw" className="etiquette">{t("revision.principal")}</label>
              <select id="rv-fw" className="champ" required value={form.framework_id} onChange={set("framework_id")}>
                <option value="">—</option>
                {frameworks.filter((f) => f.code !== "IFRS").map((f) => <option key={f.id} value={f.id}>{f.code} {f.version} ({f.pays})</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="rv-ifrs" className="etiquette">{t("revision.ifrs")}</label>
              <select id="rv-ifrs" className="champ" value={form.ifrs_framework_id} onChange={set("ifrs_framework_id")}>
                <option value="">{t("revision.sansIfrs")}</option>
                {frameworks.filter((f) => f.code === "IFRS").map((f) => <option key={f.id} value={f.id}>{f.code} {f.version}</option>)}
              </select>
            </div>
            <div className="md:col-span-2">
              <label htmlFor="rv-nf" className="etiquette">{t("revision.col.cadre")}</label>
              <select id="rv-nf" className="champ" value={form.normative_id} onChange={set("normative_id")}>
                <option value="">—</option>
                {normatives.map((n) => <option key={n.id} value={n.id}>{n.libelle}</option>)}
              </select>
            </div>
          </div>
          <button type="submit" className="btn-primaire">{t("revision.creer")}</button>
        </form>
      )}
    </div>
  );
}
