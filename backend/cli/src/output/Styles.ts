// VS Code CLI 风格输出样式（对齐 cli/src/commands/output.rs）
// 使用 chalk 实现 console crate 的同等效果
import chalk from 'chalk'

export const title       = chalk.bold
export const label       = chalk.dim
export const uri         = chalk.cyan
export const success     = chalk.green.bold
export const warning     = chalk.yellow.bold
export const error       = chalk.red.bold
export const muted       = chalk.dim

/** 打印 Banner 头部（对齐 print_banner_header） */
export function printBannerHeader(titleText: string, elapsedMs: number): void {
  console.log()
  console.log(`  ${chalk.cyan.bold(titleText)}  ${chalk.dim(`ready in ${elapsedMs}ms`)}`)
  console.log()
}

/** 打印 Banner 行（对齐 print_banner_line） */
export function printBannerLine(labelText: string, value: string): void {
  console.log(
    `  ${chalk.green.bold('➜')}  ${chalk.bold(labelText.padEnd(12))} ${chalk.cyan(value)}`
  )
}

/** 打印 Banner 尾部 */
export function printBannerFooter(): void {
  console.log()
}

/** 打印网络监听地址（对齐 print_network_lines） */
export function printNetworkLines(port: number, host: string, tokenSuffix: string = ''): void {
  printBannerLine('Local', `http://localhost:${port}${tokenSuffix}`)
  if (host === '0.0.0.0') {
    // 枚举网络接口
    const os = require('os')
    const ifaces = os.networkInterfaces()
    for (const name of Object.keys(ifaces)) {
      for (const iface of ifaces[name] ?? []) {
        if (iface.family === 'IPv4' && !iface.internal) {
          printBannerLine('Network', `http://${iface.address}:${port}${tokenSuffix}`)
        }
      }
    }
  }
}