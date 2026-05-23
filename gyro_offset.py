"""
Gyro Offset Middleware (FINAL STABLE VERSION)
- NO vgamepad
- NO pyvigem
- Uses native ViGEmBus DLL via ctypes
"""

import threading
import time
import struct
import ctypes
import tkinter as tk
from tkinter import messagebox

try:
    import hid
except ImportError:
    try:
        import hidapi as hid
    except ImportError:
        hid = None


DS4_IDS = [(0x054C, 0x05C4), (0x054C, 0x09CC), (0x054C, 0x0CE6)]
GYRO_OFF = 13
ACC_OFF = 19


# ---------------- ViGEm ----------------

vigem = None
client = None
target = None


def load_vigem():
    global vigem
    try:
        vigem = ctypes.WinDLL("ViGEmClient.dll")
        return True
    except Exception:
        return False


def init_vigem():
    global client, target

    if not vigem:
        return False

    vigem.vigem_alloc.restype = ctypes.c_void_p
    vigem.vigem_connect.restype = ctypes.c_int
    vigem.vigem_target_ds4_alloc.restype = ctypes.c_void_p
    vigem.vigem_target_add.restype = ctypes.c_int
    vigem.vigem_target_ds4_update.restype = ctypes.c_int

    client = vigem.vigem_alloc()
    if not client:
        return False

    if vigem.vigem_connect(client) != 0:
        return False

    target = vigem.vigem_target_ds4_alloc()
    if not target:
        return False

    vigem.vigem_target_add(client, target)

    return True


def send_motion(p, y, r):
    if not vigem or not target:
        return

    class DS4Report(ctypes.Structure):
        _fields_ = [
            ("report_id", ctypes.c_ubyte),
            ("gyro_pitch", ctypes.c_short),
            ("gyro_yaw", ctypes.c_short),
            ("gyro_roll", ctypes.c_short),
        ]

    report = DS4Report(0, int(p), int(y), int(r))

    vigem.vigem_target_ds4_update(client, target, ctypes.byref(report))


# ---------------- App ----------------

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Gyro Offset")
        self.root.geometry("420x300")

        self.running = False
        self.hid_dev = None
        self.path = None

        self.off_p = self.off_y = self.off_r = 0

        self.v_status = tk.StringVar(value="Stopped")
        self.v_device = tk.StringVar(value="Scanning...")

        tk.Label(root, textvariable=self.v_device).pack()
        tk.Label(root, textvariable=self.v_status).pack()

        tk.Button(root, text="RECENTER", command=self.recenter).pack(fill="x")
        tk.Button(root, text="START", command=self.toggle).pack(fill="x")

        self.scan()

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
        pass

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        if not self.path:
            messagebox.showerror("Error", "No DS4 found")
            return

        if not load_vigem():
            messagebox.showerror("Error", "ViGEmClient.dll missing")
            return

        if not init_vigem():
            messagebox.showerror("Error", "ViGEm init failed")
            return

        self.hid_dev = hid.device()
        self.hid_dev.open_path(self.path)
        self.hid_dev.set_nonblocking(True)

        self.running = True
        self.v_status.set("Running")

        threading.Thread(target=self.loop, daemon=True).start()

    def stop(self):
        self.running = False
        self.v_status.set("Stopped")

    def loop(self):
        while self.running:
            data = self.hid_dev.read(64)
            if not data:
                time.sleep(0.002)
                continue

            try:
                gx, gy, gz = struct.unpack_from("<hhh", bytes(data), GYRO_OFF)
            except:
                continue

            send_motion(gx, gy, gz)
            time.sleep(0.004)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
