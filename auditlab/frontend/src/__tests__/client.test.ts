import { api, ApiError, tokenStore, UNAUTHORIZED_EVENT } from "../api/client";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    status,
    ok: status >= 200 && status < 300,
    statusText: "Erreur",
    json: () => Promise.resolve(body),
  });
}

afterEach(() => {
  tokenStore.clear();
  vi.unstubAllGlobals();
});

describe("client API", () => {
  it("envoie le jeton porteur", async () => {
    tokenStore.set("abc");
    const fetchMock = mockFetch(200, { ok: 1 });
    vi.stubGlobal("fetch", fetchMock);
    await expect(api("/auth/me")).resolves.toEqual({ ok: 1 });
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer abc");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/me");
  });

  it("signale l'expiration de session sur 401 et efface le jeton", async () => {
    tokenStore.set("abc");
    vi.stubGlobal("fetch", mockFetch(401, { detail: "Session expirée ou invalide" }));
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);
    await expect(api("/users")).rejects.toThrow("Session expirée ou invalide");
    expect(listener).toHaveBeenCalledOnce();
    expect(tokenStore.get()).toBeNull();
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });

  it("restitue les erreurs de validation", async () => {
    vi.stubGlobal("fetch", mockFetch(422, { detail: [{ msg: "champ requis" }] }));
    const err = await api("/users").catch((e: ApiError) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
    expect((err as ApiError).message).toBe("champ requis");
  });
});
