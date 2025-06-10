import { ref } from "vue";
import { defineStore } from "pinia";
import type { AIMessage, History, UserMessage } from "@/common/interfaces";

export const useHistoryStore = defineStore(
  "history",
  () => {
    const histories = ref<History[]>([]);

    // 添加一整条消息
    const addUserMessage = (id: string, message: UserMessage) => {
      const history = histories.value.find((h) => h.id === id);
      if (history) history.messages.push(message);
    };
    // 流式添加AI回复消息
    const addAiMessageChunk = (id: string, step: number, content: string) => {
      const history = histories.value.find((h) => h.id === id);
      if (history == null) return;
      // 强制将最后一条消息转换为 AIMessage 类型
      let lastMes = history.messages[history.messages.length - 1];
      if (lastMes == null) return;
      // 如果最后一条消息是UserMessage类型，或者不是AIMessage类型，那么添加一条AIMessage类型的消息
      if (lastMes.role !== "ai" && step == 1) {
        const newAIMessage: AIMessage = {
          role: "ai",
          content: content,
          sendTime: new Date().toDateString(),
          step_1_content: content,
          step_2_content: "",
          step_3_content: "",
          step_4_content: "",
          step_5_content: "",
          step_6_content: "",
          step_7_content: "",
          step_8_content: "",
          step_9_content: "",
        };
        history.messages.push(newAIMessage);
        lastMes = newAIMessage;
      }
      // 确保lastMes是AIMessage类型再进行操作
      const aiMessage = lastMes as AIMessage;
      aiMessage.content += content;
      type StepKey = `step_${1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9}_content`;
      const stepKey: StepKey = `step_${step}_content` as StepKey;
      if (Object.prototype.hasOwnProperty.call(aiMessage, stepKey)) aiMessage[stepKey] += content;
    };
    // 添加历史记录
    const addHistory = (history: History) => histories.value.unshift(history);
    // 移除历史消息
    const removeHistory = (id: string | null) =>
      (histories.value = histories.value.filter((h) => h.id !== id));
    // 移除历史消息中的部分消息
    const removeMessages = (id: string | null, messageIndex: number) => {
      const history = histories.value.find((h) => h.id === id);
      if (history) history.messages.splice(messageIndex);
    };
    // 加载历史记录
    const loadHistories = (): History[] => histories.value;

    return {
      histories,
      addUserMessage,
      addAiMessageChunk,
      addHistory,
      removeHistory,
      removeMessages,
      loadHistories,
    };
  },
  {
    persist: {},
  }
);
