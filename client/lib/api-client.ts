import { API_URL } from './constants';
import type {
  GenerateScriptRequest,
  GenerateScriptResponse,
  ProduceRequest,
  ProduceResponse,
  VoicesResponse,
  StatusResponse,
  JobStatus,
  PipelineRequest,
  PipelineJsonResponse,
  WorkflowConfig,
  WorkflowRecord,
  WorkflowCreateResponse,
  WorkflowRunRecord,
  WebhookTriggerRequest,
  Series,
  CreateSeriesRequest,
  ContinueSeriesRequest,
  UpdateSeriesRequest,
  SeriesResponse,
  Episode,
  ReproduceEpisodeRequest,
  CloneVoiceResponse,
  ClonedVoice,
  BatchGenerateRequest,
  BatchGenerateResponse,
} from './types';

// ---------------------------------------------------------------------------
// ApiError
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ---------------------------------------------------------------------------
// ApiClient
// ---------------------------------------------------------------------------

class ApiClient {
  private base: string;

  constructor(base: string = API_URL) {
    this.base = base.replace(/\/$/, '');
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    options?: RequestInit,
  ): Promise<T> {
    const url = `${this.base}/studio${path}`;
    const headers: HeadersInit = {};
    let bodyPayload: BodyInit | undefined;

    if (body instanceof FormData) {
      bodyPayload = body;
    } else if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      bodyPayload = JSON.stringify(body);
    }

    const res = await fetch(url, {
      method,
      headers,
      body: bodyPayload,
      ...options,
    });

    if (!res.ok) {
      let detail: unknown;
      try {
        detail = await res.json();
      } catch {
        detail = await res.text();
      }
      const msg =
        typeof detail === 'object' && detail !== null && 'detail' in detail
          ? String((detail as Record<string, unknown>).detail)
          : `HTTP ${res.status}`;
      throw new ApiError(res.status, msg, detail);
    }

    const ct = res.headers.get('content-type') ?? '';
    if (ct.includes('application/json')) {
      return res.json() as Promise<T>;
    }
    // Return blob URL for audio responses
    const blob = await res.blob();
    return URL.createObjectURL(blob) as unknown as T;
  }

  private get<T>(path: string): Promise<T> {
    return this.request<T>('GET', path);
  }

  private post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('POST', path, body);
  }

  private put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('PUT', path, body);
  }

  private delete<T>(path: string): Promise<T> {
    return this.request<T>('DELETE', path);
  }

  // ---- Core endpoints ----

  generateScript(req: GenerateScriptRequest): Promise<GenerateScriptResponse> {
    return this.post('/generate-script', req);
  }

  produce(req: ProduceRequest): Promise<ProduceResponse> {
    return this.post('/produce', req);
  }

  getJobStatus(jobId: string): Promise<JobStatus> {
    return this.get(`/job/${jobId}`);
  }

  getVoices(): Promise<VoicesResponse> {
    return this.get('/voices');
  }

  getStatus(): Promise<StatusResponse> {
    return this.get('/status');
  }

  downloadUrl(jobId: string): string {
    return `${this.base}/studio/download/${jobId}`;
  }

  // ---- Pipeline ----

  pipeline(req: PipelineRequest): Promise<string> {
    return this.post('/pipeline', req);
  }

  pipelineJson(req: PipelineRequest): Promise<PipelineJsonResponse> {
    return this.post('/pipeline/json', req);
  }

  // ---- Voice cloning ----

  async cloneVoice(file: File, name: string, text: string): Promise<CloneVoiceResponse> {
    const form = new FormData();
    form.append('file', file);
    form.append('name', name);
    form.append('text', text);
    return this.request<CloneVoiceResponse>('POST', '/clone-voice', form);
  }

  deleteClonedVoice(voiceName: string): Promise<{ status: string; message: string }> {
    return this.delete(`/clone-voice/${voiceName}`);
  }

  listClonedVoices(): Promise<{ custom_voices: ClonedVoice[] }> {
    return this.get('/clone-voice');
  }

  // ---- Workflows ----

  listWorkflows(): Promise<{ workflows: WorkflowRecord[] }> {
    return this.get('/workflows');
  }

  createWorkflow(config: WorkflowConfig): Promise<WorkflowCreateResponse> {
    return this.post('/workflows', config);
  }

  getWorkflow(wfId: string): Promise<WorkflowRecord> {
    return this.get(`/workflows/${wfId}`);
  }

  updateWorkflow(wfId: string, config: WorkflowConfig): Promise<{ status: string; workflow: WorkflowRecord }> {
    return this.put(`/workflows/${wfId}`, config);
  }

  deleteWorkflow(wfId: string): Promise<{ status: string }> {
    return this.delete(`/workflows/${wfId}`);
  }

  triggerWorkflow(wfId: string, req: WebhookTriggerRequest): Promise<string> {
    return this.post(`/workflows/${wfId}/trigger`, req);
  }

  getWorkflowRuns(wfId: string): Promise<{ runs: WorkflowRunRecord[] }> {
    return this.get(`/workflows/${wfId}/runs`);
  }

  // ---- Series ----

  listSeries(): Promise<{ series: Series[] }> {
    return this.get('/series');
  }

  createSeries(req: CreateSeriesRequest): Promise<SeriesResponse> {
    return this.post('/series', req);
  }

  batchGenerate(req: BatchGenerateRequest): Promise<BatchGenerateResponse> {
    return this.post('/series/batch-generate', req);
  }

  getSeries(sid: string): Promise<Series> {
    return this.get(`/series/${sid}`);
  }

  updateSeries(sid: string, req: UpdateSeriesRequest): Promise<SeriesResponse> {
    return this.put(`/series/${sid}`, req);
  }

  deleteSeries(sid: string): Promise<{ status: string }> {
    return this.delete(`/series/${sid}`);
  }

  continueSeries(
    sid: string,
    req: ContinueSeriesRequest,
  ): Promise<{ status: string; episode: Episode; download_url: string }> {
    return this.post(`/series/${sid}/continue`, req);
  }

  mergeSeries(sid: string): Promise<{
    status: string;
    download_url: string;
    total_episodes: number;
    total_duration_s: number;
  }> {
    return this.post(`/series/${sid}/merge`);
  }

  exportSeries(sid: string): Promise<Series> {
    return this.get(`/series/${sid}/export`);
  }

  async importSeries(file: File): Promise<{ status: string; series: Series; note: string }> {
    const form = new FormData();
    form.append('file', file);
    return this.request('POST', '/series/import', form);
  }

  reproduceEpisode(
    sid: string,
    epNum: number,
    req: ReproduceEpisodeRequest,
  ): Promise<{ status: string; download_url: string }> {
    return this.post(`/series/${sid}/episodes/${epNum}/reproduce`, req);
  }

  downloadEpisodeUrl(sid: string, epNum: number): string {
    return `${this.base}/studio/series/${sid}/episodes/${epNum}/download`;
  }
}

export const api = new ApiClient();
