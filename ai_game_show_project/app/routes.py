from flask import Blueprint, jsonify, request
from . import db  # Assuming db is in app/__init__.py
from .models import Question, GameSession
from sqlalchemy.sql.expression import func
from sqlalchemy.orm.attributes import flag_modified
from flask import current_app, render_template
import logging
import random
from datetime import datetime # Added datetime for game_session.end_time

# API Blueprint
bp = Blueprint('api', __name__)

# Main Blueprint (for serving HTML)
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html')

# --- Mock LLM Helper Function ---
def get_mock_llm_response(question_text, answer_choices):
    question_text_lower = question_text.lower()

    # 1. Keyword Matching
    keyword_map = {
        "capital of france": "Paris",
        "color of the sky": "blue",
        "2 + 2": "4",
        "what is h2o": "Water",
        "square root of 16": "4"
        # Add more keywords as desired
    }
    for keyword, answer in keyword_map.items():
        if keyword in question_text_lower:
            return f"{answer} (keyword match)"

    # 2. Answer Choice Selection (Improved)
    if answer_choices and isinstance(answer_choices, list) and len(answer_choices) > 0:
        # Heuristic: if a choice (as a whole word/phrase, case insensitive) is in the question
        for choice in answer_choices:
            if str(choice).lower() in question_text_lower:
                # This simple check might be too broad, e.g. "Is it apple or banana?" with choice "apple"
                # A more robust check might involve checking for choice as a standalone word in question.
                # For now, if the choice string appears in the question, we'll consider it "hinted".
                # return f"{choice} (hinted in question)" # This might be too aggressive, disabling for now
                pass

        # Fallback to random choice if no clear hint or strong heuristic match
        return f"{random.choice(answer_choices)} (random choice)"

    # 3. Generic Fallback
    generic_answers = [
        "Hmm, that's a good question. Let me ponder...",
        "That's a tricky one! My circuits are whirring.",
        "I'll take a calculated guess: Is it '42' perhaps?",
        "My programming suggests... 'syzygy' is a fun word!",
        "Let's go with C, always a classic choice in multiple choice scenarios.",
        "I'm just a mock AI, you know. How about 'mock-a-doodle-doo' as an answer?"
    ]
    return random.choice(generic_answers)

# --- AI Agent Service Endpoint ---
@bp.route('/agent/get_answer', methods=['POST'])
def get_ai_answer():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input, JSON expected"}), 400

    player_id = data.get('player_id')
    question_text = data.get('question_text')
    answer_choices = data.get('answer_choices')

    if not question_text:
        return jsonify({"error": "Missing required field: question_text"}), 400

    # TODO: Replace with real LLM call in the future
    suggested_answer = get_mock_llm_response(question_text, answer_choices)

    response = {
        "player_id": player_id,
        "suggested_answer": suggested_answer
    }
    return jsonify(response), 200

# --- Question Service Endpoints ---

@bp.route('/questions', methods=['POST'])
def add_question():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input, JSON expected"}), 400

    required_fields = ['text', 'correct_answer']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    try:
        question = Question(
            text=data['text'],
            correct_answer=data['correct_answer'],
            answer_choices=data.get('answer_choices'), # Optional
            difficulty=data.get('difficulty', 'medium'),
            pack_name=data.get('pack_name'), # Optional
            question_type=data.get('question_type', 'text') # Optional, defaults to 'text'
        )
        db.session.add(question)
        db.session.commit()

        # Prepare a serializable representation of the question
        # (SQLAlchemy model instances are not directly JSON serializable in this way)
        created_question = {
            "id": question.id,
            "text": question.text,
            "answer_choices": question.answer_choices,
            "correct_answer": question.correct_answer,
            "difficulty": question.difficulty,
            "pack_name": question.pack_name,
            "question_type": question.question_type,
            "created_at": question.created_at.isoformat() if question.created_at else None
        }
        return jsonify(created_question), 201

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding question: {e}") # Log the actual error
        return jsonify({"error": "Failed to add question due to an internal error"}), 500


@bp.route('/questions/<int:question_id>', methods=['GET'])
def get_question(question_id):
    question = db.session.get(Question, question_id) # More direct way to get by PK with SQLAlchemy 2.x style
    if question:
        return jsonify({
            "id": question.id,
            "text": question.text,
            "answer_choices": question.answer_choices,
            "correct_answer": question.correct_answer,
            "difficulty": question.difficulty,
            "pack_name": question.pack_name,
            "question_type": question.question_type,
            "created_at": question.created_at.isoformat() if question.created_at else None
        })
    return jsonify({"error": "Question not found"}), 404


@bp.route('/questions/random', methods=['GET'])
def get_random_question():
    # For SQLite, func.random() works. For PostgreSQL, use func.random().
    # For MySQL, use func.rand().
    # This assumes SQLite for now.
    question = db.session.query(Question).order_by(func.random()).first()
    if question:
        return jsonify({
            "id": question.id,
            "text": question.text,
            "answer_choices": question.answer_choices,
            "correct_answer": question.correct_answer,
            "difficulty": question.difficulty,
            "pack_name": question.pack_name,
            "question_type": question.question_type,
            "created_at": question.created_at.isoformat() if question.created_at else None
        })
    return jsonify({"error": "No questions found"}), 404


# --- Game Logic Service Endpoints ---

@bp.route('/game/start', methods=['POST'])
def start_game():
    players = ["AI_Player_1", "AI_Player_2"]
    initial_scores = {player: 0 for player in players}

    # Use test_client to get a random question
    # This avoids external HTTP requests and direct function calls across services for now
    # In a microservice architecture, this would be an actual HTTP call.
    with current_app.test_client() as client:
        random_question_response = client.get('/api/questions/random') # Internal call

    if random_question_response.status_code != 200:
        logging.error(f"Failed to get initial question: {random_question_response.get_json()}")
        return jsonify({"error": "Failed to start game: Could not retrieve initial question"}), 500

    first_question_data = random_question_response.get_json()
    if not first_question_data or 'id' not in first_question_data:
        logging.error(f"Invalid question data received: {first_question_data}")
        return jsonify({"error": "Failed to start game: Invalid initial question data"}), 500

    first_question_id = first_question_data['id']

    try:
        session = GameSession(
            scores=initial_scores,
            current_player_id=players[0], # Player 1 starts
            current_question_id=first_question_id,
            game_state='active',
            session_name=f"GameSession_{GameSession.query.count() + 1}" # Basic unique name
        )
        db.session.add(session)
        db.session.commit()

        game_session_data = {
            "id": session.id,
            "session_name": session.session_name,
            "players": players,
            "scores": session.scores,
            "current_player_id": session.current_player_id,
            "current_question_id": session.current_question_id,
            "current_question_text": first_question_data.get("text"), # Include text for convenience
            "game_state": session.game_state,
            "start_time": session.start_time.isoformat()
        }
        return jsonify(game_session_data), 201

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error starting game session: {e}")
        return jsonify({"error": "Failed to start game session due to an internal error"}), 500

@bp.route('/game/<int:session_id>/answer', methods=['POST'])
def submit_answer(session_id):
    # The frontend now just triggers the AI's turn.
    # It can optionally send player_id for validation.
    data = request.get_json()
    requesting_player_id = data.get('player_id') if data else None

    game_session = db.session.get(GameSession, session_id)
    if not game_session:
        return jsonify({"error": "Game session not found"}), 404
    if game_session.game_state != 'active':
        return jsonify({"error": "Game is not active"}), 400

    current_player_id = game_session.current_player_id
    if requesting_player_id and requesting_player_id != current_player_id:
        return jsonify({"error": f"It's {current_player_id}'s turn, not {requesting_player_id}'s"}), 400

    current_question = game_session.current_question
    if not current_question:
        return jsonify({"error": "Current question not found for this session"}), 500

    # Call AI Agent Service to get an answer
    ai_agent_payload = {
        "player_id": current_player_id,
        "question_text": current_question.text,
        "answer_choices": current_question.answer_choices
    }
    with current_app.test_client() as client:
        ai_response = client.post('/api/agent/get_answer', json=ai_agent_payload)

    if ai_response.status_code != 200:
        logging.error(f"AI Agent service error: {ai_response.get_json()}")
        return jsonify({"error": "AI Agent service failed"}), 500

    ai_data = ai_response.get_json()
    suggested_answer_from_ai = ai_data.get("suggested_answer", "") # Default to empty string

    # Quick fix for mock AI's descriptive answers: strip the description part
    # e.g., "Paris (keyword match)" -> "Paris"
    # This is a hack for the current mock; a real AI service should return just the answer.
    processed_suggested_answer = suggested_answer_from_ai
    suffixes_to_strip = [" (keyword match)", " (random choice)", " (hinted in question)"]
    for suffix in suffixes_to_strip:
        if processed_suggested_answer.endswith(suffix):
            processed_suggested_answer = processed_suggested_answer[:-len(suffix)]
            break

    answer_correct = (processed_suggested_answer == current_question.correct_answer)
    if answer_correct:
        game_session.scores[current_player_id] = game_session.scores.get(current_player_id, 0) + 1
        flag_modified(game_session, "scores")

    # Determine next player (simple alternation for 2 players)
    players = list(game_session.scores.keys())
    current_player_index = players.index(current_player_id)
    next_player_id = players[(current_player_index + 1) % len(players)]
    game_session.current_player_id = next_player_id
    game_session.current_round += 1 # Increment round

    # Game completion logic (e.g., after a certain number of rounds)
    # For 2 players, 5 rounds mean 10 questions total.
    # current_round will be 1 after first player, 2 after second, etc.
    # So after round 10, game ends.
    MAX_ROUNDS = 10
    if game_session.current_round >= MAX_ROUNDS:
        game_session.game_state = 'finished'
        game_session.end_time = datetime.utcnow() # Import datetime if not already
        next_question_id_for_response = None
        next_question_text_for_response = "Game Over!"
    else:
        with current_app.test_client() as client:
            random_question_response = client.get('/api/questions/random')

        if random_question_response.status_code != 200:
            logging.error(f"Failed to get next question: {random_question_response.get_json()}")
            db.session.commit()
            return jsonify({"error": "AI answer processed, but failed to retrieve next question."}), 500

        next_question_data = random_question_response.get_json()
        if not next_question_data or 'id' not in next_question_data:
            logging.error(f"Invalid next question data: {next_question_data}")
            db.session.commit()
            return jsonify({"error": "AI answer processed, but invalid data for next question."}), 500

        game_session.current_question_id = next_question_data['id']
        next_question_id_for_response = next_question_data['id']
        next_question_text_for_response = next_question_data.get("text")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error committing answer processing: {e}")
        return jsonify({"error": "Database error processing answer"}), 500

    response_data = {
        "session_id": game_session.id,
        "answer_result": "correct" if answer_correct else "incorrect",
        "suggested_answer": suggested_answer_from_ai, # Show original AI response in output
        "scores": game_session.scores,
        "current_player_id": game_session.current_player_id, # This is the *next* player
        "game_state": game_session.game_state,
        "current_round": game_session.current_round
    }
    if game_session.game_state == 'active':
        response_data["next_question_id"] = next_question_id_for_response
        response_data["next_question_text"] = next_question_text_for_response
    elif game_session.game_state == 'finished':
        response_data["message"] = "Game Over! Final scores are above."

    return jsonify(response_data)


@bp.route('/game/<int:session_id>/status', methods=['GET'])
def game_session_status(session_id):
    game_session = db.session.get(GameSession, session_id)
    if not game_session:
        return jsonify({"error": "Game session not found"}), 404

    response_data = {
        "id": game_session.id,
        "session_name": game_session.session_name,
        "scores": game_session.scores,
        "current_player_id": game_session.current_player_id,
        "current_question_id": game_session.current_question_id,
        "game_state": game_session.game_state,
        "start_time": game_session.start_time.isoformat(),
        "end_time": game_session.end_time.isoformat() if game_session.end_time else None,
    }
    if game_session.current_question:
        response_data["current_question_text"] = game_session.current_question.text

    return jsonify(response_data)
