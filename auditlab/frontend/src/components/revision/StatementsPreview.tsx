import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Line { code: string; libelle: string; niveau: number; total: boolean; N: string; "N-1": string | null }
interface Preview {
  etats: Record<string, Line[]>;
  controles: { code: string; libelle: string; ecarts: Record<string, string>; ok: boolean }[];
}

/** Aperçu des états N / N-1, refusé tant qu'un compte n'est pas affecté (REV-10). */
export default function StatementsPreview({ file, blocked }: { file: AuditFile; blocked: boolean }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const show = async () => {
    setError(null);
    try {
      setData(await api<Preview>(`/audit-files/${file.id}/statements/preview`));
    } catch (e) {
      setData(null);
      setError((e as Error).message);
    }
  };
  return (
    <section className="carte space-y-3" aria-labelledby="apercu-titre">
      <div className="flex items-center justify-between gap-2">
        <h2 id="apercu-titre" className="text-base font-semibold">{t("affectation.apercu")}</h2>
        <button type="button" className="btn-secondaire" onClick={() => void show()} disabled={blocked} aria-describedby={blocked ? "apercu-bloque" : undefined}>
          {t("affectation.produireApercu")}
        </button>
      </div>
      {blocked && <p id="apercu-bloque" className="text-sm text-red-700">{t("affectation.bloque")}</p>}
      {error && <Alert kind="erreur">{error}</Alert>}
      {data && (
        <>
          <ul className="text-sm">
            {data.controles.map((c) => (
              <li key={c.code} className={c.ok ? "text-emerald-800" : "text-red-700"}>
                {c.ok ? "✓" : "✗"} {c.libelle}
                {!c.ok && ` (${t("affectation.ecart")} N : ${formatNombre(Number(c.ecarts.N))} ; N-1 : ${formatNombre(Number(c.ecarts["N-1"]))})`}
              </li>
            ))}
          </ul>
          {Object.entries(data.etats).map(([etat, lines]) => (
            <table key={etat} className="w-full text-left text-sm">
              <caption className="py-1 text-left font-semibold">{t(`affectation.etats.${etat}`, { defaultValue: etat })}</caption>
              <thead className="text-xs text-slate-600">
                <tr><th scope="col" className="py-1 pr-3">{t("affectation.col.poste", { periode: "" })}</th><th scope="col" className="py-1 pr-3 text-right">N</th><th scope="col" className="py-1 text-right">N-1</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {lines.map((l) => (
                  <tr key={l.code} className={l.total ? "bg-slate-50 font-semibold" : ""}>
                    <td className="py-1 pr-3"><span className="font-mono text-xs">{l.code}</span> {l.libelle}</td>
                    <td className="py-1 pr-3 text-right font-mono">{formatNombre(Number(l.N))}</td>
                    <td className="py-1 text-right font-mono">{l["N-1"] === null ? "" : formatNombre(Number(l["N-1"]))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </>
      )}
    </section>
  );
}
