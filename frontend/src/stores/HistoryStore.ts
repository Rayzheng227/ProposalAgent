import { ref } from "vue";
import { defineStore } from "pinia";
import type { AIAnswerMessage, AIQuestionMessage, History, BaseMessage } from "@/common/interfaces";

export const useHistoryStore = defineStore(
  "history",
  () => {
    const histories = ref<History[]>([]);

    // 添加一整条消息
    const addBaseMessage = (id: string, message: BaseMessage) => {
      const history = histories.value.find((h) => h.id === id);
      if (history) history.messages.push(message);
    };

    // 流式添加AI询问消息
    const addAIQuestionMessageChunk = (id: string, isFinish: boolean, content: string) => {
      const history = histories.value.find((h) => h.id === id);
      if (history == null) return;
      let lastMes = history.messages[history.messages.length - 1];
      if (lastMes == null) return;
      // 如果最后一条消息是用户消息或者是AI回答消息的话，新建一个AIQuestionMessage
      if (lastMes.role == "user" || ("isAnswer" in lastMes && lastMes.isAnswer)) {
        const newAIQuestionMessage: AIQuestionMessage = {
          role: "ai",
          content: content,
          sendTime: new Date().toDateString(),
          isAnswer: false,
          isFinish: isFinish,
        };
        history.messages.push(newAIQuestionMessage);
        lastMes = newAIQuestionMessage;
      }
      const aiQuestionMessage = lastMes as AIQuestionMessage;
      aiQuestionMessage.content += content;
      aiQuestionMessage.isFinish = isFinish;
    };

    // 流式添加AI回复消息
    const addAIAnswerMessageChunk = (
      id: string,
      isFinish: boolean,
      step: number,
      title: string,
      content: string
    ) => {
      const history = histories.value.find((h) => h.id === id);
      if (history == null) return;
      let lastMes = history.messages[history.messages.length - 1];
      if (lastMes == null) return;
      // 如果最后一条消息是用户消息或者不是AI回答消息的话，新建一个AIAnswerMessage
      if (lastMes.role == "user" || ("isAnswer" in lastMes && !lastMes.isAnswer)) {
        const newAIAnswerMessage: AIAnswerMessage = {
          role: "ai",
          content: content,
          sendTime: new Date().toDateString(),
          isAnswer: true,
          isFinish: false,
          steps: [
            {
              title: title,
              content: content,
            },
          ],
        };
        history.messages.push(newAIAnswerMessage);
        lastMes = newAIAnswerMessage;
      }
      const aiAnswerMessage = lastMes as AIAnswerMessage;
      aiAnswerMessage.content += content;
      const stepsLen = aiAnswerMessage.steps.length;
      // 如果当前步骤数等于已记录步骤数的话，则追加
      if (step == stepsLen) aiAnswerMessage.steps[step - 1].content += content;
      // 反之，说明是新的步骤，新建Step
      else
        aiAnswerMessage.steps.push({
          title: title,
          content: content,
        });
      aiAnswerMessage.isFinish = isFinish;
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
      addBaseMessage,
      addAIQuestionMessageChunk,
      addAIAnswerMessageChunk,
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
