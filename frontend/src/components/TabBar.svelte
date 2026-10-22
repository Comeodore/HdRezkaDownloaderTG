<script lang="ts">
  import { app, type Tab } from '../lib/state.svelte';
  import Icon, { type IconName } from './Icon.svelte';

  const tabs: { id: Tab; label: string; icon: IconName }[] = [
    { id: 'search', label: 'Поиск', icon: 'search' },
    { id: 'downloads', label: 'Загрузки', icon: 'download' },
    { id: 'library', label: 'Медиатека', icon: 'library' },
  ];

  const index = $derived(tabs.findIndex((tab) => tab.id === app.tab));
</script>

<nav class="tabbar" aria-label="Разделы">
  <div class="track">
    <span class="pill" style:transform="translateX({index * 100}%)"></span>
    {#each tabs as tab (tab.id)}
      <button
        class="tab"
        class:active={app.tab === tab.id}
        aria-current={app.tab === tab.id ? 'page' : undefined}
        onclick={() => app.selectTab(tab.id)}
      >
        <span class="glyph">
          <Icon name={tab.icon} size={22} stroke={app.tab === tab.id ? 2.2 : 1.9} />
          {#if tab.id === 'downloads' && app.activeJobs > 0}
            <span class="badge">{app.activeJobs}</span>
          {/if}
        </span>
        <span class="label">{tab.label}</span>
      </button>
    {/each}
  </div>
</nav>

<style>
  .tabbar {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 20;
    display: flex;
    justify-content: center;
    padding: 0 16px calc(12px + var(--safe-bottom));
    pointer-events: none;
    background: linear-gradient(to top, var(--bg) 35%, transparent);
  }
  .track {
    position: relative;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    width: min(100%, 320px);
    padding: 5px;
    border-radius: 999px;
    pointer-events: auto;
    background: rgba(30, 30, 37, 0.72);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid var(--line-strong);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
  }
  .pill {
    position: absolute;
    top: 5px;
    bottom: 5px;
    left: 5px;
    width: calc((100% - 10px) / 3);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.12);
    transition: transform 0.4s var(--ease-spring);
  }
  .tab {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 7px 0 6px;
    border-radius: 999px;
    color: var(--text-3);
    transition: color 0.25s ease;
  }
  .tab.active {
    color: var(--text);
  }
  .glyph {
    position: relative;
    display: flex;
  }
  .label {
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.1px;
  }
  .badge {
    position: absolute;
    top: -4px;
    left: 15px;
    min-width: 17px;
    height: 17px;
    padding: 0 5px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    color: var(--on-primary);
    background: var(--primary);
    box-shadow: 0 0 0 2px rgba(30, 30, 37, 0.9);
  }
</style>
