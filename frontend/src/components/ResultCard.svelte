<script lang="ts">
  import { kindLabel } from '../lib/format';
  import type { SearchItem } from '../lib/types';
  import Poster from './Poster.svelte';

  let {
    item,
    index = 0,
    onopen,
  }: { item: SearchItem; index?: number; onopen: (item: SearchItem) => void } = $props();

  const sub = $derived([kindLabel(item.kind), item.year].filter(Boolean).join(' · '));
</script>

<button class="card" style="animation-delay:{Math.min(index, 8) * 50}ms" onclick={() => onopen(item)}>
  <div class="poster">
    <Poster src={item.poster} alt={item.title} kind={item.kind} />
  </div>
  <div class="meta">
    <div class="title">{item.title}</div>
    {#if sub}<div class="sub">{sub}</div>{/if}
  </div>
</button>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    text-align: left;
    animation: cardIn 0.4s cubic-bezier(0.2, 0.8, 0.2, 1) both;
    transition: transform 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .card:active {
    transform: scale(0.95);
  }
  .poster {
    position: relative;
    aspect-ratio: 2 / 3;
    width: 100%;
    border-radius: 16px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.18),
      0 10px 24px rgba(0, 0, 0, 0.4);
  }
  .title {
    font-size: 13px;
    font-weight: 600;
    line-height: 1.25;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .sub {
    margin-top: 2px;
    font-size: 11px;
    color: var(--text-2);
  }
</style>
