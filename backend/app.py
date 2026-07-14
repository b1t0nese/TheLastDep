import logging
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from game_logic import calculate_win, get_color, spin_wheel
from models import Bet, Game, GameStatus, Transaction, TransactionType, User, db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///casino.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"check_same_thread": False},
    "pool_pre_ping": True,
}
WELCOME_BONUS = os.getenv("WELCOME_BONUS", "0.00")
MIN_BET = Decimal(os.getenv("MIN_BET", "1"))
MAX_BET = Decimal(os.getenv("MAX_BET", "500"))

db.init_app(app)

with app.app_context():
    db.create_all()
    logger.info("Database tables created.")

# ─────────────────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────────────────

@app.route("/api/users", methods=["POST"])
def create_or_get_user():
    data = request.get_json(force=True)
    telegram_id = data.get("telegram_id")
    username = data.get("username", "")

    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400

    try:
        user = db.session.get(User, int(telegram_id))
        if user is None:
            user = User(id=int(telegram_id), username=username, balance=Decimal(WELCOME_BONUS))
            db.session.add(user)
            # Welcome bonus transaction
            tx = Transaction(
                user_id=user.id,
                amount=Decimal(WELCOME_BONUS),
                type=TransactionType.deposit.value,
                description="Welcome bonus",
            )
            db.session.add(tx)
            db.session.commit()
            logger.info("New user registered: %s (%s)", telegram_id, username)
            return jsonify({"user": user.to_dict(), "new": True}), 201
        else:
            if username and user.username != username:
                user.username = username
                db.session.commit()
            return jsonify({"user": user.to_dict(), "new": False}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error("DB error in create_or_get_user: %s", e)
        return jsonify({"error": "Database error"}), 500

@app.route("/api/users/<int:user_id>/balance", methods=["GET"])
def get_balance(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user_id": user_id, "balance": str(user.balance)}), 200

@app.route("/api/users/<int:user_id>/history", methods=["GET"])
def get_user_history(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    bets = (
        db.session.execute(
            select(Bet)
            .where(Bet.user_id == user_id)
            .join(Game)
            .where(Game.status == GameStatus.finished.value)
            .order_by(Bet.created_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )

    history = []
    for bet in bets:
        history.append(
            {
                "game_id": bet.game_id,
                "result_number": bet.game.result_number,
                "result_color": bet.game.result_color(),
                "bet_type": bet.bet_type,
                "bet_value": bet.value,
                "amount": str(bet.amount),
                "win_amount": str(bet.win_amount),
                "net": str(bet.win_amount),
                "finished_at": bet.game.finished_at.isoformat() if bet.game.finished_at else None,
            }
        )
    return jsonify({"history": history}), 200

@app.route("/api/users/<int:user_id>/deposit", methods=["POST"])
def deposit(user_id):
    data = request.get_json(force=True)
    try:
        amount = Decimal(str(data.get("amount", 0)))
    except InvalidOperation:
        return jsonify({"error": "Invalid amount"}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        user.balance += amount
        tx = Transaction(
            user_id=user_id,
            amount=amount,
            type=TransactionType.deposit.value,
            description=f"Deposit via bot",
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({"balance": str(user.balance)}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error("DB error in deposit: %s", e)
        return jsonify({"error": "Database error"}), 500

# ─────────────────────────────────────────────────────────
# GAMES
# ─────────────────────────────────────────────────────────

@app.route("/api/games", methods=["POST"])
def create_game():
    # Check no active game
    active = (
        db.session.execute(
            select(Game).where(Game.status.in_(["waiting", "spinning"]))
        )
        .scalars()
        .first()
    )
    if active:
        return jsonify({"error": "Active game already exists", "game": active.to_dict()}), 409

    try:
        game = Game(status=GameStatus.waiting.value)
        db.session.add(game)
        db.session.commit()
        logger.info("New game created: %s", game.id)
        return jsonify({"game": game.to_dict()}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error("DB error in create_game: %s", e)
        return jsonify({"error": "Database error"}), 500

@app.route("/api/games/current", methods=["GET"])
def get_current_game():
    game = (
        db.session.execute(
            select(Game).where(Game.status.in_(["waiting", "spinning"])).order_by(Game.id.desc())
        )
        .scalars()
        .first()
    )
    if not game:
        return jsonify({"game": None}), 200
    return jsonify({"game": game.to_dict()}), 200

@app.route("/api/games/last-finished", methods=["GET"])
def get_last_finished_game():
    game = (
        db.session.execute(
            select(Game).where(Game.status == GameStatus.finished.value).order_by(Game.id.desc())
        )
        .scalars()
        .first()
    )
    if not game:
        return jsonify({"game": None}), 200
    return jsonify({"game": game.to_dict()}), 200

@app.route("/api/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404
    return jsonify({"game": game.to_dict()}), 200

@app.route("/api/games/<int:game_id>/bets", methods=["GET"])
def get_game_bets(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    bets = db.session.execute(select(Bet).where(Bet.game_id == game_id)).scalars().all()
    return jsonify({"bets": [b.to_dict() for b in bets]}), 200

@app.route("/api/games/<int:game_id>/spin", methods=["POST"])
def spin_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404
    if game.status != GameStatus.waiting.value:
        return jsonify({"error": f"Game is in status '{game.status}', expected 'waiting'"}), 400

    try:
        # Transition to spinning
        game.status = GameStatus.spinning.value
        db.session.flush()

        # Generate result
        result_number = spin_wheel()
        game.result_number = result_number
        result_color = get_color(result_number)

        # Calculate winnings for all bets
        bets = db.session.execute(select(Bet).where(Bet.game_id == game_id)).scalars().all()
        winners = []
        for bet in bets:
            user = db.session.get(User, bet.user_id)
            win = calculate_win(bet.bet_type, bet.value, result_number, Decimal(str(bet.amount)))
            bet.win_amount = win

            if win > 0:
                # Return bet + profit
                user.balance += Decimal(str(bet.amount)) + win
                tx_win = Transaction(
                    user_id=bet.user_id,
                    amount=win + Decimal(str(bet.amount)),
                    type=TransactionType.win.value,
                    description=f"Win game #{game_id}: {bet.bet_type} {bet.value}",
                )
                db.session.add(tx_win)
                winners.append(
                    {
                        "user_id": bet.user_id,
                        "username": user.username,
                        "bet_type": bet.bet_type,
                        "bet_value": bet.value,
                        "amount": str(bet.amount),
                        "win_amount": str(win),
                    }
                )
            # If loss: balance was already deducted when bet was placed

        game.status = GameStatus.finished.value
        game.finished_at = datetime.utcnow()
        db.session.commit()

        logger.info("Game #%s finished: result=%s (%s)", game_id, result_number, result_color)
        return jsonify(
            {
                "game": game.to_dict(),
                "result_number": result_number,
                "result_color": result_color,
                "winners": winners,
            }
        ), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error("DB error in spin_game: %s", e)
        return jsonify({"error": "Database error"}), 500

@app.route("/api/games/<int:game_id>/result", methods=["GET"])
def get_game_result(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404
    if game.status != GameStatus.finished.value:
        return jsonify({"error": "Game not finished yet"}), 400

    bets = db.session.execute(select(Bet).where(Bet.game_id == game_id)).scalars().all()
    winning_bets = [b.to_dict() for b in bets if Decimal(str(b.win_amount)) > 0]

    return jsonify(
        {
            "game": game.to_dict(),
            "result_number": game.result_number,
            "result_color": game.result_color(),
            "winning_bets": winning_bets,
            "all_bets": [b.to_dict() for b in bets],
        }
    ), 200

# ─────────────────────────────────────────────────────────
# BETS
# ─────────────────────────────────────────────────────────

@app.route("/api/bets", methods=["POST"])
def place_bet():
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    game_id = data.get("game_id")
    bet_type = data.get("bet_type")
    value = str(data.get("value", ""))
    amount_raw = data.get("amount")

    if not all([user_id, game_id, bet_type, value, amount_raw]):
        return jsonify({"error": "user_id, game_id, bet_type, value, amount required"}), 400

    try:
        amount = Decimal(str(amount_raw))
    except InvalidOperation:
        return jsonify({"error": "Invalid amount"}), 400

    if amount < MIN_BET:
        return jsonify({"error": f"Minimum bet is {MIN_BET}"}), 400
    if amount > MAX_BET:
        return jsonify({"error": f"Maximum bet is {MAX_BET}"}), 400

    VALID_BET_TYPES = {"number", "color", "parity", "dozen", "half", "column"}
    if bet_type not in VALID_BET_TYPES:
        return jsonify({"error": f"Invalid bet_type. Must be one of: {VALID_BET_TYPES}"}), 400

    user = db.session.get(User, int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    game = db.session.get(Game, int(game_id))
    if not game:
        return jsonify({"error": "Game not found"}), 404
    if game.status != GameStatus.waiting.value:
        return jsonify({"error": "Bets are closed for this game"}), 400

    if Decimal(str(user.balance)) < amount:
        return jsonify({"error": "Insufficient balance"}), 400

    try:
        # Deduct balance immediately (reservation)
        user.balance -= amount
        tx = Transaction(
            user_id=int(user_id),
            amount=-amount,
            type=TransactionType.bet.value,
            description=f"Bet game #{game_id}: {bet_type} {value}",
        )
        db.session.add(tx)

        bet = Bet(
            user_id=int(user_id),
            game_id=int(game_id),
            bet_type=bet_type,
            value=value,
            amount=amount,
            win_amount=Decimal("0.00"),
        )
        db.session.add(bet)
        db.session.commit()
        logger.info("Bet placed: user=%s game=%s type=%s val=%s amount=%s", user_id, game_id, bet_type, value, amount)
        return jsonify({"bet": bet.to_dict(), "new_balance": str(user.balance)}), 201

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error("DB error in place_bet: %s", e)
        return jsonify({"error": "Database error"}), 500

@app.route("/api/users/top-balances", methods=["GET"])
def get_top_balances():
    users = db.session.execute(
        select(User).order_by(User.balance.desc()).limit(10)
    ).scalars().all()
    return jsonify({
        "users": [{"id": u.id, "username": u.username, "balance": str(int(u.balance))} for u in users]
    }), 200

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", 7777))
    app.run(host="0.0.0.0", port=port, debug=False)