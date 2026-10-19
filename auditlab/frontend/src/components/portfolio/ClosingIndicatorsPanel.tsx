import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download } from "../../api/client";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Indicator {
  code: string;
  libelle: string;
  famille: string;
  unite: "montant" | "pourcentage" | "ratio";
  N: string | null;
  "N-1": string | null;
  variation: string | null;
  variation_pct: string | null;
}
interface Line {
  etat: string;
  code: string;
  libelle: string;
  total: boolean;
  N: string;
  "N-1": string | null;
  variation: string | null;
  variation_pct: string | null;
}
interface Management {
  exercice: number;
  devise: string;
  n1_disponible: boolean;
  indicateurs: Indicator[];
  comparatif: Line[];
}

/** Comparatif N/N-1 et indicateurs de gestion remis au client (RCO-26). */
export default function ClosingIndicatorsPanel({
  closingId,
}: {
  closingId: string;
}) {
  const { t } = useTranslation();
  const [data, setData] = useState<Management | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = `/closings/${closingId}/management`;
  useEffect(() => {
    api<Management>(url).then(setData, (e: Error) => setError(e.message));
  }, [url]);
  const value = (v: string | null, unit = "montant") =>
    v === null
      ? t("indicateursCloture.ns")
      : `${formatNombre(Number(v))}${unit === "pourcentage" ? " %" : ""}`;
  const pct = (v: string | null) =>
    v === null ? "" : `${formatNombre(Number(v))} %`;
  const get = (fmt: string) =>
    void download(
      `${url}/export?format=${fmt}`,
      undefined,
      `indicateurs.${fmt}`,
    ).catch((e: Error) => setError(e.message));
  return (
    <section className="carte space-y-3" aria-labelledby={`ind-${closingId}`}>
      <h2 id={`ind-${closingId}`} className="text-base font-semibold">
        {t("indicateursCloture.titre")}
      </h2>
      {error && <Alert kind="info">{error}</Alert>}
      {data && (
        <>
          {!data.n1_disponible && (
            <p className="text-sm text-slate-700">
              {t("indicateursCloture.sansN1")}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-secondaire"
              onClick={() => get("pdf")}
            >
              {t("indicateursCloture.pdf")}
            </button>
            <button
              type="button"
              className="btn-secondaire"
              onClick={() => get("docx")}
            >
              {t("indicateursCloture.word")}
            </button>
          </div>
          <table className="w-full text-sm">
            <caption className="sr-only">
              {t("indicateursCloture.titre")}
            </caption>
            <thead>
              <tr className="text-left">
                <th scope="col">{t("indicateursCloture.indicateur")}</th>
                <th scope="col" className="text-right">
                  {data.exercice}
                </th>
                <th scope="col" className="text-right">
                  {data.exercice - 1}
                </th>
                <th scope="col" className="text-right">
                  {t("indicateursCloture.variation")}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.indicateurs.map((i) => (
                <tr key={i.code} className="border-t">
                  <th scope="row" className="text-left font-normal">
                    {i.libelle}
                  </th>
                  <td className="text-right">{value(i.N, i.unite)}</td>
                  <td className="text-right">{value(i["N-1"], i.unite)}</td>
                  <td className="text-right">
                    {i.unite === "montant"
                      ? pct(i.variation_pct)
                      : value(i.variation, i.unite)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <details>
            <summary className="cursor-pointer text-sm font-medium">
              {t("indicateursCloture.comparatif", { devise: data.devise })}
            </summary>
            <table className="mt-2 w-full text-sm">
              <thead>
                <tr className="text-left">
                  <th scope="col">{t("indicateursCloture.poste")}</th>
                  <th scope="col" className="text-right">
                    {data.exercice}
                  </th>
                  <th scope="col" className="text-right">
                    {data.exercice - 1}
                  </th>
                  <th scope="col" className="text-right">
                    {t("indicateursCloture.variation")}
                  </th>
                  <th scope="col" className="text-right">
                    %
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.comparatif.map((l) => (
                  <tr
                    key={`${l.etat}-${l.code}`}
                    className={`border-t ${l.total ? "font-semibold" : ""}`}
                  >
                    <th scope="row" className="text-left font-normal">
                      {l.code} {l.libelle}
                    </th>
                    <td className="text-right">{value(l.N)}</td>
                    <td className="text-right">{value(l["N-1"])}</td>
                    <td className="text-right">{value(l.variation)}</td>
                    <td className="text-right">{pct(l.variation_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  );
}
