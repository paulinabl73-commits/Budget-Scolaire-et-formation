import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { StatusChange } from "../../api/types";
import { formatDateHeure } from "../../lib/format";

export default function StatusHistory({ missionId, statut }: { missionId: string; statut: string }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<StatusChange[]>([]);
  useEffect(() => {
    api<StatusChange[]>(`/engagements/${missionId}/status-history`)
      .then(setRows)
      .catch(() => setRows([]));
  }, [missionId, statut]);

  return (
    <section className="carte space-y-2">
      <h2 className="text-base font-semibold">{t("missions.historique")}</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-600">{t("missions.aucunChangement")}</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {rows.map((r) => (
            <li key={r.horodatage}>
              {formatDateHeure(r.horodatage)} — {t(`missions.statuts.${r.avant}`)} →{" "}
              <strong>{t(`missions.statuts.${r.apres}`)}</strong>
              {r.utilisateur && <span className="text-slate-600"> ({r.utilisateur})</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
