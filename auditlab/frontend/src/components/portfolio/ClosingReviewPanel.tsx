import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

interface Review {
  revues: Record<string, { le: string; par: string; commentaire: string | null }>;
  blocages: { superviseur: string[]; expert: string[] };
  superviseur_requis: boolean;
  peut_viser: { superviseur: boolean; expert: boolean };
}

/** Revue du dossier de clôture : visa du superviseur puis de l'expert-comptable (RCO-23). */
export default function ClosingReviewPanel({ closingId, onChange }: { closingId: string; onChange: () => void }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Review | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = `/closings/${closingId}/review`;
  const load = useCallback(() => api<Review>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const run = async (action: () => Promise<Review>) => {
    setError(null);
    try {
      setData(await action());
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const levels = (data.superviseur_requis ? ["superviseur", "expert"] : ["expert"]) as ("superviseur" | "expert")[];
  return (
    <section className="carte space-y-3" aria-labelledby={`rv-${closingId}`}>
      <h2 id={`rv-${closingId}`} className="text-base font-semibold">{t("revueCloture.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {levels.map((lvl) => {
        const done = data.revues[lvl];
        return (
          <div key={lvl} className="space-y-1 text-sm">
            <p className="font-medium">{t(`revueCloture.niveaux.${lvl}`)} : {done ? t("revueCloture.vise", { par: done.par, le: formatDateHeure(done.le) }) : t("revueCloture.attente")}</p>
            {!done && data.blocages[lvl].length > 0 && <ul className="list-disc pl-5 text-slate-700">{data.blocages[lvl].map((b) => <li key={b}>{b}</li>)}</ul>}
            {!done && data.peut_viser[lvl] && <button type="button" className="btn-secondaire" disabled={data.blocages[lvl].length > 0} onClick={() => void run(() => post<Review>(url, { niveau: lvl }))}>{t("revueCloture.viser")}</button>}
            {done && data.peut_viser[lvl] && <button type="button" className="underline" onClick={() => void run(() => del(`${url}/${lvl}`).then(load) as Promise<Review>)}>{t("revueCloture.retirer")}</button>}
          </div>
        );
      })}
    </section>
  );
}
