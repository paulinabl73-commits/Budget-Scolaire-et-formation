import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, post, upload } from "../../api/client";
import type { ActionPlan } from "../../api/types";
import { formatDateHeure, formatTaille } from "../../lib/format";
import Alert from "../Alert";

interface Evidence {
  id: string;
  nom_fichier: string;
  taille: number;
  sha256: string;
  commentaire: string | null;
  created_at: string | null;
  url: string;
}

/** Justificatifs d'un plan (CON-07) ; l'audit peut rejeter une réalisation déclarée. */
export default function PlanEvidence({ plan, canUpload, canReject, onChange }: { plan: ActionPlan; canUpload: boolean; canReject: boolean; onChange: () => void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Evidence[]>([]);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(() => api<Evidence[]>(`/action-plans/${plan.id}/evidence`).then(setItems), [plan.id]);
  useEffect(() => {
    load().catch(() => setItems([]));
  }, [load]);
  const closed = plan.statut === "verifie" || plan.statut === "risque_accepte";

  const send = async (file: File) => {
    setError(null);
    try {
      await upload(`/action-plans/${plan.id}/evidence`, file);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const reject = async () => {
    const commentaire = window.prompt(t("justificatifs.motifRejet"));
    if (!commentaire) return;
    try {
      await post(`/action-plans/${plan.id}/reject`, { commentaire });
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="ml-4 space-y-1 border-l-2 border-slate-100 pl-3">
      {error && <Alert kind="erreur">{error}</Alert>}
      {items.length > 0 && (
        <ul className="text-xs">
          {items.map((e) => (
            <li key={e.id}>
              <a href={e.url} className="text-marque-700 underline">{e.nom_fichier}</a>
              <span className="text-slate-600"> · {formatTaille(e.taille)} · {formatDateHeure(e.created_at)}{e.commentaire && ` · ${e.commentaire}`}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        {canUpload && !closed && (
          <>
            <input ref={input} type="file" className="sr-only" aria-label={t("justificatifs.deposer")}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void send(f); e.target.value = ""; }} />
            <button type="button" className="btn-secondaire py-1 text-xs" onClick={() => input.current?.click()}>{t("justificatifs.deposer")}</button>
          </>
        )}
        {canReject && plan.statut === "realise" && (
          <button type="button" className="btn-secondaire py-1 text-xs" onClick={reject}>{t("justificatifs.rejeter")}</button>
        )}
      </div>
    </div>
  );
}
