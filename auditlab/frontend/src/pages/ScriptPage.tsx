import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, del, post, put } from "../api/client";
import type { Dataset, UploadInfo } from "../api/types";
import type {
  ScriptEntry,
  ScriptInfo,
  ScriptRunInfo,
  SdkFunction,
} from "../api/scripts";
import Alert from "../components/Alert";
import { RUN_BADGE } from "../components/mission/ScriptsTab";
import ProposeToLibrary from "../components/scripts/ProposeToLibrary";
import SchedulePanel from "../components/scripts/SchedulePanel";
import { useAuth } from "../auth/AuthContext";
import { formatDateHeure, formatNombre } from "../lib/format";
import { can } from "../lib/permissions";

const CodeEditor = lazy(() => import("../components/scripts/CodeEditor"));

/** Script Python d'une mission (DAT-26) : code, entrées, exécutions et leurs résultats. */
export default function ScriptPage() {
  const { t } = useTranslation();
  const { id, sid } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canEdit = can(user?.permissions, "data:analyze");
  const [script, setScript] = useState<ScriptInfo | null>(null);
  const [form, setForm] = useState<{
    nom: string;
    description: string;
    code: string;
    entrees: ScriptEntry[];
  } | null>(null);
  const [tables, setTables] = useState<Dataset[]>([]);
  const [files, setFiles] = useState<UploadInfo[]>([]);
  const [sdk, setSdk] = useState<SdkFunction[]>([]);
  const [runs, setRuns] = useState<ScriptRunInfo[]>([]);
  const [shown, setShown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const timer = useRef<number>();

  const loadRuns = useCallback(async () => {
    const list = await api<ScriptRunInfo[]>(`/scripts/${sid}/runs`);
    setRuns(list);
    window.clearTimeout(timer.current);
    if (list.some((r) => r.statut === "en_cours"))
      timer.current = window.setTimeout(() => void loadRuns(), 2000);
  }, [sid]);
  useEffect(() => {
    api<ScriptInfo>(`/scripts/${sid}`).then(
      (s) => {
        setScript(s);
        setForm({
          nom: s.nom,
          description: s.description ?? "",
          code: s.code,
          entrees: s.entrees,
        });
      },
      (e: Error) => setError(e.message),
    );
    api<Dataset[]>(`/engagements/${id}/datasets`).then(
      (d) => setTables(d.filter((x) => x.statut === "pret")),
      () => setTables([]),
    );
    api<UploadInfo[]>(`/engagements/${id}/uploads`).then(setFiles, () =>
      setFiles([]),
    );
    api<SdkFunction[]>("/scripts/api").then(setSdk, () => setSdk([]));
    loadRuns().catch((e: Error) => setError(e.message));
    return () => window.clearTimeout(timer.current);
  }, [id, sid, loadRuns]);

  if (!script || !form)
    return error ? <Alert kind="erreur">{error}</Alert> : null;
  const save = async () => {
    const body = {
      ...form,
      description: form.description || null,
      entrees: form.entrees.map(({ type, id: eid }) => ({ type, id: eid })),
    };
    const s = await put<ScriptInfo>(`/scripts/${sid}`, body);
    setScript(s);
  };
  const act = async (action: () => Promise<void>, done?: string) => {
    setError(null);
    setInfo(null);
    try {
      await action();
      if (done) setInfo(done);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const run = () =>
    act(async () => {
      await save();
      const r = await post<ScriptRunInfo>(`/scripts/${sid}/runs`);
      setShown(r.id);
      await loadRuns();
    });
  const toggle = (type: "table" | "fichier", eid: string, nom: string) => {
    const has = form.entrees.some((e) => e.id === eid);
    setForm({
      ...form,
      entrees: has
        ? form.entrees.filter((e) => e.id !== eid)
        : [...form.entrees, { type, id: eid, nom }],
    });
  };
  const current = runs.find((r) => r.id === shown) ?? runs[0];
  return (
    <div className="space-y-4">
      <Link
        to={`/missions/${id}?onglet=scripts`}
        className="text-sm text-marque-700 underline"
      >
        ← {t("scripts.retour")}
      </Link>
      <h1 className="text-xl font-semibold">{script.nom}</h1>
      {script.modele && (
        <p className="text-sm text-slate-600">
          {t("scripts.modele", {
            reference: script.modele.reference,
            version: script.modele.version,
          })}
        </p>
      )}
      {error && <Alert kind="erreur">{error}</Alert>}
      {info && <Alert kind="succes">{info}</Alert>}
      <section className="carte space-y-3" aria-labelledby="script-code">
        <h2 id="script-code" className="text-base font-semibold">
          {t("scripts.code")}
        </h2>
        <div className="grid gap-2 md:grid-cols-2">
          <label className="etiquette">
            {t("scripts.col.nom")}
            <input
              className="champ"
              value={form.nom}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, nom: e.target.value })}
            />
          </label>
          <label className="etiquette">
            {t("scripts.description")}
            <input
              className="champ"
              value={form.description}
              disabled={!canEdit}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
            />
          </label>
        </div>
        <Suspense
          fallback={
            <p className="text-sm text-slate-600">{t("scripts.chargement")}</p>
          }
        >
          <CodeEditor
            value={form.code}
            readOnly={!canEdit}
            label={t("scripts.code")}
            onChange={(code) => setForm({ ...form, code })}
          />
        </Suspense>
        <fieldset className="grid gap-3 md:grid-cols-2">
          <legend className="etiquette">{t("scripts.entrees")}</legend>
          <div className="space-y-1 text-sm">
            <p className="font-medium">{t("scripts.tables")}</p>
            {tables.length === 0 && <p className="text-slate-600">—</p>}
            {tables.map((d) => (
              <label key={d.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  disabled={!canEdit}
                  checked={form.entrees.some((e) => e.id === d.id)}
                  onChange={() => toggle("table", d.id, d.nom)}
                />
                {d.nom}
              </label>
            ))}
          </div>
          <div className="space-y-1 text-sm">
            <p className="font-medium">{t("scripts.fichiers")}</p>
            {files.length === 0 && <p className="text-slate-600">—</p>}
            {files.map((f) => (
              <label key={f.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  disabled={!canEdit}
                  checked={form.entrees.some((e) => e.id === f.id)}
                  onChange={() => toggle("fichier", f.id, f.nom_fichier)}
                />
                {f.nom_fichier}
              </label>
            ))}
          </div>
        </fieldset>
        {canEdit && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-secondaire"
              onClick={() => void act(save, t("scripts.enregistre"))}
            >
              {t("scripts.enregistrer")}
            </button>
            <button
              type="button"
              className="btn-primaire"
              onClick={() => void run()}
            >
              {t("scripts.executer")}
            </button>
            <button
              type="button"
              className="underline"
              onClick={() =>
                void act(async () => {
                  await del(`/scripts/${sid}`);
                  navigate(`/missions/${id}?onglet=scripts`);
                })
              }
            >
              {t("scripts.supprimer")}
            </button>
          </div>
        )}
      </section>
      <SchedulePanel script={script} canEdit={canEdit} onChange={setScript} />
      {can(user?.permissions, "data:publish_library") && (
        <ProposeToLibrary script={script} code={form.code} />
      )}
      <details className="carte">
        <summary className="cursor-pointer text-base font-semibold">
          {t("scripts.aide")}
        </summary>
        <dl className="mt-2 space-y-2 text-sm">
          {sdk.map((f) => (
            <div key={f.nom}>
              <dt className="font-mono text-marque-700">{f.signature}</dt>
              <dd className="whitespace-pre-line text-slate-700">{f.doc}</dd>
            </div>
          ))}
        </dl>
      </details>
      <section className="carte space-y-3" aria-labelledby="script-runs">
        <h2 id="script-runs" className="text-base font-semibold">
          {t("scripts.executions")}
        </h2>
        {runs.length === 0 ? (
          <p className="text-sm text-slate-600">
            {t("scripts.aucuneExecution")}
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {runs.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  className={`underline ${current?.id === r.id ? "font-semibold" : ""}`}
                  onClick={() => setShown(r.id)}
                >
                  {formatDateHeure(r.cree_le)} ·{" "}
                  {t(`scripts.declenchements.${r.declenchement}`)}
                  {r.par && ` · ${r.par}`}
                </button>{" "}
                <span
                  className={`rounded px-2 py-0.5 text-xs ${RUN_BADGE[r.statut]}`}
                >
                  {t(`scripts.statuts.${r.statut}`)}
                </span>
                {r.alerte && (
                  <span className="ml-1 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                    {t("scripts.alerte")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {current && (
          <div className="space-y-2 border-t pt-3 text-sm">
            <p className="text-slate-600">
              {t("scripts.empreinte", {
                sha: current.code_sha256.slice(0, 16),
                duree:
                  current.duree_ms === null
                    ? "—"
                    : formatNombre(current.duree_ms),
              })}
            </p>
            {current.alerte && (
              <Alert kind="info">
                {t("scripts.alerte")} : {current.alerte}
              </Alert>
            )}
            {current.erreur && (
              <pre className="whitespace-pre-wrap rounded bg-red-50 p-2 text-red-900">
                {current.erreur}
              </pre>
            )}
            {Object.keys(current.indicateurs).length > 0 && (
              <ul>
                {Object.entries(current.indicateurs).map(([k, v]) => (
                  <li key={k}>
                    <span className="font-medium">{k}</span> : {formatNombre(v)}
                  </li>
                ))}
              </ul>
            )}
            {current.tables.length > 0 && (
              <ul>
                {current.tables.map((d) => (
                  <li key={d.id}>
                    <Link
                      to={`/missions/${id}/donnees/${d.id}`}
                      className="text-marque-700 underline"
                    >
                      {d.nom}
                    </Link>{" "}
                    ({formatNombre(d.nb_lignes ?? 0)} {t("scripts.lignes")})
                  </li>
                ))}
              </ul>
            )}
            <p className="font-medium">{t("scripts.sortie")}</p>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-slate-900 p-2 text-xs text-slate-100">
              {current.sortie || "—"}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}
