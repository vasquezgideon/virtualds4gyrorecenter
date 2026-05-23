"""
Gyro Offset Middleware - DS4 motion correction
pip install hidapi vgamepad pyinstaller
"""

import threading
import time
import struct
import tkinter as tk
from tkinter import messagebox

try:
    import hid
except ImportError:
    try:
        import hidapi as hid
    except ImportError:
        hid = None

try:
    import vgamepad as vg
    VGAMEPAD_OK = True
except ImportError:
    VGAMEPAD_OK = False

DS4_IDS   = [(0x054C, 0x05C4), (0x054C, 0x09CC), (0x054C, 0x0CE6)]
GYRO_OFF  = 13
ACCEL_OFF = 19

BG     = "#0d0d0f"
CARD   = "#16181c"
ACCENT = "#00e5ff"
MUTED  = "#4a4d55"
FG     = "#e8eaf0"
GREEN  = "#2ed573"
RED    = "#ff4757"
FONT   = "Courier New"


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Gyro Offset")
        self.root.geometry("460x570")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        self.running = False
        self.thread  = None
        self.hid_dev = None
        self.gamepad = None
        self._path   = None
        self.off_p = self.off_y = self.off_r = 0

        self.v_raw_p  = tk.StringVar(value="0")
        self.v_raw_y  = tk.StringVar(value="0")
        self.v_raw_r  = tk.StringVar(value="0")
        self.v_cor_p  = tk.StringVar(value="0")
        self.v_cor_y  = tk.StringVar(value="0")
        self.v_cor_r  = tk.StringVar(value="0")
        self.v_status = tk.StringVar(value="Stopped")
        self.v_device = tk.StringVar(value="Scanning…")

        self._build()
        self._scan()

    def _card(self, pady_top=0):
        f = tk.Frame(self.root, bg=CARD, padx=16, pady=10)
        f.pack(fill="x", padx=20, pady=(pady_top, 6))
        return f

    def _build(self):
        tk.Label(self.root, text="GYRO OFFSET",
                 font=(FONT, 18, "bold"), bg=BG, fg=ACCENT).pack(pady=(16, 2))
        tk.Label(self.root, text="DS4 motion correction middleware",
                 font=(FONT, 9), bg=BG, fg=MUTED).pack(pady=(0, 10))

        d = self._card()
        tk.Label(d, text="DEVICE", font=(FONT, 8, "bold"), fg=MUTED, bg=CARD).pack(anchor="w")
        tk.Label(d, textvariable=self.v_device, font=(FONT, 10),
                 fg=FG, bg=CARD, wraplength=400, justify="left").pack(anchor="w")

        s = self._card()
        tk.Label(s, text="STATUS", font=(FONT, 8, "bold"), fg=MUTED, bg=CARD).pack(anchor="w")
        self.status_lbl = tk.Label(s, textvariable=self.v_status,
                                   font=(FONT, 11, "bold"), fg=MUTED, bg=CARD)
        self.status_lbl.pack(anchor="w")

        v = self._card()
        tk.Label(v, text="LIVE GYRO VALUES", font=(FONT, 8, "bold"),
                 fg=MUTED, bg=CARD).pack(anchor="w", pady=(0, 6))
        tbl = tk.Frame(v, bg=CARD)
        tbl.pack(anchor="w")

        for col, txt in enumerate(["AXIS", "RAW", "CORRECTED"]):
            tk.Label(tbl, text=txt, font=(FONT, 8, "bold"),
                     fg=MUTED, bg=CARD, width=13, anchor="w").grid(row=0, column=col, sticky="w")

        for r, (name, rv, cv) in enumerate([
            ("PITCH", self.v_raw_p, self.v_cor_p),
            ("YAW",   self.v_raw_y, self.v_cor_y),
            ("ROLL",  self.v_raw_r, self.v_cor_r),
        ], 1):
            tk.Label(tbl, text=name, font=(FONT, 10),
                     fg=FG, bg=CARD, width=13, anchor="w").grid(row=r, column=0, sticky="w", pady=2)
            tk.Label(tbl, textvariable=rv, font=(FONT, 10),
                     fg=MUTED, bg=CARD, width=13, anchor="w").grid(row=r, column=1, sticky="w")
            tk.Label(tbl, textvariable=cv, font=(FONT, 10),
                     fg=ACCENT, bg=CARD, width=13, anchor="w").grid(row=r, column=2, sticky="w")

        tk.Button(self.root, text="⊕  RECENTER GYRO",
                  font=(FONT, 12, "bold"), bg=ACCENT, fg="#000",
                  activebackground="#00b8cc", activeforeground="#000",
                  relief="flat", cursor="hand2", pady=10,
                  command=self._recenter).pack(fill="x", padx=20, pady=(4, 2))
        tk.Label(self.root, text="Hold phone at comfortable angle → press Recenter.",
                 font=(FONT, 8), bg=BG, fg=MUTED).pack()

        self.btn = tk.Button(self.root, text="▶  START",
                             font=(FONT, 12, "bold"), bg=GREEN, fg="#000",
                             activebackground="#28c065", activeforeground="#000",
                             relief="flat", cursor="hand2", pady=10,
                             command=self._toggle)
        self.btn.pack(fill="x", padx=20, pady=(8, 4))

        tk.Button(self.root, text="RESCAN DEVICES",
                  font=(FONT, 9), bg=CARD, fg=MUTED,
                  activebackground="#1e2026", activeforeground=FG,
                  relief="flat", cursor="hand2", pady=6,
                  command=self._scan).pack(fill="x", padx=20)

        if not hid:
            self._warn("⚠  hidapi missing")
        if not VGAMEPAD_OK:
            self._warn("⚠  vgamepad missing — rebuild EXE")

    def _warn(self, msg):
        f = tk.Frame(self.root, bg="#1a0f0f", padx=12, pady=6)
        f.pack(fill="x", padx=20, pady=(4, 0))
        tk.Label(f, text=msg, font=(FONT, 9), bg="#1a0f0f", fg=RED).pack(anchor="w")

    def _scan(self):
        if not hid:
            self.v_device.set("hidapi not installed"); return
        self._path = None
        for vid, pid in DS4_IDS:
            for dev in hid.enumerate(vid, pid):
                self._path = dev["path"]
                name = dev.get("product_string", "DS4 Device")
                self.v_device.set(f"{name}  (VID:{vid:04X} PID:{pid:04X})")
                return
        self.v_device.set("No DS4 found — start streaming then rescan")

    def _recenter(self):
        try:
            self.off_p = int(self.v_raw_p.get())
            self.off_y = int(self.v_raw_y.get())
            self.off_r = int(self.v_raw_r.get())
        except ValueError:
            pass

    def _toggle(self):
        self._stop() if self.running else self._start()

    def _start(self):
        if not hid:
            messagebox.showerror("Missing", "hidapi not installed"); return
        if not VGAMEPAD_OK:
            messagebox.showerror("Missing", "vgamepad not installed — rebuild EXE"); return
        if self._path is None:
            messagebox.showerror("No device", "No DS4 found. Start streaming then rescan."); return
        try:
            self.hid_dev = hid.device()
            self.hid_dev.open_path(self._path)
            self.hid_dev.set_nonblocking(True)
        except Exception as e:
            messagebox.showerror("HID Error", str(e)); return
        try:
            self.gamepad = vg.VDS4Gamepad()
        except Exception as e:
            messagebox.showerror("ViGEm Error", f"{e}\n\nMake sure ViGEmBus driver is installed.\ngithub.com/nefarius/ViGEmBus/releases")
            self.hid_dev.close(); return

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.btn.config(text="■  STOP", bg=RED, activebackground="#cc3a47")
        self.v_status.set("Running")
        self.status_lbl.config(fg=GREEN)

    def _stop(self):
        self.running = False
        if self.hid_dev:
            try: self.hid_dev.close()
            except: pass
            self.hid_dev = None
        self.gamepad = None
        self.btn.config(text="▶  START", bg=GREEN, activebackground="#28c065")
        self.v_status.set("Stopped")
        self.status_lbl.config(fg=MUTED)

    def _loop(self):
        while self.running:
            try:
                data = self.hid_dev.read(64)
            except Exception:
                self.root.after(0, self.v_status.set, "Disconnected")
                self.running = False; break
            if not data or len(data) < 25:
                time.sleep(0.002); continue
            try:
                gx, gy, gz = struct.unpack_from("<hhh", bytes(data), GYRO_OFF)
                ax, ay, az = struct.unpack_from("<hhh", bytes(data), ACCEL_OFF)
            except struct.error:
                time.sleep(0.002); continue

            cp = gx - self.off_p
            cy = gy - self.off_y
            cr = gz - self.off_r

            self.root.after(0, self.v_raw_p.set, str(gx))
            self.root.after(0, self.v_raw_y.set, str(gy))
            self.root.after(0, self.v_raw_r.set, str(gz))
            self.root.after(0, self.v_cor_p.set, str(cp))
            self.root.after(0, self.v_cor_y.set, str(cy))
            self.root.after(0, self.v_cor_r.set, str(cr))

            try:
                self.gamepad.left_joystick(
                    x_value_int=data[1] - 128,
                    y_value_int=data[2] - 128)
                self.gamepad.right_joystick(
                    x_value_int=data[3] - 128,
                    y_value_int=data[4] - 128)
                self.gamepad.left_trigger(value=data[7] if len(data) > 8 else 0)
                self.gamepad.right_trigger(value=data[8] if len(data) > 8 else 0)
                self.gamepad.motion(
                    accel_x=ax, accel_y=ay, accel_z=az,
                    gyro_pitch=cp, gyro_yaw=cy, gyro_roll=cr)
                self.gamepad.update()
            except Exception:
                pass
            time.sleep(0.004)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
