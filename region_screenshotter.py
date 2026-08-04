"""
Reliable region screenshot tool for Windows.

Hotkeys:
- F7  : choose capture region
- F8  : capture saved region
- Esc : cancel region selection

Install:
    pip install mss pillow pynput
"""

import json
import queue
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk

from mss import mss
from PIL import Image
from pynput import keyboard


BASE_DIR = Path(__file__).resolve().parent
SAVE_DIR = BASE_DIR / "screenshots"
CONFIG_PATH = BASE_DIR / "screenshot_config.json"


class RegionSelector:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.result = None
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

    def select(self):
        self.result = None

        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.30)

        screen_w = overlay.winfo_screenwidth()
        screen_h = overlay.winfo_screenheight()
        overlay.geometry(f"{screen_w}x{screen_h}+0+0")
        overlay.configure(bg="black")

        canvas = tk.Canvas(overlay, highlightthickness=0, bg="black", cursor="crosshair")
        canvas.pack(fill="both", expand=True)

        canvas.create_text(
            20,
            20,
            anchor="nw",
            text="Выдели область мышью. Esc — отмена",
            fill="white",
            font=("Segoe UI", 16, "bold"),
        )

        def on_press(event):
            self.start_x = event.x
            self.start_y = event.y
            if self.rect_id is not None:
                canvas.delete(self.rect_id)
            self.rect_id = canvas.create_rectangle(
                self.start_x,
                self.start_y,
                self.start_x,
                self.start_y,
                outline="white",
                width=2,
                dash=(6, 4),
            )

        def on_drag(event):
            if self.rect_id is not None:
                canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

        def on_release(event):
            x1 = min(self.start_x, event.x)
            y1 = min(self.start_y, event.y)
            x2 = max(self.start_x, event.x)
            y2 = max(self.start_y, event.y)

            if abs(x2 - x1) >= 5 and abs(y2 - y1) >= 5:
                self.result = (x1, y1, x2, y2)
            else:
                self.result = None

            try:
                overlay.grab_release()
            except Exception:
                pass
            overlay.destroy()

        def on_escape(_event=None):
            self.result = None
            try:
                overlay.grab_release()
            except Exception:
                pass
            overlay.destroy()

        overlay.bind("<Escape>", on_escape)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        overlay.focus_force()
        overlay.lift()
        overlay.grab_set()
        self.root.wait_window(overlay)
        return self.result


class ScreenshotApp:
    def __init__(self):
        SAVE_DIR.mkdir(parents=True, exist_ok=True)

        self.root = tk.Tk()
        self.root.withdraw()

        self.region = self.load_region()
        self.command_queue = queue.Queue()
        self.is_selecting = False
        self.listener = None

    def load_region(self):
        if not CONFIG_PATH.exists():
            return None
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            region = data.get("region")
            if (
                isinstance(region, list)
                and len(region) == 4
                and all(isinstance(v, int) for v in region)
            ):
                return tuple(region)
        except Exception:
            pass
        return None

    def save_region(self):
        CONFIG_PATH.write_text(
            json.dumps({"region": list(self.region) if self.region else None}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def choose_region(self):
        if self.is_selecting:
            return

        self.is_selecting = True
        try:
            selector = RegionSelector(self.root)
            region = selector.select()
            if region:
                self.region = tuple(int(v) for v in region)
                self.save_region()
                print(f"[OK] Область сохранена: {self.region}")
            else:
                print("[INFO] Выбор области отменён.")
        except Exception as e:
            print(f"[ERROR] Не удалось выбрать область: {e}")
        finally:
            self.is_selecting = False

    def capture_region(self):
        if self.is_selecting:
            return

        if not self.region:
            print("[INFO] Сначала задай область: F7")
            return

        x1, y1, x2, y2 = self.region
        width = x2 - x1
        height = y2 - y1

        if width <= 0 or height <= 0:
            print("[ERROR] Область битая. Выбери заново: F7")
            return

        output_path = SAVE_DIR / f"screenshot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png"

        try:
            with mss() as sct:
                shot = sct.grab({
                    "left": x1,
                    "top": y1,
                    "width": width,
                    "height": height,
                })
                image = Image.frombytes("RGB", shot.size, shot.rgb)
                image.save(output_path)
            print(f"[OK] Скрин сохранён: {output_path}")
        except Exception as e:
            print(f"[ERROR] Не удалось сделать скрин: {e}")

    def on_key_press(self, key):
        try:
            if key == keyboard.Key.f7:
                self.command_queue.put("choose_region")
            elif key == keyboard.Key.f8:
                self.command_queue.put("capture")
        except Exception as e:
            print(f"[ERROR] Ошибка клавиатуры: {e}")

    def process_queue(self):
        while not self.command_queue.empty():
            command = self.command_queue.get()
            if command == "choose_region":
                self.choose_region()
            elif command == "capture":
                self.capture_region()

        self.root.after(50, self.process_queue)

    def start_listener(self):
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.daemon = True
        self.listener.start()

    def run(self):
        print("=" * 60)
        print("Скриншотер запущен")
        print("F7  -> выбрать область")
        print("F8  -> сделать скрин")
        print(f"Папка: {SAVE_DIR}")
        print(f"Конфиг: {CONFIG_PATH}")
        if self.region:
            print(f"Текущая область: {self.region}")
        else:
            print("Область пока не задана.")
        print("=" * 60)

        self.start_listener()
        self.root.after(50, self.process_queue)
        self.root.mainloop()


if __name__ == "__main__":
    try:
        ScreenshotApp().run()
    except KeyboardInterrupt:
        sys.exit(0)
