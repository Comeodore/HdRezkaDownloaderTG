<script lang="ts">
  import { api } from '../lib/api';
  import { episodesWord, formatSize, formatSpeed } from '../lib/format';
  import { upsertJob } from '../lib/stores';
  import { haptic } from '../lib/telegram';
  import type { Job, JobStatus } from '../lib/types';
  import Poster from './Poster.svelte';
  import Spinner from './Spinner.svelte';

  let { job }: { job: Job } = $props();

  interface Vis {
    word: string;
    wordColor: string;
    dot: string;
    pulse: boolean;
    showWord: boolean;
    showBar: boolean;
    orangeBar: boolean;
    shimmer: boolean;
  }

  const VIS: Record<JobStatus, Vis> = {
    running: { word: '', wordColor: 'var(--accent-light)', dot: 'var(--accent)', pulse: true, showWord: false, showBar: true, orangeBar: false, shimmer: true },
    queued: { word: 'В очереди', wordColor: 'var(--accent-light)', dot: 'var(--accent)', pulse: false, showWord: true, showBar: true, orangeBar: false, shimmer: false },
    paused: { word: 'Пауза', wordColor: 'var(--warning)', dot: 'var(--warning)', pulse: false, showWord: true, showBar: true, orangeBar: true, shimmer: false },
    success: { word: 'Готово', wordColor: 'var(--success)', dot: 'var(--success)', pulse: false, showWord: true, showBar: false, orangeBar: false, shimmer: false },
    error: { word: 'Ошибка', wordColor: 'var(--text-2)', dot: 'rgba(235,235,245,.4)', pulse: false, showWord: true, showBar: false, orangeBar: false, shimmer: false },
    partial: { word: 'Частично', wordColor: 'var(--text-2)', dot: 'rgba(235,235,245,.4)', pulse: false, showWord: true, showBar: false, orangeBar: false, shimmer: false },
    cancelled: { word: 'Отменено', wordColor: 'var(--text-2)', dot: 'rgba(235,235,245,.4)', pulse: false, showWord: true, showBar: false, orangeBar: false, shimmer: false },
  };

  let busy = $state(false);
  const vis = $derived(VIS[job.status]);
  const isDownloading = $derived(job.status === 'running');
  const isQueued = $derived(job.status === 'queued');
  const isPaused = $derived(job.status === 'paused');
  const isDone = $derived(job.status === 'success');
  const canRetry = $derived(job.status === 'error' || job.status === 'partial' || job.status === 'cancelled');
  const canCancel = $derived(isDownloading || isQueued || isPaused);

  const percent = $derived(
    isQueued
      ? 0
      : job.is_series
        ? job.total_episodes
          ? Math.round((job.done_episodes / job.total_episodes) * 100)
          : 0
        : Math.round(job.percent),
  );

  const tail = $derived(`${job.translator_name}${job.quality ? ` · ${job.quality}` : ''}`);
  const sub = $derived(buildSub(job));

  function progressText(j: Job): string {
    if (j.is_series) return `${j.done_episodes}/${j.total_episodes || '?'} эпизодов`;
    if (j.total) return `${formatSize(j.downloaded)} из ${formatSize(j.total)}`;
    return formatSize(j.downloaded);
  }

  function buildSub(j: Job): string {
    switch (j.status) {
      case 'running':
        return j.speed > 0 ? `${progressText(j)} · ${formatSpeed(j.speed)}` : progressText(j);
      case 'paused':
        return progressText(j);
      case 'queued':
        return j.is_series
          ? j.total_episodes
            ? episodesWord(j.total_episodes)
            : ''
          : j.total
            ? formatSize(j.total)
            : '';
      case 'success':
        return j.total ? formatSize(j.total) : j.is_series ? episodesWord(j.total_episodes) : '';
      case 'error':
        return j.error || 'Ошибка загрузки';
      default:
        return progressText(j);
    }
  }

  async function run(action: () => Promise<unknown>): Promise<void> {
    if (busy) return;
    busy = true;
    haptic.impact('medium');
    try {
      const result = await action();
      if (result && typeof result === 'object' && 'id' in result) upsertJob(result as Job);
    } catch {
      /* ignore — SSE will reconcile */
    } finally {
      busy = false;
    }
  }
</script>

<div class="card">
  <div class="thumb"><Poster src={job.poster} alt={job.name} kind={job.kind} /></div>

  <div class="content">
    <div class="name">{job.name}</div>
    <div class="status">
      <span class="dot" class:pulse={vis.pulse} style="background:{vis.dot};box-shadow:0 0 8px {vis.dot}"></span>
      {#if vis.showWord}
        <span class="word" style="color:{vis.wordColor}">{vis.word}</span>
        <span class="sep">·</span>
      {/if}
      <span class="tail">{tail}</span>
    </div>

    {#if vis.showBar}
      <div class="track">
        <div class="fill" class:orange={vis.orangeBar} class:shimmer={vis.shimmer} style="width:{percent}%"></div>
      </div>
    {/if}

    {#if sub}<div class="sub" class:err={job.status === 'error'}>{sub}</div>{/if}
  </div>

  <div class="actions">
    {#if busy}
      <Spinner size={18} />
    {:else}
      {#if isDownloading}
        <button class="btn primary" onclick={() => run(() => api.pauseDownload(job.id))} aria-label="Пауза">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff"><rect x="6" y="5" width="4" height="14" rx="1.4" /><rect x="14" y="5" width="4" height="14" rx="1.4" /></svg>
        </button>
      {:else if isPaused}
        <button class="btn primary" onclick={() => run(() => api.resumeDownload(job.id))} aria-label="Продолжить">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="#fff"><path d="M8 5.5v13c0 .8.9 1.3 1.6.9l10-6.5c.6-.4.6-1.4 0-1.8l-10-6.5c-.7-.4-1.6.1-1.6.9z" /></svg>
        </button>
      {/if}
      {#if canCancel}
        <button class="btn subtle" onclick={() => run(() => api.cancelDownload(job.id))} aria-label="Отменить">✕</button>
      {/if}
      {#if canRetry}
        <button class="btn primary" onclick={() => run(() => api.retryDownload(job.id))} aria-label="Повторить">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12a8 8 0 1 1-2.4-5.7" /><path d="M20 4v4.5h-4.5" /></svg>
        </button>
      {/if}
      {#if isDone}
        <span class="done-badge">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#30D158" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
        </span>
      {/if}
    {/if}
  </div>
</div>

<style>
  .card {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 12px;
    border-radius: 22px;
    background: rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(30px) saturate(160%);
    -webkit-backdrop-filter: blur(30px) saturate(160%);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.12),
      0 12px 34px rgba(0, 0, 0, 0.4);
    animation: cardIn 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .thumb {
    width: 52px;
    height: 78px;
    border-radius: 12px;
    flex: none;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.1);
  }
  .content {
    flex: 1;
    min-width: 0;
  }
  .name {
    font-size: 15px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .status {
    margin-top: 4px;
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    color: var(--text-2);
    white-space: nowrap;
    overflow: hidden;
  }
  .dot {
    flex: none;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    transition: background 0.4s;
  }
  .dot.pulse {
    animation: pulse 1.6s ease-in-out infinite;
  }
  .word {
    font-weight: 500;
    transition: color 0.4s;
  }
  .sep {
    color: rgba(235, 235, 245, 0.35);
  }
  .tail {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .track {
    margin-top: 9px;
    height: 5px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.1);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, #0a84ff, #5ac8fa, #0a84ff);
    background-size: 200% 100%;
    box-shadow: 0 0 10px rgba(10, 132, 255, 0.7);
    transition: width 0.38s linear;
  }
  .fill.shimmer {
    animation: shimmer 2.2s linear infinite;
  }
  .fill.orange {
    background: rgba(255, 159, 10, 0.75);
    box-shadow: none;
  }
  .sub {
    margin-top: 6px;
    font-size: 11.5px;
    color: var(--text-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sub.err {
    color: var(--danger);
    white-space: normal;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 7px;
    flex: none;
  }
  .btn {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.15s ease;
  }
  .btn:active {
    transform: scale(0.88);
  }
  .btn.primary {
    background: linear-gradient(180deg, rgba(10, 132, 255, 0.9), rgba(0, 100, 220, 0.8));
    border: 1px solid rgba(255, 255, 255, 0.28);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.35),
      0 6px 16px rgba(10, 132, 255, 0.35);
  }
  .btn.subtle {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
    color: rgba(235, 235, 245, 0.7);
    font-size: 14px;
  }
  .done-badge {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(48, 209, 88, 0.14);
    border: 1px solid rgba(48, 209, 88, 0.3);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }
</style>
