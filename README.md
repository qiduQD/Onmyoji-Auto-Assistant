OnmyojiAuto-Assistant: A Cross-Platform Automation Framework Based on OpenCV and ADB

📋 Project Overview

This project is an intelligent automation framework designed for the mobile game Onmyoji. It demonstrates the integration of Computer Vision (CV) and Asynchronous Control to solve repetitive task problems in mobile environments. Unlike traditional macro scripts, this system utilizes template matching for state recognition and adaptive coordinate scaling for cross-device compatibility.

🚀 Key Technical Features

1. Computer Vision-Based State Machine
Template Matching: Utilizes cv2.matchTemplate with Normalized Cross-Correlation (TM_CCOEFF_NORMED) to identify UI elements.

Confidence Thresholding: Implements dynamic threshold filtering to balance between precision and recall, ensuring robust performance under different rendering conditions.

2. Adaptive System Architecture
Resolution Calibration: Automatically retrieves device resolution via wm size and normalizes the coordinate system (e.g., 1600x900) to ensure click accuracy regardless of the source device's aspect ratio.

Non-Blocking Concurrency: Leverages Python's threading and subprocess modules to separate the GUI event loop from the automation logic, preventing UI freezing during heavy CV processing.

3. Intelligent Decision Logic
Randomized Human-Like Interaction: Implements Gaussian-distributed random offsets for tap coordinates and randomized sleep intervals to simulate human behavior and evade basic anti-cheat heuristics.

Battle State Monitoring: A continuous loop monitoring system that detects victory/defeat states and handles unexpected timeouts or pop-ups.

🛠️ Development & Engineering Practices

Object-Oriented Design (OOD): The entire system is encapsulated within a GameBotGUI class, promoting code reusability and maintainability.

Resource Virtualization: Uses a customized get_path utility to handle resource mapping for both source execution and frozen binary (PyInstaller) environments.

Environment Isolation: Developed using isolated virtual environments (venv) to manage dependencies like numpy and opencv-python.

📊 System Logic Flow

Initialization: ADB handshake and device resolution calibration.

Recognition: Captures screen buffer via ADB, decodes into NumPy arrays for OpenCV processing.

Action: Calculates randomized coordinates and dispatches input tap commands via ADB shell.

Loop: State transition from "Waiting" to "In-Battle" to "Settlement".

📧 Contact & Motivation

This project serves as a practical application of Embodied AI and Edge Computing concepts—minimizing computational overhead while maintaining high task accuracy. It reflects my proficiency in Python development, system integration, and problem-solving within the IoT/AI domain.
