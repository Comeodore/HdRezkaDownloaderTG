<script lang="ts">
  let { size = 22 }: { size?: number } = $props();
</script>

<span class="spinner" style="width:{size}px;height:{size}px"></span>

<style>
  .spinner {
    display: inline-block;
    border: 2px solid rgba(255, 255, 255, 0.14);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
</style>
