import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, put } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can, PERM } from "../../lib/permissions";
import Alert from "../Alert";

interface Section { titre?: string; texte: string; si?: string | null }
interface Template { id: string; code: string; nom: string; version: number; sections: Section[] }

/** Modèles de rapports paramétrables (REV-27) : texte des sections modifiable. */
export default function ReportTemplatesPanel() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const manager = can(user?.permissions, PERM.FRAMEWORKS_MANAGE);
  const [items, setItems] = useState<Template[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const load = useCallback(async () => setItems(await api<Template[]>("/report-templates")), []);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const current = items.find((x) => x.code === open);
  const setSection = (i: number, texte: string) => setItems(items.map((x) => (x.code === open ? { ...x, sections: x.sections.map((s, j) => (j === i ? { ...s, texte } : s)) } : x)));
  const save = async () => {
    if (!current) return;
    setError(null);
    try {
      const r = await put<Template>(`/report-templates/${current.code}`, { sections: current.sections });
      setInfo(t("modelesRapports.enregistre", { version: r.version }));
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="carte space-y-3" aria-labelledby="mr-titre">
      <h2 id="mr-titre" className="text-lg font-semibold">{t("modelesRapports.titre")}</h2>
      <p className="text-sm text-slate-600">{t("modelesRapports.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      {info && <Alert kind="succes">{info}</Alert>}
      <ul className="text-sm">{items.map((x) => <li key={x.code}><button type="button" className="underline" aria-expanded={open === x.code} onClick={() => setOpen(open === x.code ? null : x.code)}>{x.nom}</button> (v{x.version})</li>)}</ul>
      {current && (
        <div className="space-y-2">
          {current.sections.map((s, i) => (
            <div key={i}>
              <label htmlFor={`mr-${i}`} className="etiquette">{s.titre || t("modelesRapports.sansTitre")}{s.si && ` — ${t("modelesRapports.si", { condition: s.si })}`}</label>
              <textarea id={`mr-${i}`} rows={4} className="champ" readOnly={!manager} value={s.texte} onChange={(e) => setSection(i, e.target.value)} />
            </div>
          ))}
          {manager && <button type="button" className="btn-primaire" onClick={() => void save()}>{t("commun.enregistrer")}</button>}
        </div>
      )}
    </section>
  );
}
