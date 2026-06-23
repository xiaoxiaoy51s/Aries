import { LogLevel } from '../types.js';
export declare function emit(level: LogLevel, prefix: string, message: string): void;
export declare class Logger {
    private level;
    private prefix;
    constructor(level?: LogLevel, prefix?: string | null);
    withPrefix(prefix: string): Logger;
    trace(message: string): void;
    debug(message: string): void;
    info(message: string): void;
    warn(message: string): void;
    error(message: string): void;
    critical(message: string): void;
    private log;
    result(message: string): void;
}
//# sourceMappingURL=Logger.d.ts.map