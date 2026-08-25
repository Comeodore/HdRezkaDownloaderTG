export type Kind = 'movie' | 'series' | 'cartoon' | 'anime' | 'unknown';

export interface SearchItem {
  id: string;
  title: string;
  url: string;
  year: string | null;
  poster: string | null;
  kind: Kind;
}

export interface Translator {
  id: number;
  name: string;
}

export interface SeasonInfo {
  number: number;
  episodes: number;
}

export interface TitleDetails {
  url: string;
  name: string;
  kind: string;
  is_series: boolean;
  year: string | null;
  rating: number | null;
  rating_imdb: number | null;
  rating_kp: number | null;
  poster: string | null;
  translators: Translator[];
}

export type JobStatus =
  | 'queued'
  | 'running'
  | 'paused'
  | 'success'
  | 'partial'
  | 'error'
  | 'cancelled';

export interface Job {
  id: string;
  url: string;
  translator_id: number;
  translator_name: string;
  name: string;
  kind: Kind;
  is_series: boolean;
  year: string | null;
  poster: string | null;
  quality: string | null;
  seasons: number[];
  status: JobStatus;
  percent: number;
  downloaded: number;
  total: number;
  speed: number;
  current: string;
  done_episodes: number;
  total_episodes: number;
  error: string | null;
  created_at: number;
}

export interface LibraryItem {
  id: string;
  name: string;
  kind: 'movie' | 'series';
  size: number;
  episodes?: number;
  seasons?: number;
}

export interface SessionUser {
  id: number;
  first_name?: string;
  username?: string;
}
