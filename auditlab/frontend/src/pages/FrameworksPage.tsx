import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, download, patch, post, upload } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import CurrenciesPanel from "../components/revision/CurrenciesPanel";
import DsfModelsPanel from "../components/revision/DsfModelsPanel";
import RegulatoryParametersPanel from "../components/revision/RegulatoryParametersPanel";
import ReportTemplatesPanel from "../components/revision/ReportTemplatesPanel";
import ProgramsLibraryPanel from "../components/revision/ProgramsLibraryPanel";
import { formatDate, formatNombre } from "../lib/format";
import { can, PERM } from "../lib/permissions";

interface Framework {
  id: string;
  code: string;
  version: string;
  libelle: string;
  pays: string;
  date_effet: string;
  actif: boolean;
  source: string | null;
  nb_comptes: number;
  nb_postes: number;
}

interface Detail extends Framework {
  comptes: { numero: string; libelle: string; classe: number }[];
  postes: { etat: string; code: string; libelle: string; racines: { racine: string; sens: string | null }[]; formule: string | null; niveau: number }[];
  parametres: { code: string; libelle: string; valeur: string; unite: string | null; pays: string | null; exercice: number | null }[];
  ratios: { code: string; libelle: string; formule: string }[];
}

interface Normative {
  id: string;
  code: string;
  libelle: string;
  description: string | null;
  actif: boolean;
}

/** Référentiels comptables versionnés (REV-01), cadres normatifs (REV-03), devises et cours (REV-07). */
export default function FrameworksPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const manager = can(user?.permissions, PERM.FRAMEWORKS_MANAGE);
  const [rows, setRows] = useState<Framework[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tab, setTab] = useState<"postes" | "comptes" | "parametres" | "ratios">("postes");
  const [normatives, setNormatives] = useState<Normative[]>([]);
  const [nf, setNf] = useState({ code: "", libelle: "", description: "" });
  const [message, setMessage] = useState<{ kind: "succes" | "erreur"; text: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setRows(await api<Framework[]>("/frameworks"));
    setNormatives(await api<Normative[]>("/normative-frameworks"));
  }, []);
  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const importFile = async (file: File) => {
    try {
      const fw = await upload<Framework>("/frameworks/import", file);
      setMessage({ kind: "succes", text: t("referentiels.importe", { code: fw.code, version: fw.version }) });
      await load();
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    }
  };
  const exportFile = (fw: Framework) =>
    download(`/frameworks/${fw.id}/export`, undefined, `referentiel_${fw.code}_${fw.version}.xlsx`).catch((e: Error) =>
      setMessage({ kind: "erreur", text: e.message }),
    );
  const addNormative = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await post("/normative-frameworks", { ...nf, description: nf.description || null });
      setNf({ code: "", libelle: "", description: "" });
      await load();
    } catch (err) {
      setMessage({ kind: "erreur", text: (err as Error).message });
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("referentiels.titre")}</h1>
        <p className="text-slate-600">{t("referentiels.intro")}</p>
      </header>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {manager && (
        <div>
          <input ref={input} type="file" accept=".xlsx" className="sr-only" aria-label={t("referentiels.importer")}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void importFile(f); e.target.value = ""; }} />
          <button type="button" className="btn-primaire" onClick={() => input.current?.click()}>{t("referentiels.importer")}</button>
          <p className="mt-1 text-xs text-slate-600">{t("referentiels.aideImport")}</p>
        </div>
      )}
      <section className="carte overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>{["code", "version", "pays", "effet", "comptes", "postes", "etat", "actions"].map((k) => <th key={k} scope="col" className="px-4 py-2">{t(`referentiels.col.${k}`)}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {rows.map((f) => (
              <tr key={f.id}>
                <td className="px-4 py-2 font-semibold">{f.code}</td>
                <td className="px-4 py-2">
                  <button type="button" className="text-marque-700 underline" onClick={async () => setDetail(await api<Detail>(`/frameworks/${f.id}`))}>{f.version}</button>
                  <div className="text-xs text-slate-600">{f.libelle}</div>
                </td>
                <td className="px-4 py-2">{f.pays}</td>
                <td className="px-4 py-2">{formatDate(f.date_effet)}</td>
                <td className="px-4 py-2">{formatNombre(f.nb_comptes)}</td>
                <td className="px-4 py-2">{formatNombre(f.nb_postes)}</td>
                <td className="px-4 py-2">{f.actif ? t("referentiels.actif") : t("referentiels.inactif")}</td>
                <td className="flex flex-wrap gap-2 px-4 py-2">
                  <button type="button" className="btn-secondaire py-1 text-xs" onClick={() => void exportFile(f)}>{t("referentiels.exporter")}</button>
                  {manager && (
                    <button type="button" className="btn-secondaire py-1 text-xs" onClick={async () => { await patch(`/frameworks/${f.id}`, { actif: !f.actif }); await load(); }}>
                      {f.actif ? t("referentiels.desactiver") : t("referentiels.activer")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {detail && (
        <section className="carte space-y-3" aria-labelledby="ref-detail">
          <h2 id="ref-detail" className="text-lg font-semibold">{detail.code} {detail.version} — {detail.libelle}</h2>
          {detail.source && <p className="text-sm text-slate-600">{detail.source}</p>}
          <nav className="flex gap-1 border-b border-slate-200" aria-label={t("referentiels.rubriques")}>
            {(["postes", "comptes", "parametres", "ratios"] as const).map((k) => (
              <button key={k} type="button" aria-current={k === tab ? "page" : undefined} onClick={() => setTab(k)}
                className={`-mb-px border-b-2 px-3 py-1 text-sm ${k === tab ? "border-marque-600 text-marque-700" : "border-transparent text-slate-600"}`}>
                {t(`referentiels.onglets.${k}`)}
              </button>
            ))}
          </nav>
          <div className="max-h-[32rem] overflow-auto">
            <table className="w-full text-left text-xs">
              <tbody className="divide-y divide-slate-100">
                {tab === "postes" && detail.postes.map((p) => (
                  <tr key={p.code} className={p.niveau === 0 ? "font-semibold" : ""}>
                    <td className="py-1 pr-2 text-slate-600">{t(`referentiels.etats.${p.etat}`, { defaultValue: p.etat })}</td>
                    <td className="py-1 pr-2 font-mono">{p.code}</td>
                    <td className="py-1 pr-2">{p.libelle}</td>
                    <td className="py-1 pr-2 font-mono">{p.racines.map((r) => r.racine + (r.sens ? ` (${t(`referentiels.sens.${r.sens}`)})` : "")).join(", ")}</td>
                    <td className="py-1 font-mono">{p.formule}</td>
                  </tr>
                ))}
                {tab === "comptes" && detail.comptes.map((c) => (
                  <tr key={c.numero}><td className="py-1 pr-2 font-mono">{c.numero}</td><td className="py-1">{c.libelle}</td></tr>
                ))}
                {tab === "parametres" && (detail.parametres.length === 0
                  ? <tr><td className="py-2 text-slate-600">{t("referentiels.aucunParametre")}</td></tr>
                  : detail.parametres.map((p) => (
                    <tr key={`${p.code}-${p.pays}-${p.exercice}`}><td className="py-1 pr-2 font-mono">{p.code}</td><td className="py-1 pr-2">{p.libelle}</td><td className="py-1 pr-2">{p.valeur} {p.unite}</td><td className="py-1">{p.pays} {p.exercice}</td></tr>
                  )))}
                {tab === "ratios" && detail.ratios.map((r) => (
                  <tr key={r.code}><td className="py-1 pr-2">{r.libelle}</td><td className="py-1 font-mono">{r.formule}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="carte space-y-3" aria-labelledby="cadres-titre">
        <h2 id="cadres-titre" className="text-lg font-semibold">{t("referentiels.cadres")}</h2>
        <ul className="text-sm">
          {normatives.map((n) => <li key={n.id}><strong>{n.libelle}</strong>{n.description && ` — ${n.description}`}</li>)}
        </ul>
        {manager && (
          <form onSubmit={addNormative} className="grid gap-2 md:grid-cols-4">
            <div>
              <label htmlFor="nf-code" className="etiquette">{t("referentiels.cadreCode")}</label>
              <input id="nf-code" className="champ" required pattern="[a-z0-9_]+" value={nf.code} onChange={(e) => setNf({ ...nf, code: e.target.value })} />
            </div>
            <div>
              <label htmlFor="nf-lib" className="etiquette">{t("referentiels.cadreLibelle")}</label>
              <input id="nf-lib" className="champ" required value={nf.libelle} onChange={(e) => setNf({ ...nf, libelle: e.target.value })} />
            </div>
            <div>
              <label htmlFor="nf-desc" className="etiquette">{t("referentiels.cadreDescription")}</label>
              <input id="nf-desc" className="champ" value={nf.description} onChange={(e) => setNf({ ...nf, description: e.target.value })} />
            </div>
            <div className="flex items-end"><button type="submit" className="btn-primaire">{t("referentiels.ajouterCadre")}</button></div>
          </form>
        )}
      </section>
      <CurrenciesPanel />
      <RegulatoryParametersPanel />
      <ProgramsLibraryPanel />
      <DsfModelsPanel />
      <ReportTemplatesPanel />
    </div>
  );
}
