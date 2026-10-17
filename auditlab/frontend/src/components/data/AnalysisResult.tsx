import { useTranslation } from "react-i18next";

import type { Dataset } from "../../api/types";
import { formatNombre } from "../../lib/format";
import BenfordChart from "./BenfordChart";
import type { BenfordDigit } from "./BenfordChart";

function show(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return formatNombre(v);
  if (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v)) return formatNombre(Number(v));
  if (Array.isArray(v)) return v.map(show).join(" ; ");
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k} : ${show(x)}`).join(" · ");
  return String(v);
}

/** Synthèse d'une analyse : opération, paramètres, résultats et tests (lot 6). */
export default function AnalysisResult({ ds }: { ds: Dataset }) {
  const { t } = useTranslation();
  const code = ds.operation ?? "";
  const params = (ds.definition.parametres as Record<string, unknown>) ?? {};
  const { chiffres, ...scalars } = ds.resultat as { chiffres?: BenfordDigit[] } & Record<string, unknown>;
  return (
    <section className="carte space-y-3" aria-labelledby="resultat-titre">
      <h2 id="resultat-titre" className="text-base font-semibold">
        {String(ds.definition.exigence ?? "")} · {t(`analyses.${code}.titre`, { defaultValue: code })}
      </h2>
      <dl className="grid gap-x-4 gap-y-1 text-sm md:grid-cols-[max-content_1fr]">
        {Object.entries(params).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-slate-600">{t(`analyses.${code}.params.${k}`, { defaultValue: k })}</dt>
            <dd>{typeof v === "string" && !/^-?\d+(\.\d+)?$/.test(v) ? t(`analyses.choix.${v}`, { defaultValue: v }) : show(v)}</dd>
          </div>
        ))}
      </dl>
      {Object.keys(scalars).length > 0 && (
        <dl className="grid gap-x-4 gap-y-1 border-t border-slate-100 pt-2 text-sm md:grid-cols-[max-content_1fr]">
          {Object.entries(scalars).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-slate-600">{t(`resultats.${k}`, { defaultValue: k })}</dt>
              <dd className="font-mono">{typeof v === "string" && t(`resultats.valeurs.${v}`, { defaultValue: "" }) ? t(`resultats.valeurs.${v}`) : show(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {chiffres && <BenfordChart digits={chiffres} />}
    </section>
  );
}
