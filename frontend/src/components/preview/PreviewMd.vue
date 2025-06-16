<template>
  <div class="markdown-preview" v-html="renderedMarkdown"> </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, getCurrentInstance } from 'vue';
import { Marked } from 'marked';
import hljs from 'highlight.js';
import { markedHighlight } from "marked-highlight"
import 'highlight.js/styles/atom-one-dark.css'

const marked = new Marked(
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      const language = hljs.getLanguage(lang) ? lang : 'shell'
      return hljs.highlight(code, { language }).value
    }
  })
)

const instance: any = getCurrentInstance();
const proxy = instance.proxy;
const props = defineProps({
  historyId: {
    type: String,
    default: ""
  }
});
const renderedMarkdown = ref('');

const initMarkdown = async () => {
  const result = await proxy.Request({
    url: proxy.Api.download,
    data: {
      fileType: "md",
      historyId: props.historyId
    },
    responseType: 'blob'
  });
  if (!result) return;
  const reader = new FileReader();
  reader.readAsText(result.data.data);
  reader.onload = () => {
    if (reader.result) {
      renderedMarkdown.value = marked.parse(reader.result as string) as string;
    }
  };
};

onMounted(() => {
  initMarkdown();
});
</script>

<style lang="scss">
.markdown-preview {
  width: 100%;
  height: 100%;
  overflow: auto;
  background-color: rgba(50, 50, 50, 0.9);
  padding: 30px;
  color: #eee;

  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    margin-top: 20px;
    margin-bottom: 15px;
    font-weight: bold;
    scroll-margin-top: 20px;
  }

  h1 {
    font-size: 22px;
    padding-bottom: 10px;
    color: #8ab4f8;
  }

  h2 {
    font-size: 20px;
    padding-bottom: 10px;
    color: #aecbfa;
  }

  h3 {
    font-size: 18px;
    color: #c8d9fe;
  }

  h4 {
    font-size: 17px;
    color: #e8eaed;
  }

  h5 {
    font-size: 16px;
    color: #dadce0;
  }

  h6 {
    font-size: 17px;
    color: #bdc1c6;
  }

  p {
    margin-bottom: 20px;
    line-height: 30px;
    font-size: 16px;
    color: #bebeaf;
  }

  a {
    color: #3b82f6;
    text-decoration: none;
    transition: color 0.2s;
    font-size: 14px;
  }

  a:hover {
    color: #60a5fa;
    text-decoration: underline;
  }

  ul,
  ol {
    margin-bottom: 20px;
    padding-left: 30px;
    color: #cfa978;
  }

  li {
    margin-bottom: 10px;
    line-height: 20px;
    font-size: 15px;
  }

  ol>li {
    list-style-type: decimal;
  }

  ul>li {
    list-style-type: disc;
  }

  li>p {
    margin-bottom: 10px;
  }

  blockquote {
    border-left: 4px solid #4b5563;
    padding-left: 15px;
    margin-left: 0;
    margin-bottom: 25px;
    color: #9ca3af;
    font-style: italic;
  }

  pre {
    padding: 16px;
    border-radius: 16px;
    margin-bottom: 20px;
    overflow-x: auto;
    line-height: 1.8;
    font-size: 15px;
    border: 2px solid #4b5563;
  }

  pre code {
    background-color: transparent !important;
    padding: 0 !important;
    font-size: 14px;
    font-family: Verdana, Geneva, Tahoma, sans-serif;
  }

  code {
    padding: 3px 6px;
    font-family: monospace;
    font-size: 16px;
    color: #5e81e2;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
  }

  th,
  td {
    border: 1px solid #4b5563;
    padding: 12px;
    text-align: left;
  }

  th {
    background-color: #1f2937;
    font-weight: bold;
    color: #e5e7eb;
  }

  tr:nth-child(even) {
    background-color: #2d3748;
  }

  img {
    max-width: 100%;
    height: auto;
    margin: 24px 0;
    border-radius: 8px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    transition: transform 0.2s;
  }

  img:hover {
    transform: scale(1.02);
  }
}
</style>