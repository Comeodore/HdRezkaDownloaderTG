<script lang="ts" module>
  // 24×24 stroke icons (Lucide-style); `fill` marks solid glyphs.
  const ICONS = {
    search: '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.6-4.6"/>',
    download: '<path d="M12 3.5v12"/><path d="m7 10.5 5 5 5-5"/><path d="M4.5 20.5h15"/>',
    library:
      '<rect x="3.5" y="4" width="4.5" height="16" rx="1.2"/><rect x="10" y="4" width="4.5" height="16" rx="1.2"/><path d="m17.2 5.4 3.4 14.2"/>',
    play: 'fill:<path d="M7.5 5.3v13.4a1 1 0 0 0 1.53.85l10.6-6.7a1 1 0 0 0 0-1.7L9.03 4.45a1 1 0 0 0-1.53.85z"/>',
    pause: 'fill:<rect x="6" y="4.5" width="4.2" height="15" rx="1.3"/><rect x="13.8" y="4.5" width="4.2" height="15" rx="1.3"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    retry: '<path d="M20 12a8 8 0 1 1-2.35-5.66"/><path d="M20 4v4.5h-4.5"/>',
    trash:
      '<path d="M4.5 6.5h15"/><path d="M9.5 6.5V4.8c0-.7.5-1.3 1.2-1.3h2.6c.7 0 1.2.6 1.2 1.3v1.7"/><path d="m6.5 6.5.8 12.2c.1 1 .9 1.8 1.9 1.8h5.6c1 0 1.8-.8 1.9-1.8l.8-12.2"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    lock: '<rect x="5" y="10.5" width="14" height="10" rx="2.2"/><path d="M8.5 10.5V7.8a3.5 3.5 0 0 1 7 0v2.7"/>',
    chevron: '<path d="m9 5 7 7-7 7"/>',
    back: '<path d="m15 5-7 7 7 7"/>',
    star: 'fill:<path d="m12 2.8 2.8 5.8 6.3.8-4.6 4.4 1.2 6.3L12 17l-5.7 3.1 1.2-6.3-4.6-4.4 6.3-.8z"/>',
    shuffle:
      '<path d="M16 3.5h4.5V8"/><path d="M4 20 20.5 3.5"/><path d="M20.5 16v4.5H16"/><path d="m15 15 5.5 5.5"/><path d="M4 4l5 5"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.35-5.66"/><path d="M20 4v4.5h-4.5"/>',
    film: '<rect x="3.5" y="4" width="17" height="16" rx="2.5"/><path d="M7.5 4v16M16.5 4v16M3.5 9h4M3.5 15h4M16.5 9h4M16.5 15h4"/>',
    tv: '<rect x="3" y="6" width="18" height="12.5" rx="2.5"/><path d="m8.5 2.5 3.5 3.5 3.5-3.5"/>',
    alert: '<path d="M12 8v5"/><path d="M12 16.5v.01"/><path d="M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    disk: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    sparkles:
      '<path d="M12 3.5 13.6 8 18 9.5l-4.4 1.6L12 15.5l-1.6-4.4L6 9.5 10.4 8z"/><path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
    more: 'fill:<circle cx="5.5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="18.5" cy="12" r="1.8"/>',
  } as const;

  export type IconName = keyof typeof ICONS;
</script>

<script lang="ts">
  let { name, size = 20, stroke = 2 }: { name: IconName; size?: number; stroke?: number } = $props();

  const raw = $derived(ICONS[name]);
  const solid = $derived(raw.startsWith('fill:'));
  const body = $derived(solid ? raw.slice(5) : raw);
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill={solid ? 'currentColor' : 'none'}
  stroke={solid ? 'none' : 'currentColor'}
  stroke-width={stroke}
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {@html body}
</svg>
