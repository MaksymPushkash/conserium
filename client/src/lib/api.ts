"use client";

import { API_BASE_URL, API_V1_URL } from "@/lib/config";
import type {
  ChatDetailResponse,
  ChatListResponse,
  ChatSession,
  DocumentListResponse,
  DocumentResponse,
  DocumentStatusResponse,
  IngestDocumentPayload,
  Note,
  NoteListResponse,
  QueryRequest,
  QueryResponse,
  QueryStreamEvent,
  TokenResponse,
  UserResponse,
} from "@/lib/types";
import { useAuthStore } from "@/stores/auth-store";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const { accessToken, refreshToken, setSession, clearSession } = useAuthStore.getState();
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_V1_URL}${path}`, {
    ...init,
    headers,
  });

  if (response.status === 401 && retry && refreshToken) {
    try {
      const refreshed = await refreshSession(refreshToken);
      setSession(refreshed.access_token, refreshed.refresh_token);
      return request<T>(path, init, false);
    } catch {
      clearSession();
    }
  }

  if (!response.ok) {
    const payload = await readPayload(response);
    throw new ApiError(errorMessage(payload, response.statusText), response.status, payload);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function readPayload(response: Response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function errorMessage(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object" && "detail" in payload) {
    return String((payload as { detail: unknown }).detail);
  }
  if (payload && typeof payload === "object" && "error" in payload) {
    return String((payload as { error: unknown }).error);
  }
  return fallback || "Request failed";
}

export async function register(payload: { email: string; password: string; display_name?: string | null }) {
  return request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }, false);
}

export async function login(payload: { email: string; password: string }) {
  return request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(payload) }, false);
}

export async function refreshSession(refreshToken: string) {
  return request<TokenResponse>(
    "/auth/refresh",
    { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) },
    false,
  );
}

export function oauthUrl(provider: "google" | "github") {
  return `${API_V1_URL}/auth/${provider}`;
}

export function getCurrentUser() {
  return request<UserResponse>("/users/me");
}

export function createChat(payload: { title?: string | null } = {}) {
  return request<ChatSession>("/chats", { method: "POST", body: JSON.stringify(payload) });
}

export function listChats(params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams({
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return request<ChatListResponse>(`/chats?${search.toString()}`);
}

export function getChat(chatId: string) {
  return request<ChatDetailResponse>(`/chats/${chatId}`);
}

export function renameChat(chatId: string, payload: { title: string }) {
  return request<ChatSession>(`/chats/${chatId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteChat(chatId: string) {
  return request<void>(`/chats/${chatId}`, { method: "DELETE" });
}

export function createNote(payload: { title?: string | null; content?: string | null; language?: string | null } = {}) {
  return request<Note>("/notes", { method: "POST", body: JSON.stringify(payload) });
}

export function listNotes(params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams({
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  return request<NoteListResponse>(`/notes?${search.toString()}`);
}

export function getNote(noteId: string) {
  return request<Note>(`/notes/${noteId}`);
}

export function updateNote(noteId: string, payload: { title: string; content: string; language?: string | null }) {
  return request<Note>(`/notes/${noteId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteNote(noteId: string) {
  return request<void>(`/notes/${noteId}`, { method: "DELETE" });
}

export function listDocuments(params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams({
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return request<DocumentListResponse>(`/documents?${search.toString()}`);
}

export function getDocument(documentId: string) {
  return request<DocumentResponse>(`/documents/${documentId}`);
}

export function deleteDocument(documentId: string) {
  return request<void>(`/documents/${documentId}`, { method: "DELETE" });
}

export function ingestDocument(payload: IngestDocumentPayload) {
  return request<DocumentResponse>("/ingest", { method: "POST", body: JSON.stringify(payload) });
}

export function ingestFile(kind: "pdf" | "audio" | "image", payload: { file: File; title?: string; language?: string }) {
  const form = new FormData();
  form.set("file", payload.file);
  if (payload.title) form.set("title", payload.title);
  if (payload.language) form.set("language", payload.language);
  return request<DocumentResponse>(`/ingest/${kind}`, { method: "POST", body: form });
}

export function getDocumentStatus(documentId: string) {
  return request<DocumentStatusResponse>(`/documents/${documentId}/status`);
}

export function queryDocuments(payload: QueryRequest) {
  return request<QueryResponse>("/query", { method: "POST", body: JSON.stringify(payload) });
}

export async function streamQueryDocuments(
  payload: QueryRequest,
  onEvent: (event: QueryStreamEvent) => void,
  signal?: AbortSignal,
) {
  const { accessToken } = useAuthStore.getState();
  const response = await fetch(`${API_V1_URL}/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    const body = await readPayload(response);
    throw new ApiError(errorMessage(body, response.statusText), response.status, body);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const parsed = parseSse(part);
      if (parsed) onEvent(parsed);
    }
  }
}

function parseSse(raw: string): QueryStreamEvent | null {
  const lines = raw.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event:"));
  const dataLine = lines.find((line) => line.startsWith("data:"));
  if (!eventLine || !dataLine) return null;
  return {
    event: eventLine.replace("event:", "").trim() as QueryStreamEvent["event"],
    data: JSON.parse(dataLine.replace("data:", "").trim()) as Record<string, unknown>,
  };
}

export async function getMetricsText() {
  const response = await fetch(`${API_BASE_URL}/metrics`);
  if (!response.ok) throw new Error("Failed to load metrics");
  return response.text();
}
