import type { ColDef, GridApi, IDatasource } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { AuditEntry, AuditPage, ChainReport } from "../api/types";
import Alert from "../components/Alert";
import { formatDateHeure, formatNombre, resumeJson } from "../lib/format";
import { AG_GRID_FR } from "../lib/grid";

const ACTIONS = ["create", "update", "delete", "login", "login_failed", "logout", "audit_chain_verified"];
const PAGE = 100;

export default function AuditLogPage() {
  const { t } = useTranslation();
  const gridApi = useRef<GridApi<AuditEntry> | null>(null);
  const [action, setAction] = useState("");
  const [total, setTotal] = useState<number | null>(null);
  const [report, setReport] = useState<ChainReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Chargement paginé côté serveur : la grille ne demande que les lignes affichées.
  const datasource = useMemo<IDatasource>(
    () => ({
      getRows: (params) => {
        const query = new URLSearchParams({
          offset: String(params.startRow),
          limit: String(params.endRow - params.startRow),
        });
        if (action) query.set("action", action);
        api<AuditPage>(`/audit-log?${query}`)
          .then((page) => {
            setTotal(page.total);
            params.successCallback(page.items, page.total);
          })
          .catch((e: Error) => {
            setError(e.message);
            params.failCallback();
          });
      },
    }),
    [action],
  );

  const verify = useCallback(async () => {
    setError(null);
    try {
      setReport(await api<ChainReport>("/audit-log/verify"));
      gridApi.current?.refreshInfiniteCache();
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const columns = useMemo<ColDef<AuditEntry>[]>(
    () => [
      { field: "seq", headerName: t("journal.seq"), width: 75 },
      {
        field: "horodatage",
        headerName: t("journal.horodatage"),
        width: 180,
        valueFormatter: (p) => formatDateHeure(p.value),
      },
      { field: "user_nom", headerName: t("journal.utilisateur"), width: 150 },
      {
        field: "action",
        headerName: t("journal.action"),
        width: 180,
        valueFormatter: (p) => (p.value ? t(`actions.${p.value}`, { defaultValue: p.value }) : ""),
      },
      {
        headerName: t("journal.objet"),
        width: 100,
        valueGetter: (p) => p.data?.object_type ?? "",
      },
      {
        field: "avant",
        headerName: t("journal.avant"),
        flex: 1,
        minWidth: 220,
        valueFormatter: (p) => resumeJson(p.value),
        tooltipValueGetter: (p) => resumeJson(p.value),
      },
      {
        field: "apres",
        headerName: t("journal.apres"),
        flex: 1,
        minWidth: 220,
        valueFormatter: (p) => resumeJson(p.value),
        tooltipValueGetter: (p) => resumeJson(p.value),
      },
      {
        field: "hash",
        headerName: t("journal.hash"),
        width: 130,
        valueFormatter: (p) => (p.value ? `${String(p.value).slice(0, 12)}…` : ""),
        tooltipField: "hash",
        cellClass: "font-mono",
      },
    ],
    [t],
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("journal.titre")}</h1>
        <p className="text-slate-600">{t("journal.intro")}</p>
      </header>
      {error && <Alert kind="erreur">{error}</Alert>}
      {report &&
        (report.ok ? (
          <Alert kind="succes">{t("journal.integre", { count: report.entries })}</Alert>
        ) : (
          <Alert kind="erreur">
            {t("journal.rompue", { seq: report.first_broken_seq, raison: report.reason })}
          </Alert>
        ))}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label htmlFor="filtre-action" className="etiquette">
            {t("journal.filtreAction")}
          </label>
          <select
            id="filtre-action"
            className="champ"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          >
            <option value="">{t("journal.toutes")}</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {t(`actions.${a}`)}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn-primaire" onClick={verify}>
          {t("journal.verifier")}
        </button>
        {total !== null && (
          <p className="text-sm text-slate-600">
            {t("journal.total", { count: total, formatted: formatNombre(total) })}
          </p>
        )}
      </div>
      <div className="ag-theme-quartz" style={{ height: 560 }}>
        <AgGridReact<AuditEntry>
          key={action}
          rowModelType="infinite"
          datasource={datasource}
          cacheBlockSize={PAGE}
          columnDefs={columns}
          localeText={AG_GRID_FR}
          onGridReady={(e) => {
            gridApi.current = e.api;
          }}
        />
      </div>
    </div>
  );
}
