import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { can } from "../lib/permissions";

export default function RequireAuth({
  children,
  permission,
}: {
  children: ReactNode;
  /** Un droit, ou une liste dont au moins un suffit. */
  permission?: string | string[];
}) {
  const { t } = useTranslation();
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <p className="p-8">{t("commun.chargement")}</p>;
  if (!user) return <Navigate to="/connexion" replace state={{ from: location.pathname }} />;
  // Rôle à double authentification obligatoire pas encore enrôlé.
  if (user.mfa_required && !user.mfa_enabled && location.pathname !== "/double-authentification") {
    return <Navigate to="/double-authentification" replace />;
  }
  const required = permission === undefined ? [] : [permission].flat();
  if (required.length && !required.some((p) => can(user.permissions, p))) {
    return (
      <p role="alert" className="alerte-erreur">
        {t("erreurs.403")}
      </p>
    );
  }
  return <>{children}</>;
}
