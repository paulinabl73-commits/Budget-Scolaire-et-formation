import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../../api/client";
import type { Signoff, SignoffType, Workpaper } from "../../api/types";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

const STEPS: SignoffType[] = ["prepare", "revu", "approuve"];

export default function SignoffsPanel({ wp, onSigned }: { wp: Workpaper; onSigned: () => void }) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Signoff[]>([]);

  useEffect(() => {
    api<Signoff[]>(`/workpapers/${wp.id}/signoffs`).then(setHistory).catch(() => setHistory([]));
  }, [wp.id, wp.version, wp.signatures.length]);

  const sign = async (type: SignoffType) => {
    if (!window.confirm(t("signatures.confirmer", { etape: t(`signatures.statuts.${type}`), version: wp.version }))) return;
    setError(null);
    try {
      await post(`/workpapers/${wp.id}/signoffs`, { type });
      onSigned();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const cancelled = history.filter((s) => s.annule_le);

  return (
    <section className="carte space-y-3" aria-labelledby="sig-titre">
      <h2 id="sig-titre" className="text-base font-semibold">{t("signatures.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ol className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {STEPS.map((step) => {
          const s = wp.signatures.find((x) => x.type === step);
          const canSign = wp.signatures_possibles.includes(step);
          return (
            <li key={step} className={`rounded-md border p-3 ${s ? "border-green-300 bg-green-50" : "border-slate-200"}`}>
              <p className="text-xs font-semibold uppercase text-slate-600">{t(`signatures.etapes.${step}`)}</p>
              {s ? (
                <>
                  <p className="text-sm font-medium">{s.user_nom}</p>
                  <p className="text-xs text-slate-600">
                    {t("signatures.le", { date: formatDateHeure(s.signed_at) })} · v{s.version}
                  </p>
                  <p className="font-mono text-[11px] text-slate-600" title={t("signatures.empreinte")}>{s.hash_contenu.slice(0, 16)}…</p>
                </>
              ) : canSign ? (
                <button type="button" className="btn-primaire mt-1" onClick={() => sign(step)}>{t(`signatures.signer.${step}`)}</button>
              ) : (
                <p className="text-sm text-slate-600" title={wp.motifs_refus[step]}>
                  {t("signatures.enAttente")}
                  {wp.motifs_refus[step] && <span className="block text-xs">{wp.motifs_refus[step]}</span>}
                </p>
              )}
            </li>
          );
        })}
      </ol>
      {cancelled.length > 0 && (
        <details className="text-xs text-slate-600">
          <summary className="cursor-pointer">{t("signatures.historique")}</summary>
          <ul className="mt-1 space-y-0.5">
            {cancelled.map((s) => (
              <li key={s.id}>
                {t(`signatures.statuts.${s.type}`)} — {s.user_nom}, {formatDateHeure(s.signed_at)} (v{s.version}),{" "}
                {t("signatures.annulee", { date: formatDateHeure(s.annule_le), motif: s.motif_annulation ?? "" })}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
