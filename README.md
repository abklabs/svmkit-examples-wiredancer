# About ABK Labs

**Just build together** - ABK Labs believes that open-source software is the
purest form of innovation. In our world, there are no competitors, only
contributors.

## Wiredancer Overview

Wiredancer is an FPGA acceleration layer for Firedancer that offloads
compute-heavy tasks like ED25519 signature verification to AWS F2 cards. Using
an asynchronous interface, it queues verification requests from software while
FPGAs work in parallel, verifying up to one million signatures per second.
Offloading this workload to dedicated hardware reduces latency, scales
across multiple FPGAs, and frees host CPUs, which boosts overall
throughput and power efficiency.

This example shows how to use Pulumi to deploy Wiredancer on AWS.

## Running the Example

1. Have `pulumi` installed, logged in to wherever you're storing state, and configured to work with AWS.

- Please see PULUMI-AWS.md for more information on how to set up your environment.

2. Navigate to the example directory:

```
% cd wiredancer-demo-py
```

3. Run `pulumi install`; this will install all of the required pieces for this example.

```
% pulumi install
```

4. Create and select a Pulumi stack

```
% pulumi stack init wiredancer-demo-py
```

5. Set pulumi config

Use `pulumi config set <key:val>` to set the following configuration values (or just use the
defaults):

| Name                       | Description                                                       | Default Value                    |
| :------------------------- | :---------------------------------------------------------------- |:-------------------------------- |
| aws:region                 | The AWS region to launch the cluster in.                          | us-west-2
| demo:debPath               | The path to wiredancer deb.                                       | wiredancer_demo_amd64.deb
| demo:pcapPath              | The path to solana pcap file.                                     | solana.pcap
| demo:afgi                  | The Wiredancer FPGA AFGI id.                                      | agfi-02d20eee5691113e4
| node:instanceType          | The AWS instance type to use for all of the nodes.                | f2.6xlarge
| node:instanceArch          | The AWS instance architecture type to use for the AMI lookup.     | x86_64
| node:iops                  | The iops to use for the EBS volume.                               | 5000
| node:rootVolSize           | The size of the root volume to use for the EBS volume.            | 200
| node:swapSize              | The size of the swap volume.                                      | 8192

6. Run `pulumi up`

```
% pulumi up
```

7. Run the demo

```
% mkdir -p wiredancer-demo-state
% ./wiredancer-demo wiredancer-demo-state
```

This will set up a tmux session that runs the Wiredancer demo and monitor
application in two separate panes.

To exit the tmux session, press `ctrl+b` and then `d`.

8. Tear down the example

```bash
% pulumi down
```

## How to build a Wiredancer Debian package (optional)

The Wiredancer example includes a prebuilt Debian package. To build your own,
follow these steps:

1. Install the required dependencies:

- bash 
- git
- golang

2. Set up sandbox:

```
% mkdir ~/wiredancer-demo
% cd ~/wiredancer-demo
```

3. Clone the Firedancer repo:

```
% git clone https://github.com/abklabs/firedancer firedancer
```

4. Clone and set up the SVMKit repo:

```
% git clone https://github.com/abklabs/svmkit svmkit
% cd svmkit
% make setup
```

5. Build the svmkit cli and install it:

```
% cd cmd/svmkit
% go install
```

6. Build the Wiredancer Debian package:

```
% cd ~/wiredancer-demo/firedancer
% ../svmkit/build/wiredancer-build
```

This will dump out a Debian package in the `~/wiredancer-demo/firedancer` directory.

