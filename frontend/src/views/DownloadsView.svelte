<script lang="ts">
  import DownloadCard from '../components/DownloadCard.svelte';
  import Icon from '../components/Icon.svelte';
  import { api } from '../lib/api';
  import { app } from '../lib/state.svelte';
  import { confirm, haptic } from '../lib/telegram';

  const ACTIVE = new Set(['running', 'queued', 'paused']);
  const ORDER: Record<string, number> = { running: 0, queued: 1, paused: 2 };

  const active = $derived(
    app.jobs.filter((job) => ACTIVE.has(job.status)).sort((a, b) => ORDER[a.status] - ORDER[b.status]),
  );
  const finished = $derived(
    app.jobs
      .filter((job) => !ACTIVE.has(job.status))
      .sort((a, b) => (b.finished_at ?? b.created_at) - (a.finished_at ?? a.created_at)),
  );

  async function clear(): Promise<void> {
    if (!(await confirm('Очистить историю загрузок? Файлы в медиатеке останутся.'))) return;
    haptic.tap();
    try {
      app.setJobs(await api.clearFinished());
    } catch (error) {
      app.fail(error);
    }
  }
</script>

<div class="screen">
  <h1 class="large-title">Загрузки</h1>

  {#if !app.jobs.length}
    <div class="empty">
      <div class="empty-icon"><Icon name="download" size={30} stroke={1.6} /></div>
      <h2>Пока ничего не качается</h2>
      <p>Найдите фильм или сериал и нажмите «Скачать» — прогресс появится здесь, а по завершении придёт сообщение в&nbsp;Telegram</p>
      <button class="chip on" onclick={() => app.selectTab('search')}>
        <Icon name="search" size={15} /> К поиску
      </button>
    </div>
  {:else}
    {#if active.length}
      <div class="section-label head">Сейчас</div>
      <div class="cards">
        {#each active as job (job.id)}
          <DownloadCard {job} />
        {/each}
      </div>
    {/if}

    {#if finished.length}
      <div class="head row">
        <span class="section-label">История</span>
        <button class="text-button" onclick={clear}>Очистить</button>
      </div>
      <div>
        {#each finished as job (job.id)}
          <DownloadCard {job} />
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .head {
    margin: 24px 0 10px;
  }
  .head.row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 2px;
  }
  .cards {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .empty {
    margin-top: 16vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 0 20px;
  }
  .empty-icon {
    display: flex;
    padding: 20px;
    border-radius: 26px;
    color: var(--text-2);
    background: var(--surface);
    border: 1px solid var(--line);
  }
  h2 {
    margin: 18px 0 0;
    font-size: 19px;
    font-weight: 700;
  }
  p {
    margin: 8px 0 20px;
    max-width: 300px;
    font-size: 14.5px;
    line-height: 1.45;
    color: var(--text-3);
  }
</style>
