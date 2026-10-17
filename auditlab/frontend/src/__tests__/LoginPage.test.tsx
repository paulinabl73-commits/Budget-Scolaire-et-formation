import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { tokenStore } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import RequireAuth from "../components/RequireAuth";
import LoginPage from "../pages/LoginPage";

const ME = {
  id: "1",
  email: "dir@exemple.org",
  nom: "Awa Directrice",
  role: "directeur_audit",
  actif: true,
  mfa_enabled: true,
  is_locked: false,
  teams: [],
  created_at: null,
  permissions: ["plan:validate"],
  mfa_required: true,
};

function respond(status: number, body: unknown) {
  return Promise.resolve({
    status,
    ok: status < 300,
    statusText: "",
    json: () => Promise.resolve(body),
  });
}

function renderApp(initial = "/connexion") {
  return render(
    <MemoryRouter
      initialEntries={[initial]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <Routes>
          <Route path="/connexion" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <p>Espace connecté</p>
              </RequireAuth>
            }
          />
          <Route path="/double-authentification" element={<p>Enrôlement TOTP</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  tokenStore.clear();
  vi.unstubAllGlobals();
});

describe("connexion", () => {
  it("demande le code TOTP puis connecte l'utilisateur", async () => {
    const fetchMock = vi.fn((url: string, init: RequestInit) => {
      if (url === "/api/auth/login") {
        const body = JSON.parse(String(init.body));
        return body.totp_code
          ? respond(200, { token: "jeton", mfa_enrollment_required: false })
          : respond(401, { detail: "mfa_required" });
      }
      return respond(200, ME);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp();

    await user.type(await screen.findByLabelText("Adresse e-mail"), "dir@exemple.org");
    await user.type(screen.getByLabelText("Mot de passe"), "MotDePasse-Solide-2026");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));

    const code = await screen.findByLabelText(/Code de vérification/);
    await user.type(code, "12a3456");
    expect(code).toHaveValue("123456");
    await user.click(screen.getByRole("button", { name: "Vérifier" }));

    expect(await screen.findByText("Espace connecté")).toBeInTheDocument();
    expect(tokenStore.get()).toBe("jeton");
  });

  it("affiche l'erreur d'identifiants", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => respond(401, { detail: "Identifiant ou mot de passe incorrect" })),
    );
    const user = userEvent.setup();
    renderApp();
    await user.type(await screen.findByLabelText("Adresse e-mail"), "x@exemple.org");
    await user.type(screen.getByLabelText("Mot de passe"), "faux");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Identifiant ou mot de passe incorrect",
    );
  });

  it("redirige vers l'enrôlement TOTP quand il est obligatoire", async () => {
    tokenStore.set("jeton");
    vi.stubGlobal("fetch", vi.fn(() => respond(200, { ...ME, mfa_enabled: false })));
    renderApp("/");
    expect(await screen.findByText("Enrôlement TOTP")).toBeInTheDocument();
  });

  it("renvoie vers la connexion sans session", async () => {
    vi.stubGlobal("fetch", vi.fn());
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Connexion" })).toBeInTheDocument();
  });
});
