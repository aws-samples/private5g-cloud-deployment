from constructs import Construct
from aws_cdk import (
    Stack,
    aws_ecr as ecr,
    aws_ssm as ssm,
    RemovalPolicy,
    CfnOutput,
)

class EcrCdkStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        ecr_repository = ecr.Repository(self, 'my-open5gs', removal_policy=RemovalPolicy.DESTROY)

        ssm.StringParameter(self, "SSMEcrRepositoryUri", parameter_name="EcrRepositoryUri", string_value=ecr_repository.repository_uri)

        CfnOutput(
            self,
            "EcrRepositoryUriOutput",
            value=ecr_repository.repository_uri
        )
