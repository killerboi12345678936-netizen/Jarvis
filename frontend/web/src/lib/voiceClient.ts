import { API, getDeviceToken } from "./api";

export type VoiceState =
  | "idle"
  | "listening"
  | "recording"
  | "transcribing"
  | "thinking"
  | "speaking";

export type VoiceTuning = {
  continuous: boolean;
  speechThreshold: number;
  silenceMs: number;
  minSpeechMs: number;
  bargeInThreshold: number;
};

export const DEFAULT_VOICE_TUNING: VoiceTuning = {
  continuous: true,
  speechThreshold: 0.015,
  silenceMs: 900,
  minSpeechMs: 300,
  bargeInThreshold: 0.035,
};

export type VoiceClientHandlers = {
  onState?: (state: VoiceState) => void;
  onTranscript?: (text: string) => void;
  onSentence?: (text: string) => void;
  onResponseDone?: (response: string, interrupted: boolean) => void;
  onInterrupted?: () => void;
  onError?: (message: string) => void;
  onMicLevel?: (level: number) => void;
  onClosed?: () => void;
};

const WORKLET_SOURCE = `
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];

    if (channel) {
      this.port.postMessage(channel.slice(0));
    }

    return true;
  }
}
registerProcessor("capture-processor", CaptureProcessor);
`;

const TARGET_SAMPLE_RATE = 16000;
const SEND_SAMPLES = 1600; // 100 ms of audio per websocket frame.

const floatToInt16 = (samples: Float32Array): Int16Array => {
  const pcm = new Int16Array(samples.length);

  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));

    pcm[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }

  return pcm;
};

const rmsOf = (samples: Float32Array): number => {
  let sum = 0;

  for (let i = 0; i < samples.length; i += 1) {
    sum += samples[i] * samples[i];
  }

  return Math.sqrt(sum / Math.max(1, samples.length));
};

export class LiveVoiceClient {
  private ws: WebSocket | null = null;

  private audioContext: AudioContext | null = null;

  private mediaStream: MediaStream | null = null;

  private workletNode: AudioWorkletNode | null = null;

  private sourceNode: MediaStreamAudioSourceNode | null = null;

  private captureBuffer: Float32Array = new Float32Array(0);

  private playbackSources: Set<AudioBufferSourceNode> = new Set();

  private playbackEpoch = 0;

  private nextStartTime = 0;

  private handlers: VoiceClientHandlers = {};

  private tuning: VoiceTuning = { ...DEFAULT_VOICE_TUNING };

  private pendingAudio: ArrayBuffer[] = [];

  private collectingAudio = false;

  connected = false;

  async connect(handlers: VoiceClientHandlers): Promise<void> {
    if (this.ws) {
      return;
    }

    this.handlers = handlers;

    const wsUrl =
      API.replace(/^http/, "ws") +
      "/api/voice/ws" +
      `?token=${encodeURIComponent(getDeviceToken())}`;

    const ws = new WebSocket(wsUrl);

    ws.binaryType = "arraybuffer";
    this.ws = ws;

    await new Promise<void>((resolve, reject) => {
      ws.onopen = () => resolve();

      ws.onerror = () => {
        // The close event carries the real status; let it reject.
      };

      ws.onclose = (event) => {
        reject(
          event.code === 4401
            ? new Error("Voice session rejected: unauthorized device.")
            : new Error(
                "Could not reach the Jarvis voice service.",
              ),
        );
      };
    });

    try {
      await this.startCapture();
    } catch (error) {
      this.cleanup();

      throw error instanceof Error
        ? error
        : new Error("Microphone unavailable.");
    }

    this.connected = true;

    this.sendControl({
      type: "config",
      sample_rate: TARGET_SAMPLE_RATE,
      continuous: this.tuning.continuous,
      speech_threshold: this.tuning.speechThreshold,
      silence_ms: this.tuning.silenceMs,
      min_speech_ms: this.tuning.minSpeechMs,
      barge_in_threshold: this.tuning.bargeInThreshold,
    });

    this.sendControl({ type: "listen" });

    ws.onmessage = (event) => this.handleMessage(event.data);
    ws.onclose = () => {
      this.connected = false;
      this.cleanup();
      this.handlers.onClosed?.();
    };
  }

  private async startCapture(): Promise<void> {
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const context = new AudioContext({
      sampleRate: TARGET_SAMPLE_RATE,
    });

    // Browsers may create the context suspended under autoplay
    // policy; a suspended context receives scheduled audio but
    // never plays it, which silences Jarvis completely.
    void context.resume().catch(() => undefined);

    this.audioContext = context;

    const workletUrl = URL.createObjectURL(
      new Blob([WORKLET_SOURCE], { type: "application/javascript" }),
    );

    await context.audioWorklet.addModule(workletUrl);
    URL.revokeObjectURL(workletUrl);

    const node = new AudioWorkletNode(
      context,
      "capture-processor",
    );

    node.port.onmessage = (event) => {
      const frame = event.data as Float32Array;

      this.handlers.onMicLevel?.(rmsOf(frame));

      this.captureBuffer = this.appendToBuffer(this.captureBuffer, frame);

      if (this.captureBuffer.length >= SEND_SAMPLES) {
        const pcm = floatToInt16(this.captureBuffer);

        this.captureBuffer = new Float32Array(0);

        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(pcm.buffer as ArrayBuffer);
        }
      }
    };

    this.workletNode = node;

    this.sourceNode = context.createMediaStreamSource(
      this.mediaStream,
    );

    // The worklet taps the mic but is deliberately not routed to the
    // destination, which would echo the microphone into the speakers.
    this.sourceNode.connect(node);
  }

  private appendToBuffer(
    buffer: Float32Array,
    frame: Float32Array,
  ): Float32Array {
    const merged = new Float32Array(buffer.length + frame.length);

    merged.set(buffer);
    merged.set(frame, buffer.length);

    return merged;
  }

  private handleMessage(data: ArrayBuffer | string): void {
    if (data instanceof ArrayBuffer) {
      if (this.collectingAudio) {
        this.pendingAudio.push(data);
      }

      return;
    }

    let payload: Record<string, unknown>;

    try {
      payload = JSON.parse(data);
    } catch {
      return;
    }

    switch (payload.type) {
      case "state":
        this.handlers.onState?.(payload.state as VoiceState);
        break;

      case "transcript":
        this.handlers.onTranscript?.(
          typeof payload.text === "string" ? payload.text : "",
        );
        break;

      case "sentence_start":
        this.handlers.onSentence?.(
          typeof payload.text === "string" ? payload.text : "",
        );
        break;

      case "audio_start":
        this.pendingAudio = [];
        this.collectingAudio = true;
        break;

      case "audio_end":
        this.collectingAudio = false;
        void this.enqueuePlayback();
        break;

      case "interrupt_ack":
        this.stopPlayback();
        this.handlers.onInterrupted?.();
        break;

      case "interrupted":
        this.stopPlayback();
        this.handlers.onInterrupted?.();
        break;

      case "response_done":
        this.handlers.onResponseDone?.(
          typeof payload.response === "string" ? payload.response : "",
          payload.interrupted === true,
        );
        break;

      case "error":
        this.handlers.onError?.(
          typeof payload.message === "string"
            ? payload.message
            : "Voice processing failed.",
        );
        break;
    }
  }

  private async enqueuePlayback(): Promise<void> {
    const context = this.audioContext;

    if (!context || this.pendingAudio.length === 0) {
      return;
    }

    const epoch = this.playbackEpoch;

    const wav = new Blob(this.pendingAudio, { type: "audio/wav" });

    this.pendingAudio = [];

    let buffer: AudioBuffer;

    try {
      buffer = await context.decodeAudioData(await wav.arrayBuffer());
    } catch {
      this.handlers.onError?.("Audio playback failed.");
      return;
    }

    if (epoch !== this.playbackEpoch) {
      return;
    }

    if (context.state === "suspended") {
      try {
        await context.resume();
      } catch {
        this.handlers.onError?.(
          "Audio is blocked until you interact with the page.",
        );
        return;
      }
    }

    const source = context.createBufferSource();

    source.buffer = buffer;
    source.connect(context.destination);

    const startAt = Math.max(
      context.currentTime + 0.03,
      this.nextStartTime,
    );

    source.start(startAt);
    this.nextStartTime = startAt + buffer.duration;

    this.playbackSources.add(source);

    source.onended = () => {
      this.playbackSources.delete(source);
    };
  }

  private stopPlayback(): void {
    this.playbackEpoch += 1;

    for (const source of this.playbackSources) {
      try {
        source.stop();
      } catch {
        // Already stopped.
      }

      source.disconnect();
    }

    this.playbackSources.clear();
    this.nextStartTime = 0;
    this.pendingAudio = [];
    this.collectingAudio = false;
  }

  private sendControl(payload: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  sendInterrupt(): void {
    this.sendControl({ type: "interrupt" });
  }

  updateTuning(patch: Partial<VoiceTuning>): void {
    this.tuning = { ...this.tuning, ...patch };

    this.sendControl({
      type: "config",
      continuous: this.tuning.continuous,
      speech_threshold: this.tuning.speechThreshold,
      silence_ms: this.tuning.silenceMs,
      min_speech_ms: this.tuning.minSpeechMs,
      barge_in_threshold: this.tuning.bargeInThreshold,
    });
  }

  disconnect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendControl({ type: "stop" });
    }

    this.ws?.close();
    this.ws = null;

    this.cleanup();
  }

  private cleanup(): void {
    this.stopPlayback();

    this.workletNode?.port.close();
    this.workletNode?.disconnect();
    this.workletNode = null;

    this.sourceNode?.disconnect();
    this.sourceNode = null;

    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;

    void this.audioContext?.close().catch(() => undefined);
    this.audioContext = null;

    this.captureBuffer = new Float32Array(0);
    this.connected = false;
  }
}
