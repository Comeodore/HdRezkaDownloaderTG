<script lang="ts">
  import { api } from '../lib/api';
  import { episodesWord, formatEta, formatSize, formatSpeed, relativeDay } from '../lib/format';
  import { app } from '../lib/state.svelte';
  import { confirm, haptic } from '../lib/telegram';
  import type { Job } from '../lib/types';
  import Icon from './Icon.svelte';
  import Poster from './Poster.svelte';
  import Spinner from './Spinner.svelte';

  let { job }: { job: Job } = $props();

  let busy = $state(false);

  const active = $derived(job.status === 'running' || job.status === 'queued' || job.status === 'paused');
  const tags = $derived(
    [job.translator_name, job.quality ?? (job.max_height < 1080 ? `до ${job.max_height}p` : null)]
      .filter(Boolean)
      .join(' · '),
  );

  const progressLine = $derived.by(() => {
    if (job.status === 'queued') return 'В очереди';
    if (job.status === 'paused') return `Пауза · ${Math.floor(job.percent)}%`;
    const parts: string[] = [];
    if (job.is_series && job.total_episodes) {
      parts.push(`${job.current || 'Серия'} · ${Math.min(job.done_episodes + 1, job.total_episodes)} из ${job.total_episodes}`);
    } else if (job.total) {
      parts.push(`${formatSize(job.downloaded)} из ${formatSize(job.total)}`);
    } else {
      parts.push('Подготовка…');
    }
    if (job.speed > 0) parts.push(formatSpeed(job.speed));
    if (job.eta) parts.push(formatEta(job.eta));
    return parts.join(' · ');
  });

  const resultLine = $derived.by(() => {
    const when = job.finished_at ? relativeDay(job.finished_at) : '';
    switch (job.status) {
      case 'success': {
        const what = job.is_series ? episodesWord(job.done_episodes) : '';
        return ['Готово', what, job.bytes_done ? formatSize(job.bytes_done) : '', when].filter(Boolean).join(' · ');
      }
      case 'partial':
        return `Частично: ${job.done_episodes} из ${job.total_episodes} · ${when}`;
      case 'cancelled':
        return ['Отменено', when].filter(Boolean).join(' · ');
      default:
        return job.error || 'Ошибка загрузки';
    }
  });

  async function act(action: () => Promise<unknown>): Promise<boolean> {
    if (busy) return false;
    busy = true;
    haptic.tap();
    try {
      const result = await action();
      if (result && typeof result === 'object' && 'id' in result) app.upsertJob(result as Job);
      return true;
    } catch (error) {
      app.fail(error);
      return false;
    } finally {
      busy = false;
    }
  }

  async function cancel(): Promise<void> {
    const message = job.is_series
      ? `Остановить загрузку «${job.name}»? Уже скачанные серии останутся.`
      : `Отменить загрузку «${job.name}»? Скачанная часть будет удалена.`;
    if (await confirm(message)) act(() => api.cancel(job.id));
  }

  async function remove(): Promise<void> {
    if (await act(() => api.remove(job.id))) app.jobs = app.jobs.filter((item) => item.id !== job.id);
  }

  function open(): void {
    app.openTitle({ url: job.url, title: job.name, kind: job.kind, year: job.year, poster: job.poster });
  }
</script>

{#if active}
  <article class="card">
    <button class="thumb" onclick={open} aria-label="Открыть «{job.name}»">
      <Poster src={job.poster} alt="" kind={job.kind} />
    </button>
    <div class="content">
      <div class="name">{job.name}</div>
      {#if tags}<div class="tags">{tags}</div>{/if}
      <div class="bar" class:paused={job.status === 'paused'} class:queued={job.status === 'queued'}>
        <div class="fill" style:width="{job.status === 'queued' ? 0 : job.percent}%"></div>
      </div>
      <div class="line">{progressLine}</div>
    </div>
    <div class="actions">
      {#if busy}
        <Spinner size={18} />
      {:else}
        {#if job.status === 'paused'}
          <button class="icon-button primary" onclick={() => act(() => api.resume(job.id))} aria-label="Продолжить">
            <Icon name="play" size={15} />
          </button>
        {:else}
          <button class="icon-button" onclick={() => act(() => api.pause(job.id))} aria-label="Пауза">
            <Icon name="pause" size={14} />
          </button>
        {/if}
        <button class="icon-button ghost" onclick={cancel} aria-label="Отменить">
          <Icon name="close" size={14} stroke={2.4} />
        </button>
      {/if}
    </div>
  </article>
{:else}
  <article class="row">
    <button class="row-main" onclick={open}>
      <span class="mini"><Poster src={job.poster} alt="" kind={job.kind} /></span>
      <span class="row-text">
        <span class="name">{job.name}</span>
        <span class="result {job.status}">{resultLine}</span>
      </span>
    </button>
    {#if busy}
      <Spinner size={16} />
    {:else}
      {#if job.status !== 'success'}
        <button class="icon-button ghost" onclick={() => act(() => api.retry(job.id))} aria-label="Повторить">
          <Icon name="retry" size={16} />
        </button>
      {/if}
      <button class="icon-button ghost" onclick={remove} aria-label="Убрать из списка">
        <Icon name="trash" size={16} />
      </button>
    {/if}
  </article>
{/if}

<style>
  .card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    border-radius: var(--radius-l);
    background: var(--surface);
    border: 1px solid var(--line);
    animation: fade-up 0.35s var(--ease-out);
  }
  .thumb {
    flex: none;
    width: 52px;
    height: 78px;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--line);
  }
  .content {
    flex: 1;
    min-width: 0;
  }
  .name {
    font-size: 15px;
    font-weight: 650;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tags {
    margin-top: 2px;
    font-size: 12.5px;
    color: var(--text-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .bar {
    margin-top: 10px;
    height: 5px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.1);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    border-radius: 3px;
    background: var(--text);
    transition: width 0.8s linear;
  }
  .bar.paused .fill {
    background: var(--warning);
  }
  .bar.queued {
    background: repeating-linear-gradient(-45deg, rgba(255, 255, 255, 0.08) 0 6px, rgba(255, 255, 255, 0.03) 6px 12px);
  }
  .line {
    margin-top: 7px;
    font-size: 12.5px;
    font-variant-numeric: tabular-nums;
    color: var(--text-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .actions {
    flex: none;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }
  .icon-button {
    width: 36px;
    height: 36px;
  }
  .icon-button.primary {
    color: var(--on-primary);
    background: var(--primary);
    border-color: transparent;
  }
  .icon-button.ghost {
    color: var(--text-2);
    background: transparent;
    border-color: transparent;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 8px 0;
    border-bottom: 1px solid var(--line);
  }
  .row-main {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 12px;
    text-align: left;
  }
  .row-main:active {
    opacity: 0.6;
  }
  .mini {
    flex: none;
    width: 36px;
    height: 54px;
    border-radius: 7px;
    overflow: hidden;
  }
  .row-text {
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .result {
    margin-top: 2px;
    font-size: 12.5px;
    color: var(--text-3);
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .result.success {
    color: var(--success);
  }
  .result.partial {
    color: var(--warning);
  }
  .result.error {
    color: var(--danger);
  }
</style>
