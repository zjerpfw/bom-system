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
const loading = ref(false);
const saving = ref(false);

const runningMode = computed(() => (aiEnabled.value ? "AI增强模式" : "规则模式"));
const runningModeType = computed(() => (aiEnabled.value ? "success" : "warning"));
const secretPlaceholder = computed(() => (apiKeyConfigured.value ? "已配置，留空则不修改" : "未配置"));

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
      AI_MATCH_MODE: "rule_first",
      OCR_EXTRACT_MODE: "rule_first",
    };
    if (openaiApiKey.value.trim()) {
      settings.OPENAI_API_KEY = openaiApiKey.value.trim();
    }
    const data = await updateSystemSettings(settings);
    aiEnabled.value = data.runtime.ai_enabled;
    apiKeyConfigured.value = data.runtime.openai_api_key_configured;
    openaiApiKey.value = "";
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
  if (!apiKeyConfigured.value && !openaiApiKey.value.trim()) {
    showFailToast("请先填写中转站密钥");
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
          label="向量模型"
          placeholder="例如 text-embedding-3-small"
          clearable
        />
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
</style>
