import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, post, put } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDate, formatDecimal, formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Account {
  compte: string; mode: string; lettrees: number; ouvertes: number; solde_balance: string; solde_ouvert: string;
  ecart: string; justifie: boolean; anomalies: string[];
  lignes_ouvertes: { date: string | null; piece: string | null; libelle: string | null; tiers: string | null; montant: string }[];
}
interface Aging {
  tranches: { libelle: string; taux: string }[];
  tiers: { tiers: string; solde: string; tranches: string[]; depreciation: string }[];
  totaux: string[];
  depreciation_requise: string; depreciation_comptabilisee: string; ecart: string;
  grille: [number, number][]; tva_pct: string | null;
}

/** Lettrage et justification des tiers, balance âgée et dépréciation des créances (REV-18). */
export default function ThirdPartiesPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [aging, setAging] = useState<Aging | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [grid, setGrid] = useState("");
  const [vat, setVat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const base = `/audit-files/${file.id}`;
  const fillAging = (a: Aging) => {
    setAging(a);
    setGrid(a.grille.map(([d, r]) => `${d}:${r}`).join(" ; "));
    setVat(a.tva_pct ? formatDecimal(a.tva_pct) : "");
  };
  const load = useCallback(async () => {
    setAccounts((await api<{ comptes: Account[] }>(`${base}/third-parties`)).comptes);
    fillAging(await api<Aging>(`${base}/receivables-aging`));
  }, [base]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  if (error && !accounts) return <Alert kind="info">{error}</Alert>;
  if (!accounts || !aging) return null;
  const n = (v: string) => formatNombre(Number(v));
  const saveGrid = async () => {
    setError(null);
    try {
      const grille = grid.split(";").map((x) => x.split(":").map((y) => Number(y.trim().replace(",", "."))));
      fillAging(await put<Aging>(`${base}/impairment-grid`, { grille, tva_pct: vat ? vat.replace(",", ".") : null }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const propose = async () => {
    setError(null);
    try {
      const r = await post<{ numero: number; montant: string }>(`${base}/receivables-aging/adjustment`);
      setInfo(t("tiers.proposee", { numero: r.numero, montant: n(r.montant) }));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      {error && <Alert kind="erreur">{error}</Alert>}
      {info && <Alert kind="succes">{info}</Alert>}
      <section className="carte space-y-2" aria-labelledby="tiers-titre">
        <h2 id="tiers-titre" className="text-base font-semibold">{t("tiers.titre")}</h2>
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-600"><tr>{["compte", "lettrage", "lettrees", "ouvertes", "balance", "ouvert", "ecart"].map((k) => <th key={k} scope="col" className="py-1 pr-3 text-left">{t(`tiers.col.${k}`)}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {accounts.map((a) => (
              <tr key={a.compte} className={a.justifie ? "" : "bg-red-50"}>
                <td className="py-1 pr-3"><button type="button" className="font-mono underline" aria-expanded={open === a.compte} onClick={() => setOpen(open === a.compte ? null : a.compte)}>{a.compte}</button>
                  {a.anomalies.map((x) => <p key={x} className="text-xs text-amber-800">{x}</p>)}</td>
                <td className="py-1 pr-3">{t(`tiers.modes.${a.mode}`)}</td>
                <td className="py-1 pr-3">{a.lettrees}</td>
                <td className="py-1 pr-3">{a.ouvertes}</td>
                <td className="py-1 pr-3 text-right font-mono">{n(a.solde_balance)}</td>
                <td className="py-1 pr-3 text-right font-mono">{n(a.solde_ouvert)}</td>
                <td className="py-1 text-right font-mono">{a.justifie ? "✓" : n(a.ecart)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {open && (
          <table className="w-full text-xs">
            <caption className="text-left font-medium">{t("tiers.lignesOuvertes", { compte: open })}</caption>
            <tbody>{accounts.find((a) => a.compte === open)?.lignes_ouvertes.map((l, i) => <tr key={i}><td className="pr-3">{formatDate(l.date)}</td><td className="pr-3">{l.piece}</td><td className="pr-3">{l.tiers}</td><td className="pr-3">{l.libelle}</td><td className="text-right font-mono">{n(l.montant)}</td></tr>)}</tbody>
          </table>
        )}
      </section>
      <section className="carte space-y-2" aria-labelledby="agee-titre">
        <h2 id="agee-titre" className="text-base font-semibold">{t("tiers.balanceAgee")}</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-600"><tr><th scope="col" className="py-1 pr-3 text-left">{t("tiers.col.tiers")}</th>{aging.tranches.map((b) => <th key={b.libelle} scope="col" className="py-1 pr-3 text-right">{b.libelle}<br />{formatDecimal(b.taux)} %</th>)}<th scope="col" className="py-1 text-right">{t("tiers.col.depreciation")}</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {aging.tiers.map((r) => <tr key={r.tiers}><td className="py-1 pr-3">{r.tiers}</td>{r.tranches.map((v, i) => <td key={i} className="py-1 pr-3 text-right font-mono">{Number(v) ? n(v) : ""}</td>)}<td className="py-1 text-right font-mono">{n(r.depreciation)}</td></tr>)}
              <tr className="font-semibold"><td className="py-1 pr-3">{t("tiers.total")}</td>{aging.totaux.map((v, i) => <td key={i} className="py-1 pr-3 text-right font-mono">{n(v)}</td>)}<td className="py-1 text-right font-mono">{n(aging.depreciation_requise)}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="text-sm">{t("tiers.comparaison", { requise: n(aging.depreciation_requise), comptabilisee: n(aging.depreciation_comptabilisee), ecart: n(aging.ecart) })}</p>
        {file.peut_travailler && Number(aging.ecart) !== 0 && <button type="button" className="btn-secondaire" onClick={() => void propose()}>{t("tiers.proposer")}</button>}
        {file.peut_gerer && (
          <div className="grid gap-2 md:grid-cols-4">
            <div className="md:col-span-2"><label htmlFor="tiers-grille" className="etiquette">{t("tiers.grille")}</label><input id="tiers-grille" className="champ" value={grid} onChange={(e) => setGrid(e.target.value)} /></div>
            <div><label htmlFor="tiers-tva" className="etiquette">{t("tiers.tva")}</label><input id="tiers-tva" className="champ" inputMode="decimal" value={vat} onChange={(e) => setVat(e.target.value)} /></div>
            <div className="flex items-end"><button type="button" className="btn-secondaire" onClick={() => void saveGrid()}>{t("tiers.appliquerGrille")}</button></div>
          </div>
        )}
      </section>
    </div>
  );
}
