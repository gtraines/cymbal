# ADR-001: Native vs Python/Cython Video Pipeline

**Status:** Accepted (initial evaluation; revisit after Phase 6 target-hardware profiling)  
**Date:** 2026-07  
**Author:** gtraines / Copilot  
**Profiling status:** Pending — Phase 6 instrumentation (`P6-loop-timing`, `P6-ipc-latency`) must be
run on a Raspberry Pi 3B+ before the performance conclusion can be confirmed.  Use the loop-timing
stats in `CymbalController.get_status()['timing']` and `data_age_ms` from the telemetry provider
to gather evidence.

---

## Context

Phase 4 extracts OSD/video rendering into a separate `cymbal-video` sidecar process
(`cymbal/video/video_service.py`).  The sidecar currently uses Python/OpenCV
(`opencv-python-headless`) for camera capture, telemetry overlay drawing, and frame
output.  The question is whether any part of this pipeline should be replaced with a
native executable (GStreamer, FFmpeg, or a compiled C/C++/Rust program) to:

1. Remove the remaining Python GIL from the video path entirely.
2. Improve throughput for higher-resolution or higher-fps workloads.
3. Enable hardware-accelerated video encoding on the Raspberry Pi (MMAL/V4L2M2M).

---

## Decision Drivers

| Factor | Weight | Notes |
|--------|--------|-------|
| RPi 3B+ resource constraints | High | 4× ARM Cortex-A53 cores, 1 GB RAM, no GPU encoder in headless Python |
| Current workload | Medium | 640×480 @ ≤30 fps OSD annotation; no encoding in the initial use case |
| Implementation complexity | High | GStreamer pipelines are powerful but require expertise and testing |
| Deployment simplicity | High | A Python sidecar is trivially deployable with pip; native requires build infra |
| Future CV workload | Low (now) | Target tracking / object detection would shift the balance significantly |

---

## Options Evaluated

### Option 1: Python/OpenCV (current implementation — `video_service.py`)

**Pros:**
- Already implemented and tested.
- All existing tests cover this path.
- `opencv-python-headless` is already a project dependency.
- GIL inside the video sidecar is not shared with the control process (separate OS process).
- Easy to extend: add picamera2, RTSP streaming, or recorder by swapping `VideoSink`.

**Cons:**
- Python GIL exists within the video process (matters only if adding parallelism inside the sidecar).
- `cv2.VideoCapture` is blocking; a dropped frame stalls the render loop briefly.
- No hardware-accelerated encoding (H.264 via MMAL).

**Verdict:** Sufficient for the current use case (640×480 OSD annotation, no encoding).

---

### Option 2: GStreamer Python bindings (`gi.repository.Gst`)

**Pros:**
- Hardware-accelerated pipelines on RPi via `omxh264enc` or `v4l2h264enc`.
- Threaded pipeline; camera decode and encoding run in GStreamer worker threads,
  decoupled from the Python OSD thread.
- Can mix Python OSD injection (via `appsrc/appsink`) with native encoding.

**Cons:**
- `python3-gst-1.0` / `gstreamer1.0-tools` add significant deployment complexity.
- OSD injection into a GStreamer pipeline requires `appsink` + OpenCV + `appsrc`,
  which is not simpler than the current approach.
- Debugging GStreamer pipelines is notoriously difficult.

**Verdict:** Worth re-evaluating if H.264 streaming becomes a requirement.

---

### Option 3: Pure GStreamer pipeline (no Python in video path)

A shell-level `gst-launch-1.0` pipeline with `textoverlay` for basic telemetry.

**Pros:**
- Fully native; no GIL; GPU-accelerated encode possible.
- Trivially streams over RTSP with `rtspclientsink`.

**Cons:**
- `textoverlay` is extremely limited (no compass widget, no background box, no
  dynamic multi-line layout).
- Feeding GPS/address data into a GStreamer pipeline requires a custom `GstElement`
  plugin in C or a `appsrc` bridge, adding complexity.
- Cannot reuse `OSDOverlay` at all.

**Verdict:** Not viable for the current OSD feature set without a custom plugin.

---

### Option 4: Rust or C sidecar with custom compositor

A native binary that receives `TelemetrySnapshot` datagrams, captures camera,
composites OSD text with a graphics library (Cairo, AGG, FreeType), and encodes.

**Pros:**
- Maximum performance; zero GIL; exact control over threading model.
- Can integrate hardware encoder APIs directly.

**Cons:**
- Significant new code (~3000+ lines for feature parity with OSDOverlay).
- Requires cross-compilation for ARMv7 / ARM64.
- Duplicates the IPC contract which must stay byte-for-byte compatible.

**Verdict:** Only justified if Python/OpenCV profiling proves to be the bottleneck
at 1080p+ or with concurrent CV workloads.

---

## Decision

**Keep Option 1 (Python/OpenCV) as the initial implementation.**

Rationale:
1. The video sidecar is already isolated in its own process (no shared GIL with the control loop).
2. 640×480 @ 30 fps OSD annotation is well within the Python/OpenCV capability on RPi 3B+.
3. The `VideoSink` abstraction allows swapping in a GStreamer or native backend later
   without changing the telemetry consumption or OSD rendering layers.
4. The IPC contract (`TelemetrySnapshotSchema`) is defined and stable; any future
   native sidecar only needs to implement the same socket reader.

---

## Consequence

If profiling on target hardware reveals that Python/OpenCV is a bottleneck (e.g.,
adding H.264 encoding, 1080p OSD, or real-time CV inference), the recommended
migration path is:

1. Benchmark `video_service.py` on the RPi 3B+ with `cProfile` + `time.perf_counter`
   instrumentation (Phase 6 work, see P6-adr-native todo).
2. If OpenCV frame rendering exceeds 5 ms average, evaluate GStreamer `appsrc/appsink`
   hybrid (Option 2) before committing to a full native rewrite.
3. If encoding or streaming is needed, evaluate a GStreamer-only pipeline with
   `textoverlay` for simple telemetry or a custom `GstElement` for full OSD (Option 3).
4. If CV inference is added, consider a `numpy`-based frame sharing mechanism
   (shared memory) between the video sidecar and a dedicated inference process,
   keeping the GIL separate for each.

This decision should be revisited in Phase 6 after `video_service.py` has been
profiled on target hardware.
