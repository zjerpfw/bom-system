<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { showFailToast, showSuccessToast } from "vant";
import VoiceCapture from "@/components/VoiceCapture.vue";
import { extractBomFromText, processBom, uploadOcrFile, type ExtractedItem, type OcrUploadResult } from "@/api";

const router = useRouter();
const productName = ref("");
const activeTab = ref("file");
const fileList = ref<Array<{ file?: File; url?: string; name?: string }>>([]);
const loading = ref(false);
const uploadResult = ref<OcrUploadResult | null>(null);

const extractedItems = computed<ExtractedItem[]>(() => uploadResult.value?.extracted.items || []);

async function handleAfterRead(fileItem: { file?: File } | { file?: File }[]) {
  const current = Array.isArray(fileItem) ? fileItem[0] : fileItem;
  if (!productName.value.trim()) {
    showFailToast("请先填写产品名称");
    fileList.value = [];
    return;
  }
  if (!current.file) {
    showFailToast("未读取到文件");
    return;
  }
  loading.value = true;
  try {
    uploadResult.value = await uploadOcrFile(current.file, productName.value.trim());
    showSuccessToast("识别完成");
  } catch {
    showFailToast("识别失败，请换一张更清晰的图纸");
  } finally {
    loading.value = false;
  }
}

async function handleVoiceSubmit(text: string) {
  if (!productName.value.trim()) {
    showFailToast("请先填写产品名称");
    return;
  }
  loading.value = true;
  try {
    uploadResult.value = await extractBomFromText(text, productName.value.trim());
    showSuccessToast("语音文本已提取");
  } catch {
    showFailToast("语音文本提取失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function submitBom() {
  if (!uploadResult.value) return;
  loading.value = true;
  try {
    await processBom(uploadResult.value.extracted, productName.value.trim());
    showSuccessToast("已提交审核");
    router.push("/review");
  } catch {
    showFailToast("提交审核失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="page">
    <van-nav-bar title="上传图纸" fixed placeholder />
    <div class="page-body">
      <van-field
        v-model="productName"
        class="product-input"
        label="产品名称"
        placeholder="请输入产品名称"
        clearable
        required
      />

      <van-tabs v-model:active="activeTab" class="upload-tabs" color="#1D9E75" title-active-color="#1D9E75">
        <van-tab title="文件上传" name="file">
          <section class="upload-zone surface">
            <van-uploader
              v-model="fileList"
              :max-count="1"
              :after-read="handleAfterRead"
              accept="image/*,.xls,.xlsx,.csv"
              upload-icon="plus"
            >
              <div class="upload-box">
                <van-icon name="upgrade" size="42" color="#1D9E75" />
                <strong>点击上传图纸或Excel</strong>
                <span>支持拍照、截图、表格文件</span>
              </div>
            </van-uploader>
          </section>
        </van-tab>
        <van-tab title="语音录入" name="voice">
          <VoiceCapture @submit="handleVoiceSubmit" />
        </van-tab>
      </van-tabs>

      <van-loading v-if="loading" class="upload-loading" color="#1D9E75" vertical>
        正在识别，请稍候
      </van-loading>

      <template v-if="uploadResult">
        <h2 class="section-title">识别预览</h2>
        <div class="surface preview-list">
          <van-cell
            v-for="(item, index) in extractedItems"
            :key="`${item.name}-${index}`"
            :title="item.name"
            :label="`${item.spec || '无规格'} · ${item.quantity ?? '-'} ${item.unit || ''}`"
          />
          <div v-if="!extractedItems.length" class="empty-note">未提取到物料条目</div>
        </div>
        <van-button
          class="submit-button primary-button"
          type="primary"
          block
          :disabled="!extractedItems.length"
          @click="submitBom"
        >
          确认提交审核
        </van-button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.product-input {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

.upload-zone {
  display: flex;
  justify-content: center;
  margin-top: 16px;
  padding: 26px 16px;
}

.upload-tabs {
  margin-top: 16px;
}

.upload-box {
  display: grid;
  justify-items: center;
  gap: 10px;
  width: min(76vw, 320px);
  min-height: 168px;
  padding: 20px;
  border: 2px dashed #8fd6bf;
  border-radius: 8px;
  color: var(--color-muted);
  text-align: center;
  font-size: 16px;
}

.upload-box strong {
  color: var(--color-text);
  font-size: 19px;
}

.upload-loading {
  margin: 22px 0;
}

.preview-list {
  overflow: hidden;
}

.submit-button {
  min-height: 50px;
  margin-top: 16px;
  border-radius: 8px;
  font-size: 18px;
  font-weight: 850;
}
</style>
