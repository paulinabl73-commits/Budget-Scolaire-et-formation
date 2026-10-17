import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { Route, Routes } from "react-router-dom";

import RequireAuth from "./components/RequireAuth";
import Layout from "./components/Layout";
import { PERM } from "./lib/permissions";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import MfaSetupPage from "./pages/MfaSetupPage";
import ProfilePage from "./pages/ProfilePage";

// Pages avec AG Grid chargées à la demande.
const AuditLogPage = lazy(() => import("./pages/AuditLogPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));

export default function App() {
  const { t } = useTranslation();
  return (
    <Suspense fallback={<p className="p-8">{t("commun.chargement")}</p>}>
    <Routes>
      <Route path="/connexion" element={<LoginPage />} />
      <Route
        path="/double-authentification"
        element={
          <RequireAuth>
            <MfaSetupPage />
          </RequireAuth>
        }
      />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<HomePage />} />
        <Route
          path="utilisateurs"
          element={
            <RequireAuth permission={PERM.USERS_MANAGE}>
              <UsersPage />
            </RequireAuth>
          }
        />
        <Route
          path="journal"
          element={
            <RequireAuth permission={PERM.AUDIT_LOG_READ}>
              <AuditLogPage />
            </RequireAuth>
          }
        />
        <Route path="profil" element={<ProfilePage />} />
        <Route path="*" element={<p className="alerte-erreur">{t("erreurs.404")}</p>} />
      </Route>
    </Routes>
    </Suspense>
  );
}
