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

class EksInfraCFStack(Stack):
    
    def load_config(self, file_path):
        with open(file_path, 'r') as config_file:
            self.config = json.load(config_file)
            self.key_name = self.config.get("KEY_NAME")

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        self.load_config(config_path)

        eks_vpc_id = ssm.StringParameter.value_from_lookup(self, "EksVpcId")
        eks_vpc = ec2.Vpc.from_lookup(self,"lookupVPC",vpc_id=eks_vpc_id)

        # EKSIamRole
        eks_iam_role = iam.Role(self, "EKSIamRole", assumed_by=iam.ServicePrincipal("eks.amazonaws.com"))
        eks_iam_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSClusterPolicy"))
        eks_iam_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSServicePolicy"))

        # EKS Cluster
        eks_control_security_group = ec2.SecurityGroup(self,"EksControlSecurityGroup",vpc=eks_vpc)
        subnet_ids = [subnet.subnet_id for subnet in eks_vpc.private_subnets + eks_vpc.public_subnets]


        EKSCluster = eks.CfnCluster(self, "EKSCluster",resources_vpc_config=eks.CfnCluster.ResourcesVpcConfigProperty(
            subnet_ids=subnet_ids,
            security_group_ids=[eks_control_security_group.security_group_id],),
        role_arn=eks_iam_role.role_arn,
        )

        user_data = """#!/bin/bash
        sudo amazon-linux-extras install epel -y
        """

        bastion_sg = ec2.SecurityGroup(
            self,
            'BastionSecurityGroup',
            vpc=eks_vpc,
            allow_all_outbound=True,
        )

        bastion_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description='Allow SSH access'
        )

        bastion_instance = ec2.Instance(
            self,
            'BastionInstance',
            vpc=eks_vpc,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.C5,
                ec2.InstanceSize.XLARGE2
            ),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
            ),
            key_name=self.key_name,
            user_data=ec2.UserData.custom(user_data),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=bastion_sg,            
        )

        ssm.StringParameter(self, "EKSClusterName", parameter_name="EKSClusterName", string_value=EKSCluster.ref)        
        ssm.StringParameter(self, "EKSClusterControlSGId", parameter_name="EKSClusterControlSGId", string_value=eks_control_security_group.security_group_id)
        

        CfnOutput(self, "ClusterNameOutput", value=EKSCluster.ref)
        CfnOutput(self, "ClusterControlSecurityGroupOutput", value=eks_control_security_group.security_group_id)
        CfnOutput(self, "SubnetsOutput", value=str(subnet_ids))
        CfnOutput(self, "VpcIdOutput", value=eks_vpc_id)
