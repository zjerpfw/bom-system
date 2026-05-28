<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { showFailToast, showToast } from "vant";

const emit = defineEmits<{
  submit: [text: string];
}>();

interface SpeechRecognitionEventResult {
  readonly isFinal: boolean;
  readonly 0: { transcript: string };
}

interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionEventResult[];
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance;

const finalText = ref("");
const interimText = ref("");
const editableText = ref("");
const isRecording = ref(false);
const isIosSafari = /iP(ad|hone|od).+Safari/i.test(navigator.userAgent) && !/CriOS|EdgiOS/i.test(navigator.userAgent);
const recognition = ref<SpeechRecognitionInstance | null>(null);

const speechRecognitionConstructor = computed<SpeechRecognitionConstructor | null>(() => {
  const speechWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition || null;
});

const isSupported = computed(() => Boolean(speechRecognitionConstructor.value) && !isIosSafari);
const currentText = computed(() => `${finalText.value}${interimText.value}`.trim());
const displayText = computed({
  get: () => editableText.value || currentText.value,
  set: (value: string) => {
    editableText.value = value;
    finalText.value = value;
    interimText.value = "";
  },
});

function createRecognition() {
  // 创建浏览器语音识别实例。
  if (!speechRecognitionConstructor.value) return null;
  const instance = new speechRecognitionConstructor.value();
  instance.lang = "zh-CN";
  instance.continuous = true;
  instance.interimResults = true;
  instance.onresult = (event: SpeechRecognitionEvent) => {
    let nextFinalText = finalText.value;
    let nextInterimText = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const transcript = result[0]?.transcript || "";
      if (result.isFinal) {
        nextFinalText += transcript;
      } else {
        nextInterimText += transcript;
      }
    }
    finalText.value = nextFinalText;
    interimText.value = nextInterimText;
    editableText.value = `${finalText.value}${interimText.value}`.trim();
  };
  instance.onerror = (event: SpeechRecognitionErrorEvent) => {
    isRecording.value = false;
    showFailToast(event.error === "not-allowed" ? "请允许浏览器使用麦克风" : "语音识别失败，请重试");
  };
  instance.onend = () => {
    isRecording.value = false;
    interimText.value = "";
    editableText.value = finalText.value.trim() || editableText.value.trim();
  };
  return instance;
}

function startRecording() {
  // 长按开始语音识别。
  if (!isSupported.value) return;
  try {
    recognition.value?.abort();
    recognition.value = createRecognition();
    recognition.value?.start();
    isRecording.value = true;
  } catch {
    showFailToast("语音识别启动失败");
  }
}

function stopRecording() {
  // 松开停止语音识别。
  if (!isRecording.value) return;
  recognition.value?.stop();
  isRecording.value = false;
}

function submitText() {
  // 提交识别后的文本。
  const text = displayText.value.trim();
  if (!text) {
    showToast("请先录入或输入物料清单");
    return;
  }
  emit("submit", text);
}

onBeforeUnmount(() => {
  recognition.value?.abort();
});
</script>

<template>
  <section class="voice-panel surface">
    <div class="compat-note">推荐使用 Chrome 浏览器以获得最佳语音识别效果</div>

    <template v-if="isSupported">
      <button
        class="mic-button"
        :class="{ recording: isRecording }"
        type="button"
        aria-label="长按说话"
        @pointerdown.prevent="startRecording"
        @pointerup.prevent="stopRecording"
        @pointercancel.prevent="stopRecording"
        @pointerleave.prevent="stopRecording"
      >
        <van-icon name="audio" size="36" color="#fff" />
      </button>
      <div class="record-hint">{{ isRecording ? "正在识别，松开结束" : "长按说话" }}</div>
    </template>

    <div v-else class="fallback-note">
      当前浏览器不支持稳定的语音识别，请使用上传功能，或在下方手动输入口述内容。
    </div>

    <van-field
      v-model="displayText"
      class="voice-text"
      type="textarea"
      rows="7"
      autosize
      placeholder="例如：产品A需要铜柱M3四个，螺钉八个，线束一根"
    />

    <van-button class="submit-voice primary-button" type="primary" block @click="submitText">
      提交识别
    </van-button>
  </section>
</template>

<style scoped>
.voice-panel {
  display: grid;
  justify-items: center;
  gap: 16px;
  padding: 20px 16px;
}

.compat-note,
.fallback-note,
.record-hint {
  width: 100%;
  color: var(--color-muted);
  font-size: 16px;
  line-height: 1.55;
  text-align: center;
}

.fallback-note {
  padding: 14px;
  border: 1px solid #f0c36d;
  border-radius: 8px;
  background: #fff7e6;
  color: #9a6700;
}

.mic-button {
  display: grid;
  place-items: center;
  width: 80px;
  height: 80px;
  border: 0;
  border-radius: 50%;
  background: #1D9E75;
  box-shadow: 0 10px 24px rgba(29, 158, 117, 0.25);
  touch-action: none;
}

.mic-button.recording {
  background: #d64545;
  box-shadow: 0 0 0 10px rgba(214, 69, 69, 0.12);
}

.voice-text {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  font-size: 16px;
}

.submit-voice {
  min-height: 50px;
  border-radius: 8px;
  font-size: 18px;
  font-weight: 850;
}
</style>
