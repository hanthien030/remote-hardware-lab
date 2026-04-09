import { useCallback, useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';

const WS_URL = `${window.location.protocol}//${window.location.host}`;

export interface DeviceConnectedEvent {
  tag_name: string;
  port: string;
  type: string;
  status: 'connected';
}

export interface DeviceDisconnectedEvent {
  tag_name: string;
  port: string;
  status: 'disconnected';
}

export interface DeviceLockedEvent {
  tag_name: string;
  locked_by: string;
}

export interface DeviceUnlockedEvent {
  tag_name: string;
}

export interface FlashStartedEvent {
  tag_name: string;
  user: string;
}

export interface FlashDoneEvent {
  tag_name: string;
  user: string;
  success: boolean;
  log: string;
}

export interface FlashTaskUpdateEvent {
  request_id: number;
  tag_name: string;
  user: string;
  status: 'waiting' | 'flashing' | 'success' | 'failed' | 'cancelled';
  log: string;
}

export interface FlashSerialStartedEvent {
  request_id: number;
  tag_name: string;
  user: string;
  duration_seconds: number;
  baud_rate: number;
}

export interface FlashSerialChunkEvent {
  request_id: number;
  tag_name: string;
  user: string;
  chunk: string;
}

export interface FlashSerialFinishedEvent {
  request_id: number;
  tag_name: string;
  user: string;
  reason: string;
}

export interface FlashSerialPingEvent {
  request_id: number;
  tag_name: string;
  deadline_seconds: number;
}

let globalSocket: Socket | null = null;
let globalSocketToken: string | null = null;

function currentToken(): string | null {
  return localStorage.getItem('token');
}

function getSocket(): Socket {
  const token = currentToken();

  if (globalSocket && globalSocketToken !== token) {
    globalSocket.disconnect();
    globalSocket = null;
  }

  if (!globalSocket) {
    globalSocketToken = token;
    globalSocket = io(WS_URL, {
      path: '/socket.io/',
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
      auth: token ? { token } : undefined,
    });
  }

  return globalSocket;
}

export function useDeviceSocket() {
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    socketRef.current = getSocket();
    return () => {
      // Keep singleton alive across component mounts.
    };
  }, []);

  const onDeviceConnected = useCallback((cb: (data: DeviceConnectedEvent) => void) => {
    const socket = getSocket();
    socket.on('device_connected', cb);
    return () => socket.off('device_connected', cb);
  }, []);

  const onDeviceDisconnected = useCallback((cb: (data: DeviceDisconnectedEvent) => void) => {
    const socket = getSocket();
    socket.on('device_disconnected', cb);
    return () => socket.off('device_disconnected', cb);
  }, []);

  const onDeviceLocked = useCallback((cb: (data: DeviceLockedEvent) => void) => {
    const socket = getSocket();
    socket.on('device_locked', cb);
    return () => socket.off('device_locked', cb);
  }, []);

  const onDeviceUnlocked = useCallback((cb: (data: DeviceUnlockedEvent) => void) => {
    const socket = getSocket();
    socket.on('device_unlocked', cb);
    return () => socket.off('device_unlocked', cb);
  }, []);

  const onFlashStarted = useCallback((cb: (data: FlashStartedEvent) => void) => {
    const socket = getSocket();
    socket.on('flash_started', cb);
    return () => socket.off('flash_started', cb);
  }, []);

  const onFlashDone = useCallback((cb: (data: FlashDoneEvent) => void) => {
    const socket = getSocket();
    socket.on('flash_done', cb);
    return () => socket.off('flash_done', cb);
  }, []);

  const onFlashTaskUpdate = useCallback((cb: (data: FlashTaskUpdateEvent) => void) => {
    const socket = getSocket();
    socket.on('flash_task_update', cb);
    return () => socket.off('flash_task_update', cb);
  }, []);

  const onFlashSerialStarted = useCallback((cb: (data: FlashSerialStartedEvent) => void) => {
    const socket = getSocket();
    socket.on('flash_serial_started', cb);
    return () => socket.off('flash_serial_started', cb);
  }, []);

  const onFlashSerialChunk = useCallback((cb: (data: FlashSerialChunkEvent) => void) => {
    const socket = getSocket();
    socket.on('flash_serial_chunk', cb);
    return () => socket.off('flash_serial_chunk', cb);
  }, []);

  const onFlashSerialFinished = useCallback((cb: (data: FlashSerialFinishedEvent) => void) => {
    const socket = getSocket();
    socket.on('flash_serial_finished', cb);
    return () => socket.off('flash_serial_finished', cb);
  }, []);

  const onFlashSerialPing = useCallback((cb: (data: FlashSerialPingEvent) => void) => {
    const socket = getSocket();
    socket.on('flash_serial_ping', cb);
    return () => socket.off('flash_serial_ping', cb);
  }, []);

  const emitFlashSerialViewStart = useCallback((requestId: number) => {
    getSocket().emit('flash_serial_view_start', { request_id: requestId });
  }, []);

  const emitFlashSerialViewStop = useCallback((requestId: number) => {
    getSocket().emit('flash_serial_view_stop', { request_id: requestId });
  }, []);

  const emitFlashSerialPong = useCallback((requestId: number) => {
    getSocket().emit('flash_serial_pong', { request_id: requestId });
  }, []);

  return {
    onDeviceConnected,
    onDeviceDisconnected,
    onDeviceLocked,
    onDeviceUnlocked,
    onFlashStarted,
    onFlashDone,
    onFlashTaskUpdate,
    onFlashSerialStarted,
    onFlashSerialChunk,
    onFlashSerialFinished,
    onFlashSerialPing,
    emitFlashSerialViewStart,
    emitFlashSerialViewStop,
    emitFlashSerialPong,
  };
}
