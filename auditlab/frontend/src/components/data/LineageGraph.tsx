import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, post } from "../../api/client";
import type { Dataset } from "../../api/types";
import { formatDateHeure, formatNombre } from "../../lib/format";
import Alert from "../Alert";
import { SaveMacro } from "./MacroPanel";

interface Node {
  id: string;
  nom: string;
  kind: string;
  operation: string;
  parametres: Record<string, unknown>;
  nb_lignes: number | null;
  empreinte: string | null;
  niveau: number;
  created_at: string | null;
}

interface Graph {
  noeuds: Node[];
  aretes: { de: string; vers: string }[];
}

interface ReplayResult {
  identique: boolean;
  erreur?: string;
  etapes: { id: string; nom: string; identique: boolean | null }[];
}

const W = 200;
const H = 64;
const GX = 70;
const GY = 24;

/** Graphe de lignée (DAT-24) et rejeu depuis la source (NF-04). */
export default function LineageGraph({ ds, canEdit = false }: { ds: Dataset; canEdit?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [graph, setGraph] = useState<Graph | null>(null);
  const [replay, setReplay] = useState<ReplayResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Graph>(`/datasets/${ds.id}/lineage`).then(setGraph).catch((e: Error) => setError(e.message));
  }, [ds.id]);

  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!graph) return null;
  const columns = new Map<number, Node[]>();
  graph.noeuds.forEach((n) => columns.set(n.niveau, [...(columns.get(n.niveau) ?? []), n]));
  const pos = new Map<string, { x: number; y: number }>();
  columns.forEach((nodes, level) => nodes.forEach((n, i) => pos.set(n.id, { x: level * (W + GX), y: i * (H + GY) })));
  const width = Math.max(...[...pos.values()].map((p) => p.x)) + W + 2;
  const height = Math.max(...[...pos.values()].map((p) => p.y)) + H + 2;
  const label = (n: Node) =>
    n.kind === "analyse" ? t(`analyses.${n.operation}.titre`, { defaultValue: n.operation }) : t(`donnees.kinds.${n.kind}`);

  const run = async () => {
    setBusy(true);
    setReplay(null);
    try {
      setReplay(await post<ReplayResult>(`/datasets/${ds.id}/replay`, {}));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="carte space-y-3" aria-labelledby="lignee-titre">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="lignee-titre" className="text-base font-semibold">{t("lignee.titre")}</h2>
        <button type="button" className="btn-secondaire" onClick={run} disabled={busy}>
          {busy ? t("lignee.rejeuEnCours") : t("lignee.rejouer")}
        </button>
      </div>
      {replay && (
        <Alert kind={replay.identique ? "succes" : "erreur"}>
          {replay.erreur ?? (replay.identique ? t("lignee.identique", { n: replay.etapes.length }) : t("lignee.different", {
            tables: replay.etapes.filter((s) => s.identique === false).map((s) => s.nom).join(", "),
          }))}
        </Alert>
      )}
      <div className="overflow-x-auto">
        <svg width={width} height={height} role="group" aria-label={t("lignee.graphe")}>
          <defs>
            <marker id="fleche" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="#64748b" />
            </marker>
          </defs>
          {graph.aretes.map((e) => {
            const a = pos.get(e.de);
            const b = pos.get(e.vers);
            if (!a || !b) return null;
            return <line key={`${e.de}-${e.vers}`} x1={a.x + W} y1={a.y + H / 2} x2={b.x} y2={b.y + H / 2} stroke="#64748b" markerEnd="url(#fleche)" />;
          })}
          {graph.noeuds.map((n) => {
            const p = pos.get(n.id)!;
            const current = n.id === ds.id;
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} className="cursor-pointer" role="link" tabIndex={0}
                onClick={() => navigate(`/missions/${ds.engagement_id}/donnees/${n.id}`)}
                onKeyDown={(e) => e.key === "Enter" && navigate(`/missions/${ds.engagement_id}/donnees/${n.id}`)}>
                <title>{`${n.nom}\n${formatDateHeure(n.created_at)}\n${n.empreinte ?? ""}`}</title>
                <rect width={W} height={H} rx="6" fill={current ? "#dbeafe" : "#fff"} stroke={current ? "#1d4ed8" : "#94a3b8"} />
                <text x="8" y="20" fontSize="12" fontWeight="600">{n.nom.length > 28 ? `${n.nom.slice(0, 27)}…` : n.nom}</text>
                <text x="8" y="38" fontSize="11" fill="#475569">{label(n)}</text>
                <text x="8" y="54" fontSize="11" fill="#475569">
                  {n.nb_lignes !== null ? t("table.lignes", { n: formatNombre(n.nb_lignes) }) : ""}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      {canEdit && ds.kind !== "import" && <SaveMacro ds={ds} />}
    </section>
  );
}
