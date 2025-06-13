// Request里自动给请求附加/api头，这里不用加
export default {
  // ws
  loadMessageStream: "ws://localhost:8810/ws",
  // http
  sendQuery: "/sendQuery",
  checkFileExist: "/checkFileExist",
  download: "/download",
};
