import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, post } from "../api/client";
import type { AppNotification } from "../api/types";
import { formatDateHeure } from "../lib/format";

const POLL_MS = 60_000;

export default function NotificationBell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<AppNotification[]>([]);

  const load = useCallback(async () => {
    const page = await api<{ non_lues: number; items: AppNotification[] }>("/me/notifications");
    setUnread(page.non_lues);
    setItems(page.items);
  }, []);

  useEffect(() => {
    load().catch(() => undefined);
    const timer = window.setInterval(() => load().catch(() => undefined), POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const openItem = async (n: AppNotification) => {
    if (!n.lue_le) await post(`/me/notifications/${n.id}/read`).catch(() => undefined);
    setOpen(false);
    await load();
    if (n.lien) navigate(n.lien);
  };

  return (
    <div className="relative">
      <button type="button" className="relative mt-3 flex items-center gap-2 text-sm underline"
        aria-expanded={open} aria-label={t("notifications.nonLues", { count: unread })} onClick={() => setOpen((v) => !v)}>
        {t("notifications.titre")}
        {unread > 0 && <span className="rounded-full bg-red-600 px-2 text-xs font-semibold text-white no-underline">{unread}</span>}
      </button>
      {open && (
        <div role="dialog" aria-label={t("notifications.titre")}
          className="absolute bottom-10 left-0 z-20 w-96 rounded-md border border-slate-200 bg-white p-3 text-slate-900 shadow-lg">
          <div className="mb-2 flex items-center justify-between">
            <p className="font-semibold">{t("notifications.titre")}</p>
            {unread > 0 && (
              <button type="button" className="text-xs text-marque-700 underline"
                onClick={async () => { await post("/me/notifications/read-all"); await load(); }}>
                {t("notifications.toutLu")}
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="text-sm text-slate-600">{t("notifications.aucune")}</p>
          ) : (
            <ul className="max-h-96 space-y-2 overflow-y-auto">
              {items.map((n) => (
                <li key={n.id} className={`rounded p-2 text-sm ${n.lue_le ? "" : "bg-marque-50"}`}>
                  <button type="button" className="w-full text-left" onClick={() => openItem(n)}>
                    <p className="font-medium">{n.titre}</p>
                    <p className="text-xs text-slate-700">{n.message}</p>
                    <p className="mt-0.5 text-[11px] text-slate-600">{formatDateHeure(n.created_at)}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
