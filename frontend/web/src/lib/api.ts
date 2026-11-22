const resolveApiBase = (): string => {
  // 1. Explicit override wins (VITE_API_URL in .env / build env).
  const envUrl = import.meta.env.VITE_API_URL?.trim();

  if (envUrl) {
    return envUrl.replace(/\/+$/, "");
  }

  // 2. The Vite dev server proxies /api (HTTP and WebSocket) to the
  // backend, so same-origin requests work from any device — desktop
  // localhost or a phone on the home Wi-Fi — with no CORS setup.
  return window.location.origin;
};

export const API = resolveApiBase();

const DEVICE_TOKEN_KEY = "jarvis.deviceToken";

export const getDeviceToken = (): string =>
  localStorage.getItem(DEVICE_TOKEN_KEY) ?? "";

export const setDeviceToken = (token: string): void => {
  localStorage.setItem(DEVICE_TOKEN_KEY, token.trim());
};

export const clearDeviceToken = (): void => {
  localStorage.removeItem(DEVICE_TOKEN_KEY);
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const NETWORK_ERROR = `Cannot reach the Jarvis backend at ${API}. Start it with start_jarvis.bat or: .venv\\Scripts\\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`;

const authHeaders = (): Record<string, string> => {
  const token = getDeviceToken();

  return token ? { "X-Device-Token": token } : {};
};

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  let response: Response;

  try {
    response = await fetch(`${API}${path}`, {
      ...init,
      headers: {
        ...authHeaders(),
        ...(init?.headers as Record<string, string> | undefined),
      },
    });
  } catch {
    throw new ApiError(NETWORK_ERROR, 0);
  }

  if (!response.ok) {
    if (response.status === 401) {
      throw new ApiError(
        "This device is not authorized. Enter the Jarvis device code.",
        401,
      );
    }

    let message = `Request failed (${response.status}).`;

    try {
      const data = await response.json();

      if (typeof data?.detail === "string") {
        message = data.detail;
      }
    } catch {
      // Keep the default error message.
    }

    throw new ApiError(message, response.status);
  }

  return response.json() as Promise<T>;
};

export const apiGet = <T>(path: string): Promise<T> =>
  request<T>(path);

export const apiPost = <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, {
    method: "POST",
    headers: body === undefined
      ? undefined
      : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const apiPut = <T>(path: string, body: unknown): Promise<T> =>
  request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const apiDelete = <T>(path: string): Promise<T> =>
  request<T>(path, { method: "DELETE" });

export const fetchTtsAudio = async (
  endpoint: string,
  text: string,
  signal?: AbortSignal,
): Promise<Blob> => {
  let response: Response;

  try {
    response = await fetch(`${API}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({ text }),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;

    throw new Error(NETWORK_ERROR);
  }

  if (response.status === 401) {
    throw new ApiError(
      "This device is not authorized. Enter the Jarvis device code.",
      401,
    );
  }

  if (!response.ok) {
    throw new Error("Voice generation failed.");
  }

  return response.blob();
};
