export type Kind = 'movie' | 'series' | 'cartoon' | 'anime';

export interface SearchItem {
  url: string;
  title: string;
  kind: Kind;
  year: string | null;
  country: string | null;
  genre: string | null;
  status: string | null;
  poster: string | null;
}

export interface SearchPage {
  items: SearchItem[];
  page: number;
  has_next: boolean;
}

export interface Translator {
  key: string;
  id: number;
  name: string;
  premium: boolean;
  director: boolean;
  camrip: boolean;
  ads: boolean;
}

export interface Part {
  url: string;
  title: string;
  year: number | null;
  rating: number | null;
  current: boolean;
}

export interface TitleDetails {
  id: number;
  url: string;
  name: string;
  orig_name: string | null;
  kind: Kind;
  is_series: boolean;
  year: number | null;
  rating: number | null;
  rating_imdb: number | null;
  rating_kp: number | null;
  duration: number | null;
  country: string | null;
  genres: string[];
  age: string | null;
  description: string | null;
  status: string | null;
  poster: string | null;
  poster_hq: string | null;
  translators: Translator[];
  default_translator: string | null;
  parts: Part[];
  local: { exists: boolean; episodes: Record<string, number> };
  disk_free: number | null;
}

export interface SeasonInfo {
  number: number;
  episodes: number;
  local: number;
}

export interface QualityOption {
  label: string;
  height: number;
  size: number;
}

export type JobStatus = 'queued' | 'running' | 'paused' | 'success' | 'partial' | 'error' | 'cancelled';

export interface Job {
  id: string;
  url: string;
  name: string;
  year: number | null;
  kind: Kind;
  is_series: boolean;
  poster: string | null;
  translator_name: string;
  max_height: number;
  seasons: number[];
  status: JobStatus;
  quality: string | null;
  current: string;
  downloaded: number;
  total: number;
  speed: number;
  done_episodes: number;
  total_episodes: number;
  failed: string[];
  bytes_done: number;
  error: string | null;
  target: string | null;
  created_at: number;
  finished_at: number | null;
  percent: number;
  eta: number | null;
  /** bumps on every server-side change; older copies must not replace newer ones */
  version: number;
}

export interface LibraryItem {
  id: string;
  entry: string;
  name: string;
  title: string | null;
  year: number | null;
  url: string | null;
  poster: string | null;
  kind: 'movie' | 'series';
  size: number;
  modified: number;
  episodes?: number;
  seasons?: number;
  downloading: boolean;
}

export interface Disk {
  total: number;
  used: number;
  free: number;
}

export interface SessionUser {
  id: number;
  first_name?: string;
  username?: string;
}

/** What the title page needs to render instantly, before details arrive. */
export interface TitleRef {
  url: string;
  title: string;
  kind?: Kind;
  year?: string | number | null;
  poster?: string | null;
}
