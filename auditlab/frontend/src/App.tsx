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
const UniversePage = lazy(() => import("./pages/UniversePage"));
const CriteriaPage = lazy(() => import("./pages/CriteriaPage"));
const RiskMapPage = lazy(() => import("./pages/RiskMapPage"));
const PlanPage = lazy(() => import("./pages/PlanPage"));
const MissionsPage = lazy(() => import("./pages/MissionsPage"));
const MissionPage = lazy(() => import("./pages/MissionPage"));
const LibraryPage = lazy(() => import("./pages/LibraryPage"));
const WorkpaperPage = lazy(() => import("./pages/WorkpaperPage"));
const TickmarksPage = lazy(() => import("./pages/TickmarksPage"));
const ReportTemplatesPage = lazy(() => import("./pages/ReportTemplatesPage"));
const DashboardsPage = lazy(() => import("./pages/DashboardsPage"));
const DatasetPage = lazy(() => import("./pages/DatasetPage"));
const ScriptPage = lazy(() => import("./pages/ScriptPage"));
const FrameworksPage = lazy(() => import("./pages/FrameworksPage"));
const AuditFilePage = lazy(() => import("./pages/AuditFilePage"));
const PortfolioPage = lazy(() => import("./pages/PortfolioPage"));
const ClientPage = lazy(() => import("./pages/ClientPage"));
const FindingPage = lazy(() => import("./pages/FindingPage"));
const PortalFindingPage = lazy(() => import("./pages/portal/PortalFindingPage"));

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
        <Route
          path="univers"
          element={
            <RequireAuth permission={PERM.PLAN_READ}>
              <UniversePage />
            </RequireAuth>
          }
        />
        <Route
          path="carte-des-risques"
          element={
            <RequireAuth permission={PERM.PLAN_READ}>
              <RiskMapPage />
            </RequireAuth>
          }
        />
        <Route
          path="plan"
          element={
            <RequireAuth permission={PERM.PLAN_READ}>
              <PlanPage />
            </RequireAuth>
          }
        />
        <Route
          path="missions"
          element={
            <RequireAuth permission={[PERM.MISSIONS_READ_ALL, PERM.MISSIONS_READ_OWN]}>
              <MissionsPage />
            </RequireAuth>
          }
        />
        <Route
          path="missions/:id"
          element={
            <RequireAuth permission={[PERM.MISSIONS_READ_ALL, PERM.MISSIONS_READ_OWN]}>
              <MissionPage />
            </RequireAuth>
          }
        />
        <Route
          path="missions/:id/papiers/:wpId"
          element={
            <RequireAuth permission={[PERM.MISSIONS_READ_ALL, PERM.MISSIONS_READ_OWN]}>
              <WorkpaperPage />
            </RequireAuth>
          }
        />
        <Route
          path="missions/:id/revision/:fid"
          element={
            <RequireAuth permission="revision:read">
              <AuditFilePage />
            </RequireAuth>
          }
        />
        <Route
          path="referentiels"
          element={
            <RequireAuth permission={["revision:read", "frameworks:manage"]}>
              <FrameworksPage />
            </RequireAuth>
          }
        />
        <Route
          path="portail/constats/:fid"
          element={
            <RequireAuth permission="findings:respond">
              <PortalFindingPage />
            </RequireAuth>
          }
        />
        <Route
          path="missions/:id/constats/:fid"
          element={
            <RequireAuth permission="findings:read">
              <FindingPage />
            </RequireAuth>
          }
        />
        <Route
          path="missions/:id/scripts/:sid"
          element={
            <RequireAuth permission="data:read">
              <ScriptPage />
            </RequireAuth>
          }
        />
        <Route
          path="missions/:id/donnees/:dsId"
          element={
            <RequireAuth permission="data:read">
              <DatasetPage />
            </RequireAuth>
          }
        />
        <Route
          path="portefeuille"
          element={
            <RequireAuth permission={PERM.REVISION_READ}>
              <PortfolioPage />
            </RequireAuth>
          }
        />
        <Route
          path="portefeuille/:cid"
          element={
            <RequireAuth permission={PERM.REVISION_READ}>
              <ClientPage />
            </RequireAuth>
          }
        />
        <Route
          path="bibliotheque"
          element={
            <RequireAuth permission={[PERM.MISSIONS_READ_ALL, PERM.MISSIONS_READ_OWN]}>
              <LibraryPage />
            </RequireAuth>
          }
        />
        <Route
          path="tableaux-de-bord"
          element={
            <RequireAuth permission={PERM.DASHBOARDS_GLOBAL}>
              <DashboardsPage />
            </RequireAuth>
          }
        />
        <Route
          path="modeles-rapport"
          element={
            <RequireAuth permission={[PERM.SETTINGS_MANAGE, PERM.REPORT_PUBLISH]}>
              <ReportTemplatesPage />
            </RequireAuth>
          }
        />
        <Route
          path="marques"
          element={
            <RequireAuth permission={[PERM.SETTINGS_MANAGE, PERM.PLAN_MANAGE]}>
              <TickmarksPage />
            </RequireAuth>
          }
        />
        <Route
          path="criteres"
          element={
            <RequireAuth permission={[PERM.SETTINGS_MANAGE, PERM.PLAN_MANAGE]}>
              <CriteriaPage />
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
