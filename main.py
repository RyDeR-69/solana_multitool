import asyncio
import aiofiles

from base58 import b58encode, b58decode
from solana.keypair import Keypair

from modules.solana import Solana, MissingTokenProgram


async def generate_wallets(queue: asyncio.Queue, fmt: int, save_file: str | None):
    new_wallet = Keypair()
    while True:
        if queue.empty():
            return True
        await queue.get()

        if fmt == 1:
            if save_file:
                async with aiofiles.open("new_wallets.txt", mode="a+") as file:
                    await file.write(f"{b58encode(new_wallet.secret_key).decode('utf-8')}:{new_wallet.public_key}\n")
            else:
                print(f"{b58encode(new_wallet.secret_key).decode('utf-8')}:{new_wallet.public_key}")
        elif fmt == 2:
            if save_file:
                async with aiofiles.open("new_wallets.txt", mode="a+") as file:
                    await file.write(f"{b58encode(new_wallet.secret_key).decode('utf-8')}\n")
            else:
                print(b58encode(new_wallet.secret_key).decode('utf-8'))
        else:
            raise ValueError("invalid input")


async def private_to_address(queue: asyncio.Queue):
    while True:
        if queue.empty():
            return True
        wallet = await queue.get()

        print(Keypair.from_secret_key(b58decode(wallet)).public_key)


async def collect_token(queue: asyncio.Queue, token_contract: str, main_address: str, amount: str):
    while True:
        try:
            if queue.empty():
                return True
            if amount:
                amount = float(amount)

            wallet = await queue.get()
            address = Keypair.from_secret_key(b58decode(wallet)).public_key

            async with Solana(rpc=rpc, skip_confirmation=skip_confirmations) as client:
                tx = await client.send_token(key=wallet, token_contract=token_contract, to=main_address, amount=amount)
                if address_with_tx:
                    print(f"{address}: {tx}")
                else:
                    print(tx)

        except Exception as e:
            if e:
                print(e)


async def collect_sol(queue: asyncio.Queue, main_address: str, amount: str):
    while True:
        try:
            if queue.empty():
                return True

            if amount:
                amount = float(amount)
            wallet = await queue.get()
            address = Keypair.from_secret_key(b58decode(wallet)).public_key

            async with Solana(rpc=rpc, skip_confirmation=skip_confirmations) as client:
                tx = await client.send_solana(key=wallet, to=main_address, amount=amount)
                if address_with_tx:
                    print(f"{address}: {tx}")
                else:
                    print(tx)
        except Exception as e:
            print(e)


async def check_sol(queue: asyncio.Queue):
    total_balance = 0
    while True:
        try:
            data = await queue.get()
            wallet = Keypair.from_secret_key(b58decode(data)).public_key

            async with Solana(rpc=rpc) as client:
                balance = await client.get_balance(address=wallet, return_sol=True)
                print(f"{wallet}: {balance} SOL")
                if balance:
                    total_balance += balance

            if queue.empty():
                return total_balance
        except Exception as e:
            print(e)


async def check_token(queue: asyncio.Queue, token_contract: str):
    total_balance = 0
    while True:
        try:
            data = await queue.get()
            wallet = Keypair.from_secret_key(b58decode(data)).public_key

            async with Solana(rpc=rpc) as client:
                balance = await client.get_token_balance(address=wallet, token_contract=token_contract, return_sol=True)
                print(f"{wallet}: {balance}")
                if balance:
                    total_balance += balance

            if queue.empty():
                return total_balance
        except MissingTokenProgram as e:
            print(e)


async def create_task():
    queue = asyncio.Queue()
    show_total = False
    tasks = []

    for wallet in wallets:
        queue.put_nowait(wallet)

    match choise:
        case 0:
            exit(69)
        case 1:
            tasks = [asyncio.create_task(check_sol(queue)) for _ in range(threads)]
            show_total = True
        case 2:
            token_contract = input("enter token contract >>> ")
            tasks = [asyncio.create_task(check_token(queue, token_contract)) for _ in range(threads)]
            show_total = True
        case 3:
            main_address = input("enter main wallet >>> ")
            amount = input("enter amount to send (skip for all balance) >>> ")
            tasks = [asyncio.create_task(collect_sol(queue, main_address, amount)) for _ in range(threads)]
        case 4:
            main_address = input("enter main wallet >>> ")
            token_contract = input("enter token contract >>> ")
            amount = input("enter amount to send (skip for all balance) >>> ")
            tasks = [asyncio.create_task(collect_token(
                queue, token_contract, main_address, amount
            )) for _ in range(threads)]
        case 5:
            tasks = [asyncio.create_task(private_to_address(queue)) for _ in range(threads)]
        case 6:
            temp_quque = asyncio.Queue()

            for i in range(int(input("how many wallets >>> "))):
                temp_quque.put_nowait(i)

            fmt = int(input(
                "choose format: \n"
                "1 - key:address\n"
                "2 - key\n"
                ">>> "
            ))
            save_file = input("save data in file (y/skip) >>> ")
            tasks = [asyncio.create_task(generate_wallets(temp_quque, fmt, save_file)) for _ in range(10)]
        case _:
            raise Exception("invalid input")

    result = await asyncio.gather(*tasks)
    if show_total:
        print(f"total balance on accounts: {sum(filter(None, result))}")


if __name__ == '__main__':
    skip_confirmations: bool = False
    rpc: str = "https://solana-mainnet.phantom.tech"
    address_with_tx: bool = False

    if value := input("enter your rpc (skip for using default rpc) >>> "):
        rpc = value

    wallets = list(filter(bool, open("data/wallets.txt").read().strip().split("\n")))
    print(f"\nloaded {len(wallets)} wallets!\n")

    while True:
        choise = int(input(
            "0 - exit\n"
            "1 - check account balances (sol)\n"
            "2 - check account balances (token)\n"
            "3 - collect sol from accounts\n"
            "4 - collect tokens from accounts\n"
            "5 - privat key to address\n"
            "6 - generate wallets\n"
            ">>> "
        ))
        threads = int(input("threads >>> ")) if len(wallets) > 25 else len(wallets)
        asyncio.run(create_task())
