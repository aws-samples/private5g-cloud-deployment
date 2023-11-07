import os
import json

from constructs import Construct
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_eks as eks,
    aws_ssm as ssm,
    CfnTag,
    Fn,
    CfnOutput
)

script_dir = os.path.dirname(os.path.realpath(__file__))
config_path = os.path.join(script_dir, 'config', 'variables.json')

class CustomerVpcCdkStack(Stack):


    def load_config(self, file_path):
        with open(file_path, 'r') as config_file:
            self.config = json.load(config_file)
            self.key_name = self.config.get("KEY_NAME")
            self.eks_vpc_cidr = self.config.get("VPC_CIDR")
            self.customer_vpc_cidr = self.config.get("CUSTOMER_VPC_CIDR")

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.load_config(config_path)

        # Create customer VPC with subnets
        customer_vpc = ec2.Vpc(
            self,
            "CustomerVPC",
            ip_addresses=ec2.IpAddresses.cidr(self.customer_vpc_cidr),
            enable_dns_hostnames=True,
            enable_dns_support=True,
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="PrivateSubnet",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ]
        )
        
        ssm.StringParameter(self, "SSMCustomerVPCId", parameter_name="CustomerVpcId", string_value=customer_vpc.vpc_id)

        # Create security group for customer RAN
        customer_ran_sg = ec2.SecurityGroup(
            self,
            'CustomerRanSecurityGroup',
            vpc=customer_vpc,
            allow_all_outbound=True,
        )

        # Add ingress rules to the security group
        customer_ran_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.all_traffic(),
            description='Allow all traffic'
        )

        ubuntu_machine_image = ec2.MachineImage.from_ssm_parameter(
          parameter_name='/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id'
)

        ransim_user_data = """#!/bin/bash
            sudo apt update -y
            sudo apt upgrade -y
            sudo apt install git -y

            cd ~
            git clone https://github.com/aligungr/UERANSIM

            sudo apt install make -y
            sudo apt install gcc -y
            sudo apt install g++ -y

            sudo apt install libsctp-dev lksctp-tools -y

            sudo apt install iproute2 -y
            sudo snap install cmake --classic

            cd ~/UERANSIM
            make -j2
        """
        # Create EC2 instance for customer RAN
        ec2.Instance(
            self,
            'CustomerRANInstance',
            vpc=customer_vpc,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.C5,
                ec2.InstanceSize.LARGE
            ),
            machine_image=ubuntu_machine_image,
            allow_all_outbound=True,
            key_name=self.key_name,
            user_data=ec2.UserData.custom(ransim_user_data),
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_group=customer_ran_sg,
        )

        # Create user data script for GW instance
        gw_user_data = """#!/bin/bash
        sudo amazon-linux-extras install epel -y
        sudo yum install strongswan -y
        sudo yum install quagga -y
        """

        # Create security group for customer GW
        customer_gw_sg = ec2.SecurityGroup(
            self,
            'CustomerGWSecurityGroup',
            vpc=customer_vpc,
            allow_all_outbound=True,
        )

        # Add ingress rules to the security group
        customer_gw_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description='Allow SSH access'
        )
        customer_gw_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.udp(500),
            description='allow vpn tunnel udp(ISAKMP)'
        )
        customer_gw_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.udp(4500),
            description='allow vpn tunnel udp(IPsec NAT)'
        )
        customer_gw_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.icmp_ping(),
            description='allow icmp'
        )      
        customer_gw_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.customer_vpc_cidr), 
            connection=ec2.Port.all_traffic(), 
            description='allow customer vpc'
            )
        customer_gw_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.eks_vpc_cidr),
            connection=ec2.Port.all_traffic(),
            description='allow EKS vpc')
        

        # Create EC2 instance for customer GW
        gw_instance = ec2.Instance(
            self,
            'CustomerGWInstance',
            vpc=customer_vpc,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.C5,
                ec2.InstanceSize.XLARGE2
            ),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
            ),
            allow_all_outbound=True,
            key_name=self.key_name,
            user_data=ec2.UserData.custom(gw_user_data),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=customer_gw_sg,
            source_dest_check=False
        )

        # Allocate an Elastic IP
        eip = ec2.CfnEIP(self, "CustomerGWInstanceEIP")

        # Associate the Elastic IP with the instance
        ec2.CfnEIPAssociation(
            self,
            "CustomerGWInstanceEIPAssociation",
            instance_id=gw_instance.instance_id,
            eip=eip.ref
        )
        
        ssm.StringParameter(self, "SSMCustomerGWInstanceEIP", parameter_name="CustomerGWInstanceEIP", string_value=eip.attr_public_ip)        
        ssm.StringParameter(self, "SSMCustomerGWInstanceId", parameter_name="CustomerGWInstanceId", string_value=gw_instance.instance_id)        

        # Output
        CfnOutput(
            self,
            "CustomerVPCIdOutput",
            value=customer_vpc.vpc_id
        )
        CfnOutput(
            self,
            "CustomerGWInstanceEIPOutput",
            value=eip.attr_public_ip
        )