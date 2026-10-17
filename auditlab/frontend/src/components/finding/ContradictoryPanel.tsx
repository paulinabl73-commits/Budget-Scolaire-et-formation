import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../../api/client";
import type { Auditee, Finding } from "../../api/types";
import { formatDate, formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

/** Phase contradictoire (CON-04) : envoi à l'audité, réponse, validation. */
export default function ContradictoryPanel({ finding, canSend, canValidate, onChange }: {
  finding: Finding;
  canSend: boolean;
  canValidate: boolean;
  onChange: (f: Finding) => void;
}) {
  const { t } = useTranslation();
  const [auditees, setAuditees] = useState<Auditee[]>([]);
  const [audite, setAudite] = useState("");
  const [limite, setLimite] = useState("");
  const [commentaire, setCommentaire] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (canSend && finding.statut === "brouillon") api<Auditee[]>("/auditees").then(setAuditees).catch(() => setAuditees([]));
  }, [canSend, finding.statut]);

  const act = async (path: string, body: unknown) => {
    setError(null);
    try {
      onChange(await post<Finding>(`/findings/${finding.id}/${path}`, body));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const lateNoAnswer = finding.statut === "envoye" && !!finding.date_limite_reponse && finding.date_limite_reponse < new Date().toISOString().slice(0, 10);

  return (
    <section className="carte space-y-3" aria-labelledby="contradictoire-titre">
      <h2 id="contradictoire-titre" className="text-base font-semibold">{t("contradictoire.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {finding.statut === "brouillon" && !canSend && <p className="text-sm text-slate-600">{t("contradictoire.brouillon")}</p>}
      {finding.statut === "brouillon" && canSend && (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="ct-audite" className="etiquette">{t("contradictoire.destinataire")}</label>
            <select id="ct-audite" className="champ mt-0" value={audite} onChange={(e) => setAudite(e.target.value)}>
              <option value="">—</option>
              {auditees.map((a) => <option key={a.id} value={a.id}>{a.nom}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="ct-limite" className="etiquette">{t("contradictoire.dateLimite")}</label>
            <input id="ct-limite" type="date" className="champ mt-0" value={limite} onChange={(e) => setLimite(e.target.value)} />
          </div>
          <button type="button" className="btn-primaire" disabled={!audite}
            onClick={() => act("send", { audite_id: audite, date_limite_reponse: limite || null })}>
            {t("contradictoire.envoyer")}
          </button>
        </div>
      )}
      {finding.envoye_le && (
        <p className="text-sm">
          {t("contradictoire.envoye", { nom: finding.audite_nom, date: formatDateHeure(finding.envoye_le), limite: formatDate(finding.date_limite_reponse) })}
        </p>
      )}
      {finding.reponse_position && (
        <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm">
          <p className="font-medium">
            {t(`contradictoire.positions.${finding.reponse_position}`)}
            {finding.repondu_le && ` · ${formatDateHeure(finding.repondu_le)}`}
          </p>
          {finding.reponse_commentaire && <p className="whitespace-pre-line">{finding.reponse_commentaire}</p>}
        </div>
      )}
      {canValidate && (finding.statut === "repondu" || lateNoAnswer) && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <label htmlFor="ct-com" className="etiquette">{t("contradictoire.commentaireValidation")}</label>
            <input id="ct-com" className="champ mt-0" value={commentaire} onChange={(e) => setCommentaire(e.target.value)} />
          </div>
          <button type="button" className="btn-primaire" onClick={() => act("validate", { commentaire: commentaire || null })}>
            {lateNoAnswer ? t("contradictoire.validerSansReponse") : t("contradictoire.valider")}
          </button>
        </div>
      )}
      {finding.valide_le && (
        <Alert kind="succes">
          {t("contradictoire.valide", { date: formatDateHeure(finding.valide_le) })}
          {finding.commentaire_validation && ` — ${finding.commentaire_validation}`}
        </Alert>
      )}
    </section>
  );
}
