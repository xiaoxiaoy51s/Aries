export declare const title: import("chalk").ChalkInstance;
export declare const label: import("chalk").ChalkInstance;
export declare const uri: import("chalk").ChalkInstance;
export declare const success: import("chalk").ChalkInstance;
export declare const warning: import("chalk").ChalkInstance;
export declare const error: import("chalk").ChalkInstance;
export declare const muted: import("chalk").ChalkInstance;
/** 打印 Banner 头部（对齐 print_banner_header） */
export declare function printBannerHeader(titleText: string, elapsedMs: number): void;
/** 打印 Banner 行（对齐 print_banner_line） */
export declare function printBannerLine(labelText: string, value: string): void;
/** 打印 Banner 尾部 */
export declare function printBannerFooter(): void;
/** 打印网络监听地址（对齐 print_network_lines） */
export declare function printNetworkLines(port: number, host: string, tokenSuffix?: string): void;
//# sourceMappingURL=Styles.d.ts.map