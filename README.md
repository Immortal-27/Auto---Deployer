# Stellar Node Auto-Deployer

Stellar Node Auto-Deployer is a Python-based Command Line Interface (CLI) tool designed to fully automate the provisioning, installation, and configuration of a Stellar Core node on AWS infrastructure — **plus** build, deploy, and manage Soroban smart contracts on the Stellar network.

With a few simple commands, you can stand up a live `t3.medium` EC2 instance, install the official `stellar-core` binary and PostgreSQL backend, join the Stellar Testnet or Pubnet, **and deploy the included Challenge Escrow smart contract**.

## 🚀 Tech Stack

- **CLI Framework:** [Typer](https://typer.tiangolo.com/) for building a clean, modern Python CLI.
- **Infrastructure:** [AWS Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) for programmatic EC2 provisioning.
- **Configuration Management:** [Ansible](https://www.ansible.com/) for server configuration and database scaffolding.
- **Database:** PostgreSQL (The persistence layer for Stellar Core).
- **Blockchain:** [Stellar SDK](https://stellar-sdk.readthedocs.io/) for network interactions.
- **Smart Contracts:** [Soroban](https://soroban.stellar.org/) (Rust) — Challenge Escrow contract included.

## 🛠 Prerequisites

1. **Python 3.8+**
2. **AWS Account** with an existing EC2 SSH Key Pair.
3. Proper permissions to launch EC2 instances and create Security Groups.
4. **Rust toolchain** (for building the Soroban contract) — install via [rustup](https://rustup.rs/).
5. **Soroban CLI** — `cargo install --locked soroban-cli`

### AWS Credentials

This tool uses Boto3, which strictly adheres to AWS credential standards. Ensure you have your AWS access keys exported in your current environment or configured in your `~/.aws/credentials` profile.

```bash
export AWS_ACCESS_KEY_ID="your_access_key_id"
export AWS_SECRET_ACCESS_KEY="your_secret_access_key"
export AWS_DEFAULT_REGION="us-east-1"
```

*Note: The default AMI logic is tailored to `us-east-1`. Please override the `--ami-id` if you launch in another region.*

### Stellar Credentials (for contract deployment)

```bash
export STELLAR_SECRET_KEY="S..."  # Your Stellar secret key
```

## ⚙️ Installation

1. Clone or download the repository.
2. Navigate to the project root directory:
   ```bash
   cd stellar-node-deployer
   ```
3. Install the required python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. (Optional) Build the Soroban smart contract:
   ```bash
   cd soroban && cargo build --target wasm32-unknown-unknown --release
   ```

## 📖 Usage

You can invoke the CLI entry point by running the Python module:

```bash
python -m stellar_deployer.main --help
```

---

### Node Management Commands

### 1. Provisioning

Launch a fresh EC2 Ubuntu instance on AWS. This will automatically create a Security Group (`stellar-core-sg`) configuring required ingress ports (22, 11625) and mount a 100GB EBS volume.

```bash
python -m stellar_deployer.main provision --key-name "my-aws-key-pair"
```

*The CLI will wait for the instance to become fully ready and then respond with your new Node's Public IP Address.*

### 2. Installation & Configuration

Takes the provisioned IP Address from the previous step and remotely triggers an Ansible Playbook. This installs PostgreSQL, sets up database credentials, downloads the SDF repository keys, installs Soroban CLI, and dynamically compiles the `/etc/stellar/stellar-core.cfg` reflecting the specified network parameters. 

```bash
python -m stellar_deployer.main install \
  --ip-address 12.34.56.78 \
  --ssh-key-path "~/.ssh/my-aws-key-pair.pem" \
  --network testnet \
  --mode watcher
```

### 3. Monitoring Health Status

Rapidly query the Stellar Core HTTP admin interface (`port 11626`) to parse state and sync metrics.

```bash
python -m stellar_deployer.main status --ip-address 12.34.56.78
```

### 4. Stopping the Node

Stop the stellar-core systemd service daemon remotely. 

```bash
python -m stellar_deployer.main stop \
  --ip-address 12.34.56.78 \
  --ssh-key-path "~/.ssh/my-aws-key-pair.pem"
```

---

### Smart Contract Commands

### 5. Build the Smart Contract

Compile the Soroban Challenge Escrow contract to WASM:

```bash
python -m stellar_deployer.main build-contract
```

### 6. Deploy the Smart Contract

Build, deploy, and initialize the contract on the Stellar network:

```bash
python -m stellar_deployer.main deploy-contract \
  --network testnet \
  --source-secret "S..." \
  --admin-address "G..."
```

### 7. Query Contract Status

Check the state of your deployed contract:

```bash
python -m stellar_deployer.main contract-status \
  --contract-id "C..." \
  --network testnet \
  --source-secret "S..." \
  --challenge-id 1
```

---

## 📜 Smart Contract: Challenge Escrow

The included Soroban smart contract (`soroban/src/lib.rs`) implements a **Challenge Escrow System** on the Stellar blockchain:

| Function | Description |
|---|---|
| `initialize(admin)` | Sets the contract admin (one-time) |
| `create_challenge(creator, stake, desc)` | Creator stakes XLM into a new challenge |
| `join_challenge(challenger, id)` | Challenger matches the stake |
| `resolve_challenge(id, winner)` | Admin resolves — winner gets the pot |
| `refund_challenge(id)` | Creator refunds if no one joined |
| `get_challenge(id)` | Query challenge details |
| `get_challenge_count()` | Total challenges created |

## ⚠️ Important Note

- Executing the `provision` command dynamically utilizes **real, paid AWS resources**. By using this tool, you acknowledge that you are responsible for any charges incurred on your AWS account.
- When tearing down your deployment, remember to terminate the EC2 instances directly from your AWS Console or via AWS CLI to stop billing.
- The smart contract uses the **Stellar Testnet** by default. Switch to `pubnet` only when you are ready for production.
