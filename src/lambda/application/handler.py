"""Application: serves the Custom UI and, using the Amazon SDK (boto3),
orchestrates the full identity-federation flow before calling the AI
assistant's chat sync API:

  1. Authentication  -- Cognito User Pool: trades a username/password for an
     OIDC-style identity token (id_token).
  2. Authorization    -- the trusted token issuer (modeled here with an IAM
     OIDC identity provider that trusts the Cognito user pool): exchanges the
     identity token for a trusted token scoped for AWS, via
     sso-oidc:CreateTokenWithIAM.
  3. AWS STS          -- AssumeRoleWithWebIdentity: exchanges the trusted
     token for short-lived, scoped credentials on the ai-assistant-access
     IAM role. This call is unauthenticated federation; it needs no IAM
     permission of its own, only the role's OIDC trust policy.
  4. Amazon SDK        -- calls the AI assistant's chat sync API (a Lambda
     function) using those temporary, scoped credentials.
"""
import json
import os
import uuid

import boto3

REGION = os.environ.get("REGION", "us-east-1")
ENDPOINT_URL = os.environ.get("FLOCI_ENDPOINT", "http://localhost:4566")
USER_POOL_ID = os.environ["USER_POOL_ID"]
USER_POOL_CLIENT_ID = os.environ["USER_POOL_CLIENT_ID"]
TRUSTED_TOKEN_ISSUER_ARN = os.environ["TRUSTED_TOKEN_ISSUER_ARN"]
ASSISTANT_ROLE_ARN = os.environ["ASSISTANT_ROLE_ARN"]
AI_ASSISTANT_FUNCTION_NAME = os.environ["AI_ASSISTANT_FUNCTION_NAME"]

_boto_kwargs = {
    "region_name": REGION,
    "endpoint_url": ENDPOINT_URL,
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
}

cognito_idp = boto3.client("cognito-idp", **_boto_kwargs)
sso_oidc = boto3.client("sso-oidc", **_boto_kwargs)
sts = boto3.client("sts", **_boto_kwargs)


def lambda_handler(event, context):
    method = (event.get("requestContext") or {}).get("http", {}).get("method", "GET")

    if method == "GET":
        return _html_response(_render_custom_ui())

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _json_response(400, {"error": "Request body must be valid JSON."})

    username = body.get("username")
    password = body.get("password")
    prompt = body.get("prompt")
    if not (username and password and prompt):
        return _json_response(400, {"error": "'username', 'password' and 'prompt' are required."})

    try:
        identity_token = _authenticate(username, password)
        trusted_token = _exchange_for_trusted_token(identity_token)
        credentials = _assume_scoped_role(trusted_token)
        answer = _call_ai_assistant(credentials, prompt)
    except Exception as exc:
        return _json_response(502, {"error": str(exc)})

    return _json_response(200, answer)


def _authenticate(username, password):
    """Authentication: trades Cognito user credentials for an identity token."""
    response = cognito_idp.initiate_auth(
        ClientId=USER_POOL_CLIENT_ID,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": password},
    )
    return response["AuthenticationResult"]["IdToken"]


def _exchange_for_trusted_token(identity_token):
    """Authorization: exchanges the identity token for a trusted token through
    the trusted token issuer (sso-oidc:CreateTokenWithIAM)."""
    response = sso_oidc.create_token_with_iam(
        clientId=TRUSTED_TOKEN_ISSUER_ARN,
        grantType="urn:ietf:params:oauth:grant-type:token-exchange",
        subjectToken=identity_token,
        subjectTokenType="urn:ietf:params:oauth:token-type:id_token",
    )
    return response["accessToken"]


def _assume_scoped_role(trusted_token):
    """AWS STS: exchanges the trusted token for short-lived, scoped
    credentials on the ai-assistant-access role."""
    response = sts.assume_role_with_web_identity(
        RoleArn=ASSISTANT_ROLE_ARN,
        RoleSessionName=f"custom-ui-{uuid.uuid4().hex[:8]}",
        WebIdentityToken=trusted_token,
    )
    return response["Credentials"]


def _call_ai_assistant(credentials, prompt):
    """Amazon SDK: invokes the AI assistant's chat sync API using the
    temporary, scoped credentials obtained from STS."""
    scoped_lambda = boto3.client(
        "lambda",
        region_name=REGION,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )
    response = scoped_lambda.invoke(
        FunctionName=AI_ASSISTANT_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps({"prompt": prompt}).encode("utf-8"),
    )
    return json.loads(response["Payload"].read())


def _render_custom_ui():
    path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _html_response(html):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": html,
    }


def _json_response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(payload),
    }
