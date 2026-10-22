<script lang="ts">
  let { size = 22, tone = 'light' }: { size?: number; tone?: 'light' | 'dark' } = $props();
</script>

<span class="spinner {tone}" style:width="{size}px" style:height="{size}px" role="progressbar" aria-label="Загрузка"></span>

<style>
  .spinner {
    display: inline-block;
    flex: none;
    border-radius: 50%;
    border: 2px solid rgba(255, 255, 255, 0.14);
    border-top-color: var(--text);
    animation: spin 0.75s linear infinite;
  }
  .dark {
    border-color: rgba(0, 0, 0, 0.15);
    border-top-color: var(--on-primary);
  }
</style>
