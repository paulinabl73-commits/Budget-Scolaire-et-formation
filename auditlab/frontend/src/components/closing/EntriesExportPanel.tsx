import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download } from "../../api/client";
import type { AuditFile } from "../../api/types";
import Alert from "../Alert";

/** Export des écritures acceptées au format du logiciel du client (RCO-17). */
export default function EntriesExportPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [formats, setFormats] = useState<{ code: string; libelle: string }[]>([]);
  const [format, setFormat] = useState("generique");
  const [journal, setJournal] = useState("OD");
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<{ code: string; libelle: string }[]>("/entry-export-formats").then(setFormats).catch(() => setFormats([]));
  }, []);
  const run = async () => {
    setError(null);
    try {
      await download(`/audit-files/${file.id}/entries-export?format=${format}&journal=${encodeURIComponent(journal)}&toutes=${all}`, undefined, "ecritures.csv");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="carte space-y-3" aria-labelledby="ex-titre">
      <h2 id="ex-titre" className="text-base font-semibold">{t("exportEcritures.titre")}</h2>
      <p className="text-sm text-slate-600">{t("exportEcritures.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="ex-format" className="etiquette">{t("exportEcritures.format")}</label>
          <select id="ex-format" className="champ" value={format} onChange={(e) => setFormat(e.target.value)}>
            {formats.map((f) => <option key={f.code} value={f.code}>{f.libelle}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="ex-journal" className="etiquette">{t("exportEcritures.journal")}</label>
          <input id="ex-journal" className="champ w-24" value={journal} onChange={(e) => setJournal(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />{t("exportEcritures.toutes")}</label>
        <button type="button" className="btn-primaire" onClick={() => void run()}>{t("exportEcritures.exporter")}</button>
      </div>
    </section>
  );
}
