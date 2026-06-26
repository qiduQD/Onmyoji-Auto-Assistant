import cv2
import numpy as np
import subprocess
import secrets
import base64
import time
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import threading
import re
import sys
import os
import platform


def get_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        # 打包后的路径
        return os.path.join(sys._MEIPASS, "assets", relative_path)

    # 源码运行时的路径：当前目录 + assets + 文件名
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", relative_path)


def get_default_adb_candidates():
    """根据系统返回可能存在的 adb 路径候选（按优先级）。"""
    system_name = platform.system()
    # 先构造空列表，再按系统添加候选项（保证 extend 不会出错）
    candidates = []

    if system_name == "Darwin":
        # macOS 下优先使用 MuMu 内置 adb，然后回退到 PATH 中的 adb
        candidates.extend([
            "/Applications/MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb",
            "adb"
        ])

    # 通用：项目自带的 adb 可执行文件（打包时会放入 assets）
    candidates.extend([
        get_path("adb"),
        get_path("adb.exe")
    ])

    if system_name == "Windows":
        # 优先尝试 MuMu 的 adb（常见于 C: 与 D:），然后回退到 PATH 中的 adb.exe
        candidates.extend([
            r"C:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe",
            r"D:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe",
            "adb.exe"
        ])
    else:
        candidates.extend([
            "/usr/bin/adb",
            "/usr/local/bin/adb",
            os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
            "adb"
        ])

    # 保持顺序并去重
    uniq = []
    seen = set()
    for p in candidates:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq


class GameBotGUI:
    def __init__(self, root):
        # 初始化图片缓存字典
        self.image_cache = {}
        self.root = root
        self.root.title("痒痒鼠小助手 v2.3 - 已适配阴阳师新UI,多开组队，挂机斗技优化")
        # --- 设置窗口图标（兼容 Windows/macOS） ---
        try:
            if platform.system() == "Windows":
                icon_path = get_path("app.ico")
                self.root.iconbitmap(icon_path)
            else:
                # Tk 在 macOS 上对 .ico 支持有限，优先尝试 png 作为窗口图标
                icon_png = get_path("app.png")
                if os.path.exists(icon_png):
                    icon_img = tk.PhotoImage(file=icon_png)
                    self.root.iconphoto(True, icon_img)
                    # 保留引用，避免被垃圾回收导致图标失效
                    self._icon_img = icon_img
                else:
                    icon_ico = get_path("app.ico")
                    if os.path.exists(icon_ico):
                        self.root.iconbitmap(icon_ico)
        except Exception as e:
            # 如果没有图标文件，程序也会正常运行，不会崩溃
            print(f"窗口图标加载失败: {e}")
        self.root.geometry("800x750")
        self.is_running = False
        self.devices = []
        self.rng = secrets.SystemRandom()
        self.screen_w = 1600  # 默认值
        self.screen_h = 900  # 默认值
        self.task_start_time = None
        self.total_time_limit_seconds = 0
        self.time_limit_hit = False

        # --- UI 布局 ---
        # 1. ADB 路径
        tk.Label(root, text="ADB 路径:", font=("微软雅黑", 9)).pack(pady=2)
        self.adb_path_entry = tk.Entry(root, width=60)
        possible_adb_paths = get_default_adb_candidates()

        selected_adb = ""
        for p in possible_adb_paths:
            # 允许直接使用 PATH 中的 adb 命令
            if p in ("adb", "adb.exe"):
                selected_adb = p
                break
            if os.path.exists(p):
                selected_adb = p
                break

        self.adb_path_entry = tk.Entry(root, width=60)
        self.adb_path_entry.insert(0, selected_adb if selected_adb else "请手动指定 adb 路径")
        self.adb_path_entry.pack()
        # 关卡名称与对应图片文件的映射
        self.level_map = {
            "英杰等普通耗3体副本": {
                "start": get_path("start_button_3.png"),
                "end": get_path("finish_mark_300.png")
            },
            "活动御魂300次": {
                "start": get_path("start_button_300.png"),
                "end": get_path("finish_mark_300.png")
            },
            "御魂十": {
                "start": get_path("start_button.png"),
                "end": get_path("finish_mark_300.png")
            },
            "御魂十一": {
                "start": get_path("start_button.png"),
                "end": get_path("finish_mark_300.png")
            },
            "御魂十二": {
                "start": get_path("start_button.png"),
                "end": get_path("finish_mark_300.png")
            },
            "御灵": {
                "start": get_path("start_button.png"),
                "end": get_path("finish_mark_300.png")
            },
            "御魂痴": {
                "start": get_path("start_button.png"),
                "end": get_path("finish_mark_300.png")
            },
        }

        # 2. 设备选择区
        device_frame = tk.Frame(root)
        device_frame.pack(pady=10)
        tk.Label(device_frame, text="选择设备:").grid(row=0, column=0)
        self.device_var = tk.StringVar()
        self.device_menu = ttk.Combobox(device_frame, textvariable=self.device_var, width=25, state="readonly")
        self.device_menu.grid(row=0, column=1, padx=5)
        tk.Button(device_frame, text="刷新设备列表", command=self.refresh_devices).grid(row=0, column=2)
        self.screenshot_btn = tk.Button(device_frame, text="截图确认", command=self.screenshot_confirm, bg="#CFD8D9", fg="black", width=15)
        self.screenshot_btn.grid(row=0, column=3, padx=10, pady=8)

        #关卡选择区
        level_frame = tk.Frame(root)
        level_frame.pack(pady=10)
        tk.Label(level_frame, text="选择目标关卡:").grid(row=0, column=0)

        self.level_var = tk.StringVar()
        self.level_menu = ttk.Combobox(level_frame, textvariable=self.level_var, width=25, state="readonly")
        self.level_menu['values'] = list(self.level_map.keys())
        self.level_menu.current(0)  # 默认选第一个
        self.level_menu.grid(row=0, column=1, padx=5)

        # 3. 阈值设置
        tk.Label(root, text="识别阈值 (推荐 0.7-0.8):").pack(pady=2)
        self.conf_slider = tk.Scale(root, from_=0.1, to=1.0, resolution=0.05, orient=tk.HORIZONTAL, length=200)
        self.conf_slider.set(0.8)  # 默认值 0.8
        self.conf_slider.pack()

        # 4. 控制按钮
        self.btn_frame = tk.Frame(root)
        self.btn_frame.pack(pady=15)
        self.start_btn = tk.Button(self.btn_frame, text="开始挂机", command=self.start_task, bg="#4CAF50", fg="black",
                                   width=15)
        self.start_btn.grid(row=0, column=0, padx=10)
        self.stop_btn = tk.Button(self.btn_frame, text="停止运行", command=self.stop_task, state=tk.DISABLED,
                                  bg="#F44336", fg="black", width=15)
        self.stop_btn.grid(row=0, column=1, padx=10)
        self.combat_btn = tk.Button(self.btn_frame, text="结界突破", command=self.start_combat_option, bg="#2196F3", fg="black", width=15)
        self.combat_btn.grid(row=0, column=2, padx=10)
        self.hard28_btn = tk.Button(self.btn_frame, text="困难二十八", command=self.start_hard_28, bg="#FF9800", fg="black", width=15)
        self.hard28_btn.grid(row=0, column=3, padx=10)
        self.draw_roll_btn = tk.Button(self.btn_frame, text="绘卷模式", command=self.start_draw_roll, bg="#9C27B0", fg="black", width=15)
        self.draw_roll_btn.grid(row=0, column=4, padx=10)
        self.draw_roll2_btn = tk.Button(self.btn_frame, text="绘卷模式2", command=self.start_draw_roll2, bg="#795548", fg="black", width=15)
        self.draw_roll2_btn.grid(row=1, column=0, padx=10, pady=8)
        self.combat8_btn = tk.Button(self.btn_frame, text="阴阳寮突破", command=self.start_combat_option_8, bg="#607D8B", fg="black", width=15)
        self.combat8_btn.grid(row=1, column=2, padx=10, pady=8)
        self.arena_btn = tk.Button(self.btn_frame, text="斗技", command=self.start_arena, bg="#E91E63", fg="black", width=15)
        self.arena_btn.grid(row=1, column=1, padx=10, pady=8)
        self.zudui_btn = tk.Button(self.btn_frame, text="组队", command=self.start_zudui, bg="#7D5A5A", fg="black", width=15)
        self.zudui_btn.grid(row=1, column=3, padx=10, pady=8)
        self.bezudui_btn = tk.Button(self.btn_frame, text="被组队", command=self.start_bezudui, bg="#9E9E9E", fg="black", width=15)
        self.bezudui_btn.grid(row=1, column=4, padx=10, pady=8)
        
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

        time_frame = tk.Frame(root)
        time_frame.pack(pady=5)
        tk.Label(time_frame, text="总时长(分钟，0表示无限):").grid(row=0, column=0)

        self.time_limit_var = tk.StringVar()
        self.time_limit_entry = tk.Entry(time_frame, textvariable=self.time_limit_var, width=10)
        self.time_limit_entry.insert(0, "0")
        self.time_limit_entry.grid(row=0, column=1, padx=5)

        self.count_label.pack(pady=5)
        self.roll_label.pack(pady=2)



        # 5. 日志窗口
        tk.Label(root, text="运行日志:").pack()
        self.log_area = scrolledtext.ScrolledText(root, width=75, height=25, font=("Consolas", 9))
        self.log_area.pack(pady=10)

        # 初始化刷新一次设备
        self.refresh_devices()

    # ================= 智能化工具函数 =================
    def log(self, message):
        timestamp = time.strftime("[%H:%M:%S]")
        
        # 定义一个修改界面的小函数
        def update_text():
            self.log_area.insert(tk.END, f"{timestamp} {message}\n")
            self.log_area.see(tk.END)
            
        # 使用 after 将其安全地派发到主线程执行
        self.root.after(0, update_text)

    def start_total_time_control(self):
        self.task_start_time = time.time()
        try:
            total_minutes = float(self.time_limit_var.get())
        except ValueError:
            total_minutes = 0
            self.log("总时长格式错误，已默认为无限模式")

        self.total_time_limit_seconds = max(0, int(total_minutes * 60))
        self.time_limit_hit = False

    def check_total_time_limit(self):
        if not self.is_running:
            return False
        if self.total_time_limit_seconds <= 0 or self.task_start_time is None:
            return False

        elapsed = time.time() - self.task_start_time
        if elapsed < self.total_time_limit_seconds:
            return False

        if not self.time_limit_hit:
            self.time_limit_hit = True
            self.log("已达到总时长，脚本自动停止。")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        return True

    def refresh_devices(self):
        """获取当前所有连接的 ADB 设备"""
        try:
            adb = self.adb_path_entry.get().strip()

            # 优先使用当前输入框中的 adb 路径/命令
            result = subprocess.run(f'"{adb}" devices', shell=True, capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')[1:]
            devices = [line.split('\t')[0] for line in lines if line.strip()]

            # 若当前 adb 未检测到设备，则尝试候选路径并自动切换到可以工作的 adb
            if not devices:
                candidates = get_default_adb_candidates()
                for cand in candidates:
                    if not cand or cand == adb:
                        continue
                    try:
                        res = subprocess.run(f'"{cand}" devices', shell=True, capture_output=True, text=True)
                        lines2 = res.stdout.strip().split('\n')[1:]
                        devices2 = [line.split('\t')[0] for line in lines2 if line.strip()]
                        if devices2:
                            adb = cand
                            # 更新输入框以反映切换的 adb
                            try:
                                self.adb_path_entry.delete(0, tk.END)
                                self.adb_path_entry.insert(0, adb)
                            except Exception:
                                pass
                            self.log(f"未检测到设备，已切换 ADB 到: {adb}")
                            devices = devices2
                            break
                    except Exception:
                        continue

            self.devices = devices

            if self.devices:
                self.device_menu['values'] = self.devices
                self.device_menu.current(0)
                self.log(f"已发现设备: {', '.join(self.devices)}")
            else:
                self.device_menu['values'] = []
                self.device_var.set("")
                self.log("未发现任何在线设备，请检查模拟器是否开启。")
        except Exception as e:
            self.log(f"获取设备失败: {e}")

    def update_screen_size(self):
        """自动获取并校准分辨率"""
        adb = self.adb_path_entry.get()
        dev = self.device_var.get()
        result = subprocess.run(f'"{adb}" -s {dev} shell wm size', shell=True, capture_output=True, text=True)

        match = re.search(r'(\d+)x(\d+)', result.stdout)
        if match:
            raw_w = int(match.group(1))
            raw_h = int(match.group(2))

            if raw_w < raw_h:
                self.screen_w = raw_h
                self.screen_h = raw_w
            else:
                self.screen_w = raw_w
                self.screen_h = raw_h

            self.log(f"坐标系已校准: {self.screen_w}x{self.screen_h}")
        else:
            self.log("无法获取分辨率，使用默认 1600x900")

    def adb_command(self, cmd):
        return subprocess.run(f'"{self.adb_path_entry.get()}" -s {self.device_var.get()} {cmd}', shell=True,
                              capture_output=True)

    def tap_confirm(self):
        # 为确认按钮提供替代点击：在指定区域随机点击
        x = self.rng.randint(895, 1045)
        y = self.rng.randint(480, 520)
        self.log(f" -> [confirm] 随机点击: ({x}, {y})")
        self.adb_command(f"shell input tap {x} {y}")

    def tap_confirm_2(self):
        # 为确认按钮提供替代点击：在指定区域随机点击
        x = self.rng.randint(880, 975)
        y = self.rng.randint(505, 545)
        self.log(f" -> [confirm] 随机点击: ({x}, {y})")
        self.adb_command(f"shell input tap {x} {y}")
    
    def tap_cancel(self):
        # 为取消按钮提供替代点击：在指定区域随机点击
        x = self.rng.randint(30, 60)
        y = self.rng.randint(30, 60)
        self.log(f" -> [cancel] 随机点击: ({x}, {y})")
        self.adb_command(f"shell input tap {x} {y}")

    def random_in_offset(self, base, offset=30):
        return self.rng.randint(base - offset, base + offset)

    def get_screenshot(self):
        adb = self.adb_path_entry.get()
        dev = self.device_var.get()

        # Mac 专属精简指令集：直接利用 exec-out 或 shell 在安卓内部做 base64 编码
        base64_cmds = [
            [adb, "-s", dev, "exec-out", "screencap -p | base64"],
            [adb, "-s", dev, "shell", "screencap -p | base64"]
        ]
        
        for cmd in base64_cmds:
            try:
                # Mac 下无需任何 Windows 的 creationflags 参数，直接拉起原生 POSIX 进程，开销极低
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = process.communicate(timeout=5)  # Mac 性能较好，5秒超时足够
                
                if stdout:
                    try:
                        # 纯净的 Unix 字节流，直接去掉首尾空白后进行 Base64 解码
                        binary_data = base64.b64decode(stdout.strip())
                        img = cv2.imdecode(np.frombuffer(binary_data, np.uint8), cv2.IMREAD_COLOR)
                        if img is not None:
                            return img
                    except Exception as e:
                        self.log(f"Base64 解码失败: {e}")
                        continue
                        
            except subprocess.TimeoutExpired:
                self.log("警告：macOS 端 ADB 截图超时，尝试备用通道")
                continue
            except Exception as e:
                self.log(f"截图异常: {e}")
                continue

        self.log("错误：所有 Mac 截图通道均未成功，请检查模拟器连接")
        return None

    def full_screen_random_tap(self):
        # 基于自动获取的分辨率计算安全区域随机点击
        tx = self.rng.randint(500, 630)
        ty = self.rng.randint(750, 850)
        self.log(f" -> [清理中] 随机点击: ({tx}, {ty})")
        self.adb_command(f"shell input tap {tx} {ty}")

    def swipe_left_full(self):
        # 屏幕从右向左滑动，用于更大范围刷新列表或页面
        x1 = int(self.screen_w * 0.85)
        x2 = int(self.screen_w * 0.15)
        y = int(self.screen_h * 0.5)
        self.log(f" -> [刷新] 左滑屏幕: ({x1},{y}) -> ({x2},{y})")
        self.adb_command(f"shell input swipe {x1} {y} {x2} {y} 300")
        time.sleep(0.8)

    def find_and_tap(self, template_path, confidence=0.7, do_tap=True, screen=None):
        # 1. 优先使用外部传入的截图，如果没有才自己截取
        if screen is None:
            screen = self.get_screenshot()
            
        if screen is None:
            return False

        # 2. 内存字典缓存模板图片（避免疯狂读取硬盘）
        if not hasattr(self, 'image_cache'):
            self.image_cache = {}
            
        if template_path not in self.image_cache:
            self.image_cache[template_path] = load_image(template_path)
            
        template = self.image_cache[template_path]
        
        if template is None:
            self.log(f"错误：无法读取资源文件 -> {os.path.basename(template_path)}")
            return False

        # 3. 直接进入模板匹配核心算法 (这里直接用 screen，绝对不重复截图)
        h, w = template.shape[:2]
        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= confidence:
            if do_tap:
                mw, mh = int(w * 0.1), int(h * 0.1)
                tx = self.rng.randint(max_loc[0] + mw, max_loc[0] + w - mw)
                ty = self.rng.randint(max_loc[1] + mh, max_loc[1] + h - mh)
                self.adb_command(f"shell input tap {tx} {ty}")
                # 使用 os.path.basename 只显示文件名，不显示长路径
                self.log(f"命中: {os.path.basename(template_path)} ({max_val:.2f})")
            return True
            
        return False
    
    def check_up_buff_parallel(self, timeout=4, confidence=0.6, interval=0.5):
        """
        在规定时间内循环检测 up.png 或 up_2.png，任意一张出现即返回中心坐标和置信度。
        """
        # 预先加载两张图（利用你现有的 load_image 缓存机制）
        template_1 = load_image(get_path("up.png"))
        template_2 = load_image(get_path("up_2.png"))
        template_3 = load_image(get_path("up_3.png"))

        if template_1 is None or template_2 is None or template_3 is None:
            self.log("错误：无法读取加成UP资源文件")
            return None

        start_t = time.time()
        while self.is_running and time.time() - start_t < timeout:
            screen = self.get_screenshot()
            if screen is None:
                time.sleep(interval)
                continue

            # 1. 检测第一张图 (up.png)
            h1, w1 = template_1.shape[:2]
            res1 = cv2.matchTemplate(screen, template_1, cv2.TM_CCOEFF_NORMED)
            _, max_val1, _, max_loc1 = cv2.minMaxLoc(res1)

            if max_val1 >= confidence:
                return max_loc1[0] + w1 // 2, max_loc1[1] + h1 // 2, max_val1

            # 2. 检测第二张图 (up_2.png)
            h2, w2 = template_2.shape[:2]
            res2 = cv2.matchTemplate(screen, template_2, cv2.TM_CCOEFF_NORMED)
            _, max_val2, _, max_loc2 = cv2.minMaxLoc(res2)

            if max_val2 >= confidence:
                return max_loc2[0] + w2 // 2, max_loc2[1] + h2 // 2, max_val2
            
            # 3. 检测第三张图 (up_3.png)
            h3, w3 = template_3.shape[:2]
            res3 = cv2.matchTemplate(screen, template_3, cv2.TM_CCOEFF_NORMED)
            _, max_val3, _, max_loc3 = cv2.minMaxLoc(res3)

            if max_val3 >= confidence:
                return max_loc3[0] + w3 // 2, max_loc3[1] + h3 // 2, max_val3

            time.sleep(interval)

        self.log(f"等待超时，未识别到目标坐标")
        return None
    

    def find_and_tap_in_region(self, template_path, center_x, center_y, region_w=500, region_h=300, confidence=0.6, timeout=4, interval=0.5):
        """在给定中心点附近的局部区域内循环识别并点击模板，直到超时。"""
        template = load_image(template_path)

        if template is None:
            self.log(f"错误：无法读取资源文件 -> {os.path.basename(template_path)}")
            return False

        start_t = time.time()
        while self.is_running and time.time() - start_t < timeout:
            screen = self.get_screenshot()
            if screen is None:
                time.sleep(interval)
                continue

            screen_h, screen_w = screen.shape[:2]
            half_w = region_w // 2
            half_h = region_h // 2
            left = max(0, int(center_x - half_w))
            top = max(0, int(center_y - half_h))
            right = min(screen_w, int(center_x + half_w))
            bottom = min(screen_h, int(center_y + half_h))

            region = screen[top:bottom, left:right]
            if region.size == 0:
                time.sleep(interval)
                continue

            h, w = template.shape[:2]
            if region.shape[0] < h or region.shape[1] < w:
                time.sleep(interval)
                continue

            res = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val >= confidence:
                mw, mh = int(w * 0.1), int(h * 0.1)
                tx = self.rng.randint(left + max_loc[0] + mw, left + max_loc[0] + w - mw)
                ty = self.rng.randint(top + max_loc[1] + mh, top + max_loc[1] + h - mh)
                self.adb_command(f"shell input tap {tx} {ty}")
                self.log(f"命中: {os.path.basename(template_path)} ({max_val:.2f})，局部区域: ({left},{top})-({right},{bottom})")
                return True

            time.sleep(interval)

        self.log(f"等待超时: {os.path.basename(template_path)}，局部区域扫描已结束")
        return False
    

    def wait_for_image(self, template_path, timeout=60, confidence=0.6, do_tap=False, interval=1.0):
        start_t = time.time()
        while self.is_running and time.time() - start_t < timeout:
            if self.check_total_time_limit():
                return False
            # 【优化点1】每轮循环只向模拟器要一次截图
            current_screen = self.get_screenshot()
            if current_screen is None:
                time.sleep(interval)
                continue
            # 全局检测：优先扫描并点击任务接受弹窗（task-accept.png），若存在则点击并继续等待目标
            try:
                task_accept_img = get_path("task-accept.png")
                # 使用较高置信度，若命中则直接点击（find_and_tap 会在命中时记录日志）
                if self.find_and_tap(task_accept_img, confidence=0.7, do_tap=True, screen=current_screen):
                    self.log("【系统提示】触发悬赏任务！已自动接受。")
                    import sys
                    sys.stdout.write('\a')
                    sys.stdout.flush()
                    time.sleep(0.6)
                    continue # 既然点了弹窗，画面变了，直接进入下一轮循环重新截图
            except Exception:
                pass

            # 检测目标图片，同样传入 current_screen
            if self.find_and_tap(template_path, confidence=confidence, do_tap=False, screen=current_screen):
                if do_tap:
                    time.sleep(0.5) 
                    # 此时画面可能变了，再次检测时让它内部重新截图确认
                    if not self.find_and_tap(template_path, confidence=confidence, do_tap=True):
                        self.log(f"警告：目标 {os.path.basename(template_path)} 在点击时未找到")
                        self.full_screen_random_tap()
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

    def process_finish_mark_300(self, timeout=60):
        conf_val = self.conf_slider.get()
        mark = get_path("finish_mark_300.png")

        # 先发现结算标记，不立刻点击
        if not self.wait_for_image(mark, timeout=timeout, confidence=conf_val, do_tap=False):
            self.log("未检测到 finish_mark_300")
            return False

        self.log("发现 finish_mark_300，开始扫描 ken.png 以确认掉落")

        # 3s 内找到 ken.png：+1 卷, 继续点击 finish_mark_300；未找到则结束本次流程
        if self.wait_for_image(get_path("ken.png"), timeout=3, confidence=conf_val, do_tap=False):
            self.log("扫描到 ken.png，结界突破卷 +1")
            self.increment_break_roll()
            self.wait_for_image(mark, timeout=5, confidence=conf_val, do_tap=True)
            self.log("点击 finish_mark_300 完成结算")
            return True
        else:
            self.log("3s 内未扫描到 ken.png，退出本轮结算流程")
            self.wait_for_image(mark, timeout=5, confidence=conf_val, do_tap=True)
            self.log("点击 finish_mark_300 完成结算")
            return True

    def combat_option_cycle(self):

        conf_val = self.conf_slider.get()
        # 1. 先找 break 按钮进入战斗选项入口
        if not self.wait_for_image(get_path("break.png"), timeout=10, confidence=0.7, do_tap=True):
            self.log("未找到 break 按钮，结界突破终止。")
            return False
        time.sleep(3)

        if not self.wait_for_image(get_path("unlock.png"), timeout=1, confidence=0.9, do_tap=True):
            self.log("未找到 unlock 按钮，阵容已锁定")
            time.sleep(0.3)

        base_slots = [
            (523, 584), (931, 584), (1325, 584),
            (523, 403), (931, 403), (1325, 403),
            (523, 243), (931, 243), (1325, 243)
        ]
        slots = [
            (self.random_in_offset(x, 30), self.random_in_offset(y, 30))
            for x, y in base_slots
        ]
        self.rng.shuffle(slots)
        self.log(f"已随机组合九个战斗位置: {slots}")

        for idx, (x, y) in enumerate(slots, start=1):
            if not self.is_running:
                self.log("脚本已停止，退出结界突破。")
                return False

            self.log(f"点击第 {idx} 个位置: ({x},{y})")
            
            # 普通8次逻辑
            if idx < 9:
                self.adb_command(f"shell input tap {x} {y}")
                time.sleep(1)

                 # 等待出现 attack 按钮并进入战斗
                if not self.wait_for_image(get_path("attack.png"), timeout=3, confidence=conf_val, do_tap=True):
                   self.log("未找到 attack 按钮，跳过此位置")
                   continue
                self.wait_for_image(get_path("finish_mark_300.png"), timeout=180, confidence=conf_val, do_tap=True)
                time.sleep(2)
                self.wait_for_image(get_path("finish_mark_300.png"), timeout=5, confidence=conf_val, do_tap=True)
                self.log(f"第 {idx} 次位置战斗结束，继续下一个位置")
                time.sleep(2)
                continue

            # 第九次特殊逻辑 (额外处理)
            self.log("第九次特殊逻辑：4 次返回确认 + 重启 + 准备战斗")
            if not self.wait_for_image(get_path("lock.png"), timeout=3, confidence=0.9, do_tap=True):
                self.log("未找到 lock 按钮，阵容解锁")
                time.sleep(0.2)
            self.adb_command(f"shell input tap {x} {y}")
            time.sleep(1)
            if not self.wait_for_image(get_path("attack.png"), timeout=3, confidence=conf_val, do_tap=True):
                self.log("未找到 attack 按钮，跳过此位置")
                self.wait_for_image(get_path("cancel.png"), timeout=10, confidence=conf_val, do_tap=True)
                return True  # 跳过第九次的特殊流程，继续结界突破整体流程
            for round_i in range(1, 5):
                if not self.is_running:
                    return False
                time.sleep(2)
                self.tap_cancel()  # 点击左上角返回
                time.sleep(1)
                self.tap_confirm_2()  # 点击确认返回
                time.sleep(1)
                self.wait_for_image(get_path("restart.png"), timeout=10, confidence=conf_val, do_tap=True)
                self.log(f"第九次循环第 {round_i} 轮: 返回/确认/重启 完成")

            self.wait_for_image(get_path("prepare.png"), timeout=3, confidence=conf_val, do_tap=True)
            self.wait_for_image(get_path("finish_mark_300.png"), timeout=180, confidence=conf_val, do_tap=True)
            time.sleep(2)
            self.wait_for_image(get_path("finish_mark_300.png"), timeout=5, confidence=conf_val, do_tap=True)
            self.log("第九次位置战斗结束，结界突破完成")

        self.log("结界突破整体完成")
        time.sleep(2)
        self.wait_for_image(get_path("cancel.png"), timeout=10, confidence=conf_val, do_tap=True)
        return True

    def combat_option_logic(self):
        for i in range(3):
                if self.check_total_time_limit():
                    break
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
            (815, 220), (1235, 220), (815, 400),(1235, 400),(815, 560), (1235, 560), (815, 720),(1235, 720)
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
                time.sleep(2)

                if not self.wait_for_image(get_path("attack.png"), timeout=3, confidence=0.45, do_tap=True):
                    fail_count += 1
                    self.log(f"第 {idx} 个位置检测到 attack 失败，准备切换到下一个位置")
                    break

                # 同时轮询 fail 与 finish：finish 继续当前坐标，fail 或 finish 超时则切换坐标
                fight_timeout = 180
                start_t = time.time()
                finish_detected = False
                while self.is_running and time.time() - start_t < fight_timeout:
                    if self.find_and_tap(fail_img, confidence=0.7, do_tap=False):
                        time.sleep(0.5)
                        self.full_screen_random_tap()  # 检测到 fail 就随机点击清理一下，增加下一轮检测的成功率
                        fail_count += 1
                        self.log(f"第 {idx} 个位置失败，准备切换到下一个位置")
                        time.sleep(2)
                        break

                    if self.find_and_tap(finish_img, confidence=0.7, do_tap=False):
                        time.sleep(0.5)
                        self.find_and_tap(finish_img, confidence=0.7, do_tap=True)
                        finish_detected = True
                        time.sleep(1.4)
                        break

                    time.sleep(2)

                if fail_count > 0:
                    break

                if not finish_detected:
                    fail_count += 1
                    self.log(f"第 {idx} 个位置检测 finish_mark_300 超时，按失败处理")
                    break

                time.sleep(2)

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
            if self.check_total_time_limit():
                break
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
        self.log("开始一轮困难二十八流程：button_28 -> search -> 小怪 -> boss -> takara/search/button_28")

        # 首先扫描 button_28，4s 没扫描到就跳过到 search 扫描
        button_found = self.wait_for_image(get_path("button_28.png"), timeout=4, confidence=0.6, do_tap=True)
        if not button_found:
            self.log("4s 内未找到 button_28.png，转到 search 扫描")

        # search 逻辑：扫描到直接进入，否则本轮结束
        if not self.wait_for_image(get_path("search.png"), timeout=5, confidence=0.6, do_tap=True):
            self.log("未找到 search.png，结束本轮困难二十八流程")
            return False
        
        # 进行小怪战斗
        swipe_retries = 0
        while self.is_running:
            if self.find_and_tap(get_path("boss.png"), confidence=0.7, do_tap=False):
                self.log("检测到 boss，跳过小怪阶段进入 boss 战")
                break

            up_hit = self.check_up_buff_parallel()
            if up_hit:
                up_x, up_y, up_conf = up_hit
                self.log(f"识别到红达摩坐标: ({up_x}, {up_y})，置信度: {up_conf:.2f}")
                if self.find_and_tap_in_region(get_path("attack_28.png"), up_x, up_y, region_w=500, region_h=600, confidence=0.6, timeout=3, interval=0.5):
                    swipe_retries = 0
                    if self.process_finish_mark_300(timeout=20):
                        self.log("挑战成功")
                    else:
                        self.log("未检测到finish_mark_300，本次小怪不计数，继续重试")

                    if self.break_roll_count >= 27:
                        self.log("结界突破卷已达到27，停止困难28循环")
                        return True
                    continue

                self.log("在 红达摩 局部区域内未找到 attack_28，执行左滑刷新")
            else:
                self.log("未识别到 红达摩，执行左滑刷新")

            self.swipe_left_full()
            swipe_retries += 1
            
            if swipe_retries > 2:
                self.log("连续两次刷新后仍未找到 红达摩，结束小怪战斗流程")
                break
        # boss 战
        if self.wait_for_image(get_path("boss.png"), timeout=1, confidence=0.6, do_tap=True):
            self.process_finish_mark_300(timeout=20)
            time.sleep(3)
            if self.break_roll_count >= 27:
                self.log("结界突破卷已达27，停止困难28循环")
                return True


        # takara/search/button_28 回退机制
        if self.wait_for_image(get_path("takara.png"), timeout=1, confidence=0.8, do_tap=False):
            self.log("找到 takara.png，继续回到 search 流程")
            self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.6, do_tap=True)
            time.sleep(1)
            self.tap_confirm()
            return True
        if self.wait_for_image(get_path("search.png"), timeout=1, confidence=0.6, do_tap=False):
            self.log("1s内未找到 takara，找到 search.png，继续 search 流程")
            return True
        if self.wait_for_image(get_path("button_28.png"), timeout=1, confidence=0.6, do_tap=False):
            self.log("1s内未找到 takara/search，找到 button_28.png，继续 button_28 流程")
            return True

        self.log("takara/search/button_28 均未找到，结束困难二十八流程")
        self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.6, do_tap=True)
        time.sleep(1)
        self.tap_confirm()
        return True


    def hard_28_logic(self):
        while self.is_running:
            if self.check_total_time_limit():
                break
            if not self.hard_28_cycle():
                break

        self.log("困难二十八流程结束，重置运行状态")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def start_draw_roll(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.start_total_time_control()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.draw_roll_logic, daemon=True).start()

    def draw_roll_logic(self):
        self.log("开始绘卷模式循环")

        while self.is_running:
            if self.check_total_time_limit():
                break
            self.break_roll_count = 0
            self.roll_label.config(text=f"结界突破卷: {self.break_roll_count}/30")

            # 先运行困难二十八直到卷数达到 27
            while self.is_running and self.break_roll_count < 27:
                result = self.hard_28_cycle()
                if not self.is_running:
                    break
                if result and self.break_roll_count >= 27:
                    self.log("结界突破卷达标，准备进入结界突破")
                    break

            if not self.is_running:
                self.log("绘卷模式被中断")
                break

            if self.break_roll_count < 27:
                self.log("困难二十八未达到27卷，继续下一轮")
                continue

            self.log("结界突破卷达标(>=27)，执行返回并确认")
            self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.7, do_tap=True)
            time.sleep(1)
            self.tap_confirm()
            time.sleep(1)
            self.wait_for_image(get_path("back_button.png"), timeout=3, confidence=0.7, do_tap=True)
            time.sleep(1)

            # 结界突破模式循环3次（3次9格=27次战斗）
            for i in range(3):
                if not self.is_running:
                    break
                self.log(f"绘卷模式: 第 {i+1} 次结界突破循环")
                self.combat_option_cycle()
                time.sleep(1)

            self.log("绘卷模式本轮完成，返回选择界面，准备下一轮")

        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def run_dungeon_once(self, selected_level_name, current_start_img, current_end_img, conf_val):
        """执行一轮副本模式，成功完成后返回 True。"""
        if not self.is_running:
            return False

        # 1. 寻找开始按钮
        self.log(f"等待【{selected_level_name}】按钮...")
        while self.is_running:
            if self.wait_for_image(current_start_img, timeout=10, confidence=conf_val, do_tap=True):
                time.sleep(2)
                # 检查是否成功进入（按钮消失则视为进入）
                if not self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                    break
            time.sleep(2)

        if not self.is_running:
            return False

        # 2. 战斗监控
        self.log("进入战斗监控...")
        start_time = time.time()

        while self.is_running:
            if self.check_total_time_limit():
                return False
            if self.wait_for_image(current_end_img, timeout=90, confidence=conf_val, do_tap=True):
                while self.is_running:
                    if self.check_total_time_limit():
                        return False
                    if self.wait_for_image(current_start_img, timeout=3, confidence=conf_val, do_tap=False):
                        self.count += 1
                        self.count_label.config(text=f"已成功运行: {self.count} 轮")
                        self.log(f"第 {self.count} 轮结束，回到主界面")
                        return True
                    else:
                        self.log("未检测到开始按钮，继续等待...")
                        self.full_screen_random_tap()  # 可能卡在结算界面，随机点击清理一下
                    time.sleep(1)

                return False

            # 超_时/挂机处理
            if time.time() - start_time > 90:
                while self.is_running:
                    if self.check_total_time_limit():
                        return False
                    if self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                        self.count += 1
                        self.count_label.config(text=f"已成功运行: {self.count} 轮")
                        self.log(f"第 {self.count} 轮超时检测到开始按钮，视为完成")
                        return True
                    else:
                        self.log("超时检测未找到开始按钮，执行随机点击清理")
                        self.full_screen_random_tap()
                        time.sleep(1)  # 每次乱点后重置一点时间，避免疯狂点击

                
            time.sleep(1)

        return False
    
    def run_dungeon_zudui(self, conf_val):
        """执行一轮组队副本模式，成功完成后返回 True。"""
        if not self.is_running:
            return False

        # 1. 寻找开始按钮
        self.log(f"等待组队挑战按钮...")
        while self.is_running:
            if self.wait_for_image(get_path("start_button_zudui.png"), timeout=10, confidence=conf_val, do_tap=True):
                time.sleep(2)
                # 检查是否成功进入（按钮消失则视为进入）
                if not self.find_and_tap(get_path("start_button_zudui.png"), confidence=conf_val, do_tap=False):
                    break
            time.sleep(2)

        if not self.is_running:
            return False

        # 2. 战斗监控
        self.log("进入战斗监控...")
        start_time = time.time()

        while self.is_running:
            if self.check_total_time_limit():
                return False
            finish_imgs = [get_path("finish_mark.png"), get_path("finish_mark_sp.png")]
            finish_detected = False
            matched_finish_img = None
            finish_start_t = time.time()
            while self.is_running and time.time() - finish_start_t < 90:
                if self.check_total_time_limit():
                    return False

                for finish_img in finish_imgs:
                    if self.find_and_tap(finish_img, confidence=conf_val, do_tap=False):
                        matched_finish_img = finish_img
                        finish_detected = True
                        break

                if finish_detected:
                    time.sleep(0.5)
                    self.find_and_tap(matched_finish_img, confidence=conf_val, do_tap=True)
                    break

                time.sleep(1)

            if finish_detected:
                self.wait_for_image(get_path("finish_mark_300.png"), timeout=5, confidence=conf_val, do_tap=True)
                while self.is_running:
                    if self.check_total_time_limit():
                        return False
                    if self.wait_for_image(get_path("start_button_zudui.png"), timeout=3, confidence=conf_val, do_tap=False):
                        self.count += 1
                        self.count_label.config(text=f"已成功运行: {self.count} 轮")
                        self.log(f"第 {self.count} 轮结束，回到主界面")
                        return True
                    else:
                        self.log("未检测到开始按钮，继续等待...")
                        self.full_screen_random_tap()  # 可能卡在结算界面，随机点击清理一下
                    time.sleep(1)

                return False

            # 超_时/挂机处理
            if time.time() - start_time > 90:
                while self.is_running:
                    if self.check_total_time_limit():
                        return False
                    if self.find_and_tap(get_path("start_button_zudui.png"), confidence=conf_val, do_tap=False):
                        self.count += 1
                        self.count_label.config(text=f"已成功运行: {self.count} 轮")
                        self.log(f"第 {self.count} 轮超时检测到开始按钮，视为完成")
                        return True
                    else:
                        self.log("超时检测未找到开始按钮，执行随机点击清理")
                        self.full_screen_random_tap()
                        time.sleep(1)  # 每次乱点后重置一点时间，避免疯狂点击

                
            time.sleep(1)

        return False
    
    def run_dungeon_random(self, selected_level_name, current_start_img, conf_val):
        """执行绘卷副本模式，成功完成后返回 True。"""
        if not self.is_running:
            return False

        # 1. 寻找开始按钮
        self.log(f"等待【{selected_level_name}】按钮...")
        while self.is_running:
            if self.wait_for_image(current_start_img, timeout=3, confidence=conf_val, do_tap=True):
                time.sleep(2)
                # 检查是否成功进入（按钮消失则视为进入）
                if not self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                    break
            time.sleep(2)

        if not self.is_running:
            return False

        # 2. 战斗监控
        self.log("进入战斗监控...")
        start_time = time.time()

        while self.is_running:
            if self.check_total_time_limit():
                return False
            if self.process_finish_mark_300(timeout=90):
                while self.is_running:
                    if self.check_total_time_limit():
                        return False
                    if self.wait_for_image(current_start_img, timeout=10, confidence=conf_val, do_tap=False):
                        self.count += 1
                        self.count_label.config(text=f"已成功运行: {self.count} 轮")
                        self.log(f"第 {self.count} 轮结束，回到主界面")
                        return True
                    else:
                        self.log("未检测到开始按钮，继续等待...")
                        self.full_screen_random_tap()  # 可能卡在结算界面，随机点击清理一下
                    time.sleep(1)

                return False

            # 超_时/挂机处理
            if time.time() - start_time > 90:
                while self.is_running:
                    if self.check_total_time_limit():
                        return False
                    if self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                        self.count += 1
                        self.count_label.config(text=f"已成功运行: {self.count} 轮")
                        self.log(f"第 {self.count} 轮超时检测到开始按钮，视为完成")
                        return True
                    else:
                        self.log("超时检测未找到开始按钮，执行随机点击清理")
                        self.full_screen_random_tap()
                        time.sleep(1)  # 每次乱点后重置一点时间，避免疯狂点击

            time.sleep(1)

        return False

    def draw_roll2_logic(self):
        self.log("开始绘卷模式2循环：副本模式 -> 9卷切结界突破 -> 返回副本 -> 重复")

        conf_val = self.conf_slider.get()
        selected_level_name = self.level_var.get()
        level_cfg = self.level_map.get(selected_level_name)
        if not level_cfg:
            self.log("未找到当前关卡配置，绘卷模式2终止")
            self.is_running = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            return

        current_start_img = level_cfg["start"]
        current_end_img = level_cfg["end"]
        self.log(f"绘卷模式2当前副本：{selected_level_name}")

        while self.is_running:
            if self.check_total_time_limit():
                break
            self.break_roll_count = 0
            self.roll_label.config(text=f"结界突破卷: {self.break_roll_count}/30")

            while self.is_running and self.break_roll_count < 9:
                if not self.run_dungeon_random(selected_level_name, current_start_img, conf_val):
                    break

                if self.break_roll_count >= 9:
                    break

            if not self.is_running:
                break

            if self.break_roll_count < 9:
                self.log("绘卷模式2未达到9张结界突破卷，继续副本循环")
                continue

            self.log("绘卷模式2卷数达标(>=9)，点击 back_button 进入结界突破")
            self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=conf_val, do_tap=True)
            time.sleep(1)


            self.log("绘卷模式2：执行结界突破模式")
            self.combat_option_cycle()
            time.sleep(1)

            self.log("绘卷模式2：结界突破结束，点击 button_task 返回副本界面")
            self.wait_for_image(get_path("button_task.png"), timeout=10, confidence=conf_val, do_tap=True)
            self.wait_for_image(get_path("confirm_boss.png"), timeout=10, confidence=conf_val, do_tap=True)
            time.sleep(1)

        self.log("绘卷模式2流程结束")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def start_combat_option(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.start_total_time_control()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.combat_option_logic, daemon=True).start()

    def start_draw_roll2(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.start_total_time_control()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.draw_roll2_logic, daemon=True).start()

    def start_combat_option_8(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.count = 0
        self.start_total_time_control()
        self.count_label.config(text=f"已成功运行: {self.count} 轮")
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.combat_option_8_logic, daemon=True).start()

    def start_hard_28(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.start_total_time_control()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.hard_28_logic, daemon=True).start()

    def arena_cycle(self):
        """执行一轮斗技流程：点击 battle_start -> 等待 auto -> 点击 auto_on -> 等待 finish -> 随机点击清理并返回 True"""
        conf_val = self.conf_slider.get()

        # 1. 点击 battle_start
        if not self.wait_for_image(get_path("battle_start.png"), timeout=10, confidence=conf_val, do_tap=True):
            if not self.wait_for_image(get_path("cancel.png"), timeout=10, confidence=conf_val, do_tap=True): 
              self.log("未找到 battle_start.png，斗技终止。")
            return False
        time.sleep(1)

        # 2. 等待 auto 图标出现（进入战斗前的自动战斗按钮界面）
        if not self.wait_for_image(get_path("auto.png"), timeout=10, confidence=0.6, do_tap=True):
            self.log("未检测到 auto.png，斗技进入战斗失败")
            return False
        time.sleep(1)

        # 3. 不再自动点击 auto_on，改为进入战斗后轮询检测
        # 4. 轮询等待 finish 标记：每次检测 finish 之前先扫描 texie.png（若存在则先随机清理一次）
        finish_img = get_path("finish_douji.png")
        texie_img = get_path("texie.png")
        start_t = time.time()
        while self.is_running:
            if self.check_total_time_limit():
                return False

            # 若出现 texie（特异提示），先进行一次随机清理点击再继续检测 finish
            try:
                if self.find_and_tap(texie_img, confidence=conf_val, do_tap=False):
                    self.log("检测到 texie.png，执行随机点击清理")
                    self.full_screen_random_tap()
                    time.sleep(0.6)
            except Exception:
                pass

            if self.find_and_tap(finish_img, confidence=conf_val, do_tap=False):
                # 发现结算，点击并清理
                self.find_and_tap(finish_img, confidence=conf_val, do_tap=True)
                time.sleep(1)
                self.full_screen_random_tap()
                self.count += 1
                self.count_label.config(text=f"已成功运行: {self.count} 轮")
                self.log(f"斗技第 {self.count} 轮结束")
                return True

            # 超时保护：长时间无响应则随机点一次尝试恢复
            if time.time() - start_t > 1800:  # 30分钟未检测到 finish 或 texie，执行随机点击尝试恢复
                self.log("斗技战斗超时，执行随机点击尝试恢复")
                self.full_screen_random_tap()
                start_t = time.time()

            time.sleep(1)

        return False

    def arena_logic(self):
        try:
            target_limit = int(self.limit_var.get())
        except ValueError:
            target_limit = 0
            self.log("目标轮数格式错误，斗技已默认为无限模式")

        round_count = 0
        while self.is_running:
            if self.check_total_time_limit():
                break
            if target_limit > 0 and round_count >= target_limit:
                self.log(f"斗技已达到目标轮数 {target_limit}，自动停止")
                break

            self.log(f"斗技第 {round_count + 1} 轮开始")
            if self.arena_cycle():
                round_count += 1
                self.count = round_count
                self.count_label.config(text=f"已成功运行: {self.count} 轮")
                self.log(f"斗技第 {round_count} 轮结束")
            else:
                self.log("斗技本轮未完成，准备重试")

            time.sleep(1)

        self.log("斗技流程结束")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def start_arena(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.count = 0
        self.start_total_time_control()
        self.count_label.config(text=f"已成功运行: {self.count} 轮")
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.arena_logic, daemon=True).start()

    def bezudui_cycle(self):
        """执行一轮被组队流程:等待finish -> 点击确认 -> 点击 battle_start -> 等待 auto -> 进入战斗后轮询 finish 和 texie，直到检测到 finish 则点击并清理返回 True"""
        conf_val = self.conf_slider.get()

        # 等待 finish 标记出现，点击确认进入下一步
        while self.is_running:
            if self.check_total_time_limit():
                return False
            finish_imgs = [get_path("finish_mark.png"), get_path("finish_mark_sp.png")]
            finish_detected = False
            matched_finish_img = None
            finish_start_t = time.time()
            while self.is_running and time.time() - finish_start_t < 90:
                if self.check_total_time_limit():
                    return False

                for finish_img in finish_imgs:
                    if self.find_and_tap(finish_img, confidence=conf_val, do_tap=False):
                        matched_finish_img = finish_img
                        finish_detected = True
                        break

                if finish_detected:
                    time.sleep(0.5)
                    self.find_and_tap(matched_finish_img, confidence=conf_val, do_tap=True)
                    break

                time.sleep(1)

            if finish_detected:
                time.sleep(0.5)
                self.wait_for_image(get_path("finish_mark_300.png"),timeout=10, confidence=0.7, do_tap=True)
                time.sleep(0.5)
                self.wait_for_image(get_path("zudui-accept.png"), timeout=20, confidence=conf_val, do_tap=True)
                return True
            time.sleep(2)
    

    def zudui_logic(self):
        self.log("=== 组队挑战开始运行 ===")
        conf_val = self.conf_slider.get()

        # 获取当前目标轮数
        try:
            target_limit = int(self.limit_var.get())
        except ValueError:
            target_limit = 0
            self.log("目标轮数格式错误，已默认为无限模式")

        while self.is_running:
            if self.check_total_time_limit():
                break
            # --- 新增：检查是否达到目标轮数 ---
            if target_limit > 0 and self.count >= target_limit:
                self.log(f"已达到目标轮数 {target_limit}，脚本自动停止。")
                self.is_running = False
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                break
            if not self.run_dungeon_zudui(conf_val):
                break


    def start_zudui(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.count = 0
        self.start_total_time_control()
        self.count_label.config(text=f"已成功运行: {self.count} 轮")
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.zudui_logic, daemon=True).start()


    def bezudui_logic(self):
        try:
            target_limit = int(self.limit_var.get())
        except ValueError:
            target_limit = 0
            self.log("目标轮数格式错误，已默认为无限模式")

        round_count = 0
        while self.is_running:
            if self.check_total_time_limit():
                break
            if target_limit > 0 and round_count >= target_limit:
                self.log(f"被组队已达到目标轮数 {target_limit}，自动停止")
                break

            self.log(f"被组队第 {round_count + 1} 轮开始")
            if self.bezudui_cycle():
                round_count += 1
                self.count = round_count
                self.count_label.config(text=f"已成功运行: {self.count} 轮")
                self.log(f"被组队第 {round_count} 轮结束")
            else:
                self.log("被组队本轮未完成，准备重试")

            time.sleep(1)

        self.log("被组队流程结束")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)


    def start_bezudui(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.count = 0
        self.start_total_time_control()
        self.count_label.config(text=f"已成功运行: {self.count} 轮")
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.bezudui_logic, daemon=True).start()

    # ================= 线程运行控制 =================
    def start_task(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return
        self.update_screen_size()
        self.start_total_time_control()
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.run_logic, daemon=True).start()

    def stop_task(self):
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def screenshot_confirm(self):
        """获取模拟器截图并保存到本地"""
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return
        
        threading.Thread(target=self._do_screenshot_confirm, daemon=True).start()

    def _do_screenshot_confirm(self):
        """在线程中执行截图操作并保存"""
        try:
            self.log("正在获取模拟器截图...")
            
            # 获取截图
            screenshot = self.get_screenshot()
            if screenshot is None:
                self.log("错误：无法获取截图，请检查设备连接")
                self.root.after(0, lambda: messagebox.showerror("错误", "无法获取截图，请检查设备连接"))
                return
            
            # 创建 screenshots 文件夹
            screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            
            # 生成带时间戳的文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = os.path.join(screenshot_dir, filename)
            
            # 保存截图
            cv2.imwrite(filepath, screenshot)
            
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath) / 1024  # 转换为 KB
                self.log(f"✓ 截图已保存: {filename} ({file_size:.1f}KB)")
                self.root.after(0, lambda: messagebox.showinfo("成功", f"截图已保存到:\nscreenshots\\{filename}"))
            else:
                self.log("错误：保存截图失败")
                self.root.after(0, lambda: messagebox.showerror("错误", "保存截图失败"))
                
        except Exception as e:
            self.log(f"截图出错: {e}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"截图出错: {e}"))

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
            if self.check_total_time_limit():
                break
            # --- 新增：检查是否达到目标轮数 ---
            if target_limit > 0 and self.count >= target_limit:
                self.log(f"已达到目标轮数 {target_limit}，脚本自动停止。")
                self.is_running = False
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                break
            if not self.run_dungeon_once(selected_level_name, current_start_img, current_end_img, conf_val):
                break


if __name__ == "__main__":
    from tkinter import messagebox

    root = tk.Tk()
    app = GameBotGUI(root)
    root.mainloop()