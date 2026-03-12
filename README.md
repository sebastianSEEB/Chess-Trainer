**Chess Trainer** 
A feature-rich Chess training application built with Python. This tool allows users to play against the Stockfish engine, solve tactical puzzles, and review their games with centipawn accuracy analysis.

**Features**
Practice Mode: Play against Stockfish with adjustable ELO (800–2500+).

Puzzle Trainer: Tactical puzzles filtered by theme (Mates, Material) and user ELO.

Game Review: Post-game analysis featuring move badges (Best, Blunder, Mistake).

Session Persistence: Automatically saves your game state, ELO, and streaks.

**Installation**
Clone the repository:

git clone https://github.com/sebastianSEEB/Chess-Trainer.git
cd Chess-Trainer
Install Dependencies:

pip install chess
Setup Stockfish (Required):

Download the Stockfish binary for your OS from stockfishchess.org.

Place the stockfish.exe (or the equivalent for your OS) directly in the root folder of this project.

Ensure the file is named exactly stockfish.exe (or update the STOCKFISH_PATH in Chess.py).

**Setup Puzzles:**

Place a Lichess puzzle CSV named lichess_db_puzzle.csv in the root folder.

On first run, the app will automatically generate a lightweight puzzles_db.json.

**Usage**
Run the application using:

python Chess.py
