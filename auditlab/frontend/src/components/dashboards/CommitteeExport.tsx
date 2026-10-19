import { useState } from "react";
import { useTranslation } from "react-i18next";

import { download } from "../../api/client";
import Alert from "../Alert";

/** Rapport trimestriel au comité d'audit (REP-07). */
export default function CommitteeExport() {
  const { t } = useTranslation();
  const today = new Date();
  const [annee, setAnnee] = useState(String(today.getFullYear()));
  const [trimestre, setTrimestre] = useState(
    String(Math.floor(today.getMonth() / 3) + 1),
  );
  const [error, setError] = useState<string | null>(null);
  const get = (fmt: string) =>
    void download(
      `/dashboards/committee?annee=${annee}&trimestre=${trimestre}&format=${fmt}`,
      undefined,
      `comite_audit_${annee}_T${trimestre}.${fmt}`,
    ).catch((e: Error) => setError(e.message));
  return (
    <section className="carte space-y-3" aria-labelledby="tb-comite">
      <h2 id="tb-comite" className="text-base font-semibold">
        {t("tableauxDeBord.comite.titre")}
      </h2>
      <p className="text-sm text-slate-700">
        {t("tableauxDeBord.comite.aide")}
      </p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="flex flex-wrap items-end gap-2">
        <label className="etiquette">
          {t("tableauxDeBord.comite.annee")}
          <input
            type="number"
            className="champ w-28"
            min={2000}
            max={2100}
            value={annee}
            onChange={(e) => setAnnee(e.target.value)}
          />
        </label>
        <label className="etiquette">
          {t("tableauxDeBord.comite.trimestre")}
          <select
            className="champ"
            value={trimestre}
            onChange={(e) => setTrimestre(e.target.value)}
          >
            {[1, 2, 3, 4].map((q) => (
              <option key={q} value={q}>{`T${q}`}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn-primaire"
          onClick={() => get("pdf")}
        >
          {t("tableauxDeBord.comite.pdf")}
        </button>
        <button
          type="button"
          className="btn-secondaire"
          onClick={() => get("docx")}
        >
          {t("tableauxDeBord.comite.word")}
        </button>
      </div>
    </section>
  );
}
