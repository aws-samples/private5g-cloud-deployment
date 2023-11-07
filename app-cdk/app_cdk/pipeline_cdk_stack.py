import os
from constructs import Construct
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_codecommit as codecommit,
    aws_codepipeline as codepipeline,
    aws_codebuild as codebuild,
    aws_codepipeline_actions as codepipeline_actions,
    aws_iam as iam,
    aws_ssm as ssm
)

IMAGE_TAG="v265"

class PipelineCdkStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        ecr_repository_uri = ssm.StringParameter.value_from_lookup(self, "EcrRepositoryUri")
        cluster_name = ssm.StringParameter.value_from_lookup(self, "EKSClusterName")
        
        # # create new role for codebuild
        codebuild_role=iam.Role(
            self,
            "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com")
        )
        codebuild_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSClusterPolicy"))
        codebuild_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSWorkerNodePolicy"))
        codebuild_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSServicePolicy"))
        codebuild_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeCommitFullAccess"))
        codebuild_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodePipeline_FullAccess"))
        codebuild_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryFullAccess"))

        repo = codecommit.Repository(
            self,
            "Private5gCloudDeployment",
            repository_name="private5g-cloud-deployment",
            description="This repository folder houses the core components of our project, encompassing the intricate process of deploying a private 5G network infrastructure within a cloud environment. This comprehensive project includes infrastructure provisioning, Kubernetes (EKS) deployment, and the orchestration of 5G Pods.",
        )
        

        pipeline = codepipeline.Pipeline(
            self, "Private5GPipeline", cross_account_keys=False
        )

        codeQualityBuild = codebuild.PipelineProject(
            self, "CodeQuality",
            build_spec=codebuild.BuildSpec.from_source_filename(
            "./buildspec_test.yaml"
            ),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_6_0,
                privileged=True,
                compute_type=codebuild.ComputeType.LARGE,
                environment_variables={
                    "IMAGE_TAG": codebuild.BuildEnvironmentVariable(
                        type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value=IMAGE_TAG
                    ),
                    "IMAGE_REPO_URI": codebuild.BuildEnvironmentVariable(
                        type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value=ecr_repository_uri
                    ),
                    "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(
                        type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value=os.environ["CDK_DEFAULT_REGION"]
                    )
                }
            ),
            role=codebuild_role,
        )

        docker_build_project = codebuild.PipelineProject(
            self, "DockerBuild",
            build_spec=codebuild.BuildSpec.from_source_filename("./buildspec_docker.yaml"),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_5_0,
                privileged=True,
                compute_type=codebuild.ComputeType.LARGE,
                environment_variables={
                    "IMAGE_TAG": codebuild.BuildEnvironmentVariable(
                        type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value=IMAGE_TAG
                    ),
                    "IMAGE_REPO_URI": codebuild.BuildEnvironmentVariable(
                        type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value=ecr_repository_uri
                    ),
                    "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(
                        type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value=os.environ["CDK_DEFAULT_REGION"]
                    ),
                    "CLUSTER_NAME": codebuild.BuildEnvironmentVariable(
                        type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value=cluster_name
                    ),
                }
            ),
            role=codebuild_role,
        )

        source_output = codepipeline.Artifact()
        unit_test_output = codepipeline.Artifact()
        docker_build_output = codepipeline.Artifact()
        
        source_action = codepipeline_actions.CodeCommitSourceAction(
            action_name="CodeCommit",
            repository=repo,
            output=source_output,
            code_build_clone_output=True,
            branch="main"
        )

        pipeline.add_stage(
            stage_name="Source",
            actions=[source_action]
        )

        build_action = codepipeline_actions.CodeBuildAction(
            action_name="Unit-Test",
            project=codeQualityBuild,
            input=source_output, 
            outputs=[unit_test_output]
        )
        
        pipeline.add_stage(
            stage_name="Code-Quality-Testing",
            actions=[build_action]
        )        
        
        docker_build_action = codepipeline_actions.CodeBuildAction(
            action_name="Docker-Build",
            project=docker_build_project,
            input=source_output,
            outputs=[docker_build_output]
        )

        pipeline.add_stage(
            stage_name="Docker-Build",
            actions=[docker_build_action]
        )

        ssm.StringParameter(self, "SSMCodeCommitUri", parameter_name="CodeCommitUri", string_value=repo.repository_clone_url_http)
        ssm.StringParameter(self, "SSMCodeBuildRoleArn", parameter_name="CodeBuildRoleArn", string_value=codebuild_role.role_arn)

        CfnOutput(
            self, 'CodeCommitRepositoryUrl',
            value=repo.repository_clone_url_http
        )

        CfnOutput(
            self, 'CodeBuildRoleArnOutput',
            value=codebuild_role.role_arn
        )