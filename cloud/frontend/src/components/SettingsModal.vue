<template>
  <div class="settings-screen" @click.self="handleClose">
    <div class="settings-modal">
    <!-- 头部 -->
    <header class="settings-head">
      <h2 id="settings-title" class="settings-title">{{ t('settings.title') }}</h2>
      <button type="button" class="settings-close" :title="t('settings.cancel')" @click="handleClose">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </header>

    <!-- 左侧竖 tab + 右侧内容 -->
    <div class="settings-layout">
      <aside class="settings-sidebar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="settings-tab"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span class="settings-tab-icon" v-html="tab.icon" />
          <span class="settings-tab-label">{{ tab.label }}</span>
        </button>
      </aside>

      <!-- 内容区 -->
      <div class="settings-body">
        <!-- 个人信息 -->
        <section v-if="activeTab === 'profile'" class="settings-section">
          <div class="settings-section-head">
            <div class="settings-section-meta">
              <div class="settings-section-title">{{ t('settings.profile') }}</div>
              <div class="settings-section-desc">{{ t('settings.profileDesc') }}</div>
            </div>
          </div>

          <div class="settings-card">
            <div class="settings-card-body">
              <div class="settings-profile-card">
                <div class="settings-profile-avatar">
                  {{ (auth.user?.username || 'U').charAt(0).toUpperCase() }}
                </div>
                <div class="settings-profile-meta">
                  <div class="settings-profile-name">{{ auth.user?.username || 'User' }}</div>
                  <div class="settings-profile-email">{{ auth.user?.email || '' }}</div>
                  <span class="settings-profile-badge">{{ membershipText(auth.user?.membership_level) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="settings-card">
            <div class="settings-card-body">
              <div class="settings-profile-details">
                <div class="settings-profile-detail-item">
                  <span class="settings-profile-detail-label">{{ t('settings.profileUsername') }}</span>
                  <span class="settings-profile-detail-value">{{ auth.user?.username || '-' }}</span>
                </div>
                <div class="settings-profile-detail-item">
                  <span class="settings-profile-detail-label">{{ t('settings.profileEmail') }}</span>
                  <span class="settings-profile-detail-value">{{ auth.user?.email || '-' }}</span>
                </div>
                <div class="settings-profile-detail-item">
                  <span class="settings-profile-detail-label">{{ t('settings.profileMembership') }}</span>
                  <span class="settings-profile-detail-value">{{ membershipText(auth.user?.membership_level) }}</span>
                </div>
                <div class="settings-profile-detail-item">
                  <span class="settings-profile-detail-label">{{ t('settings.profileJoinTime') }}</span>
                  <span class="settings-profile-detail-value">{{ formattedJoinTime }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="settings-profile-actions">
            <button type="button" class="settings-logout-btn" @click="handleLogout">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              {{ t('settings.profileLogout') }}
            </button>
          </div>
        </section>

        <!-- 模型管理 -->
        <section v-if="activeTab === 'models'" class="settings-section">
          <div class="settings-section-head">
            <div class="settings-section-meta">
              <div class="settings-section-title">{{ t('settings.models') }}</div>
              <div class="settings-section-desc">{{ t('settings.noModels') }}</div>
            </div>
            <button type="button" class="ds-btn ds-btn-primary" @click="openAddForm">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 5v14M5 12h14"/>
              </svg>
              {{ t('settings.addModel') }}
            </button>
          </div>

          <!-- 模型类型子标签：对话 / OCR / ASR -->
          <div class="settings-subtabs">
            <button
              v-for="mt in modelTypes"
              :key="mt.key"
              type="button"
              class="settings-subtab"
              :class="{ active: modelTypeTab === mt.key }"
              @click="modelTypeTab = mt.key"
            >
              {{ mt.label }}
            </button>
          </div>

          <div class="settings-card">
            <div v-if="models.length === 0" class="settings-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
              <p>{{ t('settings.noModels') }}</p>
            </div>

            <div v-else class="settings-model-list">
              <div v-for="m in models" :key="m.id" class="settings-model-card">
                <div class="settings-model-info">
                  <div class="settings-model-name">
                    {{ m.name }}
                    <span v-if="m.isActive" class="settings-tag settings-tag-success">{{ t('settings.active') }}</span>
                  </div>
                  <div class="settings-model-meta">
                    <span class="settings-model-id">{{ m.model }}</span>
                    <span class="settings-model-sep">·</span>
                    <span class="settings-model-url">{{ m.baseUrl }}</span>
                  </div>
                </div>
                <div class="settings-model-actions">
                  <label class="settings-switch" :title="t('settings.active')">
                    <input type="checkbox" :checked="m.isActive" @change="(e) => toggleActive(m, e.target.checked)" />
                    <span class="settings-switch-thumb" />
                  </label>
                  <button type="button" class="ds-btn ds-btn-secondary" @click="openEditForm(m)">{{ t('settings.editModel') }}</button>
                  <button type="button" class="settings-icon-btn settings-icon-btn-danger" :title="t('settings.delete')" @click="handleDelete(m)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                      <path d="M10 11v6M14 11v6"/>
                      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 通用设置 -->
        <section v-if="activeTab === 'general'" class="settings-section">
          <div class="settings-section-head">
            <div class="settings-section-meta">
              <div class="settings-section-title">{{ t('settings.general') }}</div>
            </div>
          </div>
          <div class="settings-card">
            <div class="settings-card-body">
              <div class="settings-form">
                <div class="settings-field settings-field-inline">
                  <label class="settings-field-label">{{ t('settings.language') }}</label>
                  <div class="settings-radio-group">
                    <label class="settings-radio">
                      <input type="radio" value="zh" :checked="settingsStore.language === 'zh'" @change="settingsStore.setLanguage('zh')" />
                      <span class="settings-radio-dot" />
                      <span>中文</span>
                    </label>
                    <label class="settings-radio">
                      <input type="radio" value="en" :checked="settingsStore.language === 'en'" @change="settingsStore.setLanguage('en')" />
                      <span class="settings-radio-dot" />
                      <span>English</span>
                    </label>
                  </div>
                </div>

                <div class="settings-field settings-field-inline">
                  <label class="settings-field-label">{{ t('settings.theme') }}</label>
                  <div class="settings-radio-group">
                    <label class="settings-radio">
                      <input type="radio" value="light" :checked="settingsStore.theme === 'light'" @change="settingsStore.setTheme('light')" />
                      <span class="settings-radio-dot" />
                      <span>{{ t('settings.themeLight') }}</span>
                    </label>
                    <label class="settings-radio">
                      <input type="radio" value="dark" :checked="settingsStore.theme === 'dark'" @change="settingsStore.setTheme('dark')" />
                      <span class="settings-radio-dot" />
                      <span>{{ t('settings.themeDark') }}</span>
                    </label>
                    <label class="settings-radio">
                      <input type="radio" value="system" :checked="settingsStore.theme === 'system'" @change="settingsStore.setTheme('system')" />
                      <span class="settings-radio-dot" />
                      <span>{{ t('settings.themeSystem') }}</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 记忆与规则 -->
        <section v-if="activeTab === 'memory'" class="settings-section">
          <div class="settings-section-head">
            <div class="settings-section-meta">
              <div class="settings-section-title">{{ t('settings.memory') }}</div>
              <div class="settings-section-desc">{{ t('settings.memoryDesc') }}</div>
            </div>
          </div>

          <!-- 子标签切换 -->
          <div class="settings-subtabs">
            <button type="button" class="settings-subtab" :class="{ active: memoryTab === 'global' }" @click="switchMemoryTab('global')">
              {{ t('settings.memoryGlobal') }}
            </button>
            <button type="button" class="settings-subtab" :class="{ active: memoryTab === 'project' }" @click="switchMemoryTab('project')">
              {{ t('settings.memoryProject') }}
            </button>
          </div>

          <!-- 全局记忆 -->
          <div v-if="memoryTab === 'global'" class="settings-card">
            <div class="settings-card-body">
              <p class="settings-memory-desc">{{ t('settings.memoryGlobalDesc') }}</p>
              <textarea
                v-model="globalMemory"
                class="ds-input settings-memory-editor"
                :placeholder="t('settings.memoryPlaceholder')"
                :disabled="memoryLoading"
              ></textarea>
              <div class="settings-memory-foot">
                <span class="settings-memory-hint">{{ globalMemory.length }} / 32000</span>
                <button type="button" class="ds-btn ds-btn-primary" :disabled="memoryLoading || memorySaving" @click="saveGlobal">
                  {{ memorySaving ? t('settings.memorySaving') : t('settings.save') }}
                </button>
              </div>
            </div>
          </div>

          <!-- 项目记忆 -->
          <div v-if="memoryTab === 'project'" class="settings-card">
            <div class="settings-card-body">
              <p class="settings-memory-desc">{{ t('settings.memoryProjectDesc') }}</p>
              <div class="settings-field">
                <label class="settings-field-label">{{ t('settings.memorySelectWorkspace') }}</label>
                <select v-model="selectedWorkspace" class="ds-input" :disabled="memoryLoading" @change="loadProjectMemory">
                  <option value="" disabled>{{ t('settings.memorySelectWorkspacePlaceholder') }}</option>
                  <option v-for="p in projectMemories" :key="p.workspace" :value="p.workspace">
                    {{ p.workspace }}{{ p.has_memory ? ` · ${t('settings.memoryHasContent')}` : '' }}
                  </option>
                </select>
              </div>
              <textarea
                v-model="projectMemory"
                class="ds-input settings-memory-editor"
                :placeholder="selectedWorkspace ? t('settings.memoryPlaceholder') : t('settings.memorySelectWorkspacePlaceholder')"
                :disabled="memoryLoading || !selectedWorkspace"
              ></textarea>
              <div class="settings-memory-foot">
                <span class="settings-memory-hint">{{ projectMemory.length }} / 32000</span>
                <button type="button" class="ds-btn ds-btn-primary" :disabled="memoryLoading || memorySaving || !selectedWorkspace" @click="saveProject">
                  {{ memorySaving ? t('settings.memorySaving') : t('settings.save') }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- 关于我们 -->
        <section v-if="activeTab === 'about'" class="settings-section">
          <div class="settings-section-head">
            <div class="settings-section-meta">
              <div class="settings-section-title">{{ t('settings.about') }}</div>
              <div class="settings-section-desc">{{ t('settings.aboutDesc') }}</div>
            </div>
          </div>
          <div class="settings-card">
            <div class="settings-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="16" x2="12" y2="12"/>
                <line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
              <p>{{ t('settings.aboutDesc') }}</p>
            </div>
          </div>
        </section>

        <!-- 消息平台 -->
        <section v-if="activeTab === 'bots'" class="settings-section">
          <div class="settings-section-head">
            <div class="settings-section-meta">
              <div class="settings-section-title">消息平台</div>
              <div class="settings-section-desc">绑定 QQ / 飞书 / 微信，让 AI 通过即时通讯平台与用户对话</div>
            </div>
          </div>

          <div class="settings-card">
            <!-- 平台 Tab -->
            <div class="bot-tabs" role="tablist">
              <button
                v-for="tab in botTabs"
                :key="tab.key"
                type="button"
                class="bot-tab"
                :class="{ active: botTab === tab.key }"
                role="tab"
                :aria-selected="botTab === tab.key"
                @click="botTab = tab.key"
              >
                <span class="bot-tab-icon">
                  <img :src="tab.icon" :alt="tab.label" />
                </span>
                <span class="bot-tab-label">{{ tab.label }}</span>
                <span
                  v-if="botStatus[tab.key]?.bound && botStatus[tab.key]?.enabled"
                  class="bot-tab-dot dot-success"
                  title="已启用"
                ></span>
                <span
                  v-else-if="botStatus[tab.key]?.bound"
                  class="bot-tab-dot dot-warning"
                  title="已绑定·未启用"
                ></span>
              </button>
            </div>

            <div class="bot-tab-content">
              <!-- QQ -->
              <div v-if="botTab === 'qq'" class="bot-platform-card">
                <div class="bot-platform-header">
                  <div class="bot-platform-info">
                    <div class="bot-platform-icon-big">
                      <img :src="qqIcon" alt="QQ" />
                    </div>
                    <div>
                      <div class="bot-platform-name">QQ 机器人</div>
                      <div class="bot-platform-status">
                        <span v-if="botStatus.qq?.bound && botStatus.qq?.enabled" class="settings-tag settings-tag-success">已启用</span>
                        <span v-else-if="botStatus.qq?.bound" class="settings-tag settings-tag-warning">已绑定·未启用</span>
                        <span v-else class="settings-tag settings-tag-muted">未配置</span>
                      </div>
                    </div>
                  </div>
                  <label v-if="botStatus.qq?.bound" class="settings-switch" title="启用/禁用">
                    <input type="checkbox" :checked="botStatus.qq?.enabled" @change="toggleBot('qq', $event.target.checked)" />
                    <span class="settings-switch-thumb" />
                  </label>
                </div>

                <div class="bot-platform-form" v-if="!botStatus.qq?.bound || botEdit.qq">
                  <a href="https://q.qq.com/qqbot/openclaw/" target="_blank" rel="noopener" class="bot-help-link">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                    前往 QQ 开放平台注册机器人
                  </a>
                  <div class="settings-field">
                    <label class="settings-field-label">App ID</label>
                    <input v-model="botForms.qq.app_id" type="text" class="ds-input" placeholder="请输入 QQ 机器人 App ID" />
                  </div>
                  <div class="settings-field">
                    <label class="settings-field-label">App Secret</label>
                    <input v-model="botForms.qq.app_secret" type="password" class="ds-input" placeholder="请输入 App Secret" autocomplete="off" />
                  </div>
                  <div class="bot-form-actions">
                    <button v-if="botStatus.qq?.bound" type="button" class="ds-btn ds-btn-secondary" @click="botEdit.qq = false">取消</button>
                    <button type="button" class="ds-btn ds-btn-danger-ghost" v-if="botStatus.qq?.bound" @click="unbindBot('qq')">解绑</button>
                    <button type="button" class="ds-btn ds-btn-primary" :disabled="botSaving" @click="saveQQ">
                      {{ botSaving ? '保存中...' : '保存并启用' }}
                    </button>
                  </div>
                </div>

                <div class="bot-platform-actions" v-else>
                  <button type="button" class="ds-btn ds-btn-secondary" @click="botEdit.qq = true">修改配置</button>
                  <button type="button" class="ds-btn ds-btn-danger-ghost" @click="unbindBot('qq')">解绑</button>
                </div>
              </div>

              <!-- 飞书 -->
              <div v-if="botTab === 'feishu'" class="bot-platform-card">
                <div class="bot-platform-header">
                  <div class="bot-platform-info">
                    <div class="bot-platform-icon-big">
                      <img :src="feishuIcon" alt="飞书" />
                    </div>
                    <div>
                      <div class="bot-platform-name">飞书机器人</div>
                      <div class="bot-platform-status">
                        <span v-if="botStatus.feishu?.bound && botStatus.feishu?.enabled" class="settings-tag settings-tag-success">已启用</span>
                        <span v-else-if="botStatus.feishu?.bound" class="settings-tag settings-tag-warning">已绑定·未启用</span>
                        <span v-else class="settings-tag settings-tag-muted">未配置</span>
                      </div>
                    </div>
                  </div>
                  <label v-if="botStatus.feishu?.bound" class="settings-switch" title="启用/禁用">
                    <input type="checkbox" :checked="botStatus.feishu?.enabled" @change="toggleBot('feishu', $event.target.checked)" />
                    <span class="settings-switch-thumb" />
                  </label>
                </div>

                <!-- 扫码区域 -->
                <div class="bot-qrcode-area" v-if="!botStatus.feishu?.bound">
                  <template v-if="feishuQRImg">
                    <img :src="feishuQRImg" alt="飞书二维码" class="bot-qrcode-img" />
                    <p class="bot-qrcode-tip">{{ feishuPollStatus === 'confirmed' ? '授权成功' : '请使用飞书 App 扫码授权' }}</p>
                  </template>
                  <template v-else>
                    <button type="button" class="ds-btn ds-btn-primary" :disabled="botSaving" @click="startFeishuQR">
                      {{ botSaving ? '获取中...' : '获取二维码' }}
                    </button>
                  </template>
                </div>

                <div class="bot-platform-actions" v-else>
                  <button type="button" class="ds-btn ds-btn-danger-ghost" @click="unbindBot('feishu')">解绑</button>
                </div>
              </div>

              <!-- 微信 -->
              <div v-if="botTab === 'wechat'" class="bot-platform-card">
                <div class="bot-platform-header">
                  <div class="bot-platform-info">
                    <div class="bot-platform-icon-big">
                      <img :src="weixinIcon" alt="微信" />
                    </div>
                    <div>
                      <div class="bot-platform-name">微信机器人</div>
                      <div class="bot-platform-status">
                        <span v-if="botStatus.wechat?.bound && botStatus.wechat?.enabled" class="settings-tag settings-tag-success">已启用</span>
                        <span v-else-if="botStatus.wechat?.bound" class="settings-tag settings-tag-warning">已绑定·未启用</span>
                        <span v-else class="settings-tag settings-tag-muted">未配置</span>
                      </div>
                    </div>
                  </div>
                  <label v-if="botStatus.wechat?.bound" class="settings-switch" title="启用/禁用">
                    <input type="checkbox" :checked="botStatus.wechat?.enabled" @change="toggleBot('wechat', $event.target.checked)" />
                    <span class="settings-switch-thumb" />
                  </label>
                </div>

                <!-- 扫码区域 -->
                <div class="bot-qrcode-area" v-if="!botStatus.wechat?.bound">
                  <template v-if="wechatQRImg">
                    <img :src="wechatQRImg" alt="微信二维码" class="bot-qrcode-img" />
                    <p class="bot-qrcode-tip">{{ wechatPollStatus === 'scaned' ? '已扫码，请在手机上确认' : '请使用微信扫码绑定' }}</p>
                  </template>
                  <template v-else>
                    <button type="button" class="ds-btn ds-btn-primary" :disabled="botSaving" @click="startWechatQR">
                      {{ botSaving ? '获取中...' : '获取二维码' }}
                    </button>
                  </template>
                </div>

                <div class="bot-platform-actions" v-else>
                  <button type="button" class="ds-btn ds-btn-danger-ghost" @click="unbindBot('wechat')">解绑</button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
    </div><!-- /.settings-modal -->

    <!-- 模型新增/编辑表单 -->
    <div v-if="formVisible" class="settings-screen settings-form-overlay" @click.self="formVisible = false">
        <div class="settings-dialog-form">
          <header class="settings-head">
            <h2 class="settings-title">{{ editingModel ? t('settings.editModel') : t('settings.addModel') }}</h2>
            <button type="button" class="settings-close" :title="t('settings.cancel')" @click="formVisible = false">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </header>
          <form class="settings-form settings-card-body" @submit.prevent="handleSave">
            <div class="settings-field">
              <label class="settings-field-label">{{ t('settings.modelId') }}</label>
              <input v-model="formData.model" type="text" class="ds-input" :placeholder="t('settings.modelIdHint')" />
            </div>
            <div class="settings-field">
              <label class="settings-field-label">{{ t('settings.apiKey') }}</label>
              <input v-model="formData.apiKey" type="password" class="ds-input" placeholder="sk-..." autocomplete="off" />
            </div>
            <div class="settings-field">
              <label class="settings-field-label">{{ t('settings.baseUrl') }}</label>
              <input v-model="formData.baseUrl" type="text" class="ds-input" placeholder="https://api.openai.com/v1" />
            </div>

            <div class="settings-advanced">
              <button type="button" class="settings-advanced-toggle" @click="advancedOpen = !advancedOpen">
                <span>{{ t('settings.advancedParams') }}</span>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  :class="{ 'settings-advanced-chevron-open': advancedOpen }"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
              <div v-show="advancedOpen" class="settings-advanced-panel">
                <div class="settings-field">
                  <label class="settings-field-label">{{ t('settings.modelName') }}</label>
                  <input
                    v-model="formData.name"
                    type="text"
                    class="ds-input"
                    :placeholder="t('settings.modelNameHint')"
                    @input="nameManuallyEdited = true"
                  />
                </div>
                <div class="settings-field-row">
                  <div class="settings-field">
                    <label class="settings-field-label">{{ t('settings.toolRounds') }}</label>
                    <input v-model.number="formData.max_tool_rounds" type="number" min="1" max="500" class="ds-input" />
                  </div>
                  <div class="settings-field">
                    <label class="settings-field-label">{{ t('settings.contextWindow') }}</label>
                    <input v-model.number="formData.context_window" type="number" min="1" class="ds-input" placeholder="200000" />
                  </div>
                </div>
                <div class="settings-field settings-field-inline">
                  <label class="settings-field-label">{{ t('settings.active') }}</label>
                  <label class="settings-switch">
                    <input type="checkbox" v-model="formData.isActive" />
                    <span class="settings-switch-thumb" />
                  </label>
                </div>
              </div>
            </div>

            <footer class="settings-foot">
              <button type="button" class="ds-btn ds-btn-secondary" @click="formVisible = false">{{ t('settings.cancel') }}</button>
              <button type="submit" class="ds-btn ds-btn-primary" :disabled="saving">
                <span v-if="saving">保存中…</span>
                <span v-else>{{ t('settings.save') }}</span>
              </button>
            </footer>
          </form>
        </div>
      </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSettingsStore } from '../stores/settings'
import { useAuthStore } from '../stores/auth'
import { useI18n } from '../i18n'
import api from '../api'
import {
  getGlobalMemory,
  saveGlobalMemory,
  listProjectMemories,
  getProjectMemory,
  saveProjectMemory,
} from '../api/memory'
import qqIcon from '../assets/QQ.png'
import feishuIcon from '../assets/feishu.png'
import weixinIcon from '../assets/weixin.png'
import './SettingsModal.css'

const settingsStore = useSettingsStore()
const auth = useAuthStore()
const { t, tm } = useI18n()

const visible = ref(true)
const activeTab = ref('profile')

const tabs = [
  {
    key: 'profile',
    label: t('settings.profile'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`
  },
  {
    key: 'models',
    label: t('settings.models'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="3"/></svg>`
  },
  {
    key: 'general',
    label: t('settings.general'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`
  },
  {
    key: 'bots',
    label: t('settings.bots'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>`
  },
  {
    key: 'memory',
    label: t('settings.memory'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7z"/><line x1="9" y1="21" x2="15" y2="21"/><line x1="10" y1="17" x2="10" y2="21"/><line x1="14" y1="17" x2="14" y2="21"/></svg>`
  },
  {
    key: 'about',
    label: t('settings.about'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`
  },
]

const formattedJoinTime = computed(() => {
  const t = auth.user?.created_at
  if (!t) return '-'
  try {
    return new Date(t).toLocaleDateString()
  } catch {
    return '-'
  }
})

function membershipText(level) {
  const map = tm('settings.membership')
  return map[level] ?? map[0]
}

// 模型列表
const models = ref([])
const loading = ref(false)

// 模型类型子标签（对话 / OCR / ASR）
const modelTypes = [
  { key: 'chat', label: t('settings.modelTypeChat') },
  { key: 'ocr', label: t('settings.modelTypeOcr') },
  { key: 'asr', label: t('settings.modelTypeAsr') },
]
const modelTypeTab = ref('chat')

async function fetchModels() {
  loading.value = true
  try {
    const res = await api.get('/api/models', { params: { type: modelTypeTab.value } })
    models.value = res.data
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Failed to load models')
  } finally {
    loading.value = false
  }
}

onMounted(fetchModels)

watch(activeTab, (tab) => {
  if (tab === 'models') {
    fetchModels()
  }
})

watch(modelTypeTab, () => fetchModels())

// 新增/编辑表单
const formVisible = ref(false)
const editingModel = ref(null)
const saving = ref(false)
const advancedOpen = ref(false)
const nameManuallyEdited = ref(false)
const formData = reactive({
  name: '',
  model: '',
  apiKey: '',
  baseUrl: '',
  max_tool_rounds: 100,
  context_window: 200000,
  isActive: false,
  type: 'chat',
})

watch(
  () => formData.model,
  (val) => {
    if (!nameManuallyEdited.value) {
      formData.name = val
    }
  },
)

function resetForm() {
  formData.name = ''
  formData.model = ''
  formData.apiKey = ''
  formData.baseUrl = ''
  formData.max_tool_rounds = 100
  formData.context_window = 200000
  formData.isActive = false
  formData.type = 'chat'
  advancedOpen.value = false
  nameManuallyEdited.value = false
}

function openAddForm() {
  editingModel.value = null
  resetForm()
  formData.type = modelTypeTab.value
  formVisible.value = true
}

function openEditForm(m) {
  editingModel.value = m
  formData.name = m.name
  formData.model = m.model
  formData.apiKey = m.apiKey
  formData.baseUrl = m.baseUrl
  formData.max_tool_rounds = m.max_tool_rounds
  formData.context_window = m.context_window
  formData.isActive = m.isActive
  formData.type = m.type || 'chat'
  advancedOpen.value = m.name !== m.model
  nameManuallyEdited.value = m.name !== m.model
  formVisible.value = true
}

function buildPayload() {
  const payload = { ...formData }
  if (!payload.name?.trim()) {
    payload.name = payload.model
  }
  return payload
}

async function handleSave() {
  if (!formData.model || !formData.apiKey || !formData.baseUrl) {
    ElMessage.warning(t('settings.fillRequiredFields'))
    return
  }
  saving.value = true
  try {
    const payload = buildPayload()
    if (editingModel.value) {
      await api.put(`/api/models/${editingModel.value.id}`, payload)
      ElMessage.success('Updated')
    } else {
      await api.post('/api/models', payload)
      ElMessage.success('Created')
    }
    formVisible.value = false
    await fetchModels()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Save failed')
  } finally {
    saving.value = false
  }
}

async function handleDelete(m) {
  try {
    await ElMessageBox.confirm(t('settings.deleteConfirm'), '', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/models/${m.id}`)
    ElMessage.success('Deleted')
    await fetchModels()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Delete failed')
  }
}

async function toggleActive(m, val) {
  try {
    await api.put(`/api/models/${m.id}`, { isActive: val })
    await fetchModels()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Update failed')
  }
}

// ── 消息平台（QQ 表单 / 飞书扫码 / 微信扫码）──
const botTab = ref('qq')
const botTabs = [
  { key: 'qq', label: 'QQ 机器人', icon: qqIcon },
  { key: 'feishu', label: '飞书机器人', icon: feishuIcon },
  { key: 'wechat', label: '微信机器人', icon: weixinIcon },
]
const botStatus = ref({ qq: null, feishu: null, wechat: null })
const botEdit = ref({ qq: false })
const botSaving = ref(false)
const botForms = reactive({
  qq: { app_id: '', app_secret: '' },
})

// 微信扫码
const wechatQRImg = ref('')
const wechatQRKey = ref('')
const wechatPollStatus = ref('')
let wechatPollTimer = null

// 飞书扫码
const feishuQRImg = ref('')
const feishuPollStatus = ref('')
let feishuPollTimer = null

async function fetchBotStatus() {
  try {
    const res = await api.get('/api/bot/platforms')
    for (const p of res.data) {
      botStatus.value[p.platform] = { enabled: p.enabled, bound: p.bound }
    }
  } catch (err) {
    // 静默失败
  }
}

watch(activeTab, (tab) => {
  if (tab === 'bots') fetchBotStatus()
  else { stopWechatPoll(); stopFeishuPoll() }
  if (tab === 'memory') initMemory()
})

// ── 记忆与规则 ──
const memoryTab = ref('global')
const globalMemory = ref('')
const projectMemory = ref('')
const selectedWorkspace = ref('')
const projectMemories = ref([])
const memoryLoading = ref(false)
const memorySaving = ref(false)
let globalLoaded = false

async function initMemory() {
  // 全局记忆仅加载一次，项目列表每次进入刷新（可能新建了 workspace）
  if (!globalLoaded) {
    await loadGlobalMemory()
    globalLoaded = true
  }
  await fetchProjectMemories()
}

async function loadGlobalMemory() {
  memoryLoading.value = true
  try {
    const res = await getGlobalMemory()
    globalMemory.value = res.data.content || ''
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '加载全局记忆失败')
  } finally {
    memoryLoading.value = false
  }
}

async function fetchProjectMemories() {
  try {
    const res = await listProjectMemories()
    projectMemories.value = res.data.projects || []
    // 若当前选中的 workspace 已不存在，重置选择
    if (selectedWorkspace.value && !projectMemories.value.some(p => p.workspace === selectedWorkspace.value)) {
      selectedWorkspace.value = ''
      projectMemory.value = ''
    }
  } catch (err) {
    // 静默失败
  }
}

async function loadProjectMemory() {
  if (!selectedWorkspace.value) {
    projectMemory.value = ''
    return
  }
  memoryLoading.value = true
  try {
    const res = await getProjectMemory(selectedWorkspace.value)
    projectMemory.value = res.data.content || ''
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '加载项目记忆失败')
    projectMemory.value = ''
  } finally {
    memoryLoading.value = false
  }
}

function switchMemoryTab(tab) {
  memoryTab.value = tab
}

async function saveGlobal() {
  memorySaving.value = true
  try {
    await saveGlobalMemory(globalMemory.value)
    ElMessage.success(t('settings.memorySaved'))
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    memorySaving.value = false
  }
}

async function saveProject() {
  if (!selectedWorkspace.value) return
  memorySaving.value = true
  try {
    await saveProjectMemory(selectedWorkspace.value, projectMemory.value)
    ElMessage.success(t('settings.memorySaved'))
    // 刷新列表中的 has_memory 状态
    await fetchProjectMemories()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    memorySaving.value = false
  }
}

// ── QQ（表单）──
async function saveQQ() {
  if (!botForms.qq.app_id?.trim() || !botForms.qq.app_secret?.trim()) {
    ElMessage.warning('App ID 和 App Secret 不能为空')
    return
  }
  botSaving.value = true
  try {
    await api.post('/api/bot/platforms/qq', {
      app_id: botForms.qq.app_id,
      app_secret: botForms.qq.app_secret,
      enabled: true,
    })
    ElMessage.success('QQ 配置已保存')
    botEdit.value.qq = false
    botForms.qq.app_id = ''
    botForms.qq.app_secret = ''
    await fetchBotStatus()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    botSaving.value = false
  }
}

// ── 微信（扫码）──
async function startWechatQR() {
  botSaving.value = true
  try {
    const res = await api.post('/api/bot/platforms/wechat/qrcode')
    if (res.data.success && res.data.qrcode_img) {
      wechatQRImg.value = res.data.qrcode_img
      wechatQRKey.value = res.data.qrcode_key || ''
      wechatPollStatus.value = 'pending'
      startWechatPoll()
    } else {
      ElMessage.error(res.data.error || '获取二维码失败')
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '获取二维码失败')
  } finally {
    botSaving.value = false
  }
}

function startWechatPoll() {
  stopWechatPoll()
  wechatPollTimer = setInterval(async () => {
    try {
      const res = await api.post('/api/bot/platforms/wechat/qrcode/poll', {
        qrcode_key: wechatQRKey.value || undefined,
      })
      wechatPollStatus.value = res.data.status || ''
      if (res.data.status === 'confirmed') {
        stopWechatPoll()
        wechatQRImg.value = ''
        ElMessage.success('微信绑定成功')
        await fetchBotStatus()
      } else if (res.data.status === 'expired') {
        stopWechatPoll()
        wechatQRImg.value = ''
        ElMessage.warning('二维码已过期，请重新获取')
      }
    } catch {
      // ignore
    }
  }, 3000)
}

function stopWechatPoll() {
  if (wechatPollTimer) {
    clearInterval(wechatPollTimer)
    wechatPollTimer = null
  }
}

// ── 飞书（扫码）──
async function startFeishuQR() {
  botSaving.value = true
  try {
    const res = await api.post('/api/bot/platforms/feishu/qrcode')
    if (res.data.phase === 'configured' || res.data.phase === 'authorized') {
      // 已配置，直接刷新状态
      await fetchBotStatus()
      return
    }
    if (res.data.success && res.data.qrcode_img) {
      feishuQRImg.value = res.data.qrcode_img
      feishuPollStatus.value = 'pending'
      startFeishuPoll()
    } else {
      ElMessage.error(res.data.message || res.data.error || '获取二维码失败')
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '获取二维码失败')
  } finally {
    botSaving.value = false
  }
}

function startFeishuPoll() {
  stopFeishuPoll()
  feishuPollTimer = setInterval(async () => {
    try {
      const res = await api.post('/api/bot/platforms/feishu/qrcode/poll')
      feishuPollStatus.value = res.data.status || ''
      if (res.data.status === 'confirmed') {
        stopFeishuPoll()
        feishuQRImg.value = ''
        ElMessage.success('飞书绑定成功')
        await fetchBotStatus()
      } else if (res.data.status === 'error' || res.data.status === 'cancelled') {
        stopFeishuPoll()
        feishuQRImg.value = ''
        ElMessage.error(res.data.message || '飞书授权失败')
      }
    } catch {
      // ignore
    }
  }, 3000)
}

function stopFeishuPoll() {
  if (feishuPollTimer) {
    clearInterval(feishuPollTimer)
    feishuPollTimer = null
  }
}

// ── 通用 ──
async function toggleBot(platform, enabled) {
  try {
    await api.post(`/api/bot/platforms/${platform}/toggle`, { enabled })
    await fetchBotStatus()
  } catch (err) {
    ElMessage.error('切换状态失败')
    await fetchBotStatus()
  }
}

async function unbindBot(platform) {
  const name = platform === 'qq' ? 'QQ' : platform === 'feishu' ? '飞书' : '微信'
  try {
    await ElMessageBox.confirm(`确定解绑${name}吗？解绑后将清除凭据并停止该平台机器人。`, '', { type: 'warning' })
    // 飞书解绑前取消注册
    if (platform === 'feishu') {
      stopFeishuPoll()
      feishuQRImg.value = ''
      await api.post('/api/bot/platforms/feishu/cancel').catch(() => {})
    }
    // 微信解绑前清除二维码
    if (platform === 'wechat') {
      stopWechatPoll()
      wechatQRImg.value = ''
    }
    await api.delete(`/api/bot/platforms/${platform}`)
    ElMessage.success('已解绑')
    botEdit.value[platform] = false
    await fetchBotStatus()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.response?.data?.detail || '解绑失败')
  }
}

function handleLogout() {
  auth.logout()
  settingsStore.closeSettings()
}

function handleClose() {
  settingsStore.closeSettings()
}
</script>
