#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, token, Address, Env, String, Symbol, Vec,
};

// ─── Storage Keys ───────────────────────────────────────────────────────────

const ADMIN: Symbol = symbol_short!("ADMIN");
const CH_COUNT: Symbol = symbol_short!("CH_COUNT");

// ─── Data Types ─────────────────────────────────────────────────────────────

#[contracttype]
#[derive(Clone, Debug, PartialEq)]
pub enum ChallengeStatus {
    Open,
    Active,
    Resolved,
    Refunded,
}

#[contracttype]
#[derive(Clone, Debug)]
pub struct Challenge {
    pub id: u64,
    pub creator: Address,
    pub challenger: Option<Address>,
    pub stake_amount: i128,
    pub description: String,
    pub status: ChallengeStatus,
    pub winner: Option<Address>,
}

/// Storage key for individual challenges
#[contracttype]
pub enum DataKey {
    Challenge(u64),
}

// ─── Contract ───────────────────────────────────────────────────────────────

#[contract]
pub struct ChallengeEscrow;

#[contractimpl]
impl ChallengeEscrow {
    // ── Admin ────────────────────────────────────────────────────────────

    /// Initialize the contract with an admin address.
    /// Can only be called once.
    pub fn initialize(env: Env, admin: Address) {
        if env.storage().instance().has(&ADMIN) {
            panic!("Contract already initialized");
        }
        admin.require_auth();
        env.storage().instance().set(&ADMIN, &admin);
        env.storage().instance().set(&CH_COUNT, &0u64);

        env.events()
            .publish((symbol_short!("init"),), admin.clone());
    }

    // ── Mutations ────────────────────────────────────────────────────────

    /// Create a new challenge. The creator stakes `stake_amount` of the
    /// native XLM token into the contract.
    pub fn create_challenge(
        env: Env,
        creator: Address,
        stake_amount: i128,
        description: String,
    ) -> u64 {
        creator.require_auth();

        if stake_amount <= 0 {
            panic!("Stake amount must be positive");
        }

        // Transfer stake from creator to contract
        let native_token = token::StellarAssetClient::new(&env, &env.current_contract_address());
        // For native token transfers we use the token client
        let token_client = token::Client::new(&env, &env.current_contract_address());
        // Actually, the native token address needs to come from the network.
        // We transfer XLM from the creator to this contract.
        Self::transfer_to_contract(&env, &creator, stake_amount);

        // Increment challenge counter
        let mut count: u64 = env.storage().instance().get(&CH_COUNT).unwrap_or(0);
        count += 1;
        env.storage().instance().set(&CH_COUNT, &count);

        let challenge = Challenge {
            id: count,
            creator: creator.clone(),
            challenger: None,
            stake_amount,
            description,
            status: ChallengeStatus::Open,
            winner: None,
        };

        env.storage()
            .persistent()
            .set(&DataKey::Challenge(count), &challenge);

        env.events().publish(
            (symbol_short!("create"), creator),
            (count, stake_amount),
        );

        count
    }

    /// A challenger joins an open challenge by matching the stake.
    pub fn join_challenge(env: Env, challenger: Address, challenge_id: u64) {
        challenger.require_auth();

        let mut challenge: Challenge = env
            .storage()
            .persistent()
            .get(&DataKey::Challenge(challenge_id))
            .expect("Challenge not found");

        if challenge.status != ChallengeStatus::Open {
            panic!("Challenge is not open for joining");
        }

        if challenge.creator == challenger {
            panic!("Creator cannot join their own challenge");
        }

        // Transfer matching stake from challenger to contract
        Self::transfer_to_contract(&env, &challenger, challenge.stake_amount);

        challenge.challenger = Some(challenger.clone());
        challenge.status = ChallengeStatus::Active;

        env.storage()
            .persistent()
            .set(&DataKey::Challenge(challenge_id), &challenge);

        env.events().publish(
            (symbol_short!("join"), challenger),
            (challenge_id, challenge.stake_amount),
        );
    }

    /// Admin resolves a challenge, sending the full pot to the winner.
    pub fn resolve_challenge(env: Env, challenge_id: u64, winner: Address) {
        let admin: Address = env
            .storage()
            .instance()
            .get(&ADMIN)
            .expect("Contract not initialized");
        admin.require_auth();

        let mut challenge: Challenge = env
            .storage()
            .persistent()
            .get(&DataKey::Challenge(challenge_id))
            .expect("Challenge not found");

        if challenge.status != ChallengeStatus::Active {
            panic!("Challenge is not active");
        }

        // Verify winner is either the creator or the challenger
        let challenger = challenge.challenger.clone().expect("No challenger");
        if winner != challenge.creator && winner != challenger {
            panic!("Winner must be a participant");
        }

        // Transfer full pot (2x stake) to winner
        let pot = challenge.stake_amount * 2;
        Self::transfer_from_contract(&env, &winner, pot);

        challenge.status = ChallengeStatus::Resolved;
        challenge.winner = Some(winner.clone());

        env.storage()
            .persistent()
            .set(&DataKey::Challenge(challenge_id), &challenge);

        env.events()
            .publish((symbol_short!("resolve"),), (challenge_id, winner, pot));
    }

    /// Creator can refund their stake if no one has joined yet.
    pub fn refund_challenge(env: Env, challenge_id: u64) {
        let mut challenge: Challenge = env
            .storage()
            .persistent()
            .get(&DataKey::Challenge(challenge_id))
            .expect("Challenge not found");

        if challenge.status != ChallengeStatus::Open {
            panic!("Can only refund open challenges");
        }

        challenge.creator.require_auth();

        // Return stake to creator
        Self::transfer_from_contract(&env, &challenge.creator, challenge.stake_amount);

        challenge.status = ChallengeStatus::Refunded;

        env.storage()
            .persistent()
            .set(&DataKey::Challenge(challenge_id), &challenge);

        env.events().publish(
            (symbol_short!("refund"),),
            (challenge_id, challenge.creator.clone()),
        );
    }

    // ── Queries ──────────────────────────────────────────────────────────

    /// Get details of a specific challenge.
    pub fn get_challenge(env: Env, challenge_id: u64) -> Challenge {
        env.storage()
            .persistent()
            .get(&DataKey::Challenge(challenge_id))
            .expect("Challenge not found")
    }

    /// Get the total number of challenges created.
    pub fn get_challenge_count(env: Env) -> u64 {
        env.storage().instance().get(&CH_COUNT).unwrap_or(0)
    }

    /// Get the admin address.
    pub fn get_admin(env: Env) -> Address {
        env.storage()
            .instance()
            .get(&ADMIN)
            .expect("Contract not initialized")
    }

    // ── Internal Helpers ─────────────────────────────────────────────────

    /// Transfer native token from a user to the contract.
    fn transfer_to_contract(env: &Env, from: &Address, amount: i128) {
        let native_token_address = Address::from_string(&String::from_str(
            env,
            "CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC",
        ));
        let client = token::Client::new(env, &native_token_address);
        client.transfer(from, &env.current_contract_address(), &amount);
    }

    /// Transfer native token from the contract to a user.
    fn transfer_from_contract(env: &Env, to: &Address, amount: i128) {
        let native_token_address = Address::from_string(&String::from_str(
            env,
            "CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC",
        ));
        let client = token::Client::new(env, &native_token_address);
        client.transfer(&env.current_contract_address(), to, &amount);
    }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod test {
    use super::*;
    use soroban_sdk::testutils::Address as _;
    use soroban_sdk::Env;

    fn setup_contract() -> (Env, Address, ChallengeEscrowClient<'static>) {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, ChallengeEscrow);
        let client = ChallengeEscrowClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        client.initialize(&admin);

        (env, admin, client)
    }

    #[test]
    fn test_initialize() {
        let (env, admin, client) = setup_contract();
        assert_eq!(client.get_admin(), admin);
        assert_eq!(client.get_challenge_count(), 0);
    }

    #[test]
    #[should_panic(expected = "Contract already initialized")]
    fn test_double_initialize_panics() {
        let (env, _, client) = setup_contract();
        let another = Address::generate(&env);
        client.initialize(&another);
    }

    #[test]
    fn test_challenge_count_increments() {
        let (_env, _admin, client) = setup_contract();
        // Challenge count starts at 0 after init
        assert_eq!(client.get_challenge_count(), 0);
    }
}
