<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './components/Icon.svelte';
  import Spinner from './components/Spinner.svelte';
  import TabBar from './components/TabBar.svelte';
  import Toast from './components/Toast.svelte';
  import { app } from './lib/state.svelte';
  import DownloadsView from './views/DownloadsView.svelte';
  import LibraryView from './views/LibraryView.svelte';
  import SearchView from './views/SearchView.svelte';
  import TitlePage from './views/TitlePage.svelte';

  onMount(() => {
    let stop = () => {};
    app.boot().then((unsubscribe) => (stop = unsubscribe));
    return () => stop();
  });

  // each title page knows whether a preview sits on top of it
  const pages = $derived(
    app.stack
      .map((route, index) => ({ route, index, preview: app.stack[index + 1]?.kind === 'preview' }))
      .filter((page) => page.route.kind === 'title'),
  );
</script>

<div class="stage">
  {#if app.booting}
    <div class="center"><Spinner size={28} /></div>
  {:else if app.fatal}
    <div class="gate">
      <div class="gate-icon">
        <Icon name={app.fatal === 'forbidden' ? 'lock' : 'alert'} size={30} stroke={1.7} />
      </div>
      {#if app.fatal === 'outside'}
        <h1>Откройте в Telegram</h1>
        <p>Приложение работает только внутри Telegram — через кнопку в чате с ботом.</p>
      {:else if app.fatal === 'forbidden'}
        <h1>Доступ закрыт</h1>
        <p>Ваш аккаунт не в списке разрешённых. Попросите владельца сервера добавить вас.</p>
      {:else}
        <h1>Не удалось запуститься</h1>
        <p>{app.fatal}</p>
        <button class="chip on" onclick={() => location.reload()}>
          <Icon name="retry" size={15} /> Перезапустить
        </button>
      {/if}
    </div>
  {:else}
    <main class="tabs" class:hidden={pages.length > 0} aria-hidden={pages.length > 0}>
      {#if app.tab === 'search'}
        <SearchView />
      {:else if app.tab === 'downloads'}
        <DownloadsView />
      {:else}
        <LibraryView />
      {/if}
    </main>
    <TabBar />
    {#each pages as page (page.index)}
      {#if page.route.kind === 'title'}
        <TitlePage ref={page.route.ref} previewOpen={page.preview} />
      {/if}
    {/each}
  {/if}
  <Toast />
</div>

<style>
  .stage {
    position: fixed;
    inset: 0;
    overflow: hidden;
    background: var(--bg);
  }
  .tabs {
    position: absolute;
    inset: 0;
  }
  /* keep the tab mounted (scroll position survives) but out of the way */
  .tabs.hidden {
    visibility: hidden;
  }
  .center {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .gate {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 32px;
    text-align: center;
  }
  .gate-icon {
    display: flex;
    padding: 18px;
    border-radius: 24px;
    color: var(--text-2);
    background: var(--surface);
    border: 1px solid var(--line);
  }
  .gate h1 {
    margin: 8px 0 0;
    font-size: 21px;
    font-weight: 700;
  }
  .gate p {
    margin: 0 0 10px;
    max-width: 290px;
    color: var(--text-3);
    line-height: 1.45;
  }
</style>
