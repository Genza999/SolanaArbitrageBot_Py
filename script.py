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


# This is a script to perform arbitrage on the solana network using python

solana_client = AsyncClient('https://api.mainnet-beta.solana.com')

# Fetch your wallet using the secret key
wallet = Keypair.from_secret_key(based58.b58decode('xxx'.encode("ascii")))


def get_mint(index, indexedRouteMap):
   return indexedRouteMap['mintKeys'][int(index)]

def get_route_map():
    # You could do this

    # generatedRouteMap = {}
    # indexedRouteMap = requests.get('https://quote-api.jup.ag/v1/indexed-route-map').json()
    # for key, index in indexedRouteMap['indexedRouteMap'].items():
    #     generatedRouteMap[get_mint(key, indexedRouteMap)] = list(map(lambda item: get_mint(item, indexedRouteMap) ,indexedRouteMap['indexedRouteMap'][key]))
    # print("the generatedRouteMap: ", generatedRouteMap['EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'])
    # return generatedRouteMap

    # or use the usdc_swaps.py file directly
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
                'userPublicKey': str(wallet.public_key),
                'wrapUnwrapSOL': False
            },
            timeout=15.0
        )
       return r.json()


async def execute_trancation(transacx):
    # Execute transactions
    opts = TxOpts(skip_preflight=True)
    for tx_name, raw_transaction in transacx.items():
        if raw_transaction:
            try:
                transaction = Transaction.deserialize(base64.b64decode(raw_transaction))
                tx = await solana_client.send_transaction(transaction, wallet, opts=opts)
                print("tx result: ", tx)
                txid = tx.get("result")
                print(f"transaction details :https://solscan.io/tx/{txid}")
            except Exception as e:
                print("Error occured at ex tx: ", str(e))
                return str(e)

async def serialized_swap_transaction(usdcToTokenRoute, tokenToUsdcRoute):
    if usdcToTokenRoute:
        try:
            usdcToTokenTransaction = await get_coin_swap_quote(usdcToTokenRoute)
            await execute_trancation(usdcToTokenTransaction )
        except Exception as e:
            print("Error occured at ser usdctotoken: ", str(e))
            return str(e)

        if tokenToUsdcRoute:
            try:
                tokenToUsdcTransaction = await get_coin_swap_quote(tokenToUsdcRoute)
                await execute_trancation(tokenToUsdcTransaction)
            except Exception as e:
                print("Error occured at ser tokentousdc: ", str(e))
                return str(e)

async def _create_associated_token_account(token):
    # Create Associated token account if not available
    token_associated_account = get_associated_token_address(
        wallet.public_key,
        PublicKey(token)
    )
    opts = TxOpts(skip_preflight=True)
    ata = await solana_client.get_account_info(PublicKey(token_associated_account))
    if not ata.get('result').get('value'):
        try:
            instruction = create_associated_token_account(
                wallet.public_key,
                wallet.public_key,
                PublicKey(token)
            )
            txn = Transaction().add(instruction)
            txn.recent_blockhash = await solana_client.get_recent_blockhash()
            resp = await solana_client.send_transaction(txn, wallet, opts=opts)
            print("Response:", resp)
        except Exception as e:
            print("Error occured while creating ata: ", str(e))
        
    else:
        print("Associated token account exists: ", ata)

    return ata

async def swap(input, generatedRouteMap):

    while True:
        print('**********************************************************')
        print('\n\n')
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
                    usdcToToken.get('data')[0].get('outAmountWithSlippage')
                )

                if tokenToUsdc.get('data'):
                    if tokenToUsdc.get('data')[0].get('outAmountWithSlippage') > input:
                        print("=========> Bingo:", token, " || ", tokenToUsdc.get('data')[0].get('outAmountWithSlippage') / 1000000)
                        ata_created = await _create_associated_token_account(token)
                        await serialized_swap_transaction(usdcToToken.get('data')[0], tokenToUsdc.get('data')[0])
                        profit = tokenToUsdc.get('data')[0].get('outAmountWithSlippage') - input
                        print("Approx Profit made: ", profit / 1000000)
    

if __name__ == '__main__':
    generatedRouteMap = get_route_map()
    # Swap 5 USDC
    asyncio.run(swap(5000000, generatedRouteMap))
