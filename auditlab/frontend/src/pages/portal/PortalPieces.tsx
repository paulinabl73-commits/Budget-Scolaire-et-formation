import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, upload } from "../../api/client";
import Alert from "../../components/Alert";
import { PIECE_BADGE, PieceFiles } from "../../components/portfolio/PiecesPanel";
import type { Piece } from "../../components/portfolio/PiecesPanel";
import { formatDate } from "../../lib/format";

/** Pièces demandées par le cabinet, déposées depuis le portail (RCO-04). */
export default function PortalPieces() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Piece[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Piece[]>("/portal/pieces").then(setRows), []);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  if (!rows || rows.length === 0) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const send = async (id: string, file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      await upload(`/portal/pieces/${id}/files`, file);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="carte space-y-2" aria-labelledby="portail-pieces">
      <h2 id="portail-pieces" className="text-lg font-semibold">{t("pieces.portail")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="divide-y divide-slate-100 text-sm">
        {rows.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-3 py-2">
            <span className="min-w-64 flex-1">{p.libelle} <span className="text-xs text-slate-500">({p.client}, {p.exercice})</span>
              {p.commentaire && p.statut !== "recue" && <span className="block text-xs text-red-700">{p.commentaire}</span>}
            </span>
            <span>{t("pieces.avant", { date: formatDate(p.date_limite) })}</span>
            <span className={`rounded px-2 py-0.5 text-xs ${PIECE_BADGE[p.statut]}`}>{t(`pieces.statuts.${p.statut}`)}</span>
            <PieceFiles piece={p} />
            <label className="btn-secondaire cursor-pointer">
              {t("pieces.deposer")}
              <input type="file" className="sr-only" aria-label={t("pieces.deposerPour", { piece: p.libelle })} onChange={(e) => void send(p.id, e.target.files?.[0])} />
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}
