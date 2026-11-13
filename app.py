from flask import Flask
from flask_bootstrap import Bootstrap5
from route import register_routes
from modes import db,User
from schema_updates import allow_job_payment_installments, ensure_user_active_column, ensure_security_schema, ensure_product_value, schema_transaction
from installation_secret import installation_secret
from database_writes import configure_sqlite, sqlite_pool_options
import logging
from waitress import serve
import os

SERVER_OPTIONS = dict(threads=8, asyncore_use_poll=True,
                      connection_limit=2048, backlog=2048)

def create_app(test_config=None):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('APP_SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        "DATABASE_URI", "sqlite:///cloth.db"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_BINDS'] = {
        'users': os.environ.get("USERS_DATABASE_URI", "sqlite:///users.db")
    }
    app.config['SIMPLE_WORKFLOW'] = True
    app.config['LABEL_PRINT_ROOT'] = os.environ.get('LABEL_PRINT_ROOT')
    if test_config:
        app.config.update(test_config)
    app.config['SECRET_KEY'] = installation_secret(app)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        **sqlite_pool_options(app.config['SQLALCHEMY_DATABASE_URI']),
        **app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}),
    }
    app.config['SQLALCHEMY_BINDS'] = {
        name: {**sqlite_pool_options(options['url'] if isinstance(options, dict) else options),
               **(options if isinstance(options, dict) else {'url': options})}
        for name, options in app.config['SQLALCHEMY_BINDS'].items()
    }

    db.init_app(app)
    Bootstrap5(app)
    with app.app_context():
        for engine in db.engines.values():
            configure_sqlite(engine)
        for bind_key, engine in db.engines.items():
            with schema_transaction(engine) as connection:
                db.metadatas[bind_key].create_all(bind=connection)
        ensure_product_value(db.engine)
        allow_job_payment_installments(db.engine)
        ensure_user_active_column(db.engines['users'])
        ensure_security_schema(db.engine, db.engines['users'])
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
    serve(app, host='127.0.0.1', port=5000, **SERVER_OPTIONS)
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
