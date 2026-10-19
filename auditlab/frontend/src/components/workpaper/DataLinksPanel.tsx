import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, del } from "../../api/client";
import { formatDateHeure, formatNombre } from "../../lib/format";
import Alert from "../Alert";
import BarChart from "../data/BarChart";
import BenfordChart from "../data/BenfordChart";
import type { BenfordDigit } from "../data/BenfordChart";

export interface DataLink {
  id: string;
  dataset_id: string;
  dataset_nom: string | null;
  empreinte: string | null;
  empreinte_actuelle: string | null;
  nb_lignes: number | null;
  lignee: { noeuds: { id: string; nom: string; kind: string; operation: string }[] };
  graphique: { type?: string; points?: { etiquette: string; valeur: number }[]; chiffres?: BenfordDigit[]; categorie?: string; valeur?: string | null };
  commentaire: string | null;
  created_at: string | null;
}

/** Tables de résultat jointes au papier (DAT-30), avec historique et graphique figés. */
export default function DataLinksPanel({ workpaperId, missionId, editable, refresh }: { workpaperId: string; missionId: string; editable: boolean; refresh: number }) {
  const { t } = useTranslation();
  const [links, setLinks] = useState<DataLink[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<DataLink[]>(`/workpapers/${workpaperId}/data-links`).then(setLinks), [workpaperId]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load, refresh]);

  const step = (n: DataLink["lignee"]["noeuds"][number]) =>
    n.kind === "analyse" ? t(`analyses.${n.operation}.titre`, { defaultValue: n.operation }) : t(`donnees.kinds.${n.kind}`);

  return (
    <section className="carte space-y-3" aria-labelledby="liens-titre">
      <h2 id="liens-titre" className="text-base font-semibold">{t("liens.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {links.length === 0 && <p className="text-sm text-slate-600">{t("liens.aucun")}</p>}
      {links.map((l) => (
        <article key={l.id} className="space-y-2 border-t border-slate-100 pt-2 first:border-0 first:pt-0">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="text-sm">
              <Link to={`/missions/${missionId}/donnees/${l.dataset_id}`} className="font-semibold text-marque-700 underline">{l.dataset_nom}</Link>
              <span className="text-slate-600"> · {t("table.lignes", { n: formatNombre(l.nb_lignes ?? 0) })} · {formatDateHeure(l.created_at)}</span>
              <p className="text-slate-600">{t("liens.historique")} : {l.lignee.noeuds.map(step).join(" → ")}</p>
              <p className="font-mono text-xs text-slate-600">SHA-256 : {l.empreinte}</p>
              {l.commentaire && <p>{l.commentaire}</p>}
            </div>
            {editable && (
              <button type="button" className="text-sm text-red-700 underline"
                onClick={async () => { await del(`/data-links/${l.id}`); await load(); }}>
                {t("liens.retirer")}
              </button>
            )}
          </div>
          {l.empreinte_actuelle !== l.empreinte && <Alert kind="erreur">{t("liens.modifiee")}</Alert>}
          {l.graphique.type === "barres" && l.graphique.points && (
            <BarChart points={l.graphique.points} label={`${l.graphique.valeur ?? t("liens.nombre")} / ${l.graphique.categorie}`} />
          )}
          {l.graphique.type === "benford" && l.graphique.chiffres && <BenfordChart digits={l.graphique.chiffres} />}
        </article>
      ))}
    </section>
  );
}
