import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, put } from "../../api/client";
import type { AuditFile } from "../../api/types";
import Alert from "../Alert";

interface Point { code: string; libelle: string; reponse: string | null; commentaire: string | null }
interface Checklist { normes: { norme: string; applicable: boolean; points: Point[] }[]; total: number; repondus: number; informations_manquantes: number }

/** Check-list des informations à fournir en annexe, par norme (IFR-04). */
export default function IfrsChecklistPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Checklist | null>(null);
  const [all, setAll] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/ifrs/checklist`;
  useEffect(() => {
    api<Checklist>(url).then(setData).catch((e: Error) => setError(e.message));
  }, [url]);
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const answer = async (p: Point, reponse: string) => {
    setError(null);
    try {
      setData(await put<Checklist>(`${url}/${encodeURIComponent(p.code)}`, { reponse, commentaire: notes[p.code] ?? p.commentaire ?? null }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="carte space-y-3" aria-labelledby="ick-titre">
      <h2 id="ick-titre" className="text-base font-semibold">{t("checklistIfrs.titre")}</h2>
      <p className="text-sm" role="status">{t("checklistIfrs.avancement", { repondus: data.repondus, total: data.total, manquantes: data.informations_manquantes })}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />{t("checklistIfrs.toutes")}</label>
      {data.normes.filter((n) => all || n.applicable).map((n) => (
        <fieldset key={n.norme} className="space-y-1">
          <legend className="font-semibold">{n.norme}</legend>
          {n.points.map((p) => (
            <div key={p.code} className="grid gap-2 border-b border-slate-100 py-1 text-sm md:grid-cols-[1fr_auto_16rem]">
              <span>{p.libelle}</span>
              <span className="flex gap-2" role="radiogroup" aria-label={p.libelle}>
                {["oui", "non", "na"].map((r) => (
                  <label key={r} className="flex items-center gap-1"><input type="radio" name={`ick-${p.code}`} disabled={!file.peut_travailler} checked={p.reponse === r} onChange={() => void answer(p, r)} />{t(`checklistIfrs.reponses.${r}`)}</label>
                ))}
              </span>
              <input className="champ" aria-label={t("checklistIfrs.commentaire", { point: p.libelle })} placeholder={t("checklistIfrs.commentairePlaceholder")} readOnly={!file.peut_travailler}
                value={notes[p.code] ?? p.commentaire ?? ""} onChange={(e) => setNotes({ ...notes, [p.code]: e.target.value })} onBlur={() => p.reponse && notes[p.code] !== undefined && void answer(p, p.reponse)} />
            </div>
          ))}
        </fieldset>
      ))}
    </section>
  );
}
