import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { Criticality, Dataset, Finding } from "../../api/types";
import Alert from "../Alert";
import { CRITICITES } from "../mission/FindingsTab";

/** DAT-31 : les lignes sélectionnées deviennent un constat (ou complètent un constat). */
export default function LinesToFinding({ ds, rows }: { ds: Dataset; rows: Record<string, unknown>[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [titre, setTitre] = useState("");
  const [criticite, setCriticite] = useState<Criticality>("moyenne");
  const [existing, setExisting] = useState("");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Finding[]>(`/engagements/${ds.engagement_id}/findings`).then((f) => setFindings(f.filter((x) => x.peut_modifier))).catch(() => setFindings([]));
  }, [ds.engagement_id]);
  if (rows.length === 0) return <p className="text-sm text-slate-600">{t("lignesConstat.aide")}</p>;

  const submit = async () => {
    setError(null);
    try {
      const f = await post<Finding>(`/datasets/${ds.id}/findings`, {
        titre: titre || t("lignesConstat.titreDefaut", { table: ds.nom }),
        criticite,
        lignes: rows,
        finding_id: existing || null,
      });
      navigate(`/missions/${ds.engagement_id}/constats/${f.id}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="flex flex-wrap items-end gap-2 rounded border border-amber-200 bg-amber-50 p-3">
      <p className="w-full text-sm font-medium">{t("lignesConstat.selection", { n: rows.length })}</p>
      <div>
        <label htmlFor="lc-existant" className="etiquette">{t("lignesConstat.cible")}</label>
        <select id="lc-existant" className="champ mt-0" value={existing} onChange={(e) => setExisting(e.target.value)}>
          <option value="">{t("lignesConstat.nouveau")}</option>
          {findings.map((f) => <option key={f.id} value={f.id}>{f.reference} · {f.titre}</option>)}
        </select>
      </div>
      {!existing && (
        <>
          <div className="min-w-64 flex-1">
            <label htmlFor="lc-titre" className="etiquette">{t("constats.col.titre")}</label>
            <input id="lc-titre" className="champ mt-0" maxLength={300} value={titre} placeholder={t("lignesConstat.titreDefaut", { table: ds.nom })} onChange={(e) => setTitre(e.target.value)} />
          </div>
          <div>
            <label htmlFor="lc-crit" className="etiquette">{t("constats.criticite")}</label>
            <select id="lc-crit" className="champ mt-0" value={criticite} onChange={(e) => setCriticite(e.target.value as Criticality)}>
              {CRITICITES.map((c) => <option key={c} value={c}>{t(`constats.criticites.${c}`)}</option>)}
            </select>
          </div>
        </>
      )}
      <button type="button" className="btn-primaire" onClick={submit}>{existing ? t("lignesConstat.ajouter") : t("lignesConstat.creer")}</button>
      {error && <Alert kind="erreur">{error}</Alert>}
    </div>
  );
}
