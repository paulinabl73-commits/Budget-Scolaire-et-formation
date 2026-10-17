const TOKEN_KEY = "auditlab.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export const tokenStore = {
  get: (): string | null => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export const UNAUTHORIZED_EVENT = "auditlab:unauthorized";

function detail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => (e as { msg?: string }).msg ?? "").join(" ; ");
    if (d && typeof d === "object" && "message" in d) return String((d as { message: unknown }).message);
  }
  return fallback;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(`/api${path}`, { ...options, headers });
  if (resp.status === 204) return undefined as T;
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    if (resp.status === 401 && token && !path.startsWith("/auth/login")) {
      tokenStore.clear();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(resp.status, detail(body, resp.statusText));
  }
  return body as T;
}

export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });
export const patch = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });
export const put = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(data) });
export const upload = <T>(path: string, file: File, field = "file") => {
  const form = new FormData();
  form.append(field, file);
  return api<T>(path, { method: "POST", body: form });
};
export const del = (path: string) => api<void>(path, { method: "DELETE" });

/** Téléchargement d'un fichier produit par une requête POST (exports). */
export async function download(path: string, data: unknown, fallbackName: string): Promise<void> {
  const headers = new Headers();
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  // Sans données : GET ; avec données : POST (exports filtrés).
  const init: RequestInit = data === undefined ? { headers } : { method: "POST", headers, body: JSON.stringify(data) };
  if (data !== undefined) headers.set("Content-Type", "application/json");
  const resp = await fetch(`/api${path}`, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new ApiError(resp.status, detail(body, resp.statusText));
  }
  const name = /filename="([^"]+)"/.exec(resp.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
