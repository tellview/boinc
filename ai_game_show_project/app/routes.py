from flask import Blueprint, jsonify, request
from . import db  # Assuming db is in app/__init__.py
from .models import Question, GameSession, AudienceVote # Added AudienceVote
from sqlalchemy.sql.expression import func
from sqlalchemy.orm.attributes import flag_modified
from flask import current_app, render_template
import logging
import random
import requests # For LLM integration
import json # For LLM integration
from datetime import datetime
from flask import current_app # For logger in websockets
from ai_game_show_project.app import sockets # Import sockets object

# API Blueprint
bp = Blueprint('api', __name__)

# Main Blueprint (for serving HTML)
main_bp = Blueprint('main', __name__)

# Hardcoded player details including avatar URLs
# In a real app, this might come from a user model or config
PLAYER_AVATARS = {
    "AI_Player_1": "/static/images/avatar1.png",
    "AI_Player_2": "/static/images/avatar2.png"
}
# List of player IDs, one will be human, one AI for this PoC
PLAYER_IDS = ["Human_Player_1", "AI_Opponent_1"]
MAX_STRIKES = 3
POINTS_PER_QUESTION = 10


@main_bp.route('/')
def index():
    return render_template('index.html')

# --- WebSocket Signaling ---
# WARNING: This simple list for connected_clients_ws is not suitable for production with multiple workers.
connected_clients_ws = []

@sockets.route('/ws/signaling')
def signaling_socket(ws): # ws is a WebSocket object from flask_sockets
    global connected_clients_ws # Ensure modification of the global list
    if ws not in connected_clients_ws:
        connected_clients_ws.append(ws)
    current_app.logger.info(f"WebSocket client connected: {ws}. Total clients: {len(connected_clients_ws)}")

    try:
        while not ws.closed:
            message = ws.receive() # Blocks until a message is received or connection closes
            if message:
                current_app.logger.info(f"WS Received from a client: {message[:200]}...") # Log snippet
                # Broadcast to ALL OTHER connected clients
                for client in connected_clients_ws:
                    if client != ws and not client.closed: # Check if client is not itself and not closed
                        try:
                            client.send(message)
                        except Exception as e:
                            current_app.logger.error(f"Error sending to client {client}: {e}")
                            # Optionally remove problematic client from list here or mark for removal
            elif message is None:
                # This condition usually means client closed connection gracefully
                current_app.logger.info(f"WS Received None from {ws}, client likely closed gracefully.")
                break # Exit loop as client is closed or sent None
    except Exception as e: # Catch broader exceptions like WebSocketError if not specifically caught by flask-sockets
        current_app.logger.error(f"Error in WebSocket handler for client {ws}: {e}")
    finally:
        if ws in connected_clients_ws:
            connected_clients_ws.remove(ws)
        current_app.logger.info(f"WebSocket client disconnected: {ws}. Remaining clients: {len(connected_clients_ws)}")

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
    # No specific logging in the helper, logging will be done by the calling route
    return random.choice(generic_answers)

# --- Real LLM Helper Function (Ollama) ---
def get_real_llm_response(question_text, answer_choices):
    ollama_endpoint = "http://localhost:11434/api/generate"
    model_name = "phi" # Small model, assuming it's available

    prompt = f"Answer the following question. "
    if answer_choices and isinstance(answer_choices, list) and len(answer_choices) > 0:
        prompt += f"Choose the best option from these choices: {', '.join(answer_choices)}. "
        prompt += f"If the answer is clearly among the choices, repeat only the choice as your answer. "
    else:
        prompt += f"Provide a concise answer. "

    prompt += f"\nQuestion: {question_text}\nAnswer:"

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False  # Get the full response at once
    }

    try:
        current_app.logger.debug(f"Attempting to call Ollama. Model: {model_name}, Prompt: {prompt[:100]}...")
        response = requests.post(ollama_endpoint, json=payload, timeout=20) # 20-second timeout
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        response_data = response.json()
        llm_answer = response_data.get("response", "").strip()

        if not llm_answer:
            current_app.logger.warning("Ollama response was empty. Falling back to mock.")
            return get_mock_llm_response(question_text, answer_choices) + " (fallback from empty LLM response)"

        current_app.logger.info(f"Ollama ({model_name}) responded: '{llm_answer[:100]}...'")
        return llm_answer

    except requests.exceptions.ConnectionError as e:
        current_app.logger.error(f"Ollama connection error: {e}. Falling back to mock response.")
        return get_mock_llm_response(question_text, answer_choices) + " (fallback from connection error)"
    except requests.exceptions.Timeout as e:
        current_app.logger.error(f"Ollama request timed out: {e}. Falling back to mock response.")
        return get_mock_llm_response(question_text, answer_choices) + " (fallback from timeout)"
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Ollama request failed: {e}. Response: {e.response.text if e.response else 'N/A'}. Falling back to mock response.")
        return get_mock_llm_response(question_text, answer_choices) + " (fallback from request error)"
    except json.JSONDecodeError as e:
        current_app.logger.error(f"Failed to decode Ollama JSON response: {e}. Falling back to mock response.")
        return get_mock_llm_response(question_text, answer_choices) + " (fallback from JSON decode error)"
    except Exception as e: # Catch any other unexpected errors
        current_app.logger.error(f"Unexpected error calling LLM: {e}. Falling back to mock response.")
        return get_mock_llm_response(question_text, answer_choices) + " (fallback from unexpected error)"


# --- AI Agent Service Endpoint ---
@bp.route('/agent/get_answer', methods=['POST'])
def get_ai_answer():
    data = request.get_json()
    if not data:
        current_app.logger.warning("AI Agent /get_answer: Invalid input, no JSON data received.")
        return jsonify({"error": "Invalid input, JSON expected"}), 400

    player_id = data.get('player_id')
    question_text = data.get('question_text')
    answer_choices = data.get('answer_choices')

    if not question_text:
        current_app.logger.warning("AI Agent /get_answer: Missing question_text.")
        return jsonify({"error": "Missing required field: question_text"}), 400

    # Call the new function that attempts real LLM and falls back to mock
    suggested_answer = get_real_llm_response(question_text, answer_choices)

    # Logging of the final answer (whether from LLM or mock) happens here
    current_app.logger.info(f"AI Agent final answer for player {player_id}, Q: '{question_text[:50]}...': '{suggested_answer}'")

    response = {
        "player_id": player_id,
        "suggested_answer": suggested_answer
    }
    return jsonify(response), 200

# --- Question Service Endpoints ---

@bp.route('/questions/batch', methods=['POST'])
def add_questions_batch():
    questions_data = request.get_json()
    if not isinstance(questions_data, list):
        current_app.logger.warning("POST /questions/batch: Data is not a list.")
        return jsonify({"error": "Request body must be a list of question objects"}), 400

    successful_adds = 0
    failed_adds = 0
    errors = []

    for i, q_data in enumerate(questions_data):
        if not isinstance(q_data, dict):
            errors.append({"index": i, "error": "Item is not a valid JSON object"})
            failed_adds += 1
            continue

        required_fields = ['text', 'correct_answer']
        missing_fields = [field for field in required_fields if field not in q_data]
        if missing_fields:
            errors.append({"index": i, "original_data": q_data.get('text', 'N/A')[:50], "error": f"Missing fields: {', '.join(missing_fields)}"})
            failed_adds += 1
            continue

        try:
            question = Question(
                text=q_data['text'],
                correct_answer=q_data['correct_answer'],
                answer_choices=q_data.get('answer_choices'),
                difficulty=q_data.get('difficulty', 'medium'),
                pack_name=q_data.get('pack_name'),
                question_type=q_data.get('question_type', 'text')
            )
            db.session.add(question)
            # To get an ID for logging before commit, we can flush.
            # db.session.flush() # This would assign an ID if the object is to be persisted.
            # current_app.logger.info(f"Batch import: Staged question ID {question.id if question.id else 'N/A'}: {question.text[:30]}...")
            successful_adds += 1
        except Exception as e:
            # db.session.rollback() # Rollback individual add if not batch committing later
            errors.append({"index": i, "original_data": q_data.get('text', 'N/A')[:50], "error": str(e)})
            failed_adds += 1
            current_app.logger.error(f"Error adding question during batch import (index {i}): {str(e)}")

    try:
        db.session.commit()
        current_app.logger.info(f"Batch question import complete. Successful: {successful_adds}, Failed: {failed_adds}.")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing batch question import: {str(e)}")
        # This is a larger failure; might want to indicate all items from this batch failed to commit
        return jsonify({
            "message": "Batch import failed during final commit.",
            "successful_adds": 0, # Or reflect staged adds if some were flushed and ID'd
            "failed_adds": len(questions_data),
            "errors": [{"index": "ALL", "error": f"Commit failed: {str(e)}"}] + errors
        }), 500

    status_code = 201 # Created
    if failed_adds > 0 and successful_adds > 0:
        status_code = 207 # Multi-Status
    elif failed_adds > 0 and successful_adds == 0:
        status_code = 400 # Bad Request (if all failed due to data issues)

    return jsonify({
        "message": "Batch question import processed.",
        "successful_adds": successful_adds,
        "failed_adds": failed_adds,
        "errors": errors
    }), status_code


@bp.route('/questions', methods=['POST'])
def add_question():
    data = request.get_json()
    if not data:
        current_app.logger.warning("POST /questions: Invalid input, no JSON data received.")
        return jsonify({"error": "Invalid input, JSON expected"}), 400

    required_fields = ['text', 'correct_answer']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        current_app.logger.warning(f"POST /questions: Missing fields: {missing_fields}")
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
        current_app.logger.info(f"New question added: ID {question.id}, Text: {question.text[:50]}...")

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
        current_app.logger.error(f"Error adding question: {str(e)}")
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
    # players = ["AI_Player_1", "AI_Player_2"] # Now using PLAYER_IDS
    initial_scores = {player_id: 0 for player_id in PLAYER_IDS}

    # Use test_client to get a random question
    # This avoids external HTTP requests and direct function calls across services for now
    # In a microservice architecture, this would be an actual HTTP call.
    with current_app.test_client() as client:
        random_question_response = client.get('/api/questions/random') # Internal call

    if random_question_response.status_code != 200:
        error_payload = random_question_response.get_json()
        current_app.logger.error(f"Failed to get initial question for new game: {error_payload.get('error', 'Unknown error') if error_payload else 'No JSON in error response'}")
        return jsonify({"error": "Failed to start game: Could not retrieve initial question"}), 500

    first_question_data = random_question_response.get_json()
    if not first_question_data or 'id' not in first_question_data:
        current_app.logger.error(f"Invalid question data received for new game: {first_question_data}")
        return jsonify({"error": "Failed to start game: Invalid initial question data"}), 500

    first_question_id = first_question_data['id']

    try:
        session = GameSession(
            scores=initial_scores, # DB stores only scores: {"AI_Player_1": 0, "AI_Player_2": 0}
            current_player_id=PLAYER_IDS[0], # Player 1 starts
            current_question_id=first_question_id,
            game_state='active',
            session_name=f"GameSession_{GameSession.query.with_for_update().count() + 1}" # Basic unique name, with_for_update for potential concurrent creation
        )
        db.session.add(session)
        db.session.commit()
        current_app.logger.info(f"New game started: Session ID {session.id}, Name: {session.session_name}, Initial QID: {first_question_id}")

        # Construct player_details for the response dynamically
        player_details_response = {
            PLAYER_IDS[0]: {"score": session.scores.get(PLAYER_IDS[0], 0),
                              "avatar_url": PLAYER_AVATARS.get("AI_Player_1"), # Placeholder for human
                              "type": "HUMAN"},
            PLAYER_IDS[1]: {"score": session.scores.get(PLAYER_IDS[1], 0),
                             "avatar_url": PLAYER_AVATARS.get("AI_Player_2"), # Placeholder for AI opponent
                             "type": "AI"}
        }

        game_session_data = {
            "id": session.id,
            "session_name": session.session_name,
            "player_details": player_details_response,
            "current_player_id": session.current_player_id, # This will be PLAYER_IDS[0] (Human)
            "current_question_id": session.current_question_id,
            "current_question_text": first_question_data.get("text"),
            "current_question_answer_choices": first_question_data.get("answer_choices"), # ADDED
            "game_state": session.game_state,
            "start_time": session.start_time.isoformat(),
            "current_round": session.current_round
        }
        return jsonify(game_session_data), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error starting game session: {str(e)}")
        return jsonify({"error": "Failed to start game session due to an internal error"}), 500

@bp.route('/game/<int:session_id>/answer', methods=['POST'])
def submit_answer(session_id):
    # The frontend now just triggers the AI's turn.
    # It can optionally send player_id for validation.
    data = request.get_json()
    requesting_player_id = data.get('player_id') if data else None

    game_session = db.session.get(GameSession, session_id)
    if not game_session:
        current_app.logger.warning(f"Submit answer: Game session {session_id} not found.")
        return jsonify({"error": "Game session not found"}), 404
    if game_session.game_state != 'active':
        current_app.logger.warning(f"Submit answer: Game session {session_id} is not active (state: {game_session.game_state}).")
        return jsonify({"error": "Game is not active"}), 400

    current_player_id = game_session.current_player_id
    if requesting_player_id and requesting_player_id != current_player_id:
        current_app.logger.warning(f"Submit answer: Turn validation failed for session {session_id}. Requested by: {requesting_player_id}, Current: {current_player_id}")
        return jsonify({"error": f"It's {current_player_id}'s turn, not {requesting_player_id}'s"}), 400

    current_question = game_session.current_question
    if not current_question:
        current_app.logger.error(f"Submit answer: No current question found for active session {session_id}.")
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
        ai_error_payload = ai_response.get_json()
        current_app.logger.error(f"AI Agent service error for session {session_id}, Q{current_question.id}: {ai_error_payload.get('error', 'Unknown AI error') if ai_error_payload else 'No JSON in AI error'}")
        return jsonify({"error": "AI Agent service failed"}), 500

    ai_data = ai_response.get_json()
    suggested_answer_from_ai = ai_data.get("suggested_answer", "") # Default to empty string

    # Quick fix for mock AI's descriptive answers: strip the description part
    # e.g., "Paris (keyword match)" -> "Paris"
    # This is a hack for the current mock; a real AI service should return just the answer.
    processed_suggested_answer = suggested_answer_from_ai

    suffixes_to_strip = [ # Order can matter if suffixes can be part of others
        " (fallback from empty LLM response)",
        " (fallback from connection error)",
        " (fallback from timeout)",
        " (fallback from request error)",
        " (fallback from JSON decode error)",
        " (fallback from unexpected error)",
        " (keyword match)",
        " (random choice)",
        " (hinted in question)",
    ]

    # Iteratively strip suffixes until none are found
    # This handles cases like "Actual Answer (suffix1) (suffix2)"
    stripped_in_last_pass = True
    while stripped_in_last_pass:
        stripped_in_last_pass = False
        for suffix in suffixes_to_strip:
            if processed_suggested_answer.endswith(suffix):
                processed_suggested_answer = processed_suggested_answer[:-len(suffix)]
                stripped_in_last_pass = True
                # No break here, try to strip multiple suffixes if they are stacked
                # However, if a suffix itself contains another (e.g. " (error)", " (connection error)")
                # ordering or more specific logic might be needed.
                # For current distinct suffixes, this iterative pass should be okay.
                # A safer break and re-loop:
                # break
        # if stripped_in_last_pass and any(processed_suggested_answer.endswith(s) for s in suffixes_to_strip):
        #     continue # Force another pass if a suffix was stripped and more might exist

    answer_correct = (processed_suggested_answer == current_question.correct_answer)
    if answer_correct:
        game_session.scores[current_player_id] = game_session.scores.get(current_player_id, 0) + 1
        flag_modified(game_session, "scores")

    # Determine next player (simple alternation for 2 players)
    # players = list(game_session.scores.keys()) # Now using PLAYER_IDS
    current_player_index = PLAYER_IDS.index(current_player_id)
    next_player_id = PLAYER_IDS[(current_player_index + 1) % len(PLAYER_IDS)]
    game_session.current_player_id = next_player_id
    game_session.current_round += 1 # Increment round

    # --- Strike and Steal Logic ---
    next_player_id = ""
    advance_question = False

    if game_session.game_mode == 'active':
        if answer_correct:
            game_session.scores[current_player_id] = game_session.scores.get(current_player_id, 0) + POINTS_PER_QUESTION
            flag_modified(game_session, "scores")
            game_session.current_question_strikes = 0
            game_session.player_who_can_steal = None # Clear any previous steal opportunity

            # Determine next player for the new question
            current_player_index = PLAYER_IDS.index(current_player_id)
            next_player_id = PLAYER_IDS[(current_player_index + 1) % len(PLAYER_IDS)]
            game_session.current_player_id = next_player_id
            advance_question = True
            current_app.logger.info(f"S{session_id} P{current_player_id} Q{current_question.id} Correct. Points: {POINTS_PER_QUESTION}. Strikes reset.")
        else: # Incorrect answer in 'active' mode
            game_session.current_question_strikes += 1
            # Specific log for strike increment
            current_app.logger.info(f'Session {session_id}, Player {current_player_id} received strike {game_session.current_question_strikes} on Q{current_question.id}.')
            # current_app.logger.info(f"S{session_id} P{current_player_id} Q{current_question.id} Incorrect. Strike {game_session.current_question_strikes}.") # Old log
            if game_session.current_question_strikes >= MAX_STRIKES:
                game_session.game_mode = 'steal_attempt'
                current_app.logger.info(f'Session {session_id}, Game mode set to: {game_session.game_mode}.') # Log mode change
                # Determine other player for steal
                other_player_index = (PLAYER_IDS.index(current_player_id) + 1) % len(PLAYER_IDS)
                game_session.player_who_can_steal = PLAYER_IDS[other_player_index]
                # Specific log for strikeout and steal mode
                current_app.logger.info(f'Session {session_id}, Player {current_player_id} struck out on Q{current_question.id}. Game mode changing to steal_attempt for Player {game_session.player_who_can_steal}.')
                game_session.current_player_id = game_session.player_who_can_steal # Turn passes to stealer
                advance_question = False # Steal attempt on the same question
            else:
                # Player still has strikes left on this question, their turn continues on the same question
                next_player_id = current_player_id # Same player's turn
                game_session.current_player_id = current_player_id
                advance_question = False # Same question

    elif game_session.game_mode == 'steal_attempt':
        if requesting_player_id != game_session.player_who_can_steal:
            current_app.logger.warning(f"S{session_id} Steal attempt by wrong player {requesting_player_id}, expected {game_session.player_who_can_steal}")
            return jsonify({"error": "Not your turn to steal"}), 400

        # Log the steal attempt itself, including AI's answer
        current_app.logger.info(f'Session {session_id}, Player {requesting_player_id} attempting steal for Q{current_question.id}. AI answer: {suggested_answer_from_ai}. Correct: {answer_correct}.')

        if answer_correct:
            game_session.scores[current_player_id] = game_session.scores.get(current_player_id, 0) + POINTS_PER_QUESTION
            flag_modified(game_session, "scores")
            # current_app.logger.info(f"S{session_id} P{current_player_id} Q{current_question.id} Steal SUCCESSFUL. Points: {POINTS_PER_QUESTION}.") # Old log
        # else:
            # current_app.logger.info(f"S{session_id} P{current_player_id} Q{current_question.id} Steal FAILED.") # Old log

        game_session.game_mode = 'active'
        current_app.logger.info(f'Session {session_id}, Game mode set to: {game_session.game_mode}.') # Log mode change
        game_session.current_question_strikes = 0
        game_session.player_who_can_steal = None
        # Determine next player for the new question after steal attempt
        current_player_index = PLAYER_IDS.index(current_player_id)
        next_player_id = PLAYER_IDS[(current_player_index + 1) % len(PLAYER_IDS)]
        game_session.current_player_id = next_player_id
        advance_question = True

    # --- Round and Game Completion Logic ---
    if advance_question:
        game_session.current_round += 1 # Increment round only when question advances
        MAX_ROUNDS = 10
        if game_session.current_round >= MAX_ROUNDS:
            game_session.game_state = 'finished'
            current_app.logger.info(f'Session {session_id}, Game mode set to: {game_session.game_state}.') # Log mode change
            game_session.end_time = datetime.utcnow()
            next_question_id_for_response = None
            next_question_text_for_response = "Game Over!"
            next_question_answer_choices_for_response = None
        else: # Fetch next question
            with current_app.test_client() as client:
                random_question_response = client.get('/api/questions/random')
            if random_question_response.status_code != 200:
                next_q_error = random_question_response.get_json()
                current_app.logger.error(f"Failed to get next question for session {session_id}: {next_q_error.get('error', 'Unknown error') if next_q_error else 'No JSON in error'}")
                # Not committing here, let the main commit handle it or error out if critical
                return jsonify({"error": "Processed answer, but failed to retrieve next question."}), 500
            next_question_data = random_question_response.get_json()
            if not next_question_data or 'id' not in next_question_data:
                current_app.logger.error(f"Invalid next question data for session {session_id}: {next_question_data}")
                return jsonify({"error": "Processed answer, but invalid data for next question."}), 500
            game_session.current_question_id = next_question_data['id']
            next_question_id_for_response = next_question_data['id']
            next_question_text_for_response = next_question_data.get("text")
            next_question_answer_choices_for_response = next_question_data.get("answer_choices")
    else: # Same question continues (due to non-max strike for current player or for steal attempt by other player)
        next_question_id_for_response = game_session.current_question_id
        next_question_text_for_response = current_question.text
        next_question_answer_choices_for_response = current_question.answer_choices
        # current_player_id is already set correctly for these scenarios earlier in the logic

    # Log final state for the turn before commit
    current_app.logger.info(f"S{session_id} Turn End. Current Player (for next action): {game_session.current_player_id}, Q_to_be_played: {game_session.current_question_id}, Mode: {game_session.game_mode}, Strikes on Q: {game_session.current_question_strikes}")
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing answer processing for session {session_id}: {str(e)}")
        return jsonify({"error": "Database error processing answer"}), 500

    # Construct player_details for the response
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing answer processing for session {session_id}: {str(e)}")
        return jsonify({"error": "Database error processing answer"}), 500

    # Construct player_details for the response
    player_details_response = {
        p_id: {"score": game_session.scores.get(p_id, 0), "avatar_url": PLAYER_AVATARS.get(p_id)}
        for p_id in PLAYER_IDS
    }

    response_data = {
        "session_id": game_session.id,
        "answer_result": "correct" if answer_correct else "incorrect",
        "suggested_answer": suggested_answer_from_ai,
        "player_details": player_details_response,
        "current_player_id": game_session.current_player_id,
        "game_state": game_session.game_mode, # Use game_mode from session
        "current_round": game_session.current_round,
        "current_question_strikes": game_session.current_question_strikes, # Add this
        "player_who_can_steal": game_session.player_who_can_steal # Add this
    }
    if game_session.game_mode == 'active' and advance_question: # Check game_mode and if question advanced
        response_data["next_question_id"] = next_question_id_for_response
        response_data["next_question_text"] = next_question_text_for_response
        response_data["next_question_answer_choices"] = next_question_answer_choices_for_response
    elif game_session.game_mode == 'steal_attempt': # If steal mode, current question is the steal question
        response_data["current_question_id"] = game_session.current_question_id
        response_data["current_question_text"] = current_question.text # current_question is already fetched
        response_data["current_question_answer_choices"] = current_question.answer_choices
    elif game_session.game_mode == 'finished': # Use game_mode from session
        response_data["message"] = "Game Over! Final scores are above."
        # Clear next question fields if game is over
        response_data.pop("next_question_id", None)
        response_data.pop("next_question_text", None)
        response_data.pop("next_question_answer_choices", None)

    return jsonify(response_data)

# New endpoint for human answers
@bp.route('/game/<int:session_id>/human_submit_answer', methods=['POST'])
def human_submit_answer(session_id):
    data = request.get_json()
    if not data or 'player_id' not in data or 'answer' not in data:
        current_app.logger.warning(f"Human answer S{session_id}: Missing player_id or answer.")
        return jsonify({"error": "Invalid request: player_id and answer are required"}), 400

    requesting_player_id = data['player_id']
    submitted_answer = data['answer']

    game_session = db.session.get(GameSession, session_id)
    if not game_session:
        current_app.logger.warning(f"Human answer S{session_id}: Game session not found.")
        return jsonify({"error": "Game session not found"}), 404

    # Validate player is human (crude check based on PLAYER_IDS[0] being human)
    if requesting_player_id != PLAYER_IDS[0]: # Assumes PLAYER_IDS[0] is "Human_Player_1"
         current_app.logger.warning(f"S{session_id}: Non-human player {requesting_player_id} attempted to use human_submit_answer.")
         return jsonify({"error": "Only human players can use this endpoint."}), 403

    if game_session.game_state != 'active' and not (game_session.game_mode == 'steal_attempt' and game_session.player_who_can_steal == requesting_player_id) :
        current_app.logger.warning(f"Human answer S{session_id}: Game not in state to accept human answer (state: {game_session.game_state}, mode: {game_session.game_mode}).")
        return jsonify({"error": "Game is not in a state to accept your answer."}), 400

    if game_session.current_player_id != requesting_player_id:
        current_app.logger.warning(f"Human answer S{session_id}: Turn validation failed. Requested by: {requesting_player_id}, Current: {game_session.current_player_id}")
        return jsonify({"error": f"It's {game_session.current_player_id}'s turn, not yours."}), 400

    current_question = game_session.current_question
    if not current_question:
        current_app.logger.error(f"Human answer S{session_id}: No current_question found.")
        return jsonify({"error": "Current question not found for this session"}), 500

    answer_correct = (submitted_answer == current_question.correct_answer)

    # Simplified strike/steal logic for human - can be expanded later
    # This is mostly copied from AI block and needs careful review/adaptation for full Human vs AI game flow
    # For PoC, let's assume it's similar to AI's turn processing for now.

    session_player_ids = list(game_session.scores.keys()) # These are "Human_Player_1", "AI_Opponent_1"
    current_player_id = game_session.current_player_id # This is the human player

    advance_question = False
    next_player_id_for_response = ""

    if game_session.game_mode == 'active':
        if answer_correct:
            game_session.scores[current_player_id] = game_session.scores.get(current_player_id, 0) + POINTS_PER_QUESTION
            flag_modified(game_session, "scores")
            game_session.current_question_strikes = 0
            game_session.player_who_can_steal = None
            current_player_index = session_player_ids.index(current_player_id)
            next_player_id_for_response = session_player_ids[(current_player_index + 1) % len(session_player_ids)]
            game_session.current_player_id = next_player_id_for_response
            advance_question = True
            current_app.logger.info(f"S{session_id} Human P{current_player_id} Q{current_question.id} Correct. Points: {POINTS_PER_QUESTION}. Strikes reset.")
        else:
            game_session.current_question_strikes += 1
            current_app.logger.info(f'S{session_id} Human P{current_player_id} received strike {game_session.current_question_strikes} on Q{current_question.id}.')
            if game_session.current_question_strikes >= MAX_STRIKES:
                game_session.game_mode = 'steal_attempt'
                current_app.logger.info(f'S{session_id} Game mode set to: {game_session.game_mode}.')
                other_player_index = (session_player_ids.index(current_player_id) + 1) % len(session_player_ids)
                game_session.player_who_can_steal = session_player_ids[other_player_index]
                current_app.logger.info(f'S{session_id} Human P{current_player_id} struck out on Q{current_question.id}. Steal by {game_session.player_who_can_steal}.')
                game_session.current_player_id = game_session.player_who_can_steal
                advance_question = False
            else:
                game_session.current_player_id = current_player_id
                advance_question = False

    elif game_session.game_mode == 'steal_attempt': # Human is stealing
        current_app.logger.info(f'S{session_id} Human P{requesting_player_id} attempting steal for Q{current_question.id}. Submitted: {submitted_answer}. Correct: {answer_correct}.')
        if answer_correct:
            game_session.scores[current_player_id] = game_session.scores.get(current_player_id, 0) + POINTS_PER_QUESTION
            flag_modified(game_session, "scores")
        game_session.game_mode = 'active'
        current_app.logger.info(f'S{session_id} Game mode set to: {game_session.game_mode}.')
        game_session.current_question_strikes = 0
        game_session.player_who_can_steal = None
        current_player_index = session_player_ids.index(current_player_id)
        next_player_id_for_response = session_player_ids[(current_player_index + 1) % len(session_player_ids)]
        game_session.current_player_id = next_player_id_for_response
        advance_question = True

    # --- Round, Game Completion, Next Question (if advance_question) ---
    next_question_id_for_response = None
    next_question_text_for_response = None
    next_question_answer_choices_for_response = None

    if advance_question:
        game_session.current_round += 1
        # (Game completion logic as in AI answer block) ...
        if game_session.current_round >= MAX_ROUNDS: # MAX_ROUNDS defined globally
            game_session.game_state = 'finished'
            # ... (set end_time, log)
        else:
            # ... (fetch new question, set next_question_..._for_response vars)
             with current_app.test_client() as client:
                random_question_response = client.get('/api/questions/random')
                if random_question_response.status_code == 200:
                    next_question_data = random_question_response.get_json()
                    if next_question_data and 'id' in next_question_data:
                        game_session.current_question_id = next_question_data['id']
                        next_question_id_for_response = game_session.current_question_id
                        next_question_text_for_response = next_question_data.get("text")
                        next_question_answer_choices_for_response = next_question_data.get("answer_choices")
                    else: # Error handling if next_question_data is bad
                        current_app.logger.error(f"S{session_id} Human Turn: Invalid data for next question.")
                        # Potentially end game or handle error state
                else: # Error handling if random question fetch fails
                    current_app.logger.error(f"S{session_id} Human Turn: Failed to get next question.")
                    # Potentially end game
    else: # Same question continues
        next_question_id_for_response = game_session.current_question_id
        next_question_text_for_response = current_question.text
        next_question_answer_choices_for_response = current_question.answer_choices

    current_app.logger.info(f"S{session_id} Human Turn End. Next Player: {game_session.current_player_id}, Q_to_be_played: {game_session.current_question_id}, Mode: {game_session.game_mode}, Strikes: {game_session.current_question_strikes}")
    db.session.commit()

    player_details_response = {
        p_id: {"score": game_session.scores.get(p_id, 0),
               "avatar_url": PLAYER_AVATARS.get("AI_Player_1") if "Human" in p_id else PLAYER_AVATARS.get("AI_Player_2"), # Simplified avatar
               "type": "HUMAN" if "Human" in p_id else "AI"}
        for p_id in session_player_ids
    }

    response_data = {
        "session_id": game_session.id, "answer_result": "correct" if answer_correct else "incorrect",
        "submitted_answer": submitted_answer, "player_details": player_details_response,
        "current_player_id": game_session.current_player_id, "game_state": game_session.game_mode,
        "current_round": game_session.current_round, "current_question_strikes": game_session.current_question_strikes,
        "player_who_can_steal": game_session.player_who_can_steal
    }
    # ... (add next_question details or game_over message to response_data as in AI answer) ...
    if game_session.game_mode == 'active' and advance_question:
        response_data["next_question_id"] = next_question_id_for_response
        response_data["next_question_text"] = next_question_text_for_response
        response_data["next_question_answer_choices"] = next_question_answer_choices_for_response
    elif game_session.game_mode == 'steal_attempt': # Current question is the steal question
        response_data["current_question_id"] = game_session.current_question_id
        response_data["current_question_text"] = current_question.text
        response_data["current_question_answer_choices"] = current_question.answer_choices
    elif game_session.game_mode == 'finished':
        response_data["message"] = "Game Over! Final scores are above."

    return jsonify(response_data)

@bp.route('/game/<int:session_id>/status', methods=['GET'])
def game_session_status(session_id):
    game_session = db.session.get(GameSession, session_id)
    if not game_session:
        return jsonify({"error": "Game session not found"}), 404

    # Construct player_details for the response
    player_details_response = {
        p_id: {"score": game_session.scores.get(p_id, 0), "avatar_url": PLAYER_AVATARS.get(p_id)}
        for p_id in PLAYER_IDS
    }

    response_data = {
        "id": game_session.id,
        "session_name": game_session.session_name,
        "player_details": player_details_response, # Use new structure
        "current_player_id": game_session.current_player_id,
        "current_question_id": game_session.current_question_id,
        "game_state": game_session.game_mode, # Use game_mode
        "start_time": game_session.start_time.isoformat(),
        "current_round": game_session.current_round,
        "current_question_strikes": game_session.current_question_strikes, # Add this
        "player_who_can_steal": game_session.player_who_can_steal, # Add this
        "end_time": game_session.end_time.isoformat() if game_session.end_time else None,
    }
    if game_session.current_question and game_session.game_mode != 'finished':
        response_data["current_question_text"] = game_session.current_question.text
        response_data["current_question_answer_choices"] = game_session.current_question.answer_choices

    return jsonify(response_data)

# --- Audience Voting Endpoints ---

# --- WebSocket Signaling ---
# This list will store connected WebSocket clients.
# WARNING: This is a simple in-memory list and will not work correctly if you have multiple
# server processes or workers (e.g., when using gunicorn with more than one worker).
# For a PoC with Flask's dev server (usually single process), it's okay.
connected_clients = []

@sockets.route('/ws/signaling')
def signaling_socket(ws):
    current_app.logger.info(f"WebSocket client connected: {ws}")
    connected_clients.append(ws)
    try:
        while not ws.closed:
            message = ws.receive()
            if message:
                current_app.logger.info(f"WS Received: {message[:100]}...")
                # Broadcast to other clients
                for client in connected_clients:
                    if client != ws and not client.closed:
                        try:
                            client.send(message)
                        except Exception as e:
                            current_app.logger.error(f"Error sending WS message to client {client}: {e}")
    except Exception as e:
        current_app.logger.error(f"Error in WebSocket handler for {ws}: {e}")
    finally:
        current_app.logger.info(f"WebSocket client disconnected: {ws}")
        if ws in connected_clients:
            connected_clients.remove(ws)

@bp.route('/game/<int:session_id>/question/<int:question_id>/vote', methods=['POST'])
def record_audience_vote(session_id, question_id):
    data = request.get_json()
    if not data or 'selected_choice' not in data:
        current_app.logger.warning(f"Audience vote S{session_id}/Q{question_id}: Missing 'selected_choice'.")
        return jsonify({"error": "Missing selected_choice in request body"}), 400

    selected_choice = data['selected_choice']

    game_session = db.session.get(GameSession, session_id) # Using .get() is fine for PK lookup
    if not game_session:
        current_app.logger.warning(f"Audience vote S{session_id}/Q{question_id}: Game session not found.")
        return jsonify({"error": "Game session not found"}), 404
    question = db.session.get(Question, question_id)
    if not question:
        current_app.logger.warning(f"Audience vote S{session_id}/Q{question_id}: Question not found.")
        return jsonify({"error": "Question not found"}), 404

    try:
        vote = AudienceVote(
            game_session_id=session_id,
            question_id=question_id,
            selected_choice=selected_choice
        )
        db.session.add(vote)
        db.session.commit()
        current_app.logger.info(f'Vote recorded for Q{question_id} in S{session_id}: choice {selected_choice}, Vote ID {vote.id}')
        return jsonify({"message": "Vote recorded", "vote_id": vote.id}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error recording vote S{session_id}/Q{question_id}: {str(e)}")
        return jsonify({"error": "Internal server error while recording vote."}), 500

@bp.route('/game/<int:session_id>/question/<int:question_id>/results', methods=['GET'])
def get_vote_results(session_id, question_id):
    game_session = db.session.get(GameSession, session_id)
    if not game_session:
        current_app.logger.warning(f"Vote results S{session_id}/Q{question_id}: Game session not found.")
        return jsonify({"error": "Game session not found"}), 404
    question = db.session.get(Question, question_id)
    if not question:
        current_app.logger.warning(f"Vote results S{session_id}/Q{question_id}: Question not found.")
        return jsonify({"error": "Question not found"}), 404

    try:
        votes = AudienceVote.query.filter_by(
            game_session_id=session_id,
            question_id=question_id
        ).all()

        if not votes:
            current_app.logger.info(f"No votes yet for Q{question_id} in S{session_id}.")
            return jsonify({"message": "No votes yet for this question.", "results": {}}), 200

        vote_counts = {}
        for vote in votes:
            vote_counts[vote.selected_choice] = vote_counts.get(vote.selected_choice, 0) + 1

        total_votes = len(votes)
        vote_percentages = {
            choice: round((count / total_votes) * 100, 1)
            for choice, count in vote_counts.items()
        }
        current_app.logger.info(f"Retrieved vote results for Q{question_id} S{session_id}: {total_votes} total votes.")
        return jsonify({
            "question_id": question_id,
            "total_votes": total_votes,
            "results_raw_counts": vote_counts,
            "results_percentages": vote_percentages
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error retrieving vote results S{session_id}/Q{question_id}: {str(e)}")
        return jsonify({"error": "Internal server error while retrieving results."}), 500


@bp.route('/game/<int:session_id>/stop', methods=['POST'])
def stop_game_session(session_id):
    game_session = db.session.get(GameSession, session_id)
    if not game_session:
        current_app.logger.warning(f"Stop game: Session {session_id} not found.")
        return jsonify({"error": "Game session not found"}), 404

    if game_session.game_state != 'active':
        current_app.logger.warning(f"Stop game: Session {session_id} is not active (state: {game_session.game_state}).")
        return jsonify({"error": "Game is not currently active, cannot stop."}), 400

    try:
        game_session.game_state = 'finished'
        game_session.end_time = datetime.utcnow()
        db.session.commit()
        current_app.logger.info(f'Game stopped: session ID {session_id}')

        # Construct player_details for the response, similar to game_session_status
        player_details_response = {
            p_id: {"score": game_session.scores.get(p_id, 0), "avatar_url": PLAYER_AVATARS.get(p_id)}
            for p_id in PLAYER_IDS
        }
        response_data = {
            "id": game_session.id,
            "session_name": game_session.session_name,
            "player_details": player_details_response,
            "current_player_id": game_session.current_player_id,
            "current_question_id": game_session.current_question_id,
            "game_state": game_session.game_state,
            "start_time": game_session.start_time.isoformat(),
            "current_round": game_session.current_round,
            "end_time": game_session.end_time.isoformat() if game_session.end_time else None,
            "message": "Game session stopped by host."
        }
        if game_session.current_question:
            response_data["current_question_text"] = game_session.current_question.text

        return jsonify(response_data), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error stopping game session {session_id}: {str(e)}")
        return jsonify({"error": "Internal server error while stopping game session."}), 500
