from constructs import Construct
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    CfnTag,
    CfnOutput
)

# Configuration constants
BGP_ASN = 65016

class TransitGatewayVPNStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Retrieve VPC using eks_vpc_id
        eks_vpc_id = ssm.StringParameter.value_from_lookup(self, "EksVpcId")
        eks_vpc = ec2.Vpc.from_lookup(self, "LookupVPC", vpc_id=eks_vpc_id)

        cgw_ip = ssm.StringParameter.value_from_lookup(self, "CustomerGWInstanceEIP")


        # Create a Transit Gateway
        cfn_tgw = ec2.CfnTransitGateway(self, "MyTGW")

        ssm.StringParameter(self, "SSMTgwId", parameter_name="TgwId", string_value=cfn_tgw.ref)

        # Retrieve necessary values for Transit Gateway Attachment
        tgw_subnet = eks_vpc.private_subnets[0].subnet_id

        # Attach VPC to Transit Gateway
        ec2.CfnTransitGatewayAttachment(self, "TGWAttachment",
            subnet_ids=[tgw_subnet],
            transit_gateway_id=cfn_tgw.ref,
            vpc_id=eks_vpc_id,
        )

        # Create Customer Gateway for VPN
        cgw = ec2.CfnCustomerGateway(self, 'CustomerGW',
            bgp_asn=BGP_ASN,
            ip_address=cgw_ip,
            type="ipsec.1"
        )

        # Create VPN Connection
        ec2.CfnVPNConnection(self, "Site2SiteVPN",
            transit_gateway_id=cfn_tgw.ref,
            customer_gateway_id=cgw.ref,
            static_routes_only=False,
            type="ipsec.1",
            vpn_tunnel_options_specifications=[
                ec2.CfnVPNConnection.VpnTunnelOptionsSpecificationProperty(
                    pre_shared_key="strongswan_awsvpn",
                    tunnel_inside_cidr="169.254.11.0/30"
                ),
                ec2.CfnVPNConnection.VpnTunnelOptionsSpecificationProperty(
                    pre_shared_key="strongswan_awsvpn",
                    tunnel_inside_cidr="169.254.12.0/30"
                )
            ]
        )

        # Output
        CfnOutput(self, "TransitGatewayId", value=cfn_tgw.ref)