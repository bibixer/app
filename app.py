from flask import Flask
from flask_bootstrap import Bootstrap5
from route import register_routes
from modes import db,User
import logging
from waitress import serve

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


logging.basicConfig(filename='flask.log', level=logging.INFO)
if __name__ == '__main__':
    app = create_app()
    logging.info("Flask service starting")
    serve(app, host='127.0.0.1', port=5000, threads=8)

    # with app.app_context():
    #     data = []
    #     from sqlalchemy.exc import IntegrityError
    #
    #     try:
    #         for u in data:
    #             user = User(
    #                 username=u['usre'].strip().lower(),
    #                 password=u['password'],
    #                 role=u['role']
    #             )
    #             db.session.add(user)
    #
    #         db.session.commit()
    #
    #     except IntegrityError:
    #         db.session.rollback()
    #         print("Duplicate username detected")
