<template>
  <div class="conn-lost-overlay">
    <div class="conn-lost-card">
      <div class="conn-lost-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
          <path d="M12 8v4"/>
          <path d="M12 16h.01"/>
        </svg>
      </div>
      <h2 class="conn-lost-title">与后端的连接已断开</h2>
      <p class="conn-lost-desc">
        应用可能因长时间运行或系统休眠后无响应。<br />
        正在运行的任务可能受到影响，建议重启应用以恢复。
      </p>
      <div class="conn-lost-actions">
        <button type="button" class="conn-btn conn-btn--primary" @click="$emit('restart')">
          重启应用
        </button>
        <button type="button" class="conn-btn conn-btn--secondary" @click="$emit('retry')">
          重试连接
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineEmits<{
  restart: []
  retry: []
}>()
</script>

<style scoped>
.conn-lost-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 17, 21, 0.45);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.conn-lost-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px 48px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  max-width: 420px;
  text-align: center;
}

.conn-lost-icon {
  color: #b45309;
}

.conn-lost-title {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a18;
  margin: 0;
}

.conn-lost-desc {
  font-size: 14px;
  line-height: 1.6;
  color: #5c6672;
  margin: 0;
}

.conn-lost-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.conn-btn {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}

.conn-btn--primary {
  background: #1a1a18;
  color: #fff;
}

.conn-btn--primary:hover {
  background: #333330;
}

.conn-btn--secondary {
  background: #f5f7fb;
  color: #1a1a18;
  border: 1px solid #e3e8f0;
}

.conn-btn--secondary:hover {
  background: #eef2f8;
}
</style>
