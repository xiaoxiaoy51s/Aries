<template>
  <span class="session-loading-dots" aria-label="处理中">
    <span></span>
    <span></span>
    <span></span>
  </span>
</template>

<style scoped>
.session-loading-dots {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  margin-right: 6px;
}

.session-loading-dots span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent, #6366f1);
  animation: session-dot-bounce 1.4s infinite ease-in-out both;
}

.session-loading-dots span:nth-child(1) {
  animation-delay: -0.32s;
}

.session-loading-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes session-dot-bounce {
  0%, 80%, 100% {
    transform: scale(0.4);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
