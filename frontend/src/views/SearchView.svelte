<script lang="ts">
  import { api } from '../lib/api';
  import { query, results, searched, searchError, searching, selection } from '../lib/stores';
  import { haptic } from '../lib/telegram';
  import type { SearchItem } from '../lib/types';
  import ResultCard from '../components/ResultCard.svelte';
  import Spinner from '../components/Spinner.svelte';

  let timer: ReturnType<typeof setTimeout> | undefined;
  let lastQuery = '';

  $effect(() => {
    const q = $query.trim();
    clearTimeout(timer);
    if (!q) {
      results.set([]);
      searched.set(false);
      searchError.set('');
      return;
    }
    timer = setTimeout(() => runSearch(q), 300);
    return () => clearTimeout(timer);
  });

  async function runSearch(q: string): Promise<void> {
    if (q === lastQuery && $searched && !$searchError) return;
    lastQuery = q;
    searching.set(true);
    searchError.set('');
    try {
      results.set(await api.search(q));
    } catch (e) {
      searchError.set(e instanceof Error ? e.message : String(e));
      results.set([]);
    } finally {
      searching.set(false);
      searched.set(true);
    }
  }

  function submit(event: Event): void {
    event.preventDefault();
    const q = $query.trim();
    if (!q) return;
    (document.activeElement as HTMLElement | null)?.blur();
    clearTimeout(timer);
    haptic.impact('light');
    runSearch(q);
  }

  function open(item: SearchItem): void {
    haptic.impact('light');
    selection.set({ item, details: null, loading: true, error: '' });
  }
</script>

<h1>Поиск</h1>

<form class="field" onsubmit={submit}>
  <svg class="mag" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(235,235,245,.6)" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
  <input
    bind:value={$query}
    type="text"
    placeholder="Фильм или сериал…"
    enterkeyhint="search"
    autocomplete="off"
    autocapitalize="off"
  />
  {#if $query}
    <button type="button" class="clear" onclick={() => query.set('')} aria-label="Очистить">✕</button>
  {/if}
</form>

{#if !$query.trim()}
  <div class="empty">
    <div class="empty-icon">
      <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="rgba(235,235,245,.85)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="13" rx="2.5" /><path d="M3.5 7l2.2-3.4 4 1.2-2.2 3.4" /><path d="M9.7 4.8l4 1.2-2.2 3.4-4-1.2" /><path d="M13.7 6l4 1.2-2.2 3.3" /></svg>
    </div>
    <div class="empty-hint">Введите название фильма или сериала</div>
  </div>
{:else if $searchError}
  <div class="noresults">
    <div class="noresults-icon">⚠️</div>
    <div class="noresults-title">Ошибка поиска</div>
    <div class="noresults-hint">{$searchError}</div>
  </div>
{:else if $results.length}
  <div class="grid">
    {#each $results as item, i (item.id)}
      <ResultCard {item} index={i} onopen={open} />
    {/each}
  </div>
{:else if $searching}
  <div class="center"><Spinner size={26} /></div>
{:else if $searched}
  <div class="noresults">
    <div class="noresults-icon">🤷</div>
    <div class="noresults-title">Ничего не нашлось</div>
    <div class="noresults-hint">Попробуйте изменить запрос</div>
  </div>
{/if}

<style>
  h1 {
    font-size: 34px;
    font-weight: 700;
    letter-spacing: -0.5px;
    line-height: 1.1;
    margin: 0;
  }
  .field {
    margin-top: 14px;
    display: flex;
    align-items: center;
    gap: 9px;
    height: 48px;
    padding: 0 16px;
    border-radius: 24px;
    background: rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(30px) saturate(160%);
    -webkit-backdrop-filter: blur(30px) saturate(160%);
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.14),
      0 8px 28px rgba(0, 0, 0, 0.35);
  }
  .mag {
    flex: none;
  }
  input {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: none;
    font-size: 17px;
    color: #fff;
    padding: 0;
  }
  .clear {
    flex: none;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.14);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    color: rgba(255, 255, 255, 0.8);
    transition: transform 0.15s ease;
  }
  .clear:active {
    transform: scale(0.85);
  }
  .empty {
    margin-top: 120px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 0 26px;
  }
  .empty-icon {
    width: 92px;
    height: 92px;
    border-radius: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border: 1px solid rgba(255, 255, 255, 0.14);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.2),
      0 18px 44px rgba(0, 0, 0, 0.5);
  }
  .empty-hint {
    margin-top: 22px;
    font-size: 15px;
    line-height: 1.45;
    color: var(--text-2);
  }
  .grid {
    margin-top: 22px;
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
  }
  .center {
    margin-top: 120px;
    display: flex;
    justify-content: center;
  }
  .noresults {
    margin-top: 130px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 0 30px;
    animation: panelIn 0.3s ease;
  }
  .noresults-icon {
    font-size: 40px;
  }
  .noresults-title {
    margin-top: 14px;
    font-size: 18px;
    font-weight: 600;
  }
  .noresults-hint {
    margin-top: 6px;
    font-size: 14px;
    color: var(--text-3);
  }
</style>
