import os
import sys
import tempfile
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QUrl, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter, QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSlider,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".webm"}


class PlaybackWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Playback Display")

        self.video_widget = QVideoWidget()
        self.setCentralWidget(self.video_widget)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.audio.setVolume(0.9)


class ControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Playback Controller")
        self.resize(1200, 800)

        self.playback_window = PlaybackWindow()

        self.thumb_cache = Path(tempfile.gettempdir()) / "media_playback_thumbs"
        self.thumb_cache.mkdir(exist_ok=True)

        self._build_ui()
        self._connect_signals()
        self._populate_screens()

        self.player = self.playback_window.player
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.errorOccurred.connect(self._on_player_error)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._pause_on_load = False

    def _build_ui(self):
        toolbar = QToolBar("Playback Controls")
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        open_folder_action = QAction("Open Folder", self)
        open_folder_action.triggered.connect(self.open_folder)
        toolbar.addAction(open_folder_action)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("Playback Monitor: "))
        self.monitor_combo = QComboBox()
        self.monitor_combo.currentIndexChanged.connect(self.move_playback_window)
        toolbar.addWidget(self.monitor_combo)

        toolbar.addSeparator()

        self.play_btn = QAction(self.style().standardIcon(QStyle.SP_MediaPlay), "Play", self)
        self.pause_btn = QAction(self.style().standardIcon(QStyle.SP_MediaPause), "Pause", self)
        self.rewind_btn = QAction(self.style().standardIcon(QStyle.SP_MediaSeekBackward), "Reverse -10s", self)
        self.forward_btn = QAction(self.style().standardIcon(QStyle.SP_MediaSeekForward), "Forward +10s", self)

        toolbar.addAction(self.play_btn)
        toolbar.addAction(self.pause_btn)
        toolbar.addAction(self.rewind_btn)
        toolbar.addAction(self.forward_btn)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)

        central = QWidget()
        layout = QVBoxLayout(central)

        hint = QLabel("Bottom list: click any video to open it paused in fullscreen on selected monitor.")
        hint.setStyleSheet("font-size: 14px;")
        layout.addWidget(hint)

        self.video_list = QListWidget()
        self.video_list.setViewMode(QListWidget.IconMode)
        self.video_list.setIconSize(QSize(220, 124))
        self.video_list.setResizeMode(QListWidget.Adjust)
        self.video_list.setSpacing(12)
        self.video_list.setWordWrap(True)
        self.video_list.setMovement(QListWidget.Static)
        layout.addWidget(self.video_list, stretch=1)

        layout.addWidget(self.position_slider)

        self.setCentralWidget(central)

    def _connect_signals(self):
        self.play_btn.triggered.connect(self.playback_window.player.play)
        self.pause_btn.triggered.connect(self.playback_window.player.pause)
        self.forward_btn.triggered.connect(lambda: self._seek_by(10_000))
        self.rewind_btn.triggered.connect(lambda: self._seek_by(-10_000))
        self.position_slider.sliderMoved.connect(self.player_set_position)
        self.video_list.itemClicked.connect(self.load_selected_video_paused)

    def _populate_screens(self):
        self.monitor_combo.clear()
        for i, screen in enumerate(QApplication.screens()):
            geometry = screen.geometry()
            label = f"Display {i + 1}: {geometry.width()}x{geometry.height()} @ ({geometry.x()},{geometry.y()})"
            self.monitor_combo.addItem(label, i)

    def move_playback_window(self):
        index = self.monitor_combo.currentData()
        if index is None:
            return

        screens = QApplication.screens()
        if index >= len(screens):
            return

        screen = screens[index]

        if not self.playback_window.isVisible():
            self.playback_window.show()
            QApplication.processEvents()

        handle = self.playback_window.windowHandle()
        if handle is not None:
            handle.setScreen(screen)

        self.playback_window.setGeometry(screen.geometry())

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select video folder")
        if not folder:
            return

        self.video_list.clear()
        videos = [p for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in SUPPORTED_EXTENSIONS]

        if not videos:
            QMessageBox.information(self, "No videos found", "No supported video files were found in this folder.")
            return

        for video in videos:
            icon = QIcon(self._thumbnail_for(video))
            item = QListWidgetItem(icon, video.name)
            item.setData(Qt.UserRole, str(video))
            item.setSizeHint(QSize(240, 168))
            self.video_list.addItem(item)

    def _thumbnail_for(self, video_path: Path) -> str:
        thumbnail_path = self.thumb_cache / f"{video_path.stem}.jpg"

        if not thumbnail_path.exists():
            ffmpeg_exists = False
            try:
                subprocess.run(["ffmpeg", "-version"], capture_output=True, check=False)
                ffmpeg_exists = True
            except FileNotFoundError:
                ffmpeg_exists = False

            if ffmpeg_exists:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        "00:00:02",
                        "-i",
                        str(video_path),
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=440:248:force_original_aspect_ratio=decrease,pad=440:248:(ow-iw)/2:(oh-ih)/2",
                        str(thumbnail_path),
                    ],
                    capture_output=True,
                    check=False,
                )

        if thumbnail_path.exists():
            return str(thumbnail_path)

        placeholder = self.thumb_cache / "placeholder.jpg"
        if not placeholder.exists():
            pixmap = QPixmap(440, 248)
            pixmap.fill(QColor("#2E3440"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#ECEFF4"))
            painter.setFont(QFont("Segoe UI", 18, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "No Preview")
            painter.end()
            pixmap.save(str(placeholder), "JPG")
        return str(placeholder)

    def load_selected_video_paused(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return

        self.player.stop()
        self.move_playback_window()
        self.playback_window.showFullScreen()

        self._pause_on_load = True
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._pause_on_load:
            self._pause_on_load = False
            self.player.pause()
            self.player.setPosition(0)

    def _on_player_error(self, _error, message: str):
        if not message:
            return
        QMessageBox.warning(self, "Playback Error", f"Could not open video:\n{message}")

    def _seek_by(self, delta_ms: int):
        self.player.setPosition(max(0, self.player.position() + delta_ms))

    def _on_position_changed(self, position: int):
        self.position_slider.setValue(position)

    def _on_duration_changed(self, duration: int):
        self.position_slider.setRange(0, duration)

    def player_set_position(self, position: int):
        self.player.setPosition(position)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Media Playback Controller")

    window = ControlWindow()
    window.show()

    sys.exit(app.exec())
