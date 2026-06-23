/** 日志级别（对齐 VS Code log::Level） */
export declare enum LogLevel {
    Trace = 0,
    Debug = 1,
    Info = 2,
    Warn = 3,
    Error = 4,
    Critical = 5,
    Off = 6
}
/** 命令执行结果（对齐 VS Code ExecuteResult） */
export interface ExecuteResult {
    success: boolean;
    return_code: number;
    output: string;
    captured_output?: string;
    error?: string;
    command: string;
    working_dir: string;
    requires_confirmation?: boolean;
    danger_types?: string[];
    danger_info?: string;
    interrupted?: boolean;
    timed_out?: boolean;
    session_id?: string;
    pid?: number;
    auto_detached?: boolean;
}
/** 终端会话信息 */
export interface TerminalSession {
    id: string;
    workDir: string;
    pid: number | null;
    alive: boolean;
    createdAt: number;
    shellKind: string;
}
/** 命令执行请求 */
export interface ExecuteRequest {
    command: string;
    working_dir?: string;
    timeout?: number;
    skip_confirmation?: boolean;
    invocation_id?: string;
    new_terminal?: boolean;
}
/** 危险命令检测结果 */
export interface DangerCheck {
    dangerous: boolean;
    danger_types: string[];
    danger_info: string;
}
/**
 * WebSocket 消息类型
 * - output: 后端 → 前端，终端输出数据
 * - ready:  后端 → 前端，终端已就绪
 * - done:   后端 → 前端，命令执行完成
 * - error:  后端 → 前端，错误信息
 * - closed: 后端 → 前端，终端已关闭
 * - ping/pong: 心跳
 * - input:  前端 → 后端，用户输入
 * - attach: 前端 → 后端，请求附加到终端
 * - resize: 前端 → 后端，调整终端大小
 */
export type WsMessageType = 'output' | 'ready' | 'done' | 'error' | 'closed' | 'ping' | 'pong' | 'input' | 'attach' | 'resize';
/** WebSocket 消息 */
export interface WsMessage {
    type: WsMessageType;
    data?: string;
    session_id?: string;
    error?: string;
    rows?: number;
    cols?: number;
    reset?: boolean;
    replay?: boolean;
    shell?: string;
}
/** 服务配置 */
export interface CliServerConfig {
    host: string;
    port: number;
    allowedDir: string;
    logLevel: LogLevel;
}
//# sourceMappingURL=types.d.ts.map