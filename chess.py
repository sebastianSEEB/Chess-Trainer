import tkinter as tk
from tkinter import ttk
from tkinter import colorchooser
import os
import json
import threading
import random
import csv

try:
    import chess
    import chess.engine
    import chess.pgn
except ImportError:
    print("Missing Library: Please run 'pip install chess'")
    exit()

# --- CONFIGURATION ---
SQUARE_SIZE = 75
COLORS = {
    "light": "#d2b48c", "dark": "#8b5a2b", 
    "last_light": "#e6e660", "last_dark": "#c4c442",
    "select": "#ffff7f", "highlight": "#2de62d", 
    "bg": "#1e1e1e", "panel": "#2d2d2d", "text": "#ffffff",
    "best": "#4CAF50", "blunder": "#f44336", "inaccuracy": "#ffeb3b",
    "btn_bg": "#3c3f41", "btn_hover": "#505354", "accent": "#007acc",
    "arrow_plan": "#ff9800", "arrow_hint": "#00e5ff",
    "tactic": "#9c27b0"
}
DATA_FILE = "chess_data.json"
STOCKFISH_PATH = "./stockfish.exe" 
PIECE_SHAPES = {
    chess.KING: '♚', chess.QUEEN: '♛', chess.ROOK: '♜', 
    chess.BISHOP: '♝', chess.KNIGHT: '♞', chess.PAWN: '♟'
}

# --- STORAGE & MANAGERS ---
class StorageManager:
    def __init__(self):
        self.data = {
            "elo": 1000, "puzzle_streak": 0, "max_streak": 0, 
            "seen_puzzles": [], "saved_session": None,
            "stats": {"wins": 0, "losses": 0, "draws": 0, "highest_elo_beaten": 0},
            "heatmap": {"0": "#0000ff", "1": "#3300cc", "2": "#660099", "3": "#990066", "4": "#cc0033", "5": "#ff0000"}
        }
        self.load()

    def load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f: 
                    loaded = json.load(f)
                    for k, v in loaded.items():
                        if isinstance(v, dict) and isinstance(self.data.get(k), dict): 
                            self.data[k].update(v)
                        else: 
                            self.data[k] = v
                            
                if "0" not in self.data["heatmap"]:
                    self.data["heatmap"] = {"0": "#0000ff", "1": "#3300cc", "2": "#660099", "3": "#990066", "4": "#cc0033", "5": "#ff0000"}
            except json.JSONDecodeError: pass

    def save(self):
        with open(DATA_FILE, "w") as f: json.dump(self.data, f, indent=4)

    def record_game_result(self, result, cpu_elo):
        if result == "1-0":
            self.data["stats"]["wins"] += 1
            if cpu_elo > self.data["stats"]["highest_elo_beaten"]:
                self.data["stats"]["highest_elo_beaten"] = cpu_elo
        elif result == "0-1": self.data["stats"]["losses"] += 1
        else: self.data["stats"]["draws"] += 1
        self.save()

    def save_session(self, mode, cpu_elo, start_fen, cpu_color, trainer_desc, moves):
        if mode in ["puzzle", "review"]: return
        self.data["saved_session"] = {
            "mode": mode, "cpu_elo": cpu_elo, "start_fen": start_fen, 
            "cpu_color": cpu_color, "trainer_desc": trainer_desc, "moves": moves
        }
        self.save()

    def clear_session(self):
        self.data["saved_session"] = None
        self.save()

class PuzzleManager:
    def __init__(self, master):
        self.master = master
        self.current = None
        self.solution_moves = []
        self.puzzles = []
        
        self.load_database()

    def load_database(self):
        json_file = "puzzles_db.json"
        csv_file = "lichess_db_puzzle.csv"

        if not os.path.exists(json_file) and os.path.exists(csv_file):
            print("CSV found! Generating puzzle database... this will just take a second.")
            self.generate_json_from_csv(csv_file, json_file)

        try:
            with open(json_file, "r") as f: 
                self.puzzles = json.load(f)
            print(f"Success: Loaded {len(self.puzzles)} puzzles from database.")
        except FileNotFoundError:
            print("Warning: Neither puzzles_db.json nor lichess_db_puzzle.csv found. Using fallback.")
            self.puzzles = [
                {"fen": "q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17", "solution": ["e8d7", "a2e6", "d7d8", "f7f8"], "elo": 800, "theme": "Mate in 2"},
                {"fen": "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", "solution": ["e1e2", "f6h5", "g1f3"], "elo": 900, "theme": "Blunder Punish"}
            ]

    def generate_json_from_csv(self, csv_file, json_file):
        extracted_puzzles = []
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader) 
                
                for row in reader:
                    rating = int(row[3])
                    themes = row[7]

                    if "mate" in themes or "crushing" in themes:
                        display_theme = "Find the Mate" if "mate" in themes else "Win Material"
                        extracted_puzzles.append({
                            "fen": row[1],
                            "solution": row[2].split(" "),
                            "elo": rating,
                            "theme": display_theme
                        })

                    if len(extracted_puzzles) >= 2000:
                        break

            random.shuffle(extracted_puzzles)
            with open(json_file, "w") as f:
                json.dump(extracted_puzzles, f, indent=4)
        except Exception as e:
            print(f"Failed to parse CSV: {e}")

    def load_next(self, retry=False):
        if retry and self.current:
            self.solution_moves = self.current["solution"].copy()
        else:
            user_elo = self.master.storage.data['elo']
            seen = self.master.storage.data['seen_puzzles']
            
            suitable = [p for p in self.puzzles if abs(p['elo'] - user_elo) <= 500 and p['fen'] not in seen]
            if not suitable: 
                suitable = self.puzzles 
                self.master.storage.data['seen_puzzles'] = []
                
            self.current = random.choice(suitable)
            self.master.storage.data['seen_puzzles'].append(self.current['fen'])
            self.master.storage.save()
            
            self.solution_moves = self.current["solution"].copy()
            
        if len(self.solution_moves) < 2:
            self.master.after(10, self.load_next)
            return

        original_fen = self.current["fen"]
        opponent_color = chess.Board(original_fen).turn
        setup_move_uci = self.solution_moves.pop(0)

        self.master.switch_frame(GameUI, mode="puzzle", start_fen=original_fen, cpu_color=opponent_color, puzzle_logic=self, trainer_desc=f"Goal: {self.current['theme']}")
        
        ui = self.master.current_frame
        ui.game.push(chess.Move.from_uci(setup_move_uci))
        ui.view_ply += 1
        ui.update_move_list_ui()
        ui.update_turn_indicator()
        ui.draw_board()
        
        ui.puzzle_elo_lbl.config(text=f"Puzzle Rating: {self.current['elo']} ELO")
        ui.puzzle_feedback_lbl.config(text="Find the best move!", fg=COLORS["text"])

    def verify_move(self, move_san):
        ui = self.master.current_frame
        
        if not self.solution_moves:
            return False

        expected_move = self.solution_moves.pop(0)
        
        if move_san == expected_move:
            if not self.solution_moves:
                self.master.storage.data["puzzle_streak"] += 1
                if self.master.storage.data["puzzle_streak"] > self.master.storage.data["max_streak"]:
                    self.master.storage.data["max_streak"] = self.master.storage.data["puzzle_streak"]
                self.master.storage.data["elo"] += 10
                self.master.storage.save()
                
                ui.is_evaluating_game = True 
                ui.puzzle_feedback_lbl.config(text="Correct! Loading next...", fg=COLORS["best"])
                ui.streak_lbl.config(text=f"🔥 Streak: {self.master.storage.data['puzzle_streak']}")
                self.master.after(1500, self.load_next)
            else:
                ui.puzzle_feedback_lbl.config(text="Good! Opponent moved...", fg=COLORS["highlight"])
                opponent_reply = self.solution_moves.pop(0)
                ui.game.push(chess.Move.from_uci(opponent_reply))
                ui.view_ply += 1
                ui.update_move_list_ui()
                ui.update_turn_indicator()
                ui.draw_board()
            return True
        else:
            self.master.storage.data["puzzle_streak"] = 0
            self.master.storage.data["elo"] = max(800, self.master.storage.data["elo"] - 15)
            self.master.storage.save()
            
            ui.is_evaluating_game = True 
            ui.puzzle_feedback_lbl.config(text="Wrong move! Restarting...", fg=COLORS["blunder"])
            ui.streak_lbl.config(text=f"🔥 Streak: 0")
            
            self.master.after(1500, lambda: self.load_next(retry=True))
            return False

class EngineManager:
    def __init__(self):
        self.engine = None
        self.is_thinking = False
        self.lock = threading.Lock()

    def start(self):
        try: self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        except Exception as e: print(f"Engine Warning: {e}")

    def quit(self):
        if self.engine:
            try: self.engine.quit()
            except: pass

    def set_elo(self, elo):
        if not self.engine: return
        with self.lock:
            try: self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
            except: self.engine.configure({"Skill Level": max(0, min(20, int((elo - 800) / 110)))})

    def get_eval_score(self, board, time_limit=0.1):
        if not self.engine: return 0.0
        with self.lock:
            info = self.engine.analyse(board, chess.engine.Limit(time=time_limit))
            score = info["score"].white()
            if score.is_mate(): return 10.0 if score.mate() > 0 else -10.0
            return score.score() / 100.0

    def analyze_move_accuracy(self, board, played_move):
        if not self.engine: return "Unknown", COLORS["text"], ""
        with self.lock:
            info_before = self.engine.analyse(board, chess.engine.Limit(depth=10))
            score_before = info_before["score"].white().score(mate_score=10000)
            best_move = info_before.get("pv", [None])[0]
            
            board.push(played_move)
            if played_move == best_move: return "Best Move!", COLORS["best"], "★"
            
            info_after = self.engine.analyse(board, chess.engine.Limit(depth=10))
            score_after = info_after["score"].white().score(mate_score=10000)
            
            if score_before is None or score_after is None: return "Good", COLORS["text"], ""
            
            turn_multiplier = 1 if not board.turn else -1 
            loss = (score_before - score_after) * turn_multiplier
            
            if loss < 50: return "Excellent", COLORS["highlight"], "!"
            elif loss < 150: return "Inaccuracy", COLORS["inaccuracy"], "?!"
            elif loss < 300: return "Mistake", "#ff9800", "?"
            else: return "Blunder", COLORS["blunder"], "??"

    def get_best_move(self, board, depth=15):
        if not self.engine: return None
        with self.lock:
            info = self.engine.analyse(board, chess.engine.Limit(depth=depth))
            return info.get("pv", [None])[0]

    def calculate_game_accuracy(self, board_history, player_color, start_fen=chess.STARTING_FEN):
        if not self.engine or len(board_history) < 2: return None
        acc_data = {"early": [], "mid": [], "late": []}
        temp_board = chess.Board(start_fen)
        
        with self.lock:
            for i, move in enumerate(board_history):
                if temp_board.turn != player_color:
                    temp_board.push(move)
                    continue
                
                info_before = self.engine.analyse(temp_board, chess.engine.Limit(depth=10))
                sb = info_before["score"].white().score(mate_score=10000)
                if not temp_board.turn: sb *= -1
                
                temp_board.push(move)
                info_after = self.engine.analyse(temp_board, chess.engine.Limit(depth=10))
                sa = info_after["score"].white().score(mate_score=10000)
                if not temp_board.turn: sa *= -1
                
                if sb is not None and sa is not None:
                    cp_loss = max(0, sb - sa)
                    move_acc = max(0.0, 100.0 - (cp_loss / 10.0)) 
                    if i < 14: acc_data["early"].append(move_acc)
                    elif i < 40: acc_data["mid"].append(move_acc)
                    else: acc_data["late"].append(move_acc)

        def avg(lst): return sum(lst)/len(lst) if lst else 100.0
        res = {
            "Opening": round(avg(acc_data["early"]), 1),
            "Middlegame": round(avg(acc_data["mid"]), 1),
            "Endgame": round(avg(acc_data["late"]), 1)
        }
        all_acc = acc_data["early"] + acc_data["mid"] + acc_data["late"]
        res["Overall"] = round(avg(all_acc), 1)
        res["Est_ELO"] = max(400, int((res["Overall"] * 30) - 500))
        return res

    def detect_tactic(self, board):
        if not self.engine: return None, None
        with self.lock:
            info = self.engine.analyse(board, chess.engine.Limit(depth=12))
            best_move = info.get("pv", [None])[0]
            if not best_move: return None, None

            pov_score = info["score"].white() if board.turn == chess.WHITE else info["score"].black()
            
            # 1. Forced Mate
            if pov_score.is_mate() and pov_score.mate() > 0:
                return "Forced Mate", best_move

            vals = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
            moved_piece = board.piece_at(best_move.from_square)
            cap_piece = board.piece_at(best_move.to_square)
            is_cap = board.is_capture(best_move)
            
            # 2. Favorable Exchange
            if is_cap and cap_piece and moved_piece:
                if vals.get(cap_piece.piece_type, 0) > vals.get(moved_piece.piece_type, 0):
                    return "Favorable Exchange", best_move

            board.push(best_move)
            is_check = board.is_check()
            enemy_color = board.turn 
            attacks = list(board.attacks(best_move.to_square))
            valuable_targets = 0
            for sq in attacks:
                p = board.piece_at(sq)
                if p and p.color == enemy_color and p.piece_type != chess.PAWN:
                    valuable_targets += 1
            board.pop()

            # 3. Fork Check
            if valuable_targets >= 2 and moved_piece and moved_piece.piece_type in [chess.KNIGHT, chess.PAWN, chess.BISHOP, chess.QUEEN, chess.ROOK]:
                return "Fork/Skewer Opportunity", best_move
                
            # 4. Discovered or Direct Check
            if is_check and not is_cap:
                if pov_score.score() is not None and pov_score.score() > 150:
                    return "Checking Attack", best_move
                
            return None, None
class GameUI(tk.Frame):
    def __init__(self, master, mode="practice", cpu_elo=1500, start_fen=chess.STARTING_FEN, cpu_color=chess.BLACK, trainer_desc="", resume_moves=None, puzzle_logic=None, time_limit=0):
        super().__init__(master, bg=COLORS["bg"])
        self.master = master
        
        # Game State Variables
        self.mode = mode
        self.cpu_elo = cpu_elo
        self.cpu_color = cpu_color
        self.start_fen = start_fen
        self.trainer_desc = trainer_desc
        self.puzzle_logic = puzzle_logic
        self.time_limit = time_limit
        
        self.game = chess.Board(self.start_fen)
        self.view_ply = 0
        self.selected_square = None
        self.valid_moves = []
        self.hint_arrow = None
        self.is_evaluating_game = False
        
        # Review Caches
        self.move_annotations = {}
        self.best_moves = {}
        self.move_accuracy_texts = {}
        self.move_accuracy_colors = {}
        
        # Apply Engine settings if playing vs CPU
        if self.mode in ["practice", "trainer"]:
            self.master.engine_mgr.set_elo(self.cpu_elo)
            
        self.build_ui()
        
        # Resume game if passed from StorageManager or History
        if resume_moves:
            for move_uci in resume_moves:
                self.game.push(chess.Move.from_uci(move_uci))
                self.view_ply += 1
            if self.mode == "review":
                self.enter_review_mode()
        
        self.draw_board()
        self.update_turn_indicator()

        # If it's CPU's turn right from the start
        if self.mode in ["practice", "trainer"] and self.game.turn == self.cpu_color and not self.game.is_game_over():
            self.master.after(500, self.make_ai_move)

    def build_ui(self):
        # Top Header Area
        header_frame = tk.Frame(self, bg=COLORS["panel"], height=50)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        
        back_btn = tk.Button(header_frame, text="← Back to Menu", bg="#cc0000", fg="white", font=("Arial", 10, "bold"), command=self.exit_to_menu)
        back_btn.pack(side=tk.LEFT, padx=10, pady=10)
        
        header_text = f"Mode: {self.mode.capitalize()}"
        if self.trainer_desc: header_text += f" | {self.trainer_desc}"
        elif self.mode == "practice": header_text += f" | CPU ELO: {self.cpu_elo}"
        tk.Label(header_frame, text=header_text, font=("Arial", 14, "bold"), bg=COLORS["panel"], fg="white").pack(side=tk.LEFT, padx=20, pady=10)

        # Main Content Area
        content_frame = tk.Frame(self, bg=COLORS["bg"])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Left: Board
        self.board_frame = tk.Frame(content_frame, bg=COLORS["bg"])
        self.board_frame.pack(side=tk.LEFT, padx=10)
        
        self.canvas = tk.Canvas(self.board_frame, width=SQUARE_SIZE*8, height=SQUARE_SIZE*8, bg=COLORS["bg"], highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_square_clicked)

        # Right: Control Panel
        self.right_frame = tk.Frame(content_frame, bg=COLORS["panel"], width=300)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        
        self.status_bar = tk.Label(self.right_frame, text="White to move", font=("Arial", 16, "bold"), bg=COLORS["panel"], fg="white")
        self.status_bar.pack(pady=15)

        # Puzzle Specific UI
        if self.mode == "puzzle":
            self.puzzle_elo_lbl = tk.Label(self.right_frame, text="", font=("Arial", 12), bg=COLORS["panel"], fg="white")
            self.puzzle_elo_lbl.pack(pady=5)
            self.puzzle_feedback_lbl = tk.Label(self.right_frame, text="Find the best move!", font=("Arial", 12, "bold"), bg=COLORS["panel"], fg=COLORS["best"])
            self.puzzle_feedback_lbl.pack(pady=5)
            self.streak_lbl = tk.Label(self.right_frame, text=f"🔥 Streak: {self.master.storage.data['puzzle_streak']}", font=("Arial", 12), bg=COLORS["panel"], fg="#ff9800")
            self.streak_lbl.pack(pady=5)

        # Active Play Controls
        self.control_frame = tk.Frame(self.right_frame, bg=COLORS["panel"])
        if self.mode != "review":
            self.control_frame.pack(pady=10, fill=tk.X, padx=20)
            tk.Button(self.control_frame, text="🏳️ Resign", bg=COLORS["btn_bg"], fg="white", font=("Arial", 12), command=lambda: self.end_game("Resignation")).pack(fill=tk.X, pady=5)
            tk.Button(self.control_frame, text="📋 Copy FEN", bg="#4CAF50", fg="white", font=("Arial", 12), command=self.copy_fen).pack(fill=tk.X, pady=5)
            tk.Button(self.control_frame, text="📜 History", bg="#2196F3", fg="white", font=("Arial", 12), command=self.show_history).pack(fill=tk.X, pady=5)

        # Review Mode Controls (Hidden initially unless mode is review)
        self.review_frame = tk.Frame(self.right_frame, bg=COLORS["panel"])
        
        nav_frame = tk.Frame(self.review_frame, bg=COLORS["panel"])
        nav_frame.pack(pady=10)
        tk.Button(nav_frame, text="< Prev", width=8, bg=COLORS["btn_bg"], fg="white", command=lambda: self.jump_to_ply(max(0, self.view_ply - 1))).pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="Next >", width=8, bg=COLORS["btn_bg"], fg="white", command=lambda: self.jump_to_ply(min(len(self.game.move_stack), self.view_ply + 1))).pack(side=tk.LEFT, padx=5)

        self.accuracy_lbl = tk.Label(self.review_frame, text="", font=("Arial", 14, "bold"), bg=COLORS["panel"], fg="white", wraplength=250)
        self.accuracy_lbl.pack(pady=10)
        
        self.btn_review_best = tk.Button(self.review_frame, text="👀 See Best Move", font=("Arial", 12, "bold"), bg=COLORS["arrow_hint"], fg="black", command=self.show_review_best_move)
        # Not packed initially

        if self.mode == "review":
            self.enter_review_mode()

    def exit_to_menu(self):
        # Save session if game is not over and not in puzzle/review mode
        if not self.game.is_game_over() and self.mode in ["practice", "trainer", "2player"]:
            moves = [m.uci() for m in self.game.move_stack]
            self.master.storage.save_session(self.mode, self.cpu_elo, self.start_fen, self.cpu_color, self.trainer_desc, moves)
        
        self.master.show_start_screen()

    def draw_board(self):
        self.canvas.delete("all")
        view_board = chess.Board(self.start_fen)
        for m in self.game.move_stack[:self.view_ply]:
            view_board.push(m)
            
        last_move = self.game.move_stack[self.view_ply - 1] if self.view_ply > 0 else None

        for rank in range(8):
            for file in range(8):
                square = chess.square(file, 7 - rank)
                x1, y1 = file * SQUARE_SIZE, rank * SQUARE_SIZE
                x2, y2 = x1 + SQUARE_SIZE, y1 + SQUARE_SIZE
                
                is_light = (rank + file) % 2 == 0
                color = COLORS["light"] if is_light else COLORS["dark"]
                
                if last_move and square in (last_move.from_square, last_move.to_square):
                    color = COLORS["last_light"] if is_light else COLORS["last_dark"]
                if square == self.selected_square: 
                    color = COLORS["select"]
                
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
                
                piece = view_board.piece_at(square)
                if piece:
                    char = PIECE_SHAPES[piece.piece_type]
                    p_color = "white" if piece.color == chess.WHITE else "black"
                    self.canvas.create_text(x1 + SQUARE_SIZE//2, y1 + SQUARE_SIZE//2, text=char, font=("Arial", int(SQUARE_SIZE*0.6)), fill=p_color)
                
                if square in [m.to_square for m in self.valid_moves]:
                    self.canvas.create_oval(x1 + SQUARE_SIZE*.35, y1 + SQUARE_SIZE*.35, x2 - SQUARE_SIZE*.35, y2 - SQUARE_SIZE*.35, fill=COLORS["highlight"], outline="")

        if self.hint_arrow:
            start_sq, end_sq = self.hint_arrow.from_square, self.hint_arrow.to_square
            x1 = (chess.square_file(start_sq) * SQUARE_SIZE) + SQUARE_SIZE // 2
            y1 = ((7 - chess.square_rank(start_sq)) * SQUARE_SIZE) + SQUARE_SIZE // 2
            x2 = (chess.square_file(end_sq) * SQUARE_SIZE) + SQUARE_SIZE // 2
            y2 = ((7 - chess.square_rank(end_sq)) * SQUARE_SIZE) + SQUARE_SIZE // 2
            self.canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, fill=COLORS["arrow_hint"], width=5)

    def on_square_clicked(self, event):
        if self.mode == "review" or self.is_evaluating_game: return
        if self.mode in ["practice", "trainer"] and self.game.turn == self.cpu_color: return

        file, rank = event.x // SQUARE_SIZE, 7 - (event.y // SQUARE_SIZE)
        square = chess.square(file, rank)
        
        move = chess.Move(self.selected_square, square) if self.selected_square is not None else None
        
        # Auto-promote to Queen
        if move and self.game.piece_at(self.selected_square) and self.game.piece_at(self.selected_square).piece_type == chess.PAWN:
            if chess.square_rank(square) == 0 or chess.square_rank(square) == 7:
                move = chess.Move(self.selected_square, square, promotion=chess.QUEEN)

        if move in self.game.legal_moves:
            self.process_player_move(move)
        else:
            if self.game.color_at(square) == self.game.turn:
                self.selected_square = square
                self.valid_moves = [m for m in self.game.legal_moves if m.from_square == square]
            else:
                self.selected_square = None
                self.valid_moves = []
            self.draw_board()

    def process_player_move(self, move):
        if self.mode == "puzzle":
            is_correct = self.puzzle_logic.verify_move(move.uci())
            if is_correct:
                self.game.push(move)
                self.view_ply += 1
                self.selected_square = None
                self.valid_moves = []
                self.draw_board()
            return

        self.game.push(move)
        self.view_ply += 1
        self.selected_square = None
        self.valid_moves = []
        self.draw_board()
        self.update_turn_indicator()
        
        if not self.check_game_over() and self.mode in ["practice", "trainer"]:
            self.master.after(200, self.make_ai_move)

    def make_ai_move(self):
        self.status_bar.config(text="CPU is thinking...", fg="#ff9800")
        self.master.update()
        
        best_move = self.master.engine_mgr.get_best_move(self.game)
        if best_move:
            self.game.push(best_move)
            self.view_ply += 1
            self.draw_board()
            self.update_turn_indicator()
            self.check_game_over()

    def update_turn_indicator(self):
        if self.game.is_game_over(): return
        turn_str = "White to move" if self.game.turn == chess.WHITE else "Black to move"
        self.status_bar.config(text=turn_str, fg="white")

    def check_game_over(self):
        if self.game.is_game_over():
            self.is_evaluating_game = True
            result = self.game.result()
            res_text = "Draw" if result == "1/2-1/2" else ("White Wins" if result == "1-0" else "Black Wins")
            self.status_bar.config(text=f"Game Over: {res_text}", fg=COLORS["best"])
            
            # Save Stats
            if self.mode == "practice":
                self.master.storage.record_game_result(result, self.cpu_elo)
            
            self.master.storage.clear_session()
            self.save_to_history(res_text)
            
            # Auto-show Review button
            self.control_frame.pack_forget()
            tk.Button(self.right_frame, text="🔍 Review Game", bg=COLORS["accent"], fg="white", font=("Arial", 14, "bold"), command=self.enter_review_mode).pack(pady=20)
            return True
        return False

    def end_game(self, reason):
        self.is_evaluating_game = True
        res_text = f"Game Ended ({reason})"
        self.status_bar.config(text=res_text, fg=COLORS["blunder"])
        self.master.storage.clear_session()
        self.save_to_history(res_text)
        self.control_frame.pack_forget()
        tk.Button(self.right_frame, text="🔍 Review Game", bg=COLORS["accent"], fg="white", font=("Arial", 14, "bold"), command=self.enter_review_mode).pack(pady=20)

    # --- HISTORY & CLIPBOARD ---
    def copy_fen(self):
        board = chess.Board(self.start_fen)
        for m in self.game.move_stack[:self.view_ply]: board.push(m)
        current_fen = board.fen()
        self.master.clipboard_clear()
        self.master.clipboard_append(current_fen)
        self.master.update()
        self.status_bar.config(text="FEN Copied!", fg=COLORS["best"])

    def save_to_history(self, result_text):
        if len(self.game.move_stack) == 0: return # Don't save empty games
        history_file = "game_history.json"
        try:
            with open(history_file, "r") as f: history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            history = []
        
        game_data = {
            "date": "Today", # In a full app import datetime and use datetime.now().strftime("%Y-%m-%d %H:%M")
            "mode": self.mode,
            "result": result_text,
            "moves": [m.uci() for m in self.game.move_stack],
            "fen_start": self.start_fen
        }
        
        history.insert(0, game_data)
        history = history[:20]
        with open(history_file, "w") as f: json.dump(history, f, indent=4)

    def show_history(self):
        history_win = tk.Toplevel(self.master)
        history_win.title("Recent Games (Last 20)")
        history_win.geometry("500x400")
        history_win.configure(bg=COLORS["bg"])
        
        try:
            with open("game_history.json", "r") as f: history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            history = []
            
        if not history:
            tk.Label(history_win, text="No games played yet.", font=("Arial", 12), bg=COLORS["bg"], fg="white").pack(pady=40)
            return
            
        tk.Label(history_win, text="Double-click a game to Review it:", font=("Arial", 12, "italic"), bg=COLORS["bg"], fg="#aaa").pack(pady=10)
            
        listbox = tk.Listbox(history_win, font=("Arial", 11), bg=COLORS["panel"], fg="white", selectbackground=COLORS["accent"])
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        for i, game in enumerate(history):
            entry_text = f"{i+1}. {game.get('mode', 'Game').capitalize()} | {game.get('result')} ({len(game.get('moves', []))} moves)"
            listbox.insert(tk.END, entry_text)

        def load_selected_game(event):
            selection = listbox.curselection()
            if selection:
                index = selection[0]
                game_data = history[index]
                history_win.destroy()
                # Switch frame to review the selected game
                self.master.switch_frame(GameUI, mode="review", start_fen=game_data.get("fen_start"), resume_moves=game_data.get("moves", []))
                
        listbox.bind("<Double-1>", load_selected_game)

    # --- REVIEW MODE ---
    def enter_review_mode(self):
        self.mode = "review"
        self.control_frame.pack_forget()
        self.review_frame.pack(pady=10, fill=tk.X, padx=20)
        self.jump_to_ply(len(self.game.move_stack))

    def jump_to_ply(self, ply):
        self.view_ply = ply
        self.selected_square = None
        self.valid_moves = []
        self.hint_arrow = None
        self.draw_board()
        self.btn_review_best.pack_forget()
        
        if self.view_ply > 0:
            move_index = self.view_ply - 1
            if move_index not in self.move_annotations:
                self.status_bar.config(text="Engine Analyzing...", fg=COLORS["inaccuracy"])
                self.master.update()
                
                view_board = chess.Board(self.start_fen)
                for m in self.game.move_stack[:move_index]: view_board.push(m)
                played_move = self.game.move_stack[move_index]
                
                acc_text, acc_color, badge = self.master.engine_mgr.analyze_move_accuracy(view_board, played_move)
                best_move = self.master.engine_mgr.get_best_move(view_board, depth=10)
                
                self.move_annotations[move_index] = badge
                self.move_accuracy_texts[move_index] = acc_text
                self.move_accuracy_colors[move_index] = acc_color
                self.best_moves[move_index] = best_move
                
            self.accuracy_lbl.config(text=f"Move {move_index+1}: {self.move_accuracy_texts[move_index]}", fg=self.move_accuracy_colors[move_index])
            self.status_bar.config(text="Review Mode", fg="white")
            
            if self.best_moves.get(move_index) and self.move_annotations[move_index] not in ["★", ""]:
                self.btn_review_best.pack(pady=10)
        else:
            self.accuracy_lbl.config(text="")
            self.status_bar.config(text="Review Mode. Click 'Next >'.", fg="white")

    def show_review_best_move(self):
        if self.view_ply == 0: return
        move_index = self.view_ply - 1
        best_move = self.best_moves.get(move_index)
        
        if best_move:
            self.jump_to_ply(self.view_ply - 1)
            self.hint_arrow = best_move
            self.draw_board()
            self.status_bar.config(text="Showing engine best move.", fg=COLORS["arrow_hint"])
# --- UI CONTROLLERS ---
class AppController(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chess Training Platform Pro")
        self.geometry("1150x800") 
        self.resizable(False, False)
        self.configure(bg=COLORS["bg"])
        self.storage = StorageManager()
        self.engine_mgr = EngineManager()
        self.engine_mgr.start()
        self.puzzle_mgr = PuzzleManager(self)
        self.current_frame = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_start_screen()

    def switch_frame(self, frame_class, **kwargs):
        if self.current_frame: self.current_frame.destroy()
        self.current_frame = frame_class(self, **kwargs)
        self.current_frame.pack(fill=tk.BOTH, expand=True)

    def show_start_screen(self): self.switch_frame(StartScreen)
    def on_close(self):
        self.engine_mgr.quit()
        self.storage.save()
        self.destroy()

class StartScreen(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=COLORS["bg"])
        header = tk.Frame(self, bg=COLORS["panel"], height=100)
        header.pack(fill=tk.X, side=tk.TOP)
        tk.Label(header, text="Chess Training Platform", font=("Arial", 28, "bold"), bg=COLORS["panel"], fg=COLORS["text"]).pack(pady=20)
        
        btn_frame = tk.Frame(self, bg=COLORS["bg"])
        btn_frame.pack(pady=20)

        if master.storage.data.get("saved_session"):
            tk.Button(btn_frame, text="▶ Resume Last Game", width=30, font=("Arial", 14), bg=COLORS["best"], fg="white", command=self.resume_session).grid(row=0, column=0, pady=(0, 20))

        tk.Button(btn_frame, text="♟️ Play Modes", width=30, font=("Arial", 14), bg=COLORS["btn_bg"], fg="white", command=lambda: master.switch_frame(PlayMenu)).grid(row=1, column=0, pady=10)
        tk.Button(btn_frame, text="🧩 Tactics Puzzles", width=30, font=("Arial", 14), bg=COLORS["btn_bg"], fg="white", command=lambda: master.puzzle_mgr.load_next()).grid(row=2, column=0, pady=10)
        tk.Button(btn_frame, text="🎓 Dynamic Trainers", width=30, font=("Arial", 14), bg=COLORS["btn_bg"], fg="white", command=lambda: master.switch_frame(TrainerMenu)).grid(row=3, column=0, pady=10)
        tk.Button(btn_frame, text="📊 Profile & Stats", width=30, font=("Arial", 14), bg=COLORS["btn_bg"], fg="white", command=lambda: master.switch_frame(StatsScreen)).grid(row=4, column=0, pady=10)
        tk.Button(btn_frame, text="⚙️ Settings", width=30, font=("Arial", 14), bg=COLORS["accent"], fg="white", command=lambda: master.switch_frame(SettingsScreen)).grid(row=5, column=0, pady=10)

    def resume_session(self):
        s = self.master.storage.data["saved_session"]
        self.master.switch_frame(GameUI, mode=s["mode"], cpu_elo=s["cpu_elo"], start_fen=s["start_fen"], cpu_color=s["cpu_color"], trainer_desc=s["trainer_desc"], resume_moves=s["moves"])

class SettingsScreen(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=COLORS["bg"])
        tk.Label(self, text="Global Settings", font=("Arial", 24, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(pady=30)
        
        f = tk.Frame(self, bg=COLORS["panel"], padx=40, pady=20, relief=tk.RAISED, bd=2)
        f.pack()

        tk.Label(f, text="🔥 Heatmap Colors", font=("Arial", 16, "bold"), bg=COLORS["panel"], fg="white").pack(pady=(0, 15))
        
        self.color_btns = {}
        grid_f = tk.Frame(f, bg=COLORS["panel"])
        grid_f.pack()

        for i in range(6):
            val_str = str(i)
            lbl_text = f"{i} Attackers" if i < 5 else "5+ Attackers"
            tk.Label(grid_f, text=lbl_text, bg=COLORS["panel"], fg="white", font=("Arial", 12)).grid(row=i, column=0, sticky="e", pady=5, padx=10)
            
            btn = tk.Button(grid_f, bg=master.storage.data["heatmap"][val_str], width=10, relief=tk.FLAT, command=lambda v=val_str: self.change_color(v))
            btn.grid(row=i, column=1, pady=5)
            self.color_btns[val_str] = btn

        tk.Button(f, text="✨ Generate Smooth Gradient (0 -> 5+)", font=("Arial", 10, "bold"), bg=COLORS["accent"], fg="white", relief=tk.FLAT, command=self.generate_gradient).pack(pady=(15, 0))

        tk.Button(self, text="← Back", width=20, bg="#cc0000", fg="white", font=("Arial", 12), command=master.show_start_screen).pack(pady=40)

    def change_color(self, val_str):
        new_color = colorchooser.askcolor(title=f"Choose color for {val_str}")[1]
        if new_color:
            self.master.storage.data["heatmap"][val_str] = new_color
            self.color_btns[val_str].config(bg=new_color)
            self.master.storage.save()

    def generate_gradient(self):
        c0 = self.master.storage.data["heatmap"]["0"]
        c5 = self.master.storage.data["heatmap"]["5"]
        
        def hex_to_rgb(hx):
            hx = hx.lstrip('#')
            return tuple(int(hx[i:i+2], 16) for i in (0, 2, 4))
            
        def rgb_to_hex(rgb):
            return '#%02x%02x%02x' % tuple(int(x) for x in rgb)
            
        try:
            rgb0 = hex_to_rgb(c0)
            rgb5 = hex_to_rgb(c5)
        except ValueError:
            return

        for i in range(1, 5):
            ratio = i / 5.0
            new_rgb = (
                rgb0[0] + (rgb5[0] - rgb0[0]) * ratio,
                rgb0[1] + (rgb5[1] - rgb0[1]) * ratio,
                rgb0[2] + (rgb5[2] - rgb0[2]) * ratio
            )
            val_str = str(i)
            new_hex = rgb_to_hex(new_rgb)
            self.master.storage.data["heatmap"][val_str] = new_hex
            self.color_btns[val_str].config(bg=new_hex)
            
        self.master.storage.save()

class StatsScreen(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=COLORS["bg"])
        tk.Label(self, text="Player Profile & Stats", font=("Arial", 24, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(pady=30)
        
        stats = master.storage.data["stats"]
        f = tk.Frame(self, bg=COLORS["panel"], padx=40, pady=40, relief=tk.RAISED, bd=2)
        f.pack()

        tk.Label(f, text=f"🧩 Puzzle ELO: {master.storage.data['elo']}", font=("Arial", 16), bg=COLORS["panel"], fg="white").pack(pady=5)
        tk.Label(f, text=f"🔥 Max Puzzle Streak: {master.storage.data['max_streak']}", font=("Arial", 16), bg=COLORS["panel"], fg="white").pack(pady=5)
        tk.Label(f, text="---", bg=COLORS["panel"], fg="#666").pack(pady=10)
        tk.Label(f, text=f"🏆 Highest CPU Beaten: {stats['highest_elo_beaten']} ELO", font=("Arial", 16, "bold"), bg=COLORS["panel"], fg=COLORS["best"]).pack(pady=5)
        tk.Label(f, text=f"⚔️ Lifetime Wins: {stats['wins']}", font=("Arial", 16), bg=COLORS["panel"], fg="white").pack(pady=5)
        tk.Label(f, text=f"💀 Lifetime Losses: {stats['losses']}", font=("Arial", 16), bg=COLORS["panel"], fg="white").pack(pady=5)
        tk.Label(f, text=f"🤝 Lifetime Draws: {stats['draws']}", font=("Arial", 16), bg=COLORS["panel"], fg="white").pack(pady=5)

        tk.Button(self, text="← Back", width=20, bg="#cc0000", fg="white", font=("Arial", 12), command=master.show_start_screen).pack(pady=40)

class PlayMenu(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=COLORS["bg"])
        tk.Label(self, text="Practice vs CPU", font=("Arial", 24, "bold"), bg=COLORS["bg"], fg="white").pack(pady=(40, 20))
        
        self.elo_slider = tk.Scale(self, from_=800, to=3000, resolution=100, orient=tk.HORIZONTAL, bg=COLORS["bg"], fg="white", length=300)
        self.elo_slider.set(1500)
        self.elo_slider.pack(pady=10)
        tk.Button(self, text="Start Game", width=30, bg=COLORS["best"], fg="white", font=("Arial", 14), command=lambda: master.switch_frame(GameUI, mode="practice", cpu_elo=self.elo_slider.get())).pack(pady=10)

        tk.Frame(self, bg="#444", height=1, width=400).pack(pady=20)
        
        time_frame = tk.Frame(self, bg=COLORS["bg"])
        time_frame.pack(pady=10)
        tk.Label(time_frame, text="2-Player Timer:", font=("Arial", 14), bg=COLORS["bg"], fg="white").pack(side=tk.LEFT, padx=10)
        self.time_var = tk.StringVar(value="None")
        ttk.Combobox(time_frame, textvariable=self.time_var, values=["None", "3 mins", "5 mins", "10 mins"], state="readonly", width=10).pack(side=tk.LEFT)
        tk.Button(self, text="2-Player Local", width=30, bg=COLORS["btn_bg"], fg="white", font=("Arial", 14), command=self.start_2player).pack(pady=10)

        tk.Button(self, text="← Back", width=20, bg="#cc0000", fg="white", font=("Arial", 12), command=master.show_start_screen).pack(pady=40)

    def start_2player(self):
        time_map = {"None": 0, "3 mins": 180, "5 mins": 300, "10 mins": 600}
        self.master.switch_frame(GameUI, mode="2player", time_limit=time_map[self.time_var.get()])

class TrainerMenu(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=COLORS["bg"])
        tk.Label(self, text="Dynamic Trainers", font=("Arial", 24, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(pady=10)
        
        # --- TAB STYLING ---
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background=COLORS["bg"], borderwidth=0)
        style.configure('TNotebook.Tab', background=COLORS["btn_bg"], foreground="white", padding=[15, 5], font=("Arial", 12, "bold"))
        style.map('TNotebook.Tab', background=[('selected', COLORS["accent"])])

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # TAB 1: ENDGAMES
        tab_endgame = tk.Frame(notebook, bg=COLORS["panel"])
        notebook.add(tab_endgame, text="Endgames")
        
        endgames = [
            ("♕ King & Queen Mate", "KQ"),
            ("♖ King & Rook Mate", "KR"),
            ("♗ King & Two Bishops Mate", "KBB"),
            ("♘ King & Two Knights Mate", "KNN"),
            ("♗♘ Bishop & Knight Mate", "KBN")
        ]
        tk.Label(tab_endgame, text="Master essential checkmating patterns.", bg=COLORS["panel"], fg="#ccc", font=("Arial", 10, "italic")).pack(pady=10)
        for text, code in endgames:
            tk.Button(tab_endgame, text=text, width=35, font=("Arial", 14), bg=COLORS["btn_bg"], fg="white", 
                      command=lambda c=code: self.start_proc_endgame(c)).pack(pady=8)

        # TAB 2: WHITE OPENINGS
        tab_white = tk.Frame(notebook, bg=COLORS["panel"])
        notebook.add(tab_white, text="White Openings")
        
        white_openings = [
            ("Italian Game (1.e4 e5 2.Nf3 Nc6 3.Bc4)", "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"),
            ("Ruy Lopez (1.e4 e5 2.Nf3 Nc6 3.Bb5)", "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"),
            ("Queen's Gambit (1.d4 d5 2.c4)", "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR b KQkq - 0 2"),
            ("English Opening (1.c4)", "rnbqkbnr/pppppppp/8/8/2P5/8/PP1PPPPP/RNBQKBNR b KQkq - 0 1"),
            ("London System (1.d4 d5 2.Bf4)", "rnbqkbnr/ppp1pppp/8/3p4/3P1B2/8/PPP1PPPP/RN1QKBNR b KQkq - 1 2")
        ]
        tk.Label(tab_white, text="Practice playing as White from the mainline. CPU plays Black.", bg=COLORS["panel"], fg="#ccc", font=("Arial", 10, "italic")).pack(pady=10)
        for text, fen in white_openings:
            tk.Button(tab_white, text=text, width=45, font=("Arial", 12), bg=COLORS["btn_bg"], fg="white", 
                      command=lambda f=fen, t=text: self.master.switch_frame(GameUI, mode="practice", start_fen=f, cpu_color=chess.BLACK, cpu_elo=2000, trainer_desc=t)).pack(pady=8)

        # TAB 3: BLACK OPENINGS
        tab_black = tk.Frame(notebook, bg=COLORS["panel"])
        notebook.add(tab_black, text="Black Openings")
        
        black_openings = [
            ("Sicilian Defense (1.e4 c5)", "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
            ("French Defense (1.e4 e6)", "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
            ("Caro-Kann Defense (1.e4 c6)", "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
            ("King's Indian Defense (1.d4 Nf6 2.c4 g6)", "rnbqkb1r/pppppp1p/5np1/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq - 0 3"),
            ("Nimzo-Indian Defense (1.d4 Nf6 2.c4 e6 3.Nc3 Bb4)", "rnbqk2r/pppp1ppp/4pn2/8/1bPP4/2N5/PP2PPPP/R1BQKBNR w KQkq - 2 4")
        ]
        tk.Label(tab_black, text="Practice playing as Black from the mainline. CPU plays White.", bg=COLORS["panel"], fg="#ccc", font=("Arial", 10, "italic")).pack(pady=10)
        for text, fen in black_openings:
            tk.Button(tab_black, text=text, width=45, font=("Arial", 12), bg=COLORS["btn_bg"], fg="white", 
                      command=lambda f=fen, t=text: self.master.switch_frame(GameUI, mode="practice", start_fen=f, cpu_color=chess.WHITE, cpu_elo=2000, trainer_desc=t)).pack(pady=8)
        
        tk.Button(self, text="← Back", width=20, bg="#cc0000", fg="white", font=("Arial", 12), command=master.show_start_screen).pack(pady=15)

    def start_proc_endgame(self, type):
        board = chess.Board(None)
        board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
        safe_squares = [sq for sq in chess.SQUARES if sq not in [chess.E1, chess.E8, chess.D8, chess.F8, chess.D7, chess.E7, chess.F7]]
        
        def get_sq():
            sq = random.choice(safe_squares)
            safe_squares.remove(sq)
            return sq

        if type == "KQ": board.set_piece_at(get_sq(), chess.Piece(chess.QUEEN, chess.WHITE))
        elif type == "KR": board.set_piece_at(get_sq(), chess.Piece(chess.ROOK, chess.WHITE))
        elif type == "KBB":
            light_sqs = [sq for sq in safe_squares if (chess.square_rank(sq) + chess.square_file(sq)) % 2 != 0]
            dark_sqs = [sq for sq in safe_squares if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]
            board.set_piece_at(random.choice(light_sqs), chess.Piece(chess.BISHOP, chess.WHITE))
            board.set_piece_at(random.choice(dark_sqs), chess.Piece(chess.BISHOP, chess.WHITE))
        elif type == "KNN":
            board.set_piece_at(get_sq(), chess.Piece(chess.KNIGHT, chess.WHITE))
            board.set_piece_at(get_sq(), chess.Piece(chess.KNIGHT, chess.WHITE))
        elif type == "KBN":
            board.set_piece_at(get_sq(), chess.Piece(chess.BISHOP, chess.WHITE))
            board.set_piece_at(get_sq(), chess.Piece(chess.KNIGHT, chess.WHITE))
            
        board.turn = chess.WHITE
        self.master.switch_frame(GameUI, mode="endgame", start_fen=board.fen(), cpu_color=chess.BLACK, trainer_desc=f"Procedural {type} Mate", cpu_elo=3000)

class GameUI(tk.Frame):
    def __init__(self, master, mode="practice", cpu_elo=1500, start_fen=chess.STARTING_FEN, cpu_color=chess.BLACK, puzzle_logic=None, trainer_desc="", resume_moves=None, time_limit=0):
        super().__init__(master, bg=COLORS["bg"])
        self.mode, self.cpu_elo, self.start_fen, self.cpu_color = mode, cpu_elo, start_fen, cpu_color
        self.puzzle_logic, self.trainer_desc = puzzle_logic, trainer_desc
        
        if mode == "puzzle": self.board_orientation = not cpu_color 
        else: self.board_orientation = not cpu_color if cpu_color is not None else chess.WHITE
        
        self.game = chess.Board(start_fen)
        self.view_ply = 0
        self.selected_square = None
        self.valid_moves = []
        self.undone_moves = [] 
        self.move_annotations = {} 
        self.drawn_arrows = []
        self.arrow_start_square = None
        self.hint_arrow = None
        
        # Drag and Drop State
        self.drag_start_square = None
        self.is_dragging = False
        
        self.overlay_frame = None
        self.heatmap_mode = "Off" 
        self.override_cpu = False
        self.show_eval_bar = False
        self.is_evaluating_game = False
        
        self.helper_active = False
        self.tactic_move = None
        
        self.time_limit = time_limit
        self.times = {chess.WHITE: time_limit, chess.BLACK: time_limit}
        self.timer_id = None

        if self.mode in ["practice", "endgame"]: self.master.engine_mgr.set_elo(self.cpu_elo)

        self.build_ui()
        
        if resume_moves:
            for uci in resume_moves: self.game.push(chess.Move.from_uci(uci))
            self.view_ply = len(self.game.move_stack)
            self.update_move_list_ui()

        self.update_turn_indicator()
        self.draw_board()
        self.trigger_eval_update()
        self.trigger_helper_check()

        if self.mode in ["practice", "endgame"] and self.game.turn == self.cpu_color and not resume_moves:
            self.master.after(500, self.do_cpu_turn)
            
        if self.time_limit > 0: self.run_timer()
        self.update_status_bar()

    def build_ui(self):
        top_ctrl = tk.Frame(self, bg=COLORS["bg"])
        top_ctrl.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Button(top_ctrl, text="← Menu", command=self.go_back_to_menu, bg="#cc0000", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0,15))
        tk.Button(top_ctrl, text="🔄 Flip", command=self.flip_board, bg=COLORS["btn_bg"], fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        self.btn_heatmap = tk.Button(top_ctrl, text="🔥 Heatmap (Off)", command=self.cycle_heatmap, bg=COLORS["btn_bg"], fg="white", font=("Arial", 10, "bold"))
        self.btn_heatmap.pack(side=tk.LEFT, padx=5)
        
        tk.Button(top_ctrl, text="📊 Eval Bar", command=self.toggle_eval, bg=COLORS["btn_bg"], fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        self.btn_helper = tk.Button(top_ctrl, text="🤖 Helper (Off)", command=self.toggle_helper, bg=COLORS["btn_bg"], fg="white", font=("Arial", 10, "bold"))
        self.btn_helper.pack(side=tk.LEFT, padx=5)
        
        if self.mode in ["practice", "endgame"]:
            self.btn_override = tk.Button(top_ctrl, text="Force CPU Move (Off)", command=self.toggle_override, bg=COLORS["btn_bg"], fg="white", font=("Arial", 10, "bold"))
            self.btn_override.pack(side=tk.LEFT, padx=5)

        turn_frame = tk.Frame(top_ctrl, bg=COLORS["bg"])
        turn_frame.pack(side=tk.RIGHT, padx=10)
        self.turn_lbl = tk.Label(turn_frame, text="Turn Info", font=("Arial", 14, "bold"), bg=COLORS["bg"], fg="white")
        self.turn_lbl.pack(side=tk.RIGHT)
        self.turn_canvas = tk.Canvas(turn_frame, width=20, height=20, bg=COLORS["bg"], highlightthickness=0)
        self.turn_canvas.pack(side=tk.RIGHT, padx=(0, 6))

        self.main_area = tk.Frame(self, bg=COLORS["bg"])
        self.main_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.left_frame = tk.Frame(self.main_area, bg=COLORS["bg"])
        self.left_frame.pack(side=tk.LEFT)

        self.top_info = tk.Frame(self.left_frame, bg=COLORS["bg"])
        self.top_info.pack(fill=tk.X, pady=2)
        self.top_mat_lbl = tk.Label(self.top_info, text="", font=("Arial", 11, "bold"), bg=COLORS["bg"], fg="#aaa")
        self.top_mat_lbl.pack(side=tk.LEFT, padx=24) 
        self.top_time_lbl = tk.Label(self.top_info, text="", font=("Courier", 14, "bold"), bg=COLORS["bg"], fg="white")
        self.top_time_lbl.pack(side=tk.RIGHT)

        self.board_container = tk.Frame(self.left_frame, bg=COLORS["bg"])
        self.board_container.pack()
        self.eval_canvas = tk.Canvas(self.board_container, width=20, height=8*SQUARE_SIZE, bg="#333", highlightthickness=1, highlightbackground="#000")
        
        self.canvas = tk.Canvas(self.board_container, width=8*SQUARE_SIZE, height=8*SQUARE_SIZE, highlightthickness=0, bg="#111")
        self.canvas.pack(side=tk.LEFT)
        
        # New Input Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)  
        self.canvas.bind("<ButtonRelease-3>", self.on_right_release) 
        self.canvas.bind("<Double-Button-3>", self.on_right_double_click)

        self.bot_info = tk.Frame(self.left_frame, bg=COLORS["bg"])
        self.bot_info.pack(fill=tk.X, pady=2)
        self.bot_mat_lbl = tk.Label(self.bot_info, text="", font=("Arial", 11, "bold"), bg=COLORS["bg"], fg="#aaa")
        self.bot_mat_lbl.pack(side=tk.LEFT, padx=24)
        self.bot_time_lbl = tk.Label(self.bot_info, text="", font=("Courier", 14, "bold"), bg=COLORS["bg"], fg="white")
        self.bot_time_lbl.pack(side=tk.RIGHT)

        self.status_bar = tk.Label(self.left_frame, text="", bg=COLORS["bg"], fg="#888", font=("Arial", 10), anchor="w")
        self.status_bar.pack(fill=tk.X, pady=(5,0))

        self.right_frame = tk.Frame(self.main_area, width=350, bg=COLORS["panel"], highlightbackground="#444", highlightthickness=1)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        self.right_frame.pack_propagate(False)
        
        top_info = tk.Frame(self.right_frame, bg=COLORS["panel"])
        top_info.pack(fill=tk.X, pady=5, padx=10)
        tk.Label(top_info, text=f"MODE: {self.mode.upper()}", font=("Arial", 12, "bold"), bg=COLORS["panel"], fg=COLORS["accent"]).pack(anchor="w")

        if self.trainer_desc:
            tk.Label(self.right_frame, text=self.trainer_desc, font=("Arial", 10, "italic"), bg=COLORS["panel"], fg="#ccc", wraplength=300).pack(pady=5)

        self.status_lbl = tk.Label(self.right_frame, text="Your Turn", font=("Arial", 14), bg=COLORS["panel"], fg="#4CAF50")
        self.status_lbl.pack(pady=5)
        
        if self.mode == "puzzle":
            self.streak_lbl = tk.Label(self.right_frame, text=f"🔥 Streak: {self.master.storage.data['puzzle_streak']}", font=("Arial", 16, "bold"), bg=COLORS["panel"], fg="#ff9800")
            self.streak_lbl.pack(pady=5)
            self.puzzle_elo_lbl = tk.Label(self.right_frame, text="Puzzle Rating: ---", font=("Arial", 12, "bold"), bg=COLORS["panel"], fg="#00e5ff")
            self.puzzle_elo_lbl.pack(pady=5)
            self.puzzle_feedback_lbl = tk.Label(self.right_frame, text="Find the best move!", font=("Arial", 12, "bold"), bg=COLORS["panel"], fg=COLORS["text"])
            self.puzzle_feedback_lbl.pack(pady=5)

        self.accuracy_lbl = tk.Label(self.right_frame, text="", font=("Arial", 12, "bold"), bg=COLORS["panel"], fg=COLORS["text"])
        self.accuracy_lbl.pack(pady=5)

        ur_frame = tk.Frame(self.right_frame, bg=COLORS["panel"])
        ur_frame.pack(fill=tk.X, padx=10, pady=5)
        if self.mode != "puzzle":
            tk.Button(ur_frame, text="Undo 1", width=8, command=lambda: self.undo_move(1), bg=COLORS["btn_bg"], fg="white").grid(row=0, column=0, padx=2)
            tk.Button(ur_frame, text="Undo Turn", width=8, command=lambda: self.undo_move(2), bg=COLORS["btn_bg"], fg="white").grid(row=0, column=1, padx=2)
            tk.Button(ur_frame, text="Redo 1", width=8, command=lambda: self.redo_move(1), bg=COLORS["btn_bg"], fg="white").grid(row=0, column=2, padx=2)
        tk.Button(ur_frame, text="💡 Hint", width=6, command=self.show_hint, bg="#ff9800", fg="white", font=("Arial", 9, "bold")).grid(row=0, column=4, padx=2)

        tk.Label(self.right_frame, text="Move History:", bg=COLORS["panel"], fg="#aaa", font=("Arial", 9)).pack(anchor="w", padx=10, pady=(5,0))
        self.move_list_box = tk.Listbox(self.right_frame, height=8, bg="#1e1e1e", fg="white", font=("Courier", 11), relief=tk.FLAT, selectbackground=COLORS["accent"], highlightthickness=1, highlightbackground="#444")
        self.move_list_box.pack(fill=tk.BOTH, padx=10, pady=2)
        self.move_list_box.bind("<<ListboxSelect>>", self.on_history_click)

        self.helper_container = tk.Frame(self.right_frame, bg=COLORS["panel"])
        self.btn_special_move = tk.Button(self.helper_container, text="See Special Move", font=("Arial", 10, "bold"), bg=COLORS["tactic"], fg="white", command=self.reveal_tactic)
        self.btn_special_move.pack(pady=5, fill=tk.X)

        self.legend_frame = tk.Frame(self.right_frame, bg=COLORS["panel"])
        self.legend_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        self.build_heatmap_legend()

        nav_frame = tk.Frame(self.right_frame, bg=COLORS["panel"])
        nav_frame.pack(pady=5)
        tk.Button(nav_frame, text="|<", command=lambda: self.jump_to_ply(0), bg=COLORS["btn_bg"], fg="white").grid(row=0, column=0, padx=2)
        tk.Button(nav_frame, text="< Prev", command=lambda: self.jump_to_ply(max(0, self.view_ply - 1)), bg=COLORS["btn_bg"], fg="white").grid(row=0, column=1, padx=2)
        tk.Button(nav_frame, text="Next >", command=lambda: self.jump_to_ply(min(len(self.game.move_stack), self.view_ply + 1)), bg=COLORS["btn_bg"], fg="white").grid(row=0, column=2, padx=2)
        tk.Button(nav_frame, text=">|", command=lambda: self.jump_to_ply(len(self.game.move_stack)), bg=COLORS["best"], fg="white").grid(row=0, column=3, padx=2)

        self.stats_text = tk.Text(self.right_frame, height=8, bg="#1e1e1e", fg="white", font=("Courier", 10), relief=tk.FLAT)

    def build_heatmap_legend(self):
        for widget in self.legend_frame.winfo_children(): widget.destroy()
        tk.Label(self.legend_frame, text="Heatmap:", bg=COLORS["panel"], fg="#aaa", font=("Arial", 9)).grid(row=0, column=0, sticky="w", padx=(0,5))
        for i in range(6):
            btn = tk.Button(self.legend_frame, bg=self.master.storage.data["heatmap"][str(i)], width=2, command=lambda idx=i: self.change_heatmap_color(str(idx)), relief=tk.FLAT)
            btn.grid(row=0, column=i*2+1, padx=2)
            lbl = f"{i}" if i < 5 else "5+"
            tk.Label(self.legend_frame, text=lbl, bg=COLORS["panel"], fg="white", font=("Arial", 8)).grid(row=0, column=i*2+2, padx=(0,2))

    def change_heatmap_color(self, val_str):
        color = colorchooser.askcolor(title=f"Choose Color for {val_str}")[1]
        if color:
            self.master.storage.data["heatmap"][val_str] = color
            self.master.storage.save()
            self.build_heatmap_legend()
            if self.heatmap_mode != "Off": self.draw_board()

    def run_timer(self):
        if self.game.is_game_over() or self.mode == "review": return
        self.times[self.game.turn] -= 1
        top_color = chess.BLACK if self.board_orientation == chess.WHITE else chess.WHITE
        bot_color = chess.WHITE if self.board_orientation == chess.WHITE else chess.BLACK
        m1, s1 = divmod(self.times[top_color], 60)
        m2, s2 = divmod(self.times[bot_color], 60)
        self.top_time_lbl.config(text=f"{m1}:{s1:02d}")
        self.bot_time_lbl.config(text=f"{m2}:{s2:02d}")

        if self.times[self.game.turn] <= 0:
            self.show_action_overlay("Flagged! Time out.", [("Rematch", lambda: self.master.switch_frame(GameUI, mode=self.mode, time_limit=self.time_limit)), ("Menu", self.master.show_start_screen)])
            return
        self.timer_id = self.master.after(1000, self.run_timer)

    def calculate_material(self, board):
        values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
        w_mat = sum(len(board.pieces(pt, chess.WHITE)) * val for pt, val in values.items())
        b_mat = sum(len(board.pieces(pt, chess.BLACK)) * val for pt, val in values.items())
        diff = w_mat - b_mat
        top_color = chess.BLACK if self.board_orientation == chess.WHITE else chess.WHITE
        self.top_mat_lbl.config(text=f"+{abs(diff)}" if (top_color == chess.WHITE and diff > 0) or (top_color == chess.BLACK and diff < 0) else "")
        self.bot_mat_lbl.config(text=f"+{abs(diff)}" if (top_color == chess.BLACK and diff > 0) or (top_color == chess.WHITE and diff < 0) else "")

    def cycle_heatmap(self):
        modes = ["Off", "Both", "White", "Black"]
        current_index = modes.index(self.heatmap_mode)
        self.heatmap_mode = modes[(current_index + 1) % len(modes)]
        btn_text = f"🔥 Heatmap ({self.heatmap_mode})"
        self.btn_heatmap.config(text=btn_text, bg=COLORS["btn_bg"] if self.heatmap_mode == "Off" else COLORS["accent"])
        self.draw_board()

    def toggle_eval(self):
        self.show_eval_bar = not self.show_eval_bar
        if self.show_eval_bar:
            self.eval_canvas.pack(side=tk.LEFT, padx=(0, 4))
            self.trigger_eval_update()
        else: self.eval_canvas.pack_forget()

    def toggle_helper(self):
        self.helper_active = not self.helper_active
        self.btn_helper.config(text=f"🤖 Helper ({'On' if self.helper_active else 'Off'})", bg=COLORS["tactic"] if self.helper_active else COLORS["btn_bg"])
        if not self.helper_active: self.helper_container.pack_forget()
        else: self.trigger_helper_check()

    def trigger_helper_check(self):
        self.helper_container.pack_forget()
        self.tactic_move = None
        if not self.helper_active or self.game.is_game_over() or self.mode == "review": return
        view_board = chess.Board(self.start_fen)
        for move in self.game.move_stack[:self.view_ply]: view_board.push(move)
        if self.mode in ["practice", "endgame"] and view_board.turn == self.cpu_color and not self.override_cpu: return
        threading.Thread(target=self._helper_thread, args=(view_board,), daemon=True).start()

    def _helper_thread(self, board):
        tactic_name, tactic_move = self.master.engine_mgr.detect_tactic(board)
        if tactic_name and tactic_move:
            self.master.after(0, self.display_special_move_btn, tactic_name, tactic_move)

    def display_special_move_btn(self, tactic_name, tactic_move):
        self.tactic_move = tactic_move
        self.btn_special_move.config(text=f"See Special Move: {tactic_name}")
        self.helper_container.pack(fill=tk.X, padx=10, pady=5, after=self.move_list_box)

    def reveal_tactic(self):
        if self.tactic_move:
            self.hint_arrow = self.tactic_move
            self.draw_board()

    def trigger_eval_update(self):
        if not self.show_eval_bar: return
        threading.Thread(target=self._eval_thread, daemon=True).start()

    def _eval_thread(self):
        view_board = chess.Board(self.start_fen)
        for move in self.game.move_stack[:self.view_ply]: view_board.push(move)
        score = self.master.engine_mgr.get_eval_score(view_board)
        self.master.after(0, self._draw_eval_bar, score)

    def _draw_eval_bar(self, score):
        self.eval_canvas.delete("all")
        clamped = max(-5.0, min(5.0, score))
        white_percent = (clamped + 5.0) / 10.0
        height = 8 * SQUARE_SIZE
        white_pixels = int(height * white_percent)
        
        if self.board_orientation == chess.WHITE:
            self.eval_canvas.create_rectangle(0, height - white_pixels, 20, height, fill="#fff", outline="")
            self.eval_canvas.create_rectangle(0, 0, 20, height - white_pixels, fill="#333", outline="")
        else:
            self.eval_canvas.create_rectangle(0, 0, 20, white_pixels, fill="#fff", outline="")
            self.eval_canvas.create_rectangle(0, white_pixels, 20, height, fill="#333", outline="")

    def toggle_override(self):
        self.override_cpu = not self.override_cpu
        self.btn_override.config(text=f"Force CPU Move ({'On' if self.override_cpu else 'Off'})", bg=COLORS["best"] if self.override_cpu else COLORS["btn_bg"])
        if not self.override_cpu and self.game.turn == self.cpu_color: self.do_cpu_turn()

    def flip_board(self):
        self.board_orientation = not self.board_orientation
        self.draw_board()
        self.trigger_eval_update()
        self.calculate_material(chess.Board(self.start_fen))

    def update_turn_indicator(self):
        is_live = self.view_ply == len(self.game.move_stack)
        temp = chess.Board(self.start_fen)
        for move in self.game.move_stack[:self.view_ply]: temp.push(move)
        
        turn_text = "White to Move" if temp.turn == chess.WHITE else "Black to Move"
        if not is_live: turn_text += " (Viewing History)"
        self.turn_lbl.config(text=turn_text)

        self.turn_canvas.delete("all")
        if temp.turn == chess.WHITE:
            self.turn_canvas.create_oval(2, 2, 18, 18, fill="#ffffff", outline="#aaaaaa", width=1)
        else:
            self.turn_canvas.create_oval(2, 2, 18, 18, fill="#000000", outline="#aaaaaa", width=1)

    def update_status_bar(self):
        if self.mode == "review": self.status_bar.config(text="Review Mode. Click 'Next >' to evaluate moves.")
        else: self.status_bar.config(text="Drag/Click: Move | Right-click: Draw Arrows | Double Right-click: Inspect Tile")

    def go_back_to_menu(self):
        if self.timer_id: self.master.after_cancel(self.timer_id)
        if self.mode not in ["puzzle", "review"] and len(self.game.move_stack) > 0:
            self.master.storage.save_session(self.mode, self.cpu_elo, self.start_fen, self.cpu_color, self.trainer_desc, [m.uci() for m in self.game.move_stack])
        self.master.show_start_screen()

    def draw_board(self):
        self.canvas.delete("board_element")
        view_board = chess.Board(self.start_fen)
        for move in self.game.move_stack[:self.view_ply]: view_board.push(move)

        last_move = view_board.peek() if len(view_board.move_stack) > 0 else None
        self.calculate_material(view_board)
        
        for r in range(8):
            for c in range(8):
                rank = 7 - r if self.board_orientation == chess.WHITE else r
                file = c if self.board_orientation == chess.WHITE else 7 - c
                square = chess.square(file, rank)
                x1, y1 = c * SQUARE_SIZE, r * SQUARE_SIZE
                x2, y2 = x1 + SQUARE_SIZE, y1 + SQUARE_SIZE
                
                base_color = COLORS["light"] if (r + c) % 2 == 0 else COLORS["dark"]
                if last_move and square in (last_move.from_square, last_move.to_square):
                    base_color = COLORS["last_light"] if (r + c) % 2 == 0 else COLORS["last_dark"]
                if self.selected_square == square: base_color = COLORS["select"]
                
                if self.heatmap_mode != "Off":
                    w_atk = len(view_board.attackers(chess.WHITE, square))
                    b_atk = len(view_board.attackers(chess.BLACK, square))
                    
                    total_atk = 0
                    if self.heatmap_mode == "Both": total_atk = w_atk + b_atk
                    elif self.heatmap_mode == "White": total_atk = w_atk
                    elif self.heatmap_mode == "Black": total_atk = b_atk
                    
                    if total_atk > 0:
                        clamped_atk = str(min(5, total_atk))
                        base_color = self.master.storage.data["heatmap"][clamped_atk]

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=base_color, outline="#111", tags="board_element")
                
                if c == 0: self.canvas.create_text(x1 + 10, y1 + 12, text=str(rank + 1), fill=COLORS["dark"] if (r + c) % 2 == 0 else COLORS["light"], font=("Arial", 10, "bold"), tags="board_element")
                if r == 7: self.canvas.create_text(x2 - 10, y2 - 12, text=chr(ord('a') + file), fill=COLORS["dark"] if (r + c) % 2 == 0 else COLORS["light"], font=("Arial", 10, "bold"), tags="board_element")

                if square in [m.to_square for m in self.valid_moves]:
                    if view_board.piece_at(square): self.canvas.create_oval(x1+4, y1+4, x2-4, y2-4, outline=COLORS["highlight"], width=4, tags="board_element")
                    else: self.canvas.create_oval(x1+26, y1+26, x2-26, y2-26, fill=COLORS["highlight"], outline="", tags="board_element")

                piece = view_board.piece_at(square)
                if piece:
                    # Skip drawing if piece is actively being dragged
                    if getattr(self, 'is_dragging', False) and square == getattr(self, 'drag_start_square', None):
                        continue

                    main_color = "#FFFFFF" if piece.color == chess.WHITE else "#000000"
                    stroke_color = "#000000" if piece.color == chess.WHITE else "#FFFFFF"
                    px, py = (x1+x2)/2, (y1+y2)/2
                    font = ("Arial", 42)
                    for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                        self.canvas.create_text(px+dx, py+dy, text=PIECE_SHAPES[piece.piece_type], font=font, fill=stroke_color, tags="board_element")
                    self.canvas.create_text(px, py, text=PIECE_SHAPES[piece.piece_type], font=font, fill=main_color, tags="board_element")

        if self.hint_arrow and self.view_ply == len(self.game.move_stack):
            sx, sy = self.get_square_coords(self.hint_arrow.from_square)
            ex, ey = self.get_square_coords(self.hint_arrow.to_square)
            self.canvas.create_line(sx+SQUARE_SIZE//2, sy+SQUARE_SIZE//2, ex+SQUARE_SIZE//2, ey+SQUARE_SIZE//2, arrow=tk.LAST, fill=COLORS["arrow_hint"], width=6, arrowshape=(16,20,6), tags="board_element")

        for start_sq, end_sq in self.drawn_arrows:
            sx, sy = self.get_square_coords(start_sq)
            ex, ey = self.get_square_coords(end_sq)
            self.canvas.create_line(sx+SQUARE_SIZE//2, sy+SQUARE_SIZE//2, ex+SQUARE_SIZE//2, ey+SQUARE_SIZE//2, arrow=tk.LAST, fill=COLORS["arrow_plan"], width=5, arrowshape=(16,20,6), tags="board_element")

        if self.view_ply < len(self.game.move_stack) and self.mode != "review":
            self.canvas.create_rectangle(0, 0, 8*SQUARE_SIZE, 8*SQUARE_SIZE, fill="#000", stipple="gray25", tags="board_element")

    def get_square_coords(self, square):
        rank, file = chess.square_rank(square), chess.square_file(square)
        r, c = (7 - rank, file) if self.board_orientation == chess.WHITE else (rank, 7 - file)
        return c * SQUARE_SIZE, r * SQUARE_SIZE

    def show_action_overlay(self, title, buttons_data):
        if self.overlay_frame: self.overlay_frame.destroy()
        self.overlay_frame = tk.Frame(self.canvas, bg="#222", bd=2, relief=tk.RAISED, padx=20, pady=20)
        self.overlay_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        tk.Label(self.overlay_frame, text=title, font=("Arial", 18, "bold"), bg="#222", fg="white").pack(pady=(0, 15))
        for text, command in buttons_data:
            tk.Button(self.overlay_frame, text=text, font=("Arial", 12), bg=COLORS["best"] if text.startswith("Next") or text=="Review Game" else COLORS["btn_bg"], fg="white", width=15, command=command).pack(pady=5)

    def start_review_mode(self):
        if self.overlay_frame: self.overlay_frame.destroy()
        self.mode = "review"
        self.update_status_bar()
        self.jump_to_ply(0)

    def on_right_click(self, event):
        c, r = event.x // SQUARE_SIZE, event.y // SQUARE_SIZE
        if 0 <= c < 8 and 0 <= r < 8:
            rank, file = (7 - r, c) if self.board_orientation == chess.WHITE else (r, 7 - c)
            self.arrow_start_square = chess.square(file, rank)

    def on_right_release(self, event):
        if self.arrow_start_square is not None:
            c, r = event.x // SQUARE_SIZE, event.y // SQUARE_SIZE
            if 0 <= c < 8 and 0 <= r < 8:
                rank, file = (7 - r, c) if self.board_orientation == chess.WHITE else (r, 7 - c)
                end_square = chess.square(file, rank)
                if self.arrow_start_square != end_square:
                    tup = (self.arrow_start_square, end_square)
                    if tup in self.drawn_arrows: self.drawn_arrows.remove(tup) 
                    else: self.drawn_arrows.append(tup)
                    self.draw_board()
        self.arrow_start_square = None

    def on_right_double_click(self, event):
        c, r = event.x // SQUARE_SIZE, event.y // SQUARE_SIZE
        if 0 <= c < 8 and 0 <= r < 8:
            rank, file = (7 - r, c) if self.board_orientation == chess.WHITE else (r, 7 - c)
            square = chess.square(file, rank)
            
            view_board = chess.Board(self.start_fen)
            for move in self.game.move_stack[:self.view_ply]: view_board.push(move)
            
            w_atk = len(view_board.attackers(chess.WHITE, square))
            b_atk = len(view_board.attackers(chess.BLACK, square))
            sq_name = chess.square_name(square).upper()
            
            self.status_bar.config(text=f"Tile Inspector ({sq_name}):  ⚪ {w_atk} White Attackers  |  ⚫ {b_atk} Black Attackers", fg=COLORS["arrow_hint"])

    def on_press(self, event):
        self.drawn_arrows.clear()
        self.hint_arrow = None
        self.update_status_bar()

        # Input rejection conditions
        if self.mode == "review" or self.master.engine_mgr.is_thinking or self.is_evaluating_game or self.game.is_game_over() or self.overlay_frame:
            if self.view_ply < len(self.game.move_stack) and self.mode != "review":
                self.jump_to_ply(len(self.game.move_stack))
            return

        if self.mode in ["practice", "endgame"] and self.game.turn == self.cpu_color and not self.override_cpu: 
            return

        c, r = event.x // SQUARE_SIZE, event.y // SQUARE_SIZE
        if not (0 <= c < 8 and 0 <= r < 8): return
        rank, file = (7 - r, c) if self.board_orientation == chess.WHITE else (r, 7 - c)
        square = chess.square(file, rank)
        piece = self.game.piece_at(square)

        # Allow traditional click-to-move if a piece is already selected
        if self.selected_square is not None:
            move_to_make = next((m for m in self.valid_moves if m.to_square == square), None)
            if move_to_make:
                if move_to_make.promotion: move_to_make.promotion = chess.QUEEN
                self.undone_moves.clear()
                self.execute_move(move_to_make)
                return

        if piece and piece.color == self.game.turn:
            self.selected_square = square
            self.valid_moves = [m for m in self.game.legal_moves if m.from_square == square]
            self.drag_start_square = square
            self.is_dragging = False
            self.draw_board()
        else:
            self.selected_square = None
            self.valid_moves = []
            self.drag_start_square = None
            self.draw_board()

    def on_motion(self, event):
        if getattr(self, 'drag_start_square', None) is not None:
            if not getattr(self, 'is_dragging', False):
                self.is_dragging = True
                self.draw_board() 
            
            self.canvas.delete("drag_piece")
            
            piece = self.game.piece_at(self.drag_start_square)
            if piece:
                main_color = "#FFFFFF" if piece.color == chess.WHITE else "#000000"
                stroke_color = "#000000" if piece.color == chess.WHITE else "#FFFFFF"
                font = ("Arial", 42)
                for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                    self.canvas.create_text(event.x+dx, event.y+dy, text=PIECE_SHAPES[piece.piece_type], font=font, fill=stroke_color, tags="drag_piece")
                self.canvas.create_text(event.x, event.y, text=PIECE_SHAPES[piece.piece_type], font=font, fill=main_color, tags="drag_piece")

    def on_release(self, event):
        if getattr(self, 'is_dragging', False):
            self.canvas.delete("drag_piece")
            c, r = event.x // SQUARE_SIZE, event.y // SQUARE_SIZE
            
            if 0 <= c < 8 and 0 <= r < 8:
                rank, file = (7 - r, c) if self.board_orientation == chess.WHITE else (r, 7 - c)
                square = chess.square(file, rank)
                
                move_to_make = next((m for m in self.valid_moves if m.to_square == square), None)
                if move_to_make:
                    if move_to_make.promotion: move_to_make.promotion = chess.QUEEN
                    self.undone_moves.clear()
                    self.drag_start_square = None
                    self.is_dragging = False
                    self.execute_move(move_to_make)
                    return
            
            # Snap back to grid if released on invalid square or off-board
            self.is_dragging = False
            self.draw_board()
            
        self.drag_start_square = None

    def execute_move(self, move):
        self.game.push(move)
        self.view_ply += 1
        
        self.selected_square = None
        self.valid_moves = []
        
        if self.mode == "puzzle":
            self.draw_board()
            self.trigger_eval_update()
            self.trigger_helper_check()
            self.puzzle_logic.verify_move(move.uci())
            return

        if self.mode != "review":
            self.master.storage.save_session(self.mode, self.cpu_elo, self.start_fen, self.cpu_color, self.trainer_desc, [m.uci() for m in self.game.move_stack])
        
        self.update_turn_indicator()
        self.draw_board()
        self.trigger_eval_update()
        self.update_move_list_ui()
        self.trigger_helper_check()

        if self.game.is_game_over():
            self.handle_game_over()
            return

        if self.mode in ["practice", "endgame"] and self.game.turn == self.cpu_color and not self.override_cpu:
            self.do_cpu_turn()

    def update_move_list_ui(self):
        if self.mode == "puzzle": return
        self.move_list_box.delete(0, tk.END)
        board_copy = chess.Board(self.start_fen)
        for i, move in enumerate(self.game.move_stack):
            san_move = board_copy.san(move)
            badge = self.move_annotations.get(i, "")
            board_copy.push(move)
            turn_num = (i // 2) + 1
            prefix = f"{turn_num}. " if i % 2 == 0 else "   "
            self.move_list_box.insert(tk.END, f"{prefix}{san_move} {badge}")
        
        if self.view_ply > 0:
            self.move_list_box.selection_clear(0, tk.END)
            self.move_list_box.selection_set(self.view_ply - 1)
            self.move_list_box.see(self.view_ply - 1)

    def on_history_click(self, event):
        selection = self.move_list_box.curselection()
        if selection: self.jump_to_ply(selection[0] + 1)

    def jump_to_ply(self, ply):
        is_new_review_step = (self.mode == "review" and ply > self.view_ply and ply <= len(self.game.move_stack))
        
        self.view_ply = ply
        self.selected_square = None
        self.valid_moves = []
        self.update_turn_indicator()
        self.draw_board()
        self.trigger_eval_update()
        self.trigger_helper_check()
        
        if is_new_review_step:
            move_index = self.view_ply - 1
            if move_index not in self.move_annotations:
                self.status_bar.config(text="Analyzing move...", fg="#ff9800")
                self.update()
                
                view_board = chess.Board(self.start_fen)
                for m in self.game.move_stack[:move_index]: view_board.push(m)
                played_move = self.game.move_stack[move_index]
                
                acc_text, acc_color, badge = self.master.engine_mgr.analyze_move_accuracy(view_board, played_move)
                self.move_annotations[move_index] = badge
                self.accuracy_lbl.config(text=f"Move {move_index+1}: {acc_text}", fg=acc_color)
                self.status_bar.config(text="Review Mode. Click 'Next >' to evaluate moves.", fg="#888")

        self.update_move_list_ui()

    def show_hint(self):
        if self.master.engine_mgr.is_thinking or self.game.is_game_over() or self.view_ply < len(self.game.move_stack): return
        self.status_lbl.config(text="Calculating...", fg="#ff9800")
        self.update() 
        best = self.master.engine_mgr.get_best_move(self.game.copy())
        if best:
            self.hint_arrow = best 
            self.draw_board()
        self.status_lbl.config(text="Your Turn", fg="#4CAF50")

    def undo_move(self, count=1):
        if self.master.engine_mgr.is_thinking or self.mode == "review" or self.mode == "puzzle": return
        self.jump_to_ply(len(self.game.move_stack)) 
        self.drawn_arrows.clear()
        self.hint_arrow = None
        if self.overlay_frame: self.overlay_frame.destroy()
        
        if len(self.game.move_stack) >= count:
            for _ in range(count):
                self.undone_moves.append(self.game.pop())
                self.view_ply -= 1
            self.update_move_list_ui()
            self.update_turn_indicator()
            self.draw_board()
            self.trigger_eval_update()
            self.trigger_helper_check()

    def redo_move(self, count=1):
        if self.master.engine_mgr.is_thinking or not self.undone_moves or self.mode == "review" or self.mode == "puzzle": return
        self.jump_to_ply(len(self.game.move_stack))
        
        if len(self.undone_moves) >= count:
            for _ in range(count):
                self.game.push(self.undone_moves.pop())
                self.view_ply += 1
            self.update_move_list_ui()
            self.update_turn_indicator()
            self.draw_board()
            self.trigger_eval_update()
            self.trigger_helper_check()

    def do_cpu_turn(self):
        self.master.engine_mgr.is_thinking = True
        self.status_lbl.config(text="CPU is calculating...", fg="#ff9800")
        threading.Thread(target=self._cpu_thread, daemon=True).start()

    def _cpu_thread(self):
        with self.master.engine_mgr.lock:
            result = self.master.engine_mgr.engine.play(self.game, chess.engine.Limit(time=0.5))
        self.master.after(0, self._apply_cpu_move, result.move)

    def _apply_cpu_move(self, move):
        self.master.engine_mgr.is_thinking = False
        self.status_lbl.config(text="Your Turn", fg="#4CAF50")
        self.execute_move(move)

    def handle_game_over(self):
        if self.timer_id: self.master.after_cancel(self.timer_id)
        self.master.storage.clear_session()
        self.helper_container.pack_forget()
        
        res = self.game.result()
        if self.mode == "practice": self.master.storage.record_game_result(res, self.cpu_elo)
        
        self.status_lbl.config(text="Game Over! Analyzing...", fg="#00e5ff")
        self.is_evaluating_game = True
        threading.Thread(target=self._analyze_game, daemon=True).start()

    def _analyze_game(self):
        player_color = not self.cpu_color if self.cpu_color is not None else chess.WHITE
        stats = self.master.engine_mgr.calculate_game_accuracy(
            list(self.game.move_stack), 
            player_color, 
            self.start_fen
        )
        self.master.after(0, self._display_game_stats, stats)

    def _display_game_stats(self, stats):
        self.is_evaluating_game = False
        self.status_lbl.config(text=f"Result: {self.game.result()}", fg="white")
        
        if stats:
            self.stats_text.pack(fill=tk.BOTH, padx=10, pady=(5,10))
            text = f"--- GAME REPORT ---\n"
            text += f"Est. Performance ELO: {stats['Est_ELO']}\n\n"
            text += f"Overall Accuracy: {stats['Overall']}%\n"
            text += f"  - Opening: {stats['Opening']}%\n"
            text += f"  - Middlegame: {stats['Middlegame']}%\n"
            text += f"  - Endgame: {stats['Endgame']}%\n"
            self.stats_text.delete(1.0, tk.END)
            self.stats_text.insert(tk.END, text)

        actions = [("Review Game", self.start_review_mode)]
        if self.mode == "endgame" and self.game.is_checkmate() and self.game.turn == self.cpu_color:
            actions.append(("Restart Drill", lambda: self.master.switch_frame(GameUI, mode=self.mode, start_fen=self.start_fen, cpu_color=self.cpu_color, trainer_desc=self.trainer_desc)))
            self.show_action_overlay("Trainer Complete!", actions)
        else:
            actions.append(("Main Menu", self.master.show_start_screen))
            self.show_action_overlay(f"Game Over: {self.game.result()}", actions)

if __name__ == "__main__":
    app = AppController()
    app.mainloop()

