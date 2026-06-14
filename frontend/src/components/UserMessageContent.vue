<template>
  <div class="user-message-content">
    <p>{{ content }}</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  content: string
  slashCommand?: string
  slashBody?: string
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
