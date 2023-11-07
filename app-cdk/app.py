
#!/usr/bin/env python3
import aws_cdk as cdk
import os
import json

from app_cdk.app_cdk_stack import AppCdkStack
from app_cdk.pipeline_cdk_stack import PipelineCdkStack
from app_cdk.ecr_cdk_stack import EcrCdkStack
from app_cdk.eks_vpc_cdk_stack import EksVpcCdkStack
from app_cdk.eks_infra_cf_cdk_stack import EksInfraCFStack
from app_cdk.customer_vpc_cdk_stack import CustomerVpcCdkStack
from app_cdk.tgw_vpn_cdk_stack import TransitGatewayVPNStack
from app_cdk.vpn_route_cdk_stack import VpnRouteCdkStack
from app_cdk.nomultus_eks_nodegroup_stack import NoMultusNodeGroupStack   


script_dir = os.path.dirname(os.path.realpath(__file__))
config_path = os.path.join(script_dir, 'app_cdk', 'config', 'variables.json')

with open(config_path, 'r') as config_file:
    config = json.load(config_file)

import sys
if os.getenv('CDK_DEFAULT_REGION') in config.get("AZS")[0] and os.getenv('CDK_DEFAULT_REGION') in config.get("AZS")[1]:
    pass
else:
    print ("Make sure the az you set and the region in aws configure match.")
    sys.exit(1)

app = cdk.App()
AppCdkStack(app, "app-cdk-stack")

env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION'))

EksVpcCdkStack(app, "eks-vpc-cdk-stack", env=env)
EksInfraCFStack(app,"eks-infra-cf-stack", env=env)
NoMultusNodeGroupStack(app, "no-multus-nodegroup-stack", env=env,)


CustomerVpcCdkStack(app, "customer-vpc-cdk-stack", env=env)
TransitGatewayVPNStack(app, "tgw-vpn-cdk-stack", env=env)
VpnRouteCdkStack(app, "vpn-route-cdk-stack", env=env)


EcrCdkStack(app, "ecr-cdk-stack", env=env)
PipelineCdkStack(app, "pipeline-cdk-stack", env=env)

app.synth()