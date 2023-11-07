import os
import json

from constructs import Construct
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_eks as eks,
    aws_ssm as ssm,
    aws_autoscaling as autoscaling,
    aws_route53 as route53,
    Duration,
    CfnTag,
    Fn,
    CfnUpdatePolicy,
    CfnOutput,
    aws_lambda as _lambda,
    custom_resources as custom,
    aws_events as events,
    aws_events_targets as targets,
    CustomResource
    
)

# Constants
PARAMETER_NAME = "/aws/service/eks/optimized-ami/1.27/amazon-linux-2/recommended/image_id"
INSTANCE_TYPE = "c5.2xlarge"
BOOTSTRAP_ARGUMENTS = "--kubelet-extra-args '--node-labels=cnf=xyz'" 
NODE_AUTOSCALINGGROUP_DESIRED_CAPACITY = 1
NODE_AUTOSCALINGGROUP_MAX_SIZE = 1
NODE_AUTOSCALINGGROUP_MIN_SIZE = 1
REGION = os.getenv('CDK_DEFAULT_REGION')

script_dir = os.path.dirname(os.path.realpath(__file__))
config_path = os.path.join(script_dir, 'config', 'variables.json')

class NoMultusNodeGroupStack(Stack):


    def load_config(self, file_path):
        with open(file_path, 'r') as config_file:
            self.config = json.load(config_file)
            self.key_name = self.config.get("KEY_NAME")

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.load_config(config_path)

        # Lookup VPC
        eks_vpc_id = ssm.StringParameter.value_from_lookup(self, "EksVpcId")
        cluster_name = ssm.StringParameter.value_from_lookup(self, "EKSClusterName")
        cluster_cp_sg = ssm.StringParameter.value_from_lookup(self, "EKSClusterControlSGId")
        
        eks_vpc = ec2.Vpc.from_lookup(self,"lookupVPC",vpc_id=eks_vpc_id)
        eks_cluster = eks.Cluster.from_cluster_attributes(self, "eks-cluster",
                                                          cluster_name=cluster_name,
                                                          vpc=eks_vpc)
        
        # Route 53 PrivateHostedZone
        
        upf_hosted_zone = route53.PrivateHostedZone(self, "UpfHostedZone",
            zone_name="upf.open5gs.service",
            vpc=eks_vpc,
            comment="privateHostedZone-upf"
        )
                
        amf_hosted_zone = route53.PrivateHostedZone(self, "AmfHostedZone",
            zone_name="amf.open5gs.service",
            vpc=eks_vpc,
            comment="privateHostedZone-amf"
        )

        # Define IAM Role for NodeGroup
        node_instance_role = iam.Role(self, "NodeInstanceRole", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))
        node_instance_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSWorkerNodePolicy"))
        node_instance_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKS_CNI_Policy"))
        node_instance_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"))
        node_instance_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSCloudFormationFullAccess"))

        # Define IAM Instance Profile for NodeGroup
        cfn_instance_profile = iam.CfnInstanceProfile(self, "NodeInstanceProfile",roles=[node_instance_role.role_name],path="/")

        # NodeSecurityGroup
        node_security_group = ec2.CfnSecurityGroup(self, "NodeSecurityGroup",
            group_description="Security group for all nodes in the cluster",
            tags=[CfnTag(
                key="key",
                value="value"
            )],
            vpc_id=eks_vpc_id
        )

        ec2.CfnSecurityGroupIngress(
            self, "NodeSecurityGroupIngress",
            description="Allow node to communicate with each other",
            group_id=node_security_group.ref,
            ip_protocol="-1",
            from_port=0,
            to_port=65535,
            source_security_group_id=node_security_group.ref  
        )

        ec2.CfnSecurityGroupIngress(
            self, "ClusterControlPlaneSecurityGroupIngress",
            description="Allow pods to communicate with the cluster API Server",
            from_port=443,
            group_id=cluster_cp_sg,
            ip_protocol="tcp",
            source_security_group_id=node_security_group.ref,
            to_port=443
        )
        ec2.CfnSecurityGroupEgress(
            self, "ControlPlaneEgressToNodeSecurityGroup",
            description="Allow the cluster control plane to communicate with worker Kubelet and pods",
            destination_security_group_id=node_security_group.ref,
            from_port=1025,
            group_id=cluster_cp_sg,
            ip_protocol="tcp",
            to_port=65535
        )
        ec2.CfnSecurityGroupEgress(
            self, "ControlPlaneEgressToNodeSecurityGroupOn443",
            description="Allow the cluster control plane to communicate with pods running extension API servers on port 443",
            destination_security_group_id=node_security_group.ref,
            from_port=443,
            group_id=cluster_cp_sg,
            ip_protocol="tcp",
            to_port=443
        )
        ec2.CfnSecurityGroupIngress(
            self, "NodeSecurityGroupFromControlPlaneIngress",
            description="Allow worker Kubelets and pods to receive communication from the cluster control plane",
            from_port=1025,
            group_id=node_security_group.ref,
            ip_protocol="tcp",
            source_security_group_id=cluster_cp_sg,
            to_port=65535
        )
        ec2.CfnSecurityGroupIngress(
            self, "NodeSecurityGroupFromControlPlaneOn443Ingress",
            description="Allow pods running extension API servers on port 443 to receive communication from cluster control plane",
            from_port=443,
            group_id=node_security_group.ref,
            ip_protocol="tcp",
            source_security_group_id=cluster_cp_sg,
            to_port=443
        )
        
        ec2.CfnSecurityGroupIngress(
            self, "NodeSecurityGroupSSHIngress",
            description="Allow SSH traffic",
            from_port=-1,
            group_id=node_security_group.ref,
            ip_protocol="icmp",
            to_port=-1,
            cidr_ip="0.0.0.0/0"
        )
        
        ec2.CfnSecurityGroupIngress(
            self, "NodeSecurityGroupSCTPIngress",
            description="Allow SSH traffic",
            from_port=-1,
            group_id=node_security_group.ref,
            ip_protocol="132",
            to_port=-1,
            cidr_ip="0.0.0.0/0"
        )
        
        ec2.CfnSecurityGroupIngress(
            self, "NodeSecurityGroupUDPIngress",
            description="Allow UDP 2152 traffic",
            from_port=2152,
            group_id=node_security_group.ref,
            ip_protocol="udp",
            to_port=2152,
            cidr_ip="0.0.0.0/0"
        )

        # Fetch the node image ID from the SSM Parameter Store   
        node_image_id = ssm.StringParameter.from_string_parameter_attributes(self, "NodeImageId", parameter_name=PARAMETER_NAME, value_type=ssm.ParameterValueType.AWS_EC2_IMAGE_ID)
        
        # User dat script for EC2 instance
        my_user_data = f"""#!/bin/bash
            set -o xtrace
            echo "net.ipv4.conf.default.rp_filter = 0" | tee -a /etc/sysctl.conf
            echo "net.ipv4.conf.all.rp_filter = 0" | tee -a /etc/sysctl.conf
            sudo sysctl -p
            sleep 30
            ls /sys/class/net/ > /tmp/ethList;cat /tmp/ethList |while read line ; do sudo ifconfig $line up; done
            grep eth /tmp/ethList |while read line ; do echo "ifconfig $line up" >> /etc/rc.d/rc.local; done
            systemctl enable rc-local
            chmod +x /etc/rc.d/rc.local
            /etc/eks/bootstrap.sh {cluster_name} {BOOTSTRAP_ARGUMENTS}
            /opt/aws/bin/cfn-signal --exit-code $? \
                     --stack  {id} \
                     --resource NodeGroup  \
                     --region {REGION}  

                            """ 
        # Define the launch template data for EC2 instance
        launch_template_data_property = ec2.CfnLaunchTemplate.LaunchTemplateDataProperty(
            instance_type=INSTANCE_TYPE,
            key_name=self.key_name,
            block_device_mappings=[
                ec2.CfnLaunchTemplate.BlockDeviceMappingProperty(
                    device_name="/dev/xvda",
                    ebs=ec2.CfnLaunchTemplate.EbsProperty(
                        delete_on_termination=True,
                        volume_size=50,
                        volume_type="gp2"
                    ))
            ],
            user_data=Fn.base64(my_user_data),
            # iam_instance_profile=ec2.CfnLaunchTemplate.IamInstanceProfileProperty(
                # arn=cfn_instance_profile.attr_arn,
            # ),
            image_id=node_image_id.string_value, 
            security_group_ids=[node_security_group.ref],
            metadata_options=ec2.CfnLaunchTemplate.MetadataOptionsProperty(
                http_put_response_hop_limit=2,
                http_endpoint="enabled",
                http_tokens="optional"
            ),
            
        )
        
        # Create the launch template for EC2 instances
        node_launch_template = ec2.CfnLaunchTemplate(self, "NodeLaunchTemplate",
            launch_template_data=launch_template_data_property
        )

        ng = eks.Nodegroup(
            self,
            "NodeGroup",
            cluster=eks_cluster,
            min_size=NODE_AUTOSCALINGGROUP_MIN_SIZE,
            desired_size=NODE_AUTOSCALINGGROUP_DESIRED_CAPACITY,
            max_size=NODE_AUTOSCALINGGROUP_MAX_SIZE,
            launch_template_spec={
                "id": node_launch_template.ref,
                "version": node_launch_template.attr_latest_version_number
            },
            subnets=ec2.SubnetSelection(
                one_per_az=True,
                subnets=[eks_vpc.private_subnets[0]],
            ),
        )

        ssm.StringParameter(self, "SSMNGRoleArn", parameter_name="NGRoleArn", string_value=ng.role.role_arn)

        CfnOutput(self, "NodeGroupNameOutput", value=ng.nodegroup_name)
        CfnOutput(self, "NodeGroupRoleOutput", value=ng.role.role_arn)
        CfnOutput(self, "ClusterNameOutput", value=cluster_name)
        CfnOutput(self, "UpfHostedZoneIdOutput", value=upf_hosted_zone.hosted_zone_id)
        CfnOutput(self, "AmfHostedZoneIdOutput", value=amf_hosted_zone.hosted_zone_id)