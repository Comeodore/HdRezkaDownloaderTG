<script lang="ts">
  import { onMount } from 'svelte';
  import { fly } from 'svelte/transition';
  import Icon from '../components/Icon.svelte';
  import Poster from '../components/Poster.svelte';
  import Spinner from '../components/Spinner.svelte';
  import { api, ApiError } from '../lib/api';
  import { episodesWord, formatDuration, formatSize, kindLabel, plural, seasonsWord } from '../lib/format';
  import { app, errorText } from '../lib/state.svelte';
  import { haptic, hasNativeBack } from '../lib/telegram';
  import type { QualityOption, SeasonInfo, TitleDetails, TitleRef } from '../lib/types';
  import PreviewPlayer from './PreviewPlayer.svelte';

  let { ref, previewOpen }: { ref: TitleRef; previewOpen: boolean } = $props();

  const VOICES_COLLAPSED = 8;
  const HEIGHTS = [1080, 720, 480, 360];

  let details = $state<TitleDetails | null>(null);
  let loading = $state(true);
  let error = $state('');

  let chosen = $state<string | null>(null);
  let allVoices = $state(false);
  let expanded = $state(false);

  let seasons = $state<SeasonInfo[]>([]);
  let seasonsLoading = $state(false);
  let selected = $state<number[]>([]);

  let qualities = $state<QualityOption[] | null>(null);
  let qualitiesLoading = $state(false);
  let premiumOnly = $state<string | null>(null);
  let maxHeight = $state(1080);

  let starting = $state(false);
  let voiceRequest = 0;

  const isSeries = $derived(details?.is_series ?? ref.kind === 'series');
  const voices = $derived(details?.translators ?? []);
  const visibleVoices = $derived(
    allVoices || voices.length <= VOICES_COLLAPSED + 2 ? voices : voices.slice(0, VOICES_COLLAPSED),
  );
  const voice = $derived(voices.find((t) => t.key === chosen) ?? null);

  const meta = $derived(
    [
      kindLabel(details?.kind ?? ref.kind),
      details?.year ?? ref.year,
      formatDuration(details?.duration ?? null),
      details?.age,
    ]
      .filter(Boolean)
      .join(' · '),
  );
  const facts = $derived([details?.genres.slice(0, 3).join(', '), details?.country].filter(Boolean).join(' · '));

  const option = (height: number) => qualities?.find((q) => q.height === height) ?? null;
  const effective = $derived(
    qualities?.find((q) => q.height <= maxHeight) ?? (qualities?.length ? qualities[qualities.length - 1] : null),
  );

  const pendingEpisodes = $derived(
    seasons
      .filter((s) => selected.includes(s.number))
      .reduce((sum, s) => sum + Math.max(0, s.episodes - s.local), 0),
  );
  const estimate = $derived(
    effective ? (isSeries ? effective.size * pendingEpisodes : details?.local.exists ? 0 : effective.size) : 0,
  );
  const lacksSpace = $derived(Boolean(details?.disk_free && estimate && estimate > details.disk_free));

  const ready = $derived(Boolean(details && voice && !voice.premium && !premiumOnly));
  const nothingToDo = $derived(
    isSeries ? seasons.length > 0 && selected.length > 0 && pendingEpisodes === 0 : Boolean(details?.local.exists),
  );
  const ctaDisabled = $derived(
    !ready || starting || nothingToDo || lacksSpace || (isSeries && (seasonsLoading || !selected.length)),
  );
  const ctaLabel = $derived.by(() => {
    if (!details) return 'Скачать';
    if (nothingToDo) return isSeries ? 'Всё уже скачано' : 'Уже в медиатеке';
    if (isSeries) {
      if (seasonsLoading) return 'Загружаю сезоны…';
      if (!selected.length) return 'Выберите сезоны';
      return `Скачать ${episodesWord(pendingEpisodes)}`;
    }
    return details.kind === 'movie' ? 'Скачать фильм' : 'Скачать';
  });

  onMount(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  });

  async function load(signal?: AbortSignal): Promise<void> {
    loading = true;
    error = '';
    try {
      const data = await api.title(ref.url, signal);
      details = data;
      const fallback = data.translators.find((t) => !t.premium) ?? data.translators[0];
      const preferred = data.translators.find((t) => t.key === data.default_translator && !t.premium);
      chosen = (preferred ?? fallback)?.key ?? null;
      loadVoice();
    } catch (e) {
      if (!signal?.aborted) error = errorText(e);
    } finally {
      if (!signal?.aborted) loading = false;
    }
  }

  async function loadVoice(): Promise<void> {
    if (!details || !chosen) return;
    const request = ++voiceRequest;
    const key = chosen;
    qualities = null;
    premiumOnly = null;
    qualitiesLoading = true;
    if (details.is_series) {
      seasonsLoading = true;
      api
        .episodes(details.url, key)
        .then((list) => {
          if (request !== voiceRequest) return;
          const keep = selected.filter((n) => list.some((s) => s.number === n));
          seasons = list;
          selected = keep.length ? keep : defaultSeasons(list);
        })
        .catch((e) => request === voiceRequest && app.fail(e))
        .finally(() => request === voiceRequest && (seasonsLoading = false));
    }
    try {
      const { items: list, premium_only } = await api.qualities(details.url, key);
      if (request !== voiceRequest) return;
      qualities = list;
      premiumOnly = premium_only;
      if (list.length && !list.some((q) => q.height <= maxHeight)) maxHeight = list[list.length - 1].height;
    } catch {
      if (request === voiceRequest) qualities = [];
    } finally {
      if (request === voiceRequest) qualitiesLoading = false;
    }
  }

  /** Continue where the library left off: the first season that isn't fully downloaded. */
  function defaultSeasons(list: SeasonInfo[]): number[] {
    if (list.length <= 1) return list.map((s) => s.number);
    const next = list.find((s) => s.local < s.episodes);
    return next ? [next.number] : [];
  }

  function pickVoice(key: string): void {
    if (key === chosen) return;
    haptic.select();
    chosen = key;
    loadVoice();
  }

  function toggleSeason(number: number): void {
    haptic.select();
    selected = selected.includes(number)
      ? selected.filter((n) => n !== number)
      : [...selected, number].sort((a, b) => a - b);
  }

  function toggleAllSeasons(): void {
    haptic.select();
    selected = selected.length === seasons.length ? [] : seasons.map((s) => s.number);
  }

  function pickHeight(height: number): void {
    haptic.select();
    maxHeight = height;
  }

  function openPreview(): void {
    haptic.tap();
    app.push({ kind: 'preview' });
  }

  async function start(): Promise<void> {
    if (ctaDisabled || !details || !chosen) return;
    starting = true;
    haptic.press();
    try {
      const job = await api.createDownload({
        url: details.url,
        translator: chosen,
        seasons: isSeries ? selected : [],
        max_height: maxHeight,
      });
      app.upsertJob(job);
      haptic.success();
      app.notify('Добавлено в загрузки', 'success');
      app.selectTab('downloads');
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        haptic.warning();
        app.notify('Этот тайтл уже качается', 'info');
        app.selectTab('downloads');
      } else {
        app.fail(e);
      }
    } finally {
      starting = false;
    }
  }

  const seasonState = (s: SeasonInfo) =>
    s.local >= s.episodes ? 'скачан' : s.local > 0 ? `есть ${s.local} из ${s.episodes}` : episodesWord(s.episodes);
</script>

<div class="page" transition:fly={{ x: 48, duration: 320, opacity: 0 }}>
  <div class="scroller">
    <div class="backdrop" aria-hidden="true">
      {#if details?.poster_hq || ref.poster}
        <img src={details?.poster_hq ?? ref.poster} alt="" />
      {/if}
    </div>

    {#if !hasNativeBack()}
      <button class="back icon-button" onclick={() => app.back()} aria-label="Назад">
        <Icon name="back" size={20} />
      </button>
    {/if}

    <header class="hero">
      <div class="cover">
        <Poster src={details?.poster ?? ref.poster ?? null} alt={ref.title} kind={ref.kind} eager />
      </div>
      <h1>{details?.name ?? ref.title}</h1>
      {#if details?.orig_name}<div class="orig">{details.orig_name}</div>{/if}
      {#if meta}<div class="meta">{meta}</div>{/if}

      {#if details && (details.rating || details.rating_imdb || details.rating_kp)}
        <div class="ratings">
          {#if details.rating}
            <span class="rating"><span class="star"><Icon name="star" size={13} /></span>{details.rating.toFixed(1)}</span>
          {/if}
          {#if details.rating_imdb}
            <span class="rating"><b class="imdb">IMDb</b>{details.rating_imdb.toFixed(1)}</span>
          {/if}
          {#if details.rating_kp}
            <span class="rating"><b class="kp">КП</b>{details.rating_kp.toFixed(1)}</span>
          {/if}
        </div>
      {/if}

      {#if details?.local.exists}
        <div class="owned"><Icon name="check" size={14} stroke={2.6} />
          {isSeries ? 'Часть сериала уже в медиатеке' : 'Уже в медиатеке'}
        </div>
      {/if}
    </header>

    {#if loading}
      <div class="body">
        <div class="skeleton bar w90"></div>
        <div class="skeleton bar w75"></div>
        <div class="skeleton bar w60"></div>
        <div class="skeleton chips"></div>
      </div>
    {:else if error}
      <div class="body failed">
        <p>{error}</p>
        <button class="chip" onclick={() => load()}><Icon name="retry" size={15} /> Повторить</button>
      </div>
    {:else if details}
      <div class="body">
        {#if details.description}
          <button class="description" class:expanded onclick={() => (expanded = !expanded)}>
            {details.description}
          </button>
        {/if}
        {#if facts}<div class="facts">{facts}</div>{/if}
        {#if details.status}<div class="facts">{details.status}</div>{/if}

        {#if voices.length}
          <section>
            <div class="section-head">
              <span class="section-label">Озвучка</span>
              <button class="preview-link" onclick={openPreview} disabled={!ready}>
                <Icon name="play" size={12} /> Превью
              </button>
            </div>
            <div class="chips">
              {#each visibleVoices as t (t.key)}
                <button
                  class="chip"
                  class:on={chosen === t.key}
                  disabled={t.premium}
                  onclick={() => pickVoice(t.key)}
                  title={t.premium ? 'Только для премиум-аккаунта HDRezka' : undefined}
                >
                  {#if t.premium}<Icon name="lock" size={13} />{/if}
                  {t.name}
                </button>
              {/each}
              {#if visibleVoices.length < voices.length}
                <button class="chip more" onclick={() => (allVoices = true)}>
                  Ещё {voices.length - visibleVoices.length}
                </button>
              {/if}
            </div>
          </section>
        {/if}

        {#if isSeries}
          <section>
            <div class="section-head">
              <span class="section-label">
                {seasons.length ? seasonsWord(seasons.length) : 'Сезоны'}
              </span>
              {#if seasons.length > 1}
                <button class="text-button small" onclick={toggleAllSeasons}>
                  {selected.length === seasons.length ? 'Снять все' : 'Выбрать все'}
                </button>
              {/if}
            </div>
            {#if seasonsLoading && !seasons.length}
              <div class="seasons">
                {#each Array(3) as _, i (i)}<div class="season skeleton"></div>{/each}
              </div>
            {:else}
              <div class="seasons" class:dim={seasonsLoading}>
                {#each seasons as s (s.number)}
                  <button
                    class="season"
                    class:on={selected.includes(s.number)}
                    class:complete={s.local >= s.episodes}
                    onclick={() => toggleSeason(s.number)}
                  >
                    <span class="season-name">Сезон {s.number}</span>
                    <span class="season-sub">
                      {#if s.local >= s.episodes}<Icon name="check" size={12} stroke={2.6} />{/if}
                      {seasonState(s)}
                    </span>
                  </button>
                {/each}
              </div>
            {/if}
          </section>
        {/if}

        <section>
          <div class="section-head">
            <span class="section-label">Качество</span>
            {#if isSeries && effective}<span class="hint">≈ {formatSize(effective.size)} за серию</span>{/if}
          </div>
          <div class="qualities" role="radiogroup" aria-label="Качество">
            {#each HEIGHTS as height (height)}
              {@const q = option(height)}
              <button
                class="quality"
                class:on={effective?.height === height || (!qualities?.length && maxHeight === height)}
                role="radio"
                aria-checked={maxHeight === height}
                disabled={qualities !== null && qualities.length > 0 && !q}
                onclick={() => pickHeight(height)}
              >
                <span class="q-label">{height}p</span>
                <span class="q-size">
                  {#if qualitiesLoading}
                    <span class="skeleton q-skel"></span>
                  {:else if q}
                    {formatSize(q.size)}
                  {:else if qualities?.length}
                    нет
                  {:else}
                    —
                  {/if}
                </span>
              </button>
            {/each}
          </div>
        </section>

        {#if details.parts.length}
          <section>
            <div class="section-head"><span class="section-label">Другие части</span></div>
            <ul class="parts">
              {#each details.parts as part (part.url)}
                <li>
                  <button
                    class="part"
                    class:current={part.current}
                    disabled={part.current}
                    onclick={() => app.openTitle({ url: part.url, title: part.title, year: part.year })}
                  >
                    <span class="part-title">{part.title}</span>
                    <span class="part-meta">
                      {#if part.year}{part.year}{/if}
                      {#if part.rating}<span class="part-rating">КП {part.rating.toFixed(1)}</span>{/if}
                      {#if part.current}<span class="part-here">эта</span>{:else}<Icon name="chevron" size={14} />{/if}
                    </span>
                  </button>
                </li>
              {/each}
            </ul>
          </section>
        {/if}
      </div>
    {/if}
  </div>

  {#if details && !error}
    <footer class="cta-bar">
      {#if lacksSpace}
        <div class="warning">
          Не хватит места: нужно ≈ {formatSize(estimate)}, свободно {formatSize(details.disk_free ?? 0)}
        </div>
      {:else if voice?.premium}
        <div class="warning">Эта озвучка доступна только с премиум-аккаунтом</div>
      {:else if premiumOnly}
        <div class="warning">{premiumOnly}</div>
      {/if}
      <button class="cta pressable" disabled={ctaDisabled} onclick={start}>
        {#if starting}
          <Spinner size={18} tone="dark" />
        {:else}
          {#if !nothingToDo}<Icon name="download" size={19} stroke={2.2} />{/if}
          <span>{ctaLabel}</span>
          {#if estimate && !nothingToDo && !(isSeries && !selected.length)}
            <span class="cta-size">{isSeries ? '≈ ' : ''}{formatSize(estimate)}</span>
          {/if}
        {/if}
      </button>
    </footer>
  {/if}

  {#if previewOpen && details && chosen}
    <PreviewPlayer title={details.name} url={details.url} voices={voices.filter((t) => !t.premium)} bind:chosen
      onvoice={() => loadVoice()} />
  {/if}
</div>

<style>
  .page {
    position: absolute;
    inset: 0;
    z-index: 30;
    background: var(--bg);
  }
  .scroller {
    position: absolute;
    inset: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding-bottom: calc(120px + var(--safe-bottom));
  }
  .backdrop {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 460px;
    overflow: hidden;
    pointer-events: none;
  }
  .backdrop img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    filter: blur(36px) saturate(140%);
    transform: scale(1.25);
    opacity: 0.55;
  }
  .backdrop::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(to bottom, rgba(11, 11, 14, 0.15) 0%, rgba(11, 11, 14, 0.55) 55%, var(--bg) 100%);
  }
  .back {
    position: absolute;
    top: calc(12px + var(--safe-top));
    left: 14px;
    z-index: 2;
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
  }

  .hero {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: calc(28px + var(--safe-top)) 24px 0;
  }
  .cover {
    width: 136px;
    aspect-ratio: 2 / 3;
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid var(--line-strong);
    box-shadow: 0 22px 50px rgba(0, 0, 0, 0.6);
  }
  h1 {
    margin: 18px 0 0;
    font-size: 26px;
    font-weight: 750;
    letter-spacing: -0.5px;
    line-height: 1.15;
  }
  .orig {
    margin-top: 4px;
    font-size: 14px;
    color: var(--text-3);
  }
  .meta {
    margin-top: 8px;
    font-size: 14px;
    color: var(--text-2);
  }
  .ratings {
    margin-top: 12px;
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
  }
  .rating {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 10px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 650;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid var(--line);
  }
  .star {
    display: flex;
    color: var(--rating);
  }
  .rating b {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.2px;
  }
  .imdb {
    color: var(--imdb);
  }
  .kp {
    color: var(--kp);
  }
  .owned {
    margin-top: 12px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 600;
    color: var(--success);
    background: rgba(52, 199, 89, 0.12);
  }

  .body {
    position: relative;
    padding: 18px 16px 0;
    animation: fade-up 0.35s var(--ease-out);
  }
  .body.failed {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding-top: 40px;
    text-align: center;
    color: var(--text-2);
  }
  .body.failed p {
    margin: 0;
  }
  .bar {
    height: 13px;
    border-radius: 5px;
    margin-bottom: 9px;
  }
  .w90 {
    width: 90%;
  }
  .w75 {
    width: 75%;
  }
  .w60 {
    width: 60%;
  }
  .skeleton.chips {
    height: 80px;
    margin-top: 24px;
    border-radius: var(--radius-m);
  }

  .description {
    display: -webkit-box;
    -webkit-line-clamp: 4;
    line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
    width: 100%;
    text-align: left;
    font-size: 15px;
    line-height: 1.5;
    color: var(--text-2);
  }
  .description.expanded {
    -webkit-line-clamp: unset;
    line-clamp: unset;
  }
  .facts {
    margin-top: 10px;
    font-size: 13px;
    color: var(--text-3);
  }

  section {
    margin-top: 26px;
  }
  .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 32px;
    margin-bottom: 8px;
  }
  .hint {
    font-size: 13px;
    color: var(--text-3);
  }
  .preview-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 12px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 650;
    color: var(--text);
    background: var(--surface-3);
  }
  .preview-link:disabled {
    opacity: 0.4;
  }
  .preview-link:active:not(:disabled) {
    transform: scale(0.95);
  }
  .text-button.small {
    font-size: 14px;
    padding: 4px 0;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .chip.more {
    color: var(--text);
    background: transparent;
    border-style: dashed;
  }

  .seasons {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
    gap: 8px;
    transition: opacity 0.2s ease;
  }
  .seasons.dim {
    opacity: 0.5;
  }
  .season {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 3px;
    min-height: 60px;
    padding: 10px 12px;
    border-radius: var(--radius-m);
    text-align: left;
    background: var(--surface);
    border: 1px solid var(--line);
    transition:
      background 0.2s ease,
      border-color 0.2s ease,
      transform 0.18s var(--ease-out);
  }
  .season:active {
    transform: scale(0.96);
  }
  .season.on {
    background: var(--surface-3);
    border-color: var(--text-2);
  }
  .season-name {
    font-size: 15px;
    font-weight: 650;
  }
  .season-sub {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--text-3);
  }
  .season.complete .season-sub {
    color: var(--success);
  }

  .qualities {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    padding: 4px;
    border-radius: var(--radius-m);
    background: var(--surface);
    border: 1px solid var(--line);
  }
  .quality {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 0;
    border-radius: 10px;
    transition: background 0.2s ease;
  }
  .quality.on {
    background: var(--surface-3);
  }
  .quality:disabled {
    opacity: 0.35;
  }
  .q-label {
    font-size: 15px;
    font-weight: 650;
  }
  .q-size {
    min-height: 16px;
    font-size: 12px;
    color: var(--text-3);
  }
  .q-skel {
    display: block;
    width: 44px;
    height: 10px;
    margin-top: 3px;
    border-radius: 4px;
  }

  .parts {
    list-style: none;
    margin: 0;
    padding: 0;
    border-radius: var(--radius-m);
    background: var(--surface);
    border: 1px solid var(--line);
    overflow: hidden;
  }
  .parts li + li {
    border-top: 1px solid var(--line);
  }
  .part {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px;
    text-align: left;
  }
  .part:active:not(:disabled) {
    background: var(--surface-2);
  }
  .part-title {
    min-width: 0;
    font-size: 15px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .part.current .part-title {
    font-weight: 650;
  }
  .part-meta {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-3);
  }
  .part-rating {
    color: var(--text-2);
  }
  .part-here {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-2);
  }

  .cta-bar {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 3;
    padding: 28px 16px calc(14px + var(--safe-bottom));
    background: linear-gradient(to top, var(--bg) 60%, transparent);
  }
  .warning {
    margin-bottom: 10px;
    text-align: center;
    font-size: 13px;
    color: var(--warning);
  }
  .cta {
    width: 100%;
    height: 54px;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    font-size: 17px;
    font-weight: 700;
    color: var(--on-primary);
    background: var(--primary);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  }
  .cta:disabled {
    color: var(--text-3);
    background: var(--surface-2);
    box-shadow: none;
  }
  .cta-size {
    font-weight: 600;
    opacity: 0.55;
  }
</style>
