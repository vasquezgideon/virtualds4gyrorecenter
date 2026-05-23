"""
Gyro Offset Middleware - DS4 motion correction
FINAL VERSION (pyvigem, no vgamepad)
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
    from pyvigem import VDS4Gamepad
    VG_OK = True
except Exception:
    VG_OK = False


DS4_IDS  = [(0x054C, 0x05C4), (0x054C, 0x09CC), (0x054C, 0x0CE6)]
GYRO_OFF = 13
ACC_OFF  = 19


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Gyro Offset")
        self.root.geometry("460x500")

        self.running = False
        self.hid_dev = None
        self.gamepad = None
        self.path = None

        self.off_p = self.off_y = self.off_r = 0

        self.v_raw_p = tk.StringVar(value="0")
        self.v_raw_y = tk.StringVar(value="0")
        self.v_raw_r = tk.StringVar(value="0")

        self.v_cor_p = tk.StringVar(value="0")
        self.v_cor_y = tk.StringVar(value="0")
        self.v_cor_r = tk.StringVar(value="0")

        self.v_status = tk.StringVar(value="Stopped")
        self.v_device = tk.StringVar(value="Scanning...")

        self.build()
        self.scan()

    def build(self):
        tk.Label(self.root, text="GYRO OFFSET", font=("Courier", 16, "bold")).pack()

        tk.Label(self.root, textvariable=self.v_device).pack()
        tk.Label(self.root, textvariable=self.v_status).pack()

        self.table = tk.Frame(self.root)
        self.table.pack()

        for i, t in enumerate(["Axis", "Raw", "Corrected"]):
            tk.Label(self.table, text=t).grid(row=0, column=i)

        axes = ["PITCH", "YAW", "ROLL"]
        self.raw = [self.v_raw_p, self.v_raw_y, self.v_raw_r]
        self.cor = [self.v_cor_p, self.v_cor_y, self.v_cor_r]

        for r, name in enumerate(axes, 1):
            tk.Label(self.table, text=name).grid(row=r, column=0)
            tk.Label(self.table, textvariable=self.raw[r-1]).grid(row=r, column=1)
            tk.Label(self.table, textvariable=self.cor[r-1]).grid(row=r, column=2)

        tk.Button(self.root, text="RECENTER", command=self.recenter).pack(fill="x")
        tk.Button(self.root, text="START/STOP", command=self.toggle).pack(fill="x")

    def scan(self):
        if not hid:
            self.v_device.set("hid missing")
            return

        for vid, pid in DS4_IDS:
            for d in hid.enumerate(vid, pid):
                self.path = d["path"]
                self.v_device.set("DS4 found")
                return

        self.v_device.set("No DS4 found")

    def recenter(self):
        self.off_p = int(self.v_raw_p.get())
        self.off_y = int(self.v_raw_y.get())
        self.off_r = int(self.v_raw_r.get())

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        if not VG_OK:
            messagebox.showerror("Error", "pyvigem missing")
            return

        if not self.path:
            messagebox.showerror("Error", "No controller found")
            return

        self.hid_dev = hid.device()
        self.hid_dev.open_path(self.path)
        self.hid_dev.set_nonblocking(True)

        self.gamepad = VDS4Gamepad()

        self.running = True
        self.v_status.set("Running")

        threading.Thread(target=self.loop, daemon=True).start()

    def stop(self):
        self.running = False
        try:
            if self.hid_dev:
                self.hid_dev.close()
        except:
            pass
        self.v_status.set("Stopped")

    def loop(self):
        while self.running:
            data = self.hid_dev.read(64)
            if not data:
                time.sleep(0.002)
                continue

            try:
                gx, gy, gz = struct.unpack_from("<hhh", bytes(data), GYRO_OFF)
                ax, ay, az = struct.unpack_from("<hhh", bytes(data), ACC_OFF)
            except:
                continue

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
                self.gamepad.motion(
                    accel_x=ax, accel_y=ay, accel_z=az,
                    gyro_pitch=cp, gyro_yaw=cy, gyro_roll=cr
                )
                self.gamepad.update()
            except:
                pass

            time.sleep(0.004)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
