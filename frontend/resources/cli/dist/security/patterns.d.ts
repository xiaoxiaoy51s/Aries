import type { DangerCheck } from '../types.js';
/** 检查命令是否被阻止 */
export declare function isBlocked(command: string): {
    blocked: boolean;
    reason?: string;
};
/** 检查命令是否危险 */
export declare function checkDangerous(command: string): DangerCheck;
/** 检查工作目录是否越界 */
export declare function isOutOfBounds(targetDir: string, allowedDir: string, userHomeDir: string): boolean;
//# sourceMappingURL=patterns.d.ts.map