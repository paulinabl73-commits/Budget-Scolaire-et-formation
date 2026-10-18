import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download, post, put } from "../../api/client";
import type { ApiError } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

interface Convention { objet: string; parties: string; modalites?: string | null; montant?: string | null }
export interface Opinion {
  statut: string; type_opinion: string; fondement: string | null; observations: string | null; conventions: Convention[];
  lieu: string | null; suggestion: string | null; signe_par?: string | null; signe_le?: string | null;
  emis_par?: string | null; emis_le?: string | null; empreinte?: string | null; archive_sha256?: string | null;
}
const TYPES = ["sans_reserve", "avec_reserve", "defavorable", "impossibilite"];
const DOCS = ["opinion", "conventions", "affirmation"];

/** Opinion et rapports paramétrables (REV-27). */
export default function OpinionPanel({ file, onLoaded, onLocked }: { file: AuditFile; onLoaded?: (o: Opinion) => void; onLocked?: () => void }) {
  const { t } = useTranslation();
  const [o, setO] = useState<Opinion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [points, setPoints] = useState<string[]>([]);
  const url = `/audit-files/${file.id}/opinion`;
  const fill = (x: Opinion) => { setO(x); onLoaded?.(x); };
  useEffect(() => {
    api<Opinion>(url).then(fill).catch((e: Error) => setError(e.message));
  }, [url]);
  if (!o) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const editable = file.peut_gerer && (o.statut === "a_rediger" || o.statut === "brouillon");
  const save = async () => {
    setError(null);
    try {
      fill(await put<Opinion>(url, { type_opinion: o.type_opinion, fondement: o.fondement || null, observations: o.observations || null, lieu: o.lieu || null, conventions: o.conventions }));
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const act = async (action: "sign" | "unsign" | "emit") => {
    setError(null);
    setPoints([]);
    try {
      const r = await post<Opinion>(`${url}/${action}`);
      fill(r);
      if (action === "emit") onLocked?.();
    } catch (e) {
      const err = e as ApiError;
      setError(err.message);
      setPoints(err.points ?? []);
    }
  };
  const set = (patch: Partial<Opinion>) => { setO({ ...o, ...patch }); setSaved(false); };
  const setConv = (i: number, k: keyof Convention, v: string) => set({ conventions: o.conventions.map((c, j) => (j === i ? { ...c, [k]: v } : c)) });

  return (
    <section className="carte space-y-3" aria-labelledby="op-titre">
      <h2 id="op-titre" className="text-base font-semibold">{t("opinion.titre")}</h2>
      <p className="text-sm">{t(`opinion.statuts.${o.statut}`)}{o.signe_le && ` · ${t("opinion.signeePar", { nom: o.signe_par, date: formatDateHeure(o.signe_le) })}`}{o.emis_le && ` · ${t("opinion.emisePar", { nom: o.emis_par, date: formatDateHeure(o.emis_le) })}`}</p>
      {o.suggestion && <p className="text-sm text-slate-600">{t("opinion.suggestion", { type: t(`opinion.types.${o.suggestion}`) })}</p>}
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="grid gap-2 md:grid-cols-3">
        <div><label htmlFor="op-type" className="etiquette">{t("opinion.type")}</label>
          <select id="op-type" className="champ" disabled={!editable} value={o.type_opinion} onChange={(e) => set({ type_opinion: e.target.value })}>{TYPES.map((x) => <option key={x} value={x}>{t(`opinion.types.${x}`)}</option>)}</select></div>
        <div><label htmlFor="op-lieu" className="etiquette">{t("opinion.lieu")}</label><input id="op-lieu" className="champ" readOnly={!editable} value={o.lieu ?? ""} onChange={(e) => set({ lieu: e.target.value })} /></div>
      </div>
      {o.type_opinion !== "sans_reserve" && (
        <div><label htmlFor="op-fond" className="etiquette">{t("opinion.fondement")}</label><textarea id="op-fond" rows={3} className="champ" readOnly={!editable} value={o.fondement ?? ""} onChange={(e) => set({ fondement: e.target.value })} /></div>
      )}
      <div><label htmlFor="op-obs" className="etiquette">{t("opinion.observations")}</label><textarea id="op-obs" rows={2} className="champ" readOnly={!editable} value={o.observations ?? ""} onChange={(e) => set({ observations: e.target.value })} /></div>
      <fieldset className="space-y-2">
        <legend className="etiquette">{t("opinion.conventions")}</legend>
        {o.conventions.map((c, i) => (
          <div key={i} className="grid gap-2 md:grid-cols-4">
            {(["objet", "parties", "modalites", "montant"] as const).map((k) => <input key={k} className="champ" aria-label={t(`opinion.convention.${k}`, { n: i + 1 })} placeholder={t(`opinion.convention.${k}`, { n: i + 1 })} readOnly={!editable} value={c[k] ?? ""} onChange={(e) => setConv(i, k, e.target.value)} />)}
          </div>
        ))}
        {editable && <button type="button" className="text-sm underline" onClick={() => set({ conventions: [...o.conventions, { objet: "", parties: "" }] })}>{t("opinion.ajouterConvention")}</button>}
      </fieldset>
      {editable && <button type="button" className="btn-primaire" onClick={() => void save()}>{saved ? t("opinion.enregistree") : t("commun.enregistrer")}</button>}
      {o.statut !== "a_rediger" && (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-2">
          {DOCS.flatMap((d) => ["pdf", "docx"].map((fmt) => (
            <button key={`${d}-${fmt}`} type="button" className="btn-secondaire" onClick={() => void download(`/audit-files/${file.id}/reports/${d}?format=${fmt}`, undefined, `${d}.${fmt}`).catch((e: Error) => setError(e.message))}>
              {t(`opinion.docs.${d}`)} ({fmt === "pdf" ? "PDF" : "Word"})
            </button>
          )))}
        </div>
      )}
      {(file.peut_signer || o.statut === "emis") && o.statut !== "a_rediger" && (
        <div className="space-y-2 border-t border-slate-100 pt-2">
          <h3 className="font-semibold">{t("opinion.signature")}</h3>
          {o.empreinte && <p className="break-all text-xs text-slate-600">{t("opinion.empreinte", { valeur: o.empreinte })}</p>}
          {points.length > 0 && <ul className="list-disc pl-5 text-sm text-red-700">{points.map((p) => <li key={p}>{p}</li>)}</ul>}
          <div className="flex flex-wrap gap-2">
            {file.peut_signer && o.statut === "brouillon" && <button type="button" className="btn-primaire" onClick={() => void act("sign")}>{t("opinion.signer")}</button>}
            {file.peut_signer && o.statut === "signe" && (
              <>
                <button type="button" className="btn-primaire" onClick={() => { if (window.confirm(t("opinion.confirmerEmission"))) void act("emit"); }}>{t("opinion.emettre")}</button>
                <button type="button" className="btn-secondaire" onClick={() => void act("unsign")}>{t("opinion.annulerSignature")}</button>
              </>
            )}
            {o.statut === "emis" && <button type="button" className="btn-secondaire" onClick={() => void download(`${url}/archive`, undefined, "rapport_emis.pdf").catch((e: Error) => setError(e.message))}>{t("opinion.archive")}</button>}
          </div>
          {o.archive_sha256 && <p className="break-all text-xs text-slate-600">{t("opinion.empreinteArchive", { valeur: o.archive_sha256 })}</p>}
        </div>
      )}
    </section>
  );
}
