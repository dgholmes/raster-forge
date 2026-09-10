/* ============================================================================
 * rasterforge.ts — typed client for the RasterForge API.
 *
 * Thin wrapper over the generic apiService so every call site gets real types
 * and every endpoint path is written exactly once.
 * ========================================================================== */

import { apiService } from './api';
import type {
  AdminStats,
  Dataset,
  DatasetPreview,
  JobLogs,
  ProcessingJob,
  TileJobParams,
  TileOutput,
} from '../types/rasterforge';
import type { AuthUser } from '../types';

const DATASETS = '/api/datasets';
const JOBS = '/api/jobs';

export const rf = {
  /* ── Datasets ──────────────────────────────────────────────────────────── */

  listDatasets(): Promise<Dataset[]> {
    return apiService.get<Dataset[]>(DATASETS);
  },

  getDataset(id: string): Promise<Dataset> {
    return apiService.get<Dataset>(`${DATASETS}/${id}`);
  },

  uploadDataset(
    file: File,
    displayName: string,
    onProgress?: (percent: number, loaded: number, total: number) => void,
    signal?: AbortSignal,
  ): Promise<Dataset> {
    const form = new FormData();
    form.append('file', file);
    form.append('display_name', displayName);
    return apiService.upload<Dataset>(DATASETS, form, onProgress, signal);
  },

  updateDataset(id: string, patch: { display_name?: string; slug?: string }): Promise<Dataset> {
    return apiService.patch<Dataset>(`${DATASETS}/${id}`, patch);
  },

  deleteDataset(id: string): Promise<{ ok: boolean }> {
    return apiService.delete<{ ok: boolean }>(`${DATASETS}/${id}`);
  },

  reinspect(id: string): Promise<Dataset> {
    return apiService.post<Dataset>(`${DATASETS}/${id}/inspect`);
  },

  /* ── Jobs ──────────────────────────────────────────────────────────────── */

  createTileJob(id: string, params: TileJobParams): Promise<ProcessingJob> {
    return apiService.post<ProcessingJob>(`${DATASETS}/${id}/tile-jobs`, params);
  },

  listJobs(limit = 100): Promise<ProcessingJob[]> {
    return apiService.get<ProcessingJob[]>(`${JOBS}?limit=${limit}`);
  },

  getJob(jobId: string): Promise<ProcessingJob> {
    return apiService.get<ProcessingJob>(`${JOBS}/${jobId}`);
  },

  cancelJob(jobId: string): Promise<ProcessingJob> {
    return apiService.post<ProcessingJob>(`${JOBS}/${jobId}/cancel`);
  },

  getJobLogs(jobId: string, tail = 500): Promise<JobLogs> {
    return apiService.get<JobLogs>(`${JOBS}/${jobId}/logs?tail=${tail}`);
  },

  /* ── Outputs / publishing ──────────────────────────────────────────────── */

  getPreview(id: string): Promise<DatasetPreview> {
    return apiService.get<DatasetPreview>(`${DATASETS}/${id}/preview`);
  },

  listOutputs(id: string): Promise<TileOutput[]> {
    return apiService.get<TileOutput[]>(`${DATASETS}/${id}/outputs`);
  },

  /** Retry publishing only — never re-runs the expensive raster processing. */
  publish(id: string): Promise<Dataset> {
    return apiService.post<Dataset>(`${DATASETS}/${id}/publish`);
  },

  /* ── Downloads ─────────────────────────────────────────────────────────── */

  downloadSource(id: string, slug: string): Promise<void> {
    return apiService.download(`${DATASETS}/${id}/download/source`, `${slug}.tif`);
  },

  downloadTiles(id: string, slug: string): Promise<void> {
    return apiService.download(`${DATASETS}/${id}/download/tiles`, `${slug}_tiles.zip`);
  },

  downloadWorking(id: string, slug: string): Promise<void> {
    return apiService.download(`${DATASETS}/${id}/download/working`, `${slug}_clean.tif`);
  },

  downloadMetadata(id: string, slug: string): Promise<void> {
    return apiService.download(`${DATASETS}/${id}/download/metadata`, `${slug}_metadata.json`);
  },

  /* ── Admin ─────────────────────────────────────────────────────────────── */

  adminStats(): Promise<AdminStats> {
    return apiService.get<AdminStats>('/api/admin/stats');
  },

  adminUsers(): Promise<AuthUser[]> {
    return apiService.get<AuthUser[]>('/api/admin/users');
  },

  createUser(payload: {
    username: string;
    password: string;
    role: string;
    email?: string;
  }): Promise<AuthUser> {
    return apiService.post<AuthUser>('/api/admin/users', payload);
  },

  updateUser(
    userId: number,
    patch: { is_active?: boolean; role?: string; password?: string },
  ): Promise<AuthUser> {
    return apiService.patch<AuthUser>(`/api/admin/users/${userId}`, patch);
  },
};
