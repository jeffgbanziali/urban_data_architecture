// src/lib/api.ts
// Client API centralisé. Toute la logique d'appel réseau passe par ici :
//   - base URL configurable via la variable d'environnement Vite VITE_API_BASE
//   - injection automatique du header Authorization si un token est présent
//   - gestion d'erreur homogène (message lisible extrait de la réponse FastAPI)

export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const TOKEN_KEY = "urban_immo_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 204) return undefined as T;

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    const message = (body && (body.detail || body.message)) || `Erreur ${res.status}`;
    throw new ApiError(message, res.status);
  }

  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "POST", body: data ? JSON.stringify(data) : undefined }),
  put: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "PUT", body: data ? JSON.stringify(data) : undefined }),
  patch: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "PATCH", body: data ? JSON.stringify(data) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Types partagés avec l'API (cf. api/app/schemas.py côté backend)
// ---------------------------------------------------------------------------
export type Role = "client" | "employe" | "admin";

export interface AuthResponse {
  access_token: string;
  token_type: string;
  role: Role;
  full_name: string;
}

export interface UserOut {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
}

export interface Bien {
  id: number;
  titre: string;
  description?: string | null;
  arrondissement: number;
  type_bien: string;
  prix: number;
  surface_m2: number;
  photo_url?: string | null;
  statut: "disponible" | "sous_offre" | "vendu";
  employe_id?: number | null;
}

export interface IndicateurSocio {
  arrondissement: number;
  population?: number;
  revenu_median_annuel?: number;
  part_logements_sociaux_pct?: number;
  densite_hab_km2?: number;
  indice_qualite_air?: number;
  delits_pour_1000_hab?: number;
}

export interface PrixArrondissement {
  arrondissement: number;
  annee: number;
  prix_m2_median: number;
  variation_pct?: number;
}
