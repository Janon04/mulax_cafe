from app import create_app
from flask import Flask

# Create a simple test app
test_app = Flask(__name__)
test_app.config['SECRET_KEY'] = 'test'

@test_app.route('/')
def test_root():
    return "Test app working!"

@test_app.route('/test')
def test_page():
    return "Test page working!"

if __name__ == "__main__":
    test_app.run(host='0.0.0.0', port=5057, debug=True)
