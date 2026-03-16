import cv2
import numpy as np
import subprocess
import random
import time
import tkinter as tk
from tkinter import scrolledtext, ttk
import threading
import re
import sys
import os


def get_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        # 打包后的路径
        return os.path.join(sys._MEIPASS, "assets", relative_path)

    # 源码运行时的路径：当前目录 + assets + 文件名
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", relative_path)
class GameBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("痒痒鼠小助手 v1.0")
        # --- 新增：设置窗口左上角图标 ---
        try:
            # 同样需要 get_path 来确保打包后能找到图标
            icon_path = get_path("app.ico")
            self.root.iconbitmap(icon_path)
        except Exception as e:
            # 如果没有图标文件，程序也会正常运行，不会崩溃
            print(f"窗口图标加载失败: {e}")
        self.root.geometry("600x750")
        self.is_running = False
        self.devices = []
        self.screen_w = 1600  # 默认值
        self.screen_h = 900  # 默认值

        # --- UI 布局 ---
        # 1. ADB 路径
        tk.Label(root, text="ADB 路径:", font=("微软雅黑", 9)).pack(pady=2)
        self.adb_path_entry = tk.Entry(root, width=60)
        possible_adb_paths = [
            get_path("adb.exe"),  # 优先找打包在 assets 里的通用 ADB
            r"C:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe",  # 备选 MuMu 路径
            "adb.exe"  # 最后的兜底：尝试调用系统环境变量
        ]

        selected_adb = ""
        for p in possible_adb_paths:
            if os.path.exists(p):
                selected_adb = p
                break

        self.adb_path_entry = tk.Entry(root, width=60)
        self.adb_path_entry.insert(0, selected_adb if selected_adb else "请手动指定 adb.exe 路径")
        self.adb_path_entry.pack()
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

        # 2. 设备选择区
        device_frame = tk.Frame(root)
        device_frame.pack(pady=10)
        tk.Label(device_frame, text="选择设备:").grid(row=0, column=0)
        self.device_var = tk.StringVar()
        self.device_menu = ttk.Combobox(device_frame, textvariable=self.device_var, width=25, state="readonly")
        self.device_menu.grid(row=0, column=1, padx=5)
        tk.Button(device_frame, text="刷新设备列表", command=self.refresh_devices).grid(row=0, column=2)

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
        tk.Label(root, text="识别阈值 (推荐 0.5-0.6):").pack(pady=2)
        self.conf_slider = tk.Scale(root, from_=0.1, to=1.0, resolution=0.05, orient=tk.HORIZONTAL, length=200)
        self.conf_slider.set(0.5)
        self.conf_slider.pack()

        # 4. 控制按钮
        self.btn_frame = tk.Frame(root)
        self.btn_frame.pack(pady=15)
        self.start_btn = tk.Button(self.btn_frame, text="开始挂机", command=self.start_task, bg="#4CAF50", fg="white",
                                   width=15)
        self.start_btn.grid(row=0, column=0, padx=10)
        self.stop_btn = tk.Button(self.btn_frame, text="停止运行", command=self.stop_task, state=tk.DISABLED,
                                  bg="#F44336", fg="white", width=15)
        self.stop_btn.grid(row=0, column=1, padx=10)
        self.count = 0  # 初始轮次为 0
        self.count_label = tk.Label(root, text="已成功运行: 0 轮", font=("微软雅黑", 12, "bold"), fg="#1E90FF")
        # --- 目标轮数设置区 ---
        limit_frame = tk.Frame(root)
        limit_frame.pack(pady=5)
        tk.Label(limit_frame, text="目标轮数 (0表示无限):").grid(row=0, column=0)

        self.limit_var = tk.StringVar()
        self.limit_entry = tk.Entry(limit_frame, textvariable=self.limit_var, width=10)
        self.limit_entry.insert(0, "0")  # 默认 0 轮
        self.limit_entry.grid(row=0, column=1, padx=5)
        self.count_label.pack(pady=5)



        # 5. 日志窗口
        tk.Label(root, text="运行日志:").pack()
        self.log_area = scrolledtext.ScrolledText(root, width=75, height=25, font=("Consolas", 9))
        self.log_area.pack(pady=10)

        # 初始化刷新一次设备
        self.refresh_devices()

    # ================= 智能化工具函数 =================
    def log(self, message):
        now = time.strftime("%H:%M:%S", time.localtime())
        self.log_area.insert(tk.END, f"[{now}] {message}\n")
        self.log_area.see(tk.END)

    def refresh_devices(self):
        """获取当前所有连接的 ADB 设备"""
        try:
            adb = self.adb_path_entry.get()
            result = subprocess.run(f'"{adb}" devices', shell=True, capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')[1:]
            self.devices = [line.split('\t')[0] for line in lines if line.strip()]

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

    def get_screenshot(self):
        cmd = f'"{self.adb_path_entry.get()}" -s {self.device_var.get()} shell screencap -p'
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        stdout, _ = process.communicate()
        if not stdout: return None
        return cv2.imdecode(np.frombuffer(stdout.replace(b'\r\n', b'\n'), np.uint8), cv2.IMREAD_COLOR)

    def full_screen_random_tap(self):
        # 基于自动获取的分辨率计算安全区域
        tx = random.randint(int(self.screen_w * 0.3), int(self.screen_w * 0.7))
        ty = random.randint(int(self.screen_h * 0.4), int(self.screen_h * 0.8))
        self.log(f" -> [清理中] 随机点击: ({tx}, {ty})")
        self.adb_command(f"shell input tap {tx} {ty}")

    def find_and_tap(self, template_path, confidence=0.5, do_tap=True):
        # 此时 template_path 已经是 get_path 处理过的绝对路径了
        template = cv2.imread(template_path)

        if template is None:
            self.log(f"错误：无法读取资源文件 -> {os.path.basename(template_path)}")
            return False

        screen = self.get_screenshot()
        if screen is None: return False

        h, w = template.shape[:2]
        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= confidence:
            if do_tap:
                mw, mh = int(w * 0.1), int(h * 0.1)
                tx = random.randint(max_loc[0] + mw, max_loc[0] + w - mw)
                ty = random.randint(max_loc[1] + mh, max_loc[1] + h - mh)
                self.adb_command(f"shell input tap {tx} {ty}")
                # 使用 os.path.basename 只显示文件名，不显示长路径
                self.log(f"命中: {os.path.basename(template_path)} ({max_val:.2f})")
            return True
        return False

    # ================= 线程运行控制 =================
    def start_task(self):
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择一个设备！")
            return
        self.update_screen_size()
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
                    while self.is_running:
                        # --- 修正点 1：使用变量 current_start_img 而非死代码 ---
                        if self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                            self.count += 1
                            self.count_label.config(text=f"已成功运行: {self.count} 轮")
                            self.log(f"第 {self.count} 轮结束，回到主界面")
                            break
                        self.full_screen_random_tap()
                        time.sleep(random.uniform(1.0, 1.5))
                    break  # 跳出战斗监控循环

                # 超_时/挂机处理
                if time.time() - start_time > 22:
                    # --- 修正点 2：超时检测也要用变量 ---
                    if self.find_and_tap(current_start_img, confidence=conf_val, do_tap=False):
                        self.count += 1
                        self.count_label.config(text=f"已成功运行: {self.count} 轮")
                        break  # --- 修正点 3：必须 break 跳出阶段 2 ---

                    self.full_screen_random_tap()
                    # 每次乱点后重置一点时间，避免疯狂点击
                    start_time = time.time() - 15

                time.sleep(1)


if __name__ == "__main__":
    from tkinter import messagebox

    root = tk.Tk()
    app = GameBotGUI(root)
    root.mainloop()