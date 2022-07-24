from base58 import b58decode
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient, Commitment
from solana.system_program import transfer, TransferParams
from solana.rpc.types import TokenAccountOpts, TxOpts
from solana.transaction import Transaction

from spl.token.instructions import transfer_checked, TransferCheckedParams
from spl.token.constants import TOKEN_PROGRAM_ID


class RPCException(Exception):
    def __init__(self, rpc: str):
        super().__init__(f"could not connect to rpc: {rpc}")


class SolanaLowBalance(Exception):
    def __init__(self, address: str | PublicKey):
        super().__init__(f"{address} have insuficient balance")


class TokenLowBalance(Exception):
    def __init__(self, address: str | PublicKey):
        super().__init__(f"{address} have insuficient token balance")


class MissingTokenProgram(Exception):
    def __init__(self, address: str | PublicKey):
        super().__init__(f"{address} have no token program")


class Solana:
    def __init__(self, rpc: str, skip_confirmation: bool = None):
        self.rpc = rpc
        self.skip_confirmation = skip_confirmation

    async def __aenter__(self):
        self.client = AsyncClient(self.rpc)
        if await self.client.is_connected():
            return self
        raise RPCException(self.rpc)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()

    async def get_balance(
            self,
            address: str | PublicKey,
            return_sol: bool = False,
            commitment: str | Commitment = None
    ) -> int:
        if isinstance(address, str):
            address = PublicKey(address)
        if isinstance(commitment, str):
            commitment = Commitment(commitment)

        balance = (await self.client.get_balance(address, commitment=commitment))['result']['value']

        if return_sol:
            return balance / 10 ** 9
        return balance

    async def get_token_balance(
            self,
            address: str | PublicKey,
            token_contract: str | PublicKey,
            return_sol: bool = False,
            commitment: str | Commitment = None
    ) -> int:
        if isinstance(address, str):
            address = PublicKey(address)
        if isinstance(token_contract, str):
            token_contract = PublicKey(token_contract)
        if isinstance(commitment, str):
            commitment = Commitment(commitment)

        if token_program := await self.get_token_accounts_by_owner(address=address, mint=token_contract):
            balance = int((await self.client.get_token_account_balance(
                pubkey=token_program[0],
                commitment=commitment,
            ))['result']['value']['amount'])

            if return_sol:
                return balance / 10 ** 9
            return balance
        raise MissingTokenProgram(address)

    async def get_recent_blockhash(self, commitent: str | Commitment = "confirmed") -> dict:
        if isinstance(commitent, str):
            commitent = Commitment(commitent)
        return await self.client.get_recent_blockhash(commitment=commitent)

    async def send_solana(
            self,
            key: str | Keypair,
            to: str | PublicKey,
            amount: float = None,
            commitent: str | Commitment = None
    ) -> str:
        if isinstance(key, str):
            key = Keypair.from_secret_key(b58decode(key))
        if isinstance(to, str):
            to = PublicKey(to)

        balance = await self.get_balance(key.public_key)
        recent_blockhash = (await self.get_recent_blockhash(commitent))["result"]["value"]
        lamports = recent_blockhash['feeCalculator']['lamportsPerSignature']
        if amount:
            to_send = float(amount) * 10 ** 9
            if float(amount) + lamports > balance:
                raise SolanaLowBalance(key.public_key)
        else:
            to_send = balance - lamports

        if to_send < lamports:
            raise SolanaLowBalance(key.public_key)

        tx = Transaction(
            fee_payer=key.public_key,
            recent_blockhash=recent_blockhash["blockhash"]
        )
        tx.add(
            transfer(
                TransferParams(
                    from_pubkey=key.public_key,
                    to_pubkey=to,
                    lamports=int(to_send)
                )
            )
        )
        tx.sign(key)

        return (await self.client.send_transaction(
            tx,
            key,
            opts=TxOpts(skip_confirmation=self.skip_confirmation)
        ))['result']

    async def get_transaction(self, tx_hash: str) -> str:
        return (await self.client.get_transaction(tx_hash))['result']

    async def get_token_accounts_by_owner(
            self,
            address: str | PublicKey,
            mint: str | PublicKey,
            commitent: str | Commitment = None
    ) -> list[PublicKey]:
        if isinstance(address, str):
            address = PublicKey(address)
        if isinstance(mint, str):
            mint = PublicKey(mint)
        if isinstance(commitent, str):
            commitent = Commitment(commitent)
        value = (await self.client.get_token_accounts_by_owner(
            owner=address,
            opts=TokenAccountOpts(mint=mint),
            commitment=commitent
        ))

        value = value['result']['value']
        return [PublicKey(token['pubkey']) for token in value]

    async def send_token(
            self,
            key: str | Keypair,
            to: str | PublicKey,
            token_contract: str | PublicKey,
            amount: float = None,
            commitent: str | Commitment = None
    ) -> str:
        if isinstance(key, str):
            key = Keypair.from_secret_key(b58decode(key))
        if isinstance(to, str):
            to = PublicKey(to)
        if isinstance(token_contract, str):
            token_contract = PublicKey(token_contract)

        balance = await self.get_balance(key.public_key)
        token_balance = await self.get_token_balance(key.public_key, token_contract)
        recent_blockhash = (await self.get_recent_blockhash(commitent))["result"]["value"]
        lamports = recent_blockhash['feeCalculator']['lamportsPerSignature']
        if token_balance == 0:
            raise TokenLowBalance(key.public_key)
        if amount:
            amount = float(amount) * 10 ** 9
        else:
            amount = token_balance

        if balance < lamports:
            raise SolanaLowBalance(key.public_key)

        if not (dest := await self.get_token_accounts_by_owner(address=to, mint=token_contract)):
            raise MissingTokenProgram(to)

        tx = Transaction(
            fee_payer=key.public_key,
            recent_blockhash=recent_blockhash
        )

        tx.add(
            transfer_checked(
                TransferCheckedParams(
                    program_id=TOKEN_PROGRAM_ID,
                    source=(await self.get_token_accounts_by_owner(address=key.public_key, mint=token_contract))[0],
                    mint=token_contract,
                    dest=dest[0],
                    owner=key.public_key,
                    amount=int(amount),
                    decimals=9
                )
            )
        )
        return (await self.client.send_transaction(
            tx,
            key,
            opts=TxOpts(skip_confirmation=self.skip_confirmation)
        ))['result']
