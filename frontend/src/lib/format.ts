export function formatSize(bytes: number): string {
  if (!bytes) return '0 МБ';
  const mb = bytes / 1024 / 1024;
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} ГБ` : `${mb.toFixed(0)} МБ`;
}

export function formatSpeed(mbs: number): string {
  return `${mbs.toFixed(1)} МБ/с`;
}

const KIND_LABEL: Record<string, string> = {
  movie: 'Фильм',
  series: 'Сериал',
  cartoon: 'Мультфильм',
  anime: 'Аниме',
  unknown: '',
};

export function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? '';
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

export function seasonsWord(n: number): string {
  return `${n} ${plural(n, 'сезон', 'сезона', 'сезонов')}`;
}

export function episodesWord(n: number): string {
  return `${n} ${plural(n, 'эпизод', 'эпизода', 'эпизодов')}`;
}

export function titlesWord(n: number): string {
  return `${n} ${plural(n, 'тайтл', 'тайтла', 'тайтлов')}`;
}
