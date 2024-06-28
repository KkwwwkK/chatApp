from flask import Flask, redirect, render_template, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from flask_session import Session
from functools import wraps
from models import db, User, ChatRoom, Message, UserChatRoom
from flask_socketio import SocketIO, join_room, leave_room, send


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://admin:password@fsse-ken-mysql.c7u2gmuw4a44.ap-southeast-1.rds.amazonaws.com:3306/Chat_APP_RaftAHill"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
@login_required
def index():
    """Show TBD"""
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username:
            return "must provide username", 400
        if not password:
            return "must provide password", 400

        user = User.query.filter_by(username=username).first()

        if user is None or not check_password_hash(user.password_hash, password):
            return "invalid username and/or password", 400

        session["user_id"] = user.id
        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return "please fill username"
        if User.query.filter_by(username=username).first():
            return "username already existed"
        if not password:
            return "please fill password"
        if not confirmation:
            return "please fill confirmation"
        if password != confirmation:
            return "password does not match"

        password_hash = generate_password_hash(password, method="pbkdf2", salt_length=16)
        new_user = User(username=username, password_hash=password_hash)
        db.session.add(new_user)
        db.session.commit()

        user = User.query.filter_by(username=username).first()
        session["user_id"] = user.id
        return redirect("/")

    return render_template("register.html")


@app.route('/livechat')
@login_required
def livechat():
    user_id = session['user_id']
    user = User.query.get(user_id)
    chat_rooms = user.chat_rooms  # Assuming a relationship is defined in the User model
    return render_template('livechat.html', user=user, chat_rooms=chat_rooms)


@app.route('/search_user')
@login_required
def search_user():
    try:
        query = request.args.get('query')
        if not query:
            return jsonify([])

        users = User.query.filter(User.username.contains(query)).all()
        results = [{'id': user.id, 'username': user.username} for user in users]  # Remove 'last_seen'
        return jsonify(results)
    except Exception as e:
        # Log the exception for debugging purposes
        print(f"Exception in search_user: {str(e)}")
        return jsonify({'error': 'Internal Server Error'}), 500



@app.route('/initiate_chat', methods=['POST'])
@login_required
def initiate_chat():
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        current_user_id = session.get('user_id')  # Use session.get() to avoid KeyError
        if not current_user_id:
            return jsonify({'error': 'Not authenticated'}), 401

        # Check if a chat room already exists between the two users
        chat_room = ChatRoom.query.filter(
            ChatRoom.users.any(User.id == current_user_id),
            ChatRoom.users.any(User.id == user_id)
        ).first()

        if not chat_room:
            # Create a new chat room
            chat_room = ChatRoom(name=f"Chat between {current_user_id} and {user_id}")  # Provide a meaningful name
            chat_room.users.append(User.query.get(current_user_id))
            chat_room.users.append(User.query.get(user_id))
            db.session.add(chat_room)
            db.session.commit()

        return jsonify({'room_id': chat_room.id}), 200
    except Exception as e:
        # Log the exception for debugging purposes
        print(f"Exception in initiate_chat: {str(e)}")
        return jsonify({'error': 'Internal Server Error'}), 500



@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    join_room(room)
    send(f'{username} has entered the room.', to=room)


@socketio.on('message')
def handle_message(data):
    room = data['room']
    message = data['message']
    user_id = session['user_id']
    new_message = Message(content=message, chat_room_id=room, user_id=user_id)
    db.session.add(new_message)
    db.session.commit()
    send(message, to=room)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create tables
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
