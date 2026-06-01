<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { showFailToast, showSuccessToast } from "vant";
import VoiceCapture from "@/components/VoiceCapture.vue";
import {
  extractBomFromText,
  processBomBatch,
  uploadOcrFiles,
  type ExtractedItem,
  type OcrUploadResult,
} from "@/api";

interface UploadDocument {
  id: string;
  fileName: string;
  imageUrl?: string;
  productName: string;
  result: OcrUploadResult;
  items: EditableItem[];
}

interface EditableItem extends ExtractedItem {
  id: string;
  spec: string;
  quantity: number | undefined;
  unit: string;
}

const router = useRouter();
const activeTab = ref("file");
const fileList = ref<Array<{ file?: File; url?: string; name?: string }>>([]);
const ocrMode = ref("auto");
const loading = ref(false);
const documents = ref<UploadDocument[]>([]);
const activeDocumentId = ref("");
const textProductName = ref("");

const activeDocument = computed(() => documents.value.find((document) => document.id === activeDocumentId.value) || null);
const totalItemCount = computed(() => documents.value.reduce((count, document) => count + document.items.length, 0));
const currentImageUrl = computed(() => activeDocument.value?.imageUrl || "");

watch(activeDocumentId, async () => {
  await nextTick();
  revokeUnusedObjectUrls();
});

function createItem(item: Partial<ExtractedItem> = {}): EditableItem {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    name: item.name || "",
    spec: item.spec || "",
    quantity: item.quantity ?? undefined,
    unit: item.unit || "",
    level: item.level || 1,
    confidence: item.confidence ?? 0.86,
  };
}

function normalizeProductName(result: OcrUploadResult, fallbackName: string) {
  return (result.extracted.product || fallbackName.replace(/\.[^.]+$/, "") || "").trim();
}

function buildDocument(file: File, result: OcrUploadResult): UploadDocument {
  const imageUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined;
  return {
    id: `${file.name}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    fileName: file.name,
    imageUrl,
    productName: normalizeProductName(result, file.name),
    result,
    items: result.extracted.items.map((item) => createItem(item)),
  };
}

function revokeUnusedObjectUrls() {
  const activeUrls = new Set(documents.value.map((document) => document.imageUrl).filter(Boolean));
  fileList.value = fileList.value.filter((fileItem) => {
    if (!fileItem.url || activeUrls.has(fileItem.url)) {
      return true;
    }
    URL.revokeObjectURL(fileItem.url);
    return false;
  });
}

async function handleAfterRead(fileItem: { file?: File } | { file?: File }[]) {
  const incomingFiles = (Array.isArray(fileItem) ? fileItem : [fileItem])
    .map((item) => item.file)
    .filter((file): file is File => Boolean(file));
  if (!incomingFiles.length) {
    showFailToast("未读取到文件");
    return;
  }

  loading.value = true;
  try {
    const results = await uploadOcrFiles(incomingFiles, "", ocrMode.value);
    const newDocuments = results.map((result, index) => buildDocument(incomingFiles[index], result));
    documents.value.push(...newDocuments);
    if (!activeDocumentId.value && newDocuments[0]) {
      activeDocumentId.value = newDocuments[0].id;
    }
    showSuccessToast(`已识别 ${newDocuments.length} 份BOM`);
  } catch {
    showFailToast("识别失败，请换一张更清晰的图纸");
  } finally {
    loading.value = false;
  }
}

async function handleVoiceSubmit(text: string) {
  loading.value = true;
  try {
    const result = await extractBomFromText(text, textProductName.value.trim());
    const productName = normalizeProductName(result, textProductName.value || "语音录入");
    documents.value.push({
      id: `voice-${Date.now()}`,
      fileName: "语音录入",
      productName,
      result,
      items: result.extracted.items.map((item) => createItem(item)),
    });
    activeDocumentId.value = documents.value[documents.value.length - 1].id;
    showSuccessToast("语音文本已提取");
  } catch {
    showFailToast("语音文本提取失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

function addItem() {
  if (!activeDocument.value) return;
  activeDocument.value.items.push(createItem());
}

function removeItem(itemId: string) {
  if (!activeDocument.value) return;
  activeDocument.value.items = activeDocument.value.items.filter((item) => item.id !== itemId);
}

function removeDocument(documentId: string) {
  const target = documents.value.find((document) => document.id === documentId);
  if (target?.imageUrl) {
    URL.revokeObjectURL(target.imageUrl);
  }
  documents.value = documents.value.filter((document) => document.id !== documentId);
  if (activeDocumentId.value === documentId) {
    activeDocumentId.value = documents.value[0]?.id || "";
  }
}

function buildSubmitDocuments() {
  return documents.value.map((document) => ({
    product_name: document.productName.trim() || document.result.extracted.product || document.fileName.replace(/\.[^.]+$/, ""),
    extracted: {
      product: document.productName.trim() || document.result.extracted.product || document.fileName.replace(/\.[^.]+$/, ""),
      items: document.items
        .filter((item) => item.name.trim())
        .map((item) => ({
          name: item.name.trim(),
          spec: item.spec || null,
          quantity: item.quantity ?? null,
          unit: item.unit || null,
          level: item.level || 1,
          confidence: item.confidence ?? 0.86,
        })),
    },
  }));
}

async function submitBom() {
  const submitDocuments = buildSubmitDocuments().filter((document) => document.extracted.items.length);
  if (!submitDocuments.length) {
    showFailToast("请先保留至少一条物料");
    return;
  }
  loading.value = true;
  try {
    await processBomBatch(submitDocuments);
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
    <div class="page-body upload-page-body">
      <header class="upload-toolbar surface">
        <div>
          <strong>识别工作台</strong>
          <span>可批量上传BOM，识别后先修正，再提交审核。</span>
        </div>
        <van-button
          class="submit-button primary-button"
          type="primary"
          :disabled="!totalItemCount"
          :loading="loading"
          @click="submitBom"
        >
          提交审核
        </van-button>
      </header>

      <div class="upload-workspace">
        <section class="upload-left">
          <div class="surface upload-panel">
            <van-tabs v-model:active="activeTab" class="upload-tabs" color="#1D9E75" title-active-color="#1D9E75">
              <van-tab title="文件上传" name="file">
                <div class="mode-section">
                  <div class="mode-title">识别模式</div>
                  <van-radio-group v-model="ocrMode" class="mode-list">
                    <van-radio name="auto" checked-color="#1D9E75">自动识别</van-radio>
                    <van-radio name="baidu_enhanced" checked-color="#1D9E75">拍照表格增强</van-radio>
                    <van-radio name="baidu" checked-color="#1D9E75">百度原图表格</van-radio>
                    <van-radio name="paddle" checked-color="#1D9E75">本地文字识别</van-radio>
                  </van-radio-group>
                </div>

                <van-uploader
                  v-model="fileList"
                  :after-read="handleAfterRead"
                  :max-count="20"
                  multiple
                  accept="image/*"
                  upload-icon="plus"
                >
                  <div class="upload-box">
                    <van-icon name="upgrade" size="42" color="#1D9E75" />
                    <strong>点击上传一张或多张BOM</strong>
                    <span>支持拍照、截图，产品名称会自动识别，可再手动修改。</span>
                  </div>
                </van-uploader>
              </van-tab>
              <van-tab title="语音录入" name="voice">
                <van-field v-model="textProductName" label="产品名称" placeholder="可选，语音中也可包含产品名" clearable />
                <VoiceCapture @submit="handleVoiceSubmit" />
              </van-tab>
            </van-tabs>
          </div>

          <div class="document-tabs" v-if="documents.length">
            <button
              v-for="document in documents"
              :key="document.id"
              class="document-tab"
              :class="{ active: document.id === activeDocumentId }"
              type="button"
              @click="activeDocumentId = document.id"
            >
              <span>{{ document.productName || document.fileName }}</span>
              <small>{{ document.items.length }}条</small>
            </button>
          </div>

          <section class="a4-frame surface">
            <template v-if="currentImageUrl">
              <img :src="currentImageUrl" alt="BOM原图" />
            </template>
            <div v-else class="a4-placeholder">
              <van-icon name="photo-o" size="42" />
              <strong>等待上传图片</strong>
              <span>上传后会按A4比例显示，方便对照修正物料。</span>
            </div>
          </section>
        </section>

        <section class="upload-right surface">
          <van-loading v-if="loading" class="upload-loading" color="#1D9E75" vertical>
            正在识别，请稍候
          </van-loading>

          <template v-else-if="activeDocument">
            <div class="editor-header">
              <van-field
                v-model="activeDocument.productName"
                class="product-input"
                label="产品名称"
                placeholder="自动识别，可修改"
                clearable
              />
              <van-button plain type="danger" icon="delete-o" @click="removeDocument(activeDocument.id)">
                删除此BOM
              </van-button>
            </div>

            <div class="editor-actions">
              <span>共 {{ activeDocument.items.length }} 条物料</span>
              <van-button plain type="primary" icon="plus" @click="addItem">新增物料</van-button>
            </div>

            <div class="item-editor-list">
              <article v-for="(item, index) in activeDocument.items" :key="item.id" class="item-editor">
                <div class="item-index">{{ index + 1 }}</div>
                <div class="item-fields">
                  <van-field v-model="item.name" label="名称" placeholder="物料名称" clearable />
                  <van-field v-model="item.spec" label="规格" placeholder="规格型号" clearable />
                  <div class="field-row">
                    <van-field v-model.number="item.quantity" type="number" label="数量" placeholder="0" />
                    <van-field v-model="item.unit" label="单位" placeholder="个/斤" clearable />
                  </div>
                </div>
                <van-button class="delete-item" plain type="danger" icon="delete-o" @click="removeItem(item.id)" />
              </article>
              <div v-if="!activeDocument.items.length" class="empty-note">
                当前BOM没有物料，可点击“新增物料”手动补充。
              </div>
            </div>
          </template>

          <div v-else class="preview-placeholder">
            <strong>还没有识别结果</strong>
            <span>上传图片后，右侧会显示可编辑物料清单。</span>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.upload-page-body {
  display: grid;
  gap: 14px;
}

.upload-toolbar {
  display: grid;
  gap: 12px;
  padding: 14px;
}

.upload-toolbar strong,
.upload-toolbar span {
  display: block;
}

.upload-toolbar strong {
  font-size: 20px;
}

.upload-toolbar span {
  margin-top: 4px;
  color: var(--color-muted);
  font-size: 16px;
  line-height: 1.5;
}

.upload-workspace {
  display: grid;
  gap: 14px;
}

.upload-left,
.upload-right {
  min-width: 0;
}

.upload-panel,
.upload-right {
  padding: 14px;
}

.mode-section {
  display: grid;
  gap: 12px;
  padding: 4px 0 14px;
}

.mode-title {
  color: var(--color-muted);
  font-size: 16px;
}

.mode-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 10px;
  font-size: 16px;
}

.upload-box {
  display: grid;
  justify-items: center;
  gap: 10px;
  width: min(78vw, 420px);
  min-height: 178px;
  padding: 22px;
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

.document-tabs {
  display: flex;
  gap: 8px;
  margin: 12px 0;
  overflow-x: auto;
  padding-bottom: 4px;
}

.document-tab {
  min-width: 126px;
  min-height: 54px;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-muted);
  background: #ffffff;
  text-align: left;
}

.document-tab.active {
  border-color: var(--color-primary);
  color: var(--color-primary-dark);
  background: #eaf7f2;
}

.document-tab span,
.document-tab small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-tab span {
  font-weight: 800;
}

.document-tab small {
  margin-top: 4px;
}

.a4-frame {
  display: grid;
  width: 100%;
  aspect-ratio: 210 / 297;
  place-items: center;
  overflow: hidden;
  background: #f7faf8;
}

.a4-frame img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #e8ecea;
}

.a4-placeholder {
  display: grid;
  gap: 8px;
  padding: 24px;
  color: var(--color-muted);
  text-align: center;
  font-size: 16px;
}

.a4-placeholder strong {
  color: var(--color-text);
  font-size: 20px;
}

.upload-loading {
  min-height: 260px;
  justify-content: center;
}

.editor-header {
  display: grid;
  gap: 10px;
}

.product-input {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

.editor-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 14px 0;
  color: var(--color-muted);
  font-size: 16px;
}

.item-editor-list {
  display: grid;
  gap: 10px;
}

.item-editor {
  display: grid;
  grid-template-columns: 34px 1fr 44px;
  gap: 8px;
  align-items: start;
  padding: 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fbfdfc;
}

.item-index {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 8px;
  color: #ffffff;
  background: var(--color-primary);
  font-weight: 850;
}

.item-fields {
  display: grid;
  gap: 8px;
}

.field-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
}

.delete-item {
  min-width: 44px;
  height: 44px;
}

.submit-button {
  min-height: 48px;
  border-radius: 8px;
  font-size: 18px;
  font-weight: 850;
}

.preview-placeholder {
  display: grid;
  min-height: 320px;
  place-items: center;
  gap: 8px;
  color: var(--color-muted);
  text-align: center;
  font-size: 16px;
}

.preview-placeholder strong {
  color: var(--color-text);
  font-size: 22px;
}

@media (min-width: 1100px) {
  .upload-toolbar {
    grid-template-columns: minmax(0, 1fr) 220px;
    align-items: center;
  }

  .upload-workspace {
    grid-template-columns: minmax(420px, 0.9fr) minmax(520px, 1.1fr);
    align-items: start;
  }

  .upload-right {
    max-height: calc(100vh - 150px);
    overflow: auto;
  }

  .upload-box {
    width: 100%;
  }
}
</style>
