output "cognito_user_pool_id" {
  description = "ID of the Cognito User Pool (Authentication)."
  value       = aws_cognito_user_pool.authentication.id
}

output "cognito_client_id" {
  description = "ID of the Cognito app client used by the Custom UI."
  value       = aws_cognito_user_pool_client.custom_ui.id
}

output "trusted_token_issuer_arn" {
  description = "ARN of the IAM OIDC identity provider modeling the trusted token issuer (Authorization)."
  value       = aws_iam_openid_connect_provider.trusted_token_issuer.arn
}

output "assistant_role_arn" {
  description = "ARN of the scoped IAM role assumed via STS AssumeRoleWithWebIdentity to call the AI assistant."
  value       = aws_iam_role.ai_assistant_access.arn
}

output "ai_assistant_function_name" {
  description = "Name of the AI assistant Lambda function exposing the chat sync API."
  value       = aws_lambda_function.ai_assistant.function_name
}

output "application_function_url" {
  description = "Direct Function URL of the Application backend (serves the Custom UI and the chat API)."
  value       = aws_lambda_function_url.application.function_url
}

output "cloudfront_domain_name" {
  description = "Domain name of the CloudFront distribution that distributes traffic to the Application."
  value       = aws_cloudfront_distribution.distribute_traffic.domain_name
}
