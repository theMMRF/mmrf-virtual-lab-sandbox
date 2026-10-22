data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "sandbox" {
  cidr_block           = "10.86.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = var.name }
}
resource "aws_internet_gateway" "sandbox" {
  vpc_id = aws_vpc.sandbox.id
}
resource "aws_subnet" "nodes" {
  count                   = 2
  vpc_id                  = aws_vpc.sandbox.id
  cidr_block              = cidrsubnet(aws_vpc.sandbox.cidr_block, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name}-${count.index}" }
}
resource "aws_route_table" "sandbox" {
  vpc_id = aws_vpc.sandbox.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.sandbox.id
  }
}
resource "aws_route_table_association" "nodes" {
  count          = 2
  subnet_id      = aws_subnet.nodes[count.index].id
  route_table_id = aws_route_table.sandbox.id
}

resource "aws_iam_role" "cluster" {
  name               = "${var.name}-cluster"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "eks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_eks_cluster" "sandbox" {
  name     = var.name
  role_arn = aws_iam_role.cluster.arn
  version  = var.kubernetes_version
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }
  upgrade_policy { support_type = "STANDARD" }
  vpc_config {
    subnet_ids              = aws_subnet.nodes[*].id
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.operator_cidrs
  }
  depends_on = [aws_iam_role_policy_attachment.cluster]
  lifecycle {
    precondition {
      condition     = split(":", var.operator_role_arn)[4] == var.sandbox_account_id
      error_message = "The operator role must belong to the sandbox account."
    }
  }
}
resource "aws_eks_access_entry" "operator" {
  cluster_name  = aws_eks_cluster.sandbox.name
  principal_arn = var.operator_role_arn
  type          = "STANDARD"
}
resource "aws_eks_access_policy_association" "operator" {
  cluster_name  = aws_eks_cluster.sandbox.name
  principal_arn = aws_eks_access_entry.operator.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
}

resource "aws_iam_role" "nodes" {
  name               = "${var.name}-nodes"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "nodes" {
  for_each   = toset(["AmazonEKSWorkerNodePolicy", "AmazonEKS_CNI_Policy", "AmazonEC2ContainerRegistryReadOnly"])
  role       = aws_iam_role.nodes.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_eks_node_group" "sandbox" {
  cluster_name    = aws_eks_cluster.sandbox.name
  node_group_name = "synthetic"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = aws_subnet.nodes[*].id
  instance_types  = ["m6i.xlarge"]
  ami_type        = "AL2023_x86_64_STANDARD"
  disk_size       = 40
  scaling_config {
    desired_size = 1
    min_size     = 1
    max_size     = 1
  }
  depends_on = [aws_iam_role_policy_attachment.nodes, aws_route_table_association.nodes]
}
resource "aws_eks_addon" "vpc_cni" {
  cluster_name         = aws_eks_cluster.sandbox.name
  addon_name           = "vpc-cni"
  configuration_values = jsonencode({ enableNetworkPolicy = "true" })
}
resource "aws_ecr_repository" "service" {
  for_each             = toset(["frontend", "guppy", "analysis", "proteinpaint", "identity", "seed"])
  name                 = "${var.name}/${each.value}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
}
