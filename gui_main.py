import cv2
import numpy as np
import subprocess
import secrets
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


def load_image(image_path):
    """兼容中文路径的图片读取。"""
    try:
        image_data = np.fromfile(image_path, dtype=np.uint8)
        if image_data.size > 0:
            image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
            if image is not None:
                return image
    except Exception:
        pass

    # 作为回退，保留普通读取，兼容少数环境
    return cv2.imread(image_path)


def get_screenshot_dir():
    """返回一个稳定可写的截图目录。"""
    return os.path.join(os.path.expanduser("~"), "OnmyojiAuto", "screenshots")


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
    def __init__(self, root, manager=None):
        self.root = root
        self.manager = manager
        # 初始化图片缓存字典
        self.image_cache = {}
        if not manager:
            self.root.title("Onmyoji Auto · 阴阳师助手")
            self._set_window_icon()
            self.root.geometry("1080x720")
            self.root.minsize(900, 600)
        self.root.configure(bg="#F5F5F7")
        self.is_running = False
        self.devices = []
        self.rng = secrets.SystemRandom()
        self.screen_w = 1600  # 默认值
        self.screen_h = 900  # 默认值
        self.task_start_time = None
        self.total_time_limit_seconds = 0
        self.time_limit_hit = False

        # --- UI 布局 ---
        self._setup_styles()
        self._build_ui()

        # 初始化刷新一次设备
        self.refresh_devices()
        if not manager:
            self.root.protocol("WM_DELETE_WINDOW", self.close_window)

    def _set_window_icon(self):
        try:
            if platform.system() == "Windows":
                icon_path = get_path("app.ico")
                if os.path.exists(icon_path):
                    self.root.iconbitmap(icon_path)
            else:
                icon_png = get_path("app.png")
                if os.path.exists(icon_png):
                    icon_img = tk.PhotoImage(file=icon_png)
                    self.root.iconphoto(True, icon_img)
                    self._icon_img = icon_img
        except Exception as e:
            print(f"窗口图标加载失败: {e}")

    def close_window(self):
        self.is_running = False
        if self.manager:
            self.manager.close_instance(self)
        else:
            self.root.destroy()

    def _setup_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Modern.TCombobox", fieldbackground="#FFFFFF",
                        background="#FFFFFF", foreground="#1D1D1F",
                        bordercolor="#D2D2D7", lightcolor="#D2D2D7",
                        darkcolor="#D2D2D7", padding=7)
        style.map("Modern.TCombobox", fieldbackground=[("readonly", "#FFFFFF")])

    def _label(self, parent, text, size=10, color="#6E6E73", bold=False):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("微软雅黑", size, "bold" if bold else "normal"))

    def _card(self, parent, title, subtitle=None):
        card = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E5EA",
                        highlightthickness=1, bd=0)
        card.pack(fill=tk.X, pady=(0, 12))
        heading = tk.Frame(card, bg="#FFFFFF")
        heading.pack(fill=tk.X, padx=18, pady=(15, 8))
        self._label(heading, title, 13, "#1D1D1F", True).pack(side=tk.LEFT)
        if subtitle:
            self._label(heading, subtitle, 9, "#86868B").pack(side=tk.RIGHT)
        return card

    def _button(self, parent, text, command, bg="#1D1D1F", fg="#FFFFFF",
                width=12, row=0, column=0, colspan=1):
        button = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                           activebackground=bg, activeforeground=fg,
                           relief=tk.FLAT, bd=0, cursor="hand2",
                           highlightthickness=0,
                           font=("微软雅黑", 9, "bold"), width=width,
                           padx=8, pady=7)
        button.grid(row=row, column=column, columnspan=colspan,
                    padx=5, pady=5, sticky="ew")
        return button

    def _build_ui(self):
        root = self.root
        shell = tk.Frame(root, bg="#F5F5F7")
        shell.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        header = tk.Frame(shell, bg="#F5F5F7")
        header.pack(fill=tk.X, pady=(0, 12))
        title_box = tk.Frame(header, bg="#F5F5F7")
        title_box.pack(side=tk.LEFT)
        self._label(title_box, "阴阳师助手", 24, "#1D1D1F", True).pack(anchor="w")
        self._label(title_box, "ONMYOJI AUTO  ·  视觉识别与 ADB 自动化", 9,
                    "#86868B").pack(anchor="w", pady=(3, 0))
        body = tk.Frame(shell, bg="#F5F5F7")
        body.pack(fill=tk.BOTH, expand=True)
        left_shell = tk.Frame(body, bg="#F5F5F7", width=400)
        left_shell.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
        left_shell.pack_propagate(False)
        left_canvas = tk.Canvas(left_shell, bg="#F5F5F7", highlightthickness=0,
                                bd=0)
        left_scrollbar = ttk.Scrollbar(left_shell, orient=tk.VERTICAL,
                                       command=left_canvas.yview)
        left = tk.Frame(left_canvas, bg="#F5F5F7")
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def update_left_scroll_region(_event=None):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))
            left_canvas.itemconfigure(left_window, width=left_canvas.winfo_width())

        left.bind("<Configure>", update_left_scroll_region)
        left_canvas.bind("<Configure>", update_left_scroll_region)

        def scroll_left(event):
            left_canvas.yview_scroll(int(-event.delta / 120), "units")

        left_canvas.bind("<MouseWheel>", scroll_left)
        left.bind("<MouseWheel>", scroll_left)
        right = tk.Frame(body, bg="#F5F5F7")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        connection = self._card(left, "连接设备", "ADB CONNECTION")
        self._label(connection, "ADB 路径", 9).pack(anchor="w", padx=18)
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
        self.adb_path_entry = tk.Entry(connection, bg="#F5F5F7", fg="#1D1D1F",
                                       relief=tk.FLAT, bd=0, font=("Consolas", 9))
        self.adb_path_entry.insert(0, selected_adb if selected_adb else "请手动指定 adb 路径")
        self.adb_path_entry.pack(fill=tk.X, padx=18, pady=(4, 12), ipady=7)
        device_row = tk.Frame(connection, bg="#FFFFFF")
        device_row.pack(fill=tk.X, padx=13, pady=(0, 13))
        self.device_var = tk.StringVar()
        self.device_menu = ttk.Combobox(device_row, textvariable=self.device_var,
                                        width=25, state="readonly",
                                        style="Modern.TCombobox")
        self.device_menu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.refresh_btn = tk.Button(device_row, text="刷新",
                                     command=self.refresh_devices,
                                     bg="#E5E5EA", fg="#1D1D1F",
                                     activebackground="#D2D2D7", relief=tk.FLAT,
                                     bd=0, cursor="hand2", font=("微软雅黑", 9),
                                     padx=8, pady=7)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        self.screenshot_btn = tk.Button(
            device_row, text="截图", command=self.screenshot_confirm,
            bg="#E5E5EA", fg="#1D1D1F", activebackground="#D2D2D7",
            relief=tk.FLAT, bd=0, cursor="hand2", font=("微软雅黑", 9),
            padx=8, pady=7)
        self.screenshot_btn.pack(side=tk.LEFT, padx=(0, 5))

        # 关卡名称与对应图片文件的映射
        self.level_map = {
            "通用": {
                "start": get_path("start_button.png"),
                "end": get_path("finish_mark_300.png")
            },
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
        settings = self._card(left, "任务设置", "TASK SETTINGS")
        level_frame = tk.Frame(settings, bg="#FFFFFF")
        level_frame.pack(fill=tk.X, padx=18, pady=(0, 9))
        self._label(level_frame, "目标关卡", 9).pack(anchor="w")
        self.level_var = tk.StringVar()
        self.level_menu = ttk.Combobox(level_frame, textvariable=self.level_var,
                                       state="readonly", style="Modern.TCombobox")
        self.level_menu['values'] = list(self.level_map.keys())
        self.level_menu.current(0)
        self.level_menu.pack(fill=tk.X, pady=(4, 0))

        self.rest_event_enabled = tk.BooleanVar(value=True)
        threshold = tk.Frame(settings, bg="#FFFFFF")
        threshold.pack(fill=tk.X, padx=18, pady=(0, 8))
        self._label(threshold, "识别阈值", 9).pack(anchor="w")
        self.conf_slider = tk.Scale(threshold, from_=0.1, to=1.0, resolution=0.05,
                                    orient=tk.HORIZONTAL, showvalue=True,
                                    bg="#FFFFFF", fg="#1D1D1F", troughcolor="#D2D2D7",
                                    activebackground="#0A84FF", highlightthickness=0,
                                    length=270)
        self.conf_slider.set(0.8)
        self.conf_slider.pack(fill=tk.X, pady=(0, 3))

        limits = tk.Frame(settings, bg="#FFFFFF")
        limits.pack(fill=tk.X, padx=18, pady=(0, 15))
        self._label(limits, "目标轮数", 9).grid(row=0, column=0, sticky="w")
        self._label(limits, "总时长（分钟）", 9).grid(row=0, column=2, sticky="w", padx=(18, 0))
        self.count = 0  # 初始轮次为 0
        self.break_roll_count = 0  # 结界突破卷计数
        self.menpiao_count = 0  # 门票计数
        self.menpiao_visible = False  # 防止同一画面重复计数
        self.menpiao_templates = [
            get_path("menpiao.png"),
            get_path("menpiao2.png"),
            get_path("menpiao3.png"),
        ]
        self.limit_var = tk.StringVar()
        self.limit_entry = tk.Entry(limits, textvariable=self.limit_var, width=8,
                                    bg="#F5F5F7", relief=tk.FLAT, bd=0)
        self.limit_entry.insert(0, "0")  # 默认 0 轮
        self.limit_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0), ipady=6)
        self.time_limit_var = tk.StringVar()
        self.time_limit_entry = tk.Entry(limits, textvariable=self.time_limit_var, width=8,
                                         bg="#F5F5F7", relief=tk.FLAT, bd=0)
        self.time_limit_entry.insert(0, "0")
        self.time_limit_entry.grid(row=1, column=2, sticky="ew", padx=(18, 0),
                                   pady=(4, 0), ipady=6)
        limits.columnconfigure(0, weight=1)
        limits.columnconfigure(2, weight=1)

        self.btn_frame = tk.Frame(settings, bg="#FFFFFF")
        self.btn_frame.pack(fill=tk.X, padx=13, pady=(0, 13))
        self.combat_btn = self._button(self.btn_frame, "结界突破", self.start_combat_option,
                                       bg="#0A84FF", width=12, row=0, column=0)
        self.hard28_btn = self._button(self.btn_frame, "困难二十八", self.start_hard_28,
                                       bg="#5E5CE6", width=12, row=0, column=1)
        self.draw_roll_btn = self._button(self.btn_frame, "绘卷模式", self.start_draw_roll,
                                          bg="#AF52DE", width=12, row=0, column=2)
        self.draw_roll2_btn = self._button(self.btn_frame, "绘卷模式 2", self.start_draw_roll2,
                                           bg="#AF52DE", width=12, row=1, column=0)
        self.combat8_btn = self._button(self.btn_frame, "阴阳寮突破", self.start_combat_option_8,
                                        bg="#5856D6", width=12, row=1, column=1)
        self.arena_btn = self._button(self.btn_frame, "斗技", self.start_arena,
                                      bg="#FF2D55", width=12, row=1, column=2)
        self.super_ghost_btn = self._button(
            self.btn_frame, "超鬼王低星", self.start_super_ghost,
            bg="#FF375F", width=12, row=2, column=0, colspan=3)
        self.btn_frame.columnconfigure(0, weight=1)
        self.btn_frame.columnconfigure(1, weight=1)
        self.btn_frame.columnconfigure(2, weight=1)

        monitor = self._card(right, "运行监控", "LIVE STATUS")
        stats = tk.Frame(monitor, bg="#FFFFFF")
        stats.pack(fill=tk.X, padx=13, pady=(0, 13))
        self.count_label = self._label(stats, "0 轮", 16, "#0A84FF", True)
        self.roll_label = self._label(stats, "0/30 突破卷", 16, "#FF9500", True)
        self.menpiao_label = self._label(stats, "0/50 门票", 16, "#34C759", True)
        for label in (self.count_label, self.roll_label, self.menpiao_label):
            label.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5, pady=12)

        action_frame = tk.Frame(monitor, bg="#FFFFFF")
        action_frame.pack(fill=tk.X, padx=13, pady=(0, 13))
        self.start_btn = self._button(action_frame, "▶  开始挂机", self.start_task,
                                      bg="#34C759", fg="#FFFFFF", width=12, row=0, column=0)
        self.stop_btn = self._button(action_frame, "■  停止运行", self.stop_task,
                                     bg="#FF3B30", fg="#FFFFFF", width=12, row=0, column=1)
        self.stop_btn.config(state=tk.DISABLED)
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        self.zudui_btn = self._button(action_frame, "组队", self.start_zudui,
                                      bg="#FF9500", width=12, row=1, column=0)
        self.bezudui_btn = self._button(action_frame, "被组队", self.start_bezudui,
                                        bg="#8E8E93", width=12, row=1, column=1)

        log_card = tk.Frame(right, bg="#FFFFFF", highlightbackground="#E5E5EA",
                            highlightthickness=1, bd=0)
        log_card.pack(fill=tk.BOTH, expand=True)
        log_header = tk.Frame(log_card, bg="#FFFFFF")
        log_header.pack(fill=tk.X, padx=18, pady=(15, 8))
        self._label(log_header, "运行日志", 13, "#1D1D1F", True).pack(side=tk.LEFT)
        self._label(log_header, "后台线程实时输出", 9, "#86868B").pack(side=tk.RIGHT)
        self.log_area = scrolledtext.ScrolledText(
            log_card, font=("Consolas", 9), bg="#1D1D1F", fg="#F5F5F7",
            insertbackground="#FFFFFF", selectbackground="#0A84FF",
            relief=tk.FLAT, bd=0, padx=12, pady=12, wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=13, pady=(0, 13))

        def bind_left_mousewheel(widget):
            widget.bind("<MouseWheel>", scroll_left, add="+")
            for child in widget.winfo_children():
                bind_left_mousewheel(child)

        bind_left_mousewheel(left)

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
        self.menpiao_count = 0
        self.menpiao_visible = False
        self.menpiao_label.config(text="门票: 0/50")
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

    def swipe_tap(self, tx, ty):
        end_x = tx + self.rng.randint(-2, 2)
        end_y = ty + self.rng.randint(-2, 2)
        duration = max(60, min(int(self.rng.gauss(120, 25)), 250))
        time.sleep(self.rng.uniform(0.03, 0.10))
        self.adb_command(f"shell input swipe {tx} {ty} {end_x} {end_y} {duration}")
        time.sleep(self.rng.uniform(0.10, 0.25))

    def tap_confirm(self):
        # 为确认按钮提供替代点击：在指定区域随机点击
        x = self.rng.randint(895, 1045)
        y = self.rng.randint(480, 520)
        self.log(f" -> [confirm] 随机点击: ({x}, {y})")
        self.swipe_tap(x, y)

    def tap_confirm_2(self):
        # 为确认按钮提供替代点击：在指定区域随机点击
        x = self.rng.randint(880, 975)
        y = self.rng.randint(505, 545)
        self.log(f" -> [confirm] 随机点击: ({x}, {y})")
        self.swipe_tap(x, y)
    
    def tap_confirm_1(self):
        # 为确认按钮提供替代点击：在指定区域随机点击
        x = self.rng.randint(680, 700)
        y = self.rng.randint(433, 465)
        self.log(f" -> [confirm] 随机点击: ({x}, {y})")
        self.swipe_tap(x, y)
    
    def tap_cancel(self):
        # 为取消按钮提供替代点击：在指定区域随机点击
        x = self.rng.randint(30, 60)
        y = self.rng.randint(30, 60)
        self.log(f" -> [cancel] 随机点击: ({x}, {y})")
        self.swipe_tap(x, y)

    def random_in_offset(self, base, offset=30):
        return self.rng.randint(base - offset, base + offset)

    def get_screenshot(self):
        # 1. 改为列表传参，避免使用 shell=True 带来的额外 cmd.exe 进程开销
        cmd = [self.adb_path_entry.get(), "-s", self.device_var.get(), "shell", "screencap", "-p"]
        
        try:
            import sys
            # 2. 跨平台处理：在 Windows 下使用 creationflags 隐藏控制台，取代 shell=True
            if sys.platform == "win32":
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, creationflags=0x08000000)
            else:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            
            # 3. 增加 timeout，防止模拟器卡死导致脚本线程永久阻塞
            stdout, _ = process.communicate(timeout=5)
            
            if not stdout: 
                return None
                
            # 直接内存解码返回
            return cv2.imdecode(np.frombuffer(stdout.replace(b'\r\n', b'\n'), np.uint8), cv2.IMREAD_COLOR)
            
        except subprocess.TimeoutExpired:
            self.log("警告：ADB 截图请求超时，模拟器可能卡顿")
            return None
        except Exception as e:
            self.log(f"截图发生异常: {e}")
            return None

    def full_screen_random_tap(self):
        # 基于自动获取的分辨率计算安全区域随机点击
        tx = self.rng.randint(460, 630)
        ty = self.rng.randint(800, 900)
        self.log(f" -> [清理中] 随机点击: ({tx}, {ty})")
        self.swipe_tap(tx, ty)

    def swipe_bezier(self, start_x, start_y, end_x, end_y, duration=300, segments=10):
        control_offset = self.rng.randint(-40, 40)
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        control_1 = (
            int(start_x + delta_x * 0.33 - delta_y * control_offset / max(abs(delta_x) + abs(delta_y), 1)),
            int(start_y + delta_y * 0.33 + delta_x * control_offset / max(abs(delta_x) + abs(delta_y), 1))
        )
        control_2 = (
            int(start_x + delta_x * 0.67 - delta_y * control_offset / max(abs(delta_x) + abs(delta_y), 1)),
            int(start_y + delta_y * 0.67 + delta_x * control_offset / max(abs(delta_x) + abs(delta_y), 1))
        )

        points = []
        for index in range(segments + 1):
            t = index / segments
            inverse_t = 1 - t
            x = (
                inverse_t ** 3 * start_x
                + 3 * inverse_t ** 2 * t * control_1[0]
                + 3 * inverse_t * t ** 2 * control_2[0]
                + t ** 3 * end_x
            )
            y = (
                inverse_t ** 3 * start_y
                + 3 * inverse_t ** 2 * t * control_1[1]
                + 3 * inverse_t * t ** 2 * control_2[1]
                + t ** 3 * end_y
            )
            points.append((round(x), round(y)))

        segment_duration = max(1, duration // segments)
        for (segment_start_x, segment_start_y), (segment_end_x, segment_end_y) in zip(points, points[1:]):
            self.adb_command(
                f"shell input swipe {segment_start_x} {segment_start_y} "
                f"{segment_end_x} {segment_end_y} {segment_duration}"
            )

    def swipe_left_full(self):
        # 屏幕从右向左滑动，用于更大范围刷新列表或页面
        x1 = int(self.screen_w * 0.85)
        x2 = int(self.screen_w * 0.15)
        y = int(self.screen_h * 0.5)
        self.log(f" -> [刷新] 左滑屏幕: ({x1},{y}) -> ({x2},{y})")
        self.swipe_bezier(x1, y, x2, y)
        time.sleep(0.8)

    def swipe_up_full(self):
        # 每轮结束后上滑刷新目标列表
        x = self.rng.randint(1332, 1438)
        y1 = int(200)
        y2 = int(635)
        self.log(f" -> [刷新] 上滑屏幕: ({x},{y2}) -> ({x},{y1})")
        self.swipe_bezier(x, y2, x, y1)
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
                # 1. 计算模板中心坐标
                center_x = max_loc[0] + w / 2.0
                center_y = max_loc[1] + h / 2.0
                
                # 2. 高斯分布采样（以中心为偏重，标准差取宽高的 1/6）
                sigma_x, sigma_y = w / 6.0, h / 6.0
                tx = int(self.rng.gauss(center_x, sigma_x))
                ty = int(self.rng.gauss(center_y, sigma_y))
                
                # 3. 边界安全裁切（限制在中心 80% 区域内，防止点击落在边缘）
                margin_x, margin_y = w * 0.1, h * 0.1
                tx = max(int(max_loc[0] + margin_x), min(tx, int(max_loc[0] + w - margin_x)))
                ty = max(int(max_loc[1] + margin_y), min(ty, int(max_loc[1] + h - margin_y)))
                
                # 4. 拟人化参数：随机微抖动与按压时长 (80ms - 200ms)
                end_x = tx + self.rng.randint(-2, 2)
                end_y = ty + self.rng.randint(-2, 2)
                duration = max(60, min(int(self.rng.gauss(120, 25)), 250))
                
                # 5. 点击前随机反应延迟 (30ms - 100ms)
                time.sleep(self.rng.uniform(0.03, 0.10))
                
                # 6. 用原地/微滑 swipe 替代 tap 以模拟真实触摸按压
                self.adb_command(f"shell input swipe {tx} {ty} {end_x} {end_y} {duration}")
                
                # 7. 点击后视线确认停顿 (100ms - 250ms)
                time.sleep(self.rng.uniform(0.10, 0.25))
                
                self.log(f"命中: {os.path.basename(template_path)} ({max_val:.2f}) at ({tx}, {ty})")
            return True
            
        return False

    def scan_menpiao(self, screen, confidence=0.8):
        """轮询三种门票图标，每个连续出现的画面只计数一次。"""
        found_template = None
        for template_path in self.menpiao_templates:
            if self.find_and_tap(
                template_path,
                confidence=confidence,
                do_tap=True,
                screen=screen,
            ):
                found_template = template_path
                break

        found = found_template is not None
        if found and not self.menpiao_visible:
            if self.menpiao_count < 50:
                self.menpiao_count += 1
                self.root.after(
                    0,
                    lambda count=self.menpiao_count: self.menpiao_label.config(
                        text=f"门票: {count}/50"
                    ),
                )
                self.log(
                    f"扫描到门票({os.path.basename(found_template)})，"
                    f"第 {self.menpiao_count}/50 张"
                )
            elif self.menpiao_count == 50:
                self.log("门票已达到50张上限，不再计数")
        self.menpiao_visible = found

    def wait_for_image(self, template_path, timeout=60, confidence=0.5, do_tap=False, interval=1.0):
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
                    time.sleep(0.6)
                    try:
                        # 在主线程弹出提示，避免在工作线程直接调用 tkinter
                        self.root.after(0, lambda: messagebox.showinfo("提示", "有接取悬赏任务，记得完成！"))
                    except Exception:
                        pass
            except Exception:
                pass

            # 使用本轮已有截图扫描门票，避免额外请求模拟器截图
            self.scan_menpiao(current_screen)

            # 检测目标图片，同样传入 current_screen
            if self.find_and_tap(template_path, confidence=confidence, do_tap=False, screen=current_screen):
                if do_tap:
                    time.sleep(0.3) 
                    # 此时画面可能变了，再次检测时让它内部重新截图确认
                    if not self.find_and_tap(template_path, confidence=confidence, do_tap=True):
                        self.log(f"警告：目标 {os.path.basename(template_path)} 在点击时未找到，不执行兜底随机点击")
                        return False
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

        # 1s 内找到 ken.png：+1 卷, 继续点击 finish_mark_300；未找到则结束本次流程
        if self.wait_for_image(get_path("ken.png"), timeout=1, confidence=conf_val, do_tap=False):
            self.log("扫描到 ken.png，结界突破卷 +1")
            self.increment_break_roll()
            self.wait_for_image(mark, timeout=5, confidence=conf_val, do_tap=True)
            self.log("点击 finish_mark_300 完成结算")
            return True
        else:
            self.log("1s 内未扫描到 ken.png，退出本轮结算流程")
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
            self.swipe_tap(x, y)
            time.sleep(1.2)

            # 等待出现 attack 按钮并进入战斗
            if not self.wait_for_image(get_path("attack.png"), timeout=3, confidence=conf_val, do_tap=True):
                self.log("未找到 attack 按钮，跳过此位置")
                continue

            # 普通8次逻辑
            if idx < 9:
                
                self.wait_for_image(get_path("finish_mark_300.png"), timeout=60, confidence=conf_val, do_tap=True)
                time.sleep(2)
                self.wait_for_image(get_path("finish_mark_300.png"), timeout=5, confidence=conf_val, do_tap=True)
                self.log(f"第 {idx} 次位置战斗结束，继续下一个位置")
                time.sleep(2)
                continue

            # 第九次特殊逻辑 (额外处理)
            self.log("第九次特殊逻辑：4 次返回确认 + 重启 + 准备战斗")
            for round_i in range(1, 5):
                if not self.is_running:
                    return False
                time.sleep(2)
                self.tap_cancel()  # 点击左上角返回
                time.sleep(1)
                self.tap_confirm_2()  # 点击确认返回
                time.sleep(1)
                self.wait_for_image(get_path("restart.png"), timeout=10, confidence=conf_val, do_tap=True)
                if self.count == 0:
                    self.wait_for_image(get_path("daliy_confirm.png"), timeout=1, confidence=conf_val, do_tap=False)
                    self.tap_confirm_1()  # 点击每日首次确认
                    self.wait_for_image(get_path("daliy_confirm_button.png"), timeout=1, confidence=conf_val, do_tap=True)
                    self.count += 1
                time.sleep(1)
                self.log(f"第九次循环第 {round_i} 轮: 返回/确认/重启 完成")

            
            self.wait_for_image(get_path("finish_mark_300.png"), timeout=120, confidence=conf_val, do_tap=True)
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
            fail_img = get_path("fail.png")
            finish_img = get_path("finish_mark_300.png")
            while self.is_running:
                x = self.random_in_offset(base_x, 30)
                y = self.random_in_offset(base_y, 30)
                self.log(f"寮突模式第 {idx} 个位置继续 attack: ({x},{y})")
                self.swipe_tap(x, y)
                time.sleep(2)

                if not self.wait_for_image(get_path("attack.png"), timeout=3, confidence=0.8, do_tap=True):
                    self.log(f"第 {idx} 个位置未确认 attack，停止本轮，避免在未知页面点击下一个位置")
                    return False

                # 同时轮询 fail 与 finish：finish 继续当前坐标，fail 或 finish 超时则切换坐标
                fight_timeout = 180
                start_t = time.time()
                finish_detected = False
                while self.is_running and time.time() - start_t < fight_timeout:
                    if self.find_and_tap(fail_img, confidence=0.7, do_tap=False):
                        time.sleep(0.5)
                        # 已经确认 restart 图标存在时，直接点击该模板，避免随机点击误触其他页面控件。
                        self.find_and_tap(fail_img, confidence=0.7, do_tap=True)
                        fail_count += 1
                        self.log(f"第 {idx} 个位置失败，准备切换到下一个位置")
                        time.sleep(2)
                        break

                    if self.find_and_tap(finish_img, confidence=0.7, do_tap=False):
                        time.sleep(0.5)
                        if self.find_and_tap(finish_img, confidence=0.7, do_tap=True):
                            finish_detected = True
                            time.sleep(1.4)
                            break
                        self.log(f"第 {idx} 个位置检测到结算标记后未能确认点击，按失败处理")
                        fail_count += 1
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
        self.log("开始一轮困难二十八流程：button_28 -> search -> 小怪5次 -> boss -> takara/search/button_28")

        # 首先扫描 button_28，3s 没扫描到就跳过到 search 扫描
        button_found = self.wait_for_image(get_path("button_28.png"), timeout=3, confidence=0.9, do_tap=True)
        if not button_found:
            if self.wait_for_image(get_path("break.png"), timeout=1, confidence=0.7, do_tap=False):
                self.log("3s 内未找到 button_28.png，但检测到 break.png，尝试寻找button_28.png并点击")
                for attempt in range(5):
                    self.swipe_up_full()
                    self.log(f"第 {attempt + 1} 次上滑刷新后尝试寻找 button_28.png")
                    if self.wait_for_image(get_path("button_28.png"), timeout=2, confidence=0.88, do_tap=True):
                        self.log("成功找到 button_28.png 并点击")
                        button_found = True
                        break
            self.log("3s 内未找到 button_28.png，转到 search 扫描")


        # search 逻辑：扫描到直接进入，否则本轮结束
        if not self.wait_for_image(get_path("search.png"), timeout=5, confidence=0.6, do_tap=True):
            self.log("未找到 search.png，尝试直接进入战斗扫描")
            
        
        # 进行5次小怪战斗
        fight_count = 0
        swipe_retries = 0
        while self.is_running and fight_count < 5:
            if self.wait_for_image(get_path("attack_28.png"), timeout=3, confidence=0.6, do_tap=True):
                swipe_retries = 0
                if self.process_finish_mark_300(timeout=20):
                    fight_count += 1
                    self.log(f"挑战成功，完成第 {fight_count} 次小怪战斗")
                else:
                    self.log("未检测到finish_mark_300，本次小怪不计数，继续重试")

                if self.break_roll_count >= 27:
                    self.log("结界突破卷已达到27，停止困难28循环")
                    return True
                continue
            # 未检测到 attack_28，进行左滑刷新；最多重试两次，仍未找到则结束小怪阶段
            swipe_retries += 1
            self.log(f"第 {swipe_retries} 次未检测到 attack_28，执行左滑刷新")
            self.swipe_left_full()
            if swipe_retries > 2:
                self.log("连续两次刷新未找到 attack_28，结束小怪战斗流程")
                break

        # boss 战
        if self.wait_for_image(get_path("boss.png"), timeout=3, confidence=0.6, do_tap=True):
            self.process_finish_mark_300(timeout=20)
            time.sleep(3)
            if self.break_roll_count >= 27:
                self.log("结界突破卷已达27，停止困难28循环")
                return True

        # takara/search/button_28 回退机制
        if self.wait_for_image(get_path("takara.png"), timeout=2, confidence=0.8, do_tap=False):
            self.log("找到 takara.png，继续回到 search 流程")
            if self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.8, do_tap=True):
                time.sleep(1)
                self.tap_confirm()
            return True
        if self.wait_for_image(get_path("search.png"), timeout=2, confidence=0.6, do_tap=False):
            self.log("2s内未找到 takara，找到 search.png，继续 search 流程")
            return True
        if self.wait_for_image(get_path("button_28.png"), timeout=2, confidence=0.6, do_tap=True):
            self.log("2s内未找到 takara/search，找到 button_28.png，继续 button_28 流程")
            return True

        self.log("takara/search/button_28 均未找到，结束困难二十八流程")
        if self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.8, do_tap=True):
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
            if not self.wait_for_image(get_path("break.png"), timeout=2, confidence=0.7, do_tap=False):
               if not self.wait_for_image(get_path("search.png"), timeout=2, confidence=0.7, do_tap=False):
                  self.wait_for_image(get_path("back_button.png"), timeout=10, confidence=0.7, do_tap=True)
                  time.sleep(1)
                  self.tap_confirm()
                  time.sleep(1)
               if not self.wait_for_image(get_path("break.png"), timeout=2, confidence=0.7, do_tap=False):
                  self.wait_for_image(get_path("back_button.png"), timeout=3, confidence=0.7, do_tap=True)
                  time.sleep(1)

            self.count += 1
            self.count_label.config(text=f"已成功获取一轮突破卷: {self.count} 轮")

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
            finish_imgs = [get_path("finish_mark.png"), get_path("finish_mark_sp.png"), get_path("finish_mark_sp_2.png")]
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

    def run_super_ghost_low_star(self, conf_val):
        """执行一轮超鬼王低星流程：发现鬼王、准备战斗、等待结算。"""
        if not self.is_running:
            return False

        self.log("等待超鬼王入口...")
        if not self.wait_for_image(
                get_path("find.png"), timeout=10,
                confidence=conf_val, do_tap=True):
            self.log("未找到 find.png，检测是否已经召唤鬼王")

        if not self.wait_for_image(
                get_path("chao.png"), timeout=30,
                confidence=conf_val, do_tap=True):
            self.log("未找到 chao.png，超鬼王本轮未开始")
            return False

        self.log("已进入超鬼王挑战，等待准备按钮...")
        if not self.wait_for_image(
                get_path("prepare.png"), timeout=30,
                confidence=conf_val, do_tap=True):
            self.log("未找到 prepare.png，超鬼王本轮未开始")
            return False

        finish_imgs = [
            get_path("finish_mark.png"),
            get_path("finish_mark_sp.png"),
            get_path("finish_mark_sp_2.png"),
        ]
        finish_detected = False
        matched_finish_img = None
        finish_start_t = time.time()
        self.log("已进入战斗，等待超鬼王结算...")

        while self.is_running and time.time() - finish_start_t < 200:
            if self.check_total_time_limit():
                return False

            for finish_img in finish_imgs:
                if self.find_and_tap(
                        finish_img, confidence=conf_val, do_tap=False):
                    matched_finish_img = finish_img
                    finish_detected = True
                    break

            if finish_detected:
                time.sleep(0.5)
                self.find_and_tap(
                    matched_finish_img, confidence=conf_val, do_tap=True)
                break

            time.sleep(1)

        if not finish_detected:
            self.log("超鬼王战斗等待结算超时")
            return False

        self.count += 1
        self.count_label.config(text=f"{self.count} 轮")
        self.log(f"超鬼王低星第 {self.count} 轮完成")
        return True

    def super_ghost_logic(self):
        self.log("=== 超鬼王低星开始运行 ===")
        conf_val = self.conf_slider.get()

        try:
            target_limit = int(self.limit_var.get())
        except ValueError:
            target_limit = 0
            self.log("目标轮数格式错误，已默认为无限模式")

        while self.is_running:
            if self.check_total_time_limit():
                break
            if target_limit > 0 and self.count >= target_limit:
                self.log(f"已达到目标轮数 {target_limit}，脚本自动停止")
                break
            if not self.run_super_ghost_low_star(conf_val):
                break

        self.log("超鬼王低星流程结束")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def start_super_ghost(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return

        self.update_screen_size()
        self.count = 0
        self.start_total_time_control()
        self.count_label.config(text="0 轮")
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(
            target=self.super_ghost_logic, daemon=True).start()
    
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
            finish_imgs = [get_path("finish_mark.png"), get_path("finish_mark_sp.png"), get_path("finish_mark_sp_2.png")]
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
                messagebox.showerror("错误", "无法获取截图，请检查设备连接")
                return
            
            # 创建用户目录下的 screenshots 文件夹，避免程序目录不可写
            screenshot_dir = get_screenshot_dir()
            os.makedirs(screenshot_dir, exist_ok=True)
            
            # 生成带时间戳的文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = os.path.join(screenshot_dir, filename)
            
            # 保存截图
            saved = cv2.imwrite(filepath, screenshot)
            
            if saved and os.path.exists(filepath):
                file_size = os.path.getsize(filepath) / 1024  # 转换为 KB
                self.log(f"✓ 截图已保存: {filename} ({file_size:.1f}KB)")
                messagebox.showinfo("成功", f"截图已保存到:\n{filepath}")
            else:
                self.log("错误：保存截图失败")
                messagebox.showerror("错误", "保存截图失败")
                
        except Exception as e:
            self.log(f"截图出错: {e}")
            messagebox.showerror("错误", f"截图出错: {e}")

    def rest_event_2(self):
        """休息期间进入另一种界面，等待后返回副本挑战界面。"""
        conf_val = self.conf_slider.get()
        self.log("休息事件2开始")

        self.wait_for_image(get_path("rest_button.png"), timeout=10, confidence=conf_val, do_tap=True)
        rest_event_seconds = self.rng.uniform(10, 20)
        self.log(f"休息事件2等待 {rest_event_seconds:.1f} 秒")
        time.sleep(rest_event_seconds)
        self.wait_for_image(get_path("rest_back.png"), timeout=10, confidence=conf_val, do_tap=True)
        self.log("休息事件2结束，已返回副本挑战界面")

    def run_logic(self):
        self.log("=== 脚本开始运行 ===")
        conf_val = self.conf_slider.get()
        next_rest_time = time.time() + self.rng.uniform(60, 150)  # 下次休息时间随机设置为1~3分钟后

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
            if time.time() >= next_rest_time:
                self.log("达到随机休息时间")
                rest_seconds = self.rng.uniform(30, 90)
                self.log(f"达到随机休息时间，暂停 {rest_seconds / 60:.1f} 分钟")
                # 调用休息事件
                rest_event = self.rest_event_2
                rest_event()
                rest_end_time = time.time() + rest_seconds
                while self.is_running and time.time() < rest_end_time:
                    if self.check_total_time_limit():
                        break
                    time.sleep(1)
                if not self.is_running:
                    break
                self.log("休息结束，继续运行")
                next_rest_time = time.time() + self.rng.uniform(60, 150)  # 下次休息时间随机设置为1~3分钟后
            # --- 新增：检查是否达到目标轮数 ---
            if target_limit > 0 and self.count >= target_limit:
                self.log(f"已达到目标轮数 {target_limit}，脚本自动停止。")
                self.is_running = False
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                break
            if not self.run_dungeon_once(selected_level_name, current_start_img, current_end_img, conf_val):
                break


class AppManager:
    """在单一主窗口中管理多个相互独立的助手实例。"""

    def __init__(self, root):
        self.root = root
        self.instances = []
        self.next_instance_id = 1
        self.root.title("Onmyoji Auto · 多开控制台")
        self.root.geometry("1080x720")
        self.root.minsize(900, 600)
        self.root.configure(bg="#F5F5F7")
        self._set_window_icon()

        self._setup_styles()
        shell = tk.Frame(root, bg="#F5F5F7")
        shell.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        sidebar = tk.Frame(shell, bg="#FFFFFF", width=230,
                           highlightbackground="#E5E5EA",
                           highlightthickness=1)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="阴阳师助手", bg="#FFFFFF", fg="#1D1D1F",
                 font=("微软雅黑", 18, "bold")).pack(anchor="w",
                                                     padx=18, pady=(20, 2))
        tk.Label(sidebar, text="实例设置", bg="#FFFFFF", fg="#86868B",
                 font=("微软雅黑", 9)).pack(anchor="w", padx=18, pady=(0, 18))
        self.instance_status = tk.Label(
            sidebar, text="0 个实例", bg="#F5F5F7", fg="#6E6E73",
            font=("微软雅黑", 9), anchor="w", padx=12, pady=8)
        self.instance_status.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Label(sidebar, text="运行实例", bg="#FFFFFF", fg="#6E6E73",
                 font=("微软雅黑", 9, "bold")).pack(anchor="w",
                                                    padx=18, pady=(2, 6))
        self.instance_list = tk.Listbox(
            sidebar, bg="#F5F5F7", fg="#1D1D1F",
            selectbackground="#DCEBFF", selectforeground="#0A84FF",
            activestyle="none", relief=tk.FLAT, bd=0,
            highlightthickness=0, font=("微软雅黑", 10),
            height=8)
        self.instance_list.pack(fill=tk.BOTH, expand=True, padx=12)
        self.instance_list.bind("<<ListboxSelect>>", self._on_instance_selected)

        sidebar_actions = tk.Frame(sidebar, bg="#FFFFFF")
        sidebar_actions.pack(fill=tk.X, padx=12, pady=14)
        self._sidebar_button(sidebar_actions, "＋  新建实例",
                             self.open_instance, "#0A84FF", "#FFFFFF").pack(
                                 fill=tk.X, pady=(0, 7))
        self._sidebar_button(sidebar_actions, "关闭当前实例",
                             self.close_current, "#E5E5EA", "#1D1D1F").pack(
                                 fill=tk.X)

        self.content = tk.Frame(shell, bg="#F5F5F7")
        self.content.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.close_all)
        self.open_instance()

    def _sidebar_button(self, parent, text, command, bg, fg):
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground=bg, activeforeground=fg,
                         relief=tk.FLAT, bd=0, highlightthickness=0,
                         cursor="hand2", font=("微软雅黑", 9, "bold"),
                         padx=8, pady=9)

    def _setup_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background="#F5F5F7", borderwidth=0)

    def _set_window_icon(self):
        try:
            if platform.system() == "Windows":
                icon_path = get_path("app.ico")
                if os.path.exists(icon_path):
                    self.root.iconbitmap(icon_path)
            else:
                icon_png = get_path("app.png")
                if os.path.exists(icon_png):
                    icon_img = tk.PhotoImage(file=icon_png)
                    self.root.iconphoto(True, icon_img)
                    self._icon_img = icon_img
        except Exception as e:
            print(f"窗口图标加载失败: {e}")

    def open_instance(self):
        instance_number = self.next_instance_id
        self.next_instance_id += 1
        frame = tk.Frame(self.content, bg="#F5F5F7")
        app = GameBotGUI(frame, manager=self)
        self.instances.append(app)
        app.instance_number = instance_number
        self._refresh_instance_list()
        self._show_instance(app)
        self._update_instance_status()
        return app

    def close_instance(self, app):
        if app in self.instances:
            self.instances.remove(app)
        if app.root.winfo_exists():
            app.root.destroy()
        if self.instances:
            self._show_instance(self.instances[-1])
        self._update_instance_status()
        if not self.instances:
            self.open_instance()

    def close_current(self):
        if not self.instances:
            return
        if self.active_instance in self.instances:
            self.active_instance.is_running = False
            self.close_instance(self.active_instance)

    def _on_instance_selected(self, _event=None):
        selection = self.instance_list.curselection()
        if selection and selection[0] < len(self.instances):
            self._show_instance(self.instances[selection[0]])

    def _show_instance(self, app):
        self.active_instance = app
        for instance in self.instances:
            instance.root.pack_forget()
        app.root.pack(fill=tk.BOTH, expand=True)
        self._refresh_instance_list()
        self._update_instance_status()

    def _refresh_instance_list(self):
        if not hasattr(self, "instance_list"):
            return
        active_index = self.instances.index(self.active_instance) \
            if hasattr(self, "active_instance") and self.active_instance in self.instances else 0
        self.instance_list.delete(0, tk.END)
        for app in self.instances:
            device = app.device_var.get() or "未连接设备"
            status = "运行中" if app.is_running else "已停止"
            self.instance_list.insert(tk.END,
                                      f"实例 {app.instance_number}  ·  {status}\n  {device}")
        if self.instances:
            self.instance_list.selection_set(active_index)
            self.instance_list.activate(active_index)

    def _update_instance_status(self):
        if not hasattr(self, "instance_status"):
            return
        count = len(self.instances)
        active = getattr(self, "active_instance", None)
        device = active.device_var.get() if active else ""
        suffix = f" · {device}" if device else ""
        self.instance_status.config(text=f"{count} 个实例{suffix}")

    def close_all(self):
        for app in list(self.instances):
            app.is_running = False
            if app.root.winfo_exists():
                app.root.destroy()
        self.instances.clear()
        if self.root.winfo_exists():
            self.root.destroy()


if __name__ == "__main__":
    from tkinter import messagebox

    root = tk.Tk()
    manager = AppManager(root)
    root.mainloop()