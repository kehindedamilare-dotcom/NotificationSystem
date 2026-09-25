from src.extensions import db
from Logs.LogModel import NotificationLog
import main

# Create Database for Templates
with main.app.app_context():
    db.create_all()