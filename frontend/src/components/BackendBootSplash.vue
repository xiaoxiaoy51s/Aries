<template>
  <div class="boot-splash" role="status" aria-live="polite" aria-label="加载中">
    <div class="boot-wave" aria-hidden="true">
      <div class="boot-wave__blob boot-wave__blob--1" />
      <div class="boot-wave__blob boot-wave__blob--2" />
      <div class="boot-wave__blob boot-wave__blob--3" />
      <div class="boot-wave__shimmer" />
    </div>

    <div class="boot-content">
      <img class="boot-logo" src="/logo.png" alt="Aries" width="64" height="64" />
      <template v-if="error">
        <p class="boot-text boot-text--error">{{ error }}</p>
        <button type="button" class="boot-retry" @click="$emit('retry')">重试</button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  error?: string | null
}>(), {
  error: null,
})

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
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background-color: var(--boot-bg-color);
  background-image: var(--boot-bg-image);
  user-select: none;
}

.boot-wave {
  position: absolute;
  inset: -20%;
  overflow: hidden;
  pointer-events: none;
}

.boot-wave__blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(72px);
  will-change: transform;
}

.boot-wave__blob--1 {
  width: 52%;
  height: 52%;
  left: 8%;
  top: 10%;
  background: rgba(157, 192, 223, 0.55);
  animation: boot-wave-drift-1 14s ease-in-out infinite;
}

.boot-wave__blob--2 {
  width: 48%;
  height: 48%;
  right: 6%;
  bottom: 8%;
  background: rgba(209, 220, 231, 0.72);
  animation: boot-wave-drift-2 11s ease-in-out infinite;
}

.boot-wave__blob--3 {
  width: 38%;
  height: 38%;
  left: 34%;
  top: 42%;
  background: rgba(186, 210, 235, 0.45);
  animation: boot-wave-drift-3 9s ease-in-out infinite;
}

.boot-wave__shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    108deg,
    transparent 38%,
    rgba(255, 255, 255, 0.28) 50%,
    transparent 62%
  );
  background-size: 220% 100%;
  animation: boot-wave-shimmer 3.2s ease-in-out infinite;
}

.boot-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.boot-logo {
  width: 64px;
  height: 64px;
  object-fit: contain;
  animation: boot-logo-breathe 2.4s ease-in-out infinite;
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
  border: 1px solid var(--glass-border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.55);
  color: var(--text);
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
  backdrop-filter: var(--glass-blur-light);
  -webkit-backdrop-filter: var(--glass-blur-light);
}

.boot-retry:hover {
  background: var(--accent-hover);
}

@keyframes boot-wave-drift-1 {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(6%, 8%) scale(1.08);
  }
  66% {
    transform: translate(-4%, 5%) scale(0.96);
  }
}

@keyframes boot-wave-drift-2 {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  40% {
    transform: translate(-7%, -6%) scale(1.06);
  }
  70% {
    transform: translate(5%, -3%) scale(0.94);
  }
}

@keyframes boot-wave-drift-3 {
  0%, 100% {
    transform: translate(0, 0) scale(1);
    opacity: 0.75;
  }
  50% {
    transform: translate(-6%, 7%) scale(1.12);
    opacity: 1;
  }
}

@keyframes boot-wave-shimmer {
  0% {
    background-position: 180% 0;
    opacity: 0;
  }
  20% {
    opacity: 0.55;
  }
  50% {
    background-position: -80% 0;
    opacity: 0.35;
  }
  100% {
    background-position: -180% 0;
    opacity: 0;
  }
}

@keyframes boot-logo-breathe {
  0%, 100% {
    transform: scale(1);
    opacity: 0.88;
  }
  50% {
    transform: scale(1.04);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .boot-wave__blob,
  .boot-wave__shimmer,
  .boot-logo {
    animation: none;
  }
}
</style>
