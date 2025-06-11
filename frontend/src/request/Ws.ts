/**
 * WebSocket 连接工具类，支持自动重连、心跳检测等功能
 */
export default class WebSocketUtil {
  // WebSocket 实例
  private ws: WebSocket | null = null;
  // 连接状态
  private isConnected = false;
  // 重连计时器
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  // 心跳计时器
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  // 配置选项
  private options: WebSocketOptions;

  constructor(options: WebSocketOptions) {
    this.options = {
      protocols: [],
      autoReconnect: true,
      reconnectInterval: 3000,
      heartbeatInterval: 120000,
      heartbeatMsg: "ping",
      ...options,
    };
    this.init();
  }

  /**
   * 初始化 WebSocket 连接
   */
  private init(): void {
    try {
      this.ws = this.options.protocols?.length
        ? new WebSocket(this.options.url, this.options.protocols)
        : new WebSocket(this.options.url);

      this.setupEventListeners();
    } catch (error) {
      console.error("WebSocket 初始化失败:", error);
      this.reconnect();
    }
  }

  /**
   * 设置 WebSocket 事件监听器
   */
  private setupEventListeners(): void {
    if (!this.ws) return;

    this.ws.onopen = (event) => {
      this.isConnected = true;
      console.log("WebSocket 连接成功");
      this.options.onOpen?.(event);
      this.startHeartbeat();

      // 清除重连计时器
      this.clearReconnectTimer();
    };

    this.ws.onmessage = (event) => {
      this.options.onMessage?.(event);
      // 如果接收到 pong 消息，重置心跳检测
      if (event.data === "pong") {
        this.resetHeartbeat();
      }
    };

    this.ws.onclose = (event) => {
      this.isConnected = false;
      console.log("WebSocket 连接关闭:", event);
      this.options.onClose?.(event);
      this.stopHeartbeat();

      // 自动重连
      if (this.options.autoReconnect) {
        this.reconnect();
      }
    };

    this.ws.onerror = (event) => {
      console.error("WebSocket 发生错误:", event);
      this.options.onError?.(event);
    };
  }

  /**
   * 开始心跳检测
   */
  private startHeartbeat(): void {
    if (!this.options.heartbeatInterval || this.heartbeatTimer) return;

    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected && this.ws?.readyState === WebSocket.OPEN) {
        this.send(this.options.heartbeatMsg!);
      }
    }, this.options.heartbeatInterval);
  }

  /**
   * 停止心跳检测
   */
  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /**
   * 重置心跳计时器
   */
  private resetHeartbeat(): void {
    this.stopHeartbeat();
    this.startHeartbeat();
  }

  /**
   * 尝试重连
   */
  private reconnect(): void {
    if (this.reconnectTimer || !this.options.autoReconnect) return;

    this.reconnectTimer = setTimeout(() => {
      console.log("尝试重连 WebSocket...");
      this.init();
    }, this.options.reconnectInterval);
  }

  /**
   * 清除重连计时器
   */
  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  /**
   * 发送消息
   * @param data 要发送的数据
   */
  public send(data: string | ArrayBuffer | Blob | ArrayBufferView): void {
    if (!this.isConnected || this.ws?.readyState !== WebSocket.OPEN) {
      console.error("WebSocket 未连接，无法发送消息");
      return;
    }

    try {
      this.ws.send(data);
    } catch (error) {
      console.error("发送消息失败:", error);
    }
  }

  /**
   * 关闭 WebSocket 连接
   * @param code 关闭代码
   * @param reason 关闭原因
   */
  public close(code?: number, reason?: string): void {
    // 手动关闭时禁用自动重连
    this.options.autoReconnect = false;
    this.clearReconnectTimer();
    this.stopHeartbeat();

    if (this.ws?.readyState !== WebSocket.CLOSED && this.ws?.readyState !== WebSocket.CLOSING) {
      this.ws?.close(code, reason);
    }
  }

  /**
   * 获取当前连接状态
   */
  public getState(): WebSocketState {
    return {
      isConnected: this.isConnected,
      readyState: this.ws?.readyState ?? WebSocket.CLOSED,
    };
  }
}

/**
 * WebSocket 配置选项接口
 */
export interface WebSocketOptions {
  // WebSocket 连接地址
  url: string;
  // 子协议数组
  protocols?: string | string[];
  // 是否自动重连
  autoReconnect?: boolean;
  // 重连间隔时间（毫秒）
  reconnectInterval?: number;
  // 心跳检测间隔时间（毫秒）
  heartbeatInterval?: number;
  // 心跳消息内容
  heartbeatMsg?: string;
  // 连接成功回调
  onOpen?: (event: Event) => void;
  // 接收到消息回调
  onMessage?: (event: MessageEvent) => void;
  // 连接关闭回调
  onClose?: (event: CloseEvent) => void;
  // 发生错误回调
  onError?: (event: Event) => void;
}

/**
 * WebSocket 状态接口
 */
export interface WebSocketState {
  // 是否已连接
  isConnected: boolean;
  // 当前连接状态码
  readyState: number;
}
