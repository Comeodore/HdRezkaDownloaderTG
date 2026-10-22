import { api, ApiError, subscribeDownloads, type DownloadEvent } from './api';
import { bindBackButton, haptic, inTelegram } from './telegram';
import type { Disk, Job, LibraryItem, SearchItem, SessionUser, TitleRef } from './types';

export type Tab = 'search' | 'downloads' | 'library';
export type Route = { kind: 'title'; ref: TitleRef } | { kind: 'preview' };
export type ToastTone = 'info' | 'success' | 'error';

const ACTIVE = new Set(['queued', 'running', 'paused']);

class AppState {
  booting = $state(true);
  fatal = $state<'outside' | 'forbidden' | string>('');
  token = $state('');
  user = $state<SessionUser | null>(null);

  tab = $state<Tab>('search');
  stack = $state<Route[]>([]);

  jobs = $state<Job[]>([]);
  activeJobs = $derived(this.jobs.filter((job) => ACTIVE.has(job.status)).length);

  toast = $state<{ id: number; message: string; tone: ToastTone } | null>(null);

  private setBack: (visible: boolean) => void = () => {};
  private toastTimer: ReturnType<typeof setTimeout> | undefined;
  private statuses = new Map<string, string>();

  async boot(): Promise<() => void> {
    this.setBack = bindBackButton(() => this.back());
    try {
      await this.getToken(true);
      this.setJobs(await api.downloads());
    } catch (error) {
      const status = error instanceof ApiError ? error.status : 0;
      this.fatal = status === 403 ? 'forbidden' : status === 401 && !inTelegram() ? 'outside' : errorText(error);
      return () => {};
    } finally {
      this.booting = false;
    }
    return subscribeDownloads((refresh) => this.getToken(refresh), (event) => this.onEvent(event));
  }

  async getToken(refresh: boolean): Promise<string> {
    if (!refresh && this.token) return this.token;
    const session = await api.session();
    this.token = session.token;
    this.user = session.user;
    return this.token;
  }

  // ── navigation ──

  selectTab(tab: Tab): void {
    if (tab === this.tab && !this.stack.length) return;
    haptic.select();
    this.stack = [];
    this.tab = tab;
    this.syncBack();
  }

  push(route: Route): void {
    this.stack = [...this.stack, route];
    this.syncBack();
  }

  openTitle(ref: TitleRef): void {
    haptic.tap();
    this.push({ kind: 'title', ref });
  }

  back(): void {
    if (!this.stack.length) return;
    this.stack = this.stack.slice(0, -1);
    this.syncBack();
  }

  private syncBack(): void {
    this.setBack(this.stack.length > 0);
  }

  // ── jobs ──

  private onEvent(event: DownloadEvent): void {
    if (event.type === 'snapshot') this.setJobs(event.jobs);
    else this.upsertJob(event.job);
  }

  setJobs(jobs: Job[]): void {
    for (const job of jobs) this.noteStatus(job);
    this.jobs = jobs;
  }

  upsertJob(job: Job): void {
    const index = this.jobs.findIndex((existing) => existing.id === job.id);
    // an HTTP response can arrive after a newer SSE event for the same job
    if (index >= 0 && this.jobs[index].version > job.version) return;
    this.noteStatus(job);
    if (index >= 0) this.jobs[index] = job;
    else this.jobs = [job, ...this.jobs];
  }

  private noteStatus(job: Job): void {
    const previous = this.statuses.get(job.id);
    if (previous && previous !== job.status) {
      if (job.status === 'success') {
        haptic.success();
        this.notify(`«${job.name}» скачан`, 'success');
      } else if (job.status === 'error') {
        haptic.error();
      }
    }
    this.statuses.set(job.id, job.status);
  }

  // ── toast ──

  notify(message: string, tone: ToastTone = 'info'): void {
    clearTimeout(this.toastTimer);
    this.toast = { id: Date.now(), message, tone };
    this.toastTimer = setTimeout(() => (this.toast = null), tone === 'error' ? 4200 : 2600);
  }

  fail(error: unknown): void {
    haptic.error();
    this.notify(errorText(error), 'error');
  }
}

export function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

export const app = new AppState();

/** Search state lives outside the view so it survives tab switches. */
class SearchState {
  /** shared by every SearchView instance, so a remounted view still cancels the old request */
  controller: AbortController | null = null;
  query = $state('');
  submitted = $state('');
  items = $state<SearchItem[]>([]);
  page = $state(0);
  hasNext = $state(false);
  loading = $state(false);
  error = $state('');
  recent = $state<string[]>(loadRecent());

  remember(query: string): void {
    const value = query.trim();
    if (!value) return;
    this.recent = [value, ...this.recent.filter((item) => item.toLowerCase() !== value.toLowerCase())].slice(0, 8);
    try {
      localStorage.setItem('recent-searches', JSON.stringify(this.recent));
    } catch {
      /* storage unavailable */
    }
  }

  forget(query: string): void {
    this.recent = this.recent.filter((item) => item !== query);
    try {
      localStorage.setItem('recent-searches', JSON.stringify(this.recent));
    } catch {
      /* storage unavailable */
    }
  }
}

function loadRecent(): string[] {
  try {
    const parsed = JSON.parse(localStorage.getItem('recent-searches') ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string').slice(0, 8) : [];
  } catch {
    return [];
  }
}

export const search = new SearchState();

class LibraryState {
  items = $state<LibraryItem[]>([]);
  disk = $state<Disk | null>(null);
  loaded = $state(false);
  loading = $state(false);
  error = $state('');

  private followUp: ReturnType<typeof setTimeout> | undefined;

  async load(): Promise<void> {
    if (this.loading) return;
    this.loading = true;
    this.error = '';
    try {
      const result = await api.library();
      this.items = result.items;
      this.disk = result.disk;
      // posters for older files are being looked up on the server — pick them up shortly
      clearTimeout(this.followUp);
      if (result.enriching) this.followUp = setTimeout(() => this.load(), 6000);
    } catch (error) {
      this.error = errorText(error);
    } finally {
      this.loading = false;
      this.loaded = true;
    }
  }
}

export const library = new LibraryState();
