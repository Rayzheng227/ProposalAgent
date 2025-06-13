import axios, { AxiosHeaders, AxiosError, type InternalAxiosRequestConfig } from "axios";
import { ElLoading, ElMessage } from "element-plus";
import type { R } from "@/common/interfaces";

const requestTypeJson = "application/json";
const requestTypeForm = "multipart/form-data";
const responseTypeJson = "json";

let loading: ReturnType<typeof ElLoading.service> | null = null;

// 自定义请求配置类型
interface MyRequestConfig extends InternalAxiosRequestConfig {
  headers: any;
  showLoading?: boolean;
  requestType?: string;
  errorCallback?: (error: any) => void;
}

const instance = axios.create({
  withCredentials: true,
  baseURL: "/api",
  timeout: 10 * 1000,
});

// 请求前拦截器
instance.interceptors.request.use(
  (config: MyRequestConfig) => {
    if (config.showLoading) {
      loading = ElLoading.service({
        lock: true,
        text: "Loading......",
        background: "rgba(0, 0, 0, 0.7)",
      });
    }
    return config;
  },
  (error: AxiosError) => {
    const config = error.config as MyRequestConfig;
    if (config?.showLoading && loading) loading.close();
    ElMessage.error("Request Send Failed");
    return Promise.reject("Request Send Failed");
  }
);

// 请求后拦截器
instance.interceptors.response.use(
  (response: any) => {
    const { showLoading, responseType } = response.config as MyRequestConfig;
    if (showLoading && loading) loading.close();
    return response;
  },
  (error: AxiosError) => {
    const config = error.config as MyRequestConfig;
    if (config?.showLoading && loading) loading.close();
    ElMessage.error("Server Processing Error");
    return Promise.reject("Server Processing Error");
  }
);

export default async (config: Omit<MyRequestConfig, "headers"> & { headers?: any }) => {
  const {
    url,
    data,
    headers,
    requestType = requestTypeJson,
    showLoading = true,
    responseType = responseTypeJson,
    errorCallback,
  } = config;

  if (!url) throw new Error("Url is required");
  let requestData = data;
  if (requestType === requestTypeForm) {
    const formData = new FormData();
    for (const key in data) {
      formData.append(key, data[key] == undefined ? "" : data[key]);
    }
    requestData = formData;
  }
  const newHeaders = Object.assign({ "Content-Type": requestType }, headers);
  const newConfig: MyRequestConfig = {
    headers: newHeaders,
    showLoading,
    errorCallback,
    responseType,
  };
  const result = await instance.post(url, requestData, newConfig);
  // 文件流单独构造
  if (responseType === "arraybuffer" || responseType === "blob")
    return { code: 200, mes: "", data: result };
  // 否则统一包装为R类
  const responseData = result.data as R;
  // 统一处理错误，除非传入了自定义错误回调，发生错误时不会返回response
  if (responseData.code !== 200) {
    if (errorCallback) errorCallback(responseData);
    else ElMessage.error(responseData.mes);
  } else return responseData;
};
