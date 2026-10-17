import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, post, upload } from "../../api/client";
import type { DataSourceInfo, Dataset, Engagement, UploadInfo } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { formatDateHeure, formatNombre } from "../../lib/format";
import { can } from "../../lib/permissions";
import Alert from "../Alert";
import ImportWizard from "../data/ImportWizard";
import MacroPanel from "../data/MacroPanel";
import type { Preview, WizardOptions } from "../data/ImportWizard";

export const DS_BADGE: Record<string, string> = {
  en_cours: "bg-sky-100 text-sky-900",
  pret: "bg-green-100 text-green-900",
  erreur: "bg-red-100 text-red-900",
};

export default function DataTab({ mission }: { mission: Engagement }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canImport = mission.statut !== "cloturee" && can(user?.permissions, "data:analyze") && mission.mon_role !== null;
  const [rows, setRows] = useState<Dataset[]>([]);
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);
  const timer = useRef<number>();

  const load = useCallback(async () => {
    const list = await api<Dataset[]>(`/engagements/${mission.id}/datasets`);
    setRows(list);
    window.clearTimeout(timer.current);
    if (list.some((d) => d.statut === "en_cours")) timer.current = window.setTimeout(() => void load(), 2000);
  }, [mission.id]);

  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
    return () => window.clearTimeout(timer.current);
  }, [load]);

  return (
    <div className="space-y-4">
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {canImport && <ImportPanel missionId={mission.id} onImported={(text) => { setMessage({ kind: "succes", text }); void load(); }}
        onError={(text) => setMessage({ kind: "erreur", text })} />}
      {canImport && <MacroPanel tables={rows} onDone={(text, ok) => { setMessage({ kind: ok ? "succes" : "erreur", text }); void load(); }} />}
      <div className="carte overflow-x-auto p-0">
        {rows.length === 0 ? (
          <p className="p-6 text-sm text-slate-600">{t("donnees.aucune")}</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                {["colNom", "colSource", "colLignes", "colColonnes", "colStatut", "colDate"].map((k) => (
                  <th key={k} scope="col" className="px-4 py-2">{t(`donnees.${k}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {rows.map((d) => (
                <tr key={d.id}>
                  <td className="px-4 py-2">
                    {d.statut === "pret" ? (
                      <Link to={`/missions/${mission.id}/donnees/${d.id}`} className="text-marque-700 underline">{d.nom}</Link>
                    ) : d.nom}
                    <span className="ml-2 text-xs text-slate-500">{t(`donnees.kinds.${d.kind}`)}</span>
                    {d.erreur && <span className="block text-xs text-red-800">{d.erreur}</span>}
                  </td>
                  <td className="px-4 text-xs">{d.source_nom}</td>
                  <td className="px-4 text-right">{d.nb_lignes !== null ? formatNombre(d.nb_lignes) : "—"}</td>
                  <td className="px-4 text-right">{d.nb_colonnes ?? "—"}</td>
                  <td className="px-4">
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${DS_BADGE[d.statut]}`}>{t(`donnees.statuts.${d.statut}`)}</span>
                  </td>
                  <td className="px-4 text-xs text-slate-600">{formatDateHeure(d.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ImportPanel({ missionId, onImported, onError }: { missionId: string; onImported: (t: string) => void; onError: (t: string) => void }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"fichier" | "sql">("fichier");
  const [file, setFile] = useState<File | null>(null);
  const [nom, setNom] = useState("");
  const [busy, setBusy] = useState(false);
  const [sources, setSources] = useState<DataSourceInfo[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [requete, setRequete] = useState("SELECT ");
  const [wizard, setWizard] = useState<{ upload: UploadInfo; options: WizardOptions; apercu: Preview } | null>(null);

  useEffect(() => {
    api<DataSourceInfo[]>("/data-sources").then(setSources).catch(() => setSources([]));
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "fichier" && file) {
        // Étape 1 : dépôt puis détection ; l'import part depuis l'assistant.
        const up = await upload<UploadInfo>(`/engagements/${missionId}/uploads`, file);
        const det = await post<{ options: WizardOptions; apercu: Preview }>(`/uploads/${up.id}/detect`);
        setWizard({ upload: up, ...det });
        if (!nom) setNom(up.nom_fichier.replace(/\.[^.]+$/, ""));
        return;
      }
      await post(`/engagements/${missionId}/imports`, { nom, source_id: sourceId, requete });
      onImported(t("donnees.lance"));
      setNom("");
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const launch = async (options: WizardOptions) => {
    if (!wizard) return;
    try {
      await post(`/engagements/${missionId}/imports`, { nom: nom || wizard.upload.nom_fichier, upload_id: wizard.upload.id, options });
      onImported(t("donnees.lance"));
      setWizard(null);
      setFile(null);
      setNom("");
    } catch (err) {
      onError((err as Error).message);
    }
  };

  if (wizard) {
    return (
      <div className="carte space-y-3">
        <div>
          <label htmlFor="imp-nom-w" className="etiquette">{t("donnees.nom")}</label>
          <input id="imp-nom-w" className="champ" required value={nom} onChange={(e) => setNom(e.target.value)} />
        </div>
        <ImportWizard upload={wizard.upload} initial={wizard.options} initialPreview={wizard.apercu}
          onImport={launch} onCancel={() => setWizard(null)} />
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="carte space-y-3" aria-label={t("donnees.importer")}>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">{t("donnees.importer")}</h2>
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-1"><input type="radio" checked={mode === "fichier"} onChange={() => setMode("fichier")} />{t("donnees.fichier")}</label>
          <label className="flex items-center gap-1"><input type="radio" checked={mode === "sql"} onChange={() => setMode("sql")} />{t("donnees.depuisSource")}</label>
        </div>
      </div>
      {mode === "fichier" ? (
        <div>
          <label htmlFor="imp-file" className="etiquette">{t("donnees.fichier")}</label>
          <input id="imp-file" type="file" required className="mt-1 block text-sm" aria-describedby="imp-aide"
            accept=".csv,.txt,.tsv,.prn,.dat,.xlsx,.xlsm,.xls,.json,.ndjson,.jsonl,.parquet,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <p id="imp-aide" className="mt-1 text-xs text-slate-600">{t("donnees.fichierAide")}</p>
        </div>
      ) : sources.length === 0 ? (
        <p className="text-sm text-slate-600">{t("donnees.aucuneSource")}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label htmlFor="imp-src" className="etiquette">{t("donnees.source")}</label>
            <select id="imp-src" className="champ" required value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
              <option value="" />
              {sources.map((s) => <option key={s.id} value={s.id}>{s.nom} ({s.dialecte})</option>)}
            </select>
          </div>
          <div className="md:col-span-2">
            <label htmlFor="imp-sql" className="etiquette">{t("donnees.requete")}</label>
            <textarea id="imp-sql" rows={3} className="champ font-mono" required value={requete} onChange={(e) => setRequete(e.target.value)} />
          </div>
        </div>
      )}
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label htmlFor="imp-nom" className="etiquette">{t("donnees.nom")}</label>
          <input id="imp-nom" className="champ" required={mode === "sql"} value={nom} onChange={(e) => setNom(e.target.value)} />
        </div>
        <button type="submit" className="btn-primaire" disabled={busy}>{busy ? t("donnees.envoi") : t("donnees.lancer")}</button>
      </div>
    </form>
  );
}
