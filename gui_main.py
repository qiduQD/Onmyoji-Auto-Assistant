import cv2
import numpy as np
import subprocess
import secrets
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
import threading
import re
import sys
import os
import tempfile
import json


def get_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        # 打包后的路径
        return os.path.join(sys._MEIPASS, "assets", relative_path)

    # 源码运行时的路径：当前目录 + assets + 文件名
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", relative_path)
class GameBotGUI:
    BASE_WINDOW_W = 1600
    BASE_WINDOW_H = 900

    def __init__(self, root):
        self.root = root
        self.root.title("痒痒鼠小助手 mac版")
        self.is_mac = sys.platform == "darwin"
        self.root.geometry("1320x760")
        self.root.minsize(1200, 720)
        self.is_running = False
        self.rng = secrets.SystemRandom()
        self.window_x = 0
        self.window_y = 0
        self.window_w = self.BASE_WINDOW_W
        self.window_h = self.BASE_WINDOW_H
        self.target_app_name = tk.StringVar(value="阴阳师")
        self.use_absolute_coord_var = tk.BooleanVar(value=True)
        self.last_window_debug_ts = 0.0
        self.save_debug_crop_var = tk.BooleanVar(value=False)
        self.last_debug_save_ts = 0.0
        self.last_capture_permission_hint_ts = 0.0
        self.last_input_permission_hint_ts = 0.0
        self.last_activate_ts = 0.0
        self.window_snapshot_cache = None
        self.window_snapshot_cache_ts = 0.0
        self.window_snapshot_cache_ttl = 0.35
        self.debug_capture_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_last_capture.png")

        # --- UI 布局 ---
        app_frame = tk.Frame(root)
        app_frame.pack(pady=8)
        tk.Label(app_frame, text="目标进程:", font=("微软雅黑", 9)).grid(row=0, column=0, padx=5)
        self.target_app_entry = tk.Entry(app_frame, textvariable=self.target_app_name, width=24)
        self.target_app_entry.grid(row=0, column=1, padx=5)
        tk.Button(app_frame, text="置顶应用", command=self.activate_target_app, width=12).grid(row=0, column=2, padx=5)
        tk.Checkbutton(app_frame, text="保存最近一次裁剪图", variable=self.save_debug_crop_var).grid(row=0, column=3, padx=5)
        tk.Checkbutton(app_frame, text="使用绝对坐标(Cmd+Shift+4)", variable=self.use_absolute_coord_var).grid(row=0, column=4, padx=5)
        # 关卡名称与对应图片文件的映射
        self.level_map = {
            "英杰等普通耗3体副本": {
                "start": get_path("start_button_3.png"),
                "end": get_path("finish_mark.png")
            },
            "活动御魂300次": {
                "start": get_path("start_button_300.png"),
                "end": get_path("finish_mark_300.png")
            },
            "御魂十": {
                "start": get_path("start_button_6.png"),
                "end": get_path("finish_mark_10.png")
            },
            "御魂十一": {
                "start": get_path("start_button_12.png"),
                "end": get_path("finish_mark_11.png")
            },
            "御魂十二": {
                "start": get_path("start_button_30.png"),
                "end": get_path("finish_mark_11.png")
            },
            "御魂痴": {
                "start": get_path("start_button_chi.png"),
                "end": get_path("finish_mark_chi.png")
            }
        }

        # 2. 关卡选择区
        level_frame = tk.Frame(root)
        level_frame.pack(pady=10)
        tk.Label(level_frame, text="选择目标关卡:").grid(row=0, column=0)

        self.level_var = tk.StringVar()
        self.level_menu = ttk.Combobox(level_frame, textvariable=self.level_var, width=25, state="readonly")
        self.level_menu['values'] = list(self.level_map.keys())
        self.level_menu.current(0)  # 默认选第一个
        self.level_menu.grid(row=0, column=1, padx=5)

        # 3. 阈值设置
        tk.Label(root, text="识别阈值 (推荐 0.4-0.6):").pack(pady=2)
        self.conf_slider = tk.Scale(root, from_=0.1, to=1.0, resolution=0.05, orient=tk.HORIZONTAL, length=200)
        self.conf_slider.set(0.5)
        self.conf_slider.pack()

        # 4. 控制按钮
        self.btn_frame = tk.Frame(root)
        self.btn_frame.pack(pady=15)
        self.start_btn = tk.Button(self.btn_frame, text="开始挂机", command=self.start_task, bg="#4CAF50", fg="black",
                                   width=15)
        self.start_btn.grid(row=0, column=0, padx=10)
        self.stop_btn = tk.Button(self.btn_frame, text="停止运行", command=self.stop_task, state=tk.DISABLED,
                                  bg="#F44336", fg="white", width=15)
        self.stop_btn.grid(row=0, column=1, padx=10)
        self.combat_btn = tk.Button(self.btn_frame, text="结界突破", command=self.start_combat_option, bg="#2196F3", fg="black", width=15)
        self.combat_btn.grid(row=0, column=2, padx=10)
        self.hard28_btn = tk.Button(self.btn_frame, text="困难二十八", command=self.start_hard_28, bg="#FF9800", fg="black", width=15)
        self.hard28_btn.grid(row=0, column=3, padx=10)
        self.draw_roll_btn = tk.Button(self.btn_frame, text="绘卷模式", command=self.start_draw_roll, bg="#9C27B0", fg="black", width=15)
        self.draw_roll_btn.grid(row=0, column=4, padx=10)
        self.combat8_btn = tk.Button(self.btn_frame, text="阴阳寮突破", command=self.start_combat_option_8, bg="#607D8B", fg="black", width=15)
        self.combat8_btn.grid(row=1, column=2, padx=10, pady=8)
        self.mac_scan_btn = tk.Button(
            self.btn_frame,
            text="识别点击",
            command=self.start_mac_app_click,
            bg="#607D8B",
            fg="black",
            width=15
        )
        self.mac_scan_btn.grid(row=0, column=5, padx=10)
        self.count = 0  # 初始轮次为 0
        self.break_roll_count = 0  # 结界突破卷计数
        self.count_label = tk.Label(root, text="已成功运行: 0 轮", font=("微软雅黑", 12, "bold"), fg="#1E90FF")
        self.roll_label = tk.Label(root, text="结界突破卷: 0/30", font=("微软雅黑", 12, "bold"), fg="#FF4500")
        # --- 目标轮数设置区 ---
        limit_frame = tk.Frame(root)
        limit_frame.pack(pady=5)
        tk.Label(limit_frame, text="目标轮数 (0表示无限):").grid(row=0, column=0)

        self.limit_var = tk.StringVar()
        self.limit_entry = tk.Entry(limit_frame, textvariable=self.limit_var, width=10)
        self.limit_entry.insert(0, "0")  # 默认 0 轮
        self.limit_entry.grid(row=0, column=1, padx=5)
        self.count_label.pack(pady=5)
        self.roll_label.pack(pady=2)



        # 5. 日志窗口
        tk.Label(root, text="运行日志:").pack()
        self.log_area = scrolledtext.ScrolledText(root, width=128, height=25, font=("Consolas", 9))
        self.log_area.pack(pady=10)

        if self.is_mac:
            self.log("检测到 macOS，已切换为纯窗口识别模式。")
            self.log("当前坐标模式: 绝对屏幕坐标 (Cmd+Shift+4)。")
        else:
            self.log("当前不是 macOS，但程序已按 mac 逻辑加载；请在 mac 上运行。")

    # ================= 智能化工具函数 =================
    def log(self, message):
        now = time.strftime("%H:%M:%S", time.localtime())
        self.log_area.insert(tk.END, f"[{now}] {message}\n")
        self.log_area.see(tk.END)

    def _run_osascript(self, script):
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def _run_jxa(self, script):
        result = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def get_target_app_name(self):
        return self.target_app_entry.get().strip() or "阴阳师"

    def activate_target_app(self):
        now = time.time()
        if now - self.last_activate_ts < 1.0:
            return True
        app_name = self.get_target_app_name()
        script = f'tell application "{app_name}" to activate'
        code, _, err = self._run_osascript(script)
        if code != 0 and err:
            self.log(f"置顶应用失败: {err}")
            return False
        self.last_activate_ts = now
        time.sleep(0.3)
        return True

    def get_target_window_info(self):
        window_info = self.get_target_window_snapshot()
        if window_info is None:
            return None

        return window_info["x"], window_info["y"], window_info["w"], window_info["h"]

    def get_target_window_snapshot(self):
        now = time.time()
        if self.window_snapshot_cache and (now - self.window_snapshot_cache_ts) < self.window_snapshot_cache_ttl:
            return dict(self.window_snapshot_cache)

        app_name = self.get_target_app_name().replace('"', '\\"')
        self.activate_target_app()
        script = f'''
            ObjC.import("CoreGraphics");
            ObjC.import("Foundation");

            function main() {{
                const appName = "{app_name}";
                const normalize = (value) => String(value || "").toLowerCase().replace(/\\s+/g, "");
                const appNorm = normalize(appName);
                const options = $.kCGWindowListOptionAll;
                const windowList = $.CGWindowListCopyWindowInfo(options, $.kCGNullWindowID);

                if (!windowList) {{
                    return "";
                }}

                const windowCount = Number($.CFArrayGetCount(windowList));
                let best = null;
                const debugOwners = [];

                for (let index = 0; index < windowCount; index++) {{
                    const window = ObjC.deepUnwrap($.CFArrayGetValueAtIndex(windowList, index));

                    if (!window) {{
                        continue;
                    }}

                    const owner = String(window.kCGWindowOwnerName || "");
                    const name = String(window.kCGWindowName || "");
                    const ownerNorm = normalize(owner);
                    const nameNorm = normalize(name);

                    if (debugOwners.length < 8 && owner) {{
                        debugOwners.push({{
                            owner: owner,
                            name: name,
                            layer: Number(window.kCGWindowLayer || 0)
                        }});
                    }}

                    if (window.kCGWindowLayer !== 0) {{
                        continue;
                    }}
                    if (window.kCGWindowAlpha !== undefined && window.kCGWindowAlpha <= 0) {{
                        continue;
                    }}

                    const bounds = window.kCGWindowBounds || {{}};
                    const x = Math.round(bounds.X ?? bounds.x ?? 0);
                    const y = Math.round(bounds.Y ?? bounds.y ?? 0);
                    const w = Math.round(bounds.Width ?? bounds.width ?? 0);
                    const h = Math.round(bounds.Height ?? bounds.height ?? 0);

                    if (w <= 0 || h <= 0) {{
                        continue;
                    }}

                    let score = 0;
                    if (ownerNorm === appNorm || nameNorm === appNorm) {{
                        score = 4;
                    }} else if (ownerNorm.includes(appNorm) || appNorm.includes(ownerNorm)) {{
                        score = 3;
                    }} else if (nameNorm.includes(appNorm) || appNorm.includes(nameNorm)) {{
                        score = 2;
                    }}

                    if (score <= 0) {{
                        continue;
                    }}

                    const candidate = {{
                        id: Number(window.kCGWindowNumber),
                        x: x,
                        y: y,
                        w: w,
                        h: h,
                        owner: owner,
                        name: name,
                        score: score,
                        area: w * h
                    }};

                    if (!best || candidate.score > best.score || (candidate.score === best.score && candidate.area > best.area)) {{
                        best = candidate;
                    }}
                }}

                if (best) {{
                    return JSON.stringify(best);
                }}

                return JSON.stringify({{
                    id: 0,
                    debugOwners: debugOwners
                }});
            }}

            main();
        '''
        code, out, err = self._run_jxa(script)
        if code != 0 or not out:
            if err:
                self.log(f"读取窗口信息失败: {err}")
            return None

        try:
            window_info = json.loads(out)
        except Exception:
            self.log(f"窗口信息解析失败: {out}")
            return None

        try:
            x = int(window_info["x"])
            y = int(window_info["y"])
            w = int(window_info["w"])
            h = int(window_info["h"])
            window_id = int(window_info["id"])
        except (KeyError, TypeError, ValueError):
            debug_owners = window_info.get("debugOwners") if isinstance(window_info, dict) else None
            if debug_owners and (time.time() - self.last_window_debug_ts > 8):
                self.last_window_debug_ts = time.time()
                owner_tips = " | ".join([f"{item.get('owner', '')}/{item.get('name', '')}" for item in debug_owners])
                self.log(f"未匹配到目标窗口，当前可见窗口示例: {owner_tips}")
            fallback = self.get_target_window_snapshot_via_ax()
            if fallback is not None:
                return fallback
            self.log(f"窗口信息字段缺失: {window_info}")
            return None

        if window_id <= 0 or w <= 0 or h <= 0:
            fallback = self.get_target_window_snapshot_via_ax()
            if fallback is not None:
                self.window_snapshot_cache = dict(fallback)
                self.window_snapshot_cache_ts = time.time()
                return fallback
            return None

        window_info["x"] = x
        window_info["y"] = y
        window_info["w"] = w
        window_info["h"] = h
        window_info["id"] = window_id
        self.window_snapshot_cache = dict(window_info)
        self.window_snapshot_cache_ts = time.time()
        return window_info

    def get_target_window_snapshot_via_ax(self):
        app_name = self.get_target_app_name().replace('"', '\\"')
        script = f'''
            tell application "System Events"
                if not (exists process "{app_name}") then
                    return ""
                end if
                tell process "{app_name}"
                    if not (exists front window) then
                        return ""
                    end if
                    set p to position of front window
                    set s to size of front window
                    return (item 1 of p as string) & "," & (item 2 of p as string) & "," & (item 1 of s as string) & "," & (item 2 of s as string)
                end tell
            end tell
        '''
        code, out, err = self._run_osascript(script)
        if code != 0 or not out:
            if err and (time.time() - self.last_window_debug_ts > 8):
                self.last_window_debug_ts = time.time()
                self.log(f"辅助功能读取窗口失败: {err}")
            return None

        try:
            x, y, w, h = [int(v.strip()) for v in out.split(",")]
        except ValueError:
            return None

        if w <= 0 or h <= 0:
            return None

        self.log(f"已切换辅助功能窗口定位: {w}x{h} @ ({x},{y})")
        snapshot = {
            "id": -1,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "owner": app_name,
            "name": ""
        }
        self.window_snapshot_cache = dict(snapshot)
        self.window_snapshot_cache_ts = time.time()
        return snapshot

    def get_target_window_id(self):
        snapshot = self.get_target_window_snapshot()
        if snapshot is None:
            return None
        return snapshot["id"]

    def update_target_window_size(self):
        info = self.get_target_window_info()
        if info is None:
            self.log(f"无法获取目标应用窗口，使用默认窗口尺寸 {self.BASE_WINDOW_W}x{self.BASE_WINDOW_H}")
            self.window_x = 0
            self.window_y = 0
            self.window_w = self.BASE_WINDOW_W
            self.window_h = self.BASE_WINDOW_H
            return False

        self.window_x, self.window_y, self.window_w, self.window_h = info
        self.log(f"窗口坐标已校准: {self.window_w}x{self.window_h} @ ({self.window_x},{self.window_y})")
        return True

    def scale_x(self, base_x):
        if self.use_absolute_coord_var.get():
            return int(round(base_x))
        return self.window_x + int(round(base_x * self.window_w / self.BASE_WINDOW_W))

    def scale_y(self, base_y):
        if self.use_absolute_coord_var.get():
            return int(round(base_y))
        return self.window_y + int(round(base_y * self.window_h / self.BASE_WINDOW_H))

    def scale_point(self, base_x, base_y):
        return self.scale_x(base_x), self.scale_y(base_y)

    def map_capture_point_to_window(self, capture_x, capture_y, capture_w, capture_h, rect):
        if not isinstance(rect, dict):
            return capture_x, capture_y

        rx = int(rect.get("x", 0))
        ry = int(rect.get("y", 0))
        rw = max(1, int(rect.get("w", 1)))
        rh = max(1, int(rect.get("h", 1)))
        cw = max(1, int(capture_w))
        ch = max(1, int(capture_h))

        # Retina/多显示器场景下，截图坐标(像素)与窗口坐标(点)可能不一致，这里做统一映射。
        mapped_x = rx + int(round(capture_x * rw / cw))
        mapped_y = ry + int(round(capture_y * rh / ch))
        return mapped_x, mapped_y

    def random_scaled_offset(self, base_value, offset, base_size, current_size, origin=0):
        if self.use_absolute_coord_var.get():
            return self.rng.randint(base_value - offset, base_value + offset)
        scaled_center = origin + int(round(base_value * current_size / base_size))
        scaled_offset = max(1, int(round(offset * current_size / base_size)))
        return self.rng.randint(scaled_center - scaled_offset, scaled_center + scaled_offset)

    def save_latest_capture_for_debug(self, image, source="capture"):
        if image is None or not self.save_debug_crop_var.get():
            return
        try:
            cv2.imwrite(self.debug_capture_path, image)
            now = time.time()
            if now - self.last_debug_save_ts > 5:
                self.last_debug_save_ts = now
                self.log(f"调试图已更新({source}): {self.debug_capture_path}")
        except Exception as e:
            self.log(f"保存调试图失败: {e}")

    def log_capture_permission_hint(self, error_text=""):
        now = time.time()
        if now - self.last_capture_permission_hint_ts < 10:
            return
        self.last_capture_permission_hint_ts = now
        self.log("截图失败，可能缺少屏幕录制权限。请在 系统设置 -> 隐私与安全性 -> 屏幕录制 中勾选当前运行程序(终端/IDE/Python)。")
        if error_text:
            self.log(f"截图错误详情: {error_text}")

    def log_input_permission_hint(self, error_text=""):
        now = time.time()
        if now - self.last_input_permission_hint_ts < 10:
            return
        self.last_input_permission_hint_ts = now
        self.log("点击/拖拽失败，可能缺少辅助功能权限。请在 系统设置 -> 隐私与安全性 -> 辅助功能 中勾选当前运行程序(终端/IDE/Python)。")
        if error_text:
            self.log(f"输入注入错误详情: {error_text}")

    def match_template_in_window(self, screen, template):
        base_h, base_w = template.shape[:2]
        scale_x = self.window_w / self.BASE_WINDOW_W if self.BASE_WINDOW_W else 1.0
        scale_y = self.window_h / self.BASE_WINDOW_H if self.BASE_WINDOW_H else 1.0
        scale = min(scale_x, scale_y)

        candidate_scales = [1.0]
        if abs(scale - 1.0) > 0.03:
            candidate_scales.extend([scale, (scale + 1.0) / 2.0])

        best_val = -1.0
        best_loc = None
        best_size = None

        for current_scale in candidate_scales:
            resized_w = max(1, int(round(base_w * current_scale)))
            resized_h = max(1, int(round(base_h * current_scale)))
            if resized_w > screen.shape[1] or resized_h > screen.shape[0]:
                continue

            resized = cv2.resize(template, (resized_w, resized_h), interpolation=cv2.INTER_AREA if current_scale < 1.0 else cv2.INTER_CUBIC)
            res = cv2.matchTemplate(screen, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_size = (resized_w, resized_h)

        return best_val, best_loc, best_size

    def find_and_tap_on_capture(self, template_path, screen, rect, confidence=0.5, do_tap=True):
        template = cv2.imread(template_path)

        if template is None:
            self.log(f"错误：无法读取资源文件 -> {os.path.basename(template_path)}")
            return False

        if screen is None or rect is None:
            return False

        max_val, max_loc, matched_size = self.match_template_in_window(screen, template)
        if max_loc is None or matched_size is None:
            return False

        if max_val >= confidence:
            if do_tap:
                matched_w, matched_h = matched_size
                mw, mh = max(1, int(matched_w * 0.1)), max(1, int(matched_h * 0.1))
                tx_min = max_loc[0] + mw
                tx_max = max_loc[0] + max(mw, matched_w - mw)
                ty_min = max_loc[1] + mh
                ty_max = max_loc[1] + max(mh, matched_h - mh)
                tx = self.rng.randint(tx_min, tx_max)
                ty = self.rng.randint(ty_min, ty_max)

                click_x, click_y = self.map_capture_point_to_window(tx, ty, screen.shape[1], screen.shape[0], rect)
                self.click_abs(click_x, click_y)
                self.log(f"命中: {os.path.basename(template_path)} ({max_val:.2f})")
            return True
        return False

    def capture_target_window(self):
        info = self.get_target_window_snapshot()
        if info is None:
            return None, None

        x, y, w, h = info["x"], info["y"], info["w"], info["h"]
        fd, temp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        fd2, temp_full_path = tempfile.mkstemp(suffix=".png")
        os.close(fd2)

        try:
            window_id = info.get("id")
            if window_id is not None and int(window_id) > 0:
                result = subprocess.run(["screencapture", "-x", "-l", str(window_id), temp_path], capture_output=True, text=True)
            else:
                rect_cmds = [
                    ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", temp_path],
                    ["screencapture", "-x", "-D", "1", "-R", f"{x},{y},{w},{h}", temp_path],
                    ["screencapture", "-x", "-D", "2", "-R", f"{x},{y},{w},{h}", temp_path],
                    ["screencapture", "-x", "-D", "3", "-R", f"{x},{y},{w},{h}", temp_path],
                ]
                result = None
                for cmd in rect_cmds:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0:
                        break

            if result.returncode != 0:
                if result.stderr:
                    self.log(f"窗口截图失败: {result.stderr.strip()}")

                # 兜底：全屏截图后按窗口坐标裁剪，规避 -R 在部分系统上的失败
                full_cmds = [
                    ["screencapture", "-x", temp_full_path],
                    ["screencapture", "-x", "-D", "1", temp_full_path],
                    ["screencapture", "-x", "-D", "2", temp_full_path],
                    ["screencapture", "-x", "-D", "3", temp_full_path],
                ]
                fallback_full = None
                for cmd in full_cmds:
                    fallback_full = subprocess.run(cmd, capture_output=True, text=True)
                    if fallback_full.returncode == 0:
                        break

                if fallback_full.returncode != 0:
                    err = fallback_full.stderr.strip() if fallback_full and fallback_full.stderr else ""
                    if err:
                        self.log(f"全屏截图回退失败: {err}")
                    if "could not create image from display" in err or "not authorized" in err.lower():
                        self.log_capture_permission_hint(err)
                    return None, None

                full_img = cv2.imread(temp_full_path)
                if full_img is None:
                    self.log("全屏截图读取失败")
                    return None, None

                fh, fw = full_img.shape[:2]
                cropped = None
                chosen_scale = None
                for scale in (2.0, 1.5, 1.0):
                    sx = int(round(x * scale))
                    sy = int(round(y * scale))
                    sw = int(round(w * scale))
                    sh = int(round(h * scale))
                    ex = sx + sw
                    ey = sy + sh
                    if sx < 0 or sy < 0 or ex > fw or ey > fh:
                        continue
                    if sw < 50 or sh < 50:
                        continue
                    cropped = full_img[sy:ey, sx:ex]
                    chosen_scale = scale
                    break

                if cropped is None:
                    self.log(f"窗口裁剪失败: rect=({x},{y},{w},{h}), full=({fw}x{fh})")
                    return None, None

                self.log(f"已使用全屏裁剪回退截图(缩放{chosen_scale}x)")
                self.save_latest_capture_for_debug(cropped, source="fullscreen_crop")
                return cropped, info

            screen = cv2.imread(temp_path)
            self.save_latest_capture_for_debug(screen, source="window_capture")
            return screen, info
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_full_path):
                os.remove(temp_full_path)

    def click_abs(self, x, y):
        # 主路径: JXA + CGEvent，避免部分系统上 System Events click at 的 -25200 错误
        script = f'''
            ObjC.import("Quartz");
            ObjC.import("AppKit");
            const point = $.NSMakePoint({x}, {y});
            const down = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseDown, point, $.kCGMouseButtonLeft);
            const up = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseUp, point, $.kCGMouseButtonLeft);
            $.CGEventPost($.kCGHIDEventTap, down);
            $.CGEventPost($.kCGHIDEventTap, up);
        '''
        code, _, err = self._run_jxa(script)
        if code == 0:
            return True


    def adb_command(self, cmd: str):
        """在非 macOS 平台调用 adb；在 macOS 下将常见的 `shell input tap x y` 转为本地点击。

        返回: (returncode, stdout, stderr) 或在 mac 下返回 (0, "", "") 表示成功。
        """
        if not cmd:
            return -1, "", "empty-cmd"

        # 处理 macOS：将 adb 的 tap 映射为本地点击
        try:
            parts = cmd.strip().split()
        except Exception:
            parts = []

        if self.is_mac:
            # 支持: shell input tap x y
            if len(parts) >= 4 and parts[0] == "shell" and parts[1] == "input" and parts[2] == "tap":
                try:
                    x = int(parts[3])
                    y = int(parts[4]) if len(parts) > 4 else 0
                except Exception:
                    self.log(f"adb_command: 无法解析坐标: {cmd}")
                    return -1, "", "parse-error"
                self.log(f"(mac) 模拟 adb tap -> 本地点击: ({x},{y})")
                ok = self.click_abs(x, y)
                return (0, "", "") if ok else (-1, "", "click-failed")

        # 其它平台：尝试执行 adb 命令
        full_cmd = ["adb"] + cmd.strip().split()
        try:
            proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=20)
            out = proc.stdout.strip()
            err = proc.stderr.strip()
            if proc.returncode != 0:
                self.log(f"adb_command 失败: {' '.join(full_cmd)} -> {err}")
            return proc.returncode, out, err
        except FileNotFoundError:
            self.log("adb 未找到，请确保已安装并在 PATH 中。")
            return -1, "", "adb-not-found"
        except Exception as e:
            self.log(f"adb_command 异常: {e}")
            return -1, "", str(e)
        # 兜底: AppleScript click at
        fallback = f'tell application "System Events" to click at {{{x}, {y}}}'
        code2, _, err2 = self._run_osascript(fallback)
        if code2 == 0:
            return True

        combined_err = (err2 or err or "").strip()
        if combined_err:
            self.log(f"点击失败: {combined_err}")
            lower_err = combined_err.lower()
            if "-25200" in combined_err or "not authorized" in lower_err or "not permitted" in lower_err:
                self.log_input_permission_hint(combined_err)
        return False

    def drag_abs(self, start_x, start_y, end_x, end_y, steps=12):
        script = f'''
            ObjC.import("Quartz");
            ObjC.import("AppKit");
            function postMouse(type, pointX, pointY) {{
                const point = $.NSMakePoint(pointX, pointY);
                const event = $.CGEventCreateMouseEvent(null, type, point, $.kCGMouseButtonLeft);
                $.CGEventPost($.kCGHIDEventTap, event);
            }}
            postMouse($.kCGEventLeftMouseDown, {start_x}, {start_y});
            for (let i = 1; i <= {steps}; i++) {{
                const x = Math.round({start_x} + ({end_x} - {start_x}) * i / {steps});
                const y = Math.round({start_y} + ({end_y} - {start_y}) * i / {steps});
                postMouse($.kCGEventLeftMouseDragged, x, y);
            }}
            postMouse($.kCGEventLeftMouseUp, {end_x}, {end_y});
        '''
        code, _, err = self._run_jxa(script)
        if code != 0:
            if err:
                self.log(f"拖拽失败: {err}")
                lower_err = err.lower()
                if "-25200" in err or "not authorized" in lower_err or "not permitted" in lower_err:
                    self.log_input_permission_hint(err)
            # 兜底为双击两端点，避免流程直接卡死
            self.click_abs(start_x, start_y)
            time.sleep(0.15)
            self.click_abs(end_x, end_y)
            return False
        return True

    def tap_confirm(self):
        self.wait_for_image(get_path("confirm_button_2.png"), timeout=10, confidence=0.5, do_tap=True)


    def random_in_offset(self, base, offset=30):
        return self.rng.randint(base - offset, base + offset)

    def full_screen_random_tap(self):
        tx = self.rng.randint(self.scale_x(480), self.scale_x(1120))
        ty = self.rng.randint(self.scale_y(450), self.scale_y(720))
        self.log(f" -> [清理中] 随机点击: ({tx}, {ty})")
        self.click_abs(tx, ty)

    def swipe_left_full(self):
        x1 = self.scale_x(1360)
        x2 = self.scale_x(240)
        y = self.scale_y(450)
        self.log(f" -> [刷新] 左滑屏幕: ({x1},{y}) -> ({x2},{y})")
        self.drag_abs(x1, y, x2, y, steps=14)
        time.sleep(0.8)

    def find_and_tap(self, template_path, confidence=0.5, do_tap=True, screen=None, rect=None):
        if screen is None or rect is None:
            screen, rect = self.capture_target_window()
        return self.find_and_tap_on_capture(template_path, screen, rect, confidence=confidence, do_tap=do_tap)

    def wait_for_image(self, template_path, timeout=20, confidence=0.5, do_tap=False, interval=0.35):
        start_t = time.time()
        while self.is_running and time.time() - start_t < timeout:
            screen, rect = self.capture_target_window()
            if self.find_and_tap_on_capture(template_path, screen, rect, confidence=confidence, do_tap=False):
                if do_tap:
                    time.sleep(0.5)  # 发现目标后先等 0.5 秒再点击
                    self.find_and_tap_on_capture(template_path, screen, rect, confidence=confidence, do_tap=True)
                return True
            time.sleep(interval)
        self.log(f"等待超时: {os.path.basename(template_path)}")
        return False

    def increment_break_roll(self):
        if self.break_roll_count < 30:
            self.break_roll_count += 1
            self.roll_label.config(text=f"结界突破卷: {self.break_roll_count}/30")
        else:
            self.log("结界突破卷已达30上线，不再计数")

    def process_finish_mark_300(self):
        mark = get_path("finish_mark_300.png")

        # 先发现结算标记，不立刻点击
        if not self.wait_for_image(mark, timeout=15, confidence=0.7, do_tap=False):
            self.log("未检测到 finish_mark_300")
            return False

        self.log("发现 finish_mark_300，开始扫描 ken.png 以确认掉落")

        # 3s 内找到 ken.png：+1 卷, 继续点击 finish_mark_300；未找到则结束本次流程
        if self.wait_for_image(get_path("ken.png"), timeout=3, confidence=0.7, do_tap=False):
            self.log("扫描到 ken.png，结界突破卷 +1")
            self.increment_break_roll()
            self.wait_for_image(mark, timeout=5, confidence=0.7, do_tap=True)
            self.log("点击 finish_mark_300 完成结算")
            return True
        else:
            self.log("3s 内未扫描到 ken.png，退出本轮结算流程")
            self.wait_for_image(mark, timeout=5, confidence=0.7, do_tap=True)
            self.log("点击 finish_mark_300 完成结算")
            return True

    def combat_option_cycle(self):
        # 1. 先找 break 按钮进入战斗选项入口
        if not self.wait_for_image(get_path("break.png"), timeout=10, confidence=0.6, do_tap=True):
            self.log("未找到 break 按钮，结界突破终止。")
            return False
        time.sleep(3)

        base_slots = [
            (500, 300), (850, 300), (1185, 300),
            (500, 450), (850, 450), (1185, 450),
            (500, 585), (850, 585), (1185, 585)
        ]
        slots = [
            (
                self.random_scaled_offset(x, 30, self.BASE_WINDOW_W, self.window_w, self.window_x),
                self.random_scaled_offset(y, 30, self.BASE_WINDOW_H, self.window_h, self.window_y)
            )
            for x, y in base_slots
        ]
        self.rng.shuffle(slots)
        self.log(f"已随机组合九个战斗位置: {slots}")

        for idx, (x, y) in enumerate(slots, start=1):
            if not self.is_running:
                self.log("脚本已停止，退出结界突破。")
                return False

            self.log(f"点击第 {idx} 个位置: ({x},{y})")
            self.click_abs(x, y)
            time.sleep(1.2)

            # 等待出现 attack 按钮并进入战斗
            if not self.wait_for_image(get_path("attack.png"), timeout=12, confidence=0.6, do_tap=True):
                self.log("未找到 attack 按钮，跳过此位置")
                continue

            # 普通8次逻辑
            if idx < 9:
                self.wait_for_image(get_path("prepare.png"), timeout=20, confidence=0.7, do_tap=True)
                self.wait_for_image(get_path("finish_mark_300.png"), timeout=60, confidence=0.7, do_tap=True)
                time.sleep(2)
                self.wait_for_image(get_path("finish_mark_300.png"), timeout=2, confidence=0.7, do_tap=True)
                self.log(f"第 {idx} 次位置战斗结束，继续下一个位置")
                time.sleep(2)
                continue

            # 第九次特殊逻辑 (额外处理)
            self.log("第九次特殊逻辑：4 次返回确认 + 重启 + 准备战斗")
            for round_i in range(1, 5):
                if not self.is_running:
                    return False
                time.sleep(2)
                self.wait_for_image(get_path("back_button_2.png"), timeout=10, confidence=0.7, do_tap=True) # 点击左上角返回
                time.sleep(1)
                self.wait_for_image(get_path("confirm_button.png"), timeout=10, confidence=0.7, do_tap=True)# 点击确认返回
                time.sleep(1)
                self.wait_for_image(get_path("restart.png"), timeout=10, confidence=0.7, do_tap=True)
                self.log(f"第九次循环第 {round_i} 轮: 返回/确认/重启 完成")

            self.wait_for_image(get_path("prepare.png"), timeout=20, confidence=0.7, do_tap=True)
            self.wait_for_image(get_path("finish_mark_300.png"), timeout=60, confidence=0.7, do_tap=True)
            time.sleep(2)
            self.wait_for_image(get_path("finish_mark_300.png"), timeout=2, confidence=0.7, do_tap=True)
            self.log("第九次位置战斗结束，结界突破完成")

        self.log("结界突破整体完成")
        time.sleep(1)
        self.wait_for_image(get_path("cancel.png"), timeout=10, confidence=0.7, do_tap=True)
        return True

    def combat_option_logic(self):
        for i in range(3):
                if not self.is_running:
                    break
                self.log(f"第 {i+1} 次结界突破循环")
                self.combat_option_cycle()
                time.sleep(1)
        self.log("结界突破卷清理完成，自动停止")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def combat_option_8_cycle(self):
        base_slots = [
            (740, 300), (1140, 300), (740, 450), (1140, 450), (740, 585), (1140, 585), (740, 720), (1140, 720)
        ]
        self.log(f"按顺序执行八个战斗位置: {base_slots}")

        for idx, (base_x, base_y) in enumerate(base_slots, start=1):
            if not self.is_running:
                self.log("脚本已停止，退出阴阳寮突破。")
                return False
            

            fail_count = 0
            fail_img = get_path("restart.png")
            finish_img = get_path("finish_mark_300.png")
            while self.is_running:
                x = self.random_in_offset(base_x, 30)
                y = self.random_in_offset(base_y, 30)
                self.log(f"寮突模式第 {idx} 个位置继续 attack: ({x},{y})")
                self.adb_command(f"shell input tap {x} {y}")
                time.sleep(1.2)

                if not self.wait_for_image(get_path("attack.png"), timeout=12, confidence=0.45, do_tap=True):
                    fail_count += 1
                    self.log(f"第 {idx} 个位置检测到 attack 失败，准备切换到下一个位置")
                    break

                # 同时轮询 fail 与 finish：finish 继续当前坐标，fail 或 finish 超时则切换坐标
                fight_timeout = 120
                start_t = time.time()
                finish_detected = False
                while self.is_running and time.time() - start_t < fight_timeout:
                    if self.find_and_tap(fail_img, confidence=0.5, do_tap=False):
                        self.full_screen_random_tap()  # 检测到 fail 就随机点击清理一下，增加下一轮检测的成功率
                        fail_count += 1
                        self.log(f"第 {idx} 个位置失败，准备切换到下一个位置")
                        time.sleep(1.5)
                        break

                    if self.find_and_tap(finish_img, confidence=0.5, do_tap=False):
                        time.sleep(0.5)
                        self.find_and_tap(finish_img, confidence=0.5, do_tap=True)
                        finish_detected = True
                        time.sleep(1.4)
                        break

                    time.sleep(0.6)

                if fail_count > 0:
                    break

                if not finish_detected:
                    fail_count += 1
                    self.log(f"第 {idx} 个位置检测 finish_mark_300 超时，按失败处理")
                    break

                time.sleep(1.2)

            if fail_count == 0:
                self.log(f"寮突模式第 {idx} 个位置已完成并切换")
            time.sleep(1)

        self.log("阴阳寮突破本轮完成")
        time.sleep(1)
        self.swipe_up_full()
        return True
    
    def combat_option_8_logic(self):
        # 获取当前目标轮数（0 表示无限）
        try:
            target_limit = int(self.limit_var.get())
        except ValueError:
            target_limit = 0
            self.log("目标轮数格式错误，已默认为无限模式")

        round_count = 0
        while self.is_running:
            if target_limit > 0 and round_count >= target_limit:
                self.log(f"阴阳寮突破已达到目标轮数 {target_limit}，自动停止")
                break

            self.log(f"阴阳寮突破第 {round_count + 1} 轮开始")
            if self.combat_option_8_cycle():
                round_count += 1
                self.count = round_count
                self.count_label.config(text=f"已成功运行: {self.count} 轮")
                self.log(f"阴阳寮突破第 {round_count} 轮结束")
            else:
                self.log("阴阳寮突破本轮未完成，准备重试")

            time.sleep(1)

        self.log("阴阳寮突破流程结束")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def hard_28_cycle(self):
        self.log("开始一轮困难二十八流程：button_28 -> search -> 小怪4次 -> boss -> takara/search/button_28")

        # 首先扫描 button_28，5s 没扫描到就跳过到 search 扫描
        button_found = self.wait_for_image(get_path("button_28.png"), timeout=5, confidence=0.4, do_tap=True)
        if not button_found:
            self.log("5s 内未找到 button_28.png，转到 search 扫描")

        # search 逻辑：扫描到直接进入，否则本轮结束
        if not self.wait_for_image(get_path("search.png"), timeout=10, confidence=0.4, do_tap=True):
            self.log("未找到 search.png，结束本轮困难二十八流程")
            return False

        # 进行4次小怪战斗
        fight_count = 0
        while self.is_running and fight_count < 4:
            if self.find_and_tap(get_path("attack_28.png"), confidence=0.7, do_tap=True):
                if self.process_finish_mark_300():
                    fight_count += 1
                    self.log(f"挑战成功，完成第 {fight_count} 次小怪战斗")
                else:
                    self.log("未检测到finish_mark_300，本次小怪不计数，继续重试")

                if self.break_roll_count >= 27:
                    self.log("结界突破卷已达到27，停止硬28循环")
                    return True
                continue

            self.log("4s 内未检测到 attack_28.png，左滑刷新")
            self.swipe_left_full()

        # boss 战
        if self.wait_for_image(get_path("boss.png"), timeout=20, confidence=0.6, do_tap=True):
            self.process_finish_mark_300()
            time.sleep(3)
            if self.break_roll_count >= 27:
                self.log("结界突破卷已达到27，停止硬28循环")
                return True

        # takara/search/button_28 回退机制
        if self.wait_for_image(get_path("takara.png"), timeout=5, confidence=0.6, do_tap=False):
            self.log("找到 takara.png，继续回到 search 流程")
            self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.6, do_tap=True)
            time.sleep(1)
            self.tap_confirm()
            return True
        if self.wait_for_image(get_path("search.png"), timeout=5, confidence=0.6, do_tap=False):
            self.log("5s内未找到 takara，找到 search.png，继续 search 流程")
            return True
        if self.wait_for_image(get_path("button_28.png"), timeout=5, confidence=0.6, do_tap=True):
            self.log("5s内未找到 takara/search，找到 button_28.png，继续 button_28 流程")
            return True

        self.log("takara/search/button_28 均未找到，结束困难二十八流程")
        self.log("找到 takara.png，继续回到 search 流程")
        self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.6, do_tap=True)
        time.sleep(1)
        self.tap_confirm()
        return False

    def hard_28_logic(self):
        while self.is_running:
            if not self.hard_28_cycle():
                break

        self.log("困难二十八流程结束，重置运行状态")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def start_draw_roll(self):
        if not self.get_target_app_name():
            messagebox.showwarning("警告", "请先填写目标进程名！")
            return

        self.update_target_window_size()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.draw_roll_logic, daemon=True).start()

    def draw_roll_logic(self):
        self.log("开始绘卷模式循环")

        while self.is_running:
            self.break_roll_count = 0
            self.roll_label.config(text=f"结界突破卷: {self.break_roll_count}/30")

            # 先运行困难二十八直到卷数达到 27
            while self.is_running and self.break_roll_count < 27:
                result = self.hard_28_cycle()
                if not self.is_running:
                    break
                if not result:
                    self.log("困难二十八本轮结束，重新开始下一轮")
                    continue
                if self.break_roll_count >= 27:
                    break

            if not self.is_running:
                self.log("绘卷模式被中断")
                break

            if self.break_roll_count < 27:
                self.log("困难二十八未达到27卷，继续下一轮")
                continue

            self.log("结界突破卷达标(>=27)，执行返回并确认")
            self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.4, do_tap=True)
            time.sleep(1)
            self.tap_confirm()
            time.sleep(1)

            # 结界突破模式循环3次（3次9格=27次战斗）
            for i in range(3):
                if not self.is_running:
                    break
                self.log(f"绘卷模式: 第 {i+1} 次结界突破循环")
                self.combat_option_cycle()
                time.sleep(1)

            self.log("绘卷模式本轮完成，返回选择界面，准备下一轮")

        self.is_running = True
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def start_combat_option(self):
        if not self.get_target_app_name():
            messagebox.showwarning("警告", "请先填写目标进程名！")
            return

        self.update_target_window_size()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.combat_option_logic, daemon=True).start()

    def start_combat_option_8(self):
        if not self.get_target_app_name():
            messagebox.showwarning("警告", "请先填写目标进程名！")
            return

        self.update_target_window_size()
        self.count = 0
        self.count_label.config(text=f"已成功运行: {self.count} 轮")
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.combat_option_8_logic, daemon=True).start()

    def start_hard_28(self):
        if not self.get_target_app_name():
            messagebox.showwarning("警告", "请先填写目标进程名！")
            return

        self.update_target_window_size()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.hard_28_logic, daemon=True).start()

    # ================= 线程运行控制 =================
    def start_task(self):
        if not self.get_target_app_name():
            messagebox.showwarning("警告", "请先填写目标进程名！")
            return
        self.update_target_window_size()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.run_logic, daemon=True).start()

    def stop_task(self):
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def run_logic(self):
        self.log("=== 脚本开始运行 ===")
        conf_val = self.conf_slider.get()

        # 获取当前目标轮数
        try:
            target_limit = int(self.limit_var.get())
        except ValueError:
            target_limit = 0
            self.log("目标轮数格式错误，已默认为无限模式")

        selected_level_name = self.level_var.get()
        level_cfg = self.level_map.get(selected_level_name)

        # 分别取出开始图和对应的结算图
        current_start_img = level_cfg["start"]
        current_end_img = level_cfg["end"]

        self.log(f"当前模式：{selected_level_name}")

        while self.is_running:
            # --- 新增：检查是否达到目标轮数 ---
            if target_limit > 0 and self.count >= target_limit:
                self.log(f"已达到目标轮数 {target_limit}，脚本自动停止。")
                self.is_running = False
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                break
            # 1. 寻找开始按钮
            self.log(f"等待【{selected_level_name}】按钮...")
            while self.is_running:
                if self.find_and_tap(current_start_img, confidence=conf_val):
                    time.sleep(2)
                    # 检查是否成功进入（按钮消失则视为进入）
                    if not self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                        break
                time.sleep(2)

            # 2. 战斗监控
            if not self.is_running: break
            self.log("进入战斗监控...")
            start_time = time.time()

            while self.is_running:
                # 核心修改：这里使用该关卡专属的结算图 current_end_img
                if self.find_and_tap(current_end_img, confidence=0.5):
                    self.log(f"检测到【{selected_level_name}】专属结算图标...")
                    self.full_screen_random_tap()
                    time.sleep(self.rng.uniform(1.0, 1.5))
                    while self.is_running:
                        # --- 修正点 1：使用变量 current_start_img 而非死代码 ---
                        if self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                            self.count += 1
                            self.count_label.config(text=f"已成功运行: {self.count} 轮")
                            self.log(f"第 {self.count} 轮结束，回到主界面")
                            break
                        
                    break  # 跳出战斗监控循环

                # 超_时/挂机处理
                if time.time() - start_time > 20:
                    # --- 修正点 2：超时检测也要用变量 ---
                    if self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                        self.count += 1
                        self.count_label.config(text=f"已成功运行: {self.count} 轮")
                        break  # --- 修正点 3：必须 break 跳出阶段 2 ---

                    self.full_screen_random_tap()
                    # 每次乱点后重置一点时间，避免疯狂点击
                    start_time = time.time() - 15

                time.sleep(1)

    def start_mac_app_click(self):
        if not self.is_mac:
            messagebox.showwarning("警告", "该功能仅支持 macOS。")
            return

        self.update_target_window_size()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.mac_app_click_logic, daemon=True).start()

    def mac_app_click_logic(self):
        app_name = self.get_target_app_name()
        self.log(f"=== Mac识别点击模式启动，目标应用: {app_name} ===")
        conf_val = self.conf_slider.get()
        selected_level_name = self.level_var.get()
        level_cfg = self.level_map.get(selected_level_name)

        if not level_cfg:
            self.log("未找到当前关卡配置，终止 Mac 模式。")
            self.stop_task()
            return

        current_start_img = level_cfg["start"]
        current_end_img = level_cfg["end"]

        while self.is_running:
            # 优先尝试点击“开始”按钮
            if self.find_and_tap(current_start_img, confidence=conf_val, do_tap=True):
                time.sleep(1.2)
                continue

            # 再尝试处理“结算”按钮
            if self.find_and_tap(current_end_img, confidence=0.5, do_tap=True):
                self.count += 1
                self.count_label.config(text=f"已成功运行: {self.count} 轮")
                self.log(f"Mac 模式结算完成，第 {self.count} 轮")
                time.sleep(1.0)
                continue

            time.sleep(0.8)

        self.log("Mac识别点击模式已停止")


if __name__ == "__main__":
    root = tk.Tk()
    app = GameBotGUI(root)
    root.mainloop()