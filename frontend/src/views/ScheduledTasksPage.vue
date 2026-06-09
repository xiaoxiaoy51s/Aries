<template>
  <div class="scheduled-tasks-page">
    <div class="page-header">
      <h2>定时任务</h2>
    </div>
    <div class="page-body">
      <p class="placeholder-text">定时任务功能（待恢复完整代码）</p>
    </div>
  </div>
</template>

<style scoped>
.scheduled-tasks-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px 24px;
}

.page-header h2 {
  font-size: 18px;
  font-weight: 600;
}

.page-body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-text {
  color: var(--text-muted);
  font-size: 14px;
}
</style>
