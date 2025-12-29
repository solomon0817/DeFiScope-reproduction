SUPPORTED_NETWORK = {
    # platform name: {prefix in the crytic_compile, quick node api, explorer api prefix, command in flatting (check in cryticparser), explorer api key, address of wrapped stable coin}
    "ethereum": {
        "name":"mainnet", 
        "chain_id": "1",
        "quick_node":"", 
        "api_prefix":".etherscan.io", 
        "key_command": "--etherscan-apikey", 
        "api_key": "",
        "stable_coin": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", # WETH
        "symbol": "WETH",
        },
    "bsc": {
        "name":"bsc", 
        "chain_id": "56",
        "quick_node":"", 
        "api_prefix":".bscscan.com", 
        "key_command": "--etherscan-apikey",
        "api_key": "",
        "stable_coin": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", # WBNB
        "symbol": "WBNB",
        },
}