from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class GameStatus(PyEnum):
    waiting = "waiting"
    spinning = "spinning"
    finished = "finished"


class BetType(PyEnum):
    number = "number"
    color = "color"
    parity = "parity"
    dozen = "dozen"
    half = "half"
    column = "column"


class TransactionType(PyEnum):
    bet = "bet"
    win = "win"
    deposit = "deposit"
    refund = "refund"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.BigInteger, primary_key=True)  # Telegram ID
    username = db.Column(db.String(128), nullable=True)
    balance = db.Column(db.Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    bets = db.relationship("Bet", back_populates="user", lazy="dynamic")
    transactions = db.relationship("Transaction", back_populates="user", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "balance": str(int(self.balance)),
            "created_at": self.created_at.isoformat(),
        }


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    status = db.Column(db.String(16), nullable=False, default=GameStatus.waiting.value)
    result_number = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    bets = db.relationship("Bet", back_populates="game", lazy="dynamic")

    def result_color(self):
        if self.result_number is None:
            return None
        if self.result_number == 0:
            return "green"
        reds = {
            1, 3, 5, 7, 9, 12, 14, 16, 18,
            19, 21, 23, 25, 27, 30, 32, 34, 36,
        }
        return "red" if self.result_number in reds else "black"

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "result_number": self.result_number,
            "result_color": self.result_color(),
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class Bet(db.Model):
    __tablename__ = "bets"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    bet_type = db.Column(db.String(16), nullable=False)
    value = db.Column(db.String(32), nullable=False)  # "7", "red", "even", "1", ...
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    win_amount = db.Column(db.Numeric(18, 2), nullable=True, default=Decimal("0.00"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", back_populates="bets")
    game = db.relationship("Game", back_populates="bets")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "game_id": self.game_id,
            "bet_type": self.bet_type,
            "value": self.value,
            "amount": str(int(self.amount)),
            "win_amount": str(int(self.win_amount)) if self.win_amount is not None else "0",
        }


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    type = db.Column(db.String(16), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    description = db.Column(db.String(256), nullable=True)

    user = db.relationship("User", back_populates="transactions")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": str(self.amount),
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
        }
