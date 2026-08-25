<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { api, previewUrl } from '../lib/api';
  import { episodesWord, kindLabel, plural, seasonsWord } from '../lib/format';
  import { selection, tab, token, upsertJob } from '../lib/stores';
  import { backButton, haptic } from '../lib/telegram';
  import type { SearchItem, SeasonInfo, TitleDetails } from '../lib/types';
  import Poster from './Poster.svelte';
  import Spinner from './Spinner.svelte';

  let { item }: { item: SearchItem } = $props();

  let visible = $state(false);
  let closing = false;

  let loading = $state(true);
  let error = $state('');
  let details = $state<TitleDetails | null>(null);
  let chosen = $state<number | null>(null);

  let seasons = $state<SeasonInfo[]>([]);
  let selected = $state<number[]>([]);
  let loadingSeasons = $state(false);
  let seasonReq = 0;

  let starting = $state(false);

  const PREVIEW_WINDOW = 120;

  let previewOpen = $state(false);
  let videoEl: HTMLVideoElement | undefined = $state();
  let pvTime = $state(0);
  let pvWindow = $state(PREVIEW_WINDOW);
  let pvPlaying = $state(false);
  let pvBuffering = $state(true);
  let pvEnded = $state(false);
  let previewAnchor = 0;
  let previewResume: number | null = null;
  let warmupTimer: ReturnType<typeof setTimeout> | undefined;

  const isSeries = $derived(details?.is_series ?? item.kind === 'series');
  const previewSrc = $derived(
    previewOpen && chosen !== null && $token ? previewUrl(item.url, chosen, $token) : '',
  );
  const multiSeason = $derived(seasons.length > 1);
  const allSelected = $derived(multiSeason && selected.length === seasons.length);
  const selectedEpisodes = $derived(
    seasons.filter((s) => selected.includes(s.number)).reduce((sum, s) => sum + s.episodes, 0),
  );

  const subline = $derived(
    multiSeason
      ? `${seasonsWord(seasons.length)} · ${episodesWord(seasons.reduce((a, s) => a + s.episodes, 0))}`
      : '',
  );

  const ctaLabel = $derived(buildCtaLabel());
  const ctaEnabled = $derived(
    !loading && !error && chosen !== null && !(isSeries && multiSeason && selected.length === 0),
  );

  function buildCtaLabel(): string {
    if (!isSeries) return 'Скачать фильм';
    if (!multiSeason) return 'Скачать сериал';
    if (selected.length === 0) return 'Выберите сезоны';
    return `Скачать ${selected.length} ${plural(selected.length, 'сезон', 'сезона', 'сезонов')} · ${selectedEpisodes} эп.`;
  }

  onMount(() => {
    backButton.show(close);
    load();
    requestAnimationFrame(() => requestAnimationFrame(() => (visible = true)));
    return () => backButton.hide();
  });

  async function load(): Promise<void> {
    loading = true;
    error = '';
    try {
      const data = await api.title(item.url);
      details = data;
      chosen = data.translators.length ? data.translators[0].id : null;
      warmPreview();
      await loadSeasons();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function loadSeasons(): Promise<void> {
    const my = ++seasonReq;
    if (!details?.is_series || chosen === null) {
      seasons = [];
      selected = [];
      return;
    }
    loadingSeasons = true;
    try {
      const list = await api.seasons(item.url, chosen);
      if (my !== seasonReq) return;
      seasons = list;
      selected = list.length > 1 ? [list[0].number] : [];
    } catch {
      if (my !== seasonReq) return;
      seasons = [];
      selected = [];
    } finally {
      if (my === seasonReq) loadingSeasons = false;
    }
  }

  function pickVoice(id: number): void {
    if (id === chosen) return;
    haptic.impact('light');
    chosen = id;
    warmPreview();
    loadSeasons();
  }

  function warmPreview(): void {
    if (chosen === null || !$token) return;
    const url = previewUrl(item.url, chosen, $token);
    clearTimeout(warmupTimer);
    // resolve stream links server-side ahead of the «Превью» tap
    warmupTimer = setTimeout(() => {
      fetch(url, { headers: { Range: 'bytes=0-0' } }).catch(() => {});
    }, 250);
  }

  function openPreview(): void {
    haptic.impact('light');
    previewAnchor = 0;
    previewResume = null;
    pvTime = 0;
    pvWindow = PREVIEW_WINDOW;
    pvEnded = false;
    pvBuffering = true;
    pvPlaying = false;
    previewOpen = true;
    backButton.hide();
    backButton.show(closePreview);
  }

  function closePreview(): void {
    previewOpen = false;
    backButton.hide();
    backButton.show(close);
  }

  function previewVoice(id: number): void {
    if (id === chosen) return;
    previewResume = Math.min(pvTime, pvWindow);
    pvBuffering = true;
    pickVoice(id);
  }

  function initPreviewWindow(): void {
    const video = videoEl;
    if (!video) return;
    const duration = video.duration;
    if (Number.isFinite(duration) && duration > 0) {
      if (!previewAnchor) previewAnchor = Math.max(0, Math.min(600, duration * 0.35));
      pvWindow = Math.max(10, Math.min(PREVIEW_WINDOW, duration - previewAnchor - 1));
    }
    pvEnded = false;
    video.currentTime = previewAnchor + Math.min(previewResume ?? 0, pvWindow);
    video.play().catch(() => {});
  }

  function onPvTime(): void {
    const video = videoEl;
    if (!video) return;
    const t = video.currentTime - previewAnchor;
    if (t >= pvWindow) {
      video.pause();
      pvEnded = true;
      pvTime = pvWindow;
      return;
    }
    pvTime = Math.max(0, t);
  }

  function togglePvPlay(): void {
    const video = videoEl;
    if (!video) return;
    haptic.impact('light');
    if (pvEnded) {
      pvEnded = false;
      pvTime = 0;
      video.currentTime = previewAnchor;
      video.play().catch(() => {});
      return;
    }
    if (video.paused) video.play().catch(() => {});
    else video.pause();
  }

  function shuffleScene(): void {
    const video = videoEl;
    if (!video) return;
    haptic.impact('light');
    const duration = video.duration;
    if (!Number.isFinite(duration) || duration <= 0) return;
    previewAnchor = duration * (0.08 + Math.random() * 0.65);
    pvWindow = Math.max(10, Math.min(PREVIEW_WINDOW, duration - previewAnchor - 1));
    previewResume = null;
    pvEnded = false;
    pvTime = 0;
    video.currentTime = previewAnchor;
    video.play().catch(() => {});
  }

  function seekPv(event: PointerEvent): void {
    const video = videoEl;
    if (!video) return;
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    pvEnded = false;
    pvTime = fraction * pvWindow;
    video.currentTime = previewAnchor + pvTime;
  }

  function seekPvKey(event: KeyboardEvent): void {
    const video = videoEl;
    if (!video) return;
    const step = event.key === 'ArrowLeft' ? -5 : event.key === 'ArrowRight' ? 5 : 0;
    if (!step) return;
    event.preventDefault();
    pvEnded = false;
    pvTime = Math.min(pvWindow, Math.max(0, pvTime + step));
    video.currentTime = previewAnchor + pvTime;
  }

  function fmtTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function toggleSeason(number: number): void {
    haptic.impact('light');
    selected = selected.includes(number)
      ? selected.filter((n) => n !== number)
      : [...selected, number].sort((a, b) => a - b);
  }

  function toggleAll(): void {
    haptic.impact('light');
    selected = allSelected ? [] : seasons.map((s) => s.number);
  }

  async function close(): Promise<void> {
    if (closing) return;
    closing = true;
    visible = false;
    await tick();
    setTimeout(() => selection.set(null), 480);
  }

  async function start(): Promise<void> {
    if (!ctaEnabled || chosen === null || starting) return;
    starting = true;
    haptic.impact('medium');
    try {
      const seasonNumbers = isSeries && multiSeason ? selected : [];
      const job = await api.createDownload(item.url, chosen, item.poster, seasonNumbers);
      upsertJob(job);
      await close();
      tab.set('downloads');
    } catch (e) {
      haptic.error();
      error = e instanceof Error ? e.message : String(e);
    } finally {
      starting = false;
    }
  }
</script>

<div
  class="backdrop"
  style="opacity:{visible ? 1 : 0}"
  onclick={close}
  role="presentation"
></div>

<div class="sheet" style="transform:translateY({visible ? '0' : '110%'})">
  <div
    class="grabber"
    onclick={close}
    role="button"
    tabindex="-1"
    aria-label="Закрыть"
    onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && close()}
  ></div>

  <div class="hero">
    <div class="poster"><Poster src={item.poster} alt={item.title} kind={item.kind} /></div>
    <div class="hero-info">
      <div class="title">{details?.name ?? item.title}</div>
      <div class="chips-meta">
        {#if kindLabel(details?.kind ?? item.kind)}
          <span class="chip-meta">{kindLabel(details?.kind ?? item.kind)}</span>
        {/if}
        {#if item.year}<span class="chip-meta">{item.year}</span>{/if}
      </div>
      {#if details?.rating || details?.rating_imdb || details?.rating_kp}
        <div class="rates">
          {#if details.rating}
            <span class="rate">
              <svg class="star" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17l-6.1 3.6 1.4-6.8L2.2 9.1l6.9-.8z" /></svg>
              {details.rating.toFixed(1)}
            </span>
          {/if}
          {#if details.rating_imdb}
            <span class="rate"><i class="rate-badge imdb">IMDb</i>{details.rating_imdb.toFixed(1)}</span>
          {/if}
          {#if details.rating_kp}
            <span class="rate"><i class="rate-badge kp">КП</i>{details.rating_kp.toFixed(1)}</span>
          {/if}
        </div>
      {/if}
      {#if subline}<div class="subline">{subline}</div>{/if}
    </div>
  </div>

  {#if loading}
    <div class="center"><Spinner /></div>
  {:else if error}
    <div class="error">{error}</div>
    <button class="ghost" onclick={load}>Повторить</button>
  {:else if details}
    {#if details.translators.length}
      <div class="voice-head">
        <span class="section-label">Озвучка</span>
        <button class="link preview-toggle" onclick={openPreview} disabled={chosen === null}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z" /></svg>
          Превью
        </button>
      </div>
      <div class="chip-row">
        {#each details.translators as t (t.id)}
          <button class="chip" class:on={chosen === t.id} onclick={() => pickVoice(t.id)}>
            {t.name}
          </button>
        {/each}
      </div>
    {/if}

    {#if isSeries && multiSeason}
      <div class="seasons-head">
        <span class="section-label">Сезоны</span>
        <button class="link" onclick={toggleAll}>{allSelected ? 'Сбросить' : 'Выбрать все'}</button>
      </div>
      <div class="chip-row">
        {#each seasons as s (s.number)}
          <button
            class="chip season"
            class:on={selected.includes(s.number)}
            onclick={() => toggleSeason(s.number)}
          >
            {#if selected.includes(s.number)}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
            {/if}
            Сезон {s.number}<span class="eps">{s.episodes} эп.</span>
          </button>
        {/each}
      </div>
    {/if}

    <button
      class="cta"
      class:disabled={!ctaEnabled}
      disabled={!ctaEnabled || starting}
      onclick={start}
    >
      {#if starting}
        <Spinner size={18} />
      {:else}
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11" /><path d="M7 11l5 5 5-5" /><path d="M4.5 20h15" /></svg>
        {ctaLabel}
        <span class="shine"></span>
      {/if}
    </button>
  {/if}
</div>

{#if previewOpen && details}
  <div class="pv-backdrop" onclick={closePreview} role="presentation"></div>
  <div class="pv-modal">
    <div class="pv-head">
      <span class="pv-title">{details.name}</span>
      <button class="pv-close" onclick={closePreview} aria-label="Закрыть превью">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 5l14 14M19 5L5 19" /></svg>
      </button>
    </div>
    <div class="pv-player">
      <!-- svelte-ignore a11y_media_has_caption -->
      <video
        bind:this={videoEl}
        src={previewSrc}
        playsinline
        preload="metadata"
        onloadedmetadata={initPreviewWindow}
        ontimeupdate={onPvTime}
        onplay={() => (pvPlaying = true)}
        onpause={() => (pvPlaying = false)}
        onwaiting={() => (pvBuffering = true)}
        onplaying={() => (pvBuffering = false)}
        oncanplay={() => (pvBuffering = false)}
      ></video>
      <button class="pv-hit" onclick={togglePvPlay} aria-label="Плей / пауза">
        {#if !pvBuffering && !pvPlaying}
          <span class="pv-bigplay">
            {#if pvEnded}
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12a8 8 0 1 1-2.4-5.7" /><path d="M20 4v4.5h-4.5" /></svg>
            {:else}
              <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff"><path d="M8.5 5.8v12.4c0 .8.9 1.3 1.6.9l9.6-6.2c.6-.4.6-1.4 0-1.8L10.1 4.9c-.7-.4-1.6.1-1.6.9z" /></svg>
            {/if}
          </span>
        {/if}
      </button>
      {#if pvBuffering}
        <div class="pv-loading"><Spinner size={30} /></div>
      {/if}
      <div class="pv-bar">
        <span class="pv-time">{fmtTime(pvTime)}</span>
        <div
          class="pv-track"
          role="slider"
          tabindex="0"
          aria-label="Позиция фрагмента"
          aria-valuemin="0"
          aria-valuemax={Math.round(pvWindow)}
          aria-valuenow={Math.round(pvTime)}
          onpointerdown={seekPv}
          onkeydown={seekPvKey}
        >
          <div class="pv-rail"><div class="pv-fill" style="width:{(pvTime / pvWindow) * 100}%"></div></div>
        </div>
        <span class="pv-time">{fmtTime(pvWindow)}</span>
        <button class="pv-ctl" onclick={shuffleScene} aria-label="Другая сцена">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5" /><path d="M4 20L21 3" /><path d="M21 16v5h-5" /><path d="M15 15l6 6" /><path d="M4 4l5 5" /></svg>
        </button>
      </div>
    </div>
    <div class="pv-voices">
      {#each details.translators as t (t.id)}
        <button class="chip" class:on={chosen === t.id} onclick={() => previewVoice(t.id)}>
          {t.name}
        </button>
      {/each}
    </div>
    <div class="pv-hint">Момент сохраняется при переключении озвучки</div>
  </div>
{/if}

<style>
  .backdrop {
    position: absolute;
    inset: 0;
    z-index: 9;
    background: rgba(2, 3, 8, 0.5);
    backdrop-filter: blur(7px);
    -webkit-backdrop-filter: blur(7px);
    transition: opacity 0.45s;
  }
  .sheet {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10;
    border-radius: 32px 32px 0 0;
    padding: 10px 20px calc(24px + var(--safe-bottom));
    max-height: 90%;
    overflow-y: auto;
    background: rgba(18, 21, 32, 0.78);
    backdrop-filter: blur(44px) saturate(170%);
    -webkit-backdrop-filter: blur(44px) saturate(170%);
    border-top: 1px solid rgba(255, 255, 255, 0.14);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.12),
      0 -24px 70px rgba(0, 0, 0, 0.6);
    transition: transform 0.5s cubic-bezier(0.32, 0.72, 0, 1);
  }
  .grabber {
    margin: 0 auto 16px;
    width: 38px;
    height: 5px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.25);
    cursor: pointer;
  }
  .hero {
    display: flex;
    gap: 16px;
  }
  .poster {
    width: 96px;
    aspect-ratio: 2 / 3;
    border-radius: 14px;
    flex: none;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.18),
      0 12px 28px rgba(0, 0, 0, 0.45);
  }
  .hero-info {
    padding-top: 2px;
    min-width: 0;
  }
  .title {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.3px;
    line-height: 1.15;
  }
  .chips-meta {
    margin-top: 9px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip-meta {
    padding: 5px 11px;
    border-radius: 14px;
    font-size: 12px;
    font-weight: 500;
    color: rgba(235, 235, 245, 0.75);
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }
  .rates {
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .rate {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px 4px 7px;
    border-radius: 14px;
    font-size: 12.5px;
    font-weight: 650;
    letter-spacing: 0.01em;
    color: rgba(255, 255, 255, 0.92);
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }
  .rate .star {
    color: var(--rating);
    filter: drop-shadow(0 0 6px rgba(255, 214, 10, 0.45));
  }
  .rate-badge {
    font-style: normal;
    font-size: 9px;
    font-weight: 800;
    line-height: 1;
    letter-spacing: 0.02em;
    padding: 3px 5.5px;
    border-radius: 6px;
  }
  .rate-badge.imdb {
    background: #f5c518;
    color: #1a1200;
  }
  .rate-badge.kp {
    background: linear-gradient(135deg, #ff5500, #ff8a3d);
    color: #fff;
  }
  .subline {
    margin-top: 9px;
    font-size: 12px;
    line-height: 1.45;
    color: var(--text-3);
  }
  .section-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-3);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .chip-row {
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
  }
  .seasons-head {
    margin-top: 16px;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  .voice-head {
    margin-top: 16px;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  .preview-toggle {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .preview-toggle:disabled {
    opacity: 0.4;
  }
  .pv-backdrop {
    position: absolute;
    inset: 0;
    z-index: 19;
    background: rgba(2, 3, 8, 0.65);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    animation: pv-fade 0.3s ease;
  }
  .pv-modal {
    position: absolute;
    left: 14px;
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
    z-index: 20;
    border-radius: 22px;
    padding: 14px;
    background: rgba(18, 21, 32, 0.92);
    backdrop-filter: blur(44px) saturate(170%);
    -webkit-backdrop-filter: blur(44px) saturate(170%);
    border: 1px solid rgba(255, 255, 255, 0.14);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.12),
      0 24px 70px rgba(0, 0, 0, 0.6);
    animation: pv-pop 0.35s cubic-bezier(0.2, 0.9, 0.3, 1);
  }
  @keyframes pv-fade {
    from {
      opacity: 0;
    }
  }
  @keyframes pv-pop {
    from {
      opacity: 0;
      transform: translateY(-50%) scale(0.94);
    }
  }
  .pv-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 11px;
  }
  .pv-title {
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .pv-close {
    flex: none;
    width: 28px;
    height: 28px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: rgba(235, 235, 245, 0.75);
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    transition: transform 0.15s ease;
  }
  .pv-close:active {
    transform: scale(0.92);
  }
  .pv-player {
    position: relative;
    border-radius: 14px;
    overflow: hidden;
    background: #000;
    border: 1px solid rgba(255, 255, 255, 0.12);
  }
  .pv-player video {
    width: 100%;
    aspect-ratio: 16 / 9;
    display: block;
    background: #000;
  }
  .pv-hit {
    position: absolute;
    inset: 0 0 36px 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .pv-bigplay {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-left: 3px;
    background: rgba(18, 21, 32, 0.55);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.28);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.25),
      0 8px 24px rgba(0, 0, 0, 0.5);
    animation: pv-fade 0.2s ease;
  }
  .pv-loading {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.3);
    pointer-events: none;
  }
  .pv-bar {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 14px 12px 7px;
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.72));
  }
  .pv-time {
    flex: none;
    font-size: 11px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: rgba(255, 255, 255, 0.9);
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
  }
  .pv-track {
    flex: 1;
    padding: 8px 0;
    cursor: pointer;
    touch-action: none;
  }
  .pv-rail {
    height: 4px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.28);
    overflow: hidden;
  }
  .pv-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, #0a84ff, #5ac8fa);
    box-shadow: 0 0 8px rgba(10, 132, 255, 0.7);
  }
  .pv-ctl {
    flex: none;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0.9;
    transition: transform 0.15s ease;
  }
  .pv-ctl:active {
    transform: scale(0.86);
  }
  .pv-voices {
    margin-top: 12px;
    display: flex;
    gap: 7px;
    overflow-x: auto;
    padding-bottom: 2px;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }
  .pv-voices::-webkit-scrollbar {
    display: none;
  }
  .pv-voices .chip {
    flex: none;
    white-space: nowrap;
  }
  .pv-hint {
    margin-top: 8px;
    font-size: 11px;
    text-align: center;
    color: var(--text-3);
  }
  .link {
    font-size: 12px;
    font-weight: 500;
    color: var(--accent-light);
    transition: opacity 0.15s ease;
  }
  .link:active {
    opacity: 0.5;
  }
  .chip {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 15px;
    border-radius: 19px;
    font-size: 13px;
    font-weight: 500;
    color: rgba(235, 235, 245, 0.7);
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
    transition:
      transform 0.15s ease,
      background 0.25s,
      color 0.25s,
      box-shadow 0.25s;
  }
  .chip.season {
    padding: 8px 14px;
  }
  .chip:active {
    transform: scale(0.94);
  }
  .chip.on {
    font-weight: 600;
    color: #fff;
    background: linear-gradient(180deg, rgba(10, 132, 255, 0.85), rgba(10, 110, 230, 0.75));
    border-color: rgba(255, 255, 255, 0.25);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.35),
      0 6px 18px rgba(10, 132, 255, 0.35);
  }
  .eps {
    font-size: 11px;
    opacity: 0.7;
  }
  .cta {
    position: sticky;
    bottom: 0;
    z-index: 2;
    margin-top: 20px;
    width: 100%;
    height: 54px;
    border-radius: 27px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-size: 17px;
    font-weight: 600;
    color: #fff;
    overflow: hidden;
    background: linear-gradient(180deg, rgba(10, 132, 255, 0.95), rgba(0, 100, 220, 0.9));
    border: 1px solid rgba(255, 255, 255, 0.3);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.4),
      0 14px 34px rgba(10, 132, 255, 0.4);
    transition:
      transform 0.18s cubic-bezier(0.2, 0.8, 0.2, 1),
      opacity 0.25s;
  }
  .cta:active {
    transform: scale(0.97);
  }
  .cta.disabled {
    opacity: 0.45;
  }
  .shine {
    position: absolute;
    top: 0;
    bottom: 0;
    left: -60px;
    width: 60px;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
    background-size: 200% 100%;
    animation: shimmer 3.5s linear infinite;
    pointer-events: none;
  }
  .center {
    display: flex;
    justify-content: center;
    padding: 32px;
  }
  .error {
    margin-top: 18px;
    color: var(--danger);
    font-size: 14px;
  }
  .ghost {
    margin-top: 10px;
    color: var(--accent);
    font-weight: 600;
  }
</style>
