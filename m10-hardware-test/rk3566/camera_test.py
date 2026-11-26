#!/usr/bin/env python3
import argparse
import sys

import cv2

DEFAULT_DEVICE = "/dev/video0"
DEFAULT_OUTPUT = "test_capture.jpg"


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a single test image from the camera.")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="Camera device path")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output image path")
    args = parser.parse_args()

    capture = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not capture.isOpened():
        print(f"ERROR: Failed to open camera device {args.device}.", file=sys.stderr)
        return 1

    ok, frame = capture.read()
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()

    print(f"Camera resolution: {width}x{height}")
    if not ok or frame is None:
        print("ERROR: Camera opened but no frame was captured.", file=sys.stderr)
        return 1

    if not cv2.imwrite(args.output, frame):
        print(f"ERROR: Failed to save capture to {args.output}.", file=sys.stderr)
        return 1

    print(f"Saved test image to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
