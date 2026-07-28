import { ref } from 'vue'

const messages = {
  zh: {
    // Sidebar
    'nav.newChat': '新建任务',
    'nav.workspace': '工作台',
    'nav.chat': '对话',
    'nav.agent': '智能体',
    'nav.workflow': '工作流',
    'nav.schedule': '定时任务',
    'nav.resources': '资源',
    'nav.knowledge': '知识库',
    'nav.remote': '远程连接',
    'nav.system': '系统',
    'nav.settings': '设置',
    'nav.taskList': '任务列表',
    'nav.noTasks': '暂无任务',
    'nav.collapse': '收起侧边栏',
    'nav.expand': '展开侧边栏',
    'nav.logout': '退出登录',
    // Settings
    'settings.title': '设置',
    'settings.models': '模型管理',
    'settings.general': '通用设置',
    'settings.language': '语言',
    'settings.theme': '外观',
    'settings.themeLight': '浅色',
    'settings.themeDark': '深色',
    'settings.themeSystem': '跟随系统',
    'settings.addModel': '添加模型',
    'settings.editModel': '编辑模型',
    'settings.modelName': '模型名称',
    'settings.modelNameHint': '给模型起个名字，如「我的GPT」',
    'settings.modelId': '模型ID',
    'settings.modelIdHint': '实际模型名称，如 gpt-4o',
    'settings.apiKey': 'API Key',
    'settings.baseUrl': '接口地址',
    'settings.toolRounds': '工具调用轮次',
    'settings.contextWindow': '最大上下文',
    'settings.active': '激活',
    'settings.save': '保存',
    'settings.cancel': '取消',
    'settings.delete': '删除',
    'settings.deleteConfirm': '确定删除该模型配置吗？',
    'settings.noModels': '暂无模型配置，请点击「添加模型」',
    'settings.membership': { 0: '免费用户', 1: '基础会员', 2: '专业会员' },
    'chat.noModel': '暂无模型',
    'chat.noModelTitle': '当前无可用的模型，请前往设置添加模型',
    'chat.selectModel': '选择模型',
    'chat.modelMenuEmpty': '暂无可用模型',
    'chat.modelMenuAdd': '前往设置添加模型',
    'chat.switchingModel': '切换中…',
    'chat.copy': '复制',
    'chat.copied': '已复制',
    'chat.welcomeSubtitle': '与智能 Agent 对话，处理文档、数据分析、定时任务与外部连接，一站托管你的数字工作。',
    'chat.placeholder': '给 Aries Cloud 发送消息，或选择下方模板开始...',
    'chat.sendPlaceholder': '给 Aries Cloud 发送消息...',
    'chat.tip': 'Aries Cloud 可能会出错，请核查重要信息。输入 Enter 发送，Shift+Enter 换行。',
  },
  en: {
    // Sidebar
    'nav.newChat': 'New Task',
    'nav.workspace': 'Workspace',
    'nav.chat': 'Chat',
    'nav.agent': 'Agent',
    'nav.workflow': 'Workflow',
    'nav.schedule': 'Schedule',
    'nav.resources': 'Resources',
    'nav.knowledge': 'Knowledge',
    'nav.remote': 'Remote',
    'nav.system': 'System',
    'nav.settings': 'Settings',
    'nav.taskList': 'Task List',
    'nav.noTasks': 'No tasks',
    'nav.collapse': 'Collapse sidebar',
    'nav.expand': 'Expand sidebar',
    'nav.logout': 'Logout',
    // Settings
    'settings.title': 'Settings',
    'settings.models': 'Models',
    'settings.general': 'General',
    'settings.language': 'Language',
    'settings.theme': 'Theme',
    'settings.themeLight': 'Light',
    'settings.themeDark': 'Dark',
    'settings.themeSystem': 'System',
    'settings.addModel': 'Add Model',
    'settings.editModel': 'Edit Model',
    'settings.modelName': 'Model Name',
    'settings.modelNameHint': 'A nickname, e.g. "My GPT"',
    'settings.modelId': 'Model ID',
    'settings.modelIdHint': 'Actual model name, e.g. gpt-4o',
    'settings.apiKey': 'API Key',
    'settings.baseUrl': 'Base URL',
    'settings.toolRounds': 'Max Tool Rounds',
    'settings.contextWindow': 'Context Window',
    'settings.active': 'Active',
    'settings.save': 'Save',
    'settings.cancel': 'Cancel',
    'settings.delete': 'Delete',
    'settings.deleteConfirm': 'Are you sure you want to delete this model?',
    'settings.noModels': 'No models configured. Click "Add Model" to start.',
    'settings.membership': { 0: 'Free', 1: 'Basic', 2: 'Pro' },
    'chat.noModel': 'No Model',
    'chat.noModelTitle': 'No model available. Go to Settings to add one.',
    'chat.selectModel': 'Select Model',
    'chat.modelMenuEmpty': 'No models available',
    'chat.modelMenuAdd': 'Go to Settings to add a model',
    'chat.switchingModel': 'Switching…',
    'chat.copy': 'Copy',
    'chat.copied': 'Copied',
    'chat.welcomeSubtitle': 'Chat with intelligent Agents for documents, data analysis, scheduled tasks and external connections—all in one place.',
    'chat.placeholder': 'Message Aries Cloud, or choose a template below...',
    'chat.sendPlaceholder': 'Message Aries Cloud...',
    'chat.tip': 'Aries Cloud may make mistakes. Please verify important information. Press Enter to send, Shift+Enter for new line.',
  },
}

const currentLocale = ref(localStorage.getItem('language') || 'zh')

export function setLocale(locale) {
  currentLocale.value = locale
  localStorage.setItem('language', locale)
}

export function useI18n() {
  function t(key) {
    const dict = messages[currentLocale.value]
    if (!dict) return key
    const val = dict[key]
    if (val === undefined) return key
    return val
  }

  function tm(key) {
    const dict = messages[currentLocale.value]
    return dict?.[key] ?? {}
  }

  return { t, tm, locale: currentLocale }
}
