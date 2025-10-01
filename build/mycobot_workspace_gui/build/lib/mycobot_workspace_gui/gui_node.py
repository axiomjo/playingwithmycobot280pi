#!/usr/bin/env python3
import sys
import time
from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from pymycobot import MyCobot
from pymycobot import PI_PORT, PI_BAUD

from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

# --- Grid Point Generator ---
def generate_grid_points(x_range=(-200, 200), y_range=(-200, 200), z_values=[100], step=100):
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
        fig = Figure()
        self.ax = fig.add_subplot(111, projection='3d')
        super().__init__(fig)

        self.points = points
        self.colors = [(0, 0, 1, 0.5)] * len(points)  # start as blue with alpha=0.5
        self.scatter = self.ax.scatter(
            [p[0] for p in points],
            [p[1] for p in points],
            [p[2] for p in points],
            c=self.colors,
            s=50
        )

        self.ax.set_xlim(-300, 300)
        self.ax.set_ylim(-300, 300)
        self.ax.set_zlim(0, 300)
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")

    def update_point_color(self, index, color):
        self.colors[index] = color
        self.scatter.remove()
        self.scatter = self.ax.scatter(
            [p[0] for p in self.points],
            [p[1] for p in self.points],
            [p[2] for p in self.points],
            c=self.colors,
            s=50
        )
        self.draw()


# --- Main GUI ---
class WorkspaceGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyCobot Workspace Explorer")
        layout = QtWidgets.QVBoxLayout(self)

        # Connect to robot
        self.mc = MyCobot(PI_PORT, PI_BAUD)

        # Generate grid points
        self.points = generate_grid_points()
        self.current_index = 0

        # Canvas
        self.canvas = MplCanvas(self.points, self)
        layout.addWidget(self.canvas)

        # Force Home button (never disabled)
        self.home_btn = QtWidgets.QPushButton("Force Go Home")
        self.home_btn.clicked.connect(self.go_home)
        layout.addWidget(self.home_btn)

        # Timer for automation
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.check_robot_status)
        self.timer.start(200)

        # Start exploration
        self.move_to_next_point()

    def move_to_next_point(self):
        if self.current_index >= len(self.points):
            print("Exploration finished.")
            return

        target = self.points[self.current_index]
        print(f"Moving to {target}")
        self.mc.send_coords(target, 10, 0)  # non-blocking move
        self.robot_busy = True

    def check_robot_status(self):
        if self.current_index >= len(self.points):
            return

        if not self.mc.is_moving():  # robot finished moving
            # check accuracy
            target = self.points[self.current_index]
            current = self.mc.get_coords()
            error = sum(abs(current[i] - target[i]) for i in range(3))  # xyz error
            if error < 10:  # success tolerance
                color = (1, 1, 1, 0.7)  # white with alpha=0.7
                print(f"Point {self.current_index} OK: {current}")
            else:
                color = (1, 0, 0, 1.0)  # red
                print(f"Point {self.current_index} ERROR, deviation {error}")
            self.canvas.update_point_color(self.current_index, color)

            # move to next
            self.current_index += 1
            self.move_to_next_point()

    def go_home(self):
        print("Force going home!")
        self.mc.send_coords([0, 0, 200, 180, 0, 0], 20, 0)  # Home pose (adjust as needed)


# --- Main entrypoint ---
def main():
    app = QtWidgets.QApplication(sys.argv)
    gui = WorkspaceGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
