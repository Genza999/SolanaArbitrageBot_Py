import base64
import based58
import httpx
import asyncio

from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.publickey import PublicKey
from solana.keypair import Keypair
from solana.transaction import Transaction
from spl.token.instructions import get_associated_token_address, create_associated_token_account

from usdc_swaps import route_map


SOLANA_CLIENT = AsyncClient('https://api.mainnet-beta.solana.com')
WALLET = Keypair.from_secret_key(based58.b58decode('secret_key'.encode("ascii")))
INPUT_USDC_AMOUNT = 5000000
USDC_BASE = 1000000


def get_mint(index, indexedRouteMap):
   return indexedRouteMap['mintKeys'][int(index)]

def get_route_map():
    return route_map
    

async def get_coin_quote (INPUT_MINT, TOKEN_MINT, amount):
    # Get PAIR QUOTE
    url = f'https://quote-api.jup.ag/v1/quote?inputMint={INPUT_MINT}&outputMint={TOKEN_MINT}&amount={amount}&slippage=0.5'
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=15.0)
        return r.json()

async def get_coin_swap_quote(route):
    # Get PAIR SWAP QUOTE
    async with httpx.AsyncClient() as client:
       r = await client.post(
           url='https://quote-api.jup.ag/v1/swap',
           json={
                'route': route,
                'userPublicKey': str(WALLET.public_key),
                'wrapUnwrapSOL': False
            },
            timeout=15.0
        )
       return r.json()


async def execute_trancation(transacx):
    # Execute transactions
    opts = TxOpts(skip_preflight=True , max_retries=11)
    for tx_name, raw_transaction in transacx.items():
        if raw_transaction:
            try:
                transaction = Transaction.deserialize(base64.b64decode(raw_transaction))
                await SOLANA_CLIENT.send_transaction(transaction, WALLET, opts=opts)
            except Exception as e:
                print("Error occured at ex tx: ", str(e))
                return str(e)

async def serialized_swap_transaction(usdcToTokenRoute, tokenToUsdcRoute):
    if usdcToTokenRoute:
        try:
            usdcToTokenTransaction = await get_coin_swap_quote(usdcToTokenRoute)
            await execute_trancation(usdcToTokenTransaction )
        except Exception as e:
            print("Error occured at execution usdctotoken: ", str(e))
            return str(e)

        if tokenToUsdcRoute:
            try:
                tokenToUsdcTransaction = await get_coin_swap_quote(tokenToUsdcRoute)
                await execute_trancation(tokenToUsdcTransaction)
            except Exception as e:
                print("Error occured at execution tokentousdc: ", str(e))
                return str(e)

async def _create_associated_token_account(token):
    # Create Associated token account for token to swap if not available
    token_associated_account = get_associated_token_address(
        WALLET.public_key,
        PublicKey(token)
    )
    opts = TxOpts(skip_preflight=True , max_retries=11)
    ata = await SOLANA_CLIENT.get_account_info(PublicKey(token_associated_account))
    if not ata.get('result').get('value'):
        try:
            instruction = create_associated_token_account(
                WALLET.public_key,
                WALLET.public_key,
                PublicKey(token)
            )
            txn = Transaction().add(instruction)
            txn.recent_blockhash = await SOLANA_CLIENT.get_recent_blockhash()
            await SOLANA_CLIENT.send_transaction(txn, WALLET, opts=opts)
        except Exception as e:
            print("Error occured while creating ata: ", str(e))
            return e
        
    else:
        print("Associated token account exists: ", ata)


async def swap(input, generatedRouteMap):
    # Check for any possible ARB opportunities
    while True:
        for token in generatedRouteMap[:150]:
            usdcToToken = await get_coin_quote(
                'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
                token,
                input
            )
            if usdcToToken.get('data'):
                tokenToUsdc = await get_coin_quote(
                    token,
                    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
                    usdcToToken.get('data')[0].get('otherAmountThreshold')
                )

                if tokenToUsdc.get('data'):
                    if tokenToUsdc.get('data')[0].get('otherAmountThreshold') > input:
                        await _create_associated_token_account(token)
                        await serialized_swap_transaction(usdcToToken.get('data')[0], tokenToUsdc.get('data')[0])
                        profit = tokenToUsdc.get('data')[0].get('otherAmountThreshold') - input
                        print("Approx Profit made: ", profit / USDC_BASE)
    

if __name__ == '__main__':
    generatedRouteMap = get_route_map()
    asyncio.run(swap(INPUT_USDC_AMOUNT, generatedRouteMap))