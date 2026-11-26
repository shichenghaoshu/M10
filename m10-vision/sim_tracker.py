#!/usr/bin/env python3
"""
M10 Auto-Track Simulator — Mac 端实时跟踪仿真

检测后端（自动选择）:
  Priority 1: YOLOv8n (ultralytics) — 人+猫+狗 精确检测
  Priority 2: OpenCV HOG 行人检测 — 零下载、内置、CPU 友好
  Priority 3: OpenCV Haar 人脸检测 — 备用

采集 Mac 内置摄像头 → 检测 → NMS → IoU 多目标跟踪
→ BehaviorMachine 状态决策 → PID 运动解算 → 可视化叠加

按键: q 退出, s 急停/恢复, r 搜索/重置, m 切换检测模式
"""

import argparse
from pathlib import Path
import os
import time
import sys
import threading
from collections import deque

import cv2
import numpy as np

# ── 检测后端 ──
try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

# COCO 类别
PERSON_CLASS = 0
DOG_CLASS = 16
CAT_CLASS = 15
TRACK_CLASSES = {PERSON_CLASS, DOG_CLASS, CAT_CLASS}
CLASS_NAMES = {PERSON_CLASS: "person", DOG_CLASS: "dog", CAT_CLASS: "cat"}
CLASS_COLORS = {PERSON_CLASS: (56, 255, 56), DOG_CLASS: (255, 180, 56), CAT_CLASS: (56, 56, 255)}


# ═══════════════════════════════════════════════════════════════════
# 核心算法（与 m10_core C++ 实现逻辑一致）
# ═══════════════════════════════════════════════════════════════════

def compute_iou(box_a, box_b):
    x1 = max(box_a[0], box_b[0]); y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2]); y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def nms(detections, threshold=0.45):
    dets = sorted(detections, key=lambda d: d[1], reverse=True)
    kept = []
    for d in dets:
        if not any(d[0] == k[0] and compute_iou(d[2:6], k[2:6]) > threshold for k in kept):
            kept.append(d)
    return kept


class SimpleTracker:
    def __init__(self, match_iou=0.3, max_lost=30):
        self.match_iou = match_iou
        self.max_lost = max_lost
        self.tracks = []
        self.next_id = 1

    def update(self, detections, frame_w, frame_h):
        used = [False] * len(detections)
        for t in self.tracks:
            best_idx, best_iou = -1, self.match_iou
            for i, d in enumerate(detections):
                if used[i] or t["class_id"] != d[0]:
                    continue
                score = compute_iou(t["bbox"], d[2:6])
                if score > best_iou:
                    best_iou, best_idx = score, i
            if best_idx >= 0:
                d = detections[best_idx]; used[best_idx] = True
                t["bbox"] = d[2:6]
                t["center_x"] = (d[2] + d[4]) * 0.5 / max(frame_w, 1)
                t["center_y"] = (d[3] + d[5]) * 0.5 / max(frame_h, 1)
                t["confidence"] = d[1]
                t["area"] = max(0, d[4]-d[2]) * max(0, d[5]-d[3]) / max(frame_w*frame_h, 1)
                t["age"] += 1; t["lost"] = 0
            else:
                t["lost"] += 1; t["age"] += 1
        self.tracks = [t for t in self.tracks if t["lost"] <= self.max_lost]
        for i, d in enumerate(detections):
            if not used[i]:
                self.tracks.append({
                    "id": self.next_id, "class_id": d[0], "bbox": d[2:6],
                    "center_x": (d[2]+d[4])*0.5/max(frame_w,1),
                    "center_y": (d[3]+d[5])*0.5/max(frame_h,1),
                    "confidence": d[1],
                    "area": max(0,d[4]-d[2])*max(0,d[5]-d[3])/max(frame_w*frame_h,1),
                    "age": 1, "lost": 0,
                })
                self.next_id += 1
        return self.tracks


class BehaviorMachine:
    def __init__(self, center_dead_zone=0.12, target_area_min=0.05,
                 target_area_max=0.25, confidence_threshold=0.45, target_lost_frames=15):
        self.state = "IDLE"
        self.center_dead_zone = center_dead_zone
        self.target_area_min = target_area_min
        self.target_area_max = target_area_max
        self.confidence_threshold = confidence_threshold
        self.target_lost_frames = target_lost_frames
        self.lost_count = 0

    def request(self, new_state):
        if self.state != "EMERGENCY_STOP":
            self.state = new_state; self.lost_count = 0

    def emergency_stop(self):
        self.state = "EMERGENCY_STOP"

    def update(self, target, systems_ok=True):
        if self.state == "EMERGENCY_STOP":
            return "EMERGENCY_STOP", 0, 0
        if not systems_ok:
            self.state = "ERROR"; return "STOP", 0, 0
        if target is None or target.get("confidence", 0) < self.confidence_threshold:
            self.lost_count += 1
            if self.lost_count > self.target_lost_frames:
                self.state = "LOST"
            return "STOP", 0, 0
        self.lost_count = 0
        if self.state in ("IDLE", "LOST", "SEARCH"):
            self.state = "TRACK"
        cx = target["center_x"]; area = target["area"]
        linear, angular = 0, 0
        if area > self.target_area_max:
            linear = -300
        elif cx < 0.5 - self.center_dead_zone:
            angular = 250
        elif cx > 0.5 + self.center_dead_zone:
            angular = -250
        elif area < self.target_area_min:
            linear = 300 if target["confidence"] >= 0.6 else 180
        if abs(linear) > 0 or abs(angular) > 0:
            self.state = "FOLLOW"
        left = max(-1000, min(1000, linear - angular))
        right = max(-1000, min(1000, linear + angular))
        return self.state, left, right


# ═══════════════════════════════════════════════════════════════════
# 检测后端
# ═══════════════════════════════════════════════════════════════════

class YoloDetector:
    """YOLOv8n 检测人/猫/狗"""
    def __init__(self, model_name="yolov8n.pt", imgsz=640):
        self.model_name = model_name
        self.imgsz = imgsz
        self.model = None
        self._load()

    def _load(self):
        import os
        path = self.model_name
        if not os.path.exists(path):
            alt = str(Path(__file__).resolve().parent / "models" / "yolov8n_model.pt")
            if os.path.exists(alt):
                path = alt
        print(f"Loading YOLO: {path} ({os.path.getsize(path)/1e6:.1f}MB) ...")
        self.model = YOLO(path)
        print("YOLOv8n ready (CPU)")

    def detect(self, frame):
        if self.model is None:
            return []
        try:
            results = self.model(frame, verbose=False, imgsz=self.imgsz,
                                device="cpu", conf=0.25, iou=0.45)
        except Exception as e:
            print(f"YOLO error: {e}")
            return []
        dets = []
        total = 0
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            total = len(boxes)
            for box in boxes:
                cls_id = int(box.cls.item())
                conf = float(box.conf.item())
                if cls_id not in TRACK_CLASSES:
                    continue
                if conf < 0.25:
                    continue
                xyxy = box.xyxy[0].cpu().numpy()
                dets.append((cls_id, conf,
                             float(xyxy[0]), float(xyxy[1]),
                             float(xyxy[2]), float(xyxy[3])))
        if total == 0 and not hasattr(self, '_warned_empty'):
            self._warned_empty = True
            print("YOLO: no objects detected in frame (check lighting/angle)")
        return dets


class HogDetector:
    """OpenCV 内置 HOG+SVM 行人检测器，零下载"""
    def __init__(self):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.hit_threshold = 0.3  # lower = more detections
        print("HOG People Detector ready (built-in, CPU)")

    def detect(self, frame):
        rects, weights = self.hog.detectMultiScale(
            frame, winStride=(8, 8), padding=(16, 16), scale=1.05,
            hitThreshold=self.hit_threshold
        )
        dets = []
        for (x, y, bw, bh), weight in zip(rects, weights):
            conf = min(abs(weight) * 1.2, 0.99)
            dets.append((PERSON_CLASS, conf,
                         float(x), float(y), float(x + bw), float(y + bh)))
        if not dets and not hasattr(self, '_warned'):
            self._warned = True
            print("HOG: no person detected (stand in frame, ensure good lighting)")
        return dets


class HaarDetector:
    """OpenCV Haar 级联人脸检测，最轻量备用方案"""
    def __init__(self):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        print("Haar Face Detector ready (built-in, CPU)")

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(60, 60))
        return [(PERSON_CLASS, 0.70, float(x), float(y),
                 float(x + w), float(y + h)) for (x, y, w, h) in faces]


# ═══════════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════════

class TrackerApp:
    DETECTORS = ["yolo", "hog", "haar"]

    def __init__(self, camera_id=0, detector="auto", frame_w=640, frame_h=640):
        self.frame_w, self.frame_h = frame_w, frame_h
        self.cap = cv2.VideoCapture(camera_id)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera {camera_id}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        self._setup_detector(detector)
        self.tracker = SimpleTracker(match_iou=0.3, max_lost=30)
        self.behavior = BehaviorMachine()
        self.behavior.request("IDLE")
        self.emergency = False
        self.fps_hist = deque(maxlen=60)
        self.detect_hist = deque(maxlen=30)
        self.last_time = time.time()
        self.detector_idx = self.DETECTORS.index(self.detector_name)
        self.frame_count = 0

    def _setup_detector(self, detector):
        if detector == "auto":
            if HAS_YOLO:
                detector = "yolo"
            else:
                detector = "hog"

        self.detector_name = detector
        if detector == "yolo":
            self.detector = YoloDetector(
                model_name=str(Path(__file__).resolve().parent / "models" / "yolov8n_model.pt")
            )
            self.detector_label = "YOLOv8n"
        elif detector == "hog":
            self.detector = HogDetector()
            self.detector_label = "HOG+SVM"
        elif detector == "haar":
            self.detector = HaarDetector()
            self.detector_label = "Haar Face"
        else:
            raise ValueError(f"Unknown detector: {detector}")

    def _switch_detector(self):
        idx = (self.detector_idx + 1) % len(self.DETECTORS)
        name = self.DETECTORS[idx]
        if name == "yolo" and not HAS_YOLO:
            idx = (idx + 1) % len(self.DETECTORS)
            name = self.DETECTORS[idx]
        self.detector_idx = idx
        self.detector_name = name
        self._setup_detector(name)
        print(f"[SWITCH] Detector: {self.detector_label}")

    def run(self):
        print(f"\nDetector: {self.detector_label}")
        print("Controls: q=quit  s=emergency_stop  r=reset  m=switch_detector\n")
        cv2.namedWindow("M10 Auto-Track Simulator", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("M10 Auto-Track Simulator", 960, 540)

        while True:
            ret, frame = self.cap.read()
            if not ret:
                print("Camera read failed")
                break

            frame = cv2.flip(frame, 1)
            display = frame.copy()
            h, w = frame.shape[:2]
            dt = time.time() - self.last_time
            self.last_time = time.time()
            if dt > 0.001:
                self.fps_hist.append(1.0 / dt)
            fps = sum(self.fps_hist) / max(len(self.fps_hist), 1)

            # Step 1: 检测
            t0 = time.time()
            detections = self.detector.detect(frame)
            detect_ms = (time.time() - t0) * 1000
            self.detect_hist.append(detect_ms)
            avg_detect = sum(self.detect_hist) / len(self.detect_hist)

            # Step 2: NMS
            detections = nms(detections, threshold=0.45)

            # Step 3: 多目标跟踪
            tracks = self.tracker.update(detections, w, h)

            # Step 4: 行为决策
            active_target = self._select_target(tracks)
            state, left_speed, right_speed = self.behavior.update(
                active_target, systems_ok=not self.emergency
            )

            # Step 5: 可视化
            self._draw_overlay(display, w, h, tracks, active_target,
                               state, left_speed, right_speed, fps,
                               avg_detect, len(detections))
            self.frame_count += 1
            if self.frame_count % 30 == 0:
                tgt = "none" if active_target is None else \
                    f"#{active_target['id']}({active_target['confidence']:.2f})"
                print(f"[frame {self.frame_count}] fps={fps:.1f} "
                      f"det={len(detections)} trk={len(tracks)} "
                      f"tgt={tgt} state={state} | "
                      f"motor L={left_speed:+d} R={right_speed:+d}")

            cv2.imshow("M10 Auto-Track Simulator", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                self.emergency = not self.emergency
                if self.emergency:
                    self.behavior.emergency_stop()
                    print("[EMERGENCY STOP]")
                else:
                    self.behavior.request("IDLE")
                    print("[RESUME]")
            elif key == ord('r'):
                self.emergency = False
                self.behavior.request("IDLE")
                self.tracker = SimpleTracker(match_iou=0.3, max_lost=30)
                print("[RESET]")
            elif key == ord('m'):
                self._switch_detector()

        self.cap.release()
        cv2.destroyAllWindows()

    def _select_target(self, tracks):
        if not tracks:
            return None
        valid = [t for t in tracks
                 if 0.01 < t["area"] < 0.8 and t["confidence"] > 0.2]
        if not valid:
            return None
        valid.sort(key=lambda t: (t["confidence"] - 0.5) * 2.0
                   - abs(t["center_x"] - 0.5) * 0.5, reverse=True)
        return valid[0]

    def _draw_overlay(self, img, w, h, tracks, target, state, left, right,
                      fps, detect_ms, detect_count):
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, 68), (20, 20, 20), -1)
        img = cv2.addWeighted(overlay, 0.65, img, 0.35, 0)

        # 顶栏: FPS + State + Motor + Detector + Latency
        fps_c = (56, 255, 56) if fps > 8 else (56, 180, 255) if fps > 3 else (56, 56, 255)
        cv2.putText(img, f"FPS:{fps:.1f}", (6, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, fps_c, 1)

        state_c = ((56, 56, 255) if state in ("EMERGENCY_STOP", "ERROR", "LOST")
                   else (56, 255, 200) if state in ("FOLLOW", "TRACK")
                   else (200, 200, 56))
        cv2.putText(img, f"{state}", (100, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, state_c, 2)

        cv2.putText(img, f"L{left:+d} R{right:+d}", (4, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)

        cv2.putText(img, f"{self.detector_label} {detect_ms:.0f}ms", (4, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 160, 160), 1)

        cv2.putText(img, f"det:{detect_count} trk:{len(tracks)}", (280, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 160, 160), 1)

        # 中心十字
        cv2.line(img, (w//2-30, h//2), (w//2+30, h//2), (100, 100, 100), 1)
        cv2.line(img, (w//2, h//2-30), (w//2, h//2+30), (100, 100, 100), 1)

        # 死区框
        dz = int(self.behavior.center_dead_zone * w)
        cv2.rectangle(img, (w//2-dz, h//2-dz), (w//2+dz, h//2+dz),
                      (80, 80, 80), 1)

        # 目标箭头（PID 控制方向指示）
        if target and state in ("FOLLOW", "TRACK"):
            cx = int(target["center_x"] * w)
            cy = int(target["center_y"] * h)
            if left != 0 or right != 0:
                end_x = w//2 + int((left + right) * 0.1)
                end_y = h//2 + int((right - left) * 0.05)
                cv2.arrowedLine(img, (w//2, h//2), (end_x, end_y),
                                (255, 255, 100), 2, tipLength=0.3)

        # 检测框
        for t in tracks:
            clr = CLASS_COLORS.get(t["class_id"], (200, 200, 200))
            x1, y1, x2, y2 = map(int, t["bbox"])
            is_target = target and t["id"] == target["id"]
            thick = 3 if is_target else 1
            cv2.rectangle(img, (x1, y1), (x2, y2), clr, thick)
            label = f"{CLASS_NAMES.get(t['class_id'],'?')}#{t['id']} {t['confidence']:.2f}"
            ty = y1 - 8 if y1 > 16 else y2 + 16
            cv2.putText(img, label, (x1, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.35, clr, 1)
            if is_target:
                cx, cy = (x1+x2)//2, (y1+y2)//2
                cv2.circle(img, (cx, cy), 22, (56, 56, 255), 2)

        # 控制提示
        hints = "q:quit  s:stop  r:reset  m:mode"
        tw, _ = cv2.getTextSize(hints, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)[0]
        cv2.putText(img, hints, (w - tw - 8, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 120), 1)
        return img


def main():
    parser = argparse.ArgumentParser(description="M10 Auto-Track Simulator")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--detector", default="auto",
                        choices=["auto", "yolo", "hog", "haar"])
    parser.add_argument("--width", type=int, default=640)
    args = parser.parse_args()

    try:
        app = TrackerApp(camera_id=args.camera, detector=args.detector,
                         frame_w=args.width, frame_h=args.width)
        app.run()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
