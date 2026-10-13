"""ai_assistant (chat sync API): the target AI assistant. It is invoked by the
Application only after the Application has assumed the scoped `ai-assistant-access`
IAM role via STS AssumeRoleWithWebIdentity, so every call here already carries
short-lived, least-privilege credentials. Synchronously generates a chat
response for the given prompt by calling Amazon Bedrock's foundation model.
"""
import json
import os
import uuid

import boto3

REGION = os.environ.get("REGION", "us-east-1")
MODEL_ID = os.environ.get("MODEL_ID", "amazon.titan-text-express-v1")

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
    endpoint_url="http://localhost:4566",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)


def lambda_handler(event, context):
    """chat sync API: `event` is the plain payload sent by the Application's
    Amazon SDK invoke call, e.g. {"prompt": str, "conversationId": str|None}.
    """
    prompt = (event or {}).get("prompt")
    if not prompt:
        return {"error": "'prompt' is required."}

    conversation_id = event.get("conversationId") or uuid.uuid4().hex

    return {
        "answer": _generate_answer(prompt),
        "conversationId": conversation_id,
    }


def _generate_answer(prompt):
    try:
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {"maxTokenCount": 512, "temperature": 0.5},
            }),
        )
        payload = json.loads(response["body"].read())
        return payload["results"][0]["outputText"].strip()
    except Exception as exc:  # pragma: no cover - offline/floci fallback
        return f"(assistant stub) You asked: {prompt!r}. [bedrock unavailable: {exc}]"
