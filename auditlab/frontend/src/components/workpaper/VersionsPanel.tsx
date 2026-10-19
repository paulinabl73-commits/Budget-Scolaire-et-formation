import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { FieldDiff, VersionSummary } from "../../api/types";
import { formatDateHeure } from "../../lib/format";

export default function VersionsPanel({ workpaperId, current }: { workpaperId: string; current: number }) {
  const { t } = useTranslation();
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [from, setFrom] = useState<number | null>(null);
  const [to, setTo] = useState<number | null>(null);
  const [diff, setDiff] = useState<FieldDiff[] | null>(null);

  useEffect(() => {
    api<VersionSummary[]>(`/workpapers/${workpaperId}/versions`).then((v) => {
      setVersions(v);
      setTo(v[0]?.version ?? null);
      setFrom(v[1]?.version ?? null);
      setDiff(null);
    });
  }, [workpaperId, current]);

  const run = async () => {
    if (from === null || to === null) return;
    const res = await api<{ champs: FieldDiff[] }>(`/workpapers/${workpaperId}/compare?de=${from}&a=${to}`);
    setDiff(res.champs);
  };

  return (
    <section className="carte space-y-3" aria-labelledby="ver-titre">
      <h2 id="ver-titre" className="text-base font-semibold">{t("versions.titre")}</h2>
      <p className="text-xs text-slate-600">{t("versions.intro")}</p>
      <ul className="max-h-40 overflow-y-auto text-sm">
        {versions.map((v) => (
          <li key={v.version} className="flex justify-between gap-2 py-0.5">
            <span>{t("versions.version", { version: v.version })}{v.auteur && ` — ${t("versions.par", { auteur: v.auteur })}`}</span>
            <span className="text-xs text-slate-600">{formatDateHeure(v.created_at)}</span>
          </li>
        ))}
      </ul>
      {versions.length > 1 && (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="v-de" className="etiquette">{t("versions.de")}</label>
            <select id="v-de" className="champ" value={from ?? ""} onChange={(e) => setFrom(Number(e.target.value))}>
              {versions.map((v) => <option key={v.version} value={v.version}>{v.version}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="v-a" className="etiquette">{t("versions.a")}</label>
            <select id="v-a" className="champ" value={to ?? ""} onChange={(e) => setTo(Number(e.target.value))}>
              {versions.map((v) => <option key={v.version} value={v.version}>{v.version}</option>)}
            </select>
          </div>
          <button type="button" className="btn-secondaire" onClick={run}>{t("versions.comparer")}</button>
        </div>
      )}
      {diff && (
        <div className="space-y-3">
          {diff.every((d) => !d.modifie) && <p className="text-sm text-slate-600">{t("versions.aucuneDiff")}</p>}
          {diff.filter((d) => d.modifie).map((d) => (
            <div key={d.champ}>
              <p className="text-xs font-semibold text-slate-700">{d.libelle}</p>
              <p className="whitespace-pre-wrap rounded bg-slate-50 p-2 text-sm">
                {d.segments.map((s, i) =>
                  s.type === "egal" ? (
                    <span key={i}>{s.texte}</span>
                  ) : s.type === "ajoute" ? (
                    <ins key={i} className="bg-green-100 text-green-900 no-underline">{s.texte}</ins>
                  ) : (
                    <del key={i} className="bg-red-100 text-red-900">{s.texte}</del>
                  ),
                )}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
