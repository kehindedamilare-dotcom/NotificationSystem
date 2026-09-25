from src.extensions import db
from Logs.LogModel import NotificationLog


def logs(recipient, channel, template, status, response, failure_reason, failure_category=None):
    entry = NotificationLog(
        recipient=recipient,
        channel=channel,
        template_name=template,
        status=status.name if hasattr(status, "name") else str(status),
        failure_category=failure_category.name if failure_category else None,
        response_code=response,
        failure_reason=failure_reason,
    )
    db.session.add(entry)
    db.session.commit()
    print("LOGGED!!")