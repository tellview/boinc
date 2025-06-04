document.addEventListener('DOMContentLoaded', () => {
    const startGameBtn = document.getElementById('startGameBtn');
    const submitAnswerBtn = document.getElementById('submitAnswerBtn');
    const stopGameBtn = document.getElementById('stopGameBtn');
    const toggleVoiceCtrlBtn = document.getElementById('toggleVoiceCtrlBtn');
    const voiceStatusDisplay = document.getElementById('voiceStatus');

    // const playerAnswerInput = document.getElementById('playerAnswer');

    // General game info displays
    const gameSessionIdDisplay = document.getElementById('gameSessionId');
    const currentPlayerTurnDisplay = document.getElementById('currentPlayerId'); // Renamed for clarity
    const lastAnswerResultDisplay = document.getElementById('lastAnswerResult');
    const aiAnswerDisplay = document.getElementById('aiAnswer');
    const currentQuestionTextDisplay = document.getElementById('currentQuestionText');
    const audienceChoicesDiv = document.getElementById('audience-choices');
    const audienceResultsDiv = document.getElementById('audience-results');

    // Player cell specific elements
    // ... (playerInfoConfig remains the same)
    const playerCells = [ // This might not be directly used if playerInfoConfig is comprehensive
        document.getElementById('player-cell-0'),
        document.getElementById('player-cell-1')
    ];
    // Assuming player IDs "AI_Player_1" and "AI_Player_2"
    const playerInfoConfig = {
        "AI_Player_1": {
            scoreDisplayId: 'player-0-score',
            cellId: 'player-cell-0',
            avatarId: 'avatar-0',
            strikesDisplayId: 'player-0-strikes' // New
        },
        "AI_Player_2": {
            scoreDisplayId: 'player-1-score',
            cellId: 'player-cell-1',
            avatarId: 'avatar-1',
            strikesDisplayId: 'player-1-strikes' // New
        }
    };

    let currentGameSessionId = null;
    let currentPlayerId = null;
    let currentQuestionIdForVoting = null; // Store current question ID for voting

    // --- Text-to-Speech Function ---
    function speakText(text) {
        if ('speechSynthesis' in window) {
            // Optional: Clean up text for speech, e.g., remove mock suffixes
            let cleanText = text;
            const suffixes_to_strip = [" (keyword match)", " (random choice)", " (hinted in question)"];
            for (const suffix of suffixes_to_strip) {
                if (cleanText.endsWith(suffix)) {
                    cleanText = cleanText.substring(0, cleanText.length - suffix.length);
                    break;
                }
            }

            const utterance = new SpeechSynthesisUtterance(cleanText);
            // Optional: Configure voice, rate, pitch
            // const voices = window.speechSynthesis.getVoices();
            // if (voices.length > 0) {
            //     utterance.voice = voices[0]; // Example: use the first available voice
            // }
            // utterance.pitch = 1; // Range between 0 (lowest) and 2 (highest)
            // utterance.rate = 1; // Range between 0.1 (slowest) and 10 (fastest)
            // utterance.volume = 1; // Range between 0 (lowest) and 1 (highest)

            window.speechSynthesis.speak(utterance);
        } else {
            console.error("Speech synthesis not supported in this browser.");
            // Optionally, provide a fallback or notify the user via UI
        }
    }

    function updateDisplay(gameState) {
        if (!gameState) return;

        // Update general game info
        if (gameState.id) {
            gameSessionIdDisplay.textContent = gameState.id;
            currentGameSessionId = gameState.id;
        }
        if (gameState.current_player_id) {
            currentPlayerTurnDisplay.textContent = gameState.current_player_id;
            currentPlayerId = gameState.current_player_id;
        }
        if (gameState.answer_result) {
            lastAnswerResultDisplay.textContent = gameState.answer_result;
        } else {
            lastAnswerResultDisplay.textContent = "-"; // Clear on new game
        }
        if (gameState.suggested_answer) {
            aiAnswerDisplay.textContent = gameState.suggested_answer;
            // Speak the AI's answer (after displaying it)
            // The backend response for 'suggested_answer' includes the suffix,
            // speakText will clean it.
            speakText(gameState.suggested_answer);
        } else {
            aiAnswerDisplay.textContent = "-"; // Clear on new game
        }

        // Update player-specific info (scores and avatars)
        if (gameState.player_details) {
            for (const playerId in gameState.player_details) {
                if (playerInfoConfig[playerId]) {
                    const config = playerInfoConfig[playerId];
                    const playerDetail = gameState.player_details[playerId];

                    const scoreDisplay = document.getElementById(config.scoreDisplayId);
                    if (scoreDisplay) {
                        scoreDisplay.textContent = playerDetail.score;
                    }

                    const avatarDiv = document.getElementById(config.avatarId);
                    if (avatarDiv && playerDetail.avatar_url) {
                        // Replace placeholder text/content with an img tag
                        avatarDiv.innerHTML = `<img src="${playerDetail.avatar_url}" alt="${playerId} Avatar" style="width:100%;height:100%;border-radius:50%;">`;
                    }
                }
            }
        }

        // Highlight active player cell
        for (const playerId in playerInfoConfig) {
            const config = playerInfoConfig[playerId];
            const cell = document.getElementById(config.cellId);
            if (cell) {
                 if (playerId === gameState.current_player_id) {
                    cell.classList.add('active-player-cell');
                } else {
                    cell.classList.remove('active-player-cell');
                }
            }
        }

        // Update strikes display
        const numStrikes = gameState.current_question_strikes || 0;

        // Clear all strikes first
        for (const pId of PLAYER_IDS) { // Use PLAYER_IDS to ensure both are cleared
            if (playerInfoConfig[pId]) {
                const strikesDisplay = document.getElementById(playerInfoConfig[pId].strikesDisplayId);
                if (strikesDisplay) strikesDisplay.textContent = '';
            }
        }

        if (gameState.game_mode === 'active') {
            // Strikes are for the current_player_id if they are continuing on the same question (strikes > 0),
            // or 0 if it's a new question for them (after opponent's turn or successful answer).
            if (playerInfoConfig[gameState.current_player_id]) {
                 const strikesDisplay = document.getElementById(playerInfoConfig[gameState.current_player_id].strikesDisplayId);
                 if (strikesDisplay) {
                    strikesDisplay.textContent = 'X '.repeat(numStrikes);
                 }
            }
        } else if (gameState.game_mode === 'steal_attempt') {
            // Strikes (should be MAX_STRIKES) belong to the player who is NOT player_who_can_steal.
            // The current_player_id is the player_who_can_steal.
            const playerWhoStruckOut = PLAYER_IDS.find(id => id !== gameState.player_who_can_steal);
            if (playerWhoStruckOut && playerInfoConfig[playerWhoStruckOut]) {
                const strikesDisplay = document.getElementById(playerInfoConfig[playerWhoStruckOut].strikesDisplayId);
                if (strikesDisplay) {
                    strikesDisplay.textContent = 'X '.repeat(numStrikes); // Should be MAX_STRIKES
                }
            }
            // The player attempting the steal has 0 strikes for this current attempt on this question.
            if (playerInfoConfig[gameState.player_who_can_steal]) {
                const stealerStrikesDisplay = document.getElementById(playerInfoConfig[gameState.player_who_can_steal].strikesDisplayId);
                if (stealerStrikesDisplay) stealerStrikesDisplay.textContent = ''; // Or "0" for clarity
            }
        }

        // Update question text
        if (gameState.current_question_text) { // On game start
            currentQuestionTextDisplay.textContent = gameState.current_question_text;
            currentQuestionIdForVoting = gameState.current_question_id; // Capture QID for voting
            renderVotingOptions(gameState.current_question_id, gameState.current_question_answer_choices); // Render new vote options
        } else if (gameState.next_question_text) { // After submitting an answer (new question presented)
            currentQuestionTextDisplay.textContent = gameState.next_question_text;
            currentQuestionIdForVoting = gameState.next_question_id; // Capture QID for voting
            renderVotingOptions(gameState.next_question_id, gameState.next_question_answer_choices); // Render new vote options
        } else if (gameState.game_state !== 'finished') {
            currentQuestionTextDisplay.textContent = "Waiting for question...";
            clearVotingArea();
        }

        // Handle game state (finished or active)
        if (gameState.game_state === 'finished' || gameState.game_state === 'stopped_by_host') { // Check for stopped_by_host if backend uses it
            const scores = gameState.player_details || {};
            const p1Score = scores.AI_Player_1 ? scores.AI_Player_1.score : 0;
            const p2Score = scores.AI_Player_2 ? scores.AI_Player_2.score : 0;
            currentQuestionTextDisplay.textContent = gameState.message || `Game Over! Final Scores: AI_Player_1: ${p1Score}, AI_Player_2: ${p2Score}`;
            submitAnswerBtn.disabled = true;
            if (stopGameBtn) stopGameBtn.disabled = true;
            aiAnswerDisplay.textContent = gameState.message || "Game Finished!";
            clearVotingArea(); // Clear voting on game end
        } else {
            submitAnswerBtn.disabled = false;
            if (stopGameBtn) stopGameBtn.disabled = false;
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
    if (stopGameBtn) stopGameBtn.addEventListener('click', stopGame);

    // --- WebRTC PoC Variables and Elements ---
    let localStream;
    let pc1; // PeerConnection 1 (local participant)
    let pc2; // PeerConnection 2 (simulated remote participant)

    const localVideo = document.getElementById('localVideo');
    const startWebcamBtn = document.getElementById('startWebcamBtn');
    const connectPeerBtn = document.getElementById('connectPeerBtn');
    const signalingMessagesTextarea = document.getElementById('signalingMessages');

    function logSignaling(message) {
        console.log(message);
        signalingMessagesTextarea.value += message + '\n\n';
        signalingMessagesTextarea.scrollTop = signalingMessagesTextarea.scrollHeight; // Auto-scroll
    }

    function logError(error) {
        const message = `Error: ${error.name || 'Unknown Error'} - ${error.message || error}`;
        console.error(message, error);
        signalingMessagesTextarea.value += message + '\n\n';
        signalingMessagesTextarea.scrollTop = signalingMessagesTextarea.scrollHeight;
    }

    async function startWebcam() {
        logSignaling("Requesting local media...");
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            logSignaling("Local media obtained.");
            localVideo.srcObject = stream;
            localStream = stream;
            if (connectPeerBtn) connectPeerBtn.disabled = false;
            if (startWebcamBtn) startWebcamBtn.disabled = true; // Disable after starting
        } catch (e) {
            logError(e);
        }
    }

    async function connectPeers() {
        if (!localStream) {
            logError(new Error("Local stream not available. Please start webcam first."));
            return;
        }
        logSignaling("Starting peer connection process...");
        if (connectPeerBtn) connectPeerBtn.disabled = true; // Disable during connection setup

        // For this PoC, pc1 is local, pc2 simulates remote peer on same page
        const configuration = null; // No STUN/TURN servers for this local PoC

        pc1 = new RTCPeerConnection(configuration);
        logSignaling("PC1 created");
        pc1.onicecandidate = e => {
            if (e.candidate) {
                logSignaling(`PC1 ICE Candidate: ${e.candidate.candidate.substring(0,50)}...`); // Log part of candidate
                if (pc2 && pc2.signalingState !== 'closed') {
                     pc2.addIceCandidate(e.candidate).catch(logError);
                }
            }
        };
        pc1.oniceconnectionstatechange = e => logSignaling(`PC1 ICE State: ${pc1.iceConnectionState}`);


        pc2 = new RTCPeerConnection(configuration);
        logSignaling("PC2 created");
        pc2.onicecandidate = e => {
            if (e.candidate) {
                logSignaling(`PC2 ICE Candidate: ${e.candidate.candidate.substring(0,50)}...`);
                 if (pc1 && pc1.signalingState !== 'closed') {
                    pc1.addIceCandidate(e.candidate).catch(logError);
                }
            }
        };
        pc2.oniceconnectionstatechange = e => logSignaling(`PC2 ICE State: ${pc2.iceConnectionState}`);
        pc2.ontrack = e => {
            logSignaling("PC2 received remote track! (Simulated - would attach to a remote video element)");
            // In a real app: remoteVideo.srcObject = e.streams[0];
        };

        // Add local stream tracks to pc1
        localStream.getTracks().forEach(track => {
            logSignaling(`Adding track ${track.kind} to PC1`);
            pc1.addTrack(track, localStream);
        });

        try {
            logSignaling("PC1 creating offer...");
            const offer = await pc1.createOffer();
            await pc1.setLocalDescription(offer);
            logSignaling(`PC1 Offer SDP set. Signaling to PC2.`);
            // logSignaling(`PC1 Offer SDP: ${JSON.stringify(pc1.localDescription)}`);


            await pc2.setRemoteDescription(pc1.localDescription);
            logSignaling(`PC2 Remote Description (Offer from PC1) set.`);

            logSignaling("PC2 creating answer...");
            const answer = await pc2.createAnswer();
            await pc2.setLocalDescription(answer);
            logSignaling(`PC2 Answer SDP set. Signaling to PC1.`);
            // logSignaling(`PC2 Answer SDP: ${JSON.stringify(pc2.localDescription)}`);

            await pc1.setRemoteDescription(pc2.localDescription);
            logSignaling(`PC1 Remote Description (Answer from PC2) set. Connection should establish.`);

        } catch (e) {
            logError(e);
        }
    }

    if (startWebcamBtn) startWebcamBtn.addEventListener('click', startWebcam);
    if (connectPeerBtn) connectPeerBtn.addEventListener('click', connectPeers);


    // --- Speech Recognition Setup ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition;
    let voiceControlEnabled = false;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false; // Process one command at a time
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        toggleVoiceCtrlBtn.addEventListener('click', () => {
            if (voiceControlEnabled) {
                recognition.stop(); // User explicitly disables
                voiceControlEnabled = false;
                // onend will handle button text and status update
            } else {
                try {
                    recognition.start();
                    // voiceControlEnabled will be set true in onstart or here directly
                    // voiceStatusDisplay.textContent = "Listening..."; // onstart is better
                    // toggleVoiceCtrlBtn.textContent = "Disable Voice Commands";
                    // toggleVoiceCtrlBtn.classList.add('voice-enabled');
                } catch(e) {
                    // Could be if already started
                    console.error("Error trying to start recognition (possibly already started):", e);
                    voiceStatusDisplay.textContent = "Voice recognition already active or error starting.";
                     // Reset state if it failed to start properly
                    voiceControlEnabled = false;
                    toggleVoiceCtrlBtn.textContent = "Enable Voice Commands";
                    toggleVoiceCtrlBtn.classList.remove('voice-enabled');
                }
            }
        });

        recognition.onstart = () => {
            voiceControlEnabled = true;
            voiceStatusDisplay.textContent = "Voice control active. Listening...";
            toggleVoiceCtrlBtn.textContent = "Disable Voice Commands";
            toggleVoiceCtrlBtn.classList.add('voice-enabled');
        };

        recognition.onresult = (event) => {
            const command = event.results[0][0].transcript.toLowerCase().trim();
            console.log('Voice command received:', command);
            voiceStatusDisplay.textContent = 'Heard: "' + command + '". Processing...';

            if (command.includes('start game')) {
                startGameBtn.click();
            } else if (command.includes('next turn') || command.includes('process turn') || command.includes('submit answer')) {
                submitAnswerBtn.click();
            } else if (command.includes('stop game')) {
                stopGameBtn.click();
            } else {
                voiceStatusDisplay.textContent = 'Unknown command: "' + command + '". Try "start game", "next turn", or "stop game".';
            }
            // After processing a command, it will stop due to continuous=false
            // onend will then be called.
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            voiceStatusDisplay.textContent = 'Voice recognition error: ' + event.error;
            if (event.error === 'not-allowed' || event.error === 'audio-capture') {
                // Permissions issue or mic problem, disable voice control permanently for this session
                toggleVoiceCtrlBtn.disabled = true;
                voiceStatusDisplay.textContent = "Voice recognition permission denied or microphone error. Please check browser settings.";
            }
            voiceControlEnabled = false; // Ensure state is reset
             // onend will handle button text and class if it's called after error
        };

        recognition.onend = () => {
            if (voiceControlEnabled) {
                // This means it stopped naturally after one command, or due to an error not covered by onerror's specific handling
                // If we want continuous listening after each command (without continuous = true), we'd restart here.
                // For now, user must re-enable.
                voiceStatusDisplay.textContent = "Voice listening ended. Click 'Enable' to listen again.";
            } else {
                 // User explicitly disabled it or an error forced disable
                 voiceStatusDisplay.textContent = "Voice control disabled.";
            }
            voiceControlEnabled = false; // Ensure it's always reset if recognition stops
            toggleVoiceCtrlBtn.textContent = "Enable Voice Commands";
            toggleVoiceCtrlBtn.classList.remove('voice-enabled');
        };

    } else {
        // Speech Recognition API not supported
        if (toggleVoiceCtrlBtn) toggleVoiceCtrlBtn.disabled = true;
        if (voiceStatusDisplay) voiceStatusDisplay.textContent = 'Speech recognition not supported by this browser.';
        console.warn("Speech Recognition API not supported.");
    }


    function clearVotingArea() {
        audienceChoicesDiv.innerHTML = 'Vote options will appear here.';
        audienceResultsDiv.innerHTML = 'Vote results will appear here.';
    }

    function renderVotingOptions(questionId, answerChoices) {
        clearVotingArea();
        if (!answerChoices || answerChoices.length === 0) {
            audienceChoicesDiv.innerHTML = 'No answer choices provided for voting.';
            return;
        }

        answerChoices.forEach(choice => {
            const button = document.createElement('button');
            button.className = 'vote-choice-btn';
            button.textContent = choice;
            button.onclick = () => submitAudienceVote(questionId, choice);
            audienceChoicesDiv.appendChild(button);
        });
    }

    async function submitAudienceVote(questionId, selectedChoice) {
        if (!currentGameSessionId) {
            console.error("Cannot submit vote: no active game session.");
            return;
        }
        // Disable voting buttons after one vote (simple prevention)
        document.querySelectorAll('.vote-choice-btn').forEach(btn => btn.disabled = true);

        try {
            const response = await fetch(`/api/game/${currentGameSessionId}/question/${questionId}/vote`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_choice: selectedChoice })
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            // Vote recorded, now fetch and display results
            await displayVoteResults(questionId);
        } catch (error) {
            console.error('Error submitting audience vote:', error);
            audienceResultsDiv.textContent = `Error submitting vote: ${error.message}`;
            // Re-enable buttons if submission failed.
            document.querySelectorAll('.vote-choice-btn').forEach(btn => btn.disabled = false);
        }
    }

    async function displayVoteResults(questionId) {
        if (!currentGameSessionId) {
            console.error("Cannot display results: no active game session.");
            return;
        }
        try {
            const response = await fetch(`/api/game/${currentGameSessionId}/question/${questionId}/results`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            audienceResultsDiv.innerHTML = ''; // Clear previous results

            const title = document.createElement('h4');
            title.textContent = 'Audience Vote Results:';
            audienceResultsDiv.appendChild(title);

            if (!data.results_percentages || data.total_votes === 0) {
                const noVotesP = document.createElement('p');
                noVotesP.textContent = 'No votes cast yet for this question.';
                audienceResultsDiv.appendChild(noVotesP);
                return;
            }

            const totalVotesP = document.createElement('p');
            totalVotesP.textContent = `(Total Votes: ${data.total_votes})`;
            totalVotesP.style.fontSize = "0.8em";
            totalVotesP.style.marginBottom = "10px";
            audienceResultsDiv.appendChild(totalVotesP);

            // Determine a sensible maximum width for labels if choices are very different in length
            // Or ensure CSS handles it well with truncation or fixed width.
            // For now, CSS .vote-choice-label handles fixed width.

            for (const choice in data.results_percentages) {
                const percentage = data.results_percentages[choice];

                const itemDiv = document.createElement('div');
                itemDiv.className = 'vote-result-item';

                const labelSpan = document.createElement('span');
                labelSpan.className = 'vote-choice-label';
                labelSpan.textContent = choice + ':'; // Added colon for clarity

                const barContainerDiv = document.createElement('div');
                barContainerDiv.className = 'vote-bar-container';

                const barDiv = document.createElement('div');
                barDiv.className = 'vote-bar';
                // Set width after a short delay to allow CSS transition to be visible
                setTimeout(() => {
                    barDiv.style.width = percentage + '%';
                }, 100);

                // Optional: Text inside bar if it fits and looks good
                // if (percentage > 15) { // Only if bar is wide enough
                //     const barTextSpan = document.createElement('span');
                //     barTextSpan.className = 'vote-bar-text';
                //     barTextSpan.textContent = percentage + '%';
                //     barDiv.appendChild(barTextSpan);
                // }

                const percentageSpan = document.createElement('span');
                percentageSpan.className = 'vote-percentage-text';
                percentageSpan.textContent = percentage + '%';

                barContainerDiv.appendChild(barDiv);
                itemDiv.appendChild(labelSpan);
                itemDiv.appendChild(barContainerDiv);
                itemDiv.appendChild(percentageSpan);
                audienceResultsDiv.appendChild(itemDiv);
            }
        } catch (error) {
            console.error('Error fetching/displaying vote results:', error);
            audienceResultsDiv.textContent = `Error fetching results: ${error.message}`;
        }
    }

    // Stop Game function (from previous step)
    async function stopGame() {
        if (!currentGameSessionId) {
            alert("No active game to stop, or game already concluded.");
            return;
        }
        submitAnswerBtn.disabled = true;
        if (stopGameBtn) stopGameBtn.disabled = true;

        try {
            const response = await fetch(`/api/game/${currentGameSessionId}/stop`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                const errorData = await response.json();
                // Attempt to fetch current game state to correctly set button states
                const currentGameState = await fetch(`/api/game/${currentGameSessionId}/status`).then(res => res.ok ? res.json() : null);
                if (currentGameState && currentGameState.game_state === 'active') {
                    submitAnswerBtn.disabled = false;
                    if (stopGameBtn) stopGameBtn.disabled = false;
                }
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const updatedGameState = await response.json();
            updateDisplay(updatedGameState);
        } catch (error) {
            console.error('Error stopping game:', error);
            lastAnswerResultDisplay.textContent = `Error stopping game: ${error.message}`;
            // Attempt to restore button states based on potentially fetched current state
             const currentGameState = await fetch(`/api/game/${currentGameSessionId}/status`).then(res => res.ok ? res.json() : null);
             if(currentGameState && currentGameState.game_state === 'active') {
                submitAnswerBtn.disabled = false;
                if (stopGameBtn) stopGameBtn.disabled = false;
             }
        }
    }
});
