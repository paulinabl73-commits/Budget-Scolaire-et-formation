import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { AuditableEntity } from "../api/types";
import type { TreeNode } from "../lib/tree";

interface Props {
  nodes: TreeNode<AuditableEntity>[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function EntityTree({ nodes, selectedId, onSelect }: Props) {
  const { t } = useTranslation();
  return (
    <ul role="tree" aria-label={t("univers.arbre")} className="space-y-0.5 text-sm">
      {nodes.map((n) => (
        <Node key={n.item.id} node={n} level={1} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </ul>
  );
}

function Node({
  node,
  level,
  selectedId,
  onSelect,
}: {
  node: TreeNode<AuditableEntity>;
  level: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  const { item, children } = node;
  const selected = item.id === selectedId;

  return (
    <li
      role="treeitem"
      aria-level={level}
      aria-selected={selected}
      aria-expanded={children.length ? open : undefined}
    >
      <div className="flex items-center" style={{ paddingLeft: `${(level - 1) * 1.1}rem` }}>
        {children.length > 0 ? (
          <button
            type="button"
            className="mr-1 h-6 w-6 rounded text-slate-600 hover:bg-slate-200"
            aria-label={t(open ? "univers.replier" : "univers.deplier", { nom: item.nom })}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="mr-1 inline-block w-6" aria-hidden />
        )}
        <button
          type="button"
          onClick={() => onSelect(item.id)}
          className={`flex flex-1 items-center justify-between rounded px-2 py-1 text-left ${
            selected ? "bg-marque-600 text-white" : "hover:bg-slate-100"
          }`}
        >
          <span>
            {item.nom}
            <span className={`ml-2 text-xs ${selected ? "text-marque-50" : "text-slate-600"}`}>
              {t(`univers.types.${item.type}`)}
            </span>
          </span>
          {item.score_risque !== null && (
            <span className="ml-2 text-xs font-semibold">
              {item.score_risque.toLocaleString("fr-FR")}
            </span>
          )}
        </button>
      </div>
      {children.length > 0 && open && (
        <ul role="group" className="space-y-0.5">
          {children.map((c) => (
            <Node
              key={c.item.id}
              node={c}
              level={level + 1}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
