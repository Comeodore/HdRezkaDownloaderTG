import { initData } from './telegram';
import type {
  Disk,
  Job,
  LibraryItem,
  QualityOption,
  SearchPage,
  SeasonInfo,
  SessionUser,
  TitleDetails,
} from './types';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly data: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const FALLBACK: Record<number, string> = {
  401: 'Сессия устарела — перезапустите приложение',
  403: 'Доступ закрыт',
  404: 'Не найдено',
  502: 'HDRezka не отвечает',
  503: 'HDRezka временно недоступна',
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': initData(),
        ...(init.headers ?? {}),
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'Нет соединения с сервером');
  }
  if (!response.ok) {
    let data: Record<string, unknown> = {};
    try {
      data = await response.json();
    } catch {
      /* not JSON */
    }
    const detail = typeof data.detail === 'string' ? data.detail : null;
    throw new ApiError(response.status, detail ?? FALLBACK[response.status] ?? `Ошибка ${response.status}`, data);
  }
  return response.json() as Promise<T>;
}

const q = (params: Record<string, string | number>) =>
  new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  session: () => request<{ token: string; user: SessionUser }>('/api/session'),
  search: (query: string, page: number, signal?: AbortSignal) =>
    request<SearchPage>(`/api/search?${q({ q: query, page })}`, { signal }),
  title: (url: string, signal?: AbortSignal) => request<TitleDetails>(`/api/title?${q({ url })}`, { signal }),
  episodes: (url: string, translator: string, signal?: AbortSignal) =>
    request<{ seasons: SeasonInfo[] }>(`/api/episodes?${q({ url, translator })}`, { signal }).then((r) => r.seasons),
  qualities: (url: string, translator: string, signal?: AbortSignal) =>
    request<{ items: QualityOption[]; premium_only: string | null }>(`/api/qualities?${q({ url, translator })}`, {
      signal,
    }),

  downloads: () => request<{ jobs: Job[] }>('/api/downloads').then((r) => r.jobs),
  createDownload: (body: { url: string; translator: string; seasons: number[]; max_height: number }) =>
    request<{ job: Job }>('/api/downloads', { method: 'POST', body: JSON.stringify(body) }).then((r) => r.job),
  pause: (id: string) => request<{ ok: true }>(`/api/downloads/${id}/pause`, { method: 'POST' }),
  resume: (id: string) => request<{ job: Job }>(`/api/downloads/${id}/resume`, { method: 'POST' }).then((r) => r.job),
  cancel: (id: string) => request<{ ok: true }>(`/api/downloads/${id}/cancel`, { method: 'POST' }),
  retry: (id: string) => request<{ job: Job }>(`/api/downloads/${id}/retry`, { method: 'POST' }).then((r) => r.job),
  remove: (id: string) => request<{ ok: true }>(`/api/downloads/${id}`, { method: 'DELETE' }),
  clearFinished: () => request<{ jobs: Job[] }>('/api/downloads', { method: 'DELETE' }).then((r) => r.jobs),

  library: () => request<{ items: LibraryItem[]; disk: Disk; enriching: boolean }>('/api/library'),
  deleteLibrary: (id: string) => request<{ ok: true }>(`/api/library/${id}`, { method: 'DELETE' }),
};

export const previewUrl = (url: string, translator: string, token: string): string =>
  `/api/preview?${q({ url, translator, t: token })}`;

export type DownloadEvent = { type: 'snapshot'; jobs: Job[] } | { type: 'job'; job: Job };

/**
 * Live job updates over SSE. EventSource gives up for good on an HTTP error
 * (e.g. an expired token), so reconnection is handled here with a fresh token
 * and exponential backoff.
 */
export function subscribeDownloads(
  getToken: (refresh: boolean) => Promise<string>,
  onEvent: (event: DownloadEvent) => void,
): () => void {
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let stopped = false;
  let connecting = false;

  const connect = async (refresh: boolean) => {
    if (stopped || connecting || source) return;
    connecting = true;
    let token: string;
    try {
      token = await getToken(refresh);
    } catch {
      connecting = false;
      schedule();
      return;
    }
    connecting = false;
    if (stopped || source) return;
    source = new EventSource(`/api/downloads/events?${q({ t: token })}`);
    source.onopen = () => (attempt = 0);
    source.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data) as DownloadEvent);
      } catch {
        /* keep-alive or malformed frame */
      }
    };
    source.onerror = () => {
      if (source?.readyState === EventSource.CLOSED) {
        source = null;
        schedule();
      }
    };
  };

  const schedule = () => {
    if (stopped) return;
    const delay = Math.min(30_000, 1000 * 2 ** attempt++);
    timer = setTimeout(() => connect(true), delay);
  };

  const onVisible = () => {
    if (document.visibilityState === 'visible' && !source && !connecting && !stopped) {
      clearTimeout(timer);
      attempt = 0;
      connect(true);
    }
  };
  document.addEventListener('visibilitychange', onVisible);
  connect(false);

  return () => {
    stopped = true;
    clearTimeout(timer);
    source?.close();
    document.removeEventListener('visibilitychange', onVisible);
  };
}
