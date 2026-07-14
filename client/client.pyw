import math
import sys
import os
from decimal import Decimal
from typing import Optional

import requests
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QRadialGradient, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QScrollArea, QStatusBar, QMessageBox)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:7777")


RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
WHEEL_ORDER = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11,
    30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18,
    29, 7, 28, 12, 35, 3, 26,
]
N_POCKETS = 37
POCKET_ANGLE = 360.0 / N_POCKETS



def pocket_color(n: int) -> QColor:
    if n == 0:
        return QColor("#00a550")
    if n in RED_NUMBERS:
        return QColor("#c0392b")
    return QColor("#1a1a1a")


def get_color_name(n: int) -> str:
    if n == 0:
        return "green"
    return "red" if n in RED_NUMBERS else "black"


def color_emoji(color_name: str) -> str:
    return {"red": "🔴", "black": "⚫", "green": "🟢"}.get(color_name, "")


def api(method: str, path: str, **kwargs):
    url = f"{BACKEND_URL}{path}"
    resp = getattr(requests, method)(url, timeout=8, **kwargs)
    resp.raise_for_status()
    return resp.json()



class RouletteWheel(QWidget):
    spin_finished = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(460, 460)
        self._rotation = 0.0
        self._start_rotation = 0.0
        self._target_rotation = 0.0
        self._result_number: Optional[int] = None
        self._spinning = False
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._total_ticks = 0
        self._current_ticks = 0

    def start_spin(self, result_number: int, duration_ms: int = 6000):
        self._result_number = result_number
        self._spinning = True

        idx = WHEEL_ORDER.index(result_number)
        pocket_center = idx * POCKET_ANGLE
        exact_stop = (-pocket_center) % 360

        full_spins = 8
        current_norm = self._rotation % 360
        delta = (exact_stop - current_norm) % 360
        if delta < 1.0:
            delta += 360

        self._start_rotation = self._rotation
        self._target_rotation = self._rotation + full_spins * 360 + delta

        self._total_ticks = max(1, duration_ms // 16)
        self._current_ticks = 0
        self._anim_timer.start(16)

    def _tick(self):
        self._current_ticks += 1
        t = min(self._current_ticks / self._total_ticks, 1.0)
        ease = 1.0 - (1.0 - t) ** 5
        self._rotation = self._start_rotation + ease * (self._target_rotation - self._start_rotation)
        self.update()
        if self._current_ticks >= self._total_ticks:
            self._anim_timer.stop()
            self._spinning = False
            self._rotation = self._target_rotation
            self.update()
            self.spin_finished.emit(self._result_number or 0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = min(self.width(), self.height())
        cx, cy = self.width() / 2, self.height() / 2
        r = size / 2 - 10

        painter.translate(cx, cy)
        painter.rotate(self._rotation % 360)

        for i, num in enumerate(WHEEL_ORDER):
            center_deg = i * POCKET_ANGLE
            qt_center  = 90.0 - center_deg
            start_qt   = qt_center + POCKET_ANGLE / 2
            span_qt    = -POCKET_ANGLE

            color = pocket_color(num)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#c9a84c"), 1.5))
            painter.drawPie(
                QRectF(-r, -r, 2 * r, 2 * r),
                int(start_qt * 16),
                int(span_qt * 16),
            )

            angle_rad = math.radians(qt_center)
            tx = (r * 0.78) * math.cos(angle_rad)
            ty = -(r * 0.78) * math.sin(angle_rad)
            painter.save()
            painter.translate(tx, ty)
            painter.rotate(-(self._rotation % 360) + center_deg)
            font = QFont("Arial", max(8, int(r / 20)), QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QPen(QColor("#ffffff")))
            fm = painter.fontMetrics()
            text = str(num)
            w = fm.horizontalAdvance(text)
            h = fm.height()
            painter.drawText(int(-w / 2), int(h / 4), text)
            painter.restore()

        painter.resetTransform()
        painter.translate(cx, cy)
        painter.setPen(QPen(QColor("#c9a84c"), 6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

        hub_r = r * 0.12
        grad = QRadialGradient(QPointF(0, 0), hub_r)
        grad.setColorAt(0, QColor("#c9a84c"))
        grad.setColorAt(1, QColor("#7a5c00"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor("#c9a84c"), 2))
        painter.drawEllipse(QRectF(-hub_r, -hub_r, 2 * hub_r, 2 * hub_r))

        painter.resetTransform()
        painter.translate(cx, cy)
        marker_tip_y = -(r - 4)
        marker_size  = 14
        path = QPainterPath()
        path.moveTo(0, marker_tip_y)
        path.lineTo(-marker_size / 2, marker_tip_y - marker_size)
        path.lineTo( marker_size / 2, marker_tip_y - marker_size)
        path.closeSubpath()
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#c9a84c"), 2))
        painter.drawPath(path)


class BetItem(QFrame):
    def __init__(self, bet: dict, highlight: bool = False, loser: bool = False, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        if highlight:
            bg, border = "#1a3a1a", "#00ff88"
        elif loser:
            bg, border = "#3a1a1a", "#ff4444"
        else:
            bg, border = "#1e1e2e", "#3a3a5e"
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        username = bet.get("username") or f"user_{bet.get('user_id', '?')}"
        bet_type = bet.get("bet_type", "")
        value    = bet.get("value", "")
        amount   = bet.get("amount", "0")
        win      = Decimal(bet.get("win_amount", "0"))

        name_label = QLabel(f"<b>{username}</b>")
        name_label.setStyleSheet("color: #e8d5a3; font-size: 26px;")
        type_label = QLabel(f"{bet_type} <i>{value}</i>")
        type_label.setStyleSheet("color: #aaaacc; font-size: 24px;")
        amount_label = QLabel(f"💰 {amount}")
        amount_label.setStyleSheet("color: #c9a84c; font-size: 26px; font-weight: bold;")

        layout.addWidget(name_label)
        layout.addWidget(type_label)
        layout.addStretch()
        layout.addWidget(amount_label)

        if highlight and win > 0:
            win_label = QLabel(f"✅ +{win}")
            win_label.setStyleSheet("color: #00ff88; font-size: 26px; font-weight: bold;")
            layout.addWidget(win_label)
        elif loser:
            lose_label = QLabel(f"❌ -{amount}")
            lose_label.setStyleSheet("color: #ff4444; font-size: 26px; font-weight: bold;")
            layout.addWidget(lose_label)



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TheLastDep Casino — Ведущий")
        self.setMinimumSize(1280, 780)
        self._game: Optional[dict] = None
        self._bets: list[dict] = []
        self._spinning = False
        self._result_shown = False

        self._setup_ui()
        self._apply_stylesheet()

        # Poll timer
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_backend)
        self._poll_timer.start(2000)

        self._poll_backend()


    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        # ── LEFT PANEL ──
        left = QVBoxLayout()
        left.setSpacing(12)

        # Title
        title = QLabel("🎰 TheLastDep Casino")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("title")
        left.addWidget(title)

        # Status badge
        self.status_label = QLabel("⏳ Ожидание")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setObjectName("statusBadge")
        left.addWidget(self.status_label)

        # Wheel
        self.wheel = RouletteWheel()
        self.wheel.spin_finished.connect(self._on_spin_finished)
        left.addWidget(self.wheel, 1)

        # Result display
        self.result_frame = QFrame()
        self.result_frame.setObjectName("resultFrame")
        result_layout = QHBoxLayout(self.result_frame)
        self.result_number_label = QLabel("—")
        self.result_number_label.setObjectName("resultNumber")
        self.result_number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_color_label = QLabel("")
        self.result_color_label.setObjectName("resultColor")
        self.result_color_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(self.result_number_label)
        result_layout.addWidget(self.result_color_label)
        left.addWidget(self.result_frame)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_new_round = QPushButton("🎲 New Round")
        self.btn_new_round.setObjectName("btnGold")
        self.btn_new_round.clicked.connect(self._new_round)
        self.btn_new_round.setMinimumHeight(52)

        self.btn_spin = QPushButton("▶ SPIN")
        self.btn_spin.setObjectName("btnSpin")
        self.btn_spin.clicked.connect(self._spin)
        self.btn_spin.setEnabled(False)
        self.btn_spin.setMinimumHeight(52)

        self.btn_fullscreen = QPushButton("⛶ F11")
        self.btn_fullscreen.setObjectName("btnGray")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.btn_fullscreen.setMinimumHeight(52)
        self.btn_fullscreen.setMaximumWidth(80)

        btn_layout.addWidget(self.btn_new_round)
        btn_layout.addWidget(self.btn_spin)
        btn_layout.addWidget(self.btn_fullscreen)
        left.addLayout(btn_layout)

        root.addLayout(left, 3)

        # ── RIGHT PANEL ──
        right = QVBoxLayout()
        right.setSpacing(8)

        bets_title = QLabel("📋 Ставки раунда")
        bets_title.setObjectName("sectionTitle")
        right.addWidget(bets_title)

        # Stats bar
        self.stats_label = QLabel("Всего ставок: 0 | Сумма: 0 💎")
        self.stats_label.setObjectName("statsLabel")
        right.addWidget(self.stats_label)

        # Scroll area for bets
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("betsScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.bets_container = QWidget()
        self.bets_layout = QVBoxLayout(self.bets_container)
        self.bets_layout.setSpacing(4)
        self.bets_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.bets_container)
        right.addWidget(scroll, 1)

        # Top balances
        top_title = QLabel("🏆 Топ балансов")
        top_title.setObjectName("sectionTitle")
        right.addWidget(top_title)

        self.top_container = QWidget()
        self.top_layout = QVBoxLayout(self.top_container)
        self.top_layout.setSpacing(2)
        self.top_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self.top_container)

        # Connection info
        self.conn_label = QLabel(f"🌐 {BACKEND_URL}")
        self.conn_label.setObjectName("connLabel")
        right.addWidget(self.conn_label)

        root.addLayout(right, 3)

        # Status bar
        self.setStatusBar(QStatusBar())

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0d0d1a;
                color: #e8d5a3;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel#title {
                font-size: 32px;
                font-weight: bold;
                color: #c9a84c;
                letter-spacing: 2px;
            }
            QLabel#statusBadge {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
                background: #2a2a4a;
                border: 2px solid #c9a84c;
                border-radius: 10px;
                padding: 8px;
            }
            QLabel#resultNumber {
                font-size: 80px;
                font-weight: bold;
                color: #ffffff;
                min-width: 120px;
            }
            QLabel#resultColor {
                font-size: 36px;
            }
            QFrame#resultFrame {
                background: #1a1a2e;
                border: 2px solid #c9a84c;
                border-radius: 12px;
                padding: 8px;
            }
            QPushButton#btnGold {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c9a84c, stop:1 #7a5c00);
                color: #0d0d1a;
                font-size: 18px;
                font-weight: bold;
                border: none;
                border-radius: 10px;
                padding: 10px 20px;
            }
            QPushButton#btnGold:hover { background: #d4b96a; }
            QPushButton#btnGold:pressed { background: #7a5c00; }
            QPushButton#btnSpin {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c0392b, stop:1 #7b241c);
                color: #ffffff;
                font-size: 22px;
                font-weight: bold;
                border: none;
                border-radius: 10px;
                padding: 10px 20px;
                letter-spacing: 3px;
            }
            QPushButton#btnSpin:hover { background: #e74c3c; }
            QPushButton#btnSpin:pressed { background: #7b241c; }
            QPushButton#btnSpin:disabled { background: #3a3a3a; color: #666; }
            QPushButton#btnGray {
                background: #2a2a4a;
                color: #e8d5a3;
                font-size: 16px;
                border: 1px solid #c9a84c;
                border-radius: 10px;
            }
            QPushButton#btnGray:hover { background: #3a3a6a; }
            QLabel#sectionTitle {
                font-size: 32px;
                font-weight: bold;
                color: #c9a84c;
                border-bottom: 2px solid #c9a84c;
                padding-bottom: 6px;
            }
            QLabel#statsLabel {
                font-size: 26px;
                color: #aaaacc;
            }
            QScrollArea#betsScroll {
                background: #0d0d1a;
                border: 1px solid #2a2a4a;
                border-radius: 8px;
            }
            QLabel#connLabel {
                font-size: 11px;
                color: #666688;
            }
            QStatusBar {
                background: #0d0d1a;
                color: #666688;
                font-size: 11px;
            }
        """)


    def _poll_backend(self):
        if self._spinning:
            return
        try:
            self._update_top_balances_ui()
            data = api("get", "/api/games/current")
            game = data.get("game")
            self._game = game
            self._update_game_ui(game)

            if game and game["status"] == "finished" and not self._result_shown:
                self._show_result(game)
            elif game and game["status"] == "waiting":
                self._result_shown = False
                bets_data = api("get", f"/api/games/{game['id']}/bets")
                self._bets = bets_data.get("bets", [])
                self._update_bets_ui()
        except Exception as e:
            self.statusBar().showMessage(f"⚠ Нет связи с бэкендом: {e}")

    def _update_game_ui(self, game: Optional[dict]):
        if not game:
            self.status_label.setText("⏳ Нет активного раунда")
            self.status_label.setStyleSheet("color: #aaaacc; background: #2a2a4a; border: 2px solid #555588; border-radius: 10px; padding: 8px; font-size: 18px; font-weight: bold;")
            self.btn_spin.setEnabled(False)
            self.btn_new_round.setEnabled(True)
            return

        status = game["status"]
        gid = game["id"]

        if status == "waiting":
            self.status_label.setText(f"🟡 Раунд #{gid} — Приём ставок")
            self.status_label.setStyleSheet("color: #fff; background: #3a3a00; border: 2px solid #c9a84c; border-radius: 10px; padding: 8px; font-size: 18px; font-weight: bold;")
            self.btn_spin.setEnabled(True)
            self.btn_new_round.setEnabled(False)
        elif status == "spinning":
            self.status_label.setText(f"🔴 Раунд #{gid} — Вращение!")
            self.status_label.setStyleSheet("color: #fff; background: #3a0000; border: 2px solid #c0392b; border-radius: 10px; padding: 8px; font-size: 18px; font-weight: bold;")
            self.btn_spin.setEnabled(False)
            self.btn_new_round.setEnabled(False)
        elif status == "finished":
            self.status_label.setText(f"✅ Раунд #{gid} — Завершён")
            self.status_label.setStyleSheet("color: #fff; background: #003a00; border: 2px solid #00a550; border-radius: 10px; padding: 8px; font-size: 18px; font-weight: bold;")
            self.btn_spin.setEnabled(False)
            self.btn_new_round.setEnabled(True)

    def _update_top_balances_ui(self):
        try:
            data = api("get", "/api/users/top-balances")
            users = data.get("users", [])
        except Exception:
            return

        while self.top_layout.count():
            item = self.top_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        medals = ["🥇", "🥈", "🥉"]
        for i, u in enumerate(users):
            medal = medals[i] if i < 3 else f"{i+1}."
            frame = QFrame()
            frame.setStyleSheet("background: #1e1e2e; border: 1px solid #3a3a5e; border-radius: 4px; padding: 2px;")
            row = QHBoxLayout(frame)
            row.setContentsMargins(6, 2, 6, 2)
            pos = QLabel(medal)
            pos.setStyleSheet("color: #c9a84c; font-size: 24px; font-weight: bold;")
            name = QLabel(f"<b>{u.get('username', '?')}</b>")
            name.setStyleSheet("color: #e8d5a3; font-size: 24px;")
            bal = QLabel(f"⭐ {u.get('balance', '0')}")
            bal.setStyleSheet("color: #c9a84c; font-size: 24px; font-weight: bold;")
            row.addWidget(pos)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(bal)
            self.top_layout.addWidget(frame)

    def _update_bets_ui(self, winning_bet_ids: Optional[set] = None, losing_bet_ids: Optional[set] = None):
        while self.bets_layout.count():
            item = self.bets_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total_amount = sum(Decimal(b["amount"]) for b in self._bets)
        self.stats_label.setText(
            f"Всего ставок: {len(self._bets)} | Сумма: {total_amount:.2f} 💎"
        )

        for bet in self._bets:
            is_winner = winning_bet_ids is not None and bet["id"] in winning_bet_ids
            is_loser  = losing_bet_ids  is not None and bet["id"] in losing_bet_ids
            item = BetItem(bet, highlight=is_winner, loser=is_loser)
            self.bets_layout.addWidget(item)

        if not self._bets:
            empty = QLabel("Ставок пока нет...")
            empty.setStyleSheet("color: #555577; font-size: 24px; padding: 20px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bets_layout.addWidget(empty)

    def _show_result(self, game: dict):
        self._result_shown = True
        num   = game.get("result_number", 0)
        color = game.get("result_color", "")
        color_name = {"red": "🔴 Красное", "black": "⚫ Чёрное", "green": "🟢 Зеро"}.get(color, color)

        self.result_number_label.setText(str(num))
        self.result_color_label.setText(color_name)

        num_color = {"red": "#ff4444", "black": "#ffffff", "green": "#00ff88"}.get(color, "#ffffff")
        self.result_number_label.setStyleSheet(f"font-size: 80px; font-weight: bold; color: {num_color};")

        winning_ids = {b["id"] for b in self._bets if Decimal(b.get("win_amount", "0")) > 0}
        losing_ids  = {b["id"] for b in self._bets if Decimal(b.get("win_amount", "0")) == 0}
        self._update_bets_ui(winning_ids, losing_ids)


    def _new_round(self):
        try:
            data = api("post", "/api/games")
            self._game = data.get("game")
            self._bets = []
            self._result_shown = False
            self.result_number_label.setText("—")
            self.result_color_label.setText("")
            self.result_number_label.setStyleSheet(
                "font-size: 80px; font-weight: bold; color: #ffffff;"
            )
            self._update_bets_ui()
            self._update_game_ui(self._game)
            self.statusBar().showMessage(f"✅ Создан раунд #{self._game['id']}")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                self._poll_backend()
            else:
                QMessageBox.warning(self, "Ошибка", f"Не удалось создать раунд:\n{e}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать раунд:\n{e}")

    def _spin(self):
        if not self._game or self._game["status"] != "waiting":
            return

        game_id = self._game["id"]
        self._spinning = True
        self.btn_spin.setEnabled(False)
        self.btn_new_round.setEnabled(False)

        try:
            data = api("post", f"/api/games/{game_id}/spin")
            result_num = data["result_number"]

            bets_data = api("get", f"/api/games/{game_id}/bets")
            self._bets = bets_data.get("bets", [])
            self._update_bets_ui()
            self._game = data["game"]

            self.status_label.setText("🔴 Вращение...")
            self.wheel.start_spin(result_num, duration_ms=6500)

        except Exception as e:
            self._spinning = False
            QMessageBox.warning(self, "Ошибка", f"Ошибка при вращении:\n{e}")
            self._poll_backend()

    def _on_spin_finished(self, result_num: int):
        self._spinning = False
        if self._game:
            self._show_result(self._game)
            self._update_game_ui(self._game)
        self.statusBar().showMessage(f"Результат: {result_num} ({get_color_name(result_num)})")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self._toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        super().keyPressEvent(event)



def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TheLastDep Casino")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()