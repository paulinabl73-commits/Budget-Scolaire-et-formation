import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import NotificationBell from "./NotificationBell";
import { can, PERM } from "../lib/permissions";

const lien = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-3 py-2 text-sm font-medium ${
    isActive ? "bg-marque-700 text-white" : "text-marque-50 hover:bg-marque-700/60"
  }`;

export default function Layout() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/connexion");
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <a
        href="#contenu"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2"
      >
        {t("app.allerAuContenu")}
      </a>
      <aside className="flex w-60 flex-col bg-marque-900 px-3 py-5">
        <div className="mb-6 px-3">
          <p className="text-lg font-semibold text-white">{t("app.nom")}</p>
          <p className="text-xs text-marque-100">{t("app.baseline")}</p>
        </div>
        <nav aria-label={t("nav.principale")} className="flex-1 space-y-1">
          <NavLink to="/" end className={lien}>
            {t("nav.accueil")}
          </NavLink>
          {can(user?.permissions, PERM.PLAN_READ) && (
            <NavLink to="/univers" className={lien}>
              {t("nav.univers")}
            </NavLink>
          )}
          {can(user?.permissions, PERM.PLAN_READ) && (
            <NavLink to="/carte-des-risques" className={lien}>
              {t("nav.carte")}
            </NavLink>
          )}
          {can(user?.permissions, PERM.PLAN_READ) && (
            <NavLink to="/plan" className={lien}>
              {t("nav.plan")}
            </NavLink>
          )}
          {(can(user?.permissions, PERM.MISSIONS_READ_ALL) ||
            can(user?.permissions, PERM.MISSIONS_READ_OWN)) && (
            <NavLink to="/missions" className={lien}>
              {t("nav.missions")}
            </NavLink>
          )}
          {(can(user?.permissions, PERM.PORTFOLIO_MANAGE) || user?.role === "collaborateur_comptable") && (
            <NavLink to="/portefeuille" className={lien}>
              {t("nav.portefeuille")}
            </NavLink>
          )}
          {(can(user?.permissions, PERM.MISSIONS_READ_ALL) ||
            can(user?.permissions, PERM.MISSIONS_READ_OWN)) && (
            <NavLink to="/bibliotheque" className={lien}>
              {t("nav.bibliotheque")}
            </NavLink>
          )}
          {(can(user?.permissions, PERM.SETTINGS_MANAGE) ||
            can(user?.permissions, PERM.PLAN_MANAGE)) && (
            <NavLink to="/criteres" className={lien}>
              {t("nav.criteres")}
            </NavLink>
          )}
          {(can(user?.permissions, PERM.SETTINGS_MANAGE) ||
            can(user?.permissions, PERM.PLAN_MANAGE)) && (
            <NavLink to="/marques" className={lien}>
              {t("nav.marques")}
            </NavLink>
          )}
          {can(user?.permissions, PERM.USERS_MANAGE) && (
            <NavLink to="/utilisateurs" className={lien}>
              {t("nav.utilisateurs")}
            </NavLink>
          )}
          {(can(user?.permissions, PERM.REVISION_READ) || can(user?.permissions, PERM.FRAMEWORKS_MANAGE)) && (
            <NavLink to="/referentiels" className={lien}>
              {t("nav.referentiels")}
            </NavLink>
          )}
          {can(user?.permissions, PERM.AUDIT_LOG_READ) && (
            <NavLink to="/journal" className={lien}>
              {t("nav.journal")}
            </NavLink>
          )}
          <NavLink to="/profil" className={lien}>
            {t("nav.profil")}
          </NavLink>
        </nav>
        <div className="border-t border-marque-700 px-3 pt-4 text-sm text-marque-50">
          <p className="font-medium">{user?.nom}</p>
          <p className="text-xs text-marque-100">{user && t(`roles.${user.role}`)}</p>
          <NotificationBell />
          <button type="button" onClick={onLogout} className="mt-3 text-sm underline">
            {t("nav.deconnexion")}
          </button>
        </div>
      </aside>
      <main id="contenu" className="flex-1 overflow-auto p-8" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
