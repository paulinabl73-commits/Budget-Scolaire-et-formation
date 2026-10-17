import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, patch, post } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can, PERM } from "../../lib/permissions";
import Alert from "../Alert";

interface Step { id: string; referentiel: string; cycle: string; assertion: string; type_test: string; description: string; ordre: number; actif: boolean }
interface Library { referentiel: string; cycles: { code: string; libelle: string }[]; assertions: { code: string; libelle: string }[]; procedures: Step[] }

/** Bibliothèque des programmes de travail types par cycle (REV-16). */
export default function ProgramsLibraryPanel() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const manager = can(user?.permissions, PERM.FRAMEWORKS_MANAGE);
  const [ref, setRef] = useState("SYSCOHADA");
  const [cycle, setCycle] = useState("");
  const [lib, setLib] = useState<Library | null>(null);
  const [form, setForm] = useState({ assertion: "existence", type_test: "substantif", description: "" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    const l = await api<Library>(`/revision-programs?referentiel=${encodeURIComponent(ref)}`);
    setLib(l);
    setCycle((c) => c || l.cycles[0]?.code || "");
  }, [ref]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  if (!lib) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const names = Object.fromEntries(lib.assertions.map((a) => [a.code, a.libelle]));
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const add = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await post("/revision-programs", { referentiel: ref, cycle, ...form });
      setForm({ ...form, description: "" });
    });
  };
  const steps = lib.procedures.filter((p) => p.cycle === cycle);

  return (
    <section className="carte space-y-3" aria-labelledby="prog-titre">
      <h2 id="prog-titre" className="text-lg font-semibold">{t("programmes.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="flex flex-wrap items-end gap-3">
        <div><label htmlFor="prog-ref" className="etiquette">{t("programmes.referentiel")}</label>
          <select id="prog-ref" className="champ" value={ref} onChange={(e) => setRef(e.target.value)}><option value="SYSCOHADA">SYSCOHADA</option><option value="CIPRES">CIPRES</option></select></div>
        <div><label htmlFor="prog-cycle" className="etiquette">{t("programmes.cycle")}</label>
          <select id="prog-cycle" className="champ" value={cycle} onChange={(e) => setCycle(e.target.value)}>{lib.cycles.map((c) => <option key={c.code} value={c.code}>{c.libelle}</option>)}</select></div>
      </div>
      {lib.referentiel !== ref && <p className="text-sm text-slate-600">{t("programmes.repli", { ref, utilise: lib.referentiel })}</p>}
      <ol className="space-y-1 text-sm">
        {steps.map((s) => (
          <li key={s.id} className={`flex items-start justify-between gap-3 ${s.actif ? "" : "text-slate-400 line-through"}`}>
            <span><span className="mr-2 rounded bg-slate-100 px-1 text-xs">{names[s.assertion]}</span>{s.description}</span>
            {manager && <button type="button" className="shrink-0 text-xs underline" onClick={() => void run(() => patch(`/revision-programs/${s.id}`, { actif: !s.actif }))}>{s.actif ? t("programmes.desactiver") : t("programmes.reactiver")}</button>}
          </li>
        ))}
      </ol>
      {manager && (
        <form onSubmit={add} className="grid gap-2 md:grid-cols-4">
          <div><label htmlFor="prog-as" className="etiquette">{t("programmes.assertion")}</label><select id="prog-as" className="champ" value={form.assertion} onChange={(e) => setForm({ ...form, assertion: e.target.value })}>{lib.assertions.map((a) => <option key={a.code} value={a.code}>{a.libelle}</option>)}</select></div>
          <div><label htmlFor="prog-tt" className="etiquette">{t("programmes.typeTest")}</label><select id="prog-tt" className="champ" value={form.type_test} onChange={(e) => setForm({ ...form, type_test: e.target.value })}>{["substantif", "efficacite", "conception"].map((x) => <option key={x} value={x}>{t(`programmes.types.${x}`)}</option>)}</select></div>
          <div className="md:col-span-2"><label htmlFor="prog-desc" className="etiquette">{t("programmes.description")}</label><input id="prog-desc" className="champ" required minLength={10} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
          <div><button type="submit" className="btn-secondaire">{t("programmes.ajouter", { ref })}</button></div>
        </form>
      )}
    </section>
  );
}
