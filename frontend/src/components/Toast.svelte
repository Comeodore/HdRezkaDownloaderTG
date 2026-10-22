<script lang="ts">
  import { app } from '../lib/state.svelte';
  import Icon from './Icon.svelte';
</script>

{#if app.toast}
  {#key app.toast.id}
    <div class="toast {app.toast.tone}" role="status" aria-live="polite">
      {#if app.toast.tone === 'success'}
        <span class="mark ok"><Icon name="check" size={15} stroke={2.6} /></span>
      {:else if app.toast.tone === 'error'}
        <span class="mark err"><Icon name="alert" size={15} stroke={2.2} /></span>
      {/if}
      <span class="text">{app.toast.message}</span>
    </div>
  {/key}
{/if}

<style>
  .toast {
    position: absolute;
    left: 50%;
    bottom: calc(96px + var(--safe-bottom));
    z-index: 60;
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: calc(100% - 32px);
    padding: 11px 16px;
    border-radius: 16px;
    font-size: 14px;
    font-weight: 500;
    background: rgba(44, 44, 52, 0.94);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--line-strong);
    box-shadow: 0 14px 36px rgba(0, 0, 0, 0.55);
    transform: translateX(-50%);
    animation: toast-in 0.35s var(--ease-spring);
    pointer-events: none;
  }
  .text {
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
  }
  .mark {
    flex: none;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #0b0b0e;
  }
  .ok {
    background: var(--success);
  }
  .err {
    background: var(--danger);
  }
  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translate(-50%, 12px) scale(0.96);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }
</style>
