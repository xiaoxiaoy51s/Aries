<template>
  <div class="user-message-content">
    <p>{{ text }}</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  text: string
  images?: string[]
}>()
</script>

<style scoped>
.user-message-content p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
