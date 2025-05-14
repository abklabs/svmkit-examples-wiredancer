import os
import tempfile
import pulumi
from pulumi import ComponentResource, ResourceOptions, Output
import pulumi_aws as aws
import pulumi_tls as tls
import pulumi_svmkit as svmkit
import pulumi_command as command
import pulumi.asset as asset
from typing import cast

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

config = pulumi.Config('demo')

local_deb_path = config.get("debPath") or "wiredancer_demo_amd64.deb"
local_deb_name = os.path.basename(local_deb_path)
remote_deb_path = f"/tmp/{local_deb_name}"

local_pcap_path = config.get("pcapPath") or "solana.pcap"
local_pcap_name = os.path.basename(local_pcap_path)
remote_pcap_path = f"/tmp/{local_pcap_name}"

bitstream_afgi_id = config.get("afgi") or "agfi-04b2f5f86d0176c1b"

node_config = pulumi.Config("node")

instance_type   = node_config.get('instanceType')   or "f2.6xlarge"
instance_arch   = node_config.get('instanceArch')   or "x86_64"
iops            = node_config.get_int('volumeIOPS') or 5000
root_vol_size   = node_config.get_int('rootVolumeSize') or 200
swap_size       = node_config.get_int('swapSize')   or 8192

stack_name = pulumi.get_stack()

# ─────────────────────────────────────────────────────────────────────────────
# Security groups
# ─────────────────────────────────────────────────────────────────────────────
external_sg = aws.ec2.SecurityGroup(
    "external-access",
    description="Allow external SSH access to all of the nodes",
    ingress=[{
        "protocol": "tcp",
        "from_port": 0,
        "to_port": 22,
        "cidr_blocks": ["0.0.0.0/0"],
    }],
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"],
    }],
    tags={"Stack": stack_name},
)

internal_sg = aws.ec2.SecurityGroup(
    "internal-access",
    description="Permissive internal traffic",
    ingress=[{"protocol": "-1", "from_port": 0, "to_port": 0, "self": True}],
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"],
    }],
    tags={"Stack": stack_name},
)

# ─────────────────────────────────────────────────────────────────────────────
# AMI lookup
# ─────────────────────────────────────────────────────────────────────────────

ami = aws.ec2.get_ami(
    owners      = ["679593333241"],
    most_recent = True,
    filters = [
        {"name": "name",
         "values": ["FPGA Developer AMI (Ubuntu) - 1.16.0*"]},
        {"name": "architecture",
         "values": [instance_arch]},
    ],
).id

# ─────────────────────────────────────────────────────────────────────────────
# Component definition
# ─────────────────────────────────────────────────────────────────────────────
class Node(ComponentResource):
    def __init__(self, name: str, opts: ResourceOptions | None = None):
        super().__init__("pkg:index:Node", name, {}, opts)

        def rn(s: str) -> str:  # resource name helper
            return f"{name}-{s}"

        self.ssh_key = tls.PrivateKey(
            rn("ssh-key"), algorithm="ED25519",
            opts=ResourceOptions(parent=self),
        )
        self.key_pair = aws.ec2.KeyPair(
            rn("keypair"),
            public_key=self.ssh_key.public_key_openssh,
            opts=ResourceOptions(parent=self),
        )

        self.instance = aws.ec2.Instance(
            rn("instance"),
            ami=ami,
            instance_type=instance_type,
            key_name=self.key_pair.key_name,
            root_block_device={
                "volume_size": root_vol_size,
                "volume_type": "gp3",
                "iops": iops,
            },
            vpc_security_group_ids=[external_sg.id, internal_sg.id],
            user_data=f"""#!/bin/bash
mkdir -p /home/sol/accounts /home/sol/ledger
echo '/swapfile none swap sw 0 0' >> /etc/fstab
fallocate -l {swap_size}M /swapfile
chmod 600 /swapfile
mkswap /swapfile
mount -a
swapon -a
""",
            tags={"Name": f"{stack_name}-{name}", "Stack": stack_name},
            opts=ResourceOptions(parent=self),
        )

        self.connection = command.remote.ConnectionArgs(
            host=self.instance.public_dns,
            user="ubuntu",
            private_key=self.ssh_key.private_key_openssh,
        )

        self.register_outputs({
            "instance_id": self.instance.id,
            "public_dns": self.instance.public_dns,
            "connection": self.connection,
        })

primary_node = Node("primary")

# ─────────────────────────────────────────────────────────────────────────────
# Scripts
# ─────────────────────────────────────────────────────────────────────────────
fd_path = "/opt/frankendancer"
aws_fpga_path = "/tmp/aws-fpga"
remote_scripts_dir = f"/tmp/fd_scripts"

load_fpga_script = f"""#!/bin/bash
set -euo pipefail
set +u
source {aws_fpga_path}/sdk_setup.sh
set -u
sudo fpga-clear-local-image -S 0
sudo fpga-load-local-image -S 0 -I {bitstream_afgi_id}
sudo fpga-describe-local-image -S 0
"""

configure_fd_script = f"""#!/bin/bash
set +u
source {aws_fpga_path}/sdk_setup.sh
set -u
sudo {fd_path}/bin/fd_shmem_cfg reset
sudo {fd_path}/bin/fd_shmem_cfg fini
sudo {fd_path}/bin/fd_shmem_cfg alloc 32 gigantic 0 alloc 512 huge 0
sudo {fd_path}/bin/fd_shmem_cfg init 0700 $USER ""
sudo {fd_path}/bin/fd_shmem_cfg query
sudo {fd_path}/bin/fd_frank_init_demo frank 1-6 {fd_path} /tmp/solana.pcap 0 0 1 0
sudo setpci -s 34:00.0 command=06
"""

# create temp dir with scripts and archive it
build_dir   = tempfile.mkdtemp(prefix="fd_pkg_")
scripts_dir = os.path.join(build_dir, "fd_scripts")
os.makedirs(scripts_dir, exist_ok=True)

with open(os.path.join(scripts_dir, "load_fpga.sh"), "w") as f:
    f.write(load_fpga_script)
with open(os.path.join(scripts_dir, "config_fd.sh"), "w") as f:
    f.write(configure_fd_script)

script_archive = asset.FileArchive(scripts_dir)

push_scripts = command.remote.CopyToRemote(
    "push-scripts",
    connection=primary_node.connection,
    source=script_archive,
    remote_path="/tmp",
    opts=pulumi.ResourceOptions(depends_on=[primary_node.instance]),
)

# ─────────────────────────────────────────────────────────────────────────────
# Clone / update aws-fpga repository
# ─────────────────────────────────────────────────────────────────────────────
aws_fpga_sync = command.remote.Command(
    "aws-fpga-sync",
    connection=primary_node.connection,
    create=f"""
        set -euo pipefail
        if [ -d {aws_fpga_path}/.git ]; then
            git -C {aws_fpga_path} pull --ff-only
        else
            git clone --depth 1 https://github.com/aws/aws-fpga.git {aws_fpga_path}
        fi
    """,
    opts=ResourceOptions(depends_on=[primary_node.instance]),
)

# ─────────────────────────────────────────────────────────────────────────────
# Copy assets and install dependencies
# ─────────────────────────────────────────────────────────────────────────────
push_deb = command.remote.CopyToRemote(
    "push-deb",
    connection=primary_node.connection,
    source=asset.FileAsset(local_deb_path),
    remote_path=remote_deb_path,
    opts=ResourceOptions(depends_on=[primary_node.instance]),
)

install_deb = command.remote.Command(
    "install-deb",
    connection=primary_node.connection,
    create=f"sudo dpkg -i {remote_deb_path} && sudo apt-get -y -f install",
    opts=pulumi.ResourceOptions(depends_on=[push_deb]),
)

push_pcap = command.remote.CopyToRemote(
    "push-pcap",
    connection=primary_node.connection,
    source=asset.FileAsset(local_pcap_path),
    remote_path=remote_pcap_path,
    opts=ResourceOptions(depends_on=[primary_node.instance]),
)

# ─────────────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────────────
pulumi.export("nodes_name", ["primary"])
pulumi.export("nodes_public_ip", [primary_node.instance.public_ip])
pulumi.export("nodes_private_key", [primary_node.ssh_key.private_key_openssh])
