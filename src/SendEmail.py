import requests as re
from flask_restful import abort

from config import *
from time import sleep
from datetime import datetime
from Logs.logs import logs
from src.status import *

_cached_token = None

def _classify_failure(status_code):
    """400-499 means the request itself was invalid — retrying an identical
    request reproduces the identical error. 500+ and connection-level failures
    are treated as provider-side and worth retrying."""
    if status_code is not None and 400 <= status_code < 500:
        return PossibleFailure.INPUT_ERROR
    return PossibleFailure.PROVIDER_ERROR

def authenticate(des, channel, template_name):
    global _cached_token
    _token_expiry = None

    if _cached_token is None:
        headers = {
            'Content-Type': 'application/json',
        }

        body = {
            "appName": APP_NAME,
            "appId": APP_ID,
        }
        auth_response = None
        try:
            auth_response = re.post(f"{BASE_URL}/auth/login",headers=headers, json=body)
            _cached_token = auth_response.json()['token']
        except re.exceptions.ConnectionError:
            logs(des, channel, template_name, status=Status.FAILED, response=400,
                 failure_reason="Could not connect to API",
                 failure_category=PossibleFailure.AUTH_ERROR)
            abort(400, message="Unable to connect")
        except KeyError:
            logs(des, channel=channel, template=template_name, status=Status.FAILED,
                 failure_category=PossibleFailure.USER_ERROR, response=auth_response.status_code, failure_reason=auth_response.text)
            abort(auth_response.status_code, message=auth_response.text)

    return _cached_token



def send_email(destination:str, subject, message:str, tries:int, template, isHtml):
    status = Status.PENDING
    failure_reason = None
    rec = " | ".join(destination)
    status_message = ''
    status_code = None
    token = authenticate(rec, template.channel, template.name)


    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-API-KEY": f"{EMAIL_API_KEY}"
    }

    body = {
        "from" : FROM,
        "to" : destination,
        "subject" : subject,
        "body" : message,
        "isHtml" : isHtml,
    }

    r = None

    while tries > 0:
        try:
            r = re.post(f"{BASE_URL}/email/send",json=body, headers=headers, timeout=TIMEOUT)
            status = Status.SUCCESS
            if r.status_code == 200:
                logs(rec, channel=template.channel, template=template.name, status=status,
                     response=r.status_code, failure_reason=None)
                status_message = "Success"
                status_code = r.status_code
                break
            elif r.status_code == 401:
                global _cached_token
                _cached_token = None
                token = authenticate(rec, template.channel, template.name)
                tries -= 1
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-API-KEY": f"{EMAIL_API_KEY}"
                }
                logs(rec, channel=template.channel, template=template.name, status=Status.FAILED,failure_category=PossibleFailure.AUTH_ERROR, response=r.status_code, failure_reason=r.text)
            else:
                status = Status.FAILED
                status_code = r.status_code
                status_message = r.json()["message"]
                category = _classify_failure(status_code)

                logs(rec, channel=template.channel, template=template.name, status=status,
                     response=status_code, failure_reason=status_message, failure_category=category)
                if category == PossibleFailure.INPUT_ERROR:
                    break # No point in retrying a bad request
                tries -= 1

        except (re.exceptions.ConnectionError, re.exceptions.Timeout) as ce:
            status = Status.FAILED
            status_code = 503
            status_message = "Could not establish connection"
            failure_reason = "Email microservice is currently unreachable: " + str(ce)
            logs(rec, channel=template.channel, template=template.name, status=status,
                 response=status_code, failure_reason=failure_reason, failure_category=PossibleFailure.PROVIDER_ERROR)
            tries -= 1


        # Retries
        sleep(1.0)

    # Send message
    return {"message":f"{status_message}"}, status_code