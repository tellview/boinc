from flask import current_app
from sqlalchemy.orm.attributes import flag_modified # Needed if game_session.scores is JSON/mutable

# These constants would ideally be part of a shared configuration or passed explicitly.
# For now, defining them here as per the subtask description for this refactoring step.
PLAYER_IDS = ["Human_Player_1", "AI_Opponent_1"]
POINTS_PER_QUESTION = 10
MAX_STRIKES = 3
# MAX_ROUNDS is used by routes when advancing questions, not directly in this function's core logic.

def process_player_answer(game_session, current_player_id, submitted_answer_text, current_question):
    """
    Processes a player's answer, updates game_session state (scores, strikes, game_mode, current_player_id for next turn).
    Modifies game_session object directly.

    Args:
        game_session: The SQLAlchemy GameSession object.
        current_player_id: The ID of the player whose answer is being processed.
        submitted_answer_text: The textual answer submitted.
        current_question: The SQLAlchemy Question object for the current question.

    Returns:
        bool: advance_question (True if a new question should be fetched, False otherwise).
    """
    current_app.logger.debug(f"Processing answer for S{game_session.id}, P{current_player_id}, Q{current_question.id}, Answer='{submitted_answer_text}'")

    answer_correct = (submitted_answer_text.strip().lower() == current_question.correct_answer.strip().lower())

    # Ensure scores is a mutable dictionary
    # If game_session.scores is already a Python dict from JSON, this makes a copy to modify.
    # If it's None, initialize it.
    player_scores = dict(game_session.scores or {})

    advance_question = False
    # next_player_id will be set based on logic; game_session.current_player_id will be updated to this.

    if game_session.game_mode == 'active':
        if answer_correct:
            player_scores[current_player_id] = player_scores.get(current_player_id, 0) + POINTS_PER_QUESTION
            game_session.current_question_strikes = 0
            game_session.player_who_can_steal = None
            advance_question = True

            current_player_index = PLAYER_IDS.index(current_player_id)
            game_session.current_player_id = PLAYER_IDS[(current_player_index + 1) % len(PLAYER_IDS)]
            current_app.logger.info(f"S{game_session.id} P{current_player_id} Q{current_question.id} Correct. Score: {player_scores[current_player_id]}. Strikes reset. Next player: {game_session.current_player_id}")
        else: # Incorrect answer in 'active' mode
            game_session.current_question_strikes += 1
            current_app.logger.info(f'S{game_session.id} P{current_player_id} received strike {game_session.current_question_strikes} on Q{current_question.id}.')
            if game_session.current_question_strikes >= MAX_STRIKES:
                game_session.game_mode = 'steal_attempt'
                current_app.logger.info(f'S{game_session.id} Game mode set to: {game_session.game_mode}.')

                other_player_index = (PLAYER_IDS.index(current_player_id) + 1) % len(PLAYER_IDS)
                game_session.player_who_can_steal = PLAYER_IDS[other_player_index]
                game_session.current_player_id = game_session.player_who_can_steal # Turn passes to stealer
                advance_question = False # Same question for steal
                current_app.logger.info(f'S{game_session.id} P{current_player_id} struck out on Q{current_question.id}. Steal opportunity for {game_session.player_who_can_steal}.')
            else: # Strikes < MAX_STRIKES: current player continues on same question
                game_session.current_player_id = current_player_id
                advance_question = False

    elif game_session.game_mode == 'steal_attempt':
        # current_player_id is the one attempting the steal.
        # The route handler should have validated that this player_id is indeed game_session.player_who_can_steal.
        log_prefix = f"S{game_session.id} P{current_player_id} (Steal Attempt) Q{current_question.id}"
        current_app.logger.info(f"{log_prefix} Submitted: '{submitted_answer_text}'. Correct: {answer_correct}.")

        if answer_correct:
            player_scores[current_player_id] = player_scores.get(current_player_id, 0) + POINTS_PER_QUESTION
            current_app.logger.info(f"{log_prefix} Steal SUCCESSFUL. Score: {player_scores[current_player_id]}.")
        else:
            current_app.logger.info(f"{log_prefix} Steal FAILED.")

        game_session.game_mode = 'active' # Reset game mode regardless of steal success/failure
        current_app.logger.info(f'S{game_session.id} Game mode reset to: {game_session.game_mode}.')
        game_session.current_question_strikes = 0
        game_session.player_who_can_steal = None
        advance_question = True

        # Determine next player (player after the one who attempted steal)
        current_player_index = PLAYER_IDS.index(current_player_id)
        game_session.current_player_id = PLAYER_IDS[(current_player_index + 1) % len(PLAYER_IDS)]

    # Assign the potentially modified scores back to the session object.
    # SQLAlchemy's ORM should detect this assignment as a change if player_scores is different.
    game_session.scores = player_scores
    # If game_session.scores was modified in-place (which it is, via player_scores referencing it then being updated),
    # and it's a mutable JSON type, flag it.
    # This is especially important if player_scores was not a new dict but a reference.
    # player_scores = dict(game_session.scores or {}) makes it a copy, so assignment is key.
    # However, if a score was ADDED (new player) or CHANGED, flag_modified is safest for JSON.
    if answer_correct: # Only flag if score actually changed or could have changed
        flag_modified(game_session, "scores")

    # The calling route will handle db.session.commit()
    # The calling route will also handle fetching new question if advance_question is True
    return advance_question
