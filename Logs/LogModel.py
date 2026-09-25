from datetime import datetime
from src.extensions import db


class NotificationLog(db.Model):
    __tablename__ = 'notification_logs'

    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String, nullable=False)
    channel = db.Column(db.String(10), nullable=False)
    template_name = db.Column(db.String, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    failure_category = db.Column(db.String(20), nullable=True)
    response_code = db.Column(db.Integer, nullable=True)
    failure_reason = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return (f"NotificationLog(recipient={self.recipient}, channel={self.channel}, "
                f"template={self.template_name}, status={self.status}, "
                f"failure_category={self.failure_category})")