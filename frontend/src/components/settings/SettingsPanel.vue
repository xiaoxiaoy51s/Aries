<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-container">
        <!-- 左侧导航 -->
        <nav class="modal-nav">
          <div class="modal-nav-header">
            <h1>设置</h1>
          </div>
          <ul class="modal-nav-list">
            <li
              :class="{ active: activeTab === 'models' }"
              @click="activeTab = 'models'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
              模型管理
            </li>
            <li
              :class="{ active: activeTab === 'accounts' }"
              @click="activeTab = 'accounts'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              账号绑定
            </li>
            <li
              :class="{ active: activeTab === 'paths' }"
              @click="activeTab = 'paths'; loadPathPermissions()"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              路径权限
            </li>
            <li
              :class="{ active: activeTab === 'pets' }"
              @click="activeTab = 'pets'; loadPets()"
            >
              <svg t="1781971061983" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg"
              p-id="3864" width="16" height="16">
              <path d="M636.589292 466.203569c-30.641231-33.988923-74.326646-53.492185-119.855261-53.492184-45.536492
              0-89.221908 19.495385-119.863139 53.492184L183.288123 703.188677c-46.355692 51.436308-55.6032
              124.463262-23.559877 186.045046 31.578585 60.675938 95.586462 94.538831 163.005046 86.244431l194.000739-23.835569
              194.000738 23.835569c6.750523 0.827077 13.469538 1.236677 20.133416 1.236677 59.809477 0 114.467446-32.886154
              142.879507-87.488985 32.043323-61.581785 22.795815-134.600862-23.567754-186.037169L636.589292 466.203569z
              m181.248 393.940677c-15.375754 29.538462-49.569477 58.927262-99.422523 52.791139l-197.844677-24.308185a31.373785
              31.373785 0 0 0-7.687877 0L315.045415 912.935385c-49.845169
              6.104615-84.046769-23.252677-99.422523-52.791139-15.745969-30.255262-20.204308-76.288 14.469908-114.766769l213.582769-236.985108c18.983385-21.062892 44.929969-32.657723 73.050585-32.657723 28.120615 0 54.0672 11.602708 73.050584 32.657723l213.58277 236.985108c34.682092 38.478769 30.215877 84.511508 14.477784 114.766769zM266.531446 364.016246c22.795815 18.660431 48.529723 28.349046 75.019816 28.349046 3.654892 0 7.325538-0.181169 11.004061-0.551384 74.988308-7.546092 126.282831-88.9856 116.791139-185.391262-5.293292-53.736369-28.900431-101.415385-64.779816-130.788431-25.560615-20.936862-56.083692-30.790892-86.031754-27.797661-74.980431 7.546092-126.282831 88.9856-116.791138 185.391261 5.301169 53.736369 28.908308 101.407508 64.787692 130.788431z m58.320739-253.487261c1.504492-0.157538 2.985354-0.220554 4.442584-0.220554 14.871631 0 27.277785 7.467323 35.351631 14.076061 22.677662 18.573785 38.376369 51.546585 41.984 88.213662 5.8368 59.273846-21.819077 112.632123-60.392369 116.515446-16.832985 1.693538-30.932677-6.592985-39.786339-13.847631-22.685538-18.573785-38.384246-51.546585-41.991877-88.213661-5.8368-59.281723 21.819077-112.64 60.39237-116.523323zM653.501046 391.806031c3.528862 0.354462 7.057723 0.527754 10.594462 0.527754 26.442831 0 52.877785-9.854031 75.429415-28.325416 35.871508-29.373046 59.486523-77.044185 64.779815-130.788431 9.491692-96.405662-41.810708-177.845169-116.791138-185.391261-30.286769-3.040492-60.085169 6.561477-86.023877 27.789785-35.879385 29.373046-59.486523 77.052062-64.787692 130.78843-9.483815 96.421415 41.818585 177.853046 116.799015 185.399139z m-54.082954-179.215754c3.607631-36.6592 19.306338-69.639877 41.991877-88.213662 8.861538-7.254646 22.992738-15.588431 39.786339-13.84763 38.573292 3.883323 66.229169 57.2416 60.392369 116.515446-3.607631 36.6592-19.306338 69.639877-41.984 88.213661-8.861538 7.254646-23.008492 15.556923-39.786339 13.847631-38.573292-3.875446-66.237046-57.2416-60.400246-116.515446zM231.077415 464.659692c-8.491323-43.189169-31.783385-80.273723-63.905477-101.746215-24.064-16.0768-51.704123-22.039631-77.839753-16.777846C26.647631 358.730831-11.894154 432.317046 3.402831 510.164677c8.491323 43.197046 31.791262 80.2816 63.913354 101.746215 18.353231 12.264369 38.793846 18.644677 59.069046 18.644677 6.293662 0 12.579446-0.6144 18.770707-1.858954 62.676677-12.603077 101.226338-86.189292 85.921477-164.036923zM102.329108 559.521477c-18.0224-12.043815-31.885785-35.036554-37.092431-61.518769-8.483446-43.149785 8.239262-84.409108 36.517415-90.096246 2.205538-0.441108 4.371692-0.645908 6.474831-0.645908 9.641354 0 18.109046 4.151138 23.930092 8.042338 18.0224 12.043815 31.885785 35.036554 37.084554 61.510893 8.483446 43.149785-8.231385 84.409108-36.509538 90.096246-12.303754 2.465477-23.315692-2.654523-30.404923-7.388554zM934.675692 346.135631c-26.119877-5.253908-53.783631 0.701046-77.839754 16.777846-32.122092 21.464615-55.414154 58.549169-63.905476 101.746215-15.304862 77.847631 23.2448 151.425969 85.921476 164.029046 6.199138 1.244554 12.477046 1.858954 18.770708 1.858954 20.267323 0 40.715815-6.380308 59.069046-18.644677 32.122092-21.464615 55.414154-58.557046 63.905477-101.746215 15.296985-77.839754-23.2448-151.425969-85.921477-164.021169z m24.087631 151.874954c-5.206646 26.474338-19.070031 49.467077-37.084554 61.518769-7.089231 4.741908-18.109046 9.877662-30.404923 7.396431-28.270277-5.687138-44.992985-46.946462-36.509538-90.096247 5.206646-26.474338 19.070031-49.474954 37.09243-61.518769 7.081354-4.741908 18.132677-9.846154 30.404924-7.396431 28.2624 5.679262 44.985108 46.938585 36.501661 90.096247z" fill="" p-id="3865"></path></svg>
              桌面宠物
            </li>
            <li
              :class="{ active: activeTab === 'network' }"
              @click="activeTab = 'network'; loadNetworkConfig()"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="2" y1="12" x2="22" y2="12"/>
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
              </svg>
              网络代理
            </li>
          </ul>
        </nav>

        <!-- 右侧内容 -->
        <div class="modal-body">
          <div class="modal-body-header">
            <h2>{{ tabTitle }}</h2>
            <button type="button" class="close-btn" @click="$emit('close')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <div class="modal-body-content">
            <!-- 模型管理 -->
            <div v-if="activeTab === 'models'" class="settings-section">
              <div class="section-header">
                <span class="section-desc">管理可用的 AI 模型</span>
                <button type="button" class="secondary-btn" @click="openAddModal">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 5v14M5 12h14"/>
                  </svg>
                  新增模型
                </button>
              </div>
              <div class="model-list">
                <div
                  v-for="model in modelStore.modelList"
                  :key="model.id"
                  class="model-item"
                  :class="{ active: model.isActive }"
                  @click="handleSetActive(model.id)"
                >
                  <div class="model-info">
                    <span class="model-name">{{ model.name }}</span>
                    <span v-if="model.isActive" class="model-tag">默认</span>
                  </div>
                  <div class="model-actions" @click.stop>
                    <button type="button" class="icon-btn-sm" title="编辑" @click="openEditModal(model)">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                      </svg>
                    </button>
                    <button
                      v-if="model.id !== 'default-vision'"
                      type="button"
                      class="icon-btn-sm delete"
                      title="删除"
                      @click="handleDelete(model.id)"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 账号绑定 -->
            <div v-if="activeTab === 'accounts' && !configPanel" class="settings-section">
              <p class="section-desc">绑定第三方账号以启用消息推送</p>
              <div class="account-bind-list">
                <div v-for="account in accountStore.accounts" :key="account.platform" class="account-item">
                  <div class="account-icon" :class="account.platform">
                    <img v-if="account.platform === 'feishu'" src="@/assets/feishu.svg" alt="飞书" />
                    <img v-else-if="account.platform === 'qq'" src="@/assets/qq.svg" alt="QQ" />
                    <img v-else src="@/assets/weixin.svg" alt="微信" />
                  </div>
                  <div class="account-info">
                    <span class="account-name">{{ account.name }}</span>
                    <span class="account-status" :class="{ bound: account.enabled && account.running }">
                      {{ account.enabled && account.running ? '已连接' : account.enabled ? '已启用' : account.configured ? '未启用' : '未配置' }}
                    </span>
                  </div>
                  <div class="account-actions">
                    <button
                      v-if="!account.configured"
                      type="button"
                      class="bind-btn"
                      @click="openConfigPanel(account.platform)"
                    >
                      配置
                    </button>
                    <template v-else>
                      <button
                        type="button"
                        class="bind-btn"
                        :class="{ bound: account.enabled }"
                        @click="handleBind(account.platform)"
                      >
                        {{ account.enabled ? '禁用' : '启用' }}
                      </button>
                      <button
                        type="button"
                        class="unbind-btn"
                        title="解绑账号"
                        @click="handleUnbind(account.platform)"
                      >
                        解绑
                      </button>
                    </template>
                  </div>
                </div>
              </div>
            </div>

            <!-- QQ 配置面板 -->
            <div v-if="activeTab === 'accounts' && configPanel === 'qq'" class="config-panel">
              <div class="config-panel-header">
                <button type="button" class="back-btn" @click="closeConfigPanel">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                </button>
                <h3>QQ 机器人配置</h3>
              </div>
              <div class="config-form">
                <label class="form-label">App ID</label>
                <input v-model="qqForm.app_id" type="text" class="form-input" placeholder="请输入 QQ 机器人 App ID" />
                <label class="form-label">App Secret</label>
                <input v-model="qqForm.app_secret" type="password" class="form-input" placeholder="请输入 App Secret" />
                <button type="button" class="form-submit-btn" :disabled="!qqForm.app_id || !qqForm.app_secret || configLoading" @click="saveQQ">
                  {{ configLoading ? '保存中...' : '保存并启用' }}
                </button>
              </div>
            </div>

            <!-- 微信配置面板（扫码） -->
            <div v-if="activeTab === 'accounts' && configPanel === 'wechat'" class="config-panel">
              <div class="config-panel-header">
                <button type="button" class="back-btn" @click="closeConfigPanel">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                </button>
                <h3>微信绑定</h3>
              </div>
              <div class="qrcode-area">
                <template v-if="wechatQRImg">
                  <img :src="wechatQRImg" alt="微信二维码" class="qrcode-img" />
                  <p class="qrcode-tip">{{ wechatPollStatus === 'scaned' ? '已扫码，请在手机上确认' : '请使用微信扫码绑定' }}</p>
                </template>
                <template v-else>
                  <button type="button" class="form-submit-btn" :disabled="configLoading" @click="startWechatQR">
                    {{ configLoading ? '获取中...' : '获取二维码' }}
                  </button>
                </template>
              </div>
            </div>

            <!-- 飞书配置面板（扫码） -->
            <div v-if="activeTab === 'accounts' && configPanel === 'feishu'" class="config-panel">
              <div class="config-panel-header">
                <button type="button" class="back-btn" @click="closeConfigPanel">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                </button>
                <h3>飞书绑定</h3>
              </div>
              <div class="qrcode-area">
                <template v-if="feishuQRImg">
                  <img :src="feishuQRImg" alt="飞书二维码" class="qrcode-img" />
                  <p class="qrcode-tip">{{ feishuPollStatus === 'pending' ? '请使用飞书 App 扫码授权' : '授权成功' }}</p>
                </template>
                <template v-else>
                  <button type="button" class="form-submit-btn" :disabled="configLoading" @click="startFeishuQR">
                    {{ configLoading ? '获取中...' : '获取二维码' }}
                  </button>
                </template>
              </div>
            </div>

            <!-- 路径权限 -->
            <div v-if="activeTab === 'paths'" class="settings-section">
              <p class="section-desc">管理 AI 可访问的路径。白名单路径 AI 可自由操作，黑名单路径 AI 无法访问（直接拒绝并告知用户限制）。</p>

              <!-- 白名单 -->
              <div class="path-section">
                <div class="path-section-header">
                  <h4>白名单（可访问路径）</h4>
                  <button type="button" class="add-path-btn" @click="handleAddPath('whitelist')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 5v14M5 12h14"/>
                    </svg>
                    添加
                  </button>
                </div>
                <div class="path-list">
                  <div v-for="p in whitelistPaths" :key="p.id" class="path-item">
                    <span class="path-value">{{ p.path }}</span>
                    <button type="button" class="remove-path-btn" title="移除" @click="handleRemovePath(p.path)">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 6L6 18M6 6l12 12"/>
                      </svg>
                    </button>
                  </div>
                  <div v-if="whitelistPaths.length === 0" class="path-empty">暂无白名单路径</div>
                </div>
              </div>

              <!-- 黑名单 -->
              <div class="path-section">
                <div class="path-section-header">
                  <h4>黑名单（禁止访问路径）</h4>
                  <button type="button" class="add-path-btn danger" @click="handleAddPath('blacklist')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 5v14M5 12h14"/>
                    </svg>
                    添加
                  </button>
                </div>
                <div class="path-list">
                  <div v-for="p in blacklistPaths" :key="p.id" class="path-item danger">
                    <span class="path-value">{{ p.path }}</span>
                    <button type="button" class="remove-path-btn" title="移除" @click="handleRemovePath(p.path)">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 6L6 18M6 6l12 12"/>
                      </svg>
                    </button>
                  </div>
                  <div v-if="blacklistPaths.length === 0" class="path-empty">暂无黑名单路径</div>
                </div>
              </div>
            </div>

            <!-- 桌面宠物 -->
            <div v-if="activeTab === 'pets'" class="settings-section">
              <div class="section-header">
                <span class="section-desc">桌面宠物（Codex 兼容格式：spritesheet.webp + pet.json）。宠物目录：~/.Aries/pets/</span>
                <div class="section-header-actions">
                  <button type="button" class="icon-btn" :disabled="petsLoading" title="打开宠物文件夹" @click="openPetsFolder">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                    </svg>
                  </button>
                  <button type="button" class="icon-btn" :disabled="petsLoading" :title="petsLoading ? '加载中…' : '刷新'" @click="loadPets">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin': petsLoading }">
                      <path d="M3 12a9 9 0 1 0 9-9"/><path d="M3 3v6h6"/>
                    </svg>
                  </button>
                </div>
              </div>
              <div v-if="petsLoading && petsList.length === 0" class="path-empty">加载中...</div>
              <div v-else-if="petsList.length === 0" class="path-empty">
                暂无宠物，请将 Codex 宠物（spritesheet.webp + pet.json）放入 ~/.Aries/pets/&lt;宠物名&gt;/ 目录
              </div>
              <div v-else class="pet-grid">
                <div
                  v-for="pet in petsList"
                  :key="pet.id"
                  class="pet-card"
                  @click="showPetOnDesktop(pet)"
                >
                  <div class="pet-preview">
                    <div class="pet-preview-sprite" :style="getPetPreviewStyle(pet)" />
                  </div>
                  <div class="pet-name" :title="pet.displayName || pet.name">{{ pet.displayName || pet.name }}</div>
                </div>
              </div>
            </div>

            <!-- 网络代理 -->
            <div v-if="activeTab === 'network'" class="settings-section">
              <p class="section-desc">配置代理服务器。AI 搜索、爬虫、npm/git 等操作访问匹配的域名或命令时自动走代理。</p>

              <!-- 启用开关 -->
              <div class="network-toggle-row">
                <div class="network-toggle-info">
                  <span class="network-toggle-label">启用代理</span>
                  <span class="network-toggle-hint">开启后，下方域名和命令将走代理访问</span>
                </div>
                <button
                  type="button"
                  class="network-switch"
                  :class="{ on: networkConfig.enabled }"
                  @click="networkConfig.enabled = !networkConfig.enabled"
                >
                  <span class="network-switch-knob" />
                </button>
              </div>

              <!-- 代理地址 -->
              <div class="network-field">
                <label class="form-label">代理地址</label>
                <input
                  v-model="networkConfig.proxy_url"
                  type="text"
                  class="form-input"
                  placeholder="http://127.0.0.1:7890"
                  :disabled="!networkConfig.enabled"
                />
              </div>

              <!-- 命令行代理开关 -->
              <div class="network-toggle-row">
                <div class="network-toggle-info">
                  <span class="network-toggle-label">命令行代理</span>
                  <span class="network-toggle-hint">npm install / git clone 等命令也注入代理环境变量</span>
                </div>
                <button
                  type="button"
                  class="network-switch"
                  :class="{ on: networkConfig.command_proxy }"
                  :disabled="!networkConfig.enabled"
                  @click="networkConfig.command_proxy = !networkConfig.command_proxy"
                >
                  <span class="network-switch-knob" />
                </button>
              </div>

              <!-- 代理域名列表 -->
              <div class="network-field">
                <label class="form-label">代理域名</label>
                <span class="network-field-hint">访问这些域名时走代理（子域名自动匹配，如 google.com 包含 www.google.com）</span>
                <div class="network-tag-input">
                  <input
                    v-model="networkDomainInput"
                    type="text"
                    class="form-input network-tag-input-field"
                    placeholder="输入域名后回车，如 google.com"
                    :disabled="!networkConfig.enabled"
                    @keydown.enter.prevent="addNetworkDomain"
                  />
                  <button
                    type="button"
                    class="network-tag-add-btn"
                    :disabled="!networkConfig.enabled || !networkDomainInput.trim()"
                    @click="addNetworkDomain"
                  >添加</button>
                </div>
                <div class="network-tag-list">
                  <span
                    v-for="(d, i) in networkConfig.proxy_domains"
                    :key="'d' + i"
                    class="network-tag"
                  >
                    {{ d }}
                    <button
                      type="button"
                      class="network-tag-remove"
                      :disabled="!networkConfig.enabled"
                      @click="removeNetworkDomain(i)"
                    >&times;</button>
                  </span>
                  <span v-if="networkConfig.proxy_domains.length === 0" class="network-tag-empty">暂无域名</span>
                </div>
              </div>

              <!-- 代理命令列表 -->
              <div class="network-field">
                <label class="form-label">代理命令</label>
                <span class="network-field-hint">以这些前缀开头的命令会注入代理环境变量</span>
                <div class="network-tag-input">
                  <input
                    v-model="networkCommandInput"
                    type="text"
                    class="form-input network-tag-input-field"
                    placeholder="输入命令前缀后回车，如 npm install"
                    :disabled="!networkConfig.enabled || !networkConfig.command_proxy"
                    @keydown.enter.prevent="addNetworkCommand"
                  />
                  <button
                    type="button"
                    class="network-tag-add-btn"
                    :disabled="!networkConfig.enabled || !networkConfig.command_proxy || !networkCommandInput.trim()"
                    @click="addNetworkCommand"
                  >添加</button>
                </div>
                <div class="network-tag-list">
                  <span
                    v-for="(c, i) in networkConfig.proxy_commands"
                    :key="'c' + i"
                    class="network-tag"
                  >
                    {{ c }}
                    <button
                      type="button"
                      class="network-tag-remove"
                      :disabled="!networkConfig.enabled || !networkConfig.command_proxy"
                      @click="removeNetworkCommand(i)"
                    >&times;</button>
                  </span>
                  <span v-if="networkConfig.proxy_commands.length === 0" class="network-tag-empty">暂无命令</span>
                </div>
              </div>

              <!-- 操作按钮 -->
              <div class="network-actions">
                <button
                  type="button"
                  class="network-test-btn"
                  :disabled="!networkConfig.enabled || networkTesting"
                  @click="handleTestProxy"
                >{{ networkTesting ? '测试中...' : '测试代理' }}</button>
                <button
                  type="button"
                  class="form-submit-btn"
                  :disabled="networkSaving"
                  @click="handleSaveNetwork"
                >{{ networkSaving ? '保存中...' : '保存配置' }}</button>
              </div>

              <!-- 测试结果 -->
              <div v-if="networkTestResult" class="network-test-result" :class="{ success: networkTestResult.success, fail: !networkTestResult.success }">
                {{ networkTestResult.success ? '代理可用' : '代理不可用' }}{{ networkTestResult.error ? '：' + networkTestResult.error : '' }}
              </div>
            </div>
          </div>
        </div>

        <!-- 模型编辑弹窗 -->
        <ModelEditModal
          :visible="modalVisible"
          :is-edit="isEditMode"
          :model="editingModel"
          @close="closeModal"
          @save="handleSave"
        />

        <!-- 删除确认弹窗 -->
        <div v-if="showDeleteModal" class="modal-overlay" @click="cancelDelete">
          <div class="modal-dialog" @click.stop>
            <div class="modal-header">确认删除</div>
            <div class="modal-body">
              <p>确定要删除这个模型吗？</p>
            </div>
            <div class="modal-footer">
              <button class="modal-btn modal-btn-cancel" @click="cancelDelete">取消</button>
              <button class="modal-btn modal-btn-danger" @click="confirmDelete">删除</button>
            </div>
          </div>
        </div>

        <!-- 解绑确认弹窗 -->
        <div v-if="showUnbindModal" class="modal-overlay" @click="cancelUnbind">
          <div class="modal-dialog" @click.stop>
            <div class="modal-header">确认解绑</div>
            <div class="modal-body">
              <p>确定要解绑{{ unbindPlatform === 'qq' ? 'QQ' : unbindPlatform === 'wechat' ? '微信' : unbindPlatform === 'feishu' ? '飞书' : unbindPlatform }}吗？此操作会清除该平台的所有配置。</p>
            </div>
            <div class="modal-footer">
              <button class="modal-btn modal-btn-cancel" @click="cancelUnbind">取消</button>
              <button class="modal-btn modal-btn-danger" @click="confirmUnbind">解绑</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useModelStore, type ModelItem } from '@/stores/model'
import { useAccountStore } from '@/stores/account'
import {
  saveQQConfig,
  wechatQRCode,
  wechatQRCodePoll,
  feishuQRCode,
  feishuQRCodePoll,
  cancelFeishuRegistration,
} from '@/api/platform'
import {
  listPathPermissions,
  addPathPermission as apiAddPathPermission,
  removePathPermission as apiRemovePathPermission,
  type PathPermission,
} from '@/api/pathPermissions'
import { selectDirectory } from '@/api/system'
import { listPets, type PetInfo } from '@/api/pets'
import { getNetworkConfig, saveNetworkConfig, testNetworkProxy, type NetworkConfig } from '@/api/network'
import ModelEditModal from './ModelEditModal.vue'

const props = defineProps<{ visible: boolean }>()
defineEmits<{ close: [] }>()

const modelStore = useModelStore()
const accountStore = useAccountStore()

// 弹窗打开时加载数据
watch(() => props.visible, (val) => {
  if (val) {
    modelStore.loadModels()
    accountStore.fetchAccounts()
    configPanel.value = ''
  }
})

function handleBind(platform: string) {
  accountStore.togglePlatform(platform)
}

function handleUnbind(platform: string) {
  unbindPlatform.value = platform
  showUnbindModal.value = true
}

async function confirmUnbind() {
  if (unbindPlatform.value) {
    await accountStore.unbind(unbindPlatform.value)
    showUnbindModal.value = false
    unbindPlatform.value = null
  }
}

function cancelUnbind() {
  showUnbindModal.value = false
  unbindPlatform.value = null
}

// ---------- 配置面板 ----------
const configPanel = ref('')
const configLoading = ref(false)

// QQ 表单
const qqForm = ref({ app_id: '', app_secret: '' })

function openConfigPanel(platform: string) {
  // 离开飞书配置时取消后端注册流程
  if (configPanel.value === 'feishu' && platform !== 'feishu') {
    cancelFeishuRegistration().catch(() => {})
  }
  configPanel.value = platform
  qqForm.value = { app_id: '', app_secret: '' }
  wechatQRImg.value = ''
  wechatQRKey.value = ''
  wechatPollStatus.value = ''
  feishuQRImg.value = ''
  feishuPollStatus.value = ''
}

function closeConfigPanel() {
  if (configPanel.value === 'feishu') {
    cancelFeishuRegistration().catch(() => {})
  }
  stopWechatPoll()
  stopFeishuPoll()
  configPanel.value = ''
}

async function saveQQ() {
  configLoading.value = true
  try {
    await saveQQConfig({
      enabled: true,
      app_id: qqForm.value.app_id,
      app_secret: qqForm.value.app_secret,
      mode: 'agent',
    })
    configPanel.value = ''
    await accountStore.fetchAccounts()
  } catch (e: any) {
    alert(e.message || '保存失败')
  } finally {
    configLoading.value = false
  }
}

// 微信扫码
const wechatQRImg = ref('')
const wechatQRKey = ref('')
const wechatPollStatus = ref('')
let wechatPollTimer: ReturnType<typeof setInterval> | null = null

async function startWechatQR() {
  configLoading.value = true
  try {
    const res = await wechatQRCode()
    if (res.success && res.qrcode_img) {
      wechatQRImg.value = res.qrcode_img
      wechatQRKey.value = res.qrcode_key || ''
      wechatPollStatus.value = 'pending'
      startWechatPoll()
    } else {
      alert(res.error || '获取二维码失败')
    }
  } catch (e: any) {
    alert(e.message || '获取二维码失败')
  } finally {
    configLoading.value = false
  }
}

function startWechatPoll() {
  stopWechatPoll()
  wechatPollTimer = setInterval(async () => {
    try {
      const res = await wechatQRCodePoll(wechatQRKey.value || undefined)
      wechatPollStatus.value = res.status || ''
      if (res.status === 'confirmed') {
        stopWechatPoll()
        configPanel.value = ''
        await accountStore.fetchAccounts()
      } else if (res.status === 'expired') {
        stopWechatPoll()
        wechatQRImg.value = ''
      }
    } catch {
      // ignore poll errors
    }
  }, 3000)
}

function stopWechatPoll() {
  if (wechatPollTimer) {
    clearInterval(wechatPollTimer)
    wechatPollTimer = null
  }
}

// 飞书扫码
const feishuQRImg = ref('')
const feishuPollStatus = ref('')
let feishuPollTimer: ReturnType<typeof setInterval> | null = null

async function startFeishuQR() {
  configLoading.value = true
  try {
    const res = await feishuQRCode()
    if (res.success && res.qrcode_img) {
      feishuQRImg.value = res.qrcode_img
      feishuPollStatus.value = 'pending'
      startFeishuPoll()
    } else if (res.phase === 'configured' || res.phase === 'authorized') {
      feishuPollStatus.value = 'confirmed'
      configPanel.value = ''
      await accountStore.fetchAccounts()
    } else {
      alert(res.message || res.error || '获取二维码失败')
    }
  } catch (e: any) {
    alert(e.message || '获取二维码失败')
  } finally {
    configLoading.value = false
  }
}

function startFeishuPoll() {
  stopFeishuPoll()
  feishuPollTimer = setInterval(async () => {
    try {
      const res = await feishuQRCodePoll()
      feishuPollStatus.value = res.status || ''
      if (res.status === 'confirmed') {
        stopFeishuPoll()
        configPanel.value = ''
        await accountStore.fetchAccounts()
      } else if (res.status === 'error') {
        stopFeishuPoll()
        feishuQRImg.value = ''
      }
    } catch {
      // ignore poll errors
    }
  }, 3000)
}

function stopFeishuPoll() {
  if (feishuPollTimer) {
    clearInterval(feishuPollTimer)
    feishuPollTimer = null
  }
}

onUnmounted(() => {
  stopWechatPoll()
  stopFeishuPoll()
})

const activeTab = ref<'models' | 'accounts' | 'paths' | 'pets' | 'network'>('models')

const tabTitle = computed(() => {
  const map = { models: '模型管理', accounts: '账号绑定', paths: '路径权限', pets: '桌面宠物', network: '网络代理' } as const
  return map[activeTab.value]
})

// 模型编辑弹窗
const modalVisible = ref(false)
const isEditMode = ref(false)
const editingModel = ref<ModelItem | null>(null)

function openAddModal() {
  isEditMode.value = false
  editingModel.value = null
  modalVisible.value = true
}

function openEditModal(model: ModelItem) {
  isEditMode.value = true
  editingModel.value = model
  modalVisible.value = true
}

function closeModal() {
  modalVisible.value = false
  editingModel.value = null
}

async function handleSave(data: Omit<ModelItem, 'id'>) {
  if (isEditMode.value && editingModel.value) {
    await modelStore.updateModel(editingModel.value.id, data)
  } else {
    await modelStore.addModel(data)
  }
  closeModal()
}

async function handleSetActive(id: string) {
  await modelStore.setActiveModel(id)
}

// 删除确认弹窗
const showDeleteModal = ref(false)
const modelToDelete = ref<string | null>(null)

// 解绑确认弹窗
const showUnbindModal = ref(false)
const unbindPlatform = ref<string | null>(null)

function handleDelete(id: string) {
  modelToDelete.value = id
  showDeleteModal.value = true
}

async function confirmDelete() {
  if (modelToDelete.value) {
    await modelStore.deleteModel(modelToDelete.value)
    showDeleteModal.value = false
    modelToDelete.value = null
  }
}

function cancelDelete() {
  showDeleteModal.value = false
  modelToDelete.value = null
}

// ---------- 路径权限 ----------
const pathPermissions = ref<PathPermission[]>([])
const whitelistPaths = computed(() => pathPermissions.value.filter(p => p.type === 'whitelist'))
const blacklistPaths = computed(() => pathPermissions.value.filter(p => p.type === 'blacklist'))

async function loadPathPermissions() {
  try {
    const res = await listPathPermissions()
    pathPermissions.value = res.permissions || []
  } catch (e) {
    console.error('加载路径权限失败', e)
    pathPermissions.value = []
  }
}

async function handleRemovePath(path: string) {
  try {
    await apiRemovePathPermission(path)
    pathPermissions.value = pathPermissions.value.filter(p => p.path !== path)
  } catch (e: any) {
    alert(e.message || '删除失败')
  }
}

// 添加路径（使用文件夹选择对话框）
async function handleAddPath(type: 'whitelist' | 'blacklist') {
  try {
    const result = await selectDirectory()
    if (result.cancelled || !result.path) {
      return
    }
    if (result.error) {
      alert(result.error)
      return
    }
    const res = await apiAddPathPermission(result.path, type)
    if (res.success) {
      await loadPathPermissions()
    } else {
      alert(res.error || '添加失败')
    }
  } catch (e: any) {
    alert(e.message || '添加失败')
  }
}

// ---------- 网络代理 ----------
const networkConfig = ref<NetworkConfig>({
  enabled: false,
  proxy_url: 'http://127.0.0.1:7890',
  proxy_domains: [],
  proxy_commands: [],
  command_proxy: true,
})
const networkDomainInput = ref('')
const networkCommandInput = ref('')
const networkSaving = ref(false)
const networkTesting = ref(false)
const networkTestResult = ref<{ success: boolean; error?: string } | null>(null)

async function loadNetworkConfig() {
  try {
    const data = await getNetworkConfig()
    networkConfig.value = {
      enabled: data.enabled ?? false,
      proxy_url: data.proxy_url || 'http://127.0.0.1:7890',
      proxy_domains: data.proxy_domains || [],
      proxy_commands: data.proxy_commands || [],
      command_proxy: data.command_proxy ?? true,
    }
    networkTestResult.value = null
  } catch (e) {
    console.error('加载网络配置失败', e)
  }
}

function addNetworkDomain() {
  const val = networkDomainInput.value.trim().toLowerCase()
  if (!val) return
  if (networkConfig.value.proxy_domains.includes(val)) {
    networkDomainInput.value = ''
    return
  }
  networkConfig.value.proxy_domains.push(val)
  networkDomainInput.value = ''
}

function removeNetworkDomain(idx: number) {
  networkConfig.value.proxy_domains.splice(idx, 1)
}

function addNetworkCommand() {
  const val = networkCommandInput.value.trim()
  if (!val) return
  if (networkConfig.value.proxy_commands.includes(val)) {
    networkCommandInput.value = ''
    return
  }
  networkConfig.value.proxy_commands.push(val)
  networkCommandInput.value = ''
}

function removeNetworkCommand(idx: number) {
  networkConfig.value.proxy_commands.splice(idx, 1)
}

async function handleSaveNetwork() {
  networkSaving.value = true
  try {
    await saveNetworkConfig({ ...networkConfig.value })
  } catch (e: any) {
    alert(e.message || '保存失败')
  } finally {
    networkSaving.value = false
  }
}

async function handleTestProxy() {
  networkTesting.value = true
  networkTestResult.value = null
  // 先保存当前配置，确保后端用最新的 proxy_url 测试
  try {
    await saveNetworkConfig({ ...networkConfig.value })
    const res = await testNetworkProxy()
    networkTestResult.value = { success: res.success, error: res.error }
  } catch (e: any) {
    networkTestResult.value = { success: false, error: e.message || '测试失败' }
  } finally {
    networkTesting.value = false
  }
}

// ---------- 桌面宠物 ----------
const petsList = ref<PetInfo[]>([])
const petsLoading = ref(false)

async function loadPets() {
  petsLoading.value = true
  try {
    const res = await listPets()
    petsList.value = res.pets || []
  } catch (e) {
    console.error('加载宠物列表失败', e)
    petsList.value = []
  } finally {
    petsLoading.value = false
  }
}

function getPetFullUrl(url: string): string {
  return `${useModelStore().getBaseUrl()}${url}`
}

function getPetPreviewStyle(pet: PetInfo): Record<string, string> {
  // 用 idle 行第 0 帧作为缩略图：通过 background-position/size 截取
  const cols = pet.columns || 8
  const rows = pet.rows || 9
  const idle = pet.states?.find(s => s.name === 'idle')
  const row = idle?.row ?? 0
  const url = pet.spritesheetUrl || pet.previewUrl
  if (!url) return {}
  const xPct = 0
  const yPct = rows > 1 ? (row / (rows - 1)) * 100 : 0
  return {
    backgroundImage: `url("${getPetFullUrl(url)}")`,
    backgroundSize: `${cols * 100}% ${rows * 100}%`,
    backgroundPosition: `${xPct}% ${yPct}%`,
    backgroundRepeat: 'no-repeat',
    imageRendering: 'pixelated',
  }
}

async function openPetsFolder() {
  try {
    const res = await fetch(`${useModelStore().getBaseUrl()}/files/open-in-editor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 后端 _normalize_work_dir 会解析 ~，传相对路径让它落到 ~/.Aries/pets
      body: JSON.stringify({ work_dir: '~/.Aries/pets', editor: 'explorer' }),
    })
    const data = await res.json()
    if (data.error) {
      window.dispatchEvent(new CustomEvent('aries:toast', {
        detail: { message: data.error, type: 'error' },
      }))
    }
  } catch (e: any) {
    window.dispatchEvent(new CustomEvent('aries:toast', {
      detail: { message: e?.message || '打开文件夹失败', type: 'error' },
    }))
  }
}

function showPetOnDesktop(pet: PetInfo) {
  const spriteRel = pet.spritesheetUrl || pet.animations?.idle
  if (!spriteRel) return
  // 用 JSON 反复解包，确保传入 IPC 的是纯 plain object（避免 Vue Proxy 不可克隆）
  const spec = JSON.parse(JSON.stringify({
    url: getPetFullUrl(spriteRel),
    name: pet.displayName || pet.name,
    frameWidth: pet.frameWidth || 192,
    frameHeight: pet.frameHeight || 208,
    columns: pet.columns || 8,
    rows: pet.rows || 9,
    states: pet.states || undefined,
  }))
  window.electronAPI?.showPet(spec)
  localStorage.setItem('pet:active', JSON.stringify(spec))
  localStorage.setItem('pet:enabled', '1')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-container {
  display: flex;
  width: min(1080px, 92vw);
  height: min(720px, 86vh);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

/* 左侧导航 */
.modal-nav {
  width: 180px;
  min-width: 180px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 0;
}

.modal-nav-header {
  padding: 0 20px 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.modal-nav-header h1 {
  font-size: 18px;
  font-weight: 600;
}

.modal-nav-list {
  list-style: none;
  margin: 0;
  padding: 4px 8px;
}

.modal-nav-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.modal-nav-list li:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.modal-nav-list li.active {
  background: var(--accent-active);
  color: var(--text);
  font-weight: 500;
}

.modal-nav-list li svg {
  flex-shrink: 0;
}

/* 右侧内容 */
.modal-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.modal-body-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 16px;
  flex-shrink: 0;
}

.modal-body-header h2 {
  font-size: 18px;
  font-weight: 600;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.modal-body-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 24px 24px;
}

/* 通用 */
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.section-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border-strong, #ddd);
  border-radius: 6px;
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.icon-btn:hover:not(:disabled) {
  background: var(--accent-hover, #f3f3f3);
  color: var(--text, #222);
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.icon-btn .spin {
  animation: icon-btn-spin 0.9s linear infinite;
  transform-origin: center;
}

@keyframes icon-btn-spin {
  to { transform: rotate(360deg); }
}

.secondary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.secondary-btn:hover {
  background: var(--accent-hover);
  border-color: var(--border);
}

/* 模型列表 */
.model-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.15s;
}

.model-item:hover {
  border-color: var(--border-strong);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.model-item.active {
  border-color: #2d7a4f;
  background: #f8fdfb;
}

.model-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.model-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: #e8f5ee;
  color: #2d7a4f;
  border-radius: 4px;
  font-weight: 500;
}

.model-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.icon-btn-sm {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.icon-btn-sm:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.icon-btn-sm.delete:hover {
  background: #fee2e2;
  color: #991b1b;
}

/* 账号绑定 */
.account-bind-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.account-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.account-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.account-icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.account-icon.feishu,
.account-icon.qq,
.account-icon.wechat { }

.account-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.account-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.account-status {
  font-size: 12px;
  color: var(--text-muted);
}

.account-status.bound { color: #2d7a4f; }

.bind-btn {
  padding: 6px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.bind-btn:hover { background: var(--accent-hover); }
.bind-btn.bound { background: #e8f5ee; border-color: #b8dfc8; color: #2d7a4f; }
.bind-btn.disabled { opacity: 0.4; cursor: not-allowed; }

.account-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.unbind-btn {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.unbind-btn:hover {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #991b1b;
}

/* 配置面板 */
.config-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-panel-header h3 {
  font-size: 15px;
  font-weight: 600;
}

.back-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.back-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.form-input {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.form-input:focus {
  border-color: var(--border-strong);
}

.form-submit-btn {
  padding: 8px 16px;
  background: #2d7a4f;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
  margin-top: 4px;
}

.form-submit-btn:hover { opacity: 0.9; }
.form-submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 二维码区域 */
.qrcode-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
}

.qrcode-img {
  width: 180px;
  height: 180px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.qrcode-tip {
  font-size: 13px;
  color: var(--text-secondary);
}

.qrcode-tip {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 删除确认弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-dialog {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 320px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.modal-header {
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 500;
  color: var(--text);
  border-bottom: 1px solid var(--border);
}

.modal-body {
  padding: 20px;
  color: var(--text);
}

.modal-body p {
  margin: 0;
  line-height: 1.5;
}

.modal-footer {
  padding: 12px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--border);
}

.modal-btn {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: opacity 0.2s;
}

.modal-btn:hover {
  opacity: 0.85;
}

.modal-btn-cancel {
  background: #e5e7eb;
  color: #374151;
}

.modal-btn-danger {
  background: #1f2937;
  color: #ffffff;
}

/* 路径权限 */
.path-section {
  margin-bottom: 16px;
}

.path-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.path-section-header h4 {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.add-path-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s;
}

.add-path-btn:hover {
  background: var(--accent-hover);
}

.add-path-btn.danger {
  border-color: #ef4444;
  color: #ef4444;
}

.add-path-btn.danger:hover {
  background: #fef2f2;
}

.path-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.path-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.path-item.danger {
  border-color: #fca5a5;
  background: #fef2f2;
}

.path-value {
  flex: 1;
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-path-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s, color 0.15s;
}

.remove-path-btn:hover {
  background: var(--accent-hover);
  color: #ef4444;
}

.path-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 12px;
}

/* 桌面宠物 */
.pet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.pet-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.pet-card:hover {
  border-color: var(--accent, #3b82f6);
  background: var(--accent-hover, rgba(59, 130, 246, 0.08));
}

.pet-card.selected {
  border-color: var(--accent, #3b82f6);
  background: var(--accent-hover, rgba(59, 130, 246, 0.12));
}

.pet-preview {
  width: 96px;
  height: 104px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 6px;
  overflow: hidden;
}

.pet-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.pet-preview-sprite {
  width: 100%;
  height: 100%;
}

.pet-name {
  font-size: 12px;
  color: var(--text);
  text-align: center;
  word-break: break-all;
  line-height: 1.3;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pet-animations {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  width: 100%;
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.pet-anim-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.pet-anim-item img {
  width: 48px;
  height: 52px;
  object-fit: contain;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 4px;
}

.pet-anim-item span {
  font-size: 10px;
  color: var(--text-muted);
  text-align: center;
}

/* 网络代理 */
.network-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.network-toggle-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.network-toggle-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.network-toggle-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.network-switch {
  position: relative;
  width: 40px;
  height: 22px;
  border: none;
  border-radius: 11px;
  background: var(--border-strong);
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
}

.network-switch.on {
  background: var(--send-bg);
}

.network-switch:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.network-switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.network-switch.on .network-switch-knob {
  transform: translateX(18px);
}

.network-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.network-field-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: -2px;
}

.network-tag-input {
  display: flex;
  gap: 8px;
}

.network-tag-input-field {
  flex: 1;
}

.network-tag-add-btn {
  padding: 8px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.network-tag-add-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.network-tag-add-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.network-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 28px;
}

.network-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text);
}

.network-tag-remove {
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0;
  display: flex;
  align-items: center;
}

.network-tag-remove:hover:not(:disabled) {
  color: #ef4444;
}

.network-tag-remove:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.network-tag-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
}

.network-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.network-test-btn {
  padding: 8px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.network-test-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.network-test-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.network-test-result {
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}

.network-test-result.success {
  background: rgba(45, 122, 79, 0.1);
  color: #2d7a4f;
}

.network-test-result.fail {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}
</style>
