<script lang="ts">
  import { onMount } from 'svelte';
  import Spinner from './components/Spinner.svelte';
  import TabBar from './components/TabBar.svelte';
  import TitleSheet from './components/TitleSheet.svelte';
  import { api, subscribeDownloads } from './lib/api';
  import { jobs, selection, tab, token, upsertJob, user } from './lib/stores';
  import { haptic, isTelegram } from './lib/telegram';
  import type { Job } from './lib/types';
  import DownloadsView from './views/DownloadsView.svelte';
  import LibraryView from './views/LibraryView.svelte';
  import SearchView from './views/SearchView.svelte';

  let booting = $state(true);
  let fatal = $state('');
  let unsubscribe: (() => void) | null = null;
  const statusMemo = new Map<string, string>();

  onMount(() => {
    boot();
    return () => unsubscribe?.();
  });

  async function boot(): Promise<void> {
    try {
      const { token: sessionToken, user: sessionUser } = await api.session();
      token.set(sessionToken);
      user.set(sessionUser);
      const initial = await api.downloads();
      for (const job of initial) statusMemo.set(job.id, job.status);
      jobs.set(initial);
      unsubscribe = subscribeDownloads(sessionToken, handleEvent);
    } catch (e) {
      fatal = classify(e);
    } finally {
      booting = false;
    }
  }

  function handleEvent(event: unknown): void {
    const payload = event as { type: string; jobs?: Job[]; job?: Job };
    if (payload.type === 'snapshot' && payload.jobs) {
      for (const job of payload.jobs) noteCompletion(job);
      jobs.set(payload.jobs);
    } else if (payload.type === 'job' && payload.job) {
      noteCompletion(payload.job);
      upsertJob(payload.job);
    }
  }

  function noteCompletion(job: Job): void {
    const previous = statusMemo.get(job.id);
    if (job.status === 'success' && previous && previous !== 'success') haptic.success();
    statusMemo.set(job.id, job.status);
  }

  function classify(e: unknown): string {
    if (!isTelegram()) return 'outside';
    const message = e instanceof Error ? e.message : String(e);
    if (message.includes('403')) return 'forbidden';
    return message || 'error';
  }
</script>

<div class="stage">
  <div class="ambient" aria-hidden="true">
    <span class="blob b1"></span>
    <span class="blob b2"></span>
    <span class="blob b3"></span>
  </div>

  {#if booting}
    <div class="center-fill"><Spinner size={30} /></div>
  {:else if fatal === 'outside'}
    <div class="gate">
      <div class="gate-icon">📱</div>
      <div class="gate-title">Откройте в Telegram</div>
      <div class="gate-hint">Это приложение работает только внутри Telegram.</div>
    </div>
  {:else if fatal === 'forbidden'}
    <div class="gate">
      <div class="gate-icon">🔒</div>
      <div class="gate-title">Доступ закрыт</div>
      <div class="gate-hint">Ваш аккаунт не в списке разрешённых.</div>
    </div>
  {:else if fatal}
    <div class="gate">
      <div class="gate-icon">⚠️</div>
      <div class="gate-title">Не удалось запустить</div>
      <div class="gate-hint">{fatal}</div>
    </div>
  {:else}
    {#key $tab}
      <main class="panel">
        {#if $tab === 'search'}
          <SearchView />
        {:else if $tab === 'downloads'}
          <DownloadsView />
        {:else}
          <LibraryView />
        {/if}
      </main>
    {/key}
    <TabBar />
    {#if $selection}
      <TitleSheet item={$selection.item} />
    {/if}
  {/if}
</div>

<style>
  .stage {
    position: fixed;
    inset: 0;
    overflow: hidden;
    background: var(--bg);
    color: var(--text);
  }
  .ambient {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
    z-index: 0;
  }
  .blob {
    position: absolute;
    border-radius: 50%;
    display: block;
  }
  .b1 {
    top: -80px;
    left: -60px;
    width: 340px;
    height: 340px;
    background: radial-gradient(circle, rgba(10, 132, 255, 0.3), transparent 65%);
    filter: blur(50px);
    animation: drift 16s ease-in-out infinite alternate;
  }
  .b2 {
    top: 280px;
    right: -120px;
    width: 380px;
    height: 380px;
    background: radial-gradient(circle, rgba(120, 80, 255, 0.2), transparent 65%);
    filter: blur(60px);
    animation: drift2 20s ease-in-out infinite alternate;
  }
  .b3 {
    bottom: -100px;
    left: 40px;
    width: 300px;
    height: 300px;
    background: radial-gradient(circle, rgba(60, 200, 220, 0.13), transparent 65%);
    filter: blur(55px);
    animation: drift 24s ease-in-out infinite alternate-reverse;
  }
  .panel {
    position: absolute;
    inset: 0;
    z-index: 1;
    overflow-y: auto;
    padding: calc(22px + var(--safe-top)) 20px calc(130px + var(--safe-bottom));
    animation: panelIn 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .center-fill {
    position: absolute;
    inset: 0;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .gate {
    position: absolute;
    inset: 0;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 32px;
    gap: 8px;
  }
  .gate-icon {
    font-size: 52px;
  }
  .gate-title {
    font-size: 20px;
    font-weight: 700;
  }
  .gate-hint {
    color: var(--text-2);
    max-width: 280px;
  }
</style>
