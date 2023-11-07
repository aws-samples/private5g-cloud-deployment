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

class VpnRouteCdkStack(Stack):

    def load_config(self, file_path):
        with open(file_path, 'r') as config_file:
            self.config = json.load(config_file)
            self.eks_vpc_cidr = self.config.get("VPC_CIDR")
            self.customer_vpc_cidr = self.config.get("CUSTOMER_VPC_CIDR")

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.load_config(config_path)
        # Retrieve VPCs using provided IDs
        
        eks_vpc_id = ssm.StringParameter.value_from_lookup(self, "EksVpcId")
        my_vpc = ec2.Vpc.from_lookup(self, "LookupVPC", vpc_id=eks_vpc_id)

        eks_tgw_id = eks_vpc_id = ssm.StringParameter.value_from_lookup(self, "TgwId")
        customer_gw_instance_id = ssm.StringParameter.value_from_lookup(self, "CustomerGWInstanceId")

        customer_vpc_id = ssm.StringParameter.value_from_lookup(self, "CustomerVpcId")
        customer_vpc = ec2.Vpc.from_lookup(self,"lookupCVPC",vpc_id=customer_vpc_id)

        # Retrieve route table IDs from the VPCs
        my_vpc_to_tgw_route_table_id = my_vpc.private_subnets[0].route_table.route_table_id
        customer_vpc_to_tgw_route_table_id = customer_vpc.private_subnets[0].route_table.route_table_id

        # Add routes from EKS VPC to customer VPC via Transit Gateway
        ec2.CfnRoute(self, "EKSRouteToCustomer",
                     route_table_id=my_vpc_to_tgw_route_table_id,
                     destination_cidr_block=self.customer_vpc_cidr,                     
                     transit_gateway_id=eks_tgw_id)
        

        # # Add routes from customer VPC to EKS VPC via Transit Gateway and a network interface
        # ec2.CfnRoute(self, "CustomerRouteToEKS",
        #              route_table_id=customer_vpc_to_tgw_route_table_id,
        #              destination_cidr_block="0.0.0.0/0",
        #              instance_id=customer_gw_instance_id
        #              )

        # Outputs for route table IDs

