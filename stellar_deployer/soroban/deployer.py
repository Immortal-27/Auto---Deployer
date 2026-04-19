"""
Soroban Smart Contract Deployer

Provides functions to build, deploy, and interact with
the Stellar Challenge Escrow Soroban smart contract.
"""

import subprocess
import os
import json
from typing import Optional


# Path to the soroban contract source relative to the project root
CONTRACT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "soroban")
WASM_PATH = os.path.join(CONTRACT_DIR, "target", "wasm32-unknown-unknown", "release", "stellar_challenge_escrow.wasm")

# Stellar network configuration
NETWORKS = {
    "testnet": {
        "rpc_url": "https://soroban-testnet.stellar.org",
        "network_passphrase": "Test SDF Network ; September 2015",
    },
    "pubnet": {
        "rpc_url": "https://soroban-rpc.mainnet.stellar.gateway.fm",
        "network_passphrase": "Public Global Stellar Network ; September 2015",
    },
}


def build_contract() -> str:
    """
    Build the Soroban smart contract.
    Returns the path to the compiled WASM file.

    Raises:
        RuntimeError: If the build fails.
    """
    if not os.path.isdir(CONTRACT_DIR):
        raise FileNotFoundError(
            f"Contract source directory not found at {CONTRACT_DIR}. "
            "Ensure the 'soroban/' directory exists in the project root."
        )

    print(f"Building Soroban contract in {CONTRACT_DIR}...")
    result = subprocess.run(
        ["soroban", "contract", "build"],
        cwd=CONTRACT_DIR,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Contract build failed:\n{result.stderr}"
        )

    if not os.path.exists(WASM_PATH):
        raise FileNotFoundError(
            f"Build succeeded but WASM not found at expected path: {WASM_PATH}"
        )

    print(f"Contract built successfully: {WASM_PATH}")
    return WASM_PATH


def deploy_contract(
    network: str = "testnet",
    source_secret: Optional[str] = None,
) -> str:
    """
    Deploy the compiled WASM contract to the Stellar network.

    Args:
        network: Target network ('testnet' or 'pubnet').
        source_secret: Stellar secret key for the deployer account.
                       If None, uses STELLAR_SECRET_KEY env var.

    Returns:
        The deployed contract ID.

    Raises:
        RuntimeError: If deployment fails.
        ValueError: If network is invalid or secret key is missing.
    """
    if network not in NETWORKS:
        raise ValueError(f"Invalid network '{network}'. Must be one of: {list(NETWORKS.keys())}")

    secret = source_secret or os.environ.get("STELLAR_SECRET_KEY")
    if not secret:
        raise ValueError(
            "No source secret key provided. "
            "Pass --source-secret or set STELLAR_SECRET_KEY environment variable."
        )

    if not os.path.exists(WASM_PATH):
        print("WASM not found. Building contract first...")
        build_contract()

    net_config = NETWORKS[network]

    print(f"Deploying contract to {network}...")
    result = subprocess.run(
        [
            "soroban", "contract", "deploy",
            "--wasm", WASM_PATH,
            "--source", secret,
            "--rpc-url", net_config["rpc_url"],
            "--network-passphrase", net_config["network_passphrase"],
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Contract deployment failed:\n{result.stderr}"
        )

    contract_id = result.stdout.strip()
    print(f"Contract deployed successfully!")
    print(f"Contract ID: {contract_id}")
    print(f"Network: {network}")

    return contract_id


def initialize_contract(
    contract_id: str,
    admin_address: str,
    network: str = "testnet",
    source_secret: Optional[str] = None,
) -> str:
    """
    Initialize the deployed contract by setting the admin.

    Args:
        contract_id: The deployed contract ID.
        admin_address: Stellar public key to set as admin.
        network: Target network.
        source_secret: Stellar secret key for the transaction signer.

    Returns:
        Transaction result.
    """
    secret = source_secret or os.environ.get("STELLAR_SECRET_KEY")
    if not secret:
        raise ValueError("No source secret key provided.")

    net_config = NETWORKS[network]

    print(f"Initializing contract {contract_id} with admin {admin_address}...")
    result = subprocess.run(
        [
            "soroban", "contract", "invoke",
            "--id", contract_id,
            "--source", secret,
            "--rpc-url", net_config["rpc_url"],
            "--network-passphrase", net_config["network_passphrase"],
            "--", "initialize",
            "--admin", admin_address,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Contract initialization failed:\n{result.stderr}"
        )

    print("Contract initialized successfully!")
    return result.stdout.strip()


def query_challenge(
    contract_id: str,
    challenge_id: int,
    network: str = "testnet",
    source_secret: Optional[str] = None,
) -> dict:
    """
    Query a specific challenge from the contract.

    Args:
        contract_id: The deployed contract ID.
        challenge_id: ID of the challenge to query.
        network: Target network.
        source_secret: Stellar secret key.

    Returns:
        Challenge data as a dictionary.
    """
    secret = source_secret or os.environ.get("STELLAR_SECRET_KEY")
    if not secret:
        raise ValueError("No source secret key provided.")

    net_config = NETWORKS[network]

    result = subprocess.run(
        [
            "soroban", "contract", "invoke",
            "--id", contract_id,
            "--source", secret,
            "--rpc-url", net_config["rpc_url"],
            "--network-passphrase", net_config["network_passphrase"],
            "--", "get_challenge",
            "--challenge_id", str(challenge_id),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to query challenge:\n{result.stderr}"
        )

    output = result.stdout.strip()
    print(f"Challenge {challenge_id} data: {output}")
    return output


def get_challenge_count(
    contract_id: str,
    network: str = "testnet",
    source_secret: Optional[str] = None,
) -> int:
    """
    Get the total number of challenges created.

    Args:
        contract_id: The deployed contract ID.
        network: Target network.
        source_secret: Stellar secret key.

    Returns:
        Total challenge count.
    """
    secret = source_secret or os.environ.get("STELLAR_SECRET_KEY")
    if not secret:
        raise ValueError("No source secret key provided.")

    net_config = NETWORKS[network]

    result = subprocess.run(
        [
            "soroban", "contract", "invoke",
            "--id", contract_id,
            "--source", secret,
            "--rpc-url", net_config["rpc_url"],
            "--network-passphrase", net_config["network_passphrase"],
            "--", "get_challenge_count",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to get challenge count:\n{result.stderr}"
        )

    count = int(result.stdout.strip())
    return count
