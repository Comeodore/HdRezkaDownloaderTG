import { writable } from 'svelte/store';
import type { Job, LibraryItem, SearchItem, SessionUser, TitleDetails } from './types';

export type Tab = 'search' | 'downloads' | 'library';

export const token = writable('');
export const user = writable<SessionUser | null>(null);
export const tab = writable<Tab>('search');

export const query = writable('');
export const results = writable<SearchItem[]>([]);
export const searching = writable(false);
export const searched = writable(false);
export const searchError = writable('');

export interface Selection {
  item: SearchItem;
  details: TitleDetails | null;
  loading: boolean;
  error: string;
}
export const selection = writable<Selection | null>(null);

export const jobs = writable<Job[]>([]);
export const library = writable<LibraryItem[]>([]);

export function upsertJob(job: Job): void {
  jobs.update((list) => {
    const index = list.findIndex((existing) => existing.id === job.id);
    if (index >= 0) {
      const next = [...list];
      next[index] = job;
      return next;
    }
    return [job, ...list];
  });
}

export function activeJobCount(list: Job[]): number {
  return list.filter((job) => job.status === 'running' || job.status === 'queued').length;
}

export function badgeCount(list: Job[]): number {
  return list.filter(
    (job) => job.status === 'running' || job.status === 'queued' || job.status === 'paused',
  ).length;
}
