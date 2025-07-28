from flask import Flask, redirect, url_for, render_template_string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret-key'

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>Login - Mulax Cafe</title></head>
<body>
    <h1>Mulax Cafe Login</h1>
    <form method="post">
        <p>Username: <input type="text" name="username" required></p>
        <p>Password: <input type="password" name="password" required></p>
        <p><input type="submit" value="Login"></p>
    </form>
</body>
</html>
'''

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    return "<h1>Dashboard</h1><p>Welcome to Mulax Cafe Dashboard!</p>"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5058, debug=True)
