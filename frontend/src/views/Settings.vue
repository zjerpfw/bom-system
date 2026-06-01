<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { showFailToast, showSuccessToast } from "vant";
import { getSystemSettings, updateSystemSettings } from "@/api";

const apiKey = ref(localStorage.getItem("bom_api_key") || "");
const aiEnabled = ref(false);
const openaiBaseUrl = ref("");
const openaiApiKey = ref("");
const openaiChatModel = ref("gpt-5.5");
const openaiEmbeddingModel = ref("text-embedding-3-small");
const apiKeyConfigured = ref(false);
const embeddingProvider = ref("openai");
const dashscopeApiKey = ref("");
const dashscopeBaseUrl = ref("https://dashscope.aliyuncs.com/api/v1");
const dashscopeEmbeddingModel = ref("text-embedding-v4");
const dashscopeApiKeyConfigured = ref(false);
const qianfanApiKey = ref("");
const qianfanBaseUrl = ref("https://qianfan.baidubce.com/v2");
const qianfanEmbeddingModel = ref("embedding-v1");
const qianfanApiKeyConfigured = ref(false);
const baiduOcrAppId = ref("");
const baiduOcrApiKey = ref("");
const baiduOcrSecretKey = ref("");
const baiduOcrApiKeyConfigured = ref(false);
const baiduOcrSecretKeyConfigured = ref(false);
const baiduOcrAccountType = ref("personal");
const baiduOcrFreeQuotaSafetyBuffer = ref("5");
const baiduOcrTableMonthlyFreeLimit = ref("");
const loading = ref(false);
const saving = ref(false);

const runningMode = computed(() => (aiEnabled.value ? "AI增强模式" : "规则模式"));
const runningModeType = computed(() => (aiEnabled.value ? "success" : "warning"));
const secretPlaceholder = computed(() => (apiKeyConfigured.value ? "已配置，留空则不修改" : "未配置"));
const dashscopeSecretPlaceholder = computed(() => (dashscopeApiKeyConfigured.value ? "已配置，留空则不修改" : "未配置"));
const qianfanSecretPlaceholder = computed(() => (qianfanApiKeyConfigured.value ? "已配置，留空则不修改" : "未配置"));
const baiduOcrApiKeyPlaceholder = computed(() => (baiduOcrApiKeyConfigured.value ? "已配置，留空则不修改" : "未配置"));
const baiduOcrSecretKeyPlaceholder = computed(() =>
  baiduOcrSecretKeyConfigured.value ? "已配置，留空则不修改" : "未配置",
);

function saveFrontendApiKey() {
  if (apiKey.value.trim()) {
    localStorage.setItem("bom_api_key", apiKey.value.trim());
  } else {
    localStorage.removeItem("bom_api_key");
  }
  showSuccessToast("请求密钥已保存");
}

async function loadSettings() {
  loading.value = true;
  try {
    const data = await getSystemSettings();
    aiEnabled.value = data.runtime.ai_enabled;
    openaiBaseUrl.value = data.runtime.openai_base_url || "";
    openaiChatModel.value = data.runtime.openai_chat_model || "gpt-5.5";
    openaiEmbeddingModel.value = data.runtime.openai_embedding_model || "text-embedding-3-small";
    apiKeyConfigured.value = data.runtime.openai_api_key_configured;
    embeddingProvider.value = data.runtime.embedding_provider || "openai";
    dashscopeApiKeyConfigured.value = data.runtime.dashscope_api_key_configured;
    dashscopeBaseUrl.value = data.runtime.dashscope_base_url || "https://dashscope.aliyuncs.com/api/v1";
    dashscopeEmbeddingModel.value = data.runtime.dashscope_embedding_model || "text-embedding-v4";
    qianfanApiKeyConfigured.value = data.runtime.qianfan_api_key_configured;
    qianfanBaseUrl.value = data.runtime.qianfan_base_url || "https://qianfan.baidubce.com/v2";
    qianfanEmbeddingModel.value = data.runtime.qianfan_embedding_model || "embedding-v1";
    baiduOcrAppId.value = data.runtime.baidu_ocr_app_id || "";
    baiduOcrApiKeyConfigured.value = data.runtime.baidu_ocr_api_key_configured;
    baiduOcrSecretKeyConfigured.value = data.runtime.baidu_ocr_secret_key_configured;
    baiduOcrAccountType.value = data.runtime.baidu_ocr_account_type || "personal";
    baiduOcrFreeQuotaSafetyBuffer.value = String(data.runtime.baidu_ocr_free_quota_safety_buffer ?? 5);
    baiduOcrTableMonthlyFreeLimit.value = data.runtime.baidu_ocr_table_monthly_free_limit
      ? String(data.runtime.baidu_ocr_table_monthly_free_limit)
      : "";
  } catch {
    showFailToast("系统配置加载失败");
  } finally {
    loading.value = false;
  }
}

async function saveSystemSettings() {
  saving.value = true;
  try {
    const settings: Record<string, string | boolean> = {
      AI_ENABLED: aiEnabled.value,
      OPENAI_BASE_URL: openaiBaseUrl.value.trim(),
      OPENAI_CHAT_MODEL: openaiChatModel.value.trim() || "gpt-5.5",
      OPENAI_EMBEDDING_MODEL: openaiEmbeddingModel.value.trim() || "text-embedding-3-small",
      EMBEDDING_PROVIDER: embeddingProvider.value,
      DASHSCOPE_BASE_URL: dashscopeBaseUrl.value.trim() || "https://dashscope.aliyuncs.com/api/v1",
      DASHSCOPE_EMBEDDING_MODEL: dashscopeEmbeddingModel.value.trim() || "text-embedding-v4",
      QIANFAN_BASE_URL: qianfanBaseUrl.value.trim() || "https://qianfan.baidubce.com/v2",
      QIANFAN_EMBEDDING_MODEL: qianfanEmbeddingModel.value.trim() || "embedding-v1",
      BAIDU_OCR_APP_ID: baiduOcrAppId.value.trim(),
      BAIDU_OCR_ACCOUNT_TYPE: baiduOcrAccountType.value,
      BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER: baiduOcrFreeQuotaSafetyBuffer.value.trim() || "5",
      BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT: baiduOcrTableMonthlyFreeLimit.value.trim(),
      AI_MATCH_MODE: "rule_first",
      OCR_EXTRACT_MODE: "rule_first",
    };
    if (openaiApiKey.value.trim()) {
      settings.OPENAI_API_KEY = openaiApiKey.value.trim();
    }
    if (dashscopeApiKey.value.trim()) {
      settings.DASHSCOPE_API_KEY = dashscopeApiKey.value.trim();
    }
    if (qianfanApiKey.value.trim()) {
      settings.QIANFAN_API_KEY = qianfanApiKey.value.trim();
    }
    if (baiduOcrApiKey.value.trim()) {
      settings.BAIDU_OCR_API_KEY = baiduOcrApiKey.value.trim();
    }
    if (baiduOcrSecretKey.value.trim()) {
      settings.BAIDU_OCR_SECRET_KEY = baiduOcrSecretKey.value.trim();
    }
    const data = await updateSystemSettings(settings);
    aiEnabled.value = data.runtime.ai_enabled;
    apiKeyConfigured.value = data.runtime.openai_api_key_configured;
    embeddingProvider.value = data.runtime.embedding_provider;
    dashscopeApiKeyConfigured.value = data.runtime.dashscope_api_key_configured;
    qianfanApiKeyConfigured.value = data.runtime.qianfan_api_key_configured;
    baiduOcrApiKeyConfigured.value = data.runtime.baidu_ocr_api_key_configured;
    baiduOcrSecretKeyConfigured.value = data.runtime.baidu_ocr_secret_key_configured;
    baiduOcrAppId.value = data.runtime.baidu_ocr_app_id || "";
    baiduOcrAccountType.value = data.runtime.baidu_ocr_account_type || "personal";
    baiduOcrFreeQuotaSafetyBuffer.value = String(data.runtime.baidu_ocr_free_quota_safety_buffer ?? 5);
    baiduOcrTableMonthlyFreeLimit.value = data.runtime.baidu_ocr_table_monthly_free_limit
      ? String(data.runtime.baidu_ocr_table_monthly_free_limit)
      : "";
    openaiApiKey.value = "";
    dashscopeApiKey.value = "";
    qianfanApiKey.value = "";
    baiduOcrApiKey.value = "";
    baiduOcrSecretKey.value = "";
    showSuccessToast("系统配置已保存");
  } catch {
    showFailToast("系统配置保存失败");
  } finally {
    saving.value = false;
  }
}

async function testConnection() {
  await saveSystemSettings();
  if (!aiEnabled.value) {
    showSuccessToast("当前为规则模式，无需连接AI");
    return;
  }
  if (embeddingProvider.value === "openai" && !apiKeyConfigured.value && !openaiApiKey.value.trim()) {
    showFailToast("请先填写OpenAI兼容接口密钥");
    return;
  }
  if (embeddingProvider.value === "dashscope" && !dashscopeApiKeyConfigured.value && !dashscopeApiKey.value.trim()) {
    showFailToast("请先填写阿里百炼密钥");
    return;
  }
  if (embeddingProvider.value === "qianfan" && !qianfanApiKeyConfigured.value && !qianfanApiKey.value.trim()) {
    showFailToast("请先填写百度千帆密钥");
    return;
  }
  showSuccessToast("配置已保存，上传或匹配时会自动验证接口");
}

onMounted(loadSettings);
</script>

<template>
  <div class="page">
    <van-nav-bar title="设置" fixed placeholder />
    <div class="page-body">
      <section class="surface settings-section">
        <div class="section-head">
          <div>
            <h2>运行模式</h2>
            <p>找不到可用AI接口时，保持规则模式也能完成审核闭环。</p>
          </div>
          <van-tag :type="runningModeType" size="large">{{ runningMode }}</van-tag>
        </div>
        <van-cell center title="AI增强能力" label="开启后使用GPT提取和向量语义匹配">
          <template #right-icon>
            <van-switch v-model="aiEnabled" size="28px" active-color="#1D9E75" />
          </template>
        </van-cell>
      </section>

      <section class="surface settings-section">
        <h2>AI接口配置</h2>
        <van-field
          v-model="openaiBaseUrl"
          label="接口地址"
          placeholder="例如 https://fululai.cn/v1"
          clearable
        />
        <van-field
          v-model="openaiApiKey"
          label="接口密钥"
          :placeholder="secretPlaceholder"
          type="password"
          clearable
        />
        <van-field
          v-model="openaiChatModel"
          label="聊天模型"
          placeholder="例如 gpt-5.5"
          clearable
        />
        <van-field
          v-model="openaiEmbeddingModel"
          label="兼容向量"
          placeholder="例如 text-embedding-3-small"
          clearable
        />
        <div class="provider-panel">
          <div class="provider-title">向量服务</div>
          <van-radio-group v-model="embeddingProvider" direction="horizontal">
            <van-radio name="openai" checked-color="#1D9E75">兼容接口</van-radio>
            <van-radio name="dashscope" checked-color="#1D9E75">阿里</van-radio>
            <van-radio name="qianfan" checked-color="#1D9E75">百度</van-radio>
          </van-radio-group>
        </div>
        <template v-if="embeddingProvider === 'dashscope'">
          <van-field
            v-model="dashscopeApiKey"
            label="阿里密钥"
            :placeholder="dashscopeSecretPlaceholder"
            type="password"
            clearable
          />
          <van-field
            v-model="dashscopeBaseUrl"
            label="阿里地址"
            placeholder="https://dashscope.aliyuncs.com/api/v1"
            clearable
          />
          <van-field
            v-model="dashscopeEmbeddingModel"
            label="阿里向量"
            placeholder="text-embedding-v4"
            clearable
          />
        </template>
        <template v-if="embeddingProvider === 'qianfan'">
          <van-field
            v-model="qianfanApiKey"
            label="百度密钥"
            :placeholder="qianfanSecretPlaceholder"
            type="password"
            clearable
          />
          <van-field
            v-model="qianfanBaseUrl"
            label="百度地址"
            placeholder="https://qianfan.baidubce.com/v2"
            clearable
          />
          <van-field
            v-model="qianfanEmbeddingModel"
            label="百度向量"
            placeholder="embedding-v1"
            clearable
          />
        </template>
        <div class="button-stack">
          <van-button
            class="touch-button primary-button"
            type="primary"
            block
            :loading="saving"
            @click="saveSystemSettings"
          >
            保存系统配置
          </van-button>
          <van-button class="touch-button" plain type="primary" block :loading="saving" @click="testConnection">
            测试连接配置
          </van-button>
        </div>
      </section>

      <section class="surface settings-section">
        <div class="section-head">
          <div>
            <h2>百度OCR表格识别</h2>
            <p>老BOM表格截图建议配置此项，系统会按免费额度保护自动切换。</p>
          </div>
          <van-tag type="primary" size="large">表格</van-tag>
        </div>
        <van-field
          v-model="baiduOcrAppId"
          label="App ID"
          placeholder="百度智能云应用 App ID"
          clearable
        />
        <van-field
          v-model="baiduOcrApiKey"
          label="API Key"
          :placeholder="baiduOcrApiKeyPlaceholder"
          type="password"
          clearable
        />
        <van-field
          v-model="baiduOcrSecretKey"
          label="Secret Key"
          :placeholder="baiduOcrSecretKeyPlaceholder"
          type="password"
          clearable
        />
        <div class="provider-panel">
          <div class="provider-title">账号类型</div>
          <van-radio-group v-model="baiduOcrAccountType" direction="horizontal">
            <van-radio name="personal" checked-color="#1D9E75">个人</van-radio>
            <van-radio name="enterprise" checked-color="#1D9E75">企业</van-radio>
          </van-radio-group>
        </div>
        <van-field
          v-model="baiduOcrTableMonthlyFreeLimit"
          label="表格月额度"
          placeholder="不填则按账号类型默认保护"
          type="digit"
          clearable
        />
        <van-field
          v-model="baiduOcrFreeQuotaSafetyBuffer"
          label="预留次数"
          placeholder="默认5，避免用尽免费额度"
          type="digit"
          clearable
        />
        <van-button
          class="touch-button save-button"
          type="primary"
          block
          :loading="saving"
          @click="saveSystemSettings"
        >
          保存OCR配置
        </van-button>
      </section>

      <section class="surface settings-section">
        <h2>前端访问密钥</h2>
        <van-field
          v-model="apiKey"
          label="API Key"
          placeholder="后端未配置API_KEY时可留空"
          clearable
          type="password"
        />
        <van-button class="touch-button save-button" type="primary" block @click="saveFrontendApiKey">
          保存请求密钥
        </van-button>
      </section>

      <van-cell-group class="surface link-group" :border="false">
        <van-cell title="物料库维护" label="上传ERP商品CSV并重建匹配索引" is-link to="/materials" />
        <van-cell title="缺失物料" label="查看待新建物料" is-link to="/missing" />
      </van-cell-group>

      <van-loading v-if="loading" class="loading" color="#1D9E75" vertical>正在读取配置</van-loading>
    </div>
  </div>
</template>

<style scoped>
.settings-section {
  margin-bottom: 14px;
  overflow: hidden;
}

.settings-section h2 {
  margin: 0;
  padding: 14px 14px 4px;
  font-size: 18px;
  line-height: 1.35;
}

.section-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  padding: 14px;
}

.section-head h2 {
  padding: 0;
}

.section-head p {
  margin: 6px 0 0;
  color: var(--color-muted);
  font-size: 16px;
  line-height: 1.5;
}

.button-stack {
  display: grid;
  gap: 10px;
  padding: 14px;
}

.provider-panel {
  padding: 14px;
  background: #f7fbfa;
}

.provider-title {
  margin-bottom: 10px;
  color: var(--color-muted);
  font-size: 16px;
}

.save-button {
  margin: 14px;
  width: calc(100% - 28px);
}

.link-group {
  margin-top: 14px;
  overflow: hidden;
}

.loading {
  margin: 20px 0;
}

@media (min-width: 900px) {
  .page-body {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    align-items: start;
  }

  .settings-section,
  .link-group {
    margin-bottom: 0;
  }

  .settings-section:first-child,
  .link-group {
    grid-column: 1 / -1;
  }

  .button-stack {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
