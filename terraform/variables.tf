variable "sandbox_account_id" {
  description = "The dedicated hackathon account. The provider rejects any other account."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.sandbox_account_id))
    error_message = "Supply a twelve-digit dedicated sandbox account ID."
  }
}
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "mmrf-synthetic"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.name))
    error_message = "Use 3-31 lowercase letters, digits, and hyphens."
  }
}
variable "operator_role_arn" {
  description = "Existing IAM role the operator uses for Kubernetes administration; no credentials are created."
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.+", var.operator_role_arn))
    error_message = "Supply an existing IAM role ARN in the sandbox account."
  }
}
variable "operator_cidrs" {
  description = "Operator/VPN egress CIDRs allowed to reach the EKS API. Workload services remain ClusterIP."
  type        = list(string)
  validation {
    condition     = length(var.operator_cidrs) > 0 && alltrue([for c in var.operator_cidrs : can(cidrhost(c, 0)) && try(tonumber(split("/", c)[1]) >= 24, false)])
    error_message = "Supply IPv4 CIDRs with /24 or narrower masks; unrestricted API access is not supported."
  }
}
variable "kubernetes_version" {
  type    = string
  default = "1.34"
}
