from flask import Flask
from flask_bootstrap import Bootstrap5
from route import register_routes
from modes import db



def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = '8BYkEfBA6O6donzWlSihBXox7C0sKR6b'
    app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///cloth.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_BINDS'] = {
        'users': 'sqlite:///users.db'
    }

    db.init_app(app)
    Bootstrap5(app)
    with app.app_context():
        db.create_all()
    register_routes(app,db)
    return app




if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
