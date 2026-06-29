<template>
  <div class="boot-splash" role="status" aria-live="polite" aria-label="加载中">
    <img class="boot-logo" src="/logo.png" alt="Aries" width="64" height="64" />
    <template v-if="error">
      <p class="boot-text boot-text--error">{{ error }}</p>
      <button type="button" class="boot-retry" @click="$emit('retry')">重试</button>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  error: string | null
}>()

defineEmits<{
  retry: []
}>()
</script>

<style scoped>
.boot-splash {
  position: fixed;
  inset: 0;
  z-index: 900;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #ffffff;
  user-select: none;
}

.boot-logo {
  width: 64px;
  height: 64px;
  object-fit: contain;
}

.boot-text--error {
  font-size: 14px;
  color: #b45309;
  text-align: center;
  max-width: 320px;
  line-height: 1.5;
}

.boot-retry {
  padding: 8px 20px;
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  background: #fff;
  color: #1a1a18;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.boot-retry:hover {
  background: #f5f7fb;
}
</style>
