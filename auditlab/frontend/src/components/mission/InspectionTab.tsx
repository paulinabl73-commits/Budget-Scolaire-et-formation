import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, download, post, put } from "../../api/client";
import type { Engagement } from "../../api/types";
import { formatDate, formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

interface Report {
  id: string;
  version: "provisoire" | "definitif";
  titre: string;
  emis_le: string;
  sha256: string;
  destinataire: string | null;
  date_limite_reponse: string | null;
  reponse_organisme: string | null;
  reponse_recue_le: string | null;
}
interface Previous {
  finding_id: string;
  mission: string;
  reference: string;
  titre: string;
  criticite: string;
  recommandation: string | null;
  plans: string[];
  suivi: { statut: string; commentaire: string | null } | null;
}
interface Inspection {
  rapports: Report[];
  constats: { id: string; reference: string; titre: string; criticite: string; statut: string; reponse_position: string | null }[];
  recommandations_anterieures: Previous[];
  blocages: { provisoire: string[]; definitif: string[] };
  peut_gerer: boolean;
}
const FOLLOW_UPS = ["mise_en_oeuvre", "partielle", "non_mise_en_oeuvre", "sans_objet"] as const;

/** Mission d'inspection CIPRES (CIP-08) : rapports provisoire et définitif, suivi des recommandations. */
export default function InspectionTab({ mission }: { mission: Engagement }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Inspection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState("");
  const [answer, setAnswer] = useState({ reponse: "", recue_le: "" });
  const [recipient, setRecipient] = useState(t("inspection.destinataireDefaut"));
  const url = `/engagements/${mission.id}/inspection`;
  const load = useCallback(() => api<Inspection>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const reports = Object.fromEntries(data.rapports.map((r) => [r.version, r])) as Partial<Record<Report["version"], Report>>;
  const provisional = reports.provisoire;
  const final = reports.definitif;
  const submit = (fn: () => Promise<unknown>) => (e: FormEvent) => {
    e.preventDefault();
    void run(fn);
  };
  return (
    <div className="space-y-4">
      {error && <Alert kind="erreur">{error}</Alert>}
      <section className="carte space-y-2" aria-labelledby="insp-suivi">
        <h2 id="insp-suivi" className="text-base font-semibold">{t("inspection.suivi.titre")}</h2>
        {data.recommandations_anterieures.length === 0 ? <p className="text-sm text-slate-600">{t("inspection.suivi.aucune")}</p> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {data.recommandations_anterieures.map((r) => (
              <FollowUp key={r.finding_id} item={r} disabled={!data.peut_gerer || !!final} onSave={(body) => run(() => put(`${url}/follow-ups/${r.finding_id}`, body))} />
            ))}
          </ul>
        )}
      </section>
      <section className="carte space-y-2" aria-labelledby="insp-constats">
        <h2 id="insp-constats" className="text-base font-semibold">{t("inspection.constats")}</h2>
        <ul className="text-sm">
          {data.constats.map((f) => (
            <li key={f.id}>
              <span className="font-mono">{f.reference}</span> {f.titre} · {t(`constats.criticites.${f.criticite}`)} · {t(`constats.statuts.${f.statut}`)}
              {f.reponse_position && ` · ${t(`contradictoire.positions.${f.reponse_position}`)}`}
            </li>
          ))}
        </ul>
      </section>
      <section className="carte space-y-3" aria-labelledby="insp-rapports">
        <h2 id="insp-rapports" className="text-base font-semibold">{t("inspection.rapports")}</h2>
        {data.rapports.map((r) => (
          <div key={r.id} className="rounded border border-slate-200 p-3 text-sm">
            <p className="font-medium">{r.titre}</p>
            <p className="text-slate-600">
              {t("inspection.emisLe", { date: formatDateHeure(r.emis_le) })}
              {r.date_limite_reponse && ` · ${t("inspection.limite", { date: formatDate(r.date_limite_reponse) })}`}
              {r.destinataire && ` · ${r.destinataire}`}
            </p>
            <p className="break-all font-mono text-xs text-slate-600">SHA-256 {r.sha256}</p>
            <div className="mt-1 flex gap-3">
              {(["pdf", "docx"] as const).map((fmt) => (
                <button key={fmt} type="button" className="underline" onClick={() => void run(() => download(`/inspection-reports/${r.id}/export?format=${fmt}`, undefined, `rapport.${fmt}`))}>
                  {t(`inspection.export.${fmt}`)}
                </button>
              ))}
            </div>
            {r.reponse_organisme && <p className="mt-2 whitespace-pre-line">{t("inspection.reponseRecue", { date: formatDate(r.reponse_recue_le ?? "") })} {r.reponse_organisme}</p>}
          </div>
        ))}
        {data.peut_gerer && !provisional && (
          <form onSubmit={submit(() => post(`${url}/provisional`, { date_limite_reponse: limit }))} className="space-y-2">
            <Blockers items={data.blocages.provisoire} />
            <label htmlFor="insp-limite" className="etiquette">{t("inspection.dateLimite")}</label>
            <input id="insp-limite" type="date" className="champ" required value={limit} onChange={(e) => setLimit(e.target.value)} />
            <button type="submit" className="btn-primaire" disabled={data.blocages.provisoire.length > 0}>{t("inspection.emettreProvisoire")}</button>
          </form>
        )}
        {data.peut_gerer && provisional && !final && (
          <>
            <form onSubmit={submit(() => put(`${url}/response`, answer))} className="space-y-2">
              <h3 className="text-sm font-semibold">{t("inspection.reponseGenerale")}</h3>
              <label htmlFor="insp-rep" className="etiquette">{t("inspection.reponse")}</label>
              <textarea id="insp-rep" className="champ" rows={4} required value={answer.reponse} onChange={(e) => setAnswer({ ...answer, reponse: e.target.value })} />
              <label htmlFor="insp-recue" className="etiquette">{t("inspection.recueLe")}</label>
              <input id="insp-recue" type="date" className="champ" required value={answer.recue_le} onChange={(e) => setAnswer({ ...answer, recue_le: e.target.value })} />
              <button type="submit" className="btn-secondaire">{t("inspection.enregistrerReponse")}</button>
            </form>
            <form onSubmit={submit(() => post(`${url}/final`, { destinataire: recipient }))} className="space-y-2">
              <h3 className="text-sm font-semibold">{t("inspection.definitif")}</h3>
              <Blockers items={data.blocages.definitif} />
              <label htmlFor="insp-dest" className="etiquette">{t("inspection.destinataire")}</label>
              <input id="insp-dest" className="champ" required value={recipient} onChange={(e) => setRecipient(e.target.value)} />
              <button type="submit" className="btn-primaire" disabled={data.blocages.definitif.length > 0}>{t("inspection.emettreDefinitif")}</button>
            </form>
          </>
        )}
      </section>
    </div>
  );
}

function Blockers({ items }: { items: string[] }) {
  const { t } = useTranslation();
  if (items.length === 0) return null;
  return (
    <Alert kind="info">
      {t("inspection.blocages")}
      <ul className="list-disc pl-5">{items.map((b) => <li key={b}>{b}</li>)}</ul>
    </Alert>
  );
}

function FollowUp({ item, disabled, onSave }: { item: Previous; disabled: boolean; onSave: (body: { statut: string; commentaire: string | null }) => Promise<void> }) {
  const { t } = useTranslation();
  const [statut, setStatut] = useState(item.suivi?.statut ?? "");
  const [comment, setComment] = useState(item.suivi?.commentaire ?? "");
  const id = `suivi-${item.finding_id}`;
  return (
    <li className="space-y-1 py-2">
      <p>
        <span className="font-mono">{item.mission} · {item.reference}</span> {item.recommandation ?? item.titre}
        <span className="text-slate-600"> · {t("inspection.suivi.plans", { liste: item.plans.map((p) => t(`plans.statuts.${p}`, { defaultValue: p })).join(", ") || "—" })}</span>
      </p>
      <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); void onSave({ statut, commentaire: comment || null }); }}>
        <div>
          <label htmlFor={id} className="etiquette">{t("inspection.suivi.statut")}</label>
          <select id={id} className="champ" required disabled={disabled} value={statut} onChange={(e) => setStatut(e.target.value)}>
            <option value="">—</option>
            {FOLLOW_UPS.map((s) => <option key={s} value={s}>{t(`inspection.suivi.statuts.${s}`)}</option>)}
          </select>
        </div>
        <div className="min-w-64 flex-1">
          <label htmlFor={`${id}-c`} className="etiquette">{t("inspection.suivi.commentaire")}</label>
          <input id={`${id}-c`} className="champ" disabled={disabled} value={comment} onChange={(e) => setComment(e.target.value)} />
        </div>
        {!disabled && <button type="submit" className="btn-secondaire">{t("commun.enregistrer")}</button>}
      </form>
    </li>
  );
}
