import os
import sys
import tempfile
import ctypes
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QUrl, QTimer, QEventLoop
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter, QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
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


def hide_console_window() -> None:
    """Hide the parent terminal window on Windows builds."""
    if os.name != "nt":
        return

    console_window = ctypes.windll.kernel32.GetConsoleWindow()
    if console_window:
        SW_HIDE = 0
        ctypes.windll.user32.ShowWindow(console_window, SW_HIDE)


class PlaybackWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Playback Display")

        self.video_widget = QVideoWidget()
        self.video_widget.setCursor(Qt.BlankCursor)
        self.setCentralWidget(self.video_widget)
        self.setCursor(Qt.BlankCursor)

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
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

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

        window_handle = self.playback_window.windowHandle()
        if window_handle is None:
            # Ensure Qt creates the native window handle before assigning a screen.
            self.playback_window.winId()
            window_handle = self.playback_window.windowHandle()
        if window_handle is None:
            return

        window_handle.setScreen(screen)
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
            self._generate_thumbnail_with_qt(video_path, thumbnail_path)

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

    def _generate_thumbnail_with_qt(self, video_path: Path, thumbnail_path: Path):
        player = QMediaPlayer(self)
        sink = QVideoSink(self)
        player.setVideoSink(sink)

        loop = QEventLoop(self)
        target_position_ms = 2000
        seek_requested = False

        def quit_loop():
            if loop.isRunning():
                loop.quit()

        def on_media_status_changed(status):
            nonlocal seek_requested
            if status == QMediaPlayer.MediaStatus.LoadedMedia:
                player.play()
                if not seek_requested:
                    seek_requested = True
                    QTimer.singleShot(150, lambda: player.setPosition(target_position_ms))

        def on_video_frame_changed(frame):
            image = frame.toImage()
            if image.isNull():
                return

            source = QPixmap.fromImage(image)
            scaled = source.scaled(440, 248, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            canvas = QPixmap(440, 248)
            canvas.fill(QColor("#2E3440"))
            painter = QPainter(canvas)
            x = (canvas.width() - scaled.width()) // 2
            y = (canvas.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()

            canvas.save(str(thumbnail_path), "JPG")
            quit_loop()

        player.mediaStatusChanged.connect(on_media_status_changed)
        sink.videoFrameChanged.connect(on_video_frame_changed)
        player.errorOccurred.connect(lambda *_: quit_loop())

        QTimer.singleShot(4000, quit_loop)
        player.setSource(QUrl.fromLocalFile(str(video_path)))
        loop.exec()

        player.stop()

    def load_selected_video_paused(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return

        self.move_playback_window()
        self.playback_window.showFullScreen()

        self.player.setSource(QUrl.fromLocalFile(path))

        def pause_after_start():
            self.player.pause()
            QTimer.singleShot(0, lambda: self.player.setPosition(0))

        self.player.play()
        QTimer.singleShot(250, pause_after_start)

    def _seek_by(self, delta_ms: int):
        self.player.setPosition(max(0, self.player.position() + delta_ms))

    def _on_position_changed(self, position: int):
        self.position_slider.setValue(position)

    def _on_duration_changed(self, duration: int):
        self.position_slider.setRange(0, duration)

    def _on_media_status_changed(self, status):
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return

        last_frame_position = max(0, self.player.duration() - 1)
        self.player.setPosition(last_frame_position)
        self.player.pause()

    def player_set_position(self, position: int):
        self.player.setPosition(position)


if __name__ == "__main__":
    try:
        hide_console_window()
        app = QApplication(sys.argv)
        app.setApplicationName("Media Playback Controller")

        window = ControlWindow()
        window.show()

        sys.exit(app.exec())
    except Exception:
        print("Failed to open Media Playback Controller.", file=sys.stderr)
        traceback.print_exc()
        print("\nTerminal is frozen so you can review the error. Press Enter to close.", file=sys.stderr)
        try:
            input()
        except EOFError:
            pass
        sys.exit(1)
