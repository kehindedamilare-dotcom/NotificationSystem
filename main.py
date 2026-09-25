import flask_restful
from flask import Flask

from datetime import datetime
from sqlalchemy.orm import validates
from sqlalchemy import CheckConstraint
from flask_restful import Api, reqparse, Resource, fields, marshal_with, abort

from src.SendSMS import send_sms
from src.SendEmail import send_email
from config import *
from src.extensions import db

def _validate_config():
    required = {
        "EMAIL_API_KEY" : EMAIL_API_KEY, "APP_NAME": APP_NAME,
        "BASE_URL" : BASE_URL, "APP_ID": APP_ID,
        "FROM": FROM,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required configuration value(s): {', '.join(missing)}")

_validate_config()

# Initialise Flask and SQLAlchemy
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///templates.db'
db.init_app(app)
api = Api(app)

# Others
failure_reason = None
failure_category = None


# Create Template data model
class TemplateModel(db.Model):
    __tablename__ = 'templates'
    __table_args__ = (
        CheckConstraint("channel IN ('SMS', 'EMAIL')", name='check_valid_channels'),
    )
    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(5), nullable=False)
    name = db.Column(db.String, nullable=False)
    subject = db.Column(db.String, nullable=True)
    body = db.Column(db.String(500), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    template_placeholders = db.Column(db.String, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Add validation method for the 'name' field
    @validates('name')
    def uppercase_name(self, key, value):
        if value:
            # Strip trailing spaces and capitalize everything
            return value.strip().upper()
        return value

    # Add validation method for the 'channel' field
    @validates('channel')
    def uppercase_channel(self, key, value):
        if not value:
            raise ValueError("Channel cannot be empty.")

        # Standardize the case first
        uppercased_channel = value.strip().upper()

        # Explicit validation check against allowed channels
        allowed_channels = ['SMS', 'EMAIL']
        if uppercased_channel not in allowed_channels:
            # Raising a ValueError cleanly stops execution before hitting the database
            raise ValueError(f"Invalid channel '{value}'. Allowed channels are: {allowed_channels}")

        return uppercased_channel

    def __repr__(self):
        return f"Template(channel={self.channel}, name={self.name}, subject={self.subject}, body={self.body}, active={self.active}, created_at={self.created_at}, updated_at={self.updated_at})"


# Handle expected query parameters provided in the url
template_parser = reqparse.RequestParser()
template_parser.add_argument("name", type=str, required=True, help="Name cannot be blank", location='json')
template_parser.add_argument("channel", type=str, required=True, help="Channel cannot be blank", location='json')
template_parser.add_argument("subject", type=str, required=False, location='json')
template_parser.add_argument("body", type=str, required=True, help="Body cannot be blank", location='json')
template_parser.add_argument("template_placeholders", type=str, required=True, location='json', help="Placeholder cannot be blank")


# Parser for updating existing templates (PUT) - arguments are optional
template_update_parser = reqparse.RequestParser()
template_update_parser.add_argument("name", type=str, location='json')
template_update_parser.add_argument("channel", type=str, location='json')
template_update_parser.add_argument("subject", type=str, location='json')
template_update_parser.add_argument("body", type=str, location='json')
template_update_parser.add_argument("active", type=bool, location='json')
template_update_parser.add_argument("template_placeholders", type=str, location='json')

# Parser for Users
user_parser = reqparse.RequestParser()
user_parser.add_argument("name", type=str, required=True, help="Template name cannot be blank", location='json')
user_parser.add_argument("channel", type=str, required=True, help="Channel cannot be blank", location='json')
user_parser.add_argument("recipient", type=str, required=True, help="Recipient cannot be blank", location='json')
user_parser.add_argument("placeholders", type=dict, required=True, help="Placeholders cannot be blank", location='json')
# user_parser.add_argument("retries", type=int, required=True, help="Retries cannot be blank", location='json')
user_parser.add_argument("isHTML", type=bool, default=True, help="Is HTML cannot be blank", location='json')

templateFields = {
        'id': fields.Integer,
        'name':fields.String,
        'channel':fields.String,
        'subject':fields.String,
        'body':fields.String,
        'template_placeholders':fields.String,
        'updated_at':fields.DateTime,
        'created_at':fields.DateTime,
}

class Template(Resource):
    @marshal_with(templateFields)
    def get(self):
        templates = TemplateModel.query.all()
        return templates

    @marshal_with(templateFields)
    def post(self):
        args = template_parser.parse_args()
        channelUpper = args['channel'].strip().upper()
        nameUpper = args['name'].strip().upper()
        existing_item = TemplateModel.query.filter_by(name=nameUpper, channel=channelUpper).first()

        if existing_item:
            # Return an error message and a 400 Bad Request status code
            flask_restful.abort(400, message=f"A template with the name '{args['name']}' and channel '{args['channel']}' already exists.")

        try:
            # If args['channel'] is 'sms', it becomes 'SMS' inside TemplateModel
            # If it's 'push', the line below immediately throws a ValueError
            template = TemplateModel(
                name=nameUpper,
                channel=channelUpper,
                subject=args['subject'],
                body=args['body'],
                template_placeholders=args['template_placeholders'],
                updated_at=datetime.utcnow()
            )
            db.session.add(template)
            db.session.commit()
        except ValueError as e:
            db.session.rollback()
            flask_restful.abort(400, message=str(e))  # Returns the exact message from the validator

        # templates = TemplateModel.query.all()
        return template, 201


class EditingTemplates(Resource):
    @marshal_with(templateFields)
    def get(self, template_id):
        template = TemplateModel.query.filter_by(id=template_id).first()
        if not template:
            flask_restful.abort(404, message=f"Template with id '{template_id}' doesn't exist.")
        return template, 200

    @marshal_with(templateFields)
    def put(self, template_id):
        args = template_update_parser.parse_args()


        template = TemplateModel.query.filter_by(id=template_id).first()

        # Check if template with the provided id is there
        if not template:
            flask_restful.abort(404, message=f"Template with id '{template_id}' doesn't exist.")

        # Update fields
        try:
            if args['name'] is not None:
                nameUpper = args['name'].strip().upper()
                template.name = nameUpper
            if args['channel'] is not None:
                channelUpper = args['channel'].strip().upper()
                template.channel = channelUpper
            if args['subject'] is not None:
                template.subject = args['subject']
            if args['body'] is not None:
                template.body = args['body']
            if args['active'] is not None:
                template.active = args['active']
            if args['template_placeholders'] is not None:
                template.template_placeholders = args['template_placeholders']

            template.updated_at = datetime.utcnow()
            db.session.commit()
        except ValueError as e:
            db.session.rollback()
            flask_restful.abort(400, message=str(e))

        return template, 200


    def delete(self, template_id):
        template = TemplateModel.query.filter_by(id=template_id).first()

        # Check for template with id again
        if not template:
            flask_restful.abort(404, message=f"Template with id '{template_id}' doesn't exist.")


        db.session.delete(template)
        db.session.commit()

        return '', 204


class User(Resource):

    def post(self):
        args = user_parser.parse_args()
        channel = args['channel'].strip().upper()
        name = args['name'].strip().upper()
        recipient = args['recipient']
        placeholders = args['placeholders']
        isHTML = args['isHTML']

        template = TemplateModel.query.filter_by(name=name, channel=channel).first()

        # Check for availability of template
        if not template:
            abort(400, message=f"{channel} template with name '{name}' doesn't exist.")


        # Get the message body from the desired templates
        message = template.body
        sub = template.subject



        # Replace template placeholders with values
        holders = template.template_placeholders.split(',')
        for holder in holders:
            try:
                message = message.replace(f"{{{{{holder.strip()}}}}}", placeholders[holder.strip()])
                sub = sub.replace(f"{{{{{holder.strip()}}}}}", placeholders[holder.strip()])
            except KeyError as e:
                abort(400, message=f"No placeholder '{holder}'.")

        # Send message
        if channel == 'EMAIL':
            # Create an array of all recipient for email
            split_recipient = recipient.split(',')
            return send_email(split_recipient, sub, message, MAX_RETRIES, template, isHTML)
        else:
            return send_sms(message, recipient, MAX_RETRIES)




# Routing
api.add_resource(Template, '/admin/templates')
api.add_resource(EditingTemplates, '/admin/templates/<int:template_id>')
api.add_resource(User, '/send')




#
# if EMAIL_API_KEY is None or BASE_URL is None:
#     return {"message" : "Some important environment variables are not set."}

if __name__ == '__main__':
    app.run(debug=True, port=5500)