<template>
  <div class="auth-page">
    <!-- 品牌：固定在页面最左上角 -->
    <div class="auth-brand">
      <img src="../assets/logo.png" alt="Aries Cloud" class="auth-brand-logo" />
      <span class="auth-brand-name">Aries Cloud</span>
    </div>

    <div class="auth-layout">
      <!-- ============ 左侧：产品介绍（渐变背景，无方框） ============ -->
      <aside class="intro-panel">
        <!-- 标语 -->
        <div class="intro-hero">
          <h1 class="intro-hero-title">{{ heroTitle }}</h1>
          <p class="intro-hero-sub">{{ heroSub }}</p>
        </div>

        <!-- 功能列表：图标+标题同一行，描述在下，无方框 -->
        <div class="intro-features">
          <div v-for="f in features" :key="f.title" class="feature-item">
            <div class="feature-head">
              <span class="feature-icon" v-html="f.icon" />
              <h3 class="feature-title">{{ f.title }}</h3>
            </div>
            <p class="feature-desc">{{ f.desc }}</p>
          </div>
        </div>

        <!-- 底部 CTA 句 -->
        <p class="intro-foot">
          订阅基础套餐及以上，即可获得 7×24 全天候在线的专属智能助手，开箱即用。
        </p>
      </aside>

      <!-- ============ 右侧：登录/注册表单（独立白色卡片，固定高度） ============ -->
      <section class="form-panel">
        <header class="form-header">
          <h2 class="form-title">{{ title }}</h2>
          <p v-if="subtitle" class="form-sub">{{ subtitle }}</p>
        </header>

        <!-- 表单插槽 -->
        <div class="form-body">
          <slot />
        </div>

        <!-- 底部：服务条款 + 版权 -->
        <footer class="form-footer">
          <p class="footer-terms">
            继续即表示您已阅读并同意
            <a href="#" class="ds-link">服务条款</a>
            和
            <a href="#" class="ds-link">隐私政策</a>
          </p>
          <p class="footer-copy">
            © {{ year }} Aries Cloud. 版权所有。
          </p>
        </footer>
      </section>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  heroTitle: { type: String, default: '7×24 在线的智能 Agent' },
  heroSub: { type: String, default: '文件读写、命令执行、定时任务、知识库与外部连接，一站托管你的数字工作' }
})

const year = new Date().getFullYear()

const features = [
  {
    title: '智能 Agent',
    desc: '自主读写文件、执行 Bash 命令、按计划运行任务，7×24 小时不间断工作。',
    icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="6" width="16" height="13" rx="2"/><path d="M12 2v4M8 14l2 2 4-4"/><circle cx="12" cy="2.5" r="0.6" fill="currentColor"/></svg>`
  },
  {
    title: '知识库',
    desc: '集中管理文档与资料，Agent 按需检索引用，让回答有据可依。',
    icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4v16a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V8l-4-4H5a1 1 0 0 0-1 4z"/><path d="M8 13h8M8 17h6"/></svg>`
  },
  {
    title: '外部连接',
    desc: '打通微信、QQ、飞书等外部平台，消息与事件实时同步，协作更顺畅。',
    icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.5 6h7M6 8.5v7M18 8.5v7M8.5 18h7"/></svg>`
  },
  {
    title: '灵活套餐',
    desc: '提供免费、基础、专业多档套餐，用量可视化，按需选择容量与成本。',
    icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l5-5 4 4 8-8"/><path d="M14 8h6v6"/></svg>`
  }
]
</script>

<style scoped>
/* ============ 页面背景：渐变铺满全屏 ============ */
/* 顶部对齐：左侧位置不受右侧高度变化影响，完全独立 */
.auth-page {
  min-height: 100vh;
  width: 100%;
  position: relative;
  background:
    radial-gradient(1200px 800px at 12% 18%, rgba(22, 100, 255, 0.12), transparent 60%),
    radial-gradient(1000px 700px at 88% 82%, rgba(56, 123, 255, 0.12), transparent 60%),
    linear-gradient(135deg, #EBF1FF 0%, #F6F8FA 50%, #EBF1FF 100%);
  padding: 96px var(--spacer-48) var(--spacer-48);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ============ 品牌：固定页面最左上角 ============ */
.auth-brand {
  position: fixed;
  top: 28px;
  left: 40px;
  display: flex;
  align-items: center;
  gap: var(--spacer-10);
  z-index: 10;
}
.auth-brand-logo {
  width: 30px;
  height: 30px;
  object-fit: contain;
}
.auth-brand-name {
  font-family: var(--font-family-heading);
  font-size: 17px;
  font-weight: 600;
  color: var(--text-default);
  letter-spacing: -0.01em;
}

/* ============ 双栏布局 ============ */
.auth-layout {
  width: 100%;
  max-width: 1040px;
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: var(--spacer-40);
  align-items: start;
}

/* ============ 左侧：介绍面板（渐变背景，无方框，字号放大） ============ */
.intro-panel {
  padding: var(--spacer-40) var(--spacer-40);
  border-radius: var(--radius-20);
  background:
    radial-gradient(600px 400px at 0% 0%, rgba(22, 100, 255, 0.08), transparent 70%),
    linear-gradient(160deg, #EBF1FF 0%, #F6F8FA 45%, #FFFFFF 100%);
  border: 1px solid var(--border-neutral-l1);
  display: flex;
  flex-direction: column;
}

.intro-hero {
  margin-bottom: var(--spacer-32);
}
.intro-hero-title {
  font-family: var(--font-family-heading);
  font-size: 32px;
  font-weight: 600;
  line-height: 42px;
  color: var(--text-default);
  letter-spacing: -0.01em;
}
.intro-hero-sub {
  margin-top: var(--spacer-12);
  font-size: 16px;
  line-height: 26px;
  color: var(--text-secondary);
}

/* 功能列表：纯文字，无方框，图标+标题同一行 */
.intro-features {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacer-28) var(--spacer-24);
}
.feature-head {
  display: flex;
  align-items: center;
  gap: var(--spacer-10);
}
.feature-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--icon-brand);
  flex-shrink: 0;
}
.feature-title {
  font-size: 17px;
  font-weight: var(--font-weight-strong);
  color: var(--text-default);
  line-height: 26px;
}
.feature-desc {
  margin-top: var(--spacer-6);
  font-size: 14px;
  line-height: 22px;
  color: var(--text-tertiary);
  padding-left: 30px; /* 与标题文字对齐（图标宽20 + gap10） */
}

.intro-foot {
  margin-top: var(--spacer-28);
  font-size: 14px;
  line-height: 22px;
  color: var(--text-tertiary);
}

/* ============ 右侧：表单面板（独立白色卡片，自适应高度） ============ */
/* 不设固定 min-height：登录/注册各自按内容撑开，避免与左侧高度产生关联 */
.form-panel {
  width: 100%;
  padding: var(--spacer-32) var(--spacer-32);
  border-radius: var(--radius-20);
  background-color: var(--bg-base-default);
  border: 1px solid var(--border-neutral-l1);
  box-shadow: 0 8px 32px rgba(22, 100, 255, 0.06), 0 1px 4px rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.form-header {
  margin-bottom: var(--spacer-20);
}
.form-title {
  font-family: var(--font-family-heading);
  font-size: 18px;
  font-weight: 600;
  line-height: 26px;
  color: var(--text-default);
}
.form-sub {
  margin-top: var(--spacer-4);
  font-size: 13px;
  line-height: 20px;
  color: var(--text-tertiary);
}

/* 表单主体 */
.form-body {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.form-footer {
  margin-top: var(--spacer-20);
  padding-top: var(--spacer-12);
  border-top: 1px solid var(--border-neutral-l1);
}
.footer-terms {
  font-size: 12px;
  line-height: 18px;
  color: var(--text-tertiary);
}
.footer-copy {
  margin-top: var(--spacer-4);
  font-size: 12px;
  line-height: 18px;
  color: var(--text-disabled);
}

/* ============ 响应式 ============ */
/* 平板：缩小内边距，保持左右布局 */
@media (max-width: 1024px) {
  .auth-page {
    padding: 88px var(--spacer-24) var(--spacer-24);
  }
  .auth-brand {
    top: 24px;
    left: 24px;
  }
  .intro-panel,
  .form-panel {
    padding: var(--spacer-32) var(--spacer-28);
  }
  .intro-hero {
    margin-bottom: var(--spacer-28);
  }
  .intro-hero-title {
    font-size: 28px;
    line-height: 36px;
  }
  .intro-hero-sub {
    font-size: 15px;
    line-height: 24px;
  }
  .intro-features {
    gap: var(--spacer-24) var(--spacer-20);
  }
  .feature-title {
    font-size: 16px;
    line-height: 24px;
  }
  .feature-desc {
    font-size: 13px;
    line-height: 20px;
  }
  .intro-foot {
    margin-top: var(--spacer-24);
    font-size: 13px;
    line-height: 20px;
  }
  .form-panel {
    padding: var(--spacer-24) var(--spacer-24);
  }
  .form-title {
    font-size: 17px;
    line-height: 24px;
  }
  .form-sub {
    font-size: 12px;
    line-height: 18px;
  }
}

/* 手机：单列堆叠 */
@media (max-width: 640px) {
  .auth-page {
    padding: 72px var(--spacer-16) var(--spacer-16);
    align-items: flex-start;
  }
  .auth-brand {
    top: 18px;
    left: 16px;
  }
  .auth-brand-logo {
    width: 26px;
    height: 26px;
  }
  .auth-brand-name {
    font-size: 15px;
  }
  .auth-layout {
    grid-template-columns: 1fr;
    max-width: 440px;
    gap: var(--spacer-16);
  }
  .intro-panel {
    padding: var(--spacer-24) var(--spacer-20);
  }
  .intro-hero {
    margin-bottom: var(--spacer-20);
  }
  .intro-hero-title {
    font-size: 22px;
    line-height: 30px;
  }
  .intro-hero-sub {
    font-size: 14px;
    line-height: 22px;
  }
  .intro-features {
    grid-template-columns: 1fr;
    gap: var(--spacer-16);
  }
  .intro-foot {
    margin-top: var(--spacer-20);
  }
  .form-panel {
    padding: var(--spacer-24) var(--spacer-20);
    min-height: auto;
  }
}
</style>
