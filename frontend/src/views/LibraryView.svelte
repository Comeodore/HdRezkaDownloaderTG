<script lang="ts">
  import { onMount } from 'svelte';
  import LibraryCard from '../components/LibraryCard.svelte';
  import { api } from '../lib/api';
  import { formatSize, titlesWord } from '../lib/format';
  import { library } from '../lib/stores';
  import { haptic } from '../lib/telegram';

  let loaded = $state(false);
  let error = $state('');
  let refreshing = $state(false);
  let leaving = $state<Set<string>>(new Set());

  const totalSize = $derived($library.reduce((sum, item) => sum + item.size, 0));
  const summary = $derived(`${titlesWord($library.length)} · ${formatSize(totalSize)}`);

  onMount(load);

  async function load(): Promise<void> {
    error = '';
    try {
      library.set(await api.library());
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loaded = true;
    }
  }

  async function refresh(): Promise<void> {
    if (refreshing) return;
    refreshing = true;
    haptic.impact('light');
    try {
      const [items] = await Promise.all([api.library(), delay(1000)]);
      library.set(items);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      refreshing = false;
    }
  }

  function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function remove(id: string): Promise<void> {
    if (leaving.has(id)) return;
    haptic.impact('medium');
    leaving = new Set(leaving).add(id);
    try {
      await api.deleteLibrary(id);
    } catch {
      const next = new Set(leaving);
      next.delete(id);
      leaving = next;
      return;
    }
    setTimeout(() => {
      library.update((list) => list.filter((entry) => entry.id !== id));
      const next = new Set(leaving);
      next.delete(id);
      leaving = next;
    }, 330);
  }
</script>

<div class="head">
  <h1>Медиатека</h1>
  <button class="refresh" onclick={refresh} aria-label="Обновить">
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="rgba(235,235,245,.85)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class:spin={refreshing}><path d="M20 12a8 8 0 1 1-2.4-5.7" /><path d="M20 4v4.5h-4.5" /></svg>
  </button>
</div>

{#if error && !$library.length}
  <div class="state">{error}</div>
{:else if loaded && !$library.length}
  <div class="state">Медиатека пуста. Скачанное появится здесь.</div>
{:else if $library.length}
  <div class="summary">{summary}</div>
  <div class="list">
    {#each $library as item (item.id)}
      <div class="row-wrap" class:leaving={leaving.has(item.id)}>
        <LibraryCard {item} ondelete={remove} />
      </div>
    {/each}
  </div>
{/if}

<style>
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  h1 {
    font-size: 34px;
    font-weight: 700;
    letter-spacing: -0.5px;
    line-height: 1.1;
    margin: 0;
  }
  .refresh {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.14);
    transition: transform 0.15s ease;
  }
  .refresh:active {
    transform: scale(0.88);
  }
  .spin {
    animation: spin 0.9s cubic-bezier(0.4, 0.2, 0.2, 1) infinite;
  }
  .summary {
    margin-top: 6px;
    font-size: 13px;
    color: var(--text-3);
  }
  .list {
    margin-top: 6px;
    display: flex;
    flex-direction: column;
  }
  .row-wrap {
    overflow: hidden;
    max-height: 80px;
    opacity: 1;
    transition:
      max-height 0.32s cubic-bezier(0.4, 0, 0.2, 1),
      opacity 0.32s cubic-bezier(0.4, 0, 0.2, 1);
  }
  .row-wrap.leaving {
    max-height: 0;
    opacity: 0;
  }
  .state {
    margin-top: 60px;
    text-align: center;
    color: var(--text-2);
    font-size: 15px;
    padding: 0 30px;
  }
</style>
