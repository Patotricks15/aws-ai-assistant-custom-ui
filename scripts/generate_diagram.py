"""Generates docs/architecture.drawio for the AI Assistant with Custom UI project
using drawpyo.

Run with: python3 scripts/generate_diagram.py
"""
import os

import drawpyo

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")

AWS4_BASE = (
    "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;strokeColor=none;"
    "dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
    "fontSize=11;fontStyle=0;aspect=fixed;pointerEvents=1;"
)

# Category fill colors (AWS4 stencil set).
COMPUTE = "#ED7100"
SECURITY = "#DD344C"
ARTIFICIAL_INTELLIGENCE = "#01A88D"
NEUTRAL = "#232F3E"
APPLICATION_INTEGRATION = "#E7157B"


def aws_style(icon_name, fill_color):
    return f"{AWS4_BASE}fillColor={fill_color};shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{icon_name};"


def add_node(page, name, x, y, icon_name, fill_color, width=64, height=64):
    node = drawpyo.diagram.Object(page=page, value=name)
    node.position = (x, y)
    node.geometry.width = width
    node.geometry.height = height
    node.apply_style_string(aws_style(icon_name, fill_color))
    return node


def add_generic_node(page, name, x, y, width=120, height=50):
    """Non-AWS / generic box (used for Custom UI, Amazon SDK)."""
    node = drawpyo.diagram.Object(page=page, value=name)
    node.position = (x, y)
    node.geometry.width = width
    node.geometry.height = height
    node.apply_style_string(
        "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;"
        "fontSize=10;fontColor=#7F6000;align=center;"
    )
    return node


def add_aws_cloud_group(page, name, x, y, width, height):
    group = drawpyo.diagram.Object(page=page, value=name)
    group.position = (x, y)
    group.geometry.width = width
    group.geometry.height = height
    group.apply_style_string(
        "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_aws_cloud_alt;"
        "strokeColor=#232F3E;fillColor=none;verticalAlign=top;align=left;"
        "spacingLeft=30;fontColor=#232F3E;dashed=0;"
    )
    return group


def add_highlight_group(page, name, x, y, width, height):
    """Inner highlighted sub-box grouping Application, Custom UI, Amazon SDK."""
    group = drawpyo.diagram.Object(page=page, value=name)
    group.position = (x, y)
    group.geometry.width = width
    group.geometry.height = height
    group.apply_style_string(
        "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_security_group;"
        "strokeColor=#ED7100;fillColor=#FFF7EE;verticalAlign=top;align=left;"
        "spacingLeft=30;fontColor=#ED7100;dashed=0;"
    )
    return group


def add_edge(page, source, target, label=None):
    edge = drawpyo.diagram.Edge(page=page, source=source, target=target, label=label)
    edge.waypoints = "orthogonal"
    edge.endArrow = "block"
    edge.startArrow = "none"
    edge.strokeColor = "#545B64"
    return edge


def build_diagram():
    file = drawpyo.File()
    file.file_name = "architecture.drawio"
    file.file_path = OUTPUT_DIR

    page = drawpyo.Page(file=file)
    page.name = "AI Assistant with Custom UI"

    user = add_node(page, "User", 20, 260, "client", NEUTRAL)

    aws_cloud = add_aws_cloud_group(page, "AWS Cloud", 180, 40, 980, 540)

    distribute_traffic = add_node(page, "Distribute traffic\n(CloudFront)", 220, 260, "cloudfront", APPLICATION_INTEGRATION)

    # Inner highlighted box grouping Application, Custom UI, Amazon SDK.
    app_group = add_highlight_group(page, "Application", 420, 160, 300, 300)
    application = add_node(page, "Application\n(Lambda)", 460, 220, "lambda_function", COMPUTE)
    custom_ui = add_generic_node(page, "Custom UI", 620, 225, 80, 50)
    amazon_sdk = add_generic_node(page, "Amazon SDK\n(boto3)", 460, 330, 120, 50)

    authentication = add_node(page, "Authentication\n(Cognito)", 820, 80, "cognito", SECURITY)
    authorization = add_node(page, "Authorization\n(Trusted token issuer)", 820, 200, "security_group", SECURITY)
    sts = add_node(page, "AWS STS\n(AssumeRoleWithWebIdentity)", 820, 320, "security_group", SECURITY)

    ai_assistant = add_node(page, "AI assistant\n(chat sync API)", 1020, 320, "machine_learning", ARTIFICIAL_INTELLIGENCE)

    add_edge(page, user, distribute_traffic, "HTTPS")
    add_edge(page, distribute_traffic, application, "Route request")
    add_edge(page, application, custom_ui, "Serve UI")
    add_edge(page, application, authentication, "Get identity token")
    add_edge(page, application, authorization, "Exchange identity token")
    add_edge(page, authorization, application, "Trusted token")
    add_edge(page, amazon_sdk, sts, "Assume role (trusted token)")
    add_edge(page, sts, amazon_sdk, "Scoped credentials")
    add_edge(page, amazon_sdk, ai_assistant, "Invoke chat sync API")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file.write()
    print(f"Wrote {os.path.join(OUTPUT_DIR, file.file_name)}")


if __name__ == "__main__":
    build_diagram()
