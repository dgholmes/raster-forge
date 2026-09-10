/* ============================================================================
 * RasterForge domain types.
 *
 * These mirror the backend's `to_dict()` shapes exactly (backend/app/models.py).
 * If you change one side, change the other.
 * ========================================================================== */

export type DatasetStatus =
  | 'uploaded'
  | 'inspecting'
  | 'ready'
  | 'queued'
  | 'processing'
  | 'publishing'
  | 'completed'
  | 'publish_failed'
  | 'failed'
  | 'cancelled';

export type JobStatus =
  | 'queued'
  | 'processing'
  | 'publishing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type NoDataMode = 'auto' | 'preserve' | 'remove';

export type ResamplingMethod =
  | 'nearest'
  | 'bilinear'
  | 'cubic'
  | 'cubicspline'
  | 'lanczos';

export interface BandInfo {
  index: number;
  dtype: string;
  color_interp: string;
  nodata: number | null;
  is_alpha: boolean;
}

export interface RasterMetadata {
  driver: string | null;
  width: number | null;
  height: number | null;
  band_count: number | null;
  crs_name: string | null;
  epsg: number | null;
  is_geographic: boolean;
  pixel_size_x: number | null;
  pixel_size_y: number | null;
  gsd_m: number | null;
  /** [minLon, minLat, maxLon, maxLat] */
  bounds: [number, number, number, number] | null;
  /** [lon, lat] */
  center: [number, number] | null;
  has_alpha: boolean;
  nodata_values: (number | null)[] | null;
  bands: BandInfo[] | null;
  recommended_max_zoom: number | null;
  nodata_warning: string | null;
}

export interface TileJobParams {
  min_zoom: number;
  max_zoom: number;
  resampling: ResamplingMethod;
  nodata_mode: NoDataMode;
  processes?: number;
}

export interface ProcessingJob {
  id: string;
  dataset_id: string;
  dataset_name: string | null;
  type: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  params: TileJobParams | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string | null;
}

export interface TileOutput {
  id: string;
  dataset_id: string;
  job_id: string | null;
  min_zoom: number;
  max_zoom: number;
  scheme: string;
  profile: string;
  resampling: string;
  tile_count: number;
  size_bytes: number;
  public_url_template: string | null;
  bounds: [number, number, number, number] | null;
  normalised: boolean;
  is_published: boolean;
  published_at: string | null;
  created_at: string | null;
}

export interface Dataset {
  id: string;
  display_name: string;
  slug: string;
  source_filename: string;
  source_size: number;
  status: DatasetStatus;
  error_code: string | null;
  error_message: string | null;
  owner: string | null;
  owner_id: number | null;
  created_at: string | null;
  updated_at: string | null;
  metadata: RasterMetadata | null;
  latest_job: ProcessingJob | null;
  published_output: TileOutput | null;
  /** Present only on the detail endpoint. */
  jobs?: ProcessingJob[];
  outputs?: TileOutput[];
}

export interface DatasetPreview {
  dataset_id: string;
  slug: string;
  display_name: string;
  status: DatasetStatus;
  is_published: boolean;
  tile_url_template: string | null;
  min_zoom: number | null;
  max_zoom: number | null;
  tile_count: number;
  size_bytes: number;
  published_at: string | null;
  bounds: [number, number, number, number] | null;
  center: [number, number] | null;
}

export interface JobLogs {
  lines: string[];
  path: string | null;
}

export interface AdminStats {
  datasets: { total: number; published: number; failed: number };
  jobs: {
    total: number;
    active: number;
    pending: number;
    max_concurrent: number;
    failed: number;
  };
  outputs: { total: number; published: number };
  storage: {
    root: string;
    used_bytes: number;
    free_bytes: number;
    by_dataset: {
      id: string;
      display_name: string;
      slug: string;
      status: DatasetStatus;
      size_bytes: number;
      owner: string | null;
    }[];
  };
  gdal: Record<string, string | null>;
  limits: {
    max_upload_mb: number;
    max_raster_pixels: number;
    min_free_disk_gb: number;
    job_timeout_minutes: number;
  };
  failed_jobs: ProcessingJob[];
}

/** Error bodies always carry a machine code plus prose (backend/app/errors.py). */
export interface ApiErrorBody {
  error_code: string;
  error: string;
}

export const ACTIVE_JOB_STATUSES: JobStatus[] = ['queued', 'processing', 'publishing'];

export const ACTIVE_DATASET_STATUSES: DatasetStatus[] = [
  'inspecting',
  'queued',
  'processing',
  'publishing',
];
