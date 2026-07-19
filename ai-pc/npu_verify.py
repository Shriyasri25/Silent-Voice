"""
Silent Voice — NPU verification script

Run this FIRST on the venue's Qualcomm AI PC before attempting anything else
NPU-related. It checks whether the QNN (Qualcomm) execution provider is
actually available and reports what devices onnxruntime sees.

If this script doesn't show a QNN device cleanly within a few minutes,
STOP and fall back to your working camera pipeline (main_camera.py).
Don't sink demo time into debugging a broken NPU setup live.

Requires (only on the actual Snapdragon-powered AI PC, Windows ARM64):
  pip install onnxruntime onnxruntime-qnn

Run:
  python npu_verify.py
"""

import sys


def main():
    try:
        import onnxruntime as ort
    except ImportError:
        print("[FAIL] onnxruntime is not installed. Run: pip install onnxruntime")
        sys.exit(1)

    try:
        import onnxruntime_qnn as qnn_ep
    except ImportError:
        print("[FAIL] onnxruntime-qnn is not installed.")
        print("       Run: pip install onnxruntime-qnn")
        print("       Note: this package only works on Windows ARM64 with a")
        print("       Snapdragon NPU — it will not install/work on a normal x86 laptop.")
        sys.exit(1)

    print(f"[OK] onnxruntime-qnn version: {qnn_ep.__version__}")

    # Register the QNN execution provider library
    try:
        ep_lib_path = qnn_ep.get_library_path()
        lib_registration_name = "QNNExecutionProvider"
        ort.register_execution_provider_library(lib_registration_name, ep_lib_path)
        print(f"[OK] Registered QNN EP library from: {ep_lib_path}")
    except Exception as e:
        print(f"[FAIL] Could not register QNN EP library: {e}")
        sys.exit(1)

    # List all EP devices onnxruntime can see
    all_ep_devices = ort.get_ep_devices()
    print(f"\n[INFO] Found {len(all_ep_devices)} total EP device(s):")
    for dev in all_ep_devices:
        print(f"   - {dev.ep_name}")

    qnn_devices = [d for d in all_ep_devices if d.ep_name == lib_registration_name]

    if qnn_devices:
        print(f"\n[SUCCESS] Found {len(qnn_devices)} QNN (NPU) device(s) available.")
        print("You can proceed to try main_npu.py.")
    else:
        print("\n[FAIL] No QNN device found. NPU inference is NOT available on this machine.")
        print("This is expected on a normal x86/x64 laptop — QNN requires an actual")
        print("Snapdragon NPU (the Qualcomm-provided AI PC at the venue).")
        print("Fall back to main_camera.py — your working, verified pipeline.")
        sys.exit(1)


if __name__ == "__main__":
    main()
