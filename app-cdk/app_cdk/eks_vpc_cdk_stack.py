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
    CfnOutput
)

script_dir = os.path.dirname(os.path.realpath(__file__))
config_path = os.path.join(script_dir, 'config', 'variables.json')

class EksVpcCdkStack(Stack):

    def load_config(self, file_path):
        with open(file_path, 'r') as config_file:
            self.config = json.load(config_file)
            self.vpc_cidr = self.config.get("VPC_CIDR")
            self.public_subnet_az1_cidr = self.config.get("PUBLIC_SUBNET_AZ1_CIDR")
            self.public_subnet_az2_cidr = self.config.get("PUBLIC_SUBNET_AZ2_CIDR")
            self.private_subnet_az1_cidr = self.config.get("PRIVATE_SUBNET_AZ1_CIDR")
            self.private_subnet_az2_cidr = self.config.get("PRIVATE_SUBNET_AZ2_CIDR")
            self.azs = self.config.get("AZS")
            self.key_name = self.config.get("KEY_NAME")
        
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.load_config(config_path)

        # Create VPC
        self.vpc = ec2.CfnVPC(
            self, "MyVPC",
            cidr_block=self.vpc_cidr,
            enable_dns_support=True,
            enable_dns_hostnames=True
        )
        eks_vpc_id = self.vpc.ref
        ssm.StringParameter(self, "EksVpcId", parameter_name="EksVpcId", string_value=eks_vpc_id)
        # ssm.StringParameter.value_from_lookup(self, "EksVpcId")

        # Subnet configurations
        public_subnet_az1 = ec2.CfnSubnet(self,
                                          "PublicSubnetAz1",availability_zone=self.azs[0],
                                          cidr_block=self.public_subnet_az1_cidr,
                                          vpc_id=eks_vpc_id)
        public_subnet_az2 = ec2.CfnSubnet(self,
                                          "PublicSubnetAz2",availability_zone=self.azs[1],
                                          cidr_block=self.public_subnet_az2_cidr,
                                          vpc_id=eks_vpc_id)
        private_subnet_az1 = ec2.CfnSubnet(self,
                                           "PrivateSubnetAz1",availability_zone=self.azs[0],
                                           cidr_block=self.private_subnet_az1_cidr,
                                           vpc_id=eks_vpc_id)
        private_subnet_az2 = ec2.CfnSubnet(self,
                                           "PrivateSubnetAz2",availability_zone=self.azs[1],
                                           cidr_block=self.private_subnet_az2_cidr,
                                           vpc_id=eks_vpc_id)

        public_subnet_az1_id = public_subnet_az1.ref
        public_subnet_az2_id = public_subnet_az2.ref
        private_subnet_az1_id = private_subnet_az1.ref
        private_subnet_az2_id = private_subnet_az2.ref
        
        my_vpc = ec2.Vpc.from_vpc_attributes(self, "my_vpc", availability_zones=self.azs, vpc_id=eks_vpc_id)
        
        # Create Internet Gateway and attach to VPC
        cfn_igw = ec2.CfnInternetGateway(self, "MyCfnInternetGateway", tags=[CfnTag(
            key="Name",
            value=f'igw-{id}'
        )])
        my_igw_id = cfn_igw.ref
        ec2.CfnVPCGatewayAttachment(
            self,
            "MyCfnVPCGatewayAttachment",
            vpc_id=eks_vpc_id,
            internet_gateway_id=my_igw_id
        )

        # Create public route table
        public_route_table = ec2.CfnRouteTable(
            self,
            "PublicRouteTable",
            vpc_id=eks_vpc_id,
            tags=[CfnTag(
                key="Name",
                value=f'publicRouteTable-{id}'
            )]
        )
        ec2.CfnRoute(
            self,
            "PublicDefaultRoute",
            route_table_id=public_route_table.ref,
            destination_cidr_block="0.0.0.0/0",
            gateway_id=my_igw_id
        )

        # PublicRtAssoc
        ec2.CfnSubnetRouteTableAssociation(
            self,
            "PublicAz1RtAssoc",
            route_table_id=public_route_table.ref,
            subnet_id=public_subnet_az1_id
        )
        ec2.CfnSubnetRouteTableAssociation(
            self,
            "PublicAz2RtAssoc",
            route_table_id=public_route_table.ref,
            subnet_id=public_subnet_az2_id
        )

        # Create NAT Gateways and private route tables
        EipNatGwAz1 = ec2.CfnEIP(self, "EipNatGwAz1", domain=eks_vpc_id)
        EipNatGwAz2 = ec2.CfnEIP(self, "EipNatGwAz2", domain=eks_vpc_id)

        NatGatewayAz1 = ec2.CfnNatGateway(
            self,
            "NatGatewayAz1",
            subnet_id=public_subnet_az1_id,
            allocation_id=EipNatGwAz1.attr_allocation_id,
            tags=[CfnTag(
                key="Name",
                value=f'natgwAz1-{id}'
            )]
        )
        NatGatewayAz2 = ec2.CfnNatGateway(
            self,
            "NatGatewayAz2",
            subnet_id=public_subnet_az2_id,
            allocation_id=EipNatGwAz2.attr_allocation_id,
            tags=[CfnTag(
                key="Name",
                value=f'natgwAz2-{id}'
            )]
        )

        # PrivateSubnet
        PrivateAz1SubnetRt = ec2.CfnRouteTable(self, "PrivateRouteTableAz1",vpc_id=eks_vpc_id,
            tags=[CfnTag(
                key="Name",
                value=f'PrivateRouteTableAz1-{id}'
            )]
        )
        PrivateAz2SubnetRt = ec2.CfnRouteTable(self, "PrivateRouteTableAz2",vpc_id=eks_vpc_id,
            tags=[CfnTag(
                key="Name",
                value=f'PrivateRouteTableAz2-{id}'
            )]
        )

        PrivateAz1SubnetRt_id = PrivateAz1SubnetRt.ref
        PrivateAz2SubnetRt_id = PrivateAz2SubnetRt.ref

        # PrivateDfltRt
        ec2.CfnRoute(
            self,
            "PrivateDefaultRouteAz1",
            route_table_id=PrivateAz1SubnetRt_id,
            destination_cidr_block="0.0.0.0/0",
            nat_gateway_id=NatGatewayAz1.ref
        )
        ec2.CfnRoute(
            self,
            "PrivateDefaultRouteAz2",
            route_table_id=PrivateAz2SubnetRt_id,
            destination_cidr_block="0.0.0.0/0",
            nat_gateway_id=NatGatewayAz2.ref
        )

        # PrivateRtAssoc
        ec2.CfnSubnetRouteTableAssociation(
            self,
            "PrivateRouteTableAssocAz1",
            route_table_id=PrivateAz1SubnetRt_id,
            subnet_id=private_subnet_az1_id
        )
        ec2.CfnSubnetRouteTableAssociation(
            self,
            "PrivateRouteTableAssocAz2",
            route_table_id=PrivateAz2SubnetRt_id,
            subnet_id=private_subnet_az2_id
        )

        CfnOutput(
            self,
            "VpcIdOutput",
            value=eks_vpc_id
            )