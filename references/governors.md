# Supported Governors

This file documents the on-chain governor implementations that
`src/governors.py` knows how to read, and the function selectors it
relies on.

## OpenZeppelin Governor (default for `onchain` mode)

Standard ABI:

```solidity
function state(uint256 proposalId) external view returns (uint8);
function proposalVotes(uint256 proposalId)
    external view returns (uint256 againstVotes, uint256 forVotes, uint256 abstainVotes);
function proposalSnapshot(uint256 proposalId) external view returns (uint256);
function proposalDeadline(uint256 proposalId) external view returns (uint256);
function quorum(uint256 blockNumber) external view returns (uint256);
function votingPeriod() external view returns (uint256);
function votingDelay() external view returns (uint256);
```

Selectors used (precomputed in `src/rpc.py`):

| Function                       | Selector       |
|--------------------------------|----------------|
| `state(uint256)`               | `0x3e4f49e6`   |
| `proposalVotes(uint256)`       | `0xda95691a`   |
| `proposalSnapshot(uint256)`    | `0x462aca47`   |
| `proposalDeadline(uint256)`    | `0x2e03ce1b`   |
| `quorum(uint256)`              | `0xf8ce5601`   |
| `votingPeriod()`               | `0x9a7e4080`   |
| `votingDelay()`                | `0xfe0d94c1`   |

Compatible with: Governor, GovernorCountingSimple, GovernorVotes,
GovernorVotesQuorumFraction, GovernorTimelockControl, and the
"CompatibilityBravo" variant (which adds `proposals(uint256)`).

## Compound Bravo (GovernorAlpha / GovernorBravo)

Standard ABI (we read `proposals(uint256)` for the full tuple):

```solidity
function proposals(uint256) external view returns (
    uint256 id,
    address proposer,
    uint256 eta,
    uint256 startBlock,
    uint256 endBlock,
    uint256 forVotes,
    uint256 againstVotes,
    uint256 abstainVotes,
    bool canceled,
    bool executed
);
function state(uint256) external view returns (uint8);
function quorumVotes() external view returns (uint256);
function proposalCount() external view returns (uint256);
```

Selectors used:

| Function          | Selector       |
|-------------------|----------------|
| `proposals(uint256)` | `0x7d5d6a93` |
| `state(uint256)`     | `0x3e4f49e6` |
| `quorumVotes()`      | `0x973ab343` |

The current `make_governor` factory routes all `0x…` addresses to
`OZGovernor` first because it is more common. If you are forecasting
on a Compound-style governor, pass `--mode onchain` and modify
`make_governor` to return `CompoundBravoGovernor` instead, or open
an issue and we'll add a `--governor-type` flag.

## Snapshot (off-chain)

Endpoint: `https://hub.snapshot.org/graphql`

Query: `Proposal` returning `id, title, state, author, space, start,
end, votes, scores, scores_total, quorum, type`.

The skill uses `scores[0]` = for, `scores[1]` = against,
`scores[2]` = abstain. Most DAOs follow this convention; DAOs using
custom strategies may need a manual override.

The default quorum is read from `proposal.quorum`; if the DAO defines
quorum as a percentage of supply and the hub returns 0, pass
`--quorum-absolute`.

## Pharos-native governance

If Pharos ships a custom governor contract, point the skill at it the
same way you would any OZ Governor (it almost certainly is one, or
forks Compound Bravo). If neither ABI matches, the engine will
return an error and the user can fall back to `--quorum-absolute`.

## Adding a new governor

1. Add the function selectors to the `pre` dict in `src/rpc.py`.
2. If it's structurally different from OZ/Bravo, add a new
   `<NewStyle>Governor` class in `src/governors.py` that implements
   `current_state(proposal_id)` and `historical_states(n)`.
3. Wire it into the `make_governor` factory.
4. Add a row to this table.

PRs welcome.
