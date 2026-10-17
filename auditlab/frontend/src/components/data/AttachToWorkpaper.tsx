import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, post } from "../../api/client";
import type { Dataset, WorkpaperSummary } from "../../api/types";
import Alert from "../Alert";

/** Bouton « Joindre au papier de travail » (DAT-30). */
export default function AttachToWorkpaper({ ds }: { ds: Dataset }) {
  const { t } = useTranslation();
  const [papers, setPapers] = useState<WorkpaperSummary[]>([]);
  const [wp, setWp] = useState("");
  const [cat, setCat] = useState("");
  const [val, setVal] = useState("");
  const [commentaire, setCommentaire] = useState("");
  const [done, setDone] = useState<{ ok: boolean; text: string; wp?: string } | null>(null);
  useEffect(() => {
    api<WorkpaperSummary[]>(`/engagements/${ds.engagement_id}/workpapers`).then(setPapers).catch(() => setPapers([]));
  }, [ds.engagement_id]);
  const numeric = ds.schema.filter((c) => c.type === "decimal" || c.type === "entier");

  const attach = async () => {
    try {
      await post(`/workpapers/${wp}/data-links`, {
        dataset_id: ds.id,
        commentaire: commentaire || null,
        graphique: cat ? { categorie: cat, valeur: val || null } : null,
      });
      setDone({ ok: true, text: t("liens.joint"), wp });
    } catch (e) {
      setDone({ ok: false, text: (e as Error).message });
    }
  };

  if (papers.length === 0) return null;
  return (
    <section className="carte space-y-2" aria-labelledby="joindre-titre">
      <h2 id="joindre-titre" className="text-base font-semibold">{t("liens.joindre")}</h2>
      <div className="grid gap-2 md:grid-cols-4">
        <div>
          <label htmlFor="j-wp" className="etiquette">{t("liens.papier")}</label>
          <select id="j-wp" className="champ" value={wp} onChange={(e) => setWp(e.target.value)}>
            <option value="">—</option>
            {papers.map((p) => <option key={p.id} value={p.id}>{p.reference} · {p.titre}</option>)}
          </select>
        </div>
        {!ds.resultat?.chiffres && (
          <>
            <div>
              <label htmlFor="j-cat" className="etiquette">{t("liens.categorie")}</label>
              <select id="j-cat" className="champ" value={cat} onChange={(e) => setCat(e.target.value)}>
                <option value="">{t("liens.sansGraphique")}</option>
                {ds.schema.map((c) => <option key={c.nom} value={c.nom}>{c.nom}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="j-val" className="etiquette">{t("liens.valeur")}</label>
              <select id="j-val" className="champ" value={val} onChange={(e) => setVal(e.target.value)} disabled={!cat}>
                <option value="">{t("liens.nombre")}</option>
                {numeric.map((c) => <option key={c.nom} value={c.nom}>{c.nom}</option>)}
              </select>
            </div>
          </>
        )}
        <div>
          <label htmlFor="j-com" className="etiquette">{t("liens.commentaire")}</label>
          <input id="j-com" className="champ" value={commentaire} onChange={(e) => setCommentaire(e.target.value)} />
        </div>
      </div>
      <button type="button" className="btn-primaire" disabled={!wp} onClick={attach}>{t("liens.joindre")}</button>
      {done && (
        <Alert kind={done.ok ? "succes" : "erreur"}>
          {done.text}{" "}
          {done.wp && <Link className="underline" to={`/missions/${ds.engagement_id}/papiers/${done.wp}`}>{t("liens.voirPapier")}</Link>}
        </Alert>
      )}
    </section>
  );
}
