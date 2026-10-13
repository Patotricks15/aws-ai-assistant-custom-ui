# ─── Authentication: Cognito User Pool (OIDC-style identity provider) ───────

resource "aws_cognito_user_pool" "authentication" {
  name = "${local.name_prefix}-${var.cognito_user_pool_name}"

  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
  }

  tags = local.common_tags
}

resource "aws_cognito_user_pool_client" "custom_ui" {
  name         = "${local.name_prefix}-custom-ui-client"
  user_pool_id = aws_cognito_user_pool.authentication.id

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  generate_secret        = false
  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

# ─── Authorization: trusted token issuer (IAM OIDC identity provider that ────
# trusts the Cognito user pool) + the scoped IAM role assumed via
# STS AssumeRoleWithWebIdentity ───────────────────────────────────────────────

resource "aws_iam_openid_connect_provider" "trusted_token_issuer" {
  url = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.authentication.id}"

  client_id_list  = [aws_cognito_user_pool_client.custom_ui.id]
  thumbprint_list = [var.oidc_thumbprint]

  tags = local.common_tags
}

resource "aws_iam_role" "ai_assistant_access" {
  name = "${local.name_prefix}-ai-assistant-access"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = aws_iam_openid_connect_provider.trusted_token_issuer.arn }
      Condition = {
        StringEquals = {
          "${replace(aws_iam_openid_connect_provider.trusted_token_issuer.url, "https://", "")}:aud" = aws_cognito_user_pool_client.custom_ui.id
        }
      }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "ai_assistant_access_invoke" {
  name = "${local.name_prefix}-ai-assistant-access-invoke"
  role = aws_iam_role.ai_assistant_access.id

  # Scoped, temporary credentials may only invoke the chat sync API of the AI
  # assistant — nothing else.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.ai_assistant.arn
    }]
  })
}

# ─── AI assistant: the chat sync API invoked with scoped, temporary creds ───

resource "aws_iam_role" "ai_assistant_exec" {
  name = "${local.name_prefix}-ai-assistant-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ai_assistant_basic" {
  role       = aws_iam_role.ai_assistant_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ai_assistant_bedrock" {
  name = "${local.name_prefix}-ai-assistant-bedrock"
  role = aws_iam_role.ai_assistant_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"
    }]
  })
}

resource "null_resource" "ai_assistant_package" {
  triggers = {
    handler_sha = filesha256("${path.module}/src/lambda/ai_assistant/handler.py")
  }

  provisioner "local-exec" {
    command = "bash ${path.module}/scripts/build_lambda_package.sh ${path.module} ai_assistant"
  }
}

data "archive_file" "ai_assistant_zip" {
  type        = "zip"
  source_file = "${path.module}/src/lambda/ai_assistant/handler.py"
  output_path = "${path.module}/.build/ai_assistant.zip"

  depends_on = [null_resource.ai_assistant_package]
}

resource "aws_lambda_function" "ai_assistant" {
  function_name = "${local.name_prefix}-ai-assistant"
  role          = aws_iam_role.ai_assistant_exec.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  filename         = data.archive_file.ai_assistant_zip.output_path
  source_code_hash = data.archive_file.ai_assistant_zip.output_base64sha256

  environment {
    variables = {
      REGION   = var.aws_region
      MODEL_ID = var.bedrock_model_id
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ai-assistant"
  })

  depends_on = [
    aws_iam_role_policy_attachment.ai_assistant_basic,
    aws_iam_role_policy.ai_assistant_bedrock,
  ]
}

# ─── Application: serves the Custom UI and, via the Amazon SDK, performs the ─
# token exchange + STS AssumeRoleWithWebIdentity dance before calling the AI
# assistant's chat sync API ──────────────────────────────────────────────────

resource "aws_iam_role" "application_exec" {
  name = "${local.name_prefix}-application-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "application_basic" {
  role       = aws_iam_role.application_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "application_authn_authz" {
  name = "${local.name_prefix}-application-authn-authz"
  role = aws_iam_role.application_exec.id

  # The Application calls Cognito (Authentication) to authenticate the user,
  # and the trusted token issuer (Authorization, sso-oidc) to exchange the
  # resulting identity token for a trusted token. Note: the subsequent
  # sts:AssumeRoleWithWebIdentity call is unauthenticated federation — it is
  # authorized purely by the OIDC trust policy on ai_assistant_access, not by
  # an IAM permission on this role.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["cognito-idp:InitiateAuth"]
        Resource = aws_cognito_user_pool.authentication.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sso-oidc:CreateTokenWithIAM"]
        Resource = "*"
      },
    ]
  })
}

data "archive_file" "application_zip" {
  type        = "zip"
  output_path = "${path.module}/.build/application.zip"

  source {
    content  = file("${path.module}/src/lambda/application/handler.py")
    filename = "handler.py"
  }

  source {
    content = templatefile("${path.module}/web/index.html.tftpl", {
      project_name = var.project_name
    })
    filename = "index.html"
  }
}

resource "aws_lambda_function" "application" {
  function_name = "${local.name_prefix}-application"
  role          = aws_iam_role.application_exec.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  filename         = data.archive_file.application_zip.output_path
  source_code_hash = data.archive_file.application_zip.output_base64sha256

  environment {
    variables = {
      REGION                     = var.aws_region
      FLOCI_ENDPOINT             = "http://localhost:4566"
      USER_POOL_ID               = aws_cognito_user_pool.authentication.id
      USER_POOL_CLIENT_ID        = aws_cognito_user_pool_client.custom_ui.id
      TRUSTED_TOKEN_ISSUER_ARN   = aws_iam_openid_connect_provider.trusted_token_issuer.arn
      ASSISTANT_ROLE_ARN         = aws_iam_role.ai_assistant_access.arn
      AI_ASSISTANT_FUNCTION_NAME = aws_lambda_function.ai_assistant.function_name
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-application"
  })

  depends_on = [
    aws_iam_role_policy_attachment.application_basic,
    aws_iam_role_policy.application_authn_authz,
  ]
}

resource "aws_lambda_function_url" "application" {
  function_name      = aws_lambda_function.application.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST"]
    allow_headers = ["content-type"]
  }
}

# ─── Distribute traffic: CloudFront in front of the Application ─────────────

resource "aws_cloudfront_distribution" "distribute_traffic" {
  enabled             = true
  comment             = "Distribute traffic for the ${var.project_name} custom UI"
  default_root_object = ""

  origin {
    domain_name = replace(replace(aws_lambda_function_url.application.function_url, "https://", ""), "/", "")
    origin_id   = "application-origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "application-origin"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Content-Type"]
      cookies {
        forward = "all"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = local.common_tags
}
