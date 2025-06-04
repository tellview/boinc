from . import db
from datetime import datetime
# from sqlalchemy.dialects.sqlite import JSON # Already using db.JSON which is fine

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String, nullable=False)
    answer_choices = db.Column(db.JSON, nullable=True)
    correct_answer = db.Column(db.String, nullable=False)
    question_type = db.Column(db.String, default='text')
    difficulty = db.Column(db.String, default='medium')
    pack_name = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Question {self.id}>'

class GameSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_name = db.Column(db.String(100), nullable=True, unique=True) # Made it 100 char length
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    current_round = db.Column(db.Integer, default=0)
    scores = db.Column(db.JSON, nullable=True) # e.g., {'AI_Player_1': 10, 'AI_Player_2': 5}
    game_state = db.Column(db.String(50), default='pending') # e.g., 'pending', 'active', 'finished'

    # New fields for game logic
    current_question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=True)
    current_player_id = db.Column(db.String(100), nullable=True) # Made it 100 char length

    # Relationship to Question model
    current_question = db.relationship('Question', foreign_keys=[current_question_id])

    def __repr__(self):
        return f'<GameSession {self.id}: {self.session_name}>'
