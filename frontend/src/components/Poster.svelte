<script lang="ts">
  import { imageUrl } from '../lib/api';
  import { token } from '../lib/stores';

  let { src = null, alt = '', kind = 'unknown' }: { src?: string | null; alt?: string; kind?: string } = $props();
  let failed = $state(false);

  const icons: Record<string, string> = { movie: '🎬', series: '📺', cartoon: '🧸', anime: '🌸' };
  const resolved = $derived(src && $token ? imageUrl(src, $token) : '');
</script>

{#if resolved && !failed}
  <img class="poster" src={resolved} {alt} loading="lazy" onerror={() => (failed = true)} />
{:else}
  <div class="poster placeholder"><span>{icons[kind] ?? '🎬'}</span></div>
{/if}

<style>
  .poster {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 30px;
    background: linear-gradient(160deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02));
    opacity: 0.85;
  }
</style>
