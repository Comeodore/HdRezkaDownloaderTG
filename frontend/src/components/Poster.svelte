<script lang="ts">
  import Icon from './Icon.svelte';

  let {
    src = null,
    alt = '',
    kind = 'movie',
    eager = false,
  }: { src?: string | null; alt?: string; kind?: string; eager?: boolean } = $props();

  // keyed by src so a recycled component never shows a stale load state
  let loadedSrc = $state<string | null>(null);
  let failedSrc = $state<string | null>(null);
  const loaded = $derived(Boolean(src) && loadedSrc === src);
  const failed = $derived(Boolean(src) && failedSrc === src);
</script>

<div class="poster" class:ready={loaded}>
  {#if src && !failed}
    <img
      {src}
      {alt}
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
      draggable="false"
      onload={() => (loadedSrc = src)}
      onerror={() => (failedSrc = src)}
    />
  {/if}
  {#if !src || failed}
    <div class="fallback">
      <Icon name={kind === 'movie' ? 'film' : 'tv'} size={26} stroke={1.6} />
    </div>
  {/if}
</div>

<style>
  .poster {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: var(--surface-2);
  }
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0;
    transition: opacity 0.35s ease;
  }
  .ready img {
    opacity: 1;
  }
  .fallback {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-4);
    background: linear-gradient(160deg, var(--surface-3), var(--surface));
  }
</style>
