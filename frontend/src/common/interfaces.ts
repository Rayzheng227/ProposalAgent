// 导航栏项
interface History {
  id: string;
  title: string;
  messages: (BaseMessage | AIAnswerMessage | AIQuestionMessage)[];
}

// 基础消息
interface BaseMessage {
  sendTime: string;
  role: string;
  content: string;
}

interface AIQuestionMessage extends BaseMessage {
  isAnswer: boolean;
  isFinish: boolean;
}

interface Step {
  title: string;
  content: string;
}

interface AIAnswerMessage extends BaseMessage {
  isAnswer: boolean;
  isFinish: boolean;
  steps: Step[];
}

// 统一返回类
interface R {
  code: number;
  mes: string;
  data: any;
}

export type { History, BaseMessage, AIAnswerMessage, AIQuestionMessage, Step, R };
interface BaseMessage {
  sendTime: string;
  role: string;
  content: string;
}
