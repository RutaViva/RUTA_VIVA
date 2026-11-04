data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "data_services" {
  name               = "${var.project_name}-nat-data-services-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "data_services_ssm" {
  role       = aws_iam_role.data_services.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "data_services_s3" {
  name = "${var.project_name}-data-services-s3"
  role = aws_iam_role.data_services.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts"
        ]
        Resource = "${aws_s3_bucket.data_lake.arn}/*"
      },
      {
        Effect   = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:ListBucketMultipartUploads"
        ]
        Resource = aws_s3_bucket.data_lake.arn
      }
    ]
  })
}

resource "aws_iam_instance_profile" "data_services" {
  name = "${var.project_name}-nat-data-services-profile"
  role = aws_iam_role.data_services.name
}
