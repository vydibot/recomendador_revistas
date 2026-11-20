const TOKEN_KEY = "revistas_admin_token";

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler = () => {};
export const setUnauthorizedHandler = (handler: UnauthorizedHandler) => {
  onUnauthorized = handler;
};

function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // Errores de validación de FastAPI: [{loc, msg}, ...]
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) =>
        [item.loc?.slice(1).join("."), item.msg].filter(Boolean).join(": "),
      )
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return fallback;
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; form?: FormData; params?: URLSearchParams } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const query = options.params && options.params.size > 0 ? `?${options.params}` : "";

  let response: Response;
  try {
    response = await fetch(`/api${path}${query}`, { method: options.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(0, "No se pudo conectar con el servidor");
  }
  if (response.status === 204) return undefined as T;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && token) onUnauthorized();
    const detail = payload?.detail;
    throw new ApiError(response.status, messageFrom(detail, response.statusText), detail);
  }
  return payload as T;
}
