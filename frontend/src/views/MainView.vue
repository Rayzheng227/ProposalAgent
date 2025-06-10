<template>
  <div class="background">
    <div class="bg-name-container">
      <div class="name" v-for="(name, index) in names" :key="index">
        {{ name }}
      </div>
    </div>
    <div class="overlay">
      <div class="main">
        <div class="left-top-hole"></div>
        <div class="right-top-hole"></div>
        <div class="left-bottom-hole"></div>
        <div class="right-bottom-hole"></div>
        <div class="left-menu">
          <div class="menu" :class="{ collapsed: isCollapse }">
            <div class="head">
              <div class="logo-wrapper" :class="{ collapsed: isCollapse }">
                <div class="label">Proposal You</div>
              </div>
              <img class="action" :src="isCollapse ? '/src/assets/imgs/expand.png' : '/src/assets/imgs/collapse.png'"
                @click="toggleCollapse" />
            </div>
            <el-button class="new-dialog" type="default" :class="{ collapsed: isCollapse }" @click="toIsland()">
              <template #icon>
                <img class="icon" :class="{ collapsed: isCollapse }" src="/src/assets/imgs/newDialog.png" />
              </template>
              开启新对话
            </el-button>
            <div class="histories">
              <div v-for="item in histories" class="histories-item" :style="activeHistoryId == item.id
                ? { boxShadow: 'inset -2px -2px 5px 0px #aaa' }
                : {}
                " @click="switchHistory(item.id)">
                <div class="status">
                  <div class="status-ball" :style="{ backgroundColor: activeHistoryId == item.id ? 'green' : 'grey' }">
                  </div>
                </div>
                <div class="summary" :class="{ collapsed: isCollapse }">{{ item.title }}</div>
                <img src="/src/assets/imgs/delete.png" class="delete" @click.stop="removeHistory(item.id)" />
              </div>
            </div>
          </div>
        </div>
        <div class="right" v-loading="isLoading" element-loading-text="正在连接服务器!"
          element-loading-background="rgba(255, 255, 255, 0.05)">
          <div v-if="activeHistoryId != null" class="communication">
            <div class="chat-records" ref="chatRecordsRef">
              <div v-show="rendered"
                v-for="(message, index) in histories.find((item) => item.id === activeHistoryId)?.messages">
                <template v-if="message.role === 'user'">
                  <UserMessagePanel :message="(message as UserMessage)"></UserMessagePanel>
                </template>
                <template v-else>
                  <AiMessagePanel :message="(message as AIMessage)" :index="index" :history-id="activeHistoryId"
                    @refresh="refresh(index)">
                  </AiMessagePanel>
                </template>
              </div>
            </div>
            <el-button class="new-dialog" type="default" :class="{ collapsed: isCollapse }" @click="toIsland()">
              <template #icon>
                <img class="icon" :class="{ collapsed: isCollapse }" src="/src/assets/imgs/newDialog.png" />
              </template>
              开启新对话
            </el-button>
            <QueryInput @send="send"></QueryInput>
          </div>
          <div v-else class="island">
            <div class="head">
              <img src="/src/assets/imgs/logo.png" class="logo" />
              <div class="hello">我是ProposalAgent，很高兴帮你解答问题！</div>
            </div>
            <div class="prompt">我可以帮你生成调研报告、计划书等，请提交你的任务吧！</div>
            <QueryInput @send="send"></QueryInput>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, nextTick, getCurrentInstance, watch } from "vue";
import { ElMessage } from "element-plus";
import type { History, UserMessage, AIMessage, R } from "@/common/interfaces";
import { getRandomId } from "@/utils/stringUtil";
import QueryInput from "@/components/QueryInput.vue";
import UserMessagePanel from "@/components/UserMessagePanel.vue";
import AiMessagePanel from "@/components/AiMessagePanel.vue";
import { useHistoryStore } from "@/stores/HistoryStore";

const instance: any = getCurrentInstance();
const proxy = instance.proxy;
const historyStore = useHistoryStore();
const isCollapse = ref(false);
const rendered = ref(false);
const histories = ref<History[]>([]);
const activeHistoryId = ref<string | null>(null);
const chatRecordsRef = ref<HTMLElement | null>(null);
const isChatting = ref<boolean>(false);
const isUserScrolling = ref(false);
const isLoading = ref(false);
const nameElements = ref<HTMLElement[]>([]);
const names = ref<string[]>(["郑锐", "谢秋云", "樊彬峰", "禚宣伟", "吴页阳"])

const loadHistories = () => {
  histories.value = historyStore.loadHistories();
  if (activeHistoryId.value != null) {
    scrollToBottom();
    return;
  };
  if (histories.value.length > 0) {
    activeHistoryId.value = histories.value[0].id;
    scrollToBottom();
  } else activeHistoryId.value = null;
}

const switchHistory = (id: string) => {
  rendered.value = false; // 切换时先隐藏消息
  activeHistoryId.value = id;
  loadHistories();
}

const toggleCollapse = () => isCollapse.value = !isCollapse.value;

const removeHistory = (id: string) => {
  if (activeHistoryId.value === id)
    activeHistoryId.value = null;
  historyStore.removeHistory(id);
  loadHistories();
}

const toIsland = () => activeHistoryId.value = null;

const send = async (query: string) => {
  // 如果当前正在发送消息，则不允许发送操作
  if (isChatting.value) return;
  // 如果当前是新的对话，则记录到历史记录中
  if (activeHistoryId.value == null) {
    const id = getRandomId();
    const history: History = { id, title: "", messages: [] }
    historyStore.addHistory(history);
    loadHistories()
  }
  // 获取当前的消息记录
  let activeHistory = histories.value.find((item) => item.id === activeHistoryId.value)
  if (activeHistory == null) return;
  // 加载动画
  isLoading.value = true;
  // 构建历史消息
  let realQuery = "";
  activeHistory.messages.forEach((item) => realQuery += item.content);
  realQuery += query;
  // 发起请求
  isChatting.value = true;
  const result = await proxy.Request({
    url: proxy.Api.sendQuery,
    data: {
      query: realQuery,
      historyId: activeHistoryId.value
    },
    errorCallback: (errR: any) => {
      ElMessage.error(errR.mes)
      isLoading.value = false; // 确保错误时关闭加载
      isChatting.value = false;
    }
  });
  if (!result) {
    isLoading.value = false;
    isChatting.value = false;
    return;
  }
  // 如果是第一条消息，则设置标题
  if (activeHistory.title === "")
    activeHistory.title = query.substring(0, 10);
  // 记录消息
  let message: UserMessage = {
    sendTime: new Date().toDateString(),
    role: "user",
    content: query
  }
  historyStore.addUserMessage(activeHistory.id, message);
  loadHistories();

  // WS连接实时接收最新消息，添加到消息列表中
  const ws = new proxy.Ws({
    url: `${proxy.Api.loadMessageStream}/${activeHistoryId.value}`,
    autoReconnect: true,
    onMessage: (r: R) => {
      // 首次接收消息时，关闭加载动画，同时允许自动向下滚动
      if (isLoading.value) {
        isLoading.value = false
        isUserScrolling.value = false;
      }
      const { proposalId, step, content } = JSON.parse(r.data)
      if (step == 0)
        ws.close();
      else {
        historyStore.addAiMessageChunk(proposalId, step, content);
        loadHistories();
      }
    }
  });

  // isUserScrolling.value = false;
  // let i = 0;
  // let step = 1;
  // setTimeout(() => {
  //   setInterval(() => {
  //     if (i == 14) {
  //       i = 0;
  //       step += 1;
  //       if (step == 10) step = 0;
  //     }
  //     isLoading.value = false
  //     const proposalId = activeHistoryId.value!
  //     const content = "这是一个测试消息这是一个测试消息这是一个测试消息\n"
  //     historyStore.addAiMessageChunk(proposalId, step, content);
  //     loadHistories();
  //     if (step == 0) {
  //       isChatting.value = false;
  //       isLoading.value = false;
  //       return;
  //     }
  //     i++;
  //   }, 100);
  // }, 500)
  isChatting.value = false;
}

const refresh = (index: number) => {
  const activeHistory = histories.value.find((item) => item.id === activeHistoryId.value)
  if (activeHistory == null) return;
  const oldQuery = activeHistory.messages[index - 1].content
  historyStore.removeMessages(activeHistoryId.value, index - 1);
  loadHistories();
  send(oldQuery);
}

// 滚动事件处理函数
const handleScroll = () => {
  if (!chatRecordsRef.value) return;
  const element = chatRecordsRef.value;
  const { scrollTop, clientHeight, scrollHeight } = element;
  const threshold = 100;
  // 检测是否滚动到底部（阈值范围内）
  isUserScrolling.value = (scrollHeight - (scrollTop + clientHeight) > threshold);
};

// 滚动到底部并显示消息的方法
const scrollToBottom = () => {
  // 用户手动滚动过则不自动滚动
  if (isUserScrolling.value) return;
  setTimeout(() => {
    rendered.value = true;
    nextTick(() => {
      if (!chatRecordsRef.value) return;
      const element = chatRecordsRef.value;
      element.scrollTop = element.scrollHeight;
    })
  }, 50);

}

// 随机打乱名字顺序，并为每个名字设置随机动画速度
const randomNameElementSpeed = () => {
  const array = [...names.value];
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
  names.value = array;
  nextTick(() => {
    nameElements.value = Array.from(document.querySelectorAll('.name')).map((element) => element as HTMLElement);
    if (nameElements.value.length === 0) return;
    // 为每个名字设置随机动画速度，范围10s-20s
    nameElements.value.forEach(name => {
      const minSpeed = 15; // 最小动画时长
      const maxSpeed = 30; // 最大动画时长
      const randomSpeed = minSpeed + Math.random() * (maxSpeed - minSpeed);
      name.style.animationDuration = `${randomSpeed}s`;
    });
  })
}

// 监听activeHistoryId变化，动态绑定/解绑滚动事件
watch(activeHistoryId, (newVal) => {
  if (newVal !== null) {
    // 进入聊天界面，等待DOM渲染后绑定滚动事件
    nextTick(() => {
      if (chatRecordsRef.value) {
        chatRecordsRef.value.addEventListener('scroll', handleScroll);
      }
    });
  } else {
    if (chatRecordsRef.value)
      chatRecordsRef.value.removeEventListener('scroll', handleScroll);
  }
});

onMounted(() => {
  loadHistories();
  randomNameElementSpeed()
});


</script>

<style lang="scss" scoped>
.background {
  width: 100vw;
  height: 100vh;
  background-color: #000;
  user-select: none;

  .bg-name-container {
    width: 100%;
    height: 100%;
    font-size: 180px;
    font-weight: bold;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    color: #444;
    white-space: nowrap;
    overflow: hidden;
    filter: blur(5px);

    .name {
      animation: scroll linear infinite;
    }
  }

  @keyframes scroll {
    0% {
      transform: translateX(0);
    }

    100% {
      transform: translateX(100%);
    }
  }

  .overlay {
    position: fixed;
    top: 0;
    left: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    height: 100%;
    z-index: 3;
    background-color: rgba(0, 0, 0, 0.7);

    .main {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 97%;
      height: 97%;
      border-width: 2px;
      border-radius: 20px;
      box-shadow: -4px -4px 16px 0px rgba(255, 255, 255, 0.3);

      .left-top-hole {
        position: absolute;
        top: 10px;
        left: 10px;
        width: 30px;
        height: 30px;
        border-radius: 15px;
        opacity: 0.6;
        background-color: red;

        &:hover {
          scale: 1.3;
        }
      }

      .right-top-hole {
        position: absolute;
        top: 10px;
        right: 10px;
        width: 30px;
        height: 30px;
        border-radius: 15px;
        opacity: 1;
        background-color: green;

        &:hover {
          scale: 1.3;
        }
      }

      .left-bottom-hole {
        position: absolute;
        bottom: 10px;
        left: 10px;
        width: 30px;
        height: 30px;
        border-radius: 15px;
        opacity: 1;
        background-color: blue;

        &:hover {
          scale: 1.3;
        }
      }

      .right-bottom-hole {
        position: absolute;
        bottom: 10px;
        right: 10px;
        width: 40px;
        height: 40px;
        border-radius: 20px;
        box-shadow: inset 0px 0px 6px 2px rgba(255, 255, 255, 0.3);

        &:hover {
          scale: 1.3;
        }
      }

      .left-menu {
        display: flex;
        flex-direction: column;
        flex: 1;
        max-width: 250px;
        height: calc(100% - 100px);
        padding-left: 20px;

        .menu {
          display: flex;
          flex-direction: column;
          align-items: center;
          width: 100%;
          height: 100%;
          border-radius: 30px;
          box-shadow: inset -4px -4px 12px 2px rgba(255, 255, 255, 0.3);
          transition: width 0.3s ease;

          &.collapsed {
            width: 80px;
          }

          .head {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 50px;

            .logo-wrapper {
              overflow: hidden;
              transition: width 0.3s ease;
              width: 140px;

              &.collapsed {
                width: 0;
              }
            }

            .label {
              display: inline-block;
              text-align: center;
              font-size: 22px;
              font-weight: bold;
              font-family: "Times New Roman", Times, serif;
              color: skyblue;
              white-space: nowrap;
            }

            .action {
              width: 35px;

              &:hover {
                scale: 1.2;
                cursor: pointer;
              }
            }
          }

          .new-dialog {
            width: 70%;
            height: 50px;
            margin-top: 10px;
            text-align: center;
            font-size: 16px;
            color: #cccccc;
            border-width: 1px;
            border-color: blue;
            border-radius: 15px;
            background-color: #000;
            box-shadow: -1px -1px 4px 0px #aaa;

            &:hover {
              background-color: #333;
              box-shadow: -2px -2px 8px 0px #aaa;
            }

            &.collapsed {
              font-size: 0;
            }

            .icon {
              width: 25px;
              padding-right: 20px;

              &.collapsed {
                padding: 0;
              }
            }
          }

          .histories {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 100%;
            max-height: calc(100% - 150px);
            overflow: auto;
            margin-top: 20px;
            border-top: 2px solid #333;

            .histories-item {
              flex-shrink: 0;
              display: flex;
              align-items: center;
              justify-content: space-between;
              width: 90%;
              height: 50px;
              margin-top: 20px;
              color: #ccc;
              border-top: 1px solid #777;
              border-radius: 10px;
              box-shadow: -1px -1px 4px 0px rgba(255, 255, 255, 0.3);

              .status {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;

                .status-ball {
                  width: 20px;
                  height: 20px;
                  border-radius: 10px;
                  opacity: 0.8;
                }
              }

              .summary {
                line-height: 40px;
                font-size: 16px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;

                &:hover {
                  cursor: pointer;
                }

                &.collapsed {
                  display: none;
                }
              }

              .delete {
                width: 20px;
                padding-right: 10px;

                &:hover {
                  scale: 1.3;
                  cursor: pointer;
                }
              }
            }
          }

        }
      }

      .right {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;

        .island {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          width: 40%;
          min-width: 600px;
          max-width: 800px;
          padding-top: 20px;
          padding-bottom: 20px;
          color: #ccc;
          border-radius: 20px;
          box-shadow: 0px 0px 12px 0px rgba(255, 255, 255, 0.3);

          .head {
            display: flex;
            align-items: center;
            justify-content: center;

            .logo {
              width: 70px;
            }

            .hello {
              font-size: 24px;
              font-weight: bold;
              font-family: "Arial", sans-serif;
              margin-left: 20px;
            }
          }

          .prompt {
            margin-top: 10px;
            margin-bottom: 20px;
            font-size: 16px;
            font-family: "Arial", sans-serif;
          }
        }

        .communication {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: space-evenly;
          width: 100%;
          max-width: 1000px;
          height: 96%;

          .chat-records {
            display: flex;
            flex-direction: column;
            width: 100%;
            height: 80%;
            color: #fff;
            overflow: auto;
          }

          .new-dialog {
            width: 200px;
            height: 50px;
            text-align: center;
            font-size: 16px;
            color: #cccccc;
            border: none;
            border-radius: 15px;
            background-color: #222;

            &:hover {
              background-color: #333;
              box-shadow: -2px -2px 8px 0px #aaa;
            }

            .icon {
              width: 25px;
              padding-right: 20px;
            }
          }
        }

      }
    }
  }
}
</style>
