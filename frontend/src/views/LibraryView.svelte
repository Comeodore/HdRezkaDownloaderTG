<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../components/Icon.svelte';
  import Poster from '../components/Poster.svelte';
  import Spinner from '../components/Spinner.svelte';
  import { api } from '../lib/api';
  import { episodesWord, formatSize, seasonsWord, titlesWord } from '../lib/format';
  import { app, library } from '../lib/state.svelte';
  import { confirm, haptic } from '../lib/telegram';
  import type { LibraryItem } from '../lib/types';

  type Filter = 'all' | 'movie' | 'series';

  let filter = $state<Filter>('all');
  let removing = $state<Set<string>>(new Set());

  const counts = $derived({
    all: library.items.length,
    movie: library.items.filter((item) => item.kind === 'movie').length,
    series: library.items.filter((item) => item.kind === 'series').length,
  });
  const visible = $derived(filter === 'all' ? library.items : library.items.filter((item) => item.kind === filter));
  const usedShare = $derived(library.disk?.total ? (library.disk.used / library.disk.total) * 100 : 0);
  const totalSize = $derived(visible.reduce((sum, item) => sum + item.size, 0));

  onMount(() => {
    library.load();
  });

  function refresh(): void {
    haptic.tap();
    library.load();
  }

  function setFilter(value: Filter): void {
    if (value === filter) return;
    haptic.select();
    filter = value;
  }

  function describe(item: LibraryItem): string {
    if (item.kind === 'series') {
      return [
        'Сериал',
        item.seasons && item.seasons > 1 ? seasonsWord(item.seasons) : null,
        item.episodes ? episodesWord(item.episodes) : null,
        formatSize(item.size),
      ]
        .filter(Boolean)
        .join(' · ');
    }
    return `Фильм · ${formatSize(item.size)}`;
  }

  function open(item: LibraryItem): void {
    if (!item.url) {
      haptic.warning();
      app.notify('Этот файл добавлен не через приложение — ссылки на HDRezka нет');
      return;
    }
    app.openTitle({ url: item.url, title: item.title ?? item.name, kind: item.kind, year: item.year, poster: item.poster });
  }

  async function remove(item: LibraryItem): Promise<void> {
    const what = item.kind === 'series' ? `сериал «${item.name}» целиком` : `«${item.name}»`;
    if (!(await confirm(`Удалить ${what} с диска? Освободится ${formatSize(item.size)}.`))) return;
    haptic.press();
    removing = new Set(removing).add(item.id);
    try {
      await api.deleteLibrary(item.id);
      library.items = library.items.filter((entry) => entry.id !== item.id);
      if (library.disk) {
        library.disk = { ...library.disk, used: library.disk.used - item.size, free: library.disk.free + item.size };
      }
      app.notify('Удалено', 'success');
    } catch (error) {
      app.fail(error);
    } finally {
      const next = new Set(removing);
      next.delete(item.id);
      removing = next;
    }
  }
</script>

<div class="screen">
  <div class="title-row">
    <h1 class="large-title">Медиатека</h1>
    <button class="icon-button" onclick={refresh} aria-label="Обновить" disabled={library.loading}>
      <span class:spinning={library.loading} class="glyph"><Icon name="refresh" size={18} /></span>
    </button>
  </div>

  {#if library.disk && library.disk.total}
    <div class="disk">
      <div class="disk-top">
        <span class="disk-free">{formatSize(library.disk.free)}</span>
        <span class="disk-of">свободно из {formatSize(library.disk.total)}</span>
      </div>
      <div class="disk-bar"><div class="disk-fill" style:width="{usedShare}%"></div></div>
    </div>
  {/if}

  {#if !library.loaded}
    <div class="center"><Spinner /></div>
  {:else if library.error && !library.items.length}
    <div class="message">
      <p>{library.error}</p>
      <button class="chip" onclick={refresh}><Icon name="retry" size={15} /> Повторить</button>
    </div>
  {:else if !library.items.length}
    <div class="message">
      <p>Медиатека пуста — скачанное появится здесь</p>
    </div>
  {:else}
    <div class="filters" role="tablist">
      {#each [['all', 'Все'], ['movie', 'Фильмы'], ['series', 'Сериалы']] as [value, label] (value)}
        <button
          class="chip"
          class:on={filter === value}
          role="tab"
          aria-selected={filter === value}
          onclick={() => setFilter(value as Filter)}
        >
          {label}<span class="count">{counts[value as Filter]}</span>
        </button>
      {/each}
    </div>
    <div class="summary">{titlesWord(visible.length)} · {formatSize(totalSize)}</div>

    <ul class="list">
      {#each visible as item (item.id)}
        <li class:leaving={removing.has(item.id)}>
          <button class="main" onclick={() => open(item)}>
            <span class="cover"><Poster src={item.poster} alt="" kind={item.kind} /></span>
            <span class="text">
              <span class="name">{item.name}</span>
              <span class="sub">{describe(item)}</span>
              {#if item.downloading}<span class="live"><span class="dot"></span>Качается</span>{/if}
            </span>
          </button>
          <button
            class="icon-button ghost"
            onclick={() => remove(item)}
            disabled={item.downloading || removing.has(item.id)}
            aria-label="Удалить «{item.name}»"
          >
            {#if removing.has(item.id)}<Spinner size={16} />{:else}<Icon name="trash" size={17} />{/if}
          </button>
        </li>
      {/each}
    </ul>
    <p class="footnote">Файлы лежат в общей папке сервера — их видно по SMB с телевизора и компьютера</p>
  {/if}
</div>

<style>
  .title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .glyph {
    display: flex;
  }
  .spinning {
    animation: spin 0.9s linear infinite;
  }

  .disk {
    margin-top: 16px;
    padding: 14px 16px 16px;
    border-radius: var(--radius-l);
    background: var(--surface);
    border: 1px solid var(--line);
  }
  .disk-top {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .disk-free {
    font-size: 22px;
    font-weight: 750;
    letter-spacing: -0.3px;
  }
  .disk-of {
    font-size: 13px;
    color: var(--text-3);
  }
  .disk-bar {
    margin-top: 12px;
    height: 6px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.1);
    overflow: hidden;
  }
  .disk-fill {
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, var(--text-2), var(--text));
  }

  .filters {
    margin-top: 18px;
    display: flex;
    gap: 8px;
  }
  .count {
    margin-left: 2px;
    opacity: 0.55;
    font-variant-numeric: tabular-nums;
  }
  .summary {
    margin-top: 14px;
    font-size: 13px;
    color: var(--text-3);
  }
  .list {
    list-style: none;
    margin: 4px 0 0;
    padding: 0;
  }
  li {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
    transition: opacity 0.25s ease;
  }
  li.leaving {
    opacity: 0.4;
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 12px;
    text-align: left;
  }
  .main:active {
    opacity: 0.6;
  }
  .cover {
    flex: none;
    width: 44px;
    height: 66px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--line);
  }
  .text {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .name {
    font-size: 15.5px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sub {
    font-size: 13px;
    color: var(--text-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .live {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-2);
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--success);
    animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.3;
    }
  }
  .icon-button.ghost {
    flex: none;
    color: var(--text-3);
    background: transparent;
    border-color: transparent;
  }
  .icon-button.ghost:disabled {
    opacity: 0.35;
  }
  .center {
    margin-top: 20vh;
    display: flex;
    justify-content: center;
  }
  .message {
    margin-top: 16vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    text-align: center;
    color: var(--text-2);
  }
  .message p {
    margin: 0;
    max-width: 280px;
  }
  .footnote {
    margin: 18px 4px 0;
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--text-4);
    text-align: center;
  }
</style>
