#!/usr/bin/env python3
"""
MyCobot Workspace Explorer (extended)
- Live pose display
- Stop / Pause / Resume controls
- Manual jog (X/Y/Z) with step size
- Speed slider
- Logging to CSV
- 3D scatter: current target highlighted in yellow, successes white, failures red
Requirements:
- Python 3.8
- PyQt5
- matplotlib
- pymycobot 3.4.7
- ROS2 is NOT required in this script (direct pymycobot usage)
"""

import sys
import csv
import time
from datetime import datetime
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from pymycobot.mycobot import MyCobot
from pymycobot import PI_PORT, PI_BAUD

from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


# --- Grid Point Generator ---
def generate_grid_points(x_range=(-300, 300), y_range=(-300, 300), z_values=[40, 50, 100, 200], step=50):
    points = []
    for z in z_values:
        for x in range(x_range[0], x_range[1] + 1, step):
            for y in range(y_range[0], y_range[1] + 1, step):
                coords = [x, y, z, 180.0, 0.0, 0.0]
                points.append(coords)
    print(f"Generated {len(points)} grid points.")
    return points


# --- Matplotlib Canvas for Grid Visualization ---
class MplCanvas(FigureCanvas):
    def __init__(self, points, parent=None):
        fig = Figure(figsize=(6, 5))
        self.ax = fig.add_subplot(111, projection='3d')
        super().__init__(fig)

        self.points = points
        # default: blue translucent (unvisited)
        self.colors = [(0, 0, 1, 0.4)] * len(points)
        # scatter
        self.scatter = self.ax.scatter(
            [p[0] for p in points],
            [p[1] for p in points],
            [p[2] for p in points],
            c=self.colors,
            s=40,
            depthshade=True
        )

        self.ax.set_xlim(-300, 300)
        self.ax.set_ylim(-300, 300)
        self.ax.set_zlim(0, 300)
        self.ax.set_xlabel("X (mm)")
        self.ax.set_ylabel("Y (mm)")
        self.ax.set_zlabel("Z (mm)")

    def update_point_color(self, index, color):
        if not (0 <= index < len(self.points)):
            return
        self.colors[index] = color
        # re-draw scatter with updated colors
        self.scatter.remove()
        self.scatter = self.ax.scatter(
            [p[0] for p in self.points],
            [p[1] for p in self.points],
            [p[2] for p in self.points],
            c=self.colors,
            s=40,
            depthshade=True
        )
        self.draw()

    def highlight_point(self, index):
        # set all unvisited points to original blue, then highlight the index in yellow
        for i in range(len(self.points)):
            # keep passed/failed colors if previously set (white/red) else blue
            if self.colors[i] in [(1, 1, 1, 0.7), (1, 0, 0, 1.0)]:
                continue
            self.colors[i] = (0, 0, 1, 0.4)
        if 0 <= index < len(self.points):
            self.colors[index] = (1, 1, 0, 0.9)  # yellow
        self.scatter.remove()
        self.scatter = self.ax.scatter(
            [p[0] for p in self.points],
            [p[1] for p in self.points],
            [p[2] for p in self.points],
            c=self.colors,
            s=40,
            depthshade=True
        )
        self.draw()


# --- Main GUI ---
class WorkspaceGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyCobot Workspace Explorer")
        self.resize(1000, 700)

        main_layout = QtWidgets.QHBoxLayout(self)
        
        # Left column: controls and readouts
        left_col = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_col, 0)

        # Right column: plot
        right_col = QtWidgets.QVBoxLayout()
        main_layout.addLayout(right_col, 1)

        # Connect to robot
        try:
            self.mc = MyCobot(PI_PORT, PI_BAUD)
            print(" UWESSSS. Connected to MyCobot.")
            
        except Exception as e:
            print("Warning: Failed to connect to MyCobot:", e)
            self.mc = None

        # Generate grid points
        self.points = generate_grid_points()
        self.current_index = 0
        self.robot_busy = False
        self.paused = False
        self.stopped = False

        # Canvas
        self.canvas = MplCanvas(self.points, self)
        right_col.addWidget(self.canvas)

        # Live pose display
        pose_group = QtWidgets.QGroupBox("Live End-Effector Pose")
        pose_layout = QtWidgets.QFormLayout()
        pose_group.setLayout(pose_layout)
        self.pose_labels = {
            'x': QtWidgets.QLabel("N/A"),
            'y': QtWidgets.QLabel("N/A"),
            'z': QtWidgets.QLabel("N/A"),
            'r1': QtWidgets.QLabel("N/A"),
            'r2': QtWidgets.QLabel("N/A"),
            'r3': QtWidgets.QLabel("N/A"),
        }
        pose_layout.addRow("X (mm):", self.pose_labels['x'])
        pose_layout.addRow("Y (mm):", self.pose_labels['y'])
        pose_layout.addRow("Z (mm):", self.pose_labels['z'])
        pose_layout.addRow("R1:", self.pose_labels['r1'])
        pose_layout.addRow("R2:", self.pose_labels['r2'])
        pose_layout.addRow("R3:", self.pose_labels['r3'])
        left_col.addWidget(pose_group)

        # Control buttons: Pause / Resume / Stop / Home / Start / SKIP Exploration
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start")
        self.start_btn.clicked.connect(self.start_exploration)
        btn_layout.addWidget(self.start_btn)

        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self.toggle_pause)
        btn_layout.addWidget(self.pause_btn)

        self.stop_btn = QtWidgets.QPushButton("STOP")
        self.stop_btn.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        self.stop_btn.clicked.connect(self.emergency_stop)
        btn_layout.addWidget(self.stop_btn)

        self.skip_btn = QtWidgets.QPushButton("Skip Point")
        self.skip_btn.clicked.connect(self.skip_point)
        btn_layout.addWidget(self.skip_btn)

        self.color_btn = QtWidgets.QPushButton("Color Current Point Green")
        self.color_btn.clicked.connect(self.color_current_point)
        btn_layout.addWidget(self.color_btn)
        left_col.addLayout(btn_layout)

        self.reset_btn = QtWidgets.QPushButton("Clear Stop / Reset")
        self.reset_btn.clicked.connect(self.clear_stop)
        btn_layout.addWidget(self.reset_btn)
	# track stop state
        self.stopped = False
        

        # Home button (force)
        self.home_btn = QtWidgets.QPushButton("Go Home")
        self.home_btn.clicked.connect(self.go_home)
        left_col.addWidget(self.home_btn)

        # Speed slider
        speed_group = QtWidgets.QGroupBox("Movement Speed")
        speed_layout = QtWidgets.QHBoxLayout()
        self.speed_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.speed_slider.setRange(1, 50)  # reasonable range, map to pymycobot speed
        self.speed_slider.setValue(10)
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(str(v)))
        self.speed_label = QtWidgets.QLabel(str(self.speed_slider.value()))
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        speed_group.setLayout(speed_layout)
        left_col.addWidget(speed_group)

        # Jog controls
        jog_group = QtWidgets.QGroupBox("Manual Jogging")
        jog_layout = QtWidgets.QGridLayout()
        jog_group.setLayout(jog_layout)
        self.step_spin = QtWidgets.QSpinBox()
        self.step_spin.setRange(1, 200)
        self.step_spin.setValue(10)
        jog_layout.addWidget(QtWidgets.QLabel("Step (mm):"), 0, 0)
        jog_layout.addWidget(self.step_spin, 0, 1)

        # X-, X+, Y-, Y+, Z-, Z+
        btn_x_minus = QtWidgets.QPushButton("X -")
        btn_x_minus.clicked.connect(lambda: self.jog_axis(0, -self.step_spin.value()))
        btn_x_plus = QtWidgets.QPushButton("X +")
        btn_x_plus.clicked.connect(lambda: self.jog_axis(0, +self.step_spin.value()))
        btn_y_minus = QtWidgets.QPushButton("Y -")
        btn_y_minus.clicked.connect(lambda: self.jog_axis(1, -self.step_spin.value()))
        btn_y_plus = QtWidgets.QPushButton("Y +")
        btn_y_plus.clicked.connect(lambda: self.jog_axis(1, +self.step_spin.value()))
        btn_z_minus = QtWidgets.QPushButton("Z -")
        btn_z_minus.clicked.connect(lambda: self.jog_axis(2, -self.step_spin.value()))
        btn_z_plus = QtWidgets.QPushButton("Z +")
        btn_z_plus.clicked.connect(lambda: self.jog_axis(2, +self.step_spin.value()))

        jog_layout.addWidget(btn_x_minus, 1, 0)
        jog_layout.addWidget(btn_x_plus, 1, 1)
        jog_layout.addWidget(btn_y_minus, 2, 0)
        jog_layout.addWidget(btn_y_plus, 2, 1)
        jog_layout.addWidget(btn_z_minus, 3, 0)
        jog_layout.addWidget(btn_z_plus, 3, 1)
        left_col.addWidget(jog_group)

        # Status / messages
        self.status_box = QtWidgets.QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumHeight(120)
        left_col.addWidget(self.status_box)

        # Logging controls
        log_layout = QtWidgets.QHBoxLayout()
        self.log_btn = QtWidgets.QPushButton("Export CSV")
        self.log_btn.clicked.connect(self.export_log)
        self.clear_log_btn = QtWidgets.QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        log_layout.addWidget(self.log_btn)
        log_layout.addWidget(self.clear_log_btn)
        left_col.addLayout(log_layout)

        # internal logging list
        self.results = []  # each item: {target, reached, error, pass, timestamp}

        # Timer for automation & live updates
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.check_robot_status)
        self.timer.start(200)  # 200 ms update

        # If user wants to auto-start, call start_exploration here; but keep manual start
        # self.start_exploration()

        # Make sure visualization highlights the first point
        if len(self.points) > 0:
            self.canvas.highlight_point(self.current_index)

    # ---- Robot / Motion helpers ----
    def skip_point(self):
        print(f"[SKIP] Skipping point {self.current_index}")
        self.current_index += 1
        if self.current_index < len(self.points):
            self.move_to_next_point()
        else:
            print("[SKIP] Exploration finished.")


    def color_current_point(self):
        if self.current_index < len(self.points):
            print(f"[COLOR] Coloring point {self.current_index} green")
            self.canvas.update_point_color(self.current_index, (0, 1, 0, 1))  # RGBA



    def safe_mc_send_coords(self, coords, speed):
        """Wrapper to send coords defensively (non-blocking)."""
        if not self.mc:
            self.log("No robot connected.")
            return
        try:
            # send_coords(coord, speed, mode) -> mode often 0 is absolute, keep as 0
            self.mc.send_coords(coords, int(speed), 0)
            self.robot_busy = True
        except Exception as e:
            self.log(f"send_coords failed: {e}")
            # set robot_busy False to avoid stuck state
            self.robot_busy = False

    def safe_mc_get_coords(self):
        if not self.mc:
            return None
        try:
            coords = self.mc.get_coords()  # expects list of 6 floats/ints
            return coords
        except Exception as e:
            # don't spam logs; only occasionally print to console
            # print("get_coords error:", e)
            return None

    def safe_mc_is_moving(self):
        if not self.mc:
            return False
        try:
            return self.mc.is_moving()
        except Exception:
            # If API doesn't have is_moving, fallback to False (risky)
            return False

    def attempt_stop_api(self):
        """Try to call mc.stop() if available. Return True if call made."""
        if not self.mc:
            return False
        try:
            if hasattr(self.mc, "stop"):
                self.mc.stop()
                self.log("Called mc.stop()")
                return True
            # some versions may expose stop_func name differences; attempt a generic call
            # (we try only known name stop here)
        except Exception as e:
            self.log(f"mc.stop() raised: {e}")
        return False

    # ---- UI actions ----
    def start_exploration(self):
        if self.stopped:
            self.log("System stopped. Clear stop to start.")
            return
        if self.paused:
            self.log("Resuming from paused state.")
            self.paused = False
            self.pause_btn.setChecked(False)
        self.log("Starting exploration.")
        # ensure current index is valid
        if self.current_index >= len(self.points):
            self.current_index = 0
            self.log("Restarting from index 0.")
        # highlight current
        self.canvas.highlight_point(self.current_index)
        self.move_to_next_point()

    def toggle_pause(self):
        self.paused = self.pause_btn.isChecked()
        if self.paused:
            self.log("Paused exploration.")
        else:
            self.log("Resumed exploration.")
            # If robot is idle, move on to next
            if not self.robot_busy:
                self.move_to_next_point()

    def emergency_stop(self):
        """Emergency stop - attempt API stop; always set paused/stopped flags."""
        self.stopped = True
        self.paused = True
        self.pause_btn.setChecked(True)
        self.log("EMERGENCY STOP triggered!")

        # try API stop
        ok = self.attempt_stop_api()
        if not ok:
            self.log("mc.stop() not available or failed. Software pausing moves (no further commands will be sent).")
            # As fallback, attempt to send a low-speed command to current coords to reduce motion
            coords = self.safe_mc_get_coords()
            if coords:
                try:
                    speed_small = 1
                    self.mc.send_coords(coords, speed_small, 0)
                    self.log("Issued low-speed hold command to current pose.")
                except Exception as e:
                    self.log(f"Fallback hold command failed: {e}")


    def clear_stop(self):
        if self.stopped:
            print("[RESET] Clearing emergency stop...")
            self.stopped = False

            # Release servos (optional, to re-enable motors cleanly)
            self.mc.release_all_servos()
            time.sleep(0.5)

            # Move robot back to home pose for safety
            self.go_home()

            print("[RESET] System is ready again.")
    

    def go_home(self):
        self.log("PULANG WES!.")
        self.mc.send_angles([0,0,0,0,0,0],10)

    def jog_axis(self, axis_index, delta):
        """axis_index: 0=x,1=y,2=z"""
        if self.paused or self.stopped:
            self.log("Cannot jog while paused/stopped.")
            return
        coords = self.safe_mc_get_coords()
        if coords is None:
            self.log("Cannot read current coords; abort jog.")
            return
        new_coords = coords.copy()
        if axis_index in (0, 1, 2):
            new_coords[axis_index] += delta
        self.log(f"Jogging axis {axis_index} by {delta} mm -> {new_coords[:3]}")
        self.safe_mc_send_coords(new_coords, self.speed_slider.value())

    def move_to_next_point(self):
        if self.paused or self.stopped:
            self.log("Move to next aborted: paused/stopped.")
            return
        if self.current_index >= len(self.points):
            self.log("Exploration finished.")
            return
        target = self.points[self.current_index]
        self.log(f"Moving to {target}  (index {self.current_index})")
        # highlight in plot
        self.canvas.highlight_point(self.current_index)
        # send command
        self.safe_mc_send_coords(target, self.speed_slider.value())

    def check_robot_status(self):
        """Called by timer every 200ms: update live pose, check motion completion and evaluate point"""
        # update live pose
        coords = self.safe_mc_get_coords()
        if coords:
            # update labels (format floats)
            try:
                self.pose_labels['x'].setText(f"{coords[0]:.1f}")
                self.pose_labels['y'].setText(f"{coords[1]:.1f}")
                self.pose_labels['z'].setText(f"{coords[2]:.1f}")
                self.pose_labels['r1'].setText(f"{coords[3]:.1f}")
                self.pose_labels['r2'].setText(f"{coords[4]:.1f}")
                self.pose_labels['r3'].setText(f"{coords[5]:.1f}")
            except Exception:
                pass

        # If we're not busy, but robot may still be moving - check
        if self.current_index >= len(self.points) or self.paused or self.stopped:
            return

        # If robot API provides is_moving, use it; otherwise infer using robot_busy flag and get_coords
        moving = self.safe_mc_is_moving()
        if moving:
            # still moving
            return

        # If we believed robot was moving, and now it isn't => evaluate target
        if self.robot_busy:
            # read final coords
            final = self.safe_mc_get_coords()
            target = self.points[self.current_index]
            if final is None:
                self.log("Could not read final coords for evaluation.")
                # mark as unknown (use gray)
                self.canvas.update_point_color(self.current_index, (0.5, 0.5, 0.5, 0.8))
                result = {
                    'target': target,
                    'reached': None,
                    'error': None,
                    'pass': False,
                    'timestamp': datetime.utcnow().isoformat()
                }
                self.results.append(result)
            else:
                error = abs(final[0] - target[0]) + abs(final[1] - target[1]) + abs(final[2] - target[2])
                if error < 10:
                    # success
                    color = (1, 1, 1, 0.7)  # white
                    self.log(f"Point {self.current_index} OK: final {final[:3]}, error {error:.2f}")
                    passed = True
                else:
                    color = (1, 0, 0, 1.0)  # red
                    self.log(f"Point {self.current_index} FAIL: final {final[:3]}, error {error:.2f}")
                    passed = False
                self.canvas.update_point_color(self.current_index, color)
                result = {
                    'target': target,
                    'reached': final,
                    'error': error,
                    'pass': passed,
                    'timestamp': datetime.utcnow().isoformat()
                }
                self.results.append(result)

            # finished evaluating this point
            self.robot_busy = False
            self.current_index += 1

            # move to next point automatically (if not paused/stopped)
            if not self.paused and not self.stopped:
                # small delay to avoid tight loop
                QtCore.QTimer.singleShot(250, self.move_to_next_point)

    # ---- Logging / UI helpers ----
    def log(self, message):
        t = datetime.now().strftime("%H:%M:%S")
        self.status_box.append(f"[{t}] {message}")
        # also print to console
        print(f"[{t}] {message}")

    def export_log(self):
        if len(self.results) == 0:
            self.log("No results to export.")
            return
        fname = f"workspace_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        try:
            with open(fname, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                header = ["timestamp", "target_x", "target_y", "target_z", "target_r1", "target_r2", "target_r3",
                          "reached_x", "reached_y", "reached_z", "reached_r1", "reached_r2", "reached_r3",
                          "error", "pass"]
                writer.writerow(header)
                for r in self.results:
                    target = r['target']
                    reached = r['reached'] or [None] * 6
                    writer.writerow([
                        r['timestamp'],
                        target[0], target[1], target[2], target[3], target[4], target[5],
                        reached[0], reached[1], reached[2], reached[3], reached[4], reached[5],
                        r['error'], r['pass']
                    ])
            self.log(f"Exported log to {fname}")
        except Exception as e:
            self.log(f"Failed to export log: {e}")

    def clear_log(self):
        self.results = []
        self.log("Cleared log results.")


# --- Main entrypoint ---
def main():
    app = QtWidgets.QApplication(sys.argv)
    gui = WorkspaceGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
