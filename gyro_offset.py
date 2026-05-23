"""
Gyro Offset Middleware
Reads virtual DS4 from Sunshine, applies pitch/roll/yaw offset, outputs corrected DS4 via ViGEm.
Requirements: pip install hid vgamepad
Also needs HidHide installed to hide the original controller from RPCS3.
"""

import threading
import time
import struct
import tkinter as tk
from tkinter import ttk, messagebox
import sys

try:
    import hid
except ImportError:
    hid = None

try:
    import vgamepad as vg
except ImportError:
    vg = None

# DS4 USB HID identifiers
DS4_VENDORS = [
    (0x054C, 0x05C4),  # DualShock 4 v1
    (0x054C, 0x09CC),  # DualShock 4 v2
    (0x054C, 0x0CE6),  # DualSense
]

# Offsets in DS4 USB HID report (report ID 0x01)
# Gyro: 3 x int16 at bytes 13-18 (gyroX, gyroY, gyroZ)
# Accel: 3 x int16 at bytes 19-24
GYRO_OFFSET_BYTES = 13
ACCEL_OFFSET_BYTES = 19


class GyroOffsetApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gyro Offset Middleware")
        self.root.geometry("480x560")
        self.root.resizable(False, False)
        self.root.configure(bg="#0d0d0f")

        self.running = False
        self.thread = None
        self.device = None
        self.gamepad = None

        # Offsets (applied to raw gyro values)
        self.offset_pitch = 0
        self.offset_yaw = 0
        self.offset_roll = 0

        # Live values
        self.raw_pitch = tk.IntVar(value=0)
        self.raw_yaw = tk.IntVar(value=0)
        self.raw_roll = tk.IntVar(value=0)
        self.corrected_pitch = tk.IntVar(value=0)
        self.corrected_yaw = tk.IntVar(value=0)
        self.corrected_roll = tk.IntVar(value=0)
        self.status_text = tk.StringVar(value="Stopped")
        self.device_text = tk.StringVar(value="No device found")

        self._build_ui()
        self._scan_devices()

    def _build_ui(self):
        bg = "#0d0d0f"
        card = "#16181c"
        accent = "#00e5ff"
        muted = "#4a4d55"
        text = "#e8eaf0"
        danger = "#ff4757"
        success = "#2ed573"

        # Title
        tk.Label(self.root, text="GYRO OFFSET", font=("Courier New", 18, "bold"),
                 bg=bg, fg=accent).pack(pady=(18, 2))
        tk.Label(self.root, text="DS4 motion correction middleware",
                 font=("Courier New", 9), bg=bg, fg=muted).pack(pady=(0, 14))

        # Device card
        dev_frame = tk.Frame(self.root, bg=card, padx=16, pady=10)
        dev_frame.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(dev_frame, text="DEVICE", font=("Courier New", 8, "bold"),
                 bg=card, fg=muted).pack(anchor="w")
        tk.Label(dev_frame, textvariable=self.device_text, font=("Courier New", 10),
                 bg=card, fg=text, wraplength=400, justify="left").pack(anchor="w")

        # Status
        status_frame = tk.Frame(self.root, bg=card, padx=16, pady=10)
        status_frame.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(status_frame, text="STATUS", font=("Courier New", 8, "bold"),
                 bg=card, fg=muted).pack(anchor="w")
        self.status_label = tk.Label(status_frame, textvariable=self.status_text,
                                     font=("Courier New", 11, "bold"), bg=card, fg=success)
        self.status_label.pack(anchor="w")

        # Live values
        vals_frame = tk.Frame(self.root, bg=card, padx=16, pady=12)
        vals_frame.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(vals_frame, text="LIVE GYRO VALUES", font=("Courier New", 8, "bold"),
                 bg=card, fg=muted).pack(anchor="w", pady=(0, 8))

        for col, label in enumerate(["AXIS", "RAW", "CORRECTED"]):
            tk.Label(vals_frame, text=label, font=("Courier New", 8, "bold"),
                     bg=card, fg=muted, width=12, anchor="w").grid(row=0, column=col, sticky="w")

        axes = [
            ("PITCH", self.raw_pitch, self.corrected_pitch),
            ("YAW  ", self.raw_yaw, self.corrected_yaw),
            ("ROLL ", self.raw_roll, self.corrected_roll),
        ]
        for row, (name, raw, corr) in enumerate(axes, 1):
            tk.Label(vals_frame, text=name, font=("Courier New", 10),
                     bg=card, fg=text, width=12, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            tk.Label(vals_frame, textvariable=raw, font=("Courier New", 10),
                     bg=card, fg=muted, width=12, anchor="w").grid(row=row, column=1, sticky="w")
            tk.Label(vals_frame, textvariable=corr, font=("Courier New", 10),
                     bg=card, fg=accent, width=12, anchor="w").grid(row=row, column=2, sticky="w")

        # Recenter button
        self.recenter_btn = tk.Button(
            self.root, text="⊕  RECENTER GYRO",
            font=("Courier New", 12, "bold"),
            bg=accent, fg="#000000",
            activebackground="#00b8cc", activeforeground="#000000",
            relief="flat", cursor="hand2", pady=10,
            command=self._recenter
        )
        self.recenter_btn.pack(fill="x", padx=20, pady=(0, 8))

        tk.Label(self.root, text="Hold phone at your comfortable angle, then press recenter.",
                 font=("Courier New", 8), bg=bg, fg=muted, wraplength=420).pack()

        # Start/Stop button
        self.toggle_btn = tk.Button(
            self.root, text="▶  START",
            font=("Courier New", 12, "bold"),
            bg=success, fg="#000000",
            activebackground="#28c065", activeforeground="#000000",
            relief="flat", cursor="hand2", pady=10,
            command=self._toggle
        )
        self.toggle_btn.pack(fill="x", padx=20, pady=(12, 4))

        # Rescan
        tk.Button(
            self.root, text="RESCAN DEVICES",
            font=("Courier New", 9),
            bg=card, fg=muted,
            activebackground="#1e2026", activeforeground=text,
            relief="flat", cursor="hand2", pady=6,
            command=self._scan_devices
        ).pack(fill="x", padx=20, pady=(0, 4))

        # Deps warning
        if hid is None or vg is None:
            missing = []
            if hid is None:
                missing.append("hid")
            if vg is None:
                missing.append("vgamepad")
            warn = tk.Frame(self.root, bg="#2a1a1a", padx=12, pady=8)
            warn.pack(fill="x", padx=20, pady=(8, 0))
            tk.Label(warn, text=f"⚠ Missing: pip install {' '.join(missing)}",
                     font=("Courier New", 9), bg="#2a1a1a", fg=danger).pack(anchor="w")

    def _scan_devices(self):
        if hid is None:
            self.device_text.set("hid library not installed")
            return
        found = []
        for vendor_id, product_id in DS4_VENDORS:
            for dev in hid.enumerate(vendor_id, product_id):
                name = dev.get("product_string", "Unknown")
                path = dev.get("path", b"")
                found.append((name, path, vendor_id, product_id))
        if found:
            name, path, vid, pid = found[0]
            self.device_text.set(f"{name} (VID:{vid:04X} PID:{pid:04X})")
            self._device_path = path
        else:
            # Also scan all HID devices and look for DS4-like reports
            self.device_text.set("No DS4/DualSense found — is Sunshine streaming?")
            self._device_path = None

    def _recenter(self):
        """Capture current raw gyro as the new zero point."""
        self.offset_pitch = self.raw_pitch.get()
        self.offset_yaw = self.raw_yaw.get()
        self.offset_roll = self.raw_roll.get()

    def _toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self):
        if hid is None or vg is None:
            messagebox.showerror("Missing dependencies",
                                 "Run: pip install hid vgamepad\nAlso install ViGEmBus driver.")
            return
        if self._device_path is None:
            messagebox.showerror("No device", "No DS4 found. Start streaming first, then rescan.")
            return
        try:
            self.device = hid.device()
            self.device.open_path(self._device_path)
            self.device.set_nonblocking(True)
        except Exception as e:
            messagebox.showerror("HID Error", f"Could not open device:\n{e}")
            return
        try:
            self.gamepad = vg.VDS4Gamepad()
        except Exception as e:
            messagebox.showerror("ViGEm Error", f"Could not create virtual DS4:\n{e}\n\nIs ViGEmBus installed?")
            self.device.close()
            return

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.toggle_btn.config(text="■  STOP", bg="#ff4757", activebackground="#cc3a47")
        self.status_text.set("Running")
        self.status_label.config(fg="#2ed573")

    def _stop(self):
        self.running = False
        if self.device:
            try:
                self.device.close()
            except:
                pass
            self.device = None
        self.gamepad = None
        self.toggle_btn.config(text="▶  START", bg="#2ed573", activebackground="#28c065")
        self.status_text.set("Stopped")
        self.status_label.config(fg="#4a4d55")

    def _loop(self):
        """Main read/write loop."""
        while self.running:
            try:
                data = self.device.read(64)
            except Exception:
                self.root.after(0, lambda: self.status_text.set("Device disconnected"))
                self.running = False
                break

            if not data or len(data) < 25:
                time.sleep(0.001)
                continue

            # Parse gyro: 3 x int16 little-endian at bytes 13-18
            try:
                gx, gy, gz = struct.unpack_from("<hhh", bytes(data), GYRO_OFFSET_BYTES)
                ax, ay, az = struct.unpack_from("<hhh", bytes(data), ACCEL_OFFSET_BYTES)
            except struct.error:
                time.sleep(0.001)
                continue

            # DS4 axes: gx=pitch, gy=yaw, gz=roll (approximate, may vary by firmware)
            raw_p, raw_y, raw_r = gx, gy, gz

            corr_p = raw_p - self.offset_pitch
            corr_y = raw_y - self.offset_yaw
            corr_r = raw_r - self.offset_roll

            # Update UI (thread-safe)
            self.root.after(0, self.raw_pitch.set, raw_p)
            self.root.after(0, self.raw_yaw.set, raw_y)
            self.root.after(0, self.raw_roll.set, raw_r)
            self.root.after(0, self.corrected_pitch.set, corr_p)
            self.root.after(0, self.corrected_yaw.set, corr_y)
            self.root.after(0, self.corrected_roll.set, corr_r)

            # Write to virtual DS4
            try:
                # Pass through all buttons/sticks from original report
                # Buttons are at bytes 5-8 in DS4 report
                if len(data) >= 12:
                    # Left stick
                    lx = data[1] - 128
                    ly = data[2] - 128
                    rx = data[3] - 128
                    ry = data[4] - 128

                    self.gamepad.left_joystick(x_value_int=lx, y_value_int=ly)
                    self.gamepad.right_joystick(x_value_int=rx, y_value_int=ry)

                    # Triggers (bytes 7-8)
                    self.gamepad.left_trigger(value=data[7])
                    self.gamepad.right_trigger(value=data[8])

                # Set corrected motion
                self.gamepad.motion(
                    accel_x=ax, accel_y=ay, accel_z=az,
                    gyro_pitch=corr_p, gyro_yaw=corr_y, gyro_roll=corr_r
                )
                self.gamepad.update()
            except Exception:
                pass

            time.sleep(0.004)  # ~250hz polling


def main():
    root = tk.Tk()
    app = GyroOffsetApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
