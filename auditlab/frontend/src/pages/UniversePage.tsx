import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { api, del, patch, post } from "../api/client";
import type { AuditableEntity } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import AssessmentPanel from "../components/AssessmentPanel";
import EntityForm, { draftToPayload, toDraft } from "../components/EntityForm";
import type { EntityDraft } from "../components/EntityForm";
import EntityTree from "../components/EntityTree";
import { formatDate } from "../lib/format";
import { can, PERM } from "../lib/permissions";
import { buildTree, descendantIds } from "../lib/tree";

type Mode = { kind: "view" } | { kind: "create"; parentId: string | null };

export default function UniversePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canManage = can(user?.permissions, PERM.PLAN_MANAGE);
  const [entities, setEntities] = useState<AuditableEntity[]>([]);
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(params.get("entite"));
  const [mode, setMode] = useState<Mode>({ kind: "view" });
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(
    null,
  );

  const load = useCallback(async () => {
    setEntities(await api<AuditableEntity[]>("/universe/entities"));
  }, []);

  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const tree = useMemo(() => buildTree(entities), [entities]);
  const selected = entities.find((e) => e.id === selectedId) ?? null;
  const parentsFor = useMemo(() => {
    const forbidden = selected && mode.kind === "view" ? descendantIds(entities, selected.id) : new Set<string>();
    return entities.filter((e) => !forbidden.has(e.id)).sort((a, b) => a.nom.localeCompare(b.nom, "fr"));
  }, [entities, selected, mode.kind]);
  const draft = useMemo(
    () => (mode.kind === "create" ? toDraft(null, mode.parentId) : toDraft(selected)),
    [mode, selected],
  );

  const run = async <T,>(
    action: () => Promise<T>,
    success: string,
  ): Promise<{ ok: true; value: T } | { ok: false }> => {
    setMessage(null);
    try {
      const value = await action();
      setMessage({ kind: "succes", text: success });
      await load();
      return { ok: true, value };
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
      return { ok: false };
    }
  };

  const onSubmit = async (d: EntityDraft) => {
    if (mode.kind === "create") {
      const created = await run(
        () => post<AuditableEntity>("/universe/entities", draftToPayload(d)),
        t("univers.enregistree"),
      );
      if (created.ok) {
        setSelectedId(created.value.id);
        setMode({ kind: "view" });
      }
    } else if (selected) {
      await run(() => patch(`/universe/entities/${selected.id}`, draftToPayload(d)), t("univers.enregistree"));
    }
  };

  const onDelete = async () => {
    if (!selected || !window.confirm(t("univers.confirmerSuppression", { nom: selected.nom }))) return;
    const done = await run(() => del(`/universe/entities/${selected.id}`), t("univers.supprimee"));
    if (done.ok) setSelectedId(null);
  };

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t("univers.titre")}</h1>
          <p className="text-slate-600">{t("univers.intro")}</p>
        </div>
        {canManage && (
          <button type="button" className="btn-primaire"
            onClick={() => setMode({ kind: "create", parentId: null })}>
            {t("univers.nouvelle")}
          </button>
        )}
      </header>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <section className="carte lg:col-span-2">
          {entities.length === 0 ? (
            <p className="text-sm text-slate-600">{t("univers.vide")}</p>
          ) : (
            <EntityTree nodes={tree} selectedId={selectedId}
              onSelect={(id) => { setSelectedId(id); setMode({ kind: "view" }); }} />
          )}
        </section>
        <section className="carte space-y-4 lg:col-span-3" aria-live="polite">
          {mode.kind === "create" ? (
            <>
              <h2 className="text-lg font-semibold">{t("univers.nouvelle")}</h2>
              <EntityForm initial={draft} parents={parentsFor} readOnly={false}
                onSubmit={onSubmit} onCancel={() => setMode({ kind: "view" })} />
            </>
          ) : selected ? (
            <>
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-lg font-semibold">{selected.nom}</h2>
                  <p className="text-sm text-slate-600">
                    {t("univers.dernierAudit")} :{" "}
                    {selected.date_dernier_audit ? formatDate(selected.date_dernier_audit) : t("univers.jamaisAudite")}
                    {" · "}
                    {t("univers.score")} :{" "}
                    {selected.score_risque !== null
                      ? selected.score_risque.toLocaleString("fr-FR")
                      : t("univers.nonEvalue")}
                  </p>
                </div>
                {canManage && (
                  <div className="flex gap-2">
                    <button type="button" className="btn-secondaire"
                      onClick={() => setMode({ kind: "create", parentId: selected.id })}>
                      {t("univers.nouvelleSous")}
                    </button>
                    <button type="button" className="btn-danger" onClick={onDelete}>
                      {t("commun.supprimer")}
                    </button>
                  </div>
                )}
              </div>
              <EntityForm initial={draft} parents={parentsFor} readOnly={!canManage} onSubmit={onSubmit} />
              <AssessmentPanel entity={selected} canManage={canManage} onSaved={() => void load()} />
            </>
          ) : (
            <p className="text-sm text-slate-600">{t("univers.selectionner")}</p>
          )}
        </section>
      </div>
    </div>
  );
}
