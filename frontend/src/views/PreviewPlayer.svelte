<script lang="ts">
  import { fade } from 'svelte/transition';
  import Icon from '../components/Icon.svelte';
  import Spinner from '../components/Spinner.svelte';
  import { previewUrl } from '../lib/api';
  import { app } from '../lib/state.svelte';
  import { haptic } from '../lib/telegram';
  import type { Translator } from '../lib/types';

  let {
    title,
    url,
    voices,
    chosen = $bindable(),
    onvoice,
  }: { title: string; url: string; voices: Translator[]; chosen: string | null; onvoice: () => void } = $props();

  /** A fragment, not the whole film: enough to judge the voice-over and picture. */
  const WINDOW = 120;

  let video: HTMLVideoElement | undefined = $state();
  let time = $state(0);
  let span = $state(WINDOW);
  let playing = $state(false);
  let buffering = $state(true);
  let ended = $state(false);
  let failed = $state(false);
  let anchor = 0;
  let resumeAt: number | null = null;
  let renewed = false;

  const src = $derived(chosen && app.token ? previewUrl(url, chosen, app.token) : '');

  function onMetadata(): void {
    if (!video) return;
    const duration = video.duration;
    if (Number.isFinite(duration) && duration > 0) {
      if (!anchor) anchor = Math.min(600, duration * 0.3);
      span = Math.max(10, Math.min(WINDOW, duration - anchor - 1));
    }
    failed = false;
    ended = false;
    video.currentTime = anchor + Math.min(resumeAt ?? 0, span);
    resumeAt = null;
    video.play().catch(() => (buffering = false));
  }

  /** The session token in the URL may have expired while the app stayed open — renew once. */
  async function onError(): Promise<void> {
    if (!renewed) {
      renewed = true;
      resumeAt = Math.min(time, span);
      try {
        await app.getToken(true);
        return; // `src` follows the new token and the video reloads
      } catch {
        /* fall through */
      }
    }
    failed = true;
    buffering = false;
  }

  function onTime(): void {
    if (!video) return;
    const position = video.currentTime - anchor;
    if (position >= span) {
      video.pause();
      ended = true;
      time = span;
      return;
    }
    time = Math.max(0, position);
  }

  function toggle(): void {
    if (!video) return;
    haptic.tap();
    if (ended) {
      ended = false;
      time = 0;
      video.currentTime = anchor;
      video.play().catch(() => {});
    } else if (video.paused) {
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  }

  function shuffle(): void {
    if (!video || !Number.isFinite(video.duration)) return;
    haptic.tap();
    anchor = video.duration * (0.08 + Math.random() * 0.65);
    span = Math.max(10, Math.min(WINDOW, video.duration - anchor - 1));
    ended = false;
    time = 0;
    video.currentTime = anchor;
    video.play().catch(() => {});
  }

  function seek(event: PointerEvent): void {
    if (!video) return;
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    ended = false;
    time = fraction * span;
    video.currentTime = anchor + time;
  }

  function seekKey(event: KeyboardEvent): void {
    const step = event.key === 'ArrowLeft' ? -5 : event.key === 'ArrowRight' ? 5 : 0;
    if (!video || !step) return;
    event.preventDefault();
    time = Math.min(span, Math.max(0, time + step));
    video.currentTime = anchor + time;
  }

  function switchVoice(key: string): void {
    if (key === chosen) return;
    haptic.select();
    resumeAt = Math.min(time, span);
    buffering = true;
    chosen = key;
    onvoice();
  }

  const clock = (seconds: number) =>
    `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
      .toString()
      .padStart(2, '0')}`;
</script>

<div class="overlay" transition:fade={{ duration: 200 }}>
  <div class="head">
    <div class="title">
      <span class="eyebrow">Превью</span>
      <span class="name">{title}</span>
    </div>
    <button class="icon-button" onclick={() => app.back()} aria-label="Закрыть превью">
      <Icon name="close" size={16} stroke={2.4} />
    </button>
  </div>

  <div class="player">
    <!-- svelte-ignore a11y_media_has_caption -->
    <video
      bind:this={video}
      {src}
      playsinline
      preload="metadata"
      onloadedmetadata={onMetadata}
      ontimeupdate={onTime}
      onplay={() => (playing = true)}
      onpause={() => (playing = false)}
      onwaiting={() => (buffering = true)}
      onplaying={() => (buffering = false)}
      oncanplay={() => (buffering = false)}
      onerror={onError}
    ></video>

    <button class="hit" onclick={toggle} aria-label={playing ? 'Пауза' : 'Смотреть'}>
      {#if failed}
        <span class="notice">Не удалось загрузить превью</span>
      {:else if buffering}
        <Spinner size={32} />
      {:else if !playing}
        <span class="big"><Icon name={ended ? 'retry' : 'play'} size={24} stroke={2.2} /></span>
      {/if}
    </button>
  </div>

  <div class="controls">
    <span class="time">{clock(time)}</span>
    <div
      class="track"
      role="slider"
      tabindex="0"
      aria-label="Позиция в фрагменте"
      aria-valuemin={0}
      aria-valuemax={Math.round(span)}
      aria-valuenow={Math.round(time)}
      onpointerdown={seek}
      onkeydown={seekKey}
    >
      <div class="rail"><div class="fill" style:width="{(time / span) * 100}%"></div></div>
    </div>
    <span class="time">{clock(span)}</span>
    <button class="icon-button small" onclick={shuffle} aria-label="Другая сцена">
      <Icon name="shuffle" size={16} />
    </button>
  </div>

  <div class="voices">
    {#each voices as voice (voice.key)}
      <button class="chip" class:on={chosen === voice.key} onclick={() => switchVoice(voice.key)}>{voice.name}</button>
    {/each}
  </div>
  <p class="note">При смене озвучки момент сохраняется — удобно сравнивать</p>
</div>

<style>
  .overlay {
    position: absolute;
    inset: 0;
    z-index: 40;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: calc(16px + var(--safe-top)) 0 calc(16px + var(--safe-bottom));
    background: rgba(5, 5, 7, 0.97);
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 0 16px 14px;
  }
  .title {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .eyebrow {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    color: var(--text-3);
  }
  .name {
    font-size: 18px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .player {
    position: relative;
    aspect-ratio: 16 / 9;
    background: #000;
  }
  video {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: contain;
  }
  .hit {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .big {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-left: 3px;
    background: rgba(255, 255, 255, 0.16);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--line-strong);
  }
  .notice {
    font-size: 14px;
    color: var(--text-2);
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 16px 0;
  }
  .time {
    min-width: 34px;
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    color: var(--text-3);
    text-align: center;
  }
  .track {
    flex: 1;
    padding: 12px 0;
    cursor: pointer;
    touch-action: none;
  }
  .rail {
    height: 4px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.16);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--text);
    border-radius: 2px;
  }
  .icon-button.small {
    width: 36px;
    height: 36px;
  }
  .voices {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 18px 16px 4px;
    scrollbar-width: none;
  }
  .note {
    margin: 10px 16px 0;
    font-size: 12px;
    color: var(--text-4);
    text-align: center;
  }
</style>
