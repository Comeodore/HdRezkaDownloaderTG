<script lang="ts">
  import Icon from '../components/Icon.svelte';
  import Poster from '../components/Poster.svelte';
  import Spinner from '../components/Spinner.svelte';
  import { api } from '../lib/api';
  import { kindLabel } from '../lib/format';
  import { app, errorText, search } from '../lib/state.svelte';
  import { haptic } from '../lib/telegram';
  import type { SearchItem } from '../lib/types';

  const DEBOUNCE = 450;

  let input: HTMLInputElement | undefined = $state();
  let sentinel: HTMLDivElement | undefined = $state();
  let timer: ReturnType<typeof setTimeout> | undefined;

  const showRecent = $derived(!search.query.trim() && !search.items.length);

  function onInput(): void {
    clearTimeout(timer);
    const query = search.query.trim();
    if (!query) {
      search.controller?.abort();
      search.items = [];
      search.submitted = '';
      search.error = '';
      search.loading = false;
      return;
    }
    if (query.length < 2) return;
    timer = setTimeout(() => run(query, 1), DEBOUNCE);
  }

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    const query = search.query.trim();
    if (!query) return;
    clearTimeout(timer);
    input?.blur();
    search.remember(query);
    if (query !== search.submitted || search.error) run(query, 1);
  }

  async function run(query: string, page: number): Promise<void> {
    search.controller?.abort();
    const current = new AbortController();
    search.controller = current;
    search.loading = true;
    search.error = '';
    if (page === 1) search.submitted = query;
    try {
      const result = await api.search(query, page, current.signal);
      if (current.signal.aborted) return;
      const seen = new Set(page === 1 ? [] : search.items.map((item) => item.url));
      const fresh = result.items.filter((item) => !seen.has(item.url));
      search.items = page === 1 ? fresh : [...search.items, ...fresh];
      search.page = page;
      search.hasNext = result.has_next && fresh.length > 0;
    } catch (error) {
      if (current.signal.aborted) return;
      search.error = errorText(error);
      if (page === 1) search.items = [];
    } finally {
      if (search.controller === current) search.loading = false;
    }
  }

  function retry(): void {
    run(search.submitted || search.query.trim(), search.items.length ? search.page + 1 : 1);
  }

  function useRecent(query: string): void {
    haptic.tap();
    search.query = query;
    search.remember(query);
    run(query, 1);
  }

  function clearQuery(): void {
    search.query = '';
    onInput();
    input?.focus();
  }

  function open(item: SearchItem): void {
    search.remember(search.submitted);
    app.openTitle({ url: item.url, title: item.title, kind: item.kind, year: item.year, poster: item.poster });
  }

  $effect(() => {
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && search.hasNext && !search.loading && !search.error) {
          run(search.submitted, search.page + 1);
        }
      },
      { rootMargin: '600px 0px' },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  });

  const subline = (item: SearchItem) => [item.year, kindLabel(item.kind)].filter(Boolean).join(' · ');
</script>

<div class="screen">
  <h1 class="large-title">Поиск</h1>

  <form class="field" onsubmit={submit} role="search">
    <span class="lens"><Icon name="search" size={18} /></span>
    <input
      bind:this={input}
      bind:value={search.query}
      oninput={onInput}
      type="search"
      placeholder="Фильмы, сериалы, аниме"
      enterkeyhint="search"
      autocomplete="off"
      autocapitalize="off"
      spellcheck="false"
      aria-label="Поиск"
    />
    {#if search.loading && !search.items.length}
      <Spinner size={16} />
    {:else if search.query}
      <button type="button" class="clear" onclick={clearQuery} aria-label="Очистить">
        <Icon name="close" size={12} stroke={2.6} />
      </button>
    {/if}
  </form>

  {#if showRecent}
    {#if search.recent.length}
      <div class="section-label recent-label">Недавние</div>
      <ul class="recent">
        {#each search.recent as query (query)}
          <li>
            <button class="recent-item" onclick={() => useRecent(query)}>
              <span class="recent-icon"><Icon name="clock" size={17} /></span>
              <span class="recent-text">{query}</span>
            </button>
            <button class="recent-remove" onclick={() => search.forget(query)} aria-label="Убрать «{query}»">
              <Icon name="close" size={13} stroke={2.2} />
            </button>
          </li>
        {/each}
      </ul>
    {:else}
      <div class="hint">
        <div class="hint-icon"><Icon name="sparkles" size={30} stroke={1.5} /></div>
        <p>Найдите фильм или сериал на HDRezka — он скачается прямо на сервер</p>
      </div>
    {/if}
  {:else if search.error && !search.items.length}
    <div class="message">
      <p>{search.error}</p>
      <button class="chip" onclick={retry}><Icon name="retry" size={15} /> Повторить</button>
    </div>
  {:else if search.loading && !search.items.length}
    <div class="grid" aria-hidden="true">
      {#each Array(9) as _, i (i)}
        <div class="card">
          <div class="cover skeleton"></div>
          <div class="line skeleton"></div>
          <div class="line short skeleton"></div>
        </div>
      {/each}
    </div>
  {:else if search.items.length}
    <div class="grid">
      {#each search.items as item, i (item.url)}
        <button
          class="card pressable"
          style:animation-delay="{Math.min(i % 36, 12) * 25}ms"
          onclick={() => open(item)}
        >
          <div class="cover">
            <Poster src={item.poster} alt={item.title} kind={item.kind} />
            {#if item.status}<span class="badge">{item.status.replace(' (все серии)', '')}</span>{/if}
          </div>
          <div class="title">{item.title}</div>
          <div class="sub">{subline(item)}</div>
        </button>
      {/each}
    </div>
    <div bind:this={sentinel} class="more">
      {#if search.loading}
        <Spinner size={20} />
      {:else if search.error}
        <button class="chip" onclick={retry}><Icon name="retry" size={15} /> Загрузить ещё</button>
      {/if}
    </div>
  {:else if search.submitted && !search.loading}
    <div class="message">
      <p>По запросу «{search.submitted}» ничего не нашлось</p>
    </div>
  {/if}
</div>

<style>
  .field {
    margin-top: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    height: 46px;
    padding: 0 12px 0 14px;
    border-radius: var(--radius-m);
    background: var(--surface-2);
    border: 1px solid var(--line);
    transition: border-color 0.2s ease;
  }
  .field:focus-within {
    border-color: var(--line-strong);
  }
  .lens {
    display: flex;
    color: var(--text-3);
  }
  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    border: 0;
    background: transparent;
    font-size: 17px;
    -webkit-appearance: none;
    appearance: none;
  }
  input::placeholder {
    color: var(--text-4);
  }
  input::-webkit-search-cancel-button {
    display: none;
  }
  .clear {
    flex: none;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--bg);
    background: var(--text-3);
  }

  .recent-label {
    margin: 26px 0 6px;
  }
  .recent {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .recent li {
    display: flex;
    align-items: center;
    border-bottom: 1px solid var(--line);
  }
  .recent-item {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 0;
    text-align: left;
  }
  .recent-item:active {
    opacity: 0.6;
  }
  .recent-icon {
    display: flex;
    color: var(--text-3);
  }
  .recent-text {
    font-size: 16px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .recent-remove {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-4);
  }

  .hint {
    margin: 22vh auto 0;
    max-width: 260px;
    text-align: center;
    color: var(--text-3);
    font-size: 15px;
  }
  .hint-icon {
    display: inline-flex;
    padding: 18px;
    border-radius: 24px;
    color: var(--text-2);
    background: var(--surface);
    border: 1px solid var(--line);
  }
  .hint p {
    margin: 16px 0 0;
    line-height: 1.45;
  }

  .grid {
    margin-top: 18px;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 18px 10px;
  }
  .card {
    display: flex;
    flex-direction: column;
    min-width: 0;
    text-align: left;
    animation: fade-up 0.4s var(--ease-out) both;
  }
  .cover {
    position: relative;
    aspect-ratio: 2 / 3;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--line);
  }
  .badge {
    position: absolute;
    left: 6px;
    bottom: 6px;
    max-width: calc(100% - 12px);
    padding: 2px 6px;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 600;
    color: var(--text);
    background: rgba(0, 0, 0, 0.62);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .title {
    margin-top: 8px;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.25;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .sub {
    margin-top: 3px;
    font-size: 11.5px;
    color: var(--text-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .line {
    height: 11px;
    margin-top: 9px;
    border-radius: 4px;
  }
  .line.short {
    width: 55%;
    margin-top: 6px;
  }
  .more {
    min-height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .message {
    margin-top: 18vh;
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
</style>
