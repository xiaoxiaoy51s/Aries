/**
 * 文件图标工具：基于扩展名匹配 VSCode Icons 风格 SVG。
 * 图标资源位于 src/assets/public/file-icons/，通过 import.meta.glob 预加载为 URL。
 */

const iconModules = import.meta.glob('../assets/public/file-icons/*.svg', {
  eager: true,
  as: 'url',
})

/** 扩展名 -> 图标文件名映射 */
const EXT_ICON_MAP = {
  js: 'file_type_js',
  mjs: 'file_type_js',
  cjs: 'file_type_js',
  ts: 'file_type_typescript',
  tsx: 'file_type_typescript',
  jsx: 'file_type_js',
  vue: 'file_type_vue',
  html: 'file_type_html',
  htm: 'file_type_html',
  css: 'file_type_css',
  scss: 'file_type_scss',
  less: 'file_type_css',
  json: 'file_type_json',
  json5: 'file_type_json',
  jsonc: 'file_type_json',
  md: 'file_type_markdown',
  markdown: 'file_type_markdown',
  py: 'file_type_python',
  go: 'file_type_go',
  rs: 'file_type_rust',
  java: 'file_type_java',
  c: 'file_type_c',
  h: 'file_type_c',
  cpp: 'file_type_cpp',
  cxx: 'file_type_cpp',
  hpp: 'file_type_cpp',
  cc: 'file_type_cpp',
  sh: 'file_type_shell',
  bash: 'file_type_shell',
  zsh: 'file_type_shell',
  yml: 'file_type_yaml',
  yaml: 'file_type_yaml',
  xml: 'file_type_xml',
  sql: 'file_type_sql',
  toml: 'file_type_toml',
  ini: 'file_type_ini',
  cfg: 'file_type_ini',
  conf: 'file_type_ini',
  env: 'file_type_dotenv',
  pdf: 'file_type_pdf',
  zip: 'file_type_zip',
  tar: 'file_type_zip',
  gz: 'file_type_zip',
  rar: 'file_type_zip',
  '7z': 'file_type_zip',
  svg: 'file_type_svg',
  png: 'file_type_image',
  jpg: 'file_type_image',
  jpeg: 'file_type_image',
  gif: 'file_type_image',
  webp: 'file_type_image',
  bmp: 'file_type_image',
  ico: 'file_type_image',
  doc: 'file_type_word',
  docx: 'file_type_word',
  xls: 'file_type_excel',
  xlsx: 'file_type_excel',
  ppt: 'file_type_powerpoint',
  pptx: 'file_type_powerpoint',
  dockerfile: 'file_type_docker',
  gitignore: 'file_type_git',
  gitattributes: 'file_type_git',
}

/** 特殊文件名 -> 图标文件名映射 */
const NAME_ICON_MAP = {
  dockerfile: 'file_type_docker',
  '.gitignore': 'file_type_git',
  '.gitattributes': 'file_type_git',
  'package.json': 'file_type_json',
  'tsconfig.json': 'file_type_json',
  'vite.config.js': 'file_type_js',
  'vite.config.ts': 'file_type_typescript',
}

const DEFAULT_FILE_ICON = 'default_file.svg'
const DEFAULT_FOLDER_ICON = 'default_folder.svg'

function resolveIcon(iconName) {
  const key = `../assets/public/file-icons/${iconName}.svg`
  return iconModules[key] || iconModules[`../assets/public/file-icons/${DEFAULT_FILE_ICON}`] || ''
}

/**
 * 根据文件名返回对应图标的 URL。
 * @param {string} name 文件名
 * @returns {string} 图标 URL
 */
export function getFileIconUrl(name) {
  if (!name) return resolveIcon(DEFAULT_FILE_ICON)

  const lower = name.toLowerCase()

  // 先匹配特殊文件名
  if (NAME_ICON_MAP[lower]) {
    return resolveIcon(NAME_ICON_MAP[lower])
  }

  // 再匹配扩展名
  const dotIdx = lower.lastIndexOf('.')
  if (dotIdx >= 0) {
    const ext = lower.slice(dotIdx + 1)
    if (EXT_ICON_MAP[ext]) {
      return resolveIcon(EXT_ICON_MAP[ext])
    }
  }

  // 无扩展名的特殊文件（如 Dockerfile, Makefile）
  if (NAME_ICON_MAP[lower]) {
    return resolveIcon(NAME_ICON_MAP[lower])
  }

  return resolveIcon(DEFAULT_FILE_ICON)
}

/**
 * 返回文件夹图标 URL。
 * @param {boolean} opened 是否展开
 * @returns {string}
 */
export function getFolderIconUrl(opened = false) {
  const iconName = opened ? 'default_folder_opened' : 'default_folder'
  return iconModules[`../assets/public/file-icons/${iconName}.svg`] || ''
}
