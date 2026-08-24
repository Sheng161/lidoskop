export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Ошибка API" }));
    throw new ApiError(response.status, payload.detail ?? "Ошибка API");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type Job = {
  id: string;
  query: string;
  city: string | null;
  status: string;
  progress: number;
  stage: string;
  error: string | null;
  plan?: Record<string, unknown> | null;
  created_at: string;
};

export type CompanyRow = {
  id: string;
  name: string;
  inn: string | null;
  ogrn: string | null;
  status: string | null;
  website: string | null;
  city: string | null;
  score: number | null;
};
