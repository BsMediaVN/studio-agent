// TypeScript types matching the BE Pydantic models in studio_api.py

// ---- Script models ----

export type Gender = 'M' | 'F';
export type LineType = 'dialogue' | 'narration';
export type Emotion = 'neutral' | 'happy' | 'sad' | 'angry' | 'fearful' | 'surprised' | 'whisper';
export type OutputFormat = 'wav' | 'mp3';
export type ScriptMode = 'dialogue' | 'story';

export interface ScriptCharacter {
  name: string;
  gender: Gender;
  voice_tone?: string;
  voice_id?: string;
}

export interface DialogueLine {
  character: string;
  text: string;
  emotion?: Emotion;
  pause_after_ms?: number;
  line_type?: LineType;
}

export interface Scene {
  scene_num: number;
  setting?: string;
  dialogue: DialogueLine[];
}

export interface Script {
  title: string;
  characters: ScriptCharacter[];
  scenes: Scene[];
}

// ---- Request models ----

export type StoryGenre = '' | 'tâm lý' | 'hài hước' | 'kinh dị' | 'lãng mạn' | 'hành động' | 'trinh thám';
export type StoryType = 'oneshot' | 'multi';

export interface BatchGenerateRequest {
  title: string;
  prompt: string;
  num_episodes: number;
  mode?: ScriptMode;
  genre?: string;
  max_characters?: number;
  target_duration_s?: number | null;
  characters?: CharacterPreset[];
}

export interface BatchGenerateResponse {
  status: string;
  error?: string;
  series: Series | null;
}

export interface CharacterPreset {
  name: string;
  gender: Gender;
}

export interface GenerateScriptRequest {
  prompt: string;
  max_characters?: number;
  language?: string;
  mode?: ScriptMode;
  genre?: string;
  target_duration_s?: number;
  characters?: CharacterPreset[];
}

export interface ProduceRequest {
  script: Script;
  voice_map: Record<string, string>;
  silence_gap?: number;
  crossfade?: number;
  output_format?: OutputFormat;
  normalize?: boolean;
  temperature?: number;
  top_k?: number;
  speed?: number;
  target_duration_s?: number | null;
}

export interface PipelineRequest {
  text: string;
  mode?: ScriptMode;
  max_characters?: number;
  voice_overrides?: Record<string, string>;
  output_format?: OutputFormat;
  normalize?: boolean;
  silence_gap?: number;
  crossfade?: number;
  temperature?: number;
  top_k?: number;
  speed?: number;
  target_duration_s?: number | null;
}

// ---- Job / Status ----

export type JobStatusValue = 'queued' | 'processing' | 'complete' | 'error';

export interface JobStatus {
  job_id: string;
  status: JobStatusValue;
  progress: number;
  current_step: string;
  result_url: string | null;
  error: string | null;
  created_at: number;
}

// ---- Voice ----

export interface VoiceInfo {
  id: string;
  name: string;
  cached: boolean;
}

export interface ClonedVoice {
  id: string;
  has_text: boolean;
}

// ---- Workflow models ----

export interface WorkflowConfig {
  name: string;
  description?: string;
  mode?: ScriptMode;
  max_characters?: number;
  output_format?: OutputFormat;
  normalize?: boolean;
  silence_gap?: number;
  crossfade?: number;
  temperature?: number;
  top_k?: number;
  speed?: number;
  target_duration_s?: number | null;
  voice_overrides?: Record<string, string>;
  editor_data?: Record<string, unknown>;
}

export interface WorkflowRecord {
  id: string;
  config: WorkflowConfig;
  webhook_url: string;
  created_at: number;
  run_count: number;
  last_run: number | null;
}

export interface WorkflowRunRecord {
  run_id: string;
  workflow_id: string;
  status: 'success' | 'error';
  input_text: string;
  output_url: string | null;
  error: string | null;
  started_at: number;
  finished_at: number;
}

export interface WebhookTriggerRequest {
  text: string;
  voice_overrides?: Record<string, string>;
}

// ---- Series / Audiobook ----

export interface Episode {
  episode_num: number;
  title?: string;
  script_data: Record<string, unknown>;
  voice_map: Record<string, string>;
  job_id?: string;
  audio_path?: string;
  summary?: string;
  duration_s?: number;
  created_at?: number;
}

export interface Series {
  id: string;
  title: string;
  mode: ScriptMode;
  voice_map: Record<string, string>;
  characters: Array<{ name: string; gender: Gender }>;
  episodes: Episode[];
  temperature: number;
  top_k: number;
  speed: number;
  target_duration_s: number | null;
  created_at: number;
}

export interface CreateSeriesRequest {
  title: string;
  mode?: ScriptMode;
  script_data?: Record<string, unknown> | null;
  voice_map?: Record<string, string>;
  characters?: Array<{ name: string; gender: Gender }>;
  temperature?: number;
  top_k?: number;
  speed?: number;
  target_duration_s?: number | null;
}

export interface ContinueSeriesRequest {
  prompt?: string;
  max_characters?: number;
}

export interface UpdateSeriesRequest {
  title?: string | null;
  voice_map?: Record<string, string> | null;
  characters?: Array<{ name: string; gender: Gender }> | null;
  temperature?: number | null;
  top_k?: number | null;
  speed?: number | null;
  target_duration_s?: number | null;
}

export interface ReproduceEpisodeRequest {
  script_data: Record<string, unknown>;
}

// ---- API response wrappers ----

export interface GenerateScriptResponse {
  status: string;
  script: Script;
}

export interface ProduceResponse {
  status: string;
  job_id: string;
}

export interface VoicesResponse {
  voices: VoiceInfo[];
}

export interface StatusResponse {
  engine_loaded: boolean;
  voices_cached: number;
  voice_ids: string[];
  sample_rate: number;
  ffmpeg_available: boolean;
}

export interface PipelineJsonResponse {
  status: string;
  job_id: string;
  script: Script;
  voice_map: Record<string, string>;
  download_url: string;
  output_format: OutputFormat;
}

export interface WorkflowCreateResponse {
  status: string;
  workflow: WorkflowRecord;
  webhook_url: string;
  webhook_curl: string;
}

export interface SeriesResponse {
  status: string;
  series: Series;
}

export interface CloneVoiceResponse {
  status: string;
  voice_id: string;
  message: string;
}
