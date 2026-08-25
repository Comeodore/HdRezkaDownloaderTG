<script lang="ts">
  import DownloadCard from '../components/DownloadCard.svelte';
  import { api } from '../lib/api';
  import { jobs } from '../lib/stores';
  import { haptic } from '../lib/telegram';

  const FINISHED = new Set(['success', 'error', 'cancelled', 'partial']);
  const hasFinished = $derived($jobs.some((job) => FINISHED.has(job.status)));
  let clearing = $state(false);

  async function clearHistory(): Promise<void> {
    if (clearing) return;
    clearing = true;
    haptic.impact('light');
    try {
      jobs.set(await api.clearDownloads());
    } catch {
      /* ignore */
    } finally {
      clearing = false;
    }
  }
</script>

<div class="head">
  <h1>Загрузки</h1>
  {#if hasFinished}
    <button class="clear" onclick={clearHistory} disabled={clearing}>Очистить</button>
  {/if}
</div>

{#if $jobs.length}
  <div class="list">
    {#each $jobs as job (job.id)}
      <DownloadCard {job} />
    {/each}
  </div>
{:else}
  <div class="empty">
    <div class="empty-icon">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="rgba(235,235,245,.8)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11" /><path d="M7 11l5 5 5-5" /><path d="M4.5 20h15" /></svg>
    </div>
    <div class="empty-title">Пока пусто</div>
    <div class="empty-hint">Найдите фильм во вкладке Поиск и нажмите «Скачать»</div>
  </div>
{/if}

<style>
  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  h1 {
    font-size: 34px;
    font-weight: 700;
    letter-spacing: -0.5px;
    line-height: 1.1;
    margin: 0;
  }
  .clear {
    font-size: 15px;
    font-weight: 500;
    color: var(--accent);
    transition: opacity 0.15s ease;
  }
  .clear:active,
  .clear:disabled {
    opacity: 0.5;
  }
  .list {
    margin-top: 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .empty {
    margin-top: 150px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 0 30px;
  }
  .empty-icon {
    width: 84px;
    height: 84px;
    border-radius: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.16),
      0 16px 40px rgba(0, 0, 0, 0.45);
  }
  .empty-title {
    margin-top: 20px;
    font-size: 20px;
    font-weight: 700;
  }
  .empty-hint {
    margin-top: 7px;
    font-size: 14px;
    color: var(--text-2);
  }
</style>
