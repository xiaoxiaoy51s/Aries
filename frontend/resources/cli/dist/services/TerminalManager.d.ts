import { Logger } from '../log/Logger.js';
import type { ExecuteResult, TerminalSession } from '../types.js';
export declare class TerminalManager {
    private sessions;
    private logger;
    constructor(logger: Logger);
    /** 获取 shell 路径 */
    private getShell;
    /** 在 PATH 中查找可执行文件 */
    private findInPath;
    /** 是否为长运行命令 */
    isPersistent(command: string): boolean;
    /** 检测是否应自动转入后台 */
    private shouldAutoDetach;
    /** 判断会话是否存在 */
    hasSession(sessionId: string): boolean;
    /** 创建终端会话 */
    createSession(workDir: string, sessionId?: string): string;
    /** 检测 shell 类型 */
    private detectShellKind;
    /** 获取 shell 类型 */
    getShellKind(sessionId: string): string;
    /** 写入数据到终端（用户输入或命令） */
    write(sessionId: string, data: string): void;
    /** 写入命令并回车 */
    writeCommand(sessionId: string, command: string): void;
    /** 发送 Ctrl+C */
    interrupt(sessionId: string): void;
    /** 调整终端大小 */
    resize(sessionId: string, cols: number, rows: number): void;
    /** 重置会话（关闭旧 shell，创建新 shell） */
    resetSession(sessionId: string): void;
    /** 重置 agent 终端 */
    resetAgent(_workDir?: string): void;
    /** 获取终端输出缓冲区 */
    getOutput(sessionId: string): string;
    /** 清除输出缓冲区 */
    clearOutput(sessionId: string): void;
    /** 设置输出回调 */
    onOutput(sessionId: string, callback: (data: string) => void): void;
    /** 移除输出回调 */
    offOutput(sessionId: string, callback?: (data: string) => void): void;
    /** 获取所有会话 */
    getSessions(): TerminalSession[];
    /** 获取单个会话 */
    getSession(sessionId: string): TerminalSession | undefined;
    /** 清理会话 */
    closeSession(sessionId: string): void;
    /** 关闭全部 */
    closeAll(): void;
    /** 通过 invocation_id 手动 detach（用户点击"后台运行"） */
    detachByInvocation(invocationId: string): boolean;
    /** 通过 session_id 手动 detach */
    detachBySession(sessionId: string): boolean;
    /** 核心命令执行（供 AI 调用） */
    execute(command: string, options?: {
        workingDir?: string;
        timeout?: number;
        skipConfirmation?: boolean;
        invocationId?: string;
        sessionId?: string;
        allowedDir?: string;
        userHomeDir?: string;
    }): Promise<ExecuteResult>;
}
//# sourceMappingURL=TerminalManager.d.ts.map