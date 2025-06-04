document.addEventListener('DOMContentLoaded', () => {
    const startGameBtn = document.getElementById('startGameBtn');
    const submitAnswerBtn = document.getElementById('submitAnswerBtn');
    const playerAnswerInput = document.getElementById('playerAnswer');

    const gameSessionIdDisplay = document.getElementById('gameSessionId');
    const currentPlayerIdDisplay = document.getElementById('currentPlayerId');
    const player1ScoreDisplay = document.getElementById('player1Score');
    const player2ScoreDisplay = document.getElementById('player2Score');
    const lastAnswerResultDisplay = document.getElementById('lastAnswerResult');
    const currentQuestionTextDisplay = document.getElementById('currentQuestionText');
    const aiAnswerDisplay = document.getElementById('aiAnswer'); // New display for AI's answer

    let currentGameSessionId = null;
    let currentPlayerId = null; // This will be set by the backend

    function updateDisplay(gameState) {
        if (!gameState) return;

        if (gameState.id) {
            gameSessionIdDisplay.textContent = gameState.id;
            currentGameSessionId = gameState.id; // Store for submitAnswer
        }
        if (gameState.current_player_id) {
            currentPlayerIdDisplay.textContent = gameState.current_player_id;
            currentPlayerId = gameState.current_player_id; // Store for submitAnswer
        }
        if (gameState.scores) {
            player1ScoreDisplay.textContent = gameState.scores.AI_Player_1 || 0;
            player2ScoreDisplay.textContent = gameState.scores.AI_Player_2 || 0;
        }
        if (gameState.answer_result) {
            lastAnswerResultDisplay.textContent = gameState.answer_result;
        } else {
            lastAnswerResultDisplay.textContent = "-";
        }

        if (gameState.suggested_answer) {
            aiAnswerDisplay.textContent = gameState.suggested_answer;
        } else {
            aiAnswerDisplay.textContent = "-";
        }

        if (gameState.current_question_text) { // On game start
            currentQuestionTextDisplay.textContent = gameState.current_question_text;
        } else if (gameState.next_question_text) { // After submitting an answer
            currentQuestionTextDisplay.textContent = gameState.next_question_text;
        } else if (gameState.game_state !== 'finished') {
            currentQuestionTextDisplay.textContent = "Waiting for question...";
        }

        if (gameState.game_state === 'finished') {
            currentQuestionTextDisplay.textContent = gameState.message || `Game Over! Final Scores: Player 1: ${gameState.scores.AI_Player_1}, Player 2: ${gameState.scores.AI_Player_2}`;
            submitAnswerBtn.disabled = true;
            // playerAnswerInput is already disabled, but good to ensure
            if(playerAnswerInput) playerAnswerInput.disabled = true;
        } else {
            submitAnswerBtn.disabled = false;
            if(playerAnswerInput) playerAnswerInput.disabled = true; // Keep it disabled as AI answers
        }
    }

    async function startGame() {
        try {
            const response = await fetch('/api/game/start', { method: 'POST' });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const gameState = await response.json();
            updateDisplay(gameState);
            lastAnswerResultDisplay.textContent = "New game started!";
        } catch (error) {
            console.error('Error starting game:', error);
            currentQuestionTextDisplay.textContent = `Error starting game: ${error.message}`;
        }
    }

    async function submitAnswer() {
        if (!currentGameSessionId || !currentPlayerId) {
            alert("Please start a game first!");
            return;
        }

        // const answer = playerAnswerInput.value.trim(); // AI answers now, no need to get from input
        // if (!answer) {
        //     alert("Please enter an answer.");
        //     return;
        // }

        try {
            // AI's turn is processed on the backend, just send current player for validation
            const response = await fetch(`/api/game/${currentGameSessionId}/answer`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    player_id: currentPlayerId
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const newGameState = await response.json();
            updateDisplay(newGameState);
            // playerAnswerInput.value = ''; // No longer needed
        } catch (error) {
            console.error('Error processing AI turn:', error);
            lastAnswerResultDisplay.textContent = `Error: ${error.message}`;
        }
    }

    startGameBtn.addEventListener('click', startGame);
    submitAnswerBtn.addEventListener('click', submitAnswer);
});
