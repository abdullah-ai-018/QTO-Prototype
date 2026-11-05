const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

let authToken: string | null = typeof localStorage !== "undefined" ? localStorage.getItem("protake_access_token") : null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (typeof localStorage !== "undefined") {
    if (token) {
      localStorage.setItem("protake_access_token", token);
    } else {
      localStorage.removeItem("protake_access_token");
    }
  }
}

export function getAuthToken(): string | null {
  return authToken || (typeof localStorage !== "undefined" ? localStorage.getItem("protake_access_token") : null);
}

// Heavy processing endpoints need a much longer timeout (IFC parsing, multi-page vector PDF extraction + geometry extrusions)
const HEAVY_ENDPOINTS = ["/ifc", "/process", "/blueprints", "/ocr", "/ai-validate", "/pdf"];

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  timeoutMs?: number
): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  // Auto-detect heavy endpoints and give them 600s (10 minutes); standard endpoints get 300s (5 minutes)
  const isHeavy = HEAVY_ENDPOINTS.some((p) => endpoint.includes(p));
  const effectiveTimeout = timeoutMs ?? (isHeavy ? 600_000 : 300_000);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(new Error(`Request timed out after ${effectiveTimeout / 1000}s`)), effectiveTimeout);

  try {
    const response = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      if (response.status === 401 && !endpoint.startsWith("/auth/")) {
        setAuthToken(null);
        try {
          // Attempt automatic guest re-authentication
          const authRes = await fetch(`${BASE_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: "guest@protake.app", password: "GuestPassword123!" }),
          });
          if (authRes.ok) {
            const authData = await authRes.json();
            setAuthToken(authData.access_token);
            // Retry original request with fresh token
            const retryHeaders = {
              ...headers,
              Authorization: `Bearer ${authData.access_token}`,
            };
            const retryRes = await fetch(`${BASE_URL}${endpoint}`, {
              ...options,
              headers: retryHeaders,
            });
            if (retryRes.ok) {
              return retryRes.json() as Promise<T>;
            }
          }
        } catch {
          // fallback to standard error handling
        }
      }

      let errorMessage = `HTTP Error ${response.status}: ${response.statusText}`;
      try {
        const errorData = await response.json();
        if (errorData.detail) {
          errorMessage = typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail);
        }
      } catch {
        // ignore json parse errors
      }
      throw new Error(errorMessage);
    }

    return response.json() as Promise<T>;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

// For endpoints that return a binary file (page image/thumbnail) rather
// than JSON. These require the same bearer-token auth as everything else,
// which a plain <img src="..."> can't attach — so the caller fetches the
// bytes here and gets back a blob: URL to hand to <img>/Konva instead.
export async function apiRequestObjectUrl(endpoint: string, timeoutMs = 30_000): Promise<string> {
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${BASE_URL}${endpoint}`, { headers, signal: controller.signal });
    clearTimeout(timeoutId);
    if (!response.ok) {
      if (response.status === 401) {
        setAuthToken(null);
        try {
          const authRes = await fetch(`${BASE_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: "guest@protake.app", password: "GuestPassword123!" }),
          });
          if (authRes.ok) {
            const authData = await authRes.json();
            setAuthToken(authData.access_token);
            const retryHeaders = { ...headers, Authorization: `Bearer ${authData.access_token}` };
            const retryRes = await fetch(`${BASE_URL}${endpoint}`, { headers: retryHeaders });
            if (retryRes.ok) {
              const blob = await retryRes.blob();
              return URL.createObjectURL(blob);
            }
          }
        } catch {
          // fallback
        }
      }
      throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
    }
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}
