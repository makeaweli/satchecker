from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from core import utils

db_login = utils.get_db_login()

app = Flask(__name__)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["1 per second"]
)

app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://{}:{}@{}:{}/{}".format(
    db_login[0], db_login[1], db_login[2], db_login[3], db_login[4]) 
    #"postgres", "sat123", "localhost", "5432", "postgres")
db = SQLAlchemy(app)

from core import routes
