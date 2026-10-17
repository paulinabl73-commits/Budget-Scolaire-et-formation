import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { post } from "../../api/client";
import type { UploadInfo } from "../../api/types";
import Alert from "../Alert";

export interface WizardOptions {
  format: string;
  encodage?: string;
  separateur?: string;
  entete?: boolean;
  decimal?: string;
  milliers?: string;
  format_date?: string;
  feuille?: string | number | null;
  feuilles?: string[];
  lignes_ignorees?: number;
  colonnes: { nom: string; type?: string | null; debut?: number | null; fin?: number | null }[];
  [key: string]: unknown;
}

export interface Preview {
  colonnes: { nom: string; type: string }[];
  lignes: unknown[][];
  lignes_brutes: unknown[][];
  avertissements: Record<string, number>;
}

const TYPES = ["texte", "entier", "decimal", "date", "booleen"];
const DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d", "%d/%m/%y"];

interface Props {
  upload: UploadInfo;
  initial: WizardOptions;
  initialPreview: Preview;
  onImport: (options: WizardOptions) => void;
  onCancel: () => void;
}

/** Assistant d'import (DAT-02) : options détectées, types par colonne, aperçu de 100 lignes. */
export default function ImportWizard({ upload, initial, initialPreview, onImport, onCancel }: Props) {
  const { t } = useTranslation();
  const [opts, setOpts] = useState<WizardOptions>(initial);
  const [preview, setPreview] = useState<Preview>(initialPreview);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<WizardOptions>) => setOpts((o) => ({ ...o, ...patch }));
  const textual = ["csv", "txt"].includes(opts.format);
  const fixed = opts.format === "txt_fixe";
  const excel = ["xlsx", "xls"].includes(opts.format);

  // Colonnes connues : celles des options, sinon celles de l'aperçu (Excel, JSON, Parquet).
  useEffect(() => {
    if (!fixed && opts.colonnes.length === 0 && preview.colonnes.length) {
      set({ colonnes: preview.colonnes.map((c) => ({ nom: c.nom, type: null })) });
    }
  }, [preview.colonnes]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = async () => {
    setError(null);
    try {
      setPreview(await post<Preview>(`/uploads/${upload.id}/preview`, payload(opts)));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="space-y-4 rounded-md border border-marque-100 bg-marque-50/40 p-4">
      <h3 className="font-semibold">{t("assistant.titre", { fichier: upload.nom_fichier })}</h3>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {(textual || fixed) && (
          <Field id="w-enc" label={t("assistant.encodage")}>
            <select id="w-enc" className="champ" value={opts.encodage} onChange={(e) => set({ encodage: e.target.value })}>
              {["utf-8", "cp1252", "latin-1"].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </Field>
        )}
        {textual && (
          <Field id="w-sep" label={t("assistant.separateur")}>
            <select id="w-sep" className="champ" value={opts.separateur} onChange={(e) => set({ separateur: e.target.value })}>
              {[";", ",", "\t", "|"].map((v) => <option key={v} value={v}>{t(`assistant.separateurs.${v}`)}</option>)}
            </select>
          </Field>
        )}
        {(textual || fixed) && (
          <>
            <Field id="w-dec" label={t("assistant.decimal")}>
              <select id="w-dec" className="champ" value={opts.decimal ?? ","} onChange={(e) => set({ decimal: e.target.value })}>
                <option value=",">,</option>
                <option value=".">.</option>
              </select>
            </Field>
            <Field id="w-mil" label={t("assistant.milliers")}>
              <select id="w-mil" className="champ" value={opts.milliers ?? " "} onChange={(e) => set({ milliers: e.target.value })}>
                {[" ", ".", "", "'"].map((v) => <option key={v} value={v}>{t(`assistant.milliersOptions.${v}`)}</option>)}
              </select>
            </Field>
            <Field id="w-date" label={t("assistant.formatDate")}>
              <select id="w-date" className="champ" value={opts.format_date ?? "%d/%m/%Y"} onChange={(e) => set({ format_date: e.target.value })}>
                {DATE_FORMATS.map((v) => (
                  <option key={v} value={v}>
                    {v.replace("%d", "jj").replace("%m", "mm").replace("%Y", "aaaa").replace("%y", "aa")}
                  </option>
                ))}
              </select>
            </Field>
            <Field id="w-skip" label={t("assistant.lignesIgnorees")}>
              <input id="w-skip" type="number" min={0} className="champ" value={opts.lignes_ignorees ?? 0}
                onChange={(e) => set({ lignes_ignorees: Number(e.target.value) })} />
            </Field>
          </>
        )}
        {excel && (
          <Field id="w-sheet" label={t("assistant.feuille")}>
            <select id="w-sheet" className="champ" value={String(opts.feuille ?? "")}
              onChange={(e) => set({ feuille: e.target.value, colonnes: [] })}>
              {(opts.feuilles ?? []).map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </Field>
        )}
        {(textual || excel || fixed) && (
          <label className="col-span-2 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={opts.entete ?? true} onChange={(e) => set({ entete: e.target.checked })} />
            {t("assistant.entete")}
          </label>
        )}
      </div>

      {fixed ? (
        <FixedColumns opts={opts} set={set} raw={preview.lignes_brutes} />
      ) : (
        opts.colonnes.length > 0 && (
          <fieldset>
            <legend className="etiquette mb-1">{t("assistant.colonnes")}</legend>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              {opts.colonnes.map((c, i) => (
                <label key={c.nom} className="text-xs">
                  <span className="block truncate font-medium" title={c.nom}>{c.nom}</span>
                  <select className="champ mt-0.5 py-1" value={c.type ?? ""}
                    onChange={(e) => set({ colonnes: opts.colonnes.map((x, j) => (j === i ? { ...x, type: e.target.value || null } : x)) })}>
                    {!textual && <option value="">{t("assistant.typeOrigine")}</option>}
                    {TYPES.map((ty) => <option key={ty} value={ty}>{t(`assistant.types.${ty}`)}</option>)}
                  </select>
                </label>
              ))}
            </div>
          </fieldset>
        )
      )}

      {Object.entries(preview.avertissements).map(([col, n]) => (
        <Alert key={col} kind="erreur">{t("assistant.avertissement", { colonne: col, nombre: n })}</Alert>
      ))}
      <div className="flex gap-2">
        <button type="button" className="btn-secondaire" onClick={refresh}>{t("assistant.actualiser")}</button>
        <button type="button" className="btn-primaire" onClick={() => onImport(payload(opts))}>{t("assistant.importer")}</button>
        <button type="button" className="btn-secondaire" onClick={onCancel}>{t("assistant.annuler")}</button>
      </div>

      {preview.colonnes.length > 0 && (
        <div>
          <p className="etiquette mb-1">{t("assistant.apercu")}</p>
          <div className="max-h-80 overflow-auto rounded border border-slate-200 bg-white">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-100">
                <tr>
                  {preview.colonnes.map((c) => (
                    <th key={c.nom} scope="col" className="whitespace-nowrap px-2 py-1 text-left">
                      {c.nom} <span className="font-normal text-slate-500">({t(`assistant.types.${c.type}`)})</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.lignes.map((row, i) => (
                  <tr key={i} className="odd:bg-slate-50">
                    {row.map((v, j) => (
                      <td key={j}
                        className={`whitespace-nowrap px-2 py-0.5 ${["decimal", "entier"].includes(preview.colonnes[j]?.type) ? "text-right font-mono" : ""}`}>
                        {v === null ? <span className="text-slate-400">∅</span> : String(v)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="etiquette">{label}</label>
      {children}
    </div>
  );
}

function FixedColumns({ opts, set, raw }: { opts: WizardOptions; set: (p: Partial<WizardOptions>) => void; raw: unknown[][] }) {
  const { t } = useTranslation();
  const cols = opts.colonnes;
  const update = (i: number, patch: Record<string, unknown>) =>
    set({ colonnes: cols.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  return (
    <div className="space-y-2">
      {raw.length > 0 && (
        <div>
          <p className="etiquette">{t("assistant.lignesBrutes")}</p>
          <pre className="max-h-40 overflow-auto rounded border border-slate-200 bg-white p-2 text-xs">
            {"         1         2         3         4         5         6\n123456789012345678901234567890123456789012345678901234567890\n"}
            {raw.map((r) => String(r[0])).join("\n")}
          </pre>
        </div>
      )}
      <p className="etiquette">{t("assistant.largeurFixe")}</p>
      {cols.map((c, i) => (
        <div key={i} className="flex items-end gap-2">
          <input aria-label={t("assistant.colonnes")} className="champ mt-0 flex-1" value={c.nom}
            onChange={(e) => update(i, { nom: e.target.value })} />
          <input aria-label={t("assistant.debut")} type="number" min={1} className="champ mt-0 w-20" value={c.debut ?? ""}
            onChange={(e) => update(i, { debut: Number(e.target.value) })} />
          <input aria-label={t("assistant.fin")} type="number" min={1} className="champ mt-0 w-20" value={c.fin ?? ""}
            onChange={(e) => update(i, { fin: Number(e.target.value) })} />
          <select aria-label={t("assistant.type")} className="champ mt-0 w-32" value={c.type ?? "texte"}
            onChange={(e) => update(i, { type: e.target.value })}>
            {TYPES.map((ty) => <option key={ty} value={ty}>{t(`assistant.types.${ty}`)}</option>)}
          </select>
        </div>
      ))}
      <button type="button" className="text-sm text-marque-700 underline"
        onClick={() => set({ colonnes: [...cols, { nom: `colonne_${cols.length + 1}`, debut: null, fin: null, type: "texte" }] })}>
        {t("assistant.ajouterColonne")}
      </button>
    </div>
  );
}

function payload(opts: WizardOptions): WizardOptions {
  const rest = { ...opts };
  delete rest.feuilles;
  return { ...rest, colonnes: opts.colonnes.filter((c) => c.nom) };
}
