<script lang="ts">
  import { formatSize, seasonsWord } from '../lib/format';
  import { haptic } from '../lib/telegram';
  import type { LibraryItem } from '../lib/types';

  let { item, ondelete }: { item: LibraryItem; ondelete: (id: string) => void } = $props();

  let confirming = $state(false);
  let confirmTimer: ReturnType<typeof setTimeout> | undefined;

  const isSeries = $derived(item.kind === 'series');
  const meta = $derived(
    isSeries
      ? `${seasonsWord(item.seasons ?? 0)} · ${item.episodes ?? 0} эп. · ${formatSize(item.size)}`
      : formatSize(item.size),
  );

  function tapDelete(): void {
    if (!confirming) {
      haptic.impact('light');
      confirming = true;
      confirmTimer = setTimeout(() => (confirming = false), 3500);
      return;
    }
    clearTimeout(confirmTimer);
    confirming = false;
    ondelete(item.id);
  }
</script>

<div class="card">
  <div class="badge">
    {#if isSeries}
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="rgba(235,235,245,.8)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="8" width="18" height="12" rx="2.5" /><path d="M8 3.5L12 8l4-4.5" /></svg>
    {:else}
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="rgba(235,235,245,.8)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="8" width="18" height="12" rx="2.5" /><path d="M3.5 8l2-3.2 4 1.1-2 3.2" /><path d="M9.5 5.9l4 1.1-2 3.2-4-1.1" /><path d="M13.5 7l4 1.1-2 3.1" /></svg>
    {/if}
  </div>
  <div class="content">
    <div class="name">{item.name}</div>
    <div class="meta">{meta}</div>
  </div>
  <button class="del" class:confirm={confirming} onclick={tapDelete} aria-label="Удалить">
    {#if confirming}
      <span class="del-label">Удалить?</span>
    {:else}
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#FF453A" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16" /><path d="M9 7V4.8c0-.4.4-.8.8-.8h4.4c.4 0 .8.4.8.8V7" /><path d="M6.5 7l1 13h9l1-13" /><path d="M10 11v5.5" /><path d="M14 11v5.5" /></svg>
    {/if}
  </button>
</div>

<style>
  .card {
    display: flex;
    align-items: center;
    gap: 13px;
    margin-top: 10px;
    padding: 13px 14px;
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(28px) saturate(160%);
    -webkit-backdrop-filter: blur(28px) saturate(160%);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.12),
      0 10px 28px rgba(0, 0, 0, 0.35);
  }
  .badge {
    width: 42px;
    height: 42px;
    border-radius: 13px;
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.14);
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
  .meta {
    margin-top: 3px;
    font-size: 12px;
    color: var(--text-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .del {
    flex: none;
    min-width: 36px;
    height: 36px;
    border-radius: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 69, 58, 0.1);
    border: 1px solid rgba(255, 69, 58, 0.22);
    transition:
      transform 0.15s ease,
      background 0.2s;
  }
  .del:active {
    transform: scale(0.9);
  }
  .del.confirm {
    padding: 0 13px;
    background: linear-gradient(180deg, rgba(255, 69, 58, 0.95), rgba(220, 40, 30, 0.9));
    border-color: rgba(255, 255, 255, 0.3);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.3),
      0 6px 16px rgba(255, 69, 58, 0.4);
    animation: cardIn 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .del-label {
    font-size: 12.5px;
    font-weight: 600;
    color: #fff;
    white-space: nowrap;
  }
</style>
