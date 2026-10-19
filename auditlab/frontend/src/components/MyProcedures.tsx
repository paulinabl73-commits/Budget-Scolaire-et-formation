import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { MyProcedure } from "../api/types";
import { formatDate } from "../lib/format";

export default function MyProcedures() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<MyProcedure[] | null>(null);
  useEffect(() => {
    api<MyProcedure[]>("/me/procedures").then(setRows).catch(() => setRows([]));
  }, []);
  if (rows === null) return null;
  return (
    <section aria-labelledby="mes-procedures" className="carte">
      <h2 id="mes-procedures" className="mb-3 text-lg font-semibold">{t("accueil.mesProcedures")}</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-600">{t("accueil.aucuneProcedure")}</p>
      ) : (
        <ul className="divide-y divide-slate-200 text-sm">
          {rows.map((p) => (
            <li key={p.id} className="flex items-start justify-between gap-4 py-2">
              <span>
                <Link to={`/missions/${p.engagement_id}?onglet=programme`} className="font-mono text-marque-700 underline">
                  {p.engagement_reference} · {p.reference}
                </Link>{" "}
                {p.description}
                <span className="block text-xs text-slate-600">{p.controle}</span>
              </span>
              <span className={`whitespace-nowrap text-xs ${p.en_retard ? "font-semibold text-red-800" : "text-slate-600"}`}>
                {p.echeance ? formatDate(p.echeance) : ""} · {t(`programme.statuts.${p.statut}`)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
