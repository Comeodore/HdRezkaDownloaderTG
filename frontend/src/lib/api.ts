import { initData } from './telegram';
import type { Job, LibraryItem, SearchItem, SeasonInfo, SessionUser, TitleDetails } from './types';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': initData(),
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => '');
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  session: () => request<{ token: string; user: SessionUser }>('/api/session'),
  search: (q: string) =>
    request<{ results: SearchItem[] }>(`/api/search?q=${encodeURIComponent(q)}`).then((r) => r.results),
  title: (url: string) => request<TitleDetails>(`/api/title?url=${encodeURIComponent(url)}`),
  seasons: (url: string, translatorId: number) =>
    request<{ seasons: SeasonInfo[] }>(
      `/api/seasons?url=${encodeURIComponent(url)}&translator_id=${translatorId}`,
    ).then((r) => r.seasons),
  downloads: () => request<{ jobs: Job[] }>('/api/downloads').then((r) => r.jobs),
  clearDownloads: () =>
    request<{ jobs: Job[] }>('/api/downloads', { method: 'DELETE' }).then((r) => r.jobs),
  createDownload: (url: string, translatorId: number, poster: string | null, seasons: number[] = []) =>
    request<{ job: Job }>('/api/downloads', {
      method: 'POST',
      body: JSON.stringify({ url, translator_id: translatorId, poster, seasons }),
    }).then((r) => r.job),
  cancelDownload: (id: string) => request<void>(`/api/downloads/${id}`, { method: 'DELETE' }),
  pauseDownload: (id: string) => request<void>(`/api/downloads/${id}/pause`, { method: 'POST' }),
  resumeDownload: (id: string) =>
    request<{ job: Job }>(`/api/downloads/${id}/resume`, { method: 'POST' }).then((r) => r.job),
  retryDownload: (id: string) =>
    request<{ job: Job }>(`/api/downloads/${id}/retry`, { method: 'POST' }).then((r) => r.job),
  library: () => request<{ items: LibraryItem[] }>('/api/library').then((r) => r.items),
  deleteLibrary: (id: string) => request<void>(`/api/library/${id}`, { method: 'DELETE' }),
};

function base64Url(value: string): string {
  return btoa(unescape(encodeURIComponent(value)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

export function imageUrl(remote: string | null, token: string): string {
  if (!remote) return '';
  return `/api/image?u=${base64Url(remote)}&t=${encodeURIComponent(token)}`;
}

export function previewUrl(title: string, translatorId: number, token: string): string {
  return `/api/preview/stream?url=${encodeURIComponent(title)}&translator_id=${translatorId}&t=${encodeURIComponent(token)}`;
}

export function subscribeDownloads(token: string, onEvent: (event: unknown) => void): () => void {
  const source = new EventSource(`/api/downloads/events?t=${encodeURIComponent(token)}`);
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data));
    } catch {
      /* ignore keep-alive comments */
    }
  };
  return () => source.close();
}
