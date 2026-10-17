import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import MyProcedures from "../components/MyProcedures";
import { can, PERM } from "../lib/permissions";

const MODULES = ["socle", "m1", "m2", "m3", "m4", "m5", "m6"] as const;

export default function HomePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">
          {t("accueil.titre", { nom: user.nom })}
        </h1>
        <p className="text-slate-600">{t("accueil.role", { role: t(`roles.${user.role}`) })}</p>
      </header>
      {(can(user.permissions, PERM.MISSIONS_READ_OWN) || can(user.permissions, PERM.MISSIONS_READ_ALL)) && <MyProcedures />}
      <section aria-labelledby="modules" className="carte">
        <h2 id="modules" className="mb-4 text-lg font-semibold">
          {t("accueil.modules")}
        </h2>
        <ul className="divide-y divide-slate-200">
          {MODULES.map((m) => (
            <li key={m} className="flex items-center justify-between py-3 text-sm">
              <span>{t(`accueil.${m}`)}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  m === "socle" ? "bg-green-100 text-green-900" : "bg-slate-100 text-slate-700"
                }`}
              >
                {m === "socle" ? t("accueil.disponible") : t("accueil.bientot")}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
