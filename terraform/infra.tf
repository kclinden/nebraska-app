#Get VPC by ID
data "aws_vpc" "selected" {
  id = "vpc-077cef3ab0fd02758" # Replace with your VPC ID
}

#get public subnet by id subnet-02802090b0187a15d
data "aws_subnet" "public" {
  id = "subnet-02802090b0187a15d" # Replace with your public subnet ID
}

# Data source to fetch the latest AL2023 AMI
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}


# 4. Create a Security Group for HTTP Traffic
resource "aws_security_group" "web_sg" {
  name        = "HuskerAppWebSG"
  vpc_id      = data.aws_vpc.selected.id
  description = "Allow HTTP inbound traffic"

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 5. Provision the EC2 Instance
resource "aws_instance" "web" {
  ami                  = data.aws_ami.al2023.id
  instance_type        = "t3.small"
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name
  subnet_id            = data.aws_subnet.public.id

  lifecycle {
    ignore_changes = [ami]
  }

  vpc_security_group_ids = [aws_security_group.web_sg.id]

  #auto assign public IP
  associate_public_ip_address = true

  # Render user data with repo and auth settings
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repo_url    = var.app_repo_url
    repo_branch = var.app_repo_branch
  })

  # Ensure the instance replaces when you modify user_data
  user_data_replace_on_change = true

  #set root volume of 16gb and gp3
  root_block_device {
    volume_size = 16
    volume_type = "gp3"
  }

  tags = {
    Name = "Husker-Roster-Webserver"
  }
}

# Output the IP address so you can easily click it!
output "webserver_public_ip" {
  value = aws_instance.web.public_ip
}
