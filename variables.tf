variable "project_name" {
  description = "Project name used as prefix for all resources."
  type        = string
  default     = "floci-ai-assistant-custom-ui"
}

variable "aws_region" {
  description = "AWS region (simulated by floci)."
  type        = string
  default     = "us-east-1"
}

variable "cognito_user_pool_name" {
  description = "Name of the Cognito User Pool used for authentication (identity provider)."
  type        = string
  default     = "ai-assistant-users"
}

variable "bedrock_model_id" {
  description = "Bedrock foundation model id used by the AI assistant's chat sync API."
  type        = string
  default     = "amazon.titan-text-express-v1"
}

variable "oidc_thumbprint" {
  description = "Placeholder TLS thumbprint for the IAM OIDC identity provider that models the trusted token issuer (Authorization). Floci does not validate certificate thumbprints."
  type        = string
  default     = "9e99a48a9960b14926bb7f3b02e22da2b0ab7280"
}
