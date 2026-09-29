import datetime
import calendar
import json
import os
import secrets
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

class PastDateHTMLCalendar(calendar.HTMLCalendar):
    def __init__(self, year, month, tasks=None):
        super().__init__()
        self.year = year
        self.month = month
        self.today = datetime.date.today()
        self.tasks=tasks or []

    def formatday(self, day, weekday):
        if day == 0:
            return '<td class="noday">&nbsp;</td>'
        
        cell_date = datetime.date(self.year, self.month, day)
        cell_date_str = cell_date.strftime("%Y-%m-%d")

        day_tasks =[
            {
                'id':t['id'],
                'title':t['title'],
                'description': t.get("description", ""),
                "task_type": t.get("task_type", ""),
                "task_subtype": t.get("task_subtype", ""),
                "due_date": t.get("due_date", ""),
                "due_time": t.get("due_time", "")
            }
            for t in self.tasks if t.get("due_date") == cell_date_str
        ]

        tasks_json=json.dumps(day_tasks).replace('"', '&quot;')
        
        if cell_date < self.today:
            return f'<td class="past-date" data-date="{cell_date_str}" data-tasks="{tasks_json}"><span class="day-num">{day}</span></td>'
        
        return f'<td class="valid-date" data-date="{cell_date_str}" data-tasks="{tasks_json}"><span class="day-num">{day}</span></td>'
        
    def formatmonth(self, theyear, themonth, withyear=True):
        self.year = theyear
        self.month = themonth
        return super().formatmonth(theyear, themonth, withyear=withyear)


def process_overdue_tasks(username):
    tasks=load_data()
    today_str=datetime.date.today().strftime("%Y-%m-%d")
    updated=False

    for task in tasks:
        if task.get('username')==username and not task.get('done'):
            if task.get('due_date')<today_str:
                task["done"] = True
                task["status"] = "overdue_unmarked"
                task["completed_at"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
                if "justification" not in task:
                    task["justification"] = ""
                updated = True
    if updated:
        save_data(tasks)


app = Flask(__name__)
# Set FLASK_SECRET_KEY to a persistent random value in deployment. The fallback
# keeps local development usable, but invalidates sessions when the app restarts.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

DATA_FILE = Path(__file__).parent / "data" / "tasks.json"
USERS_FILE = Path(__file__).parent / "data" / "users.json"

def load_users():
    if USERS_FILE.exists():
        with open(USERS_FILE, "r") as file:
            return json.load(file)
    return {}

def save_users(users):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w") as file:
        json.dump(users, file, indent=4)   

def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r") as file:
            data = json.load(file)
            return data.get("tasks", [])
    return []


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as file:
        json.dump({"tasks": data}, file, indent=4)


@app.route("/")
def home():
    return render_template("home.html")



@app.route("/name/<username>")
def user(username):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    process_overdue_tasks(username)

    cur_datetime = datetime.datetime.now()
    today_str = cur_datetime.strftime("%Y-%m-%d")

    users=load_users()
    user_info=users.get(username,{})
    all_tasks=[task for task in load_data() if task.get('username')==username]

    active_tasks=[task for task in all_tasks if not task.get('done')]
    history_tasks=[task for task in all_tasks if task.get('done')]

    cal=PastDateHTMLCalendar(cur_datetime.year, cur_datetime.month, tasks=all_tasks)
    calendar_html = cal.formatmonth(cur_datetime.year, cur_datetime.month)
    
    return render_template('user.html', username=username, user_type=user_info.get('user_type','other'), active_tasks=active_tasks, history_tasks=history_tasks, calendar_html=calendar_html, today_str=today_str)


@app.route("/add_task", methods=["POST"])
def add_task():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    title = request.form.get("title").strip()
    description = request.form.get("description", "").strip()
    due_date = request.form.get("due_date", "")
    due_time = request.form.get("due_time", "")

    if not title or not due_date:
        return "Title and date/time are required.",400

    today_str=datetime.date.today().strftime("%Y-%m-%d")
    if due_date<today_str:
        return 'Cannot go back in time, sorry...',400
    
    username=session['username']
    users=load_users()
    user_info=users.get(username,{})
    user_type=user_info.get('user_type','other')

    selected_type= request.form.get('task_type','other').strip()
    selected_subtype=request.form.get('task_subtype',"").strip()
    custom_type=request.form.get('custom_task_type',"").strip()
    custom_subtype = request.form.get('custom_task_subtype', "").strip()

    if user_type=='ib_student':
        valid_task_types=['CAS:[Creativity, Activity, Service]','Internal','EE','Test','other']
        if selected_type not in valid_task_types:
            selected_type='other'

    elif user_type=='student':
        valid_task_types=['Test','Project','Activity','Service','other']
        if selected_type not in valid_task_types:
            selected_type='other'

    elif user_type=='adult':
        valid_task_types=['Meeting','Project','Presentation','Activity','Service','other']
        if selected_type not in valid_task_types:
            selected_type='other'
    else:
        selected_type='other'


    final_type = custom_type if selected_type == 'other' and custom_type else selected_type
    final_subtype = custom_subtype if selected_subtype == 'other_subtype' else selected_subtype
        
    tasks = load_data()
    task_id = max((task["id"] for task in tasks if "id" in task), default=0) + 1

    tasks.append({"id": task_id, "title": title,"description": description,"due_date": due_date,"due_time": due_time,"username": session["username"],"task_type":final_type,"task_subtype":final_subtype if final_subtype else None,"done": False, "status":"active"})

    save_data(tasks)
    return redirect(url_for("user", username=session["username"]))


@app.route('/get/tasks')
def get_tasks():
    if not session.get("logged_in"):
            return jsonify([]),401
    username=session.get('username')
    tasks=[t for t in load_data() if t.get('username')==username and not t.get('done')]
    return jsonify(tasks)

@app.route('/edit_task/<int:task_id>', methods=['POST'])
def edit_task(task_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    tasks = load_data()
    for task in tasks:
        if task['id'] == task_id and task['username'] == session['username']:
            task['title'] = request.form.get('title', '').strip()
            task['description'] = request.form.get('description', '').strip()
            task['due_date'] = request.form.get('due_date', '')
            task['due_time'] = request.form.get('due_time', '')
            
            selected_type = request.form.get('task_type', 'other').strip()
            custom_type = request.form.get('custom_task_type', "").strip()
            selected_subtype = request.form.get('task_subtype', "").strip()
            custom_subtype = request.form.get('custom_task_subtype', "").strip()

            task['task_type'] = custom_type if selected_type == 'other' and custom_type else selected_type
            task['task_subtype'] = custom_subtype if selected_subtype == 'other_subtype' else selected_subtype
            break
    save_data(tasks)
    return redirect(url_for('user',username=session['username']))

@app.route('/delete_task/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    tasks = load_data()
    tasks = [t for t in tasks if not (t['id'] == task_id and t['username'] == session['username'])]
    save_data(tasks)
    
    return redirect(url_for('user', username=session['username']))



@app.route('/add_justification/<int:task_id>', methods=['POST'])
def add_justification(task_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    justification = request.form.get('justification', '').strip()
    tasks = load_data()

    for task in tasks:
        if task['id'] == task_id and task['username'] == session['username']:
            task['justification'] = justification
            break

    save_data(tasks)
    return redirect(url_for('history'))



@app.route('/task_complete/<int:task_id>', methods=['POST'])
def task_complete(task_id):
    if not session.get("logged_in"):
            return redirect(url_for("login"))
    tasks=load_data()
    for task in tasks:
        if task['id']==task_id and task['username']==session['username']:
            task['done']=True
            task['completed_at']= datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            break
    save_data(tasks)
    return redirect(url_for('user', username=session['username']))

@app.route('/add_reflection/<int:task_id>', methods=['POST'])
def add_reflection(task_id):
    if not session.get("logged_in"):
                return redirect(url_for("login"))
    reflection=request.form.get('reflection','').strip()
    tasks=load_data()

    for task in tasks:
        if task['id']==task_id and task['username']==session['username']:
            task['reflection']=reflection
            break

    save_data(tasks)
    return redirect(url_for('history',username=session['username']))
@app.route("/admin")
def admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("admin.html")


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        users = load_users()
        user_record = users.get(username)
        user_password = (
            user_record.get("password")
            if isinstance(user_record, dict)
            else user_record
        )

        password_is_hashed = isinstance(user_password, str) and user_password.startswith(
            ("scrypt:", "pbkdf2:")
        )
        if password_is_hashed:
            try:
                password_matches = check_password_hash(user_password, password)
            except (ValueError, TypeError):
                password_matches = False
        else:
            # Upgrade legacy plaintext test accounts only after a valid login.
            password_matches = bool(user_password) and user_password == password

        if password_matches:
            if not password_is_hashed:
                if isinstance(user_record, dict):
                    user_record["password"] = generate_password_hash(password)
                else:
                    users[username] = {
                        "password": generate_password_hash(password),
                        "user_type": "other",
                    }
                save_users(users)

            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("user", username=username))

        return render_template("login.html", error="Wrong username/password")

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session["logged_in"] = False
    session.pop("username", None)
    return redirect(url_for("home"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username",'').strip()
        password = request.form.get("password",'')

        if not username or not password:
            return render_template("signup.html", error="Username and password are required.")

        users= load_users() 
        if username in users:
            return render_template("signup.html", error="Username already exists.")

        user_type=request.form.get("user_type",'other')
        valid_types=['student','ib_student','adult', 'other']
        if user_type not in valid_types:
            user_type='other'
        users[username]={
            'password':generate_password_hash(password),
            'user_type':user_type
        }
        save_users(users)

        session["logged_in"] = True
        session["username"] = username
        return redirect(url_for("user", username=username))

    
    return render_template("signup.html")

@app.route('/history')
def history():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    username=session.get('username')
    process_overdue_tasks(username)

    all_tasks=[task for task in load_data()if task.get('username')==username]
    history_tasks=[task for task in all_tasks if task.get('done')]

    grouped_history={}
    for task in history_tasks:
        t_type= task.get('task_type') or 'Uncategorized'
        t_subtype=task.get('task_subtype') or 'General'

        if t_type not in grouped_history:
            grouped_history[t_type]={}
        if t_subtype not in grouped_history[t_type]:
            grouped_history[t_type][t_subtype]=[]

        grouped_history[t_type][t_subtype].append(task)

    return render_template('history.html', username=username, grouped_history=grouped_history)



if __name__ == "__main__":
    # macOS AirPlay Receiver commonly occupies port 5000; use 5001 locally.
    # Hosting platforms such as Render provide PORT, which takes precedence.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

