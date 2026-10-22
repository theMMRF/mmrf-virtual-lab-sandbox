output "cluster_name" { value = aws_eks_cluster.sandbox.name }
output "region" { value = var.region }
output "image_repositories" { value = { for name, repo in aws_ecr_repository.service : name => repo.repository_url } }
output "frontend_access" {
  value = "After installing the Helm chart: kubectl -n mmrf-synthetic port-forward service/identity 3081:8080 --address 127.0.0.1"
}
