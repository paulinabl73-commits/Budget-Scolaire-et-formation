import type { ColDef, GridApi, IDatasource, SortModelItem, ValueFormatterParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { download, post } from "../../api/client";
import type { Dataset } from "../../api/types";
import { formatDate, formatDateHeure, formatNombre } from "../../lib/format";
import { AG_GRID_FR } from "../../lib/grid";

const BLOCK = 200;

interface Page {
  colonnes: string[];
  lignes: unknown[][];
  total: number | null;
}

type Row = Record<string, unknown>;

function storageKey(id: string) {
  return `auditlab.grille.${id}.masquees`;
}

function readHidden(id: string): string[] {
  try {
    return JSON.parse(localStorage.getItem(storageKey(id)) ?? "[]") as string[];
  } catch {
    return [];
  }
}

/** Nombre de décimales d'un type Decimal(precision=18, scale=2). */
export function decimalScale(dtype: string): number | undefined {
  const m = /scale=(\d+)/.exec(dtype);
  return m ? Number(m[1]) : undefined;
}

function format(type: string, dtype: string, oui: string, non: string) {
  const scale = decimalScale(dtype);
  const decimal = scale !== undefined ? new Intl.NumberFormat("fr-FR", { minimumFractionDigits: scale, maximumFractionDigits: scale }) : null;
  return (p: ValueFormatterParams<Row>) => {
    const v = p.value;
    if (v === null || v === undefined) return "";
    if (decimal) return decimal.format(Number(v));
    if (type === "decimal" || type === "entier") return formatNombre(Number(v));
    if (type === "date") return formatDate(String(v));
    if (type === "date_heure") return formatDateHeure(String(v));
    if (type === "booleen") return v ? oui : non;
    return String(v);
  };
}

/** Grille virtualisée (DAT-07) : les lignes sont lues par blocs, triées et filtrées côté serveur. */
export default function DataGrid({ ds, onColumnFocus, onQuery }: {
  ds: Dataset;
  onColumnFocus?: (col: string) => void;
  onQuery?: (q: { filtres: Record<string, unknown>; recherche: string | null }) => void;
}) {
  const { t } = useTranslation();
  const apiRef = useRef<GridApi<Row> | null>(null);
  const [hidden, setHidden] = useState<string[]>(() => readHidden(ds.id));
  const [search, setSearch] = useState("");
  const [total, setTotal] = useState<number | null>(null);
  const searchRef = useRef("");
  const [exportError, setExportError] = useState<string | null>(null);

  const exportAs = async (format: "csv" | "xlsx") => {
    setExportError(null);
    const api = apiRef.current;
    const tri = (api?.getColumnState() ?? [])
      .filter((c) => c.sort)
      .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0))
      .map((c) => ({ colonne: c.colId, sens: c.sort }));
    try {
      await download(`/datasets/${ds.id}/export`, {
        format,
        tri,
        filtres: api?.getFilterModel() ?? {},
        recherche: searchRef.current || null,
        colonnes: ds.schema.filter((c) => !hidden.includes(c.nom)).map((c) => c.nom),
      }, `${ds.nom}.${format}`);
    } catch (e) {
      setExportError((e as Error).message);
    }
  };

  const visible = ds.schema.filter((c) => !hidden.includes(c.nom));

  const columnDefs = useMemo<ColDef<Row>[]>(
    () =>
      ds.schema.map((c) => {
        const numeric = c.type === "decimal" || c.type === "entier";
        const temporal = c.type === "date" || c.type === "date_heure";
        return {
          colId: c.nom,
          field: c.nom,
          headerName: c.nom,
          headerTooltip: t(`assistant.types.${c.type}`, { defaultValue: c.type }),
          hide: hidden.includes(c.nom),
          sortable: true,
          filter: numeric ? "agNumberColumnFilter" : temporal ? "agDateColumnFilter" : "agTextColumnFilter",
          filterParams: { maxNumConditions: 2, buttons: ["reset", "apply"], closeOnApply: true },
          valueFormatter: format(c.type, c.dtype, t("commun.oui"), t("commun.non")),
          cellClass: numeric ? "text-right font-mono" : undefined,
          type: numeric ? "rightAligned" : undefined,
        };
      }),
    [ds.schema, hidden, t],
  );

  const datasource = useMemo<IDatasource>(
    () => ({
      getRows: (params) => {
        const tri = (params.sortModel as SortModelItem[]).map((s) => ({ colonne: s.colId, sens: s.sort }));
        if (params.startRow === 0) onQuery?.({ filtres: params.filterModel, recherche: searchRef.current || null });
        const colonnes = ds.schema.filter((c) => !hidden.includes(c.nom)).map((c) => c.nom);
        post<Page>(`/datasets/${ds.id}/rows`, {
          offset: params.startRow,
          limit: params.endRow - params.startRow,
          tri,
          filtres: params.filterModel,
          recherche: searchRef.current || null,
          colonnes,
          total: params.startRow === 0,
        })
          .then((page) => {
            const rows = page.lignes.map((l) => Object.fromEntries(page.colonnes.map((c, i) => [c, l[i]])));
            if (page.total !== null) setTotal(page.total);
            const last = rows.length < params.endRow - params.startRow ? params.startRow + rows.length : -1;
            params.successCallback(rows, page.total ?? last);
          })
          .catch(() => params.failCallback());
      },
    }),
    [ds.id, ds.schema, hidden, onQuery],
  );

  // Recherche globale : relance la lecture après une courte pause.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchRef.current !== search) {
        searchRef.current = search;
        apiRef.current?.purgeInfiniteCache();
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [search]);

  const toggle = (col: string) => {
    const next = hidden.includes(col) ? hidden.filter((c) => c !== col) : [...hidden, col];
    if (next.length >= ds.schema.length) return; // au moins une colonne visible
    setHidden(next);
    try {
      localStorage.setItem(storageKey(ds.id), JSON.stringify(next));
    } catch {
      /* préférence non conservée */
    }
  };

  return (
    <section className="carte space-y-2" aria-labelledby="grille-titre">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="grille-titre" className="text-base font-semibold">
          {t("grille.titre")}
          {total !== null && <span className="ml-2 text-sm font-normal text-slate-600">{t("grille.lignes", { n: formatNombre(total) })}</span>}
        </h2>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="grille-recherche" className="etiquette">{t("grille.recherche")}</label>
            <input id="grille-recherche" type="search" className="champ mt-0" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <details className="relative">
            <summary className="btn-secondaire cursor-pointer list-none">
              {t("grille.colonnes", { visibles: visible.length, total: ds.schema.length })}
            </summary>
            <fieldset className="absolute right-0 z-20 mt-1 max-h-72 w-64 overflow-auto rounded border border-slate-200 bg-white p-2 shadow">
              <legend className="sr-only">{t("grille.masquer")}</legend>
              {ds.schema.map((c) => (
                <label key={c.nom} className="flex items-center gap-2 py-0.5 text-sm">
                  <input type="checkbox" checked={!hidden.includes(c.nom)} onChange={() => toggle(c.nom)} />
                  <span className="truncate" title={c.nom}>{c.nom}</span>
                </label>
              ))}
            </fieldset>
          </details>
          <button type="button" className="btn-secondaire" onClick={() => apiRef.current?.setFilterModel(null)}>
            {t("grille.effacerFiltres")}
          </button>
          <button type="button" className="btn-secondaire" onClick={() => exportAs("xlsx")}>{t("grille.exporterExcel")}</button>
          <button type="button" className="btn-secondaire" onClick={() => exportAs("csv")}>{t("grille.exporterCsv")}</button>
        </div>
      </div>
      {exportError && <p role="alert" className="text-sm text-red-700">{exportError}</p>}
      <div className="ag-theme-quartz" style={{ height: 560 }}>
        <AgGridReact<Row>
          key={hidden.join("|")}
          columnDefs={columnDefs}
          rowModelType="infinite"
          datasource={datasource}
          cacheBlockSize={BLOCK}
          maxBlocksInCache={50}
          localeText={AG_GRID_FR}
          suppressFieldDotNotation
          onGridReady={(e) => (apiRef.current = e.api)}
          onCellFocused={(e) => {
            const col = e.column && typeof e.column !== "string" ? e.column.getColId() : null;
            if (col) onColumnFocus?.(col);
          }}
          defaultColDef={{ resizable: true, minWidth: 110 }}
        />
      </div>
    </section>
  );
}
