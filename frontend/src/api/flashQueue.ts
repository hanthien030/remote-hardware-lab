import client from './client';

export type FlashRequestStatus = 'waiting' | 'flashing' | 'success' | 'failed' | 'cancelled';

export interface FlashQueueRequest {
  id: number;
  user_id: string;
  tag_name: string;
  board_type: string;
  firmware_path: string;
  firmware_name?: string;
  project_name?: string | null;
  status: FlashRequestStatus;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  log_output?: string | null;
  serial_log?: string | null;
  queue_position?: number | null;
}

export interface FlashEligibleDevice {
  tag_name: string;
  type: string;
  device_name?: string | null;
  port?: string | null;
  status: 'connected' | 'disconnected';
  locked_by_user?: string | null;
  is_virtualized?: boolean;
  total_slots?: number;
  expires_at?: string;
  queue_depth: number;
  waiting_count: number;
  flashing_count: number;
  active_request_id?: number | null;
  is_busy: boolean;
}

export interface FlashCancelVerification {
  activeRequest: FlashQueueRequest | null;
  detailRequest: FlashQueueRequest | null;
  cancelled: boolean;
}

interface EnqueueFlashRequestInput {
  project_name: string;
  tag_name: string;
  board_type: string;
  firmware_path: string;
}

export const flashQueueAPI = {
  listEligibleDevices: () =>
    client.get<{ ok: boolean; devices: FlashEligibleDevice[] }>('/api/flash/devices'),

  enqueueRequest: (payload: EnqueueFlashRequestInput) =>
    client.post<{ ok: boolean; request: FlashQueueRequest }>('/api/flash/requests', payload),

  getActiveRequest: () =>
    client.get<{ ok: boolean; request: FlashQueueRequest | null }>('/api/flash/requests/active'),

  listHistory: (params?: { page?: number; limit?: number; status?: string }) =>
    client.get<{
      ok: boolean;
      items: FlashQueueRequest[];
      page: number;
      limit: number;
      total: number;
    }>('/api/flash/requests', { params }),

  getRequestDetail: (requestId: number) =>
    client.get<{ ok: boolean; request: FlashQueueRequest }>(`/api/flash/requests/${requestId}`),

  cancelRequest: (requestId: number) =>
    client.post<{ ok: boolean; request: FlashQueueRequest }>(`/api/flash/requests/${requestId}/cancel`),

  verifyCancelOutcome: async (requestId: number): Promise<FlashCancelVerification> => {
    const [activeResult, detailResult] = await Promise.allSettled([
      client.get<{ ok: boolean; request: FlashQueueRequest | null }>('/api/flash/requests/active'),
      client.get<{ ok: boolean; request: FlashQueueRequest }>(`/api/flash/requests/${requestId}`),
    ]);

    const activeRequest =
      activeResult.status === 'fulfilled' ? activeResult.value.data.request : null;
    const detailRequest =
      detailResult.status === 'fulfilled' ? detailResult.value.data.request : null;

    const cancelled =
      detailRequest?.status === 'cancelled'
      || (!activeRequest || activeRequest.id !== requestId) && detailRequest?.status !== 'waiting';

    return {
      activeRequest,
      detailRequest,
      cancelled: Boolean(cancelled),
    };
  },

  stopLiveSession: (requestId: number) =>
    client.post<{ ok: boolean; request: FlashQueueRequest }>(`/api/flash/requests/${requestId}/stop-live`),
};
