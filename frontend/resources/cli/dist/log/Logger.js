// VS Code CLI 风格日志系统（对齐 cli/src/log.rs）
import { LogLevel } from '../types.js';
const COLORS_ENABLED = true;
function formatTime() {
    const now = new Date();
    return now.toISOString().replace('T', ' ').slice(0, 19);
}
export function emit(level, prefix, message) {
    const time = formatTime();
    const levelName = LogLevel[level].padEnd(8);
    let colorCode = '';
    let resetCode = '';
    if (COLORS_ENABLED) {
        switch (level) {
            case LogLevel.Trace:
                colorCode = '\x1b[90m';
                break; // gray
            case LogLevel.Debug:
                colorCode = '\x1b[36m';
                break; // cyan
            case LogLevel.Info:
                colorCode = '\x1b[35m';
                break; // magenta
            case LogLevel.Warn:
                colorCode = '\x1b[33m';
                break; // yellow
            case LogLevel.Error:
                colorCode = '\x1b[31m';
                break; // red
            case LogLevel.Critical:
                colorCode = '\x1b[31m\x1b[1m';
                break; // bold red
        }
        resetCode = '\x1b[0m';
    }
    const prefixStr = prefix ? `[${prefix}] ` : '';
    console.error(`${colorCode}${time} ${levelName} ${prefixStr}${message}${resetCode}`);
}
export class Logger {
    level;
    prefix;
    constructor(level = LogLevel.Info, prefix = null) {
        this.level = level;
        this.prefix = prefix;
    }
    withPrefix(prefix) {
        return new Logger(this.level, prefix);
    }
    trace(message) { this.log(LogLevel.Trace, message); }
    debug(message) { this.log(LogLevel.Debug, message); }
    info(message) { this.log(LogLevel.Info, message); }
    warn(message) { this.log(LogLevel.Warn, message); }
    error(message) { this.log(LogLevel.Error, message); }
    critical(message) { this.log(LogLevel.Critical, message); }
    log(level, message) {
        if (level < this.level)
            return;
        emit(level, this.prefix ?? '', message);
    }
    result(message) {
        console.log(message);
    }
}
//# sourceMappingURL=Logger.js.map