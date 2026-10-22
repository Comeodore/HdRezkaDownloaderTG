import type { Kind } from './types';

export function formatSize(bytes: number): string {
  if (!bytes || bytes < 0) return '0 МБ';
  const units = ['МБ', 'ГБ', 'ТБ'];
  let value = bytes / 1024 / 1024;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(digits).replace('.', ',')} ${units[unit]}`;
}

export function formatSpeed(bytesPerSecond: number): string {
  const mb = bytesPerSecond / 1024 / 1024;
  return `${mb >= 10 ? mb.toFixed(0) : mb.toFixed(1).replace('.', ',')} МБ/с`;
}

export function formatEta(seconds: number | null): string {
  if (seconds == null) return '';
  if (seconds < 60) return 'меньше минуты';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `~${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `~${hours} ч ${rest} мин` : `~${hours} ч`;
}

export function formatDuration(minutes: number | null): string {
  if (!minutes) return '';
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} ч ${rest} мин` : `${hours} ч`;
}

const KIND_LABEL: Record<Kind, string> = {
  movie: 'Фильм',
  series: 'Сериал',
  cartoon: 'Мультфильм',
  anime: 'Аниме',
};

export const kindLabel = (kind: string | undefined): string => KIND_LABEL[kind as Kind] ?? '';

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

export const seasonsWord = (n: number) => `${n} ${plural(n, 'сезон', 'сезона', 'сезонов')}`;
export const episodesWord = (n: number) => `${n} ${plural(n, 'серия', 'серии', 'серий')}`;
export const titlesWord = (n: number) => `${n} ${plural(n, 'тайтл', 'тайтла', 'тайтлов')}`;

export function relativeDay(timestamp: number): string {
  const date = new Date(timestamp * 1000);
  const today = new Date();
  const days = Math.round((startOfDay(today) - startOfDay(date)) / 86_400_000);
  if (days === 0) return `сегодня, ${date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`;
  if (days === 1) return 'вчера';
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
