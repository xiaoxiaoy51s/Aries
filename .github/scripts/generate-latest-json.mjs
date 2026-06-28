#!/usr/bin/env node
/**
 * 根据 electron-builder 产物生成 latest.json（供客户端检测更新）。
 * 用法: node .github/scripts/generate-latest-json.mjs <version> [releaseDir]
 */
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'

const version = process.argv[2]
const releaseDir = process.argv[3] || 'frontend/release'
const repo = process.env.GITHUB_REPOSITORY || 'xiaoxiaoy51s/Aries'

if (!version) {
  console.error('Usage: node generate-latest-json.mjs <version> [releaseDir]')
  process.exit(1)
}

if (!fs.existsSync(releaseDir)) {
  console.error(`Release dir not found: ${releaseDir}`)
  process.exit(1)
}

const files = fs.readdirSync(releaseDir)
const setupExe = files.find((f) => /setup.*\.exe$/i.test(f) && !f.includes('blockmap'))
const portable7z = files.find((f) => /\.7z$/i.test(f) && !f.includes('blockmap'))

function fileInfo(filename) {
  const full = path.join(releaseDir, filename)
  const buf = fs.readFileSync(full)
  const sha256 = crypto.createHash('sha256').update(buf).digest('hex')
  const stat = fs.statSync(full)
  const tag = version.startsWith('v') ? version : `v${version}`
  const encoded = encodeURIComponent(filename)
  return {
    filename,
    url: `https://github.com/${repo}/releases/download/${tag}/${encoded}`,
    sha256,
    size: stat.size,
  }
}

const payload = {
  version: version.replace(/^v/, ''),
  releaseDate: new Date().toISOString().slice(0, 10),
  notes: `https://github.com/${repo}/releases/tag/v${version.replace(/^v/, '')}`,
  mandatory: false,
  platforms: {},
}

if (setupExe) {
  payload.platforms.win32 = fileInfo(setupExe)
}
if (portable7z) {
  payload.platforms.win32_7z = fileInfo(portable7z)
}

const outPath = path.join(releaseDir, 'latest.json')
fs.writeFileSync(outPath, JSON.stringify(payload, null, 2) + '\n', 'utf8')
console.log('Wrote', outPath)
