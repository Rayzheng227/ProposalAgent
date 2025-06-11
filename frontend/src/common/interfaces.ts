// 导航栏项
interface History {
  id: string;
  title: string;
  messages: (UserMessage | AIMessage)[];
}

interface UserMessage {
  sendTime: string;
  role: string;
  content: string;
}

interface AIMessage extends UserMessage {
  step_1_content: string;
  step_2_content: string;
  step_3_content: string;
  step_4_content: string;
  step_5_content: string;
  step_6_content: string;
  step_7_content: string;
  step_8_content: string;
  step_9_content: string;
}

// 统一返回类
interface R {
  code: number;
  mes: string;
  data: any;
}

export type { History, UserMessage, AIMessage, R };
interface UserMessage {
  sendTime: string;
  role: string;
  content: string;
}
