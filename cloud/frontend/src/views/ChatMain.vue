<template>
  <main class="chat-main">
    <!-- 空状态：欢迎页 + 输入框 + 模板画廊 -->
    <div v-if="!hasActiveChat" class="chat-empty">
      <div class="chat-empty-inner">
        <div class="chat-welcome-brand">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
          <h1 class="chat-welcome-title">{{ activeAgentName ? t('chat.asAgentTitle', { name: activeAgentName }) : 'Work with Aries Cloud' }}</h1>
        </div>
        <p class="chat-welcome-sub">
          {{ activeAgentName ? t('chat.asAgentSubtitle') : t('chat.welcomeSubtitle') }}
        </p>

        <!-- 输入框 -->
        <div class="chat-composer">
          <div v-if="attachedImages.length" class="composer-image-previews">
            <div v-for="img in attachedImages" :key="img.id" class="composer-image-preview">
              <img :src="img.data" :alt="img.name" />
              <button type="button" class="composer-image-remove" @click="removeImage(img.id)">×</button>
            </div>
          </div>
          <div
            ref="inputRef"
            class="chat-composer-input"
            contenteditable="true"
            data-placeholder="placeholder"
            :data-placeholder-text="t('chat.placeholder')"
            @keydown.enter.exact.prevent="handleSend"
            @input="onEditorInput"
            @click="onEditorClick"
            @mouseup="saveEditorSelection"
            @keyup="saveEditorSelection"
            @blur="saveEditorSelection"
            @paste="onPaste"
          ></div>
          <div class="chat-composer-actions">
            <div class="chat-composer-left">
              <button type="button" class="composer-icon-btn" :title="t('chat.uploadImage')" @click="openImagePicker">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <circle cx="9" cy="9" r="2"/>
                  <path d="m21 15-3.5-3.5a2 2 0 0 0-2.8 0L6 21"/>
                </svg>
              </button>
              <button
                type="button"
                class="composer-pill-btn composer-kb-btn"
                :class="{ 'is-kb-active': kbEnabled }"
                :title="t('chat.kbToggle')"
                @click="toggleKb"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
                  <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
                </svg>
                <span class="composer-pill-label">{{ kbEnabled ? t('chat.kbOn') : t('chat.kbOff') }}</span>
              </button>
              <button
                type="button"
                ref="agentTriggerRef"
                class="composer-pill-btn"
                :class="{ 'is-active': agentMenuOpen, 'has-value': !!activeAgentName }"
                @click="toggleAgentMenu"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2a5 5 0 1 0 0 10 5 5 0 0 0 0-10z"/>
                  <path d="M12 14c-4.4 0-8 2.7-8 6v2h16v-2c0-3.3-3.6-6-8-6z"/>
                </svg>
                <span class="composer-pill-label">{{ activeAgentName || t('chat.mainAgent') }}</span>
                <svg class="composer-pill-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>
              <button
                type="button"
                ref="skillTriggerRef"
                class="composer-pill-btn"
                :class="{ 'is-active': skillMenuOpen, 'has-value': selectedSkills.length > 0 }"
                @click="toggleSkillMenu"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                <span class="composer-pill-label">{{ skillButtonLabel }}</span>
                <svg class="composer-pill-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>
            </div>
            <div class="chat-composer-right">
              <!-- 上下文占用量指示器（模型按钮旁） -->
              <div v-if="contextInfo" class="context-usage" :title="contextTooltip">
                <span class="context-usage-label">ctx {{ contextInfo.usage_percent }}%</span>
                <span class="context-usage-bar">
                  <span class="context-usage-fill" :style="{ width: contextInfo.usage_percent + '%' }" />
                </span>
              </div>
              <div class="composer-model-dropdown" ref="welcomeDropdownRef">
                <button
                  type="button"
                  class="composer-mode-btn"
                  :class="{ 'is-active': welcomeModelOpen }"
                  :disabled="switchingModel"
                  @click="toggleModelMenu('welcome')"
                >
                    <span class="composer-mode-label">{{ switchingModel ? t('chat.switchingModel') : (hasModel ? activeModel.name : t('chat.noModel')) }}</span>
                  <svg class="composer-mode-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
                <div v-if="welcomeModelOpen" class="composer-model-menu" role="listbox">
                  <div v-if="models.length === 0" class="composer-model-menu-empty">
                    <span>{{ t('chat.modelMenuEmpty') }}</span>
                    <button type="button" class="composer-model-menu-add" @click="openSettings">{{ t('chat.modelMenuAdd') }}</button>
                  </div>
                  <template v-else>
                    <button
                      v-for="m in models"
                      :key="m.id"
                      type="button"
                      class="composer-model-option"
                      :class="{ active: m.id === activeModel?.id }"
                      role="option"
                      :aria-selected="m.id === activeModel?.id"
                      :disabled="switchingModel"
                      @click="selectModel(m)"
                    >
                      <span class="composer-model-check" :class="{ checked: m.id === activeModel?.id }" />
                      <span class="composer-model-name">{{ m.name }}</span>
                      <span class="composer-model-id">{{ m.model }}</span>
                    </button>
                    <div class="composer-model-menu-divider" />
                    <button type="button" class="composer-model-menu-add" @click="openSettings">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 5v14M5 12h14"/>
                      </svg>
                      {{ t('chat.modelMenuAdd') }}
                    </button>
                  </template>
                </div>
              </div>
              <button
                type="button"
                class="composer-send-btn"
                :class="{ 'is-stop': sending }"
                :disabled="!sending && !canSend"
                @click="sending ? $emit('stop-generation') : handleSend()"
              >
                <svg v-if="!sending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="19" x2="12" y2="5"/>
                  <polyline points="5 12 12 5 19 12"/>
                </svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
              </button>
            </div>
          </div>
        </div>

        <!-- 工作目录选择栏（仅欢迎界面） -->
        <div class="chat-composer-workspace-bar">
          <div ref="wsTriggerRef" class="workspace-picker">
            <!-- 已选非默认工作目录：显示 pill + 清除按钮 -->
            <div v-if="isCustomWorkspace" class="workspace-pill" :title="wsLabel">
              <button
                type="button"
                class="workspace-pill-main"
                @click="toggleWsMenu"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
                <span class="workspace-pill-name">{{ wsLabel }}</span>
                <svg class="workspace-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="m6 9 6 6 6-6"/>
                </svg>
              </button>
              <button
                type="button"
                class="workspace-pill-close"
                :title="t('workspace.normal')"
                @click.stop="clearWorkspace"
              >
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M18 6 6 18M6 6l12 12"/>
                </svg>
              </button>
            </div>
            <!-- 默认：普通对话 -->
            <button
              v-else
              type="button"
              class="workspace-empty-btn"
              @click="toggleWsMenu"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span>{{ t('workspace.workIn') }}</span>
              <svg class="workspace-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="m6 9 6 6 6-6"/>
              </svg>
            </button>
          </div>
          <Teleport to="body">
            <div
              v-if="wsMenuOpen"
              ref="wsMenuRef"
              class="ws-menu ws-menu-portal"
              :style="wsMenuStyle"
              @click.stop
            >
              <div class="ws-menu-search-wrap">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="11" cy="11" r="8"/>
                  <path d="m21 21-4.3-4.3"/>
                </svg>
                <input
                  ref="wsSearchRef"
                  v-model="wsSearchQuery"
                  type="text"
                  class="ws-menu-search"
                  :placeholder="t('workspace.searchPlaceholder')"
                  @keydown.escape="wsMenuOpen = false"
                />
              </div>
              <ul v-if="filteredWorkspaces.length" class="ws-menu-list">
                <li
                  v-for="w in filteredWorkspaces"
                  :key="w.name"
                  class="ws-menu-item"
                  :class="{ active: w.name === selectedWorkspace }"
                  @click="selectWorkspace(w.name)"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>
                  </svg>
                  <span class="ws-menu-name" :title="w.name">{{ workspaceDisplayName(w.name) }}</span>
                  <svg
                    v-if="w.name === selectedWorkspace"
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    class="ws-menu-check"
                  >
                    <path d="M20 6 9 17l-5-5"/>
                  </svg>
                </li>
              </ul>
              <div v-else class="ws-menu-empty">{{ t('workspace.empty') }}</div>
              <div class="ws-menu-divider"></div>
              <form v-if="creatingWs" class="ws-menu-create" @submit.prevent="confirmCreateWs">
                <input
                  ref="newWsInputRef"
                  v-model="newWsName"
                  class="ws-menu-input"
                  type="text"
                  :placeholder="t('workspace.createPrompt')"
                  @keydown.esc.prevent="cancelCreateWs"
                />
                <button type="submit" class="ws-menu-confirm" :disabled="!newWsName.trim()">{{ t('settings.save') }}</button>
                <button type="button" class="ws-menu-cancel" @click="cancelCreateWs">{{ t('settings.cancel') }}</button>
              </form>
              <button
                v-else
                type="button"
                class="ws-menu-action ws-menu-action-accent"
                @click="creatingWs = true"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
                <span>{{ t('workspace.create') }}</span>
              </button>
            </div>
          </Teleport>
        </div>

        <!-- 模板画廊 -->
        <div class="template-gallery">
          <div class="template-gallery-header">
            <span class="template-gallery-title">精选模板</span>
            <button type="button" class="template-gallery-more">查看更多 ›</button>
          </div>
          <div class="template-cards">
            <button
              v-for="tpl in templates"
              :key="tpl.id"
              type="button"
              class="template-card"
              @click="useTemplate(tpl)"
            >
              <div class="template-card-cover">
                <img :src="tpl.cover" :alt="tpl.title" />
              </div>
              <div class="template-card-meta">
                <div class="template-card-title">{{ tpl.title }}</div>
                <div class="template-card-desc">{{ tpl.desc }}</div>
              </div>
            </button>
          </div>
        </div>

        <p class="chat-composer-tip">
            {{ t('chat.tip') }}
          </p>
      </div>
    </div>

    <!-- 对话中状态 -->
    <div v-else class="chat-active">
      <header class="chat-header">
        <div class="chat-header-start">
          <h2 class="chat-header-title" :title="currentSession?.title">
            {{ activeAgentName ? `[${activeAgentName}] ${currentSession?.title || ''}` : currentSession?.title }}
          </h2>
          <div v-if="currentSession" class="chat-header-menu-wrap">
            <button
              type="button"
              class="chat-header-menu-trigger"
              :class="{ 'is-open': headerMenuOpen }"
              @click.stop="toggleHeaderMenu"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="5" cy="12" r="1.5"/>
                <circle cx="12" cy="12" r="1.5"/>
                <circle cx="19" cy="12" r="1.5"/>
              </svg>
            </button>
            <div class="sidebar-session-menu chat-header-session-menu" :class="{ show: headerMenuOpen }">
              <button type="button" class="sidebar-menu-item" @click.stop="handlePin">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2z"/></svg>
                <span>{{ currentSession.is_pinned ? t('session.unpin') : t('session.pin') }}</span>
              </button>
              <button type="button" class="sidebar-menu-item" @click.stop="handleRename">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                <span>{{ t('session.rename') }}</span>
              </button>
              <button type="button" class="sidebar-menu-item sidebar-menu-item-danger" @click.stop="handleDelete">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                <span>{{ t('session.delete') }}</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      <div
        ref="messagesContainer"
        class="chat-messages"
        @scroll="handleMessagesScroll"
        @wheel="handleMessagesWheel"
        @touchstart.passive="handleMessagesTouchStart"
        @touchmove.passive="handleMessagesTouchMove"
      >
        <div
          v-for="(msg, index) in currentMessages"
          :key="msg.id || index"
          class="msg-row"
          :class="[msg.role, { 'msg-row-search-hit': isHighlighted(msg.id) }]"
          :data-message-id="msg.id"
        >
          <div class="msg-row-inner">
            <div v-if="msg.role === 'user'" class="msg-user-wrap">
              <div v-if="msg.images?.length" class="msg-user-images">
                <img
                  v-for="(src, imgIdx) in msg.images"
                  :key="imgIdx"
                  :src="src"
                  alt=""
                  class="msg-user-image"
                />
              </div>
              <div v-if="msg.content" class="msg-content msg-content-user">
                <MarkdownRenderer :content="msg.content" :show-actions="false" />
              </div>
              <button
                type="button"
                class="msg-copy-btn"
                :title="copiedMsgId === msg.id ? t('chat.copied') : t('chat.copy')"
                @click="copyMessage(msg)"
              >
                <svg v-if="copiedMsgId === msg.id" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2"/>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
              </button>
            </div>
            <div v-else class="msg-assistant-wrap">
              <div class="msg-content msg-content-assistant">
                <AssistantMessage
                  :content="msg.content"
                  :reasoning="msg.reasoning || ''"
                  :is-loading="msg.isLoading"
                  :model="msg.model || ''"
                  :token-usage="msg.tokenUsage || null"
                  :session-id="currentSession?.id || ''"
                  :message-id="msg.id || ''"
                  :duration-ms="msg.durationMs || 0"
                  :tool-calls="msg.toolCalls || []"
                  :blocks="msg.blocks || []"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-composer-area">
        <div class="chat-composer">
          <div v-if="attachedImages.length" class="composer-image-previews">
            <div v-for="img in attachedImages" :key="img.id" class="composer-image-preview">
              <img :src="img.data" :alt="img.name" />
              <button type="button" class="composer-image-remove" @click="removeImage(img.id)">×</button>
            </div>
          </div>
          <div
            ref="inputRef"
            class="chat-composer-input"
            contenteditable="true"
            data-placeholder="placeholder"
            :data-placeholder-text="t('chat.sendPlaceholder')"
            @keydown.enter.exact.prevent="handleSend"
            @input="onEditorInput"
            @click="onEditorClick"
            @mouseup="saveEditorSelection"
            @keyup="saveEditorSelection"
            @blur="saveEditorSelection"
            @paste="onPaste"
          ></div>
          <div class="chat-composer-actions">
            <div class="chat-composer-left">
              <button type="button" class="composer-icon-btn" :title="t('chat.uploadImage')" @click="openImagePicker">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <circle cx="9" cy="9" r="2"/>
                  <path d="m21 15-3.5-3.5a2 2 0 0 0-2.8 0L6 21"/>
                </svg>
              </button>
              <button
                type="button"
                class="composer-pill-btn composer-kb-btn"
                :class="{ 'is-kb-active': kbEnabled }"
                :title="t('chat.kbToggle')"
                @click="toggleKb"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
                  <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
                </svg>
                <span class="composer-pill-label">{{ kbEnabled ? t('chat.kbOn') : t('chat.kbOff') }}</span>
              </button>
              <button
                type="button"
                ref="agentTriggerRef"
                class="composer-pill-btn"
                :class="{ 'is-active': agentMenuOpen, 'has-value': !!activeAgentName }"
                @click="toggleAgentMenu"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2a5 5 0 1 0 0 10 5 5 0 0 0 0-10z"/>
                  <path d="M12 14c-4.4 0-8 2.7-8 6v2h16v-2c0-3.3-3.6-6-8-6z"/>
                </svg>
                <span class="composer-pill-label">{{ activeAgentName || t('chat.mainAgent') }}</span>
                <svg class="composer-pill-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>
              <button
                type="button"
                ref="skillTriggerRef"
                class="composer-pill-btn"
                :class="{ 'is-active': skillMenuOpen, 'has-value': selectedSkills.length > 0 }"
                @click="toggleSkillMenu"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                <span class="composer-pill-label">{{ skillButtonLabel }}</span>
                <svg class="composer-pill-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>
            </div>
            <div class="chat-composer-right">
              <!-- 上下文占用量指示器（模型按钮旁） -->
              <div v-if="contextInfo" class="context-usage" :title="contextTooltip">
                <span class="context-usage-label">ctx {{ contextInfo.usage_percent }}%</span>
                <span class="context-usage-bar">
                  <span class="context-usage-fill" :style="{ width: contextInfo.usage_percent + '%' }" />
                </span>
              </div>
              <div class="composer-model-dropdown" ref="activeDropdownRef">
                <button
                  type="button"
                  class="composer-mode-btn"
                  :class="{ 'is-active': activeModelOpen }"
                  :disabled="switchingModel"
                  @click="toggleModelMenu('active')"
                >
                    <span class="composer-mode-label">{{ switchingModel ? t('chat.switchingModel') : (hasModel ? activeModel.name : t('chat.noModel')) }}</span>
                  <svg class="composer-mode-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
                <div v-if="activeModelOpen" class="composer-model-menu" role="listbox">
                  <div v-if="models.length === 0" class="composer-model-menu-empty">
                    <span>{{ t('chat.modelMenuEmpty') }}</span>
                    <button type="button" class="composer-model-menu-add" @click="openSettings">{{ t('chat.modelMenuAdd') }}</button>
                  </div>
                  <template v-else>
                    <button
                      v-for="m in models"
                      :key="m.id"
                      type="button"
                      class="composer-model-option"
                      :class="{ active: m.id === activeModel?.id }"
                      role="option"
                      :aria-selected="m.id === activeModel?.id"
                      :disabled="switchingModel"
                      @click="selectModel(m)"
                    >
                      <span class="composer-model-check" :class="{ checked: m.id === activeModel?.id }" />
                      <span class="composer-model-name">{{ m.name }}</span>
                      <span class="composer-model-id">{{ m.model }}</span>
                    </button>
                    <div class="composer-model-menu-divider" />
                    <button type="button" class="composer-model-menu-add" @click="openSettings">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 5v14M5 12h14"/>
                      </svg>
                      {{ t('chat.modelMenuAdd') }}
                    </button>
                  </template>
                </div>
              </div>
              <button
                type="button"
                class="composer-send-btn"
                :class="{ 'is-stop': sending }"
                :disabled="!sending && !canSend"
                @click="sending ? $emit('stop-generation') : handleSend()"
              >
                <svg v-if="!sending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="19" x2="12" y2="5"/>
                  <polyline points="5 12 12 5 19 12"/>
                </svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <input
      ref="imageInputRef"
      type="file"
      accept="image/*"
      multiple
      hidden
      @change="onImageFileChange"
    />

    <!-- Agent 选择器下拉菜单 -->
    <Teleport to="body">
      <div
        v-if="agentMenuOpen"
        ref="agentMenuRef"
        class="composer-dropdown-menu composer-dropdown-portal"
        :style="agentMenuStyle"
        @click.stop
      >
        <div class="composer-dropdown-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.3-4.3"/>
          </svg>
          <input
            ref="agentSearchRef"
            v-model="agentSearch"
            type="text"
            class="composer-dropdown-search-input"
            :placeholder="t('chat.searchAgent')"
            @keydown.escape="agentMenuOpen = false"
          />
        </div>
        <ul v-if="filteredAgents.length || !agentSearch" class="composer-dropdown-list">
          <li
            class="composer-dropdown-item"
            :class="{ active: !activeAgentName }"
            @click="selectAgent('')"
          >
            <span class="composer-dropdown-check" :class="{ checked: !activeAgentName }" />
            <span class="composer-dropdown-name">{{ t('chat.mainAgent') }}</span>
          </li>
          <li
            v-for="a in filteredAgents"
            :key="a.name"
            class="composer-dropdown-item"
            :class="{ active: a.name === activeAgentName }"
            @click="selectAgent(a.name)"
          >
            <span class="composer-dropdown-check" :class="{ checked: a.name === activeAgentName }" />
            <img v-if="a.avatar_data" :src="a.avatar_data" class="composer-dropdown-avatar" alt="" />
            <span class="composer-dropdown-name">{{ a.name }}</span>
            <span v-if="a.scope" class="composer-dropdown-scope">{{ a.scope === 'private' ? t('agents.scopePrivate') : t('agents.scopeShared') }}</span>
          </li>
        </ul>
        <div v-else class="composer-dropdown-empty">{{ t('chat.noAgent') }}</div>
      </div>
    </Teleport>

    <!-- Skill 选择器下拉菜单 -->
    <Teleport to="body">
      <div
        v-if="skillMenuOpen"
        ref="skillMenuRef"
        class="composer-dropdown-menu composer-dropdown-portal"
        :style="skillMenuStyle"
        @click.stop
      >
        <div class="composer-dropdown-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.3-4.3"/>
          </svg>
          <input
            ref="skillSearchRef"
            v-model="skillSearch"
            type="text"
            class="composer-dropdown-search-input"
            :placeholder="t('chat.searchSkill')"
            @keydown.escape="skillMenuOpen = false"
          />
        </div>
        <ul v-if="filteredSkills.length" class="composer-dropdown-list">
          <li
            v-for="s in filteredSkills"
            :key="s.folder_name"
            class="composer-dropdown-item"
            :class="{ active: isSkillSelected(s.folder_name) }"
            @click="toggleSkill(s.folder_name)"
          >
            <span class="composer-dropdown-checkbox" :class="{ checked: isSkillSelected(s.folder_name) }">
              <svg v-if="isSkillSelected(s.folder_name)" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </span>
            <img v-if="s.avatar_data" :src="s.avatar_data" class="composer-dropdown-avatar" alt="" />
            <span class="composer-dropdown-name">{{ s.name }}</span>
            <span v-if="s.scope" class="composer-dropdown-scope">{{ s.scope === 'private' ? t('skills.scopePrivate') : t('skills.scopeShared') }}</span>
          </li>
        </ul>
        <div v-else class="composer-dropdown-empty">{{ t('chat.noSkill') }}</div>
        <div v-if="selectedSkills.length" class="composer-dropdown-footer">
          <button type="button" class="composer-dropdown-clear" @click="clearSelectedSkills">{{ t('chat.clearSkills') }}</button>
        </div>
      </div>
    </Teleport>
  </main>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from '../i18n'
import { useSettingsStore } from '../stores/settings'
import api from '../api'
import { listWorkspaces, createWorkspace } from '../api/workspaces'
import { listSubagents } from '../api/subagents'
import { listSkills } from '../api/skills'
import { getFileIconUrl } from '../utils/fileIcons'
import AssistantMessage from '../components/AssistantMessage.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import tplResume from '../assets/template-resume.jpg'
import tplEvent from '../assets/template-event.jpg'
import tplBrand from '../assets/template-brand.jpg'

const { t } = useI18n()
const settingsStore = useSettingsStore()

const props = defineProps({
  hasActiveChat: Boolean,
  currentSession: Object,
  currentMessages: { type: Array, default: () => [] },
  sending: Boolean,
  user: Object,
  asAgent: { type: String, default: '' },
  highlightMessageId: { type: [String, Number], default: '' },
  selectedWorkspace: { type: String, default: 'default' },
})

const emit = defineEmits(['send-message', 'stop-generation', 'create-new-chat', 'sessions-changed', 'session-deleted', 'update:selectedWorkspace'])

const headerMenuOpen = ref(false)

function toggleHeaderMenu() {
  headerMenuOpen.value = !headerMenuOpen.value
}

function closeHeaderMenu() {
  headerMenuOpen.value = false
}

async function handlePin() {
  const s = props.currentSession
  if (!s) return
  closeHeaderMenu()
  try {
    await api.put(`/api/chat/sessions/${s.id}/pin`, { is_pinned: !s.is_pinned })
    emit('sessions-changed')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

async function handleRename() {
  const s = props.currentSession
  if (!s) return
  closeHeaderMenu()
  let value
  try {
    const result = await ElMessageBox.prompt(
      t('session.renamePrompt'),
      t('session.rename'),
      {
        confirmButtonText: t('settings.save'),
        cancelButtonText: t('settings.cancel'),
        inputValue: s.title || '',
        inputValidator: (val) => {
          if (!val?.trim()) return t('session.renameEmpty')
          return true
        },
      },
    )
    value = result.value
  } catch {
    return
  }
  const clean = value.trim()
  try {
    await api.put(`/api/chat/sessions/${s.id}/title`, { title: clean })
    emit('sessions-changed')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

async function handleDelete() {
  const s = props.currentSession
  if (!s) return
  closeHeaderMenu()
  try {
    await ElMessageBox.confirm(
      t('session.deleteConfirm', { title: s.title || s.id }),
      t('session.delete'),
      {
        type: 'warning',
        confirmButtonText: t('session.delete'),
        cancelButtonText: t('settings.cancel'),
      },
    )
  } catch {
    return
  }
  try {
    await api.delete(`/api/chat/sessions/${s.id}`)
    emit('session-deleted', s)
    emit('sessions-changed')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

const inputRef = ref(null)
const imageInputRef = ref(null)
const messagesContainer = ref(null)
const inputMessage = ref('')
const attachedImages = ref([])
// 知识库模式开关：开启后发送的消息会先检索知识库并注入上下文
const kbEnabled = ref(false)

function toggleKb() {
  kbEnabled.value = !kbEnabled.value
}
// contenteditable 编辑器状态
const editorHtml = ref('') // 保存编辑器 HTML，跨 welcome/active 切换时恢复
const hasInputContent = ref(false) // 编辑器是否有内容（含 chip）
const savedRange = ref(null) // 失焦前保存的光标位置，供插入 chip 用

// 监听 inputRef 挂载，恢复编辑器内容（处理 welcome/active 切换）
watch(inputRef, (el) => {
  if (el && editorHtml.value) {
    el.innerHTML = editorHtml.value
    placeCaretAtEnd(el)
    syncEditorState()
  }
})

// 把光标移到元素末尾
function placeCaretAtEnd(el) {
  const range = document.createRange()
  range.selectNodeContents(el)
  range.collapse(false)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
}

// 从编辑器 DOM 按顺序读取合并内容（chip 原地替换为 [@file:ref]，保持原始位置）
function getEditorContent() {
  const el = inputRef.value
  if (!el) return { content: '', hasRef: false }
  let content = ''
  let hasRef = false
  el.childNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      content += node.textContent
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      if (node.classList && node.classList.contains('composer-file-ref-chip')) {
        const ref = node.getAttribute('data-ref') || ''
        content += `[@file:${ref}]`
        hasRef = true
      } else if (node.tagName === 'BR') {
        content += '\n'
      } else if (node.tagName === 'DIV' || node.tagName === 'P') {
        content += (content ? '\n' : '') + (node.innerText || '')
      } else {
        content += node.innerText || node.textContent || ''
      }
    }
  })
  return { content: content.replace(/\u00a0/g, ' '), hasRef }
}

// 编辑器输入时同步状态
function onEditorInput() {
  syncEditorState()
}

function syncEditorState() {
  const el = inputRef.value
  if (!el) return
  // 空内容时清掉浏览器残留的 <br>，保证 :empty 占位符生效
  const hasChip = !!el.querySelector('.composer-file-ref-chip')
  const hasText = el.textContent.replace(/\u00a0/g, '').trim() !== ''
  if (!hasText && !hasChip) {
    el.innerHTML = ''
  }
  editorHtml.value = el.innerHTML
  const { content, hasRef } = getEditorContent()
  inputMessage.value = content
  hasInputContent.value = content.trim() !== '' || hasRef
}

// 供外部调用：在光标位置插入文件引用 chip
function addFileRef(ref) {
  if (!ref) return
  const hashIdx = ref.lastIndexOf('#L')
  const fullPath = hashIdx >= 0 ? ref.slice(0, hashIdx) : ref
  const lines = hashIdx >= 0 ? ref.slice(hashIdx + 1) : ''
  const name = fullPath.includes('/') ? fullPath.slice(fullPath.lastIndexOf('/') + 1) : fullPath

  const el = inputRef.value
  if (!el) {
    // 编辑器未挂载，暂存待恢复后插入（极少出现）
    return
  }
  el.focus()

  // 恢复光标
  let range
  if (savedRange.value) {
    const sel = window.getSelection()
    sel.removeAllRanges()
    sel.addRange(savedRange.value)
    range = savedRange.value
  } else {
    range = document.createRange()
    range.selectNodeContents(el)
    range.collapse(false)
  }

  // 构造 chip 节点
  const chip = document.createElement('span')
  chip.className = 'composer-file-ref-chip'
  chip.setAttribute('contenteditable', 'false')
  chip.setAttribute('data-ref', ref)
  chip.setAttribute('data-name', name)
  chip.innerHTML =
    `<img src="${getFileIconUrl(name)}" width="14" height="14" alt="" class="composer-file-ref-icon" />` +
    `<span class="composer-file-ref-name">${escapeHtml(name)}</span>` +
    (lines ? `<span class="composer-file-ref-lines">${escapeHtml(lines)}</span>` : '') +
    `<button type="button" class="composer-file-ref-remove" contenteditable="false">×</button>`

  range.deleteContents()
  range.insertNode(chip)

  // chip 后插入一个空格文本节点，便于继续输入
  const space = document.createTextNode('\u00a0')
  chip.after(space)

  // 光标移到空格后
  range.setStartAfter(space)
  range.collapse(true)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)

  syncEditorState()
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c])
}

// 点击 chip 的 × 删除（事件委托）
function onEditorClick(e) {
  const btn = e.target.closest('.composer-file-ref-remove')
  if (!btn) return
  const chip = btn.closest('.composer-file-ref-chip')
  if (!chip) return
  // 同时移除 chip 后可能跟随的空格
  const next = chip.nextSibling
  if (next && next.nodeType === Node.TEXT_NODE && next.textContent === '\u00a0') {
    next.remove()
  }
  chip.remove()
  syncEditorState()
  inputRef.value?.focus()
}

// 编辑器失焦/鼠标抬起时保存光标
function saveEditorSelection() {
  const sel = window.getSelection()
  if (sel.rangeCount && inputRef.value?.contains(sel.anchorNode)) {
    savedRange.value = sel.getRangeAt(0).cloneRange()
  }
}
const models = ref([])
const switchingModel = ref(false)
const copiedMsgId = ref(null)
let copiedMsgTimer = null

// 模型下拉：两个输入区分别维护开关
const welcomeModelOpen = ref(false)
const activeModelOpen = ref(false)
const welcomeDropdownRef = ref(null)
const activeDropdownRef = ref(null)

// ---- 工作目录选择器（仅欢迎界面）----
const workspaces = ref([])
const wsMenuOpen = ref(false)
const wsSearchQuery = ref('')
const wsSearchRef = ref(null)
const wsTriggerRef = ref(null)
const wsMenuRef = ref(null)
const wsMenuStyle = ref({})
const creatingWs = ref(false)
const newWsName = ref('')
const newWsInputRef = ref(null)

const isCustomWorkspace = computed(() => props.selectedWorkspace && props.selectedWorkspace !== 'default')

const wsLabel = computed(() => {
  const name = props.selectedWorkspace || 'default'
  if (name === 'default') return t('workspace.normal')
  return name
})

const filteredWorkspaces = computed(() => {
  // 下拉列表不展示 default（普通对话由按钮/清除操作体现）
  const list = workspaces.value.filter(w => w.name !== 'default')
  const q = wsSearchQuery.value.trim().toLowerCase()
  if (!q) return list
  return list.filter(w => w.name.toLowerCase().includes(q))
})

function workspaceDisplayName(name) {
  return name === 'default' ? t('workspace.normal') : name
}

async function loadWorkspaces() {
  try {
    const res = await listWorkspaces()
    workspaces.value = res.data.workspaces || []
  } catch (err) {
    console.error('Failed to load workspaces', err)
  }
}

function updateWsMenuPosition() {
  const el = wsTriggerRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  wsMenuStyle.value = {
    position: 'fixed',
    left: `${Math.max(8, rect.left)}px`,
    bottom: `${window.innerHeight - rect.top + 6}px`,
    minWidth: '230px',
    maxWidth: '320px',
    zIndex: '10000',
  }
}

function toggleWsMenu() {
  const next = !wsMenuOpen.value
  wsMenuOpen.value = next
  if (next) {
    wsSearchQuery.value = ''
    creatingWs.value = false
    newWsName.value = ''
    loadWorkspaces()
    nextTick(() => {
      updateWsMenuPosition()
      wsSearchRef.value?.focus()
    })
  }
}

function selectWorkspace(name) {
  wsMenuOpen.value = false
  wsSearchQuery.value = ''
  emit('update:selectedWorkspace', name)
}

function clearWorkspace() {
  wsMenuOpen.value = false
  wsSearchQuery.value = ''
  emit('update:selectedWorkspace', 'default')
}

async function confirmCreateWs() {
  const name = newWsName.value.trim()
  if (!name) return
  try {
    await createWorkspace(name)
    await loadWorkspaces()
    newWsName.value = ''
    creatingWs.value = false
    emit('update:selectedWorkspace', name)
    wsMenuOpen.value = false
    wsSearchQuery.value = ''
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('workspace.createFailed'))
  }
}

function cancelCreateWs() {
  creatingWs.value = false
  newWsName.value = ''
}

watch(creatingWs, async (val) => {
  if (val) {
    await nextTick()
    newWsInputRef.value?.focus()
  }
})

function handleWsDocClick(e) {
  if (wsMenuOpen.value) {
    if (wsTriggerRef.value && !wsTriggerRef.value.contains(e.target) &&
        wsMenuRef.value && !wsMenuRef.value.contains(e.target)) {
      wsMenuOpen.value = false
    }
  }
}

let wsRepositionHandler = null

// ---- Agent / Skill 选择器 ----
const agents = ref([])
const allSkills = ref([])
const selectedSkills = ref([]) // 选中的 skill folder_name 数组
const selectedAgent = ref(props.asAgent || '') // 本地维护的当前 Agent，可在同一对话内切换
const agentMenuOpen = ref(false)
const skillMenuOpen = ref(false)
const agentTriggerRef = ref(null)
const skillTriggerRef = ref(null)
const agentMenuRef = ref(null)
const skillMenuRef = ref(null)
const agentMenuStyle = ref({})
const skillMenuStyle = ref({})
const agentSearch = ref('')
const skillSearch = ref('')
const agentSearchRef = ref(null)
const skillSearchRef = ref(null)

const activeAgentName = computed(() => selectedAgent.value || props.asAgent || '')

// URL 传入的 asAgent 变化时同步本地状态（如从 SubagentsPage 跳转过来）
watch(() => props.asAgent, (val) => {
  selectedAgent.value = val || ''
})

const mainAgents = computed(() =>
  agents.value.filter(a => a.main_enabled && a.enabled)
)
const moreAgents = computed(() =>
  agents.value.filter(a => !(a.main_enabled && a.enabled))
)

const mainSkills = computed(() =>
  allSkills.value.filter(s => s.main_enabled && s.enabled)
)
const moreSkills = computed(() =>
  allSkills.value.filter(s => !(s.main_enabled && s.enabled))
)

const filteredAgents = computed(() => {
  const q = agentSearch.value.trim().toLowerCase()
  if (!q) return mainAgents.value
  return agents.value.filter(a =>
    a.name.toLowerCase().includes(q) || (a.description || '').toLowerCase().includes(q)
  )
})

const filteredSkills = computed(() => {
  const q = skillSearch.value.trim().toLowerCase()
  if (!q) return mainSkills.value
  return allSkills.value.filter(s =>
    s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q)
  )
})

const skillButtonLabel = computed(() => {
  if (selectedSkills.value.length === 0) return t('chat.selectSkill')
  return `${t('chat.selectSkill')} · ${selectedSkills.value.length}`
})

async function loadAgents() {
  try {
    agents.value = await listSubagents()
  } catch (err) {
    console.error('Failed to load agents', err)
  }
}

async function loadSkills() {
  try {
    allSkills.value = await listSkills()
  } catch (err) {
    console.error('Failed to load skills', err)
  }
}

function updateAgentMenuPosition() {
  const el = agentTriggerRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  agentMenuStyle.value = {
    position: 'fixed',
    left: `${Math.max(8, rect.left)}px`,
    bottom: `${window.innerHeight - rect.top + 6}px`,
    minWidth: '220px',
    maxWidth: '300px',
    zIndex: '10000',
  }
}

function updateSkillMenuPosition() {
  const el = skillTriggerRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  skillMenuStyle.value = {
    position: 'fixed',
    left: `${Math.max(8, rect.left)}px`,
    bottom: `${window.innerHeight - rect.top + 6}px`,
    minWidth: '220px',
    maxWidth: '300px',
    zIndex: '10000',
  }
}

function toggleAgentMenu() {
  const next = !agentMenuOpen.value
  agentMenuOpen.value = next
  skillMenuOpen.value = false
  if (next) {
    agentSearch.value = ''
    loadAgents()
    nextTick(() => {
      updateAgentMenuPosition()
      agentSearchRef.value?.focus()
    })
  }
}

function toggleSkillMenu() {
  const next = !skillMenuOpen.value
  skillMenuOpen.value = next
  agentMenuOpen.value = false
  if (next) {
    skillSearch.value = ''
    loadSkills()
    nextTick(() => {
      updateSkillMenuPosition()
      skillSearchRef.value?.focus()
    })
  }
}

function selectAgent(name) {
  agentMenuOpen.value = false
  agentSearch.value = ''
  selectedAgent.value = name || ''
}

function toggleSkill(folderName) {
  const idx = selectedSkills.value.indexOf(folderName)
  if (idx >= 0) {
    selectedSkills.value.splice(idx, 1)
  } else {
    selectedSkills.value.push(folderName)
  }
}

function isSkillSelected(folderName) {
  return selectedSkills.value.includes(folderName)
}

function clearSelectedSkills() {
  selectedSkills.value = []
}

let agentRepositionHandler = null
let skillRepositionHandler = null

const activeModel = computed(() => models.value.find(m => m.isActive) || models.value[0] || null)
const hasModel = computed(() => !!activeModel.value)
const canSend = computed(() => {
  return (hasInputContent.value || attachedImages.value.length > 0) && !props.sending
})

function openImagePicker() {
  imageInputRef.value?.click()
}

function addImageFiles(files) {
  for (const file of files) {
    if (!file.type.startsWith('image/')) continue
    const reader = new FileReader()
    reader.onload = () => {
      attachedImages.value.push({
        id: crypto.randomUUID(),
        data: reader.result,
        name: file.name,
      })
    }
    reader.readAsDataURL(file)
  }
}

function onImageFileChange(e) {
  addImageFiles(Array.from(e.target.files || []))
  e.target.value = ''
}

function onPaste(e) {
  const items = e.clipboardData?.items
  if (!items) return
  const imageFiles = []
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) imageFiles.push(file)
    }
  }
  if (imageFiles.length) {
    e.preventDefault()
    addImageFiles(imageFiles)
    return
  }
  // contenteditable 下：以纯文本形式粘贴，避免富文本污染
  const text = e.clipboardData?.getData('text/plain')
  if (text) {
    e.preventDefault()
    document.execCommand('insertText', false, text)
    syncEditorState()
  }
}

function removeImage(id) {
  attachedImages.value = attachedImages.value.filter(img => img.id !== id)
}

function clearComposer() {
  const el = inputRef.value
  if (el) el.innerHTML = ''
  inputMessage.value = ''
  attachedImages.value = []
  editorHtml.value = ''
  hasInputContent.value = false
  savedRange.value = null
}

function isHighlighted(messageId) {
  if (!props.highlightMessageId) return false
  return String(messageId) === String(props.highlightMessageId)
}

function scrollToMessage(messageId) {
  const id = String(messageId || props.highlightMessageId || '')
  if (!id) return
  autoScrollEnabled.value = false
  nextTick(() => {
    requestAnimationFrame(() => {
      const container = messagesContainer.value
      const el = container?.querySelector(`[data-message-id="${CSS.escape(id)}"]`)
      if (!el) return
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  })
}

// 文件引用 chip 的插入与删除见上方 contenteditable 实现（addFileRef / onEditorClick）

defineExpose({ scrollToMessage, insertText: addFileRef, addFileRef })

// 估算单条消息的文本长度（从 content 或 blocks 中提取）
function estimateMessageText(msg) {
  let text = msg?.content || ''
  const blocks = msg?.blocks
  if (Array.isArray(blocks) && blocks.length > 0) {
    for (const b of blocks) {
      if (b.text) text += '\n' + b.text
      else if (b.type === 'tool' && b.result) text += '\n' + b.result
    }
  }
  // 兜底：旧数据可能用 reasoning / toolCalls
  if (msg?.reasoning) text += '\n' + msg.reasoning
  if (Array.isArray(msg?.toolCalls)) {
    for (const tc of msg.toolCalls) {
      if (tc.result) text += '\n' + tc.result
    }
  }
  return text
}

// 从最新助手消息中获取上下文占用量；若后端尚未返回，则按当前输入 + 历史消息做兜底展示
const contextInfo = computed(() => {
  const msgs = props.currentMessages || []
  for (let i = msgs.length - 1; i >= 0; i--) {
    const info = msgs[i]?.contextInfo
    if (info) return info
  }
  const total = activeModel.value?.context_window
  if (!total) return null
  const text = (inputMessage.value || '') + msgs.map(estimateMessageText).join('')
  // 简单混合估算：CJK 约 1.5 字符/token，其他约 4 字符/token
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]/g) || []).length
  const other = text.length - cjk
  const estimated = Math.ceil(cjk / 1.5 + other / 4)
  return {
    estimated_tokens: estimated,
    context_window: total,
    usage_percent: Math.min(100, Math.round((estimated / total) * 1000) / 10),
    breakdown: {},
  }
})

const contextTooltip = computed(() => {
  if (!contextInfo.value) return ''
  const info = contextInfo.value
  const est = info.estimated_tokens || 0
  const total = info.context_window || 0
  const pct = info.usage_percent || 0
  const breakdown = info.breakdown || {}
  const source = info.breakdown && Object.keys(info.breakdown).length > 0 ? 'backend' : 'estimated'
  const parts = [`${est.toLocaleString()} / ${total.toLocaleString()} tokens (${pct}%)`, `source: ${source}`]
  if (breakdown.system) parts.push(`system: ${breakdown.system}`)
  if (breakdown.user) parts.push(`user: ${breakdown.user}`)
  if (breakdown.assistant) parts.push(`assistant: ${breakdown.assistant}`)
  if (breakdown.tool) parts.push(`tool: ${breakdown.tool}`)
  return parts.join(' | ')
})

function toggleModelMenu(which) {
  if (which === 'welcome') {
    activeModelOpen.value = false
    welcomeModelOpen.value = !welcomeModelOpen.value
  } else {
    welcomeModelOpen.value = false
    activeModelOpen.value = !activeModelOpen.value
  }
}

function closeAllModelMenus() {
  welcomeModelOpen.value = false
  activeModelOpen.value = false
}

function openSettings() {
  closeAllModelMenus()
  settingsStore.openSettings()
}

// 切换激活模型，沿用 SettingsModal 的 PUT /api/models/{id} { isActive: true }
async function selectModel(m) {
  if (switchingModel.value || m.id === activeModel.value?.id) {
    closeAllModelMenus()
    return
  }
  switchingModel.value = true
  try {
    await api.put(`/api/models/${m.id}`, { isActive: true })
    // 本地立即更新激活态，避免等待列表刷新的视觉延迟
    models.value.forEach(item => { item.isActive = item.id === m.id })
    ElMessage.success(`${t('settings.active')}: ${m.name}`)
    closeAllModelMenus()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Switch model failed')
  } finally {
    switchingModel.value = false
  }
}

function handleDocClick(e) {
  if (welcomeDropdownRef.value && !welcomeDropdownRef.value.contains(e.target)) {
    welcomeModelOpen.value = false
  }
  if (activeDropdownRef.value && !activeDropdownRef.value.contains(e.target)) {
    activeModelOpen.value = false
  }
  if (headerMenuOpen.value && !e.target.closest('.chat-header-menu-wrap')) {
    closeHeaderMenu()
  }
  handleWsDocClick(e)
  if (agentMenuOpen.value) {
    if (agentTriggerRef.value && !agentTriggerRef.value.contains(e.target) &&
        agentMenuRef.value && !agentMenuRef.value.contains(e.target)) {
      agentMenuOpen.value = false
    }
  }
  if (skillMenuOpen.value) {
    if (skillTriggerRef.value && !skillTriggerRef.value.contains(e.target) &&
        skillMenuRef.value && !skillMenuRef.value.contains(e.target)) {
      skillMenuOpen.value = false
    }
  }
}

function handleEsc(e) {
  if (e.key === 'Escape') {
    closeAllModelMenus()
    closeHeaderMenu()
    if (wsMenuOpen.value) wsMenuOpen.value = false
    if (agentMenuOpen.value) agentMenuOpen.value = false
    if (skillMenuOpen.value) skillMenuOpen.value = false
  }
}

onMounted(async () => {
  document.addEventListener('mousedown', handleDocClick)
  document.addEventListener('keydown', handleEsc)
  wsRepositionHandler = () => {
    if (wsMenuOpen.value) updateWsMenuPosition()
  }
  window.addEventListener('resize', wsRepositionHandler)
  window.addEventListener('scroll', wsRepositionHandler, true)
  agentRepositionHandler = () => {
    if (agentMenuOpen.value) updateAgentMenuPosition()
  }
  window.addEventListener('resize', agentRepositionHandler)
  window.addEventListener('scroll', agentRepositionHandler, true)
  skillRepositionHandler = () => {
    if (skillMenuOpen.value) updateSkillMenuPosition()
  }
  window.addEventListener('resize', skillRepositionHandler)
  window.addEventListener('scroll', skillRepositionHandler, true)
  try {
    const res = await api.get('/api/models')
    models.value = res.data
  } catch (err) {
    console.error('Failed to load models', err)
  }
  loadWorkspaces()
  loadAgents()
  loadSkills()
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleDocClick)
  document.removeEventListener('keydown', handleEsc)
  if (wsRepositionHandler) {
    window.removeEventListener('resize', wsRepositionHandler)
    window.removeEventListener('scroll', wsRepositionHandler, true)
    wsRepositionHandler = null
  }
  if (agentRepositionHandler) {
    window.removeEventListener('resize', agentRepositionHandler)
    window.removeEventListener('scroll', agentRepositionHandler, true)
    agentRepositionHandler = null
  }
  if (skillRepositionHandler) {
    window.removeEventListener('resize', skillRepositionHandler)
    window.removeEventListener('scroll', skillRepositionHandler, true)
    skillRepositionHandler = null
  }
})


const templates = [
  { id: 'tpl-1', title: '求职面试', desc: '结构化简历模板', cover: tplResume },
  { id: 'tpl-2', title: '活动策划', desc: '活动方案与排期', cover: tplEvent },
  { id: 'tpl-3', title: '品牌方案', desc: '品牌视觉规范', cover: tplBrand },
]

function useTemplate(tpl) {
  const el = inputRef.value
  const text = `使用「${tpl.title}」模板，${tpl.desc}。请帮我生成一份。`
  if (el) {
    el.innerText = text
    syncEditorState()
    placeCaretAtEnd(el)
  }
  nextTick(() => inputRef.value?.focus())
}

function handleSend() {
  const { content: raw } = getEditorContent()
  const content = raw.trim()
  const images = attachedImages.value.map(img => img.data)
  if ((!content && images.length === 0) || props.sending) return
  const skills = selectedSkills.value.length ? [...selectedSkills.value] : null
  const agentName = activeAgentName.value || null
  emit('send-message', { content, images, skills, agent_name: agentName, use_kb: kbEnabled.value })
  clearComposer()
}

function copyMessage(msg) {
  if (!msg.content) return
  navigator.clipboard.writeText(msg.content).then(() => {
    copiedMsgId.value = msg.id
    if (copiedMsgTimer) clearTimeout(copiedMsgTimer)
    copiedMsgTimer = setTimeout(() => { copiedMsgId.value = null }, 1500)
  }).catch(() => {})
}

const SCROLL_BOTTOM_THRESHOLD = 80
const autoScrollEnabled = ref(true)
let isProgrammaticScroll = false
let touchStartY = 0

function isNearBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_BOTTOM_THRESHOLD
}

function scrollToBottom(force = false) {
  nextTick(() => {
    const el = messagesContainer.value
    if (!el || (!force && !autoScrollEnabled.value)) return
    isProgrammaticScroll = true
    el.scrollTop = el.scrollHeight
    requestAnimationFrame(() => {
      isProgrammaticScroll = false
    })
  })
}

function handleMessagesScroll() {
  if (isProgrammaticScroll) return
  const el = messagesContainer.value
  if (!el) return
  autoScrollEnabled.value = isNearBottom(el)
}

function handleMessagesWheel(e) {
  if (e.deltaY < 0) {
    autoScrollEnabled.value = false
  }
}

function handleMessagesTouchStart(e) {
  touchStartY = e.touches[0]?.clientY ?? 0
}

function handleMessagesTouchMove(e) {
  const y = e.touches[0]?.clientY ?? touchStartY
  if (touchStartY - y > 8) {
    autoScrollEnabled.value = false
  }
}

// 消息变化时：仅在用户未主动上滑时跟随到底部（搜索定位时不抢滚动）
watch(() => props.currentMessages, () => {
  if (props.highlightMessageId) return
  scrollToBottom()
}, { deep: true })

// 发送新消息时恢复自动跟随
watch(() => props.sending, (sending) => {
  if (sending) {
    autoScrollEnabled.value = true
    scrollToBottom(true)
  }
})

// 切换会话 / 加载历史消息后滚到底部（搜索定位时除外）
watch(() => props.currentMessages.length, (len, prevLen) => {
  if (prevLen === 0 && len > 0) {
    if (props.highlightMessageId) {
      scrollToMessage(props.highlightMessageId)
    } else {
      autoScrollEnabled.value = true
      scrollToBottom(true)
    }
  }
})

watch(() => props.highlightMessageId, (id) => {
  if (id && props.currentMessages.length) {
    scrollToMessage(id)
  }
})

// 新建对话时清空输入框并聚焦
watch(() => props.hasActiveChat, (val) => {
  if (!val) {
    clearComposer()
    nextTick(() => inputRef.value?.focus())
  }
})
</script>
