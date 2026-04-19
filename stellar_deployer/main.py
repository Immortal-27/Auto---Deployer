import typer
import subprocess
import os
import requests
from typing import Optional
from stellar_deployer.aws.provisioner import provision_ec2_instance
from stellar_deployer.soroban.deployer import (
    build_contract,
    deploy_contract,
    initialize_contract,
    query_challenge,
    get_challenge_count,
)

app = typer.Typer(help="Stellar Node Auto-Deployer CLI")

@app.command()
def provision(
    key_name: str = typer.Option(..., help="AWS Key Pair name to assign to the instance"),
    instance_type: str = typer.Option("t3.medium", help="EC2 instance type"),
    ami_id: str = typer.Option("ami-0c7217cdde317cfec", help="AMI ID (defaults to Ubuntu 22.04 LTS us-east-1)")
):
    """
    Provision an EC2 instance on AWS to host the Stellar Node.
    """
    typer.echo("Starting AWS provisioning...")
    try:
        public_ip = provision_ec2_instance(key_name, instance_type, ami_id)
        typer.echo(f"Provisioning successful! Your node IP is: {public_ip}")
        typer.echo("You can now run the `install` command using this IP.")
    except Exception as e:
        typer.secho(f"Provisioning failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)

@app.command()
def install(
    ip_address: str = typer.Option(..., help="Public IP of the provisioned EC2 instance"),
    ssh_key_path: str = typer.Option(..., help="Path to your private SSH key"),
    network: str = typer.Option("testnet", help="Network to join (testnet or pubnet)"),
    mode: str = typer.Option("watcher", help="Node mode: validator or watcher")
):
    """
    Install and configure Stellar Core and PostgreSQL on the provisioned instance via Ansible.
    """
    playbook_path = os.path.join(os.path.dirname(__file__), "ansible", "install_node.yml")
    
    if not os.path.exists(playbook_path):
        typer.secho(f"Ansible playbook not found at {playbook_path}", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.echo(f"Running Ansible playbook against {ip_address}...")
    
    # We pass the network and mode as extra variables to ansible
    cmd = [
        "ansible-playbook",
        "-i", f"{ip_address},",
        "-u", "ubuntu",
        "--private-key", ssh_key_path,
        "-e", f"ansible_ssh_common_args='-o StrictHostKeyChecking=no'",
        "-e", f"stellar_network={network}",
        "-e", f"stellar_mode={mode}",
        playbook_path
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        typer.secho("Installation completed successfully!", fg=typer.colors.GREEN)
    else:
        typer.secho("Installation failed.", fg=typer.colors.RED)
        raise typer.Exit(1)

@app.command()
def status(
    ip_address: str = typer.Option(..., help="Public IP of the node")
):
    """
    Check the sync health of the Stellar node by querying its HTTP admin interface.
    """
    url = f"http://{ip_address}:11626/info"
    typer.echo(f"Querying node status at {url} ...")
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        info = data.get("info", {})
        state = info.get("state", "Unknown")
        typer.echo(f"Node state: {state}")
        # Could parse ledger sync metrics here
    except Exception as e:
        typer.secho(f"Failed to query node status: {e}", fg=typer.colors.RED)

@app.command()
def stop(
    ip_address: str = typer.Option(..., help="Public IP of the node"),
    ssh_key_path: str = typer.Option(..., help="Path to your private SSH key")
):
    """
    Stop the stellar-core daemon on the node via SSH.
    """
    typer.echo(f"Stopping stellar-core on {ip_address}...")
    cmd = [
        "ssh", "-i", ssh_key_path,
        "-o", "StrictHostKeyChecking=no",
        f"ubuntu@{ip_address}",
        "sudo systemctl stop stellar-core"
    ]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        typer.secho("Stellar Core stopped securely.", fg=typer.colors.GREEN)
    else:
        typer.secho("Failed to stop Stellar Core.", fg=typer.colors.RED)


# ─── Soroban Smart Contract Commands ────────────────────────────────────────

@app.command("build-contract")
def build_contract_cmd():
    """
    Build the Soroban smart contract (Challenge Escrow) into WASM.
    Requires Rust and soroban-cli to be installed locally.
    """
    try:
        wasm_path = build_contract()
        typer.secho(f"Build successful: {wasm_path}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Build failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command("deploy-contract")
def deploy_contract_cmd(
    network: str = typer.Option("testnet", help="Target network (testnet or pubnet)"),
    source_secret: Optional[str] = typer.Option(None, help="Stellar secret key (or set STELLAR_SECRET_KEY env var)"),
    admin_address: Optional[str] = typer.Option(None, help="Admin public key to initialize the contract with"),
):
    """
    Build, deploy, and optionally initialize the Soroban Challenge Escrow contract.
    """
    try:
        # Step 1: Build
        typer.echo("Step 1/3: Building contract...")
        build_contract()

        # Step 2: Deploy
        typer.echo("Step 2/3: Deploying to Stellar network...")
        contract_id = deploy_contract(
            network=network,
            source_secret=source_secret,
        )

        # Step 3: Initialize (if admin provided)
        if admin_address:
            typer.echo("Step 3/3: Initializing contract...")
            initialize_contract(
                contract_id=contract_id,
                admin_address=admin_address,
                network=network,
                source_secret=source_secret,
            )
        else:
            typer.echo("Step 3/3: Skipped initialization (no --admin-address provided).")
            typer.echo("Run `contract-invoke initialize` manually to set the admin.")

        typer.secho(f"\n✅ Contract deployed!", fg=typer.colors.GREEN)
        typer.echo(f"   Contract ID: {contract_id}")
        typer.echo(f"   Network:     {network}")

    except Exception as e:
        typer.secho(f"Deployment failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command("contract-status")
def contract_status_cmd(
    contract_id: str = typer.Option(..., help="Deployed contract ID"),
    network: str = typer.Option("testnet", help="Target network (testnet or pubnet)"),
    source_secret: Optional[str] = typer.Option(None, help="Stellar secret key"),
    challenge_id: Optional[int] = typer.Option(None, help="Specific challenge ID to query"),
):
    """
    Query the status of the deployed Soroban Challenge Escrow contract.
    """
    try:
        count = get_challenge_count(
            contract_id=contract_id,
            network=network,
            source_secret=source_secret,
        )
        typer.echo(f"Total challenges created: {count}")

        if challenge_id is not None:
            typer.echo(f"\nQuerying challenge #{challenge_id}...")
            data = query_challenge(
                contract_id=contract_id,
                challenge_id=challenge_id,
                network=network,
                source_secret=source_secret,
            )
            typer.echo(f"Challenge data: {data}")

    except Exception as e:
        typer.secho(f"Query failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
