import axios, { type AxiosResponse } from "axios";
import { showFailToast } from "vant";

export interface ApiResponse<T> {
  code: number;
  msg: string;
  data: T;
}

export interface DashboardData {
  total_bom_items: number;
  pending: number;
  confirmed: number;
  rejected: number;
  missing_materials: number;
  auto_confirm_rate: number;
  products: Array<{ name: string; pending: number; total: number }>;
}

export interface ReviewItem {
  id: number;
  product_name: string;
  product_code?: string | null;
  material_code?: string | null;
  material_name?: string | null;
  raw_name: string;
  quantity?: number | null;
  unit?: string | null;
  level?: number | null;
  confidence: number;
  status: string;
  match_level?: string | null;
  candidates: CandidateMaterial[];
}

export interface CandidateMaterial {
  code: string;
  name: string;
  spec?: string | null;
  score?: number;
}

export interface MissingMaterial {
  id: number;
  raw_name: string;
  ai_suggested_name?: string | null;
  ai_suggested_spec?: string | null;
  ai_suggested_unit?: string | null;
  ai_suggested_category?: string | null;
  status: string;
}

export interface PageResult<T> {
  total: number;
  page: number;
  page_size?: number;
  items: T[];
}

export interface ExtractedItem {
  name: string;
  spec?: string | null;
  quantity?: number | null;
  unit?: string | null;
  level?: number | null;
  confidence?: number;
}

export interface OcrUploadResult {
  raw_lines: string[];
  extracted: {
    product: string;
    items: ExtractedItem[];
  };
  processing_time_ms?: number;
  mode?: string;
  warnings?: string[];
}

export interface SystemSettingsData {
  runtime: {
    ai_enabled: boolean;
    openai_api_key_configured: boolean;
    openai_base_url: string;
    openai_chat_model: string;
    openai_embedding_model: string;
    ai_match_mode: string;
    ocr_extract_mode: string;
  };
  items: Record<
    string,
    {
      key: string;
      value: string;
      configured: boolean;
      value_type: string;
      group_name: string;
      description: string;
      is_secret: boolean;
    }
  >;
}

const http = axios.create({
  baseURL: "/api",
  timeout: 60000,
});

http.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem("bom_api_key");
  if (apiKey) {
    config.headers["X-API-Key"] = apiKey;
  }
  return config;
});

http.interceptors.response.use(
  (response) => {
    if (response.config.responseType === "blob") {
      return response;
    }
    const result = response.data as ApiResponse<unknown>;
    if (typeof result?.code === "number") {
      if (result.code !== 0) {
        throw new Error(result.msg || "请求失败");
      }
      return result.data;
    }
    return response.data;
  },
  (error) => {
    const message = error?.response?.data?.msg || error?.message || "网络异常，请稍后再试";
    showFailToast(message);
    return Promise.reject(error);
  },
);

export function getDashboard() {
  return http.get<DashboardData, DashboardData>("/review/dashboard");
}

export function getPendingItems(params: { product_name?: string; status?: string; page?: number; page_size?: number }) {
  return http.get<PageResult<ReviewItem>, PageResult<ReviewItem>>("/review/items", {
    params: { status: "pending", ...params },
  });
}

export function getReviewItems(params: { product_name?: string; status?: string; page?: number; page_size?: number }) {
  return http.get<PageResult<ReviewItem>, PageResult<ReviewItem>>("/review/items", { params });
}

export function confirmItem(id: number, systemCode: string) {
  return http.post<{ status: string }, { status: string }>(`/match/confirm/${id}`, {
    system_code: systemCode,
    reviewer: "前端审核",
  });
}

export function rejectItem(id: number) {
  return http.post<{ status: string }, { status: string }>(`/match/reject/${id}`, { reviewer: "前端审核" });
}

export function reassignItem(id: number, systemCode: string) {
  return http.post<{ status: string }, { status: string }>(`/review/reassign/${id}`, {
    system_code: systemCode,
    reviewer: "前端审核",
  });
}

export function batchConfirm(ids: number[]) {
  return http.post<{ confirmed: number; skipped: number }, { confirmed: number; skipped: number }>(
    "/review/batch-confirm",
    { ids, reviewer: "前端审核" },
  );
}

export function getMissingItems(params: { page?: number; page_size?: number }) {
  return http.get<PageResult<MissingMaterial>, PageResult<MissingMaterial>>("/match/missing", { params });
}

export function markMissingCreated(id: number) {
  return http.post<{ status: string }, { status: string }>(`/match/create-missing/${id}`);
}

export function uploadOcrFile(file: File, productName: string, mode = "auto") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("product_name", productName);
  formData.append("mode", mode);
  return http.post<OcrUploadResult, OcrUploadResult>("/ocr/upload", formData);
}

export function extractBomFromText(text: string, productName: string) {
  return http.post<OcrUploadResult, OcrUploadResult>("/ocr/text", {
    text,
    product_name: productName,
  });
}

export function processBom(extracted: OcrUploadResult["extracted"], productName: string) {
  return http.post<{ auto_confirmed: number; pending_review: number; missing: number; total: number }, { auto_confirmed: number; pending_review: number; missing: number; total: number }>(
    "/match/process",
    { extracted, product_name: productName },
  );
}

export function getSystemSettings() {
  return http.get<SystemSettingsData, SystemSettingsData>("/settings/system");
}

export function updateSystemSettings(settings: Record<string, string | boolean>, operator = "前端设置") {
  return http.post<SystemSettingsData, SystemSettingsData>("/settings/system", { settings, operator });
}

export async function downloadBom(productName: string) {
  const response = await http.get<Blob, AxiosResponse<Blob>>(`/export/bom/${encodeURIComponent(productName)}`, {
    responseType: "blob",
  });
  const blobUrl = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = `BOM_${productName}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(blobUrl);
}
