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

# from sqlalchemy import inspect, text
# def ensure_new_column(new_columns, table_names):
#     inspector = inspect(db.engine)
#
#     for table in table_names:
#         columns = [col["name"] for col in inspector.get_columns(table)]
#
#         for col_name, (col_type, nullable) in new_columns.items():
#             if col_name not in columns:
#                 # Determine SQL type
#                 if isinstance(col_type, db.String):
#                     sql_type = f"VARCHAR({col_type.length or 255})"
#                     default_val = "''"
#                 elif isinstance(col_type, db.Integer):
#                     sql_type = "INTEGER"
#                     default_val = "0"
#                 else:
#                     sql_type = "TEXT"
#                     default_val = "''"
#
#                 # SQLite cannot add NOT NULL without default, so fix that
#                 if nullable:
#                     alter_stmt = f"ALTER TABLE {table} ADD COLUMN {col_name} {sql_type} NULL;"
#                 else:
#                     alter_stmt = f"ALTER TABLE {table} ADD COLUMN {col_name} {sql_type} NOT NULL DEFAULT {default_val};"
#
#                 print(f"🧩 Adding missing column '{col_name}' to {table}...")
#                 with db.engine.connect() as conn:
#                     conn.execute(text(alter_stmt))
#                 print(f"✅ Column '{col_name}' added to {table} successfully!")
#             else:
#                 print(f"✅ Column '{col_name}' already exists in {table} — no change needed.")

if __name__ == '__main__':
    app = create_app()
    logging.info("Flask service starting")
    serve(app, host='127.0.0.1', port=5000, threads=8)
    # with app.app_context():
    #      new_columns = {
    #              "meters_add_remove": (db.Float,False),
    #               "bale_id ": (db.Integer, False),
    #          }
    #      ensure_new_column(new_columns, ["LumpData"])





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
