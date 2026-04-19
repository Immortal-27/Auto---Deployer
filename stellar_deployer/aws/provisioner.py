import boto3
import time
import os
import sys

def provision_ec2_instance(key_name: str, instance_type: str = 't3.medium', ami_id: str = 'ami-0c7217cdde317cfec') -> str:
    """
    Provisions an EC2 instance with proper Security Groups for Stellar Core.
    ami_id defaults to Ubuntu 22.04 LTS in us-east-1 (you might want to parameterize this based on the region).
    """
    # Explicitly creating an EC2 client and resource. Boto3 automatically picks up AWS credentials from:
    # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    
    # Let users know if AWS credentials are not set
    if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        print("Warning: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY is not set.")
        print("Boto3 will attempt to use default credentials (e.g., ~/.aws/credentials if they exist).")
    
    ec2_client = boto3.client('ec2')
    ec2_resource = boto3.resource('ec2')
    
    sg_name = 'stellar-core-sg'
    
    # 1. Create or get Security Group
    try:
        response = ec2_client.describe_security_groups(GroupNames=[sg_name])
        sg_id = response['SecurityGroups'][0]['GroupId']
        print(f"Using existing Security Group: {sg_name} ({sg_id})")
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidGroup.NotFound' in str(e):
            print(f"Creating Security Group: {sg_name}")
            response = ec2_client.create_security_group(
                GroupName=sg_name,
                Description='Security group for Stellar Core Node'
            )
            sg_id = response['GroupId']
            
            # Add Ingress Rules
            ec2_client.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    # SSH
                    {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                    # Stellar Peers
                    {'IpProtocol': 'tcp', 'FromPort': 11625, 'ToPort': 11625, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                    # Stellar HTTP Admin (restricted to localhost — use SSH tunnel for access)
                    {'IpProtocol': 'tcp', 'FromPort': 11626, 'ToPort': 11626, 'IpRanges': [{'CidrIp': '127.0.0.1/32'}]}
                ]
            )
            print("Security Group rules added (Ports 22, 11625, 11626).")
        else:
            raise e

    # 2. Launch the EC2 Instance
    print(f"Launching instance (Type: {instance_type}, AMI: {ami_id})...")
    instances = ec2_resource.create_instances(
        ImageId=ami_id,
        InstanceType=instance_type,
        KeyName=key_name,
        SecurityGroupIds=[sg_id],
        MinCount=1,
        MaxCount=1,
        BlockDeviceMappings=[
            {
                'DeviceName': '/dev/sda1',
                'Ebs': {
                    'VolumeSize': 100, # 100 GB enough for basic node. A full history node needs more.
                    'VolumeType': 'gp3',
                }
            }
        ]
    )
    
    instance = instances[0]
    print(f"Instance starting: {instance.id}")
    
    # Wait for the instance to enter 'running' state
    instance.wait_until_running()
    instance.reload()
    
    print(f"Instance is running. Public IP: {instance.public_ip_address}")
    
    # Wait for status checks to pass before indicating it's ready
    print("Waiting for instance status checks (this may take a few minutes)...")
    waiter = ec2_client.get_waiter('instance_status_ok')
    waiter.wait(InstanceIds=[instance.id])
    print("Instance ready!")

    return instance.public_ip_address
