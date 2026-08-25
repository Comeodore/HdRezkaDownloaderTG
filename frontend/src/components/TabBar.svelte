<script lang="ts">
  import { badgeCount, jobs, tab, type Tab } from '../lib/stores';
  import { haptic } from '../lib/telegram';

  type Item = { id: Tab; label: string };
  const items: Item[] = [
    { id: 'search', label: 'Поиск' },
    { id: 'downloads', label: 'Загрузки' },
    { id: 'library', label: 'Медиатека' },
  ];

  const activeIndex = $derived(items.findIndex((it) => it.id === $tab));
  const badge = $derived(badgeCount($jobs));

  function select(id: Tab): void {
    if (id === $tab) return;
    haptic.impact('light');
    tab.set(id);
  }
</script>

<nav class="tabbar">
  <div class="pill" style="transform:translateX({activeIndex * 90}px)"></div>
  {#each items as it (it.id)}
    <button
      class="tab"
      class:active={$tab === it.id}
      onclick={() => select(it.id)}
      aria-label={it.label}
    >
      <span class="glyph">
        {#if it.id === 'search'}
          <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
        {:else if it.id === 'downloads'}
          <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11" /><path d="M7 11l5 5 5-5" /><path d="M4.5 20h15" /></svg>
        {:else}
          <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4.5h3.5v15H5z" /><path d="M11 4.5h3.5v15H11z" /><path d="M17.5 6l3 13.4" /></svg>
        {/if}
        {#if it.id === 'downloads' && badge > 0}
          <span class="badge">{badge}</span>
        {/if}
      </span>
      <span class="label">{it.label}</span>
    </button>
  {/each}
</nav>

<style>
  .tabbar {
    position: absolute;
    left: 50%;
    bottom: calc(22px + var(--safe-bottom));
    transform: translateX(-50%);
    z-index: 5;
    display: flex;
    gap: 2px;
    padding: 5px;
    border-radius: 34px;
    background: rgba(22, 24, 34, 0.55);
    backdrop-filter: blur(34px) saturate(170%);
    -webkit-backdrop-filter: blur(34px) saturate(170%);
    border: 1px solid rgba(255, 255, 255, 0.11);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.13),
      0 16px 44px rgba(0, 0, 0, 0.55);
  }
  .pill {
    position: absolute;
    top: 5px;
    left: 5px;
    width: 88px;
    height: calc(100% - 10px);
    border-radius: 28px;
    background: rgba(255, 255, 255, 0.13);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.2),
      0 3px 12px rgba(0, 0, 0, 0.35);
    transition: transform 0.45s cubic-bezier(0.3, 1.4, 0.4, 1);
  }
  .tab {
    position: relative;
    width: 88px;
    padding: 9px 0 7px;
    border-radius: 28px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    color: var(--text-2);
    transition:
      color 0.3s ease,
      transform 0.15s ease;
  }
  .tab.active {
    color: #fff;
  }
  .tab:active {
    transform: scale(0.94);
  }
  .glyph {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .label {
    font-size: 10px;
    font-weight: 600;
  }
  .badge {
    position: absolute;
    top: -5px;
    right: -12px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: 9px;
    background: var(--accent);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 10px rgba(10, 132, 255, 0.6);
    animation: cardIn 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
</style>
