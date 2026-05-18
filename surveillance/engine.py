import os
import cv2
import uuid
import threading
import time
import numpy as np
import torch
from django.utils import timezone
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from ultralytics import YOLO
from deepface import DeepFace

# -- Path Configuration --
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YOLO_PATH = os.path.join(BASE_DIR, 'surveillance', 'models', 'yolo11n_models', 'yolo11n-pose.pt')

# -- Detection Constants --
DEEPFACE_MODEL      = "Facenet512"
DEEPFACE_BACKEND    = "retinaface"
THRESHOLD           = 0.30
FACE_CHECK_INTERVAL = 15   # was 5 — run face recognition less often
MATCH_COOLDOWN_SEC  = 15

# ── Shared JPEG frame buffer ──────────────────────────────────────────────────
_frame_buffers: dict = {}   # { camera_id: bytes }
_frame_locks:   dict = {}   # { camera_id: threading.Lock }

def set_frame(camera_id, jpeg_bytes):
    if camera_id not in _frame_locks:
        _frame_locks[camera_id] = threading.Lock()
    with _frame_locks[camera_id]:
        _frame_buffers[camera_id] = jpeg_bytes

def get_frame(camera_id):
    lock = _frame_locks.get(camera_id)
    if not lock:
        return None
    with lock:
        return _frame_buffers.get(camera_id)

def clear_frame_buffer(camera_id):
    _frame_buffers.pop(camera_id, None)
    _frame_locks.pop(camera_id, None)


# -- YOLO Model Loader (singleton) --
_yolo_model = None
_yolo_lock  = threading.Lock()

def get_yolo_model():
    global _yolo_model
    with _yolo_lock:
        if _yolo_model is None:
            model  = YOLO(YOLO_PATH)
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            model.to(device)
            _yolo_model = model
        return _yolo_model


# -- Broadcast Helpers --
def _broadcast(data):
    try:
        cl = get_channel_layer()
        if cl:
            async_to_sync(cl.group_send)(
                "surveillance_group",
                {"type": "forward_to_websocket", "payload": data},
            )
    except Exception:
        pass

def _broadcast_camera_status(camera_id, camera_name, location, status):
    _broadcast({
        "type":      "CAMERA_STATUS",
        "camera_id": camera_id,
        "name":      camera_name,
        "location":  location,
        "status":    status,
        "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    try:
        cl = get_channel_layer()
        if cl:
            async_to_sync(cl.group_send)(
                "camera_group",
                {
                    "type": "forward_to_websocket",
                    "payload": {
                        "type":      "CAMERA_STATUS",
                        "camera_id": camera_id,
                        "name":      camera_name,
                        "location":  location,
                        "status":    status,
                        "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                }
            )
    except Exception:
        pass

def _save_snapshot(frame):
    try:
        filename  = f"{uuid.uuid4().hex}.jpg"
        save_dir  = os.path.join(settings.MEDIA_ROOT, 'snapshots')
        os.makedirs(save_dir, exist_ok=True)
        full_path = os.path.join(save_dir, filename)
        cv2.imwrite(full_path, frame)
        return f"snapshots/{filename}"
    except Exception as e:
        print(f"[snapshot] Failed to save: {e}")
        return None

def _save_detection(camera_id, person_count, action, matched_target_id=None,
                    matched_name='', assignment_id=None, frame=None):
    try:
        import django
        django.setup() if not django.apps.registry.apps.ready else None
    except Exception:
        pass

    try:
        from surveillance.models import DetectionEvent, TargetPerson, TargetAssignment, Notification

        target_obj     = TargetPerson.objects.filter(pk=matched_target_id).first() if matched_target_id else None
        assignment_obj = TargetAssignment.objects.filter(pk=assignment_id).first()  if assignment_id    else None

        snapshot_relative_path = _save_snapshot(frame) if frame is not None else None

        event = DetectionEvent(
            timestamp=timezone.now(),
            person_count=person_count,
            action=action,
            matched_target=target_obj,
            matched_target_name=matched_name,
            camera_id=camera_id,
            related_assignment=assignment_obj,
            verification_status='pending' if (matched_target_id or action != 'Normal') else 'unreviewed',
        )

        if snapshot_relative_path:
            event.frame_snapshot.name = snapshot_relative_path

        event.save()

        channel_layer = get_channel_layer()

        if matched_target_id and assignment_obj and assignment_obj.assigned_by:
            notif = Notification.objects.create(
                recipient=assignment_obj.assigned_by,
                notification_type='verification',
                title=f"Target Found: {matched_name}",
                message=f"Detected on Camera {camera_id}",
                related_assignment=assignment_obj,
                related_event=event,
            )
            try:
                async_to_sync(channel_layer.group_send)(
                    f"user_{assignment_obj.assigned_by.id}",
                    {
                        "type":            "send_notification",
                        "notification_id": notif.id,
                        "title":           notif.title,
                        "message":         notif.message,
                        "created_at":      notif.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
            except Exception as e:
                print(f"[notification] WebSocket send failed: {e}")

        if matched_target_id and target_obj and target_obj.uploaded_by:
            supervisor = target_obj.uploaded_by
            if not (assignment_obj and assignment_obj.assigned_by == supervisor):
                try:
                    Notification.objects.create(
                        recipient=supervisor,
                        notification_type='detection',
                        title=f"Your target detected: {matched_name}",
                        message=f"Detected on Camera {camera_id}",
                        related_event=event,
                    )
                    async_to_sync(channel_layer.group_send)(
                        f"user_{supervisor.id}",
                        {
                            "type":       "send_notification",
                            "title":      f"Target Detected: {matched_name}",
                            "message":    f"Detected on Camera {camera_id}",
                            "created_at": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
                except Exception as e:
                    print(f"[supervisor notify] Failed: {e}")

        if action != 'Normal':
            try:
                async_to_sync(channel_layer.group_send)(
                    "surveillance_group",
                    {
                        "type": "forward_to_websocket",
                        "payload": {
                            "type":      "ACTIVITY_LOG",
                            "action":    action,
                            "camera_id": camera_id,
                            "timestamp": event.timestamp.strftime("%H:%M:%S")
                        }
                    }
                )
            except Exception as e:
                print(f"[activity_log] Broadcast failed: {e}")

        print(f"[_save_detection] Saved event {event.id} | action={action} | target={matched_name}")
        return event.id

    except Exception as e:
        import traceback
        print(f"[_save_detection] ERROR: {e}")
        traceback.print_exc()
        return None


# ── RTSP Frame Grabber ────────────────────────────────────────────────────────
# FIX #1 — THE MAIN CAUSE OF LAG
# OpenCV's VideoCapture queues frames internally. For RTSP, by the time your
# main loop calls cap.read() it gets a frame that is several seconds old.
# The fix is a dedicated "grabber" thread that calls cap.grab() as fast as
# possible (discarding every frame), so the internal buffer is always empty.
# The main thread calls cap.retrieve() only when it actually needs a frame,
# guaranteeing it gets the *latest* frame every time.
class RTSPFrameGrabber(threading.Thread):
    """
    Continuously drains the RTSP buffer by calling cap.grab() in a tight loop.
    The CameraThread calls retrieve() whenever it needs the latest frame.
    Without this, OpenCV accumulates many seconds of buffered frames, making
    the live feed appear heavily delayed.
    """
    def __init__(self, cap: cv2.VideoCapture):
        super().__init__(daemon=True)
        self.cap     = cap
        self.running = True
        self.lock    = threading.Lock()
        self._ok     = False   # whether the last grab succeeded

    def run(self):
        while self.running:
            with self.lock:
                self._ok = self.cap.grab()
            # Yield the CPU for ~1 ms so we don't spin at 100 %
            time.sleep(0.001)

    def retrieve(self):
        """Return (ret, frame) for the most recently grabbed frame."""
        with self.lock:
            if not self._ok:
                return False, None
            return self.cap.retrieve()

    def stop(self):
        self.running = False


# -- Face Recognition Worker Thread --
class DeepFaceWorker(threading.Thread):
    def __init__(self, on_match):
        super().__init__(daemon=True)
        self._queue           = []
        self._lock            = threading.Lock()
        self._event           = threading.Event()
        self.on_match         = on_match
        self.targets          = []
        self.running          = True
        self._embedding_cache = {}
        self._last_match_time = {}

    def submit(self, frame, boxes):
        h, w = frame.shape[:2]
        crops = []
        for (x1, y1, x2, y2) in boxes:
            pw, ph = int((x2 - x1) * 0.2), int((y2 - y1) * 0.2)
            nx1 = max(0, int(x1) - pw)
            ny1 = max(0, int(y1) - ph)
            nx2 = min(w, int(x2) + pw)
            ny2 = min(h, int(y2) + ph)
            crops.append(frame[ny1:ny2, nx1:nx2])

        with self._lock:
            self._queue = [(frame.copy(), crops)]
        self._event.set()

    def run(self):
        while self.running:
            self._event.wait()
            self._event.clear()
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue.pop(0)
            if not item or not self.targets:
                continue

            full_frame, crops = item

            for target in self.targets:
                if (time.time() - self._last_match_time.get(target['id'], 0)) < MATCH_COOLDOWN_SEC:
                    continue
                if target['id'] not in self._embedding_cache:
                    try:
                        res = DeepFace.represent(
                            img_path=target['path'],
                            model_name=DEEPFACE_MODEL,
                            detector_backend=DEEPFACE_BACKEND
                        )
                        if res:
                            self._embedding_cache[target['id']] = np.array(res[0]['embedding'])
                    except Exception as e:
                        print(f"[DeepFace] Target embed failed: {e}")
                        continue

                t_vec = self._embedding_cache.get(target['id'])
                if t_vec is None:
                    continue

                for crop in crops:
                    try:
                        res = DeepFace.represent(
                            img_path=crop,
                            model_name=DEEPFACE_MODEL,
                            detector_backend=DEEPFACE_BACKEND
                        )
                        if res:
                            c_vec = np.array(res[0]['embedding'])
                            dist  = 1.0 - (
                                np.dot(c_vec, t_vec) /
                                (np.linalg.norm(c_vec) * np.linalg.norm(t_vec))
                            )
                            if dist <= THRESHOLD:
                                self._last_match_time[target['id']] = time.time()
                                self.on_match(
                                    target['id'],
                                    target['name'],
                                    target.get('assignment_id'),
                                    full_frame.copy()
                                )
                                break
                    except Exception:
                        continue

    def stop(self):
        self.running = False
        self._event.set()


# -- Main Camera Thread --
class CameraThread(threading.Thread):
    def __init__(self, camera_obj):
        super().__init__(daemon=True)
        self.camera_id    = camera_obj.id
        self.camera_name  = camera_obj.name
        self.location     = camera_obj.location
        self.index_or_url = camera_obj.index_or_url
        self.running      = False
        self._deepface    = DeepFaceWorker(self._on_face_match)

    def _on_face_match(self, tid, name, aid, frame):
        _broadcast({
            "type":      "TARGET_MATCH",
            "name":      name,
            "camera":    self.camera_name,
            "camera_id": self.camera_id
        })
        _save_detection(
            camera_id=self.camera_id,
            person_count=1,
            action='Normal',
            matched_target_id=tid,
            matched_name=name,
            assignment_id=aid,
            frame=frame,
        )

    def analyze_pose(self, keypoints_data):
        if keypoints_data is None or len(keypoints_data.xy) == 0:
            return "Normal"
        try:
            kp   = keypoints_data.xy[0].cpu().numpy()
            conf = keypoints_data.conf[0].cpu().numpy()
            if conf[0] > 0.5:
                head_y        = kp[0][1]
                left_hand_up  = conf[9]  > 0.5 and kp[9][1]  < head_y
                right_hand_up = conf[10] > 0.5 and kp[10][1] < head_y
                if left_hand_up or right_hand_up:
                    return "HAND WAVING"
            if conf[0] > 0.5 and (conf[11] > 0.5 or conf[12] > 0.5):
                hip_y = np.mean([kp[i][1] for i in [11, 12] if conf[i] > 0.5])
                if kp[0][1] > hip_y:
                    return "FALL DETECTED"
        except Exception as e:
            print(f"Pose Analysis Error: {e}")
        return "Normal"

    def refresh_targets(self):
        try:
            from surveillance.models import TargetPerson, TargetAssignment
            active = TargetPerson.objects.filter(is_found=False).distinct()
            t_list = []
            for t in active:
                ass = TargetAssignment.objects.filter(target=t).last()
                t_list.append({
                    "id":            t.pk,
                    "name":          t.name,
                    "path":          t.image.path,
                    "assignment_id": ass.pk if ass else None
                })
            self._deepface.targets = t_list
        except Exception as e:
            print(f"[refresh_targets] Error: {e}")

    def _update_db_status(self, status):
        try:
            from camera.models import Camera
            if status == 'online':
                Camera.objects.filter(pk=self.camera_id).update(
                    status='online',
                    last_seen_at=timezone.now(),
                    went_offline_at=None,
                )
            else:
                Camera.objects.filter(pk=self.camera_id).update(
                    status='offline',
                    went_offline_at=timezone.now(),
                )
        except Exception as e:
            print(f"[Camera {self.camera_id}] DB status update failed: {e}")

    # ── FIX #2: open_capture — correct RTSP tuning flags ─────────────────────
    def _open_capture(self, src):
        """
        Open a VideoCapture with settings tuned for low-latency RTSP.

        Key changes vs the original:
          • os.environ OPENCV_FFMPEG_CAPTURE_OPTIONS — set before cap opens,
            forces TCP transport and a tiny probe/analyse duration so FFMPEG
            does not spend 2-5 s analysing the stream before the first frame.
          • CAP_PROP_BUFFERSIZE = 1 — keep only one frame in OpenCV's internal
            queue (the RTSPFrameGrabber drains the rest continuously).
          • No CAP_DSHOW for RTSP — CAP_DSHOW is a Windows-only flag for USB /
            DirectShow devices; using it with an RTSP URL silently falls back
            to FFMPEG anyway but can add 500 ms of extra overhead.
        """
        if isinstance(src, int):
            # Local USB / DirectShow camera (Windows)
            cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        else:
            # RTSP / network stream — force FFMPEG with TCP + tiny buffer
            # These environment variables are read by OpenCV's FFMPEG wrapper
            # before the connection is established, so they must be set first.
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;tcp"           # use TCP (more reliable than UDP)
                "|fflags;nobuffer"             # disable FFMPEG input buffering
                "|flags;low_delay"             # minimise decoder delay
                "|max_delay;0"                 # drop frames rather than buffer
                "|analyzeduration;100000"      # probe only 0.1 s (default = 5 s)
                "|probesize;500000"            # 500 KB probe (default = 5 MB)
            )
            cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Short open/read timeouts so a dead stream is detected quickly
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5_000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5_000)
        return cap

    def run(self):
        self.running = True
        model = get_yolo_model()
        src   = int(self.index_or_url) if self.index_or_url.isdigit() else self.index_or_url

        self._deepface.start()
        self.refresh_targets()

        frame_count       = 0
        last_action_save  = 0
        consecutive_fails = 0
        MAX_FAILS         = 10
        is_online         = False

        # ── FIX #1: open capture + start the grabber thread ──────────────────
        cap     = self._open_capture(src)
        grabber = None   # only used for RTSP sources

        if not isinstance(src, int):
            # Start the background grabber that keeps the RTSP buffer drained.
            # Without this, cap.read() returns whatever frame OpenCV queued
            # first — often several seconds behind real-time.
            grabber = RTSPFrameGrabber(cap)
            grabber.start()

        while self.running:
            # ── Read the latest frame ─────────────────────────────────────────
            try:
                if grabber is not None:
                    # RTSP path: grabber already called cap.grab(); just retrieve
                    ret, frame = grabber.retrieve()
                else:
                    # Local USB camera: simple blocking read is fine
                    ret, frame = cap.read()
            except Exception as e:
                print(f"[Camera {self.camera_id}] read exception: {e}")
                ret, frame = False, None

            # ── Handle bad frame ──────────────────────────────────────────────
            if not ret or frame is None:
                consecutive_fails += 1

                if is_online and consecutive_fails == 1:
                    is_online = False
                    self._update_db_status('offline')
                    _broadcast_camera_status(self.camera_id, self.camera_name,
                                             self.location, 'offline')

                if consecutive_fails >= MAX_FAILS:
                    print(f"[Camera {self.camera_id}] Too many failures, reconnecting…")
                    # Stop the old grabber before releasing the capture
                    if grabber:
                        grabber.stop()
                        grabber.join(timeout=2)
                        grabber = None
                    try:
                        cap.release()
                    except Exception:
                        pass
                    time.sleep(2)
                    cap = self._open_capture(src)
                    if not isinstance(src, int):
                        grabber = RTSPFrameGrabber(cap)
                        grabber.start()
                    consecutive_fails = 0
                    if not cap.isOpened():
                        time.sleep(5)
                else:
                    time.sleep(0.1)
                continue

            # ── Good frame ────────────────────────────────────────────────────
            consecutive_fails = 0

            if not is_online:
                is_online = True
                self._update_db_status('online')
                _broadcast_camera_status(self.camera_id, self.camera_name,
                                         self.location, 'online')

            # FIX #3 — encode at quality 60 (was 75).
            # For MJPEG streaming, 60 is visually very similar to 75 but
            # produces ~30 % smaller payloads, reducing browser lag.
            try:
                _, _buf = cv2.imencode(
                    '.jpg', frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 60]
                )
                set_frame(self.camera_id, _buf.tobytes())
            except Exception:
                pass

            # ── FIX #4 — resize before YOLO inference ─────────────────────────
            # Running YOLO on full 1080p / 720p frames is the #2 CPU bottleneck
            # after the buffer lag. Resizing to 640×360 before inference gives
            # the same detection quality (YOLO was trained at 640 px) at a
            # fraction of the cost, keeping the processing loop fast enough to
            # serve fresh frames to the browser.
            try:
                if frame_count % 2 == 0:
                    # Resize only for inference; keep `frame` full-res for snapshots
                    infer_frame = cv2.resize(frame, (640, 360),
                                             interpolation=cv2.INTER_LINEAR)

                    results = model.predict(source=infer_frame, conf=0.50, verbose=False)

                    if results and len(results[0].boxes) > 0:
                        person_count = len(results[0].boxes)
                        action       = self.analyze_pose(results[0].keypoints)

                        if action != "Normal":
                            _broadcast({
                                "type":      "ALARM",
                                "action":    action,
                                "camera":    self.camera_name,
                                "camera_id": self.camera_id
                            })
                            if time.time() - last_action_save > 5:
                                threading.Thread(
                                    target=_save_detection,
                                    args=(self.camera_id, person_count, action),
                                    kwargs={"frame": frame.copy()},  # save full-res snapshot
                                    daemon=True
                                ).start()
                                last_action_save = time.time()

                        if frame_count % FACE_CHECK_INTERVAL == 0:
                            # Scale bounding boxes back to original resolution
                            # (inference was done on the resized frame, so the
                            #  boxes are in 640×360 coordinates)
                            orig_h, orig_w = frame.shape[:2]
                            sx = orig_w / 640
                            sy = orig_h / 360
                            raw_boxes = results[0].boxes.xyxy.cpu().numpy()
                            boxes = [
                                (b[0]*sx, b[1]*sy, b[2]*sx, b[3]*sy)
                                for b in raw_boxes
                            ]
                            self._deepface.submit(frame, boxes)

                        _broadcast({"type": "STAT_UPDATE",
                                    "count": person_count,
                                    "camera_id": self.camera_id})
                    else:
                        _broadcast({"type": "STAT_UPDATE",
                                    "count": 0,
                                    "camera_id": self.camera_id})

            except Exception as e:
                print(f"[Camera {self.camera_id}] Processing error: {e}")

            if frame_count % 600 == 0:
                self.refresh_targets()

            frame_count += 1

        # ── Cleanup ───────────────────────────────────────────────────────────
        if grabber:
            grabber.stop()
            grabber.join(timeout=2)
        try:
            cap.release()
        except Exception:
            pass

        clear_frame_buffer(self.camera_id)
        self._deepface.stop()
        self._update_db_status('offline')
        _broadcast_camera_status(self.camera_id, self.camera_name,
                                  self.location, 'offline')
        print(f"[Camera {self.camera_id}] Thread stopped cleanly.")

    def stop(self):
        self.running = False


# -- Engine Manager --
class EngineManager:
    def __init__(self):
        self._threads: dict = {}
        self._lock = threading.Lock()

    def start_camera(self, camera_obj):
        with self._lock:
            existing = self._threads.get(camera_obj.id)
            if existing and existing.is_alive():
                print(f"[EngineManager] Camera {camera_obj.id} already running, skipping.")
                return
            t = CameraThread(camera_obj)
            self._threads[camera_obj.id] = t
            t.start()
            print(f"[EngineManager] Started camera {camera_obj.id} ({camera_obj.name})")

    def stop_camera(self, camera_id):
        with self._lock:
            t = self._threads.pop(camera_id, None)
        if t:
            t.stop()
            t.join(timeout=3.0)
            print(f"[EngineManager] Stopped camera {camera_id}")

    def restart_camera(self, camera_obj):
        self.stop_camera(camera_obj.id)
        time.sleep(0.5)
        self.start_camera(camera_obj)

    def running_ids(self):
        with self._lock:
            return {cid for cid, t in self._threads.items() if t.is_alive()}

    def invalidate_target_cache(self):
        with self._lock:
            threads = list(self._threads.values())
        for t in threads:
            if t.is_alive() and hasattr(t, 'refresh_targets'):
                t.refresh_targets()


engine_manager = EngineManager()


def probe_camera_index(idx: int, timeout: float = 3.0) -> bool:
    result = [False]
    ev     = threading.Event()

    def _try():
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok, _ = cap.read()
            result[0] = ok
        cap.release()
        ev.set()

    threading.Thread(target=_try, daemon=True).start()
    ev.wait(timeout=timeout)
    return result[0]