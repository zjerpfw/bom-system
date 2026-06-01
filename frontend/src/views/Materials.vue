<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { showFailToast, showSuccessToast } from "vant";
import {
  buildMaterialIndex,
  getMaterialStats,
  importMaterials,
  type MaterialImportResult,
  type MaterialStats,
} from "@/api";

const loading = ref(false);
const importing = ref(false);
const building = ref(false);
const selectedFile = ref<File | null>(null);
const importResult = ref<MaterialImportResult | null>(null);
const stats = ref<MaterialStats>({
  material_total: 0,
  index_ready: false,
  index_count: 0,
});

const indexReady = computed(() => stats.value.index_ready);
const indexStatusText = computed(() => (indexReady.value ? "索引已就绪" : "索引未建立"));
const indexStatusType = computed(() => (indexReady.value ? "success" : "warning"));
const fileName = computed(() => selectedFile.value?.name || "请选择ERP导出的CSV文件");

async function loadStats() {
  loading.value = true;
  try {
    stats.value = await getMaterialStats();
  } catch {
    showFailToast("物料库状态加载失败");
  } finally {
    loading.value = false;
  }
}

function afterRead(fileItem: unknown) {
  const file = Array.isArray(fileItem) ? fileItem[0]?.file : (fileItem as { file?: File })?.file;
  if (!file) {
    showFailToast("文件读取失败");
    return;
  }
  selectedFile.value = file;
  importResult.value = null;
}

async function handleImport() {
  if (!selectedFile.value) {
    showFailToast("请先选择CSV文件");
    return;
  }
  importing.value = true;
  try {
    importResult.value = await importMaterials(selectedFile.value);
    showSuccessToast("物料导入完成");
    await loadStats();
  } catch {
    showFailToast("物料导入失败");
  } finally {
    importing.value = false;
  }
}

async function handleBuildIndex() {
  building.value = true;
  try {
    await buildMaterialIndex();
    showSuccessToast("匹配索引已重建");
    await loadStats();
  } catch {
    showFailToast("索引重建失败，请检查AI配置");
  } finally {
    building.value = false;
  }
}

onMounted(loadStats);
</script>

<template>
  <div class="page">
    <van-nav-bar title="物料库维护" fixed placeholder />

    <div class="page-body">
      <section class="surface material-section status-section">
        <div class="section-head">
          <div>
            <h2>ERP商品底库</h2>
            <p>这里维护系统用于匹配研发叫法的标准商品/物料数据。</p>
          </div>
          <van-tag :type="indexStatusType" size="large">{{ indexStatusText }}</van-tag>
        </div>

        <van-grid :column-num="2" :border="false">
          <van-grid-item>
            <div class="metric">
              <strong>{{ stats.material_total }}</strong>
              <span>物料总数</span>
            </div>
          </van-grid-item>
          <van-grid-item>
            <div class="metric">
              <strong>{{ stats.index_count }}</strong>
              <span>已建向量</span>
            </div>
          </van-grid-item>
        </van-grid>

        <van-button class="touch-button refresh-button" plain type="primary" block :loading="loading" @click="loadStats">
          刷新状态
        </van-button>
      </section>

      <section class="surface material-section">
        <h2>上传ERP物料CSV</h2>
        <p class="section-copy">CSV列名必须包含：编码、名称、规格、单位、类别。编码重复时会更新原记录。</p>

        <van-uploader
          accept=".csv,text/csv"
          :max-count="1"
          :after-read="afterRead"
          :preview-image="false"
          class="material-uploader"
        >
          <div class="upload-pick">
            <van-icon name="description-o" />
            <strong>{{ fileName }}</strong>
            <span>点击选择文件</span>
          </div>
        </van-uploader>

        <van-button
          class="touch-button primary-button"
          type="primary"
          block
          :loading="importing"
          @click="handleImport"
        >
          导入或更新物料库
        </van-button>

        <div v-if="importResult" class="import-result">
          <van-cell title="读取行数" :value="String(importResult.total)" />
          <van-cell title="成功写入" :value="String(importResult.success)" />
          <van-cell title="跳过行数" :value="String(importResult.skipped)" />
          <div v-if="importResult.errors.length" class="error-list">
            <strong>导入提示</strong>
            <p v-for="error in importResult.errors" :key="error">{{ error }}</p>
          </div>
        </div>
      </section>

      <section class="surface material-section">
        <h2>重建匹配索引</h2>
        <p class="section-copy">导入新物料后需要重建索引，AI语义匹配才会使用最新底库。规则模式可先不建索引。</p>
        <van-button class="touch-button" plain type="primary" block :loading="building" @click="handleBuildIndex">
          重建AI匹配索引
        </van-button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.material-section {
  margin-bottom: 14px;
  overflow: hidden;
}

.material-section h2 {
  margin: 0;
  padding: 14px 14px 4px;
  font-size: 18px;
  line-height: 1.35;
}

.status-section {
  padding-bottom: 14px;
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

.section-head p,
.section-copy {
  margin: 6px 0 0;
  color: var(--color-muted);
  font-size: 16px;
  line-height: 1.5;
}

.section-copy {
  padding: 0 14px 14px;
}

.metric {
  width: 100%;
  min-height: 76px;
  display: grid;
  place-items: center;
  gap: 6px;
  color: var(--color-muted);
  font-size: 16px;
}

.metric strong {
  color: var(--color-primary-dark);
  font-size: 26px;
  line-height: 1.1;
}

.refresh-button,
.material-section > .touch-button {
  margin: 14px;
  width: calc(100% - 28px);
}

.material-uploader {
  display: block;
  margin: 0 14px 14px;
}

.upload-pick {
  width: 100%;
  min-height: 116px;
  display: grid;
  place-items: center;
  gap: 8px;
  padding: 16px;
  border: 1px dashed var(--color-primary);
  border-radius: 8px;
  background: #f2fbf7;
  color: var(--color-primary-dark);
  text-align: center;
}

.upload-pick .van-icon {
  font-size: 30px;
}

.upload-pick strong {
  max-width: 100%;
  overflow-wrap: anywhere;
  color: var(--color-text);
  font-size: 16px;
}

.upload-pick span {
  color: var(--color-muted);
  font-size: 16px;
}

.import-result {
  margin-top: 8px;
  border-top: 1px solid var(--color-border);
}

.error-list {
  padding: 14px;
  color: var(--color-danger);
  font-size: 16px;
  line-height: 1.5;
}

.error-list p {
  margin: 8px 0 0;
}

@media (min-width: 900px) {
  .page-body {
    display: grid;
    grid-template-columns: minmax(360px, 460px) minmax(0, 1fr);
    gap: 18px;
    align-items: start;
  }

  .status-section {
    grid-column: 1 / -1;
  }

  .material-section {
    margin-bottom: 0;
  }

  .upload-pick {
    min-height: 160px;
  }
}
</style>
